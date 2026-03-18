# Veo Workflow Design

> **Status: COMPLETED** — CLI `veo`, `finalize` 서브커맨드 구현 완료. Dialogue-in-Prompt 방식으로 전환됨.

## 목적
Veo 3.1로 대사 포함 캐릭터 영상 생성 → 후처리(자막/BGM) → YouTube 업로드.

## 전체 워크플로우

```
[1] 프롬프트 작성 (veo-shorts-writer 스킬 또는 수동)
    - 2파트 Veo prompt (대사 직접 포함)
    - dialogue 필드 (자막용)

[2] Veo 3.1 영상 생성 + extend
    - Part 1 create (8초)
    - Part 2 extend (+7초 = 15초)
    - 캐릭터가 한국어 대사를 직접 발화 (lip sync)

[3] (선택) EasyOCR + LaMa 인페인팅
    - 깨진 Veo 텍스트 제거

[4-6] finalize (자동)
    - 오디오(WAV) 추출
    - Whisper → SRT + 대사 텍스트 교정
    - 자막 burn + BGM 믹싱

[7] YouTube 업로드 (선택)
```

## CLI 인터페이스

### veo: prompt-file → Veo → finalize
```bash
uv run python Backend/cli.py veo \
  --prompt-file prompts.json \
  --image path/to/your/character.png \
  --language ko \
  --upload \
  -o output/2026-03-13/final/d03_공감_잃고얻는재물.mp4
```

### finalize: 기존 영상 + 자막/BGM
```bash
uv run python Backend/cli.py finalize \
  --video raw/video.mp4 \
  --music contents/musics/bgm.mp3 \
  --script "대사1\n대사2" \
  --upload \
  -o output/final/video.mp4
```

## 옵션

### veo
| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `subject` | - | 주제 (LLM이 프롬프트 자동 생성) |
| `--prompt` | - | 직접 Veo 프롬프트 |
| `--prompt-file` | - | JSON 프롬프트 파일 |
| `--image` | - | 레퍼런스 이미지 경로 |
| `--parts` | 2 | 파트 수 (Part 1: 8초 create + Part 2: 7초 extend = 15초) |
| `--veo-model` | env `VEO_MODEL` | Veo 모델 ID |
| `--language` | ko | 자막 언어 |
| `--font-size` | 55 | 자막 폰트 크기 |
| `--no-finalize` | False | finalize 건너뛰기 |
| `--clean-subs` | False | EasyOCR 깨진 자막 감지/제거 |
| `--add-narration` | False | TTS 나레이션 오버레이 (기본: 대사가 영상에 포함) |
| `--upload` | False | YouTube 업로드 |

### finalize
| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--video` | (필수) | 입력 영상 |
| `--music` | - | 배경음악 파일 |
| `--music-volume` | 0.10 | BGM 볼륨 (0.0~1.0) |
| `--script` | - | 대사 텍스트 (자막 교정용) |
| `--subs-position` | center,bottom | 자막 위치 |
| `--subs-color` | #FFFF00 | 자막 색상 |
| `--font-size` | 55 | 자막 폰트 크기 |
| `--upload` | False | YouTube 업로드 |

## 파일 구조
| File | Responsibility |
|------|---------------|
| `Backend/cli.py` | CLI: veo, finalize, compose, generate 서브커맨드 |
| `Backend/veo.py` | Veo API: single/multi-part 생성, extend, 자막 감지 |
| `Backend/finalize.py` | 후처리: 크롭, Whisper 자막, 교정, BGM, 업로드 |
| `Backend/workflow.py` | Veo 프롬프트 정규화, 스크립트 추출 |
| `Backend/narrate.py` | TTS 나레이션 오버레이 (legacy, `--add-narration` 시) |
