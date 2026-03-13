# Veo Shorts 프로덕션 파이프라인

## 개요

사주/운세 주제의 유튜브 쇼츠를 제작하는 end-to-end 파이프라인.
Veo 3.1로 3D 애니메이션 영상을 생성하고, 후처리로 깨진 텍스트 제거 → 자막 → BGM → YouTube 업로드까지 진행한다.

## 전체 흐름

```
[1] 프롬프트 작성 (veo-shorts-writer 스킬)
    ↓
[2] Veo 3.1 영상 생성 (2파트 extend)
    ↓
[3] EasyOCR + LaMa 인페인팅 (깨진 텍스트 제거)
    ↓
[4] ffmpeg 프레임 조립 + 원본 오디오 머지
    ↓
[5] Whisper 타이밍 추출 → 수동 SRT 작성
    ↓
[6] 자막 번 + BGM 믹싱 (finalize)
    ↓
[7] YouTube 업로드
```

## 1. 프롬프트 작성

### 스킬
`veo-shorts-writer` — 사주/운세 주제 VEO 프롬프트 + 한국어 대사 생성.

### 출력 포맷
```json
[
  {
    "prompt": "영어 VEO 프롬프트 (대사 부분만 한국어)",
    "dialogue": "한국어 대사 텍스트"
  },
  { "prompt": "...", "dialogue": "..." }
]
```

### 프롬프트 규칙
- `"3D animated character style"` 명시 — NOT live action, NOT realistic
- `"ABSOLUTELY NO MUSIC"` 명시 (Veo가 임의로 BGM 추가하는 경향)
- 레퍼런스 이미지 스타일을 모든 파트에서 일관 유지
- 대사를 프롬프트 안에 직접 포함: `Exact spoken Korean dialogue: "대사"`
- 9:16 세로 비율 명시

### 저장 위치
```
output/YYYY-MM-DD/prompts/d{일차}_{포맷}_{키워드}.json
```

## 2. Veo 3.1 영상 생성

```python
from veo import generate_multi_part_video

result = generate_multi_part_video(
    prompts=prompts,              # JSON에서 로드
    output_path="output/.../raw/파일명.mp4",
    image_path="contents/character/jeong_bin/jeongbin_사색.png",  # 레퍼런스
)
```

- **모델**: `veo-3.1-generate-preview` (Vertex AI)
- **구성**: Part 1 (8초) + Part 2 extend (+7초) = 약 15초
- **해상도**: 720x1280 (9:16)
- **타임아웃**: 600초 (환경변수 `VEO_MAX_WAIT_SECONDS`로 조정 가능)
- **출력**: `output/YYYY-MM-DD/raw/` 디렉토리

### 캐릭터 이미지 (레퍼런스)
| 파일 | 용도 |
|------|------|
| `jeongbin_사색.png` | 진지/심각한 주제 |
| `jeongbin_미소.png` | 따뜻한/긍정적 주제 |
| `jeongbin_정면.png` | 범용 |
| `jeongbin_사색_폰.png` | 폰 관련 장면 |

## 3. EasyOCR + LaMa 인페인팅

Veo가 영상 프레임 안에 깨진 한글 텍스트를 생성하는 경우가 빈번함.
위치는 매번 다르고, "사주", "C", 깨진 한글 등이 나타남.

### 스캔
```python
import cv2, easyocr
reader = easyocr.Reader(['ko', 'en'], gpu=False)

# 샘플 프레임에서 텍스트 감지
for fi in [0, 45, 90, 135, 180, 225, 270, 315, 355]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    results = reader.readtext(frame, paragraph=False)
```

### 인페인팅
```python
from simple_lama_inpainting import SimpleLama
lama = SimpleLama()

for fi in range(total_frames):
    results = reader.readtext(frame, paragraph=False)
    if results:
        mask = np.zeros((h, w), dtype=np.uint8)
        for (bbox, text, conf) in results:
            if conf < 0.01: continue
            pts = np.array(bbox, dtype=np.float32)
            center = pts.mean(axis=0)
            pts_dilated = ((pts - center) * 1.4 + center).astype(np.int32)  # 1.4x 확장
            cv2.fillPoly(mask, [pts_dilated], 255)
        result_pil = lama(frame_pil, mask_pil)
    cv2.imwrite(f'/tmp/frames/{fi:04d}.png', frame)
```

### 주의사항
- **OpenCV VideoWriter 사용 금지**: macOS에서 mp4v 코덱이 corrupt MP4 생성
- **PNG 프레임 저장 → ffmpeg 조립** 방식 사용
- bbox 확장 비율 1.3~1.4x가 적절 (너무 크면 캐릭터 훼손)
- 고정 마스크는 손/캐릭터 지울 위험 → EasyOCR per-frame 방식이 안전

## 4. ffmpeg 프레임 조립

```bash
ffmpeg -y \
  -framerate 24 \
  -i /tmp/frames/%04d.png \
  -i original_video.mp4 \
  -map 0:v:0 -map 1:a:0 \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -shortest \
  clean_video.mp4
```

## 5. 자막 타이밍

### Whisper로 raw 타이밍 추출
```python
from video import generate_subtitles
srt_path = generate_subtitles(audio_path=audio, sentences=[], audio_clips=[], voice='ko')
```

### 수동 SRT 작성
Whisper 타이밍을 참고하여 대사별로 수동 SRT 작성.
자동 그룹핑이 1블록으로 합쳐지는 경우가 있으므로 수동이 안정적.

```srt
1
00:00:00,000 --> 00:00:03,780
첫 번째 대사

2
00:00:04,220 --> 00:00:07,880
두 번째 대사

3
00:00:10,100 --> 00:00:14,460
세 번째 대사
```

## 6. Finalize (자막 번 + BGM)

### finalize 파이프라인 사용 시
```python
from finalize import run_finalize_pipeline

result = run_finalize_pipeline(
    video_path='raw/clean_video.mp4',
    output_path='final/output.mp4',
    crop=False,                              # 이미 9:16
    script="대사1\n대사2\n대사3",              # 자막 보정용
    music_path='contents/musics/bgm_옥산의메아리.mp3',
    music_volume=0.15,
    font_size=48,
    subs_color='#FFFFFF',
)
```

### 수동 SRT로 직접 굽기 (자동 그룹핑 실패 시)
```python
from ffmpeg_utils import render_subtitled_video, mux_video_audio

# 자막 번
rendered = render_subtitled_video(
    video_path, audio_path, srt_path,
    'center,bottom', '#FFFFFF',
    font_size=48, custom_font='/System/Library/Fonts/AppleSDGothicNeo.ttc',
)

# BGM 믹싱
vid = VideoFileClip(rendered)
music = AudioFileClip(bgm_path)
music = music.with_effects([afx.AudioLoop(duration=vid.duration)])
music = music.with_volume_scaled(0.15).with_fps(44100)
mixed = CompositeAudioClip([vid.audio, music]).with_duration(vid.duration)

# 최종 머지
mux_video_audio(rendered, mixed_path, final_output)
```

### 설정값
| 항목 | 값 |
|------|-----|
| BGM 볼륨 | 0.15 (15%) |
| 폰트 | AppleSDGothicNeo.ttc |
| 폰트 크기 | 48 |
| 자막 색상 | #FFFFFF |
| 자막 위치 | center,bottom |

## 7. YouTube 업로드

```python
from youtube import upload_video

response = upload_video(
    video_path='final/output.mp4',
    title='제목',
    description='설명\n\n#해시태그',
    category='22',              # People & Blogs
    keywords='사주,재물운,...',
    privacy_status='public',
)
video_id = response['id']
```

### OAuth 설정
- 토큰 파일: `Backend/youtube-oauth2.json` (고정 경로, `sys.argv` 무관)
- 채널 ID: `UCV4fN1vnlY-o4gqlqRr_duw`

## 디렉토리 구조

```
output/
  YYYY-MM-DD/
    prompts/    # Veo 프롬프트 JSON
    raw/        # Veo 원본 + 인페인팅 결과 (_clean.mp4)
    final/      # 자막+BGM 합성 최종 영상
    separated/  # demucs 분리 결과 (필요 시)

contents/
  character/jeong_bin/   # 캐릭터 레퍼런스 이미지
  musics/                # BGM 파일
  plans/                 # 콘텐츠 기획서
```

## 파일 네이밍 규칙

```
d{일차}_{포맷}_{키워드}.json/mp4
```
- 포맷: 공감 / 유형 / 조언
- 예: `d03_공감_잃고얻는재물.mp4`
- 폐기본: `_폐기` 접미사

## 콘텐츠 현황

| 날짜 | 제목 | Video ID | 유형 |
|------|------|----------|------|
| 2026-03-09 | 수기운 강한 사람의 존재감 | TS_Hb8Jj99I | 유형 |
| 2026-03-09 | 판이 바뀌는 신호 | g_OKUUsih_A | 공감 |
| 2026-03-10 | 답장 보류의 지혜 | tgaPfJcojCw | 조언 |
| 2026-03-12 | 화기운 강한 사람의 연애 | PQP8uSgCKXo | 유형 |
| 2026-03-12 | 돈이 들어오기 직전의 조짐 | sPaeerSemo4 | 공감 |
| 2026-03-13 | 재물운 트이기 전 잃는 것들 | C_PQ6gr2kWw | 공감 |
