# MoneyPrinter

AI 영상 생성으로 유튜브 쇼츠 제작을 자동화합니다. 프롬프트를 작성하고, Google Veo 3.1로 영상을 생성하고, 자막을 넣고, 유튜브에 업로드 — 명령어 하나로 끝.

> [English README](../README.md)

## 어떻게 동작하나요?

```
프롬프트 JSON → Veo 3.1 API → 15초 AI 영상 → Whisper 자막 → YouTube 업로드
```

1. 캐릭터, 장면, 대사를 담은 프롬프트를 작성합니다
2. Veo 3.1이 15초 세로 영상을 생성합니다 (8초 생성 + 7초 연장, 립싱크 포함)
3. Whisper가 음성을 인식하고, 스크립트에 맞게 자막을 교정합니다
4. 완성된 영상이 유튜브 쇼츠로 업로드됩니다

**다국어 지원** — 한국어, 영어, 일본어, 중국어 등 대사와 자막 모두 가능합니다.

## 비용

Veo 3.1은 유료 API입니다. 15초 영상 1개 기준 예상 비용:

| 모델 | 초당 비용 | 영상당 (15초) | 비고 |
|------|----------|--------------|------|
| Standard (`veo-3.1-generate-preview`) | ~$0.40 | ~$6.00 | 프로덕션 권장 |
| Fast (`veo-3.1-fast-generate-preview`) | ~$0.15 | ~$2.25 | 품질 낮음, 캐릭터 불일치 |

Standard 모델을 권장합니다. Fast 모델은 파트 간 캐릭터 일관성이 깨지는 문제가 있습니다.

## 빠른 시작

### 사전 요구사항

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python 패키지 매니저)
- FFmpeg (`brew install ffmpeg` / `apt install ffmpeg`)
- Google Cloud 프로젝트 ([Veo API](https://cloud.google.com/vertex-ai/generative-ai/docs/video/overview) 활성화 필요)

### 1. 설치

```bash
git clone https://github.com/kangnam/MoneyPrinter.git
cd MoneyPrinter
uv sync
cp .env.example .env
```

### 2. 설정

`.env` 파일 수정:
```env
GOOGLE_API_KEY="your-google-api-key"

# Vertex AI 모드 (프로덕션 권장):
VEO_USE_VERTEX="true"
GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
```

### 3. 프롬프트 작성

`my_prompt.json` 파일 생성:

```json
[
  {
    "prompt": "A cinematic vertical short-form video, 9:16. 3D animated character style matching the reference image — NOT live action. She stands in a dark mystical space with golden particles floating around her. Close-up on her face. Camera slowly pulls back.\n\nExact spoken Korean dialogue:\n\"안녕, 중요한 얘기가 있어.\"\n\"이게 모든 걸 바꿀 수도 있어.\"\n\nABSOLUTELY NO MUSIC. No subtitles. No on-screen text.",
    "dialogue": "안녕, 중요한 얘기가 있어.\n이게 모든 걸 바꿀 수도 있어."
  },
  {
    "prompt": "Continue the same scene in the SAME style. She remains standing, wearing the EXACT same outfit and colors. The golden particles glow warmer. She looks directly at the camera.\n\nExact spoken Korean dialogue:\n\"이 순간을 기억해.\"\n\nABSOLUTELY NO MUSIC. No subtitles.",
    "dialogue": "이 순간을 기억해."
  }
]
```

### 4. 영상 생성

```bash
uv run python Backend/cli.py veo \
  --prompt-file my_prompt.json \
  --image path/to/your/character.png \
  --language ko --font-size 55 \
  -o output/my_video.mp4
```

`--upload` 옵션을 추가하면 유튜브에 바로 업로드됩니다 ([YouTube 설정 가이드](youtube-setup.md) 참고).

## CLI 명령어

### `veo` — 전체 파이프라인

```bash
uv run python Backend/cli.py veo \
  --prompt-file prompts.json \
  --image character.png \
  --language ko \
  --font-size 55 \
  --upload \
  --upload-title "영상 제목" \
  -o output/final/video.mp4
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--prompt-file` | (필수) | 프롬프트 + 대사 JSON 파일 |
| `--image` | 없음 | 캐릭터 레퍼런스 이미지 |
| `--language` | `ko` | 자막 언어 코드 |
| `--font-size` | `55` | 자막 폰트 크기 |
| `--veo-model` | env `VEO_MODEL` | Veo 모델 ID |
| `--upload` | false | 유튜브 업로드 |
| `--upload-title` | 자동 | 유튜브 영상 제목 |
| `-o` | 자동 | 출력 파일 경로 |

### `finalize` — 기존 영상에 자막 추가

```bash
uv run python Backend/cli.py finalize \
  --video raw_video.mp4 \
  --music bgm.mp3 --music-volume 0.10 \
  --script "대사 1줄\n대사 2줄" \
  --upload \
  -o output/final/video.mp4
```

### `auth` — YouTube OAuth 인증

```bash
uv run python Backend/cli.py auth
```

자세한 설정은 [YouTube 설정 가이드](youtube-setup.md)를 참고하세요.

## 프롬프트 작성 팁

Veo 3.1 실전 운영 경험에서 검증된 규칙:

| 규칙 | 이유 |
|------|------|
| 배경은 "dark mystical space" | 구체적 장소(연못, 숲)는 캐릭터 배치 오류 발생 |
| 캐릭터는 항상 "stands" | 앉기/눕기는 비정상 포즈로 렌더링 |
| 배경 효과는 particles/dust/orbs만 | 동물, 건축물은 품질 저하 |
| 물/액체 묘사 금지 | 캐릭터가 물에 잠김 |
| 카메라: close-up → pull back | 복잡한 카메라 움직임은 불안정 |
| 이펙트: "slowly glow", "gradually drift" | "bursting/exploding"은 촌스러움 |
| Part 2에 "wearing the EXACT same outfit" | 파트 간 의상 색상 변경 방지 |
| "ABSOLUTELY NO MUSIC" | Veo가 자의로 BGM 추가함 |
| "No text, no subtitles" | Veo가 깨진 텍스트를 생성함 |
| Standard 모델 사용 | Fast 모델은 파트 간 캐릭터 일관성 파괴 |

나만의 캐릭터 세팅은 [캐릭터 가이드](character-guide.md)를 참고하세요.

## 설정

`.env.example`을 `.env`로 복사하고 키를 설정하세요. 전체 변수 목록은 [configuration.md](configuration.md)를 참고하세요.

### 필수

| 변수 | 설명 |
|------|------|
| `GOOGLE_API_KEY` | Google AI API 키 |
| `VEO_USE_VERTEX` | Vertex AI 모드 (`true` 권장) |
| `GOOGLE_CLOUD_PROJECT` | GCP 프로젝트 ID (Vertex 사용 시) |

## 테스트

```bash
uv run python -m pytest tests/ -q                    # 398 tests
uv run python -m pytest --cov --cov-fail-under=90    # 91% coverage
```

## 문서

- [Configuration (환경 설정)](configuration.md)
- [YouTube Setup (유튜브 설정)](youtube-setup.md)
- [Character Guide (캐릭터 가이드)](character-guide.md)
- [Veo Cost (비용 안내)](veo-cost.md)
- [Architecture (아키텍처)](architecture.md)
- [Docker](docker.md)
- [Testing (테스트)](testing.md)
- [Troubleshooting (문제 해결)](troubleshooting.md)

## 라이선스

[LICENSE](../LICENSE) 파일 참고.

## 크레딧

[FujiwaraChoki/MoneyPrinter](https://github.com/FujiwaraChoki/MoneyPrinter)에서 포크. Veo 3.1 파이프라인, Whisper 자막, YouTube 자동화를 추가했습니다.
