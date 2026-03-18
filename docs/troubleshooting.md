# Troubleshooting

## Veo Pipeline

### 캐릭터가 물에 잠기거나 이상한 포즈
프롬프트에 구체적 장소(연못, 숲)나 "sits/lies" 포즈를 지정하면 VEO가 잘못 해석함.
- "dark mystical space" + "She stands" 조합을 사용
- 물/액체 묘사 제거, 부유 입자(particles, orbs)로 대체

### 파트 간 캐릭터/의상 불일치
Part 2 프롬프트에 의상 고정 문구 추가:
```
wearing the EXACT same outfit and colors as Part 1
```

### Veo Fast 모델 캐릭터 깨짐
`veo-3.1-fast-generate-preview`는 레퍼런스 이미지 반영이 불안정. 파트 간에도 캐릭터가 달라짐.
프로덕션은 반드시 Standard 모델(`veo-3.1-generate-preview`) 사용.

### Veo 타임아웃
`VEO_MAX_WAIT_SECONDS` 환경변수로 대기 시간 조정 (기본 600초).

### 깨진 한글 텍스트가 영상에 나타남
EasyOCR + LaMa 인페인팅으로 제거. `--clean-subs` 옵션 또는 수동 처리.
자세한 방법: [Production Pipeline](veo-workflow/production-pipeline.md) 참고.

### YouTube 업로드 실패
- `Backend/client_secret.json` 존재 확인
- `Backend/youtube-oauth2.json` 토큰 유효성 확인
- `uv run python Backend/cli.py auth` 로 재인증

---

## Stock Footage Pipeline

## No Ollama models in dropdown

- Ensure Ollama is running: `ollama serve`
- Ensure at least one model exists: `ollama list`
- Pull a model if needed: `ollama pull llama3.1:8b`
- Verify backend can reach Ollama base URL in `.env` (`OLLAMA_BASE_URL`)

## Frontend cannot connect to backend

- Confirm backend is running on port `8080`
- Confirm frontend is opened from local server (for example `python3 -m http.server`)
- Check browser console/network for `/api/generate` or `/api/models` failures

## ImageMagick not detected

- Install ImageMagick and ensure executable is on `PATH`
- Or set explicit path in `.env`, for example:

```env
IMAGEMAGICK_BINARY="/usr/local/bin/magick"
```

Windows example:

```env
IMAGEMAGICK_BINARY="C:\\Program Files\\ImageMagick-7.1.1-Q16-HDRI\\magick.exe"
```

## No stock videos found

- Verify `PEXELS_API_KEY` is valid
- Try a broader video subject
- Retry generation; stock results vary by query

## Subtitles fail

- If using AssemblyAI, verify `ASSEMBLY_AI_API_KEY`
- If not using AssemblyAI, local subtitle generation should still work

## YouTube upload skipped

- Place `client_secret.json` inside `Backend/`
- Enable required YouTube scopes and OAuth consent in Google Cloud
