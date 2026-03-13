# Veo API Integration Design

## Overview

Veo API를 MoneyPrinter에 통합하여 "주제 입력 → 영상 생성 → 후처리 → 업로드" 전 과정을 자동화한다.

## Pipeline

```
subject (text)
  → LLM: 스크립트 생성 (gpt.py - generate_script)
  → LLM: Veo 프롬프트 생성 (gpt.py - generate_veo_prompt) [NEW]
  → Veo API: 영상 생성 (veo.py - generate_video) [NEW]
  → finalize: 자막 + 음악 + 크롭 + 업로드 (finalize.py - 기존)
```

## New Module: `Backend/veo.py`

### Functions

```python
def generate_video(
    prompt: str,
    output_path: str = "",
    aspect_ratio: str = "9:16",
    resolution: str = "720p",
    duration: str = "8",
    model: str = "veo-3.1-generate-preview",
    on_log=None,
) -> str:
    """Veo API로 영상 생성, 완료까지 폴링, 파일 저장 후 경로 반환."""
```

### Config

| env var | default | description |
|---------|---------|-------------|
| `GOOGLE_API_KEY` | (required) | Google AI API key |
| `VEO_MODEL` | `veo-3.1-generate-preview` | Veo model ID |
| `VEO_ASPECT_RATIO` | `9:16` | 기본 비율 |
| `VEO_RESOLUTION` | `720p` | 기본 해상도 |

## New LLM Function: `generate_veo_prompt`

스크립트를 Veo에 최적화된 영상 생성 프롬프트로 변환.
- 카메라 앵글, 조명, 분위기 등 시각적 디테일 추가
- 대사가 있으면 대사 유지 (Veo 3.1 오디오 내장)

## CLI: `veo` subcommand

```bash
# 주제만 입력하면 스크립트 → 영상 → 후처리까지 자동
cli.py veo "사주로 알아보는 돈복" --language ko --upload

# 직접 프롬프트로 영상만 생성
cli.py veo --prompt "A man..." --no-finalize
```

### Options

| flag | default | description |
|------|---------|-------------|
| `subject` | (positional) | 영상 주제 |
| `--prompt` | | 직접 Veo 프롬프트 (subject 대신) |
| `--model` | env VEO_MODEL | Veo 모델 |
| `--aspect-ratio` | `9:16` | 화면 비율 |
| `--resolution` | `720p` | 해상도 |
| `--duration` | `8` | 영상 길이 (초) |
| `--language` | `ko` | 자막 언어 |
| `--font-size` | `55` | 자막 크기 |
| `--no-finalize` | false | 후처리 스킵 (영상만 생성) |
| `--upload` | false | YouTube 업로드 |
| `-o` | auto | 출력 경로 |

## SwiftUI App Update

ContentView에 "주제 입력" 필드 + "Veo 생성" 버튼 추가.
`PipelineRunner`가 `cli.py veo` 서브커맨드 호출.

## Dependencies

- `google-genai` 패키지 추가 (`uv add google-genai`)
