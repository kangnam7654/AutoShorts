# Testing

MoneyPrinter uses `pytest` with `pytest-cov` for backend tests. Current: **397 tests, 91% coverage**.

## Install test dependencies

```bash
uv sync --group dev
```

## Run tests

```bash
uv run python -m pytest tests/ -q                          # all tests
uv run python -m pytest tests/test_veo.py::TestTimeout -q  # single test
uv run python -m pytest --cov --cov-fail-under=90          # coverage check
```

## Test structure

### Unit tests
- `test_gpt.py`, `test_gpt_extended.py`: LLM client (Ollama/OpenAI/Codex), script/prompt generation
- `test_veo.py`, `test_veo_extended.py`: Veo API client, operation polling, multi-part generation
- `test_video.py`, `test_video_extended.py`: Video processing, subtitle language codes, Whisper SRT
- `test_tiktokvoice.py`, `test_tiktokvoice_extended.py`: TikTok TTS endpoint selection, chunked audio
- `test_qwen_tts.py`: Qwen3-TTS local model
- `test_tts_utils.py`: TTS provider routing, voice defaults
- `test_ffmpeg_utils.py`: FFmpeg wrappers (mux, subtitle render)
- `test_codex_auth.py`, `test_codex_auth_extended.py`: OAuth2 PKCE flow
- `test_cli.py`, `test_cli_extended.py`: CLI dispatch, command handlers
- `test_finalize.py`, `test_finalize_helpers.py`: Finalize pipeline, SRT parsing/correction
- `test_pipeline.py`: Stock footage generation pipeline
- `test_youtube.py`: YouTube upload, OAuth, retry logic
- `test_models.py`: ORM model CRUD, relationships
- `test_db.py`: Database engine setup
- `test_utils.py`, `test_utils_extended.py`: Env validation, ImageMagick detection, LogStream
- `test_worker.py`: Worker loop behavior
- `test_workflow.py`: Veo prompt normalization
- `test_narrate.py`, `test_compose.py`, `test_search.py`, `test_logstream.py`: Other modules

### Integration tests
- `test_integration.py`: Multi-module flows (generation, finalize, compose, veo)
- `test_api_jobs.py`, `test_api_misc.py`: Flask API endpoints
- `test_repository.py`: Database queue/repository operations

### E2E tests
- `test_e2e_generation.py`: Full stock-video pipeline with mocked externals, BGM, cancellation

### Test fixtures
- `conftest.py`: Isolated in-memory SQLite session per test, mocked `DATABASE_URL`

## Mock boundaries

External I/O is always mocked in unit tests:
- LLM: `gpt.generate_response`, `gpt._generate_ollama`, `gpt._generate_openai`
- Veo API: `google.genai` client
- FFmpeg/ffprobe: `subprocess.run`
- Whisper: `mlx_whisper.transcribe`
- TTS: `tiktokvoice.get_api_response`, `qwen_tts` model
- YouTube: `youtube.upload_video`
- HTTP: `requests.get`
