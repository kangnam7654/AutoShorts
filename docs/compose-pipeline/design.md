# Compose Pipeline Design

## 목적
외부에서 생성한 영상(Veo 등) + 스크립트를 입력받아 TTS, 자막, 합성을 자동화.

## 입력
- **영상 파일**: Veo로 생성한 MP4 (사운드 포함 가능)
- **스크립트**: 나레이션할 텍스트 (직접 입력 또는 파일)

## 파이프라인

```
[영상 파일] + [스크립트 텍스트]
         │
         ▼
    ┌─────────────┐
    │  Qwen TTS   │ 스크립트 → WAV 음성
    └─────┬───────┘
          ▼
    ┌─────────────┐
    │   Whisper    │ WAV → SRT 자막 (단어 타이밍)
    └─────┬───────┘
          ▼
    ┌─────────────┐
    │  합성/렌더   │ 영상 + 음성 + 자막 → output.mp4
    │  (moviepy)   │ 원본 오디오: 제거 or 배경으로 믹스
    └─────┬───────┘
          ▼
    ┌─────────────┐
    │  YouTube     │ (선택) 업로드
    └─────────────┘
```

## CLI 인터페이스

```bash
# 스크립트 직접 입력
uv run python Backend/cli.py compose \
  --video /path/to/veo.mp4 \
  --script "The ocean covers more than 70 percent of Earth..." \
  --voice Ryan \
  --upload

# 스크립트 파일
uv run python Backend/cli.py compose \
  --video /path/to/veo.mp4 \
  --script-file /path/to/script.txt \
  --voice Ryan

# 원본 오디오 유지 (배경)
uv run python Backend/cli.py compose \
  --video /path/to/veo.mp4 \
  --script "..." \
  --keep-audio
```

## 옵션
| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--video` | (필수) | 입력 영상 경로 |
| `--script` | - | 나레이션 텍스트 |
| `--script-file` | - | 나레이션 텍스트 파일 |
| `--voice` | Ryan | Qwen TTS 음성 |
| `--keep-audio` | False | 원본 오디오를 배경(10%)으로 유지 |
| `--subs-position` | center,center | 자막 위치 |
| `--subs-color` | #FFFF00 | 자막 색상 |
| `--upload` | False | YouTube 업로드 |
| `--output` | output.mp4 | 출력 경로 |

## 파일 변경
| File | Action |
|------|--------|
| `Backend/compose.py` | 신규 - compose 파이프라인 |
| `Backend/cli.py` | compose 서브커맨드 추가 |
