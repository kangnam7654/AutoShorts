# Veo Workflow Design

## 목적
Veo로 생성한 무성 캐릭터 영상 + 후처리 나레이션 + 자막/음악 합성 → YouTube 업로드.

## 전체 워크플로우

```
[1] LLM: 3파트 워크플로우 생성 (자동)
    - part별 Veo prompt
    - narration/dialogue
    - 장면 설명
    - voice profile

[2] Veo 영상 생성 + extend (자동)
    - Part 1 생성
    - Part 2/3 extend
    - 캐릭터는 침묵, ambient sound only

[3] Narration 합성 (자동)
    ┌─────────────────────────┐
    │  Qwen/TikTok TTS        │
    │  또는 user-owned clone  │
    └─────────┬───────────────┘
              ▼
    ┌─────────────────────────┐
    │  원본 ambient와 믹스     │
    │  narrated video 생성     │
    └─────────┬───────────────┘
              ▼

[4-6] finalize 명령어 (자동)
    ┌─────────────────────────┐
    │  narrated video에서      │
    │  오디오(WAV) 추출        │
    └─────────┬───────────────┘
              ▼
    ┌─────────────────────────┐
    │  Whisper: WAV → SRT     │
    │  + optional LLM 보정      │
    └─────────┬───────────────┘
              ▼
    ┌─────────────────────────┐
    │  자막 + 배경음악 합성     │
    └─────────┬───────────────┘
              ▼
    ┌─────────────────────────┐
    │  YouTube 업로드 (선택)    │
    └─────────────────────────┘
```

## CLI 인터페이스

### veo: subject → Veo → narration → finalize
```bash
uv run python Backend/cli.py veo "사주로 보는 돈복" \
  --parts 3 \
  --language ko
```

### finalize: narrated Veo 영상 + 음악 → 자막 입힌 최종 영상
```bash
uv run python Backend/cli.py finalize \
  --video /path/to/veo_output.mp4 \
  --music /path/to/gemini_music.mp3 \
  --subs-position center,center \
  --subs-color "#FFFF00" \
  --upload \
  -o output.mp4
```

## 옵션

### finalize
| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--video` | (필수) | Veo 또는 narrated 출력 영상 |
| `--music` | - | Gemini Lyria 배경음악 파일 |
| `--music-volume` | 0.10 | 배경음악 볼륨 (0.0~1.0) |
| `--subs-position` | center,center | 자막 위치 |
| `--subs-color` | #FFFF00 | 자막 색상 |
| `--upload` | False | YouTube 업로드 |
| `-o, --output` | output.mp4 | 출력 경로 |

## 파일 변경
| File | Action |
|------|--------|
| `Backend/finalize.py` | 신규 - 오디오 추출 → 자막 → 합성 → 업로드 |
| `Backend/cli.py` | finalize 서브커맨드 추가, narrate 제거 |
