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

### 프롬프트 연출 규칙 (검증 기반)
- **배경은 추상적 공간** — "dark mystical space" 기본. 구체적 장소(연못, 숲) 지정 시 캐릭터 배치 오류 발생
- **캐릭터는 "stands"** — 앉기/눕기는 VEO가 비정상 포즈로 해석
- **배경 효과는 부유 입자만** — particles, dust, light orbs 등. 동물/건축물 금지
- **물/액체 묘사 금지** — 캐릭터가 물에 잠기는 결과 초래
- **카메라는 close-up → pull back** — 패닝/회전/빠른 컷 금지
- **이펙트 전환은 은은하게** — "bursting/exploding" 금지, "slowly glow/gradually drift" 사용
- **Part 2에 의상 고정** — "wearing the EXACT same outfit and colors as Part 1" 명시

### 모델 선택
- **Standard** (`veo-3.1-generate-preview`): 프로덕션용. 캐릭터 일관성 양호
- **Fast** (`veo-3.1-fast-generate-preview`): 프로덕션 부적합. 파트 간 캐릭터가 완전히 달라짐. 테스트용으로만 사용

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
    image_path="path/to/your/character.png",  # 레퍼런스 이미지
)
```

- **모델**: `veo-3.1-generate-preview` (Vertex AI)
- **구성**: Part 1 (8초) + Part 2 extend (+7초) = 약 15초
- **해상도**: 720x1280 (9:16)
- **타임아웃**: 600초 (환경변수 `VEO_MAX_WAIT_SECONDS`로 조정 가능)
- **출력**: `output/YYYY-MM-DD/raw/` 디렉토리

### 캐릭터 이미지 (레퍼런스)
`--image` 옵션으로 자신만의 캐릭터 이미지를 전달. Veo가 레퍼런스 이미지의 스타일을 영상에 반영한다.
- `contents/character/` 디렉토리에 캐릭터 이미지를 저장하는 것을 권장
- 표정/포즈별로 여러 이미지를 준비하면 다양한 연출 가능

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

## 5. 자막 생성 (자동)

finalize 파이프라인이 자동으로 처리:
1. Whisper로 오디오에서 타이밍 추출 (mlx-community/whisper-small-mlx)
2. `--script` 옵션의 대사 텍스트로 Whisper 인식 결과를 교정
3. 음성 gap 기반 자동 그룹핑 → SRT 생성

```bash
# CLI에서 자동 처리 (별도 작업 불필요)
uv run python Backend/cli.py veo \
  --prompt-file prompts.json --language ko --font-size 55 \
  -o output/final/video.mp4
```

대사 텍스트는 prompt JSON의 `dialogue` 필드에서 자동 추출.

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
  character/            # 캐릭터 레퍼런스 이미지 (사용자 추가)
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

각 사용자가 자신의 영상 업로드 현황을 이 테이블에서 관리할 수 있다.

| 날짜 | 제목 | Video ID | 유형 |
|------|------|----------|------|
| (예시) | 내 첫 번째 영상 | abc123 | 공감 |
