# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoShorts automates YouTube Shorts creation. Two main pipelines:

1. **Stock footage pipeline** (legacy) — Ollama script + Pexels stock clips + TikTok TTS + moviepy composition
2. **Veo pipeline** (primary) — Google Veo 3.1 AI video generation + Whisper subtitles + BGM mixing + YouTube upload

Output: 9:16 vertical video for YouTube Shorts.

## Commands

### Setup
```bash
cp .env.example .env        # then fill in API keys
uv sync                     # install dependencies
```

### Run (local)
```bash
uv run python Backend/main.py                              # API on :8080
uv run python Backend/worker.py                            # queue worker
python3 -m http.server 3000 --directory Frontend           # frontend on :3000
```

### Run (Docker)
```bash
docker compose up --build   # frontend :3000, backend :8080, postgres :5433
```

### CLI (Veo pipeline)
```bash
# Veo end-to-end: generate video + subtitles + upload
uv run python Backend/cli.py veo \
  --prompt-file prompts.json --language ko --upload \
  -o output/final/video.mp4

# Finalize only: add subtitles + BGM to existing video
uv run python Backend/cli.py finalize \
  --video raw.mp4 --music bgm.mp3 --script "대사" --upload

# Stock footage pipeline
uv run python Backend/cli.py generate "topic"
```

### Verify
```bash
uv run python -m compileall Backend          # syntax check
curl http://localhost:8080/api/models         # API smoke test
```

### Tests
```bash
uv run python -m pytest tests/ -q                          # all tests (397 tests)
uv run python -m pytest tests/test_file.py::test_name -q   # single test
uv run python -m pytest --cov --cov-fail-under=90          # coverage check (91%)
```

## Architecture

### Veo Pipeline (primary, end-to-end flow)

```
CLI: moneyprinter veo --prompt-file prompts.json
  → veo.py: generate_multi_part_video()
    → Part 1: Veo API create (8s)
    → Part 2: Veo API extend (+7s = 15s cumulative)
  → output/raw/{slug}_part1.mp4, _part2.mp4
  → (optional) detect_veo_subtitles() + clean (EasyOCR)
  → finalize.py: run_finalize_pipeline()
    → [1/6] Crop to 9:16 (face-aware)
    → [2/6] Extract audio (ffmpeg → WAV)
    → [3/6] Generate subtitles (mlx_whisper → .srt)
    → [4/6] Correct subtitle text (match script to Whisper timing)
    → [5/6] Burn subtitles (ffmpeg drawtext)
    → [6/6] Mix BGM (moviepy, 10% volume)
  → youtube.py: upload_video() (OAuth2)
  → output/final/{slug}.mp4
```

### Stock Footage Pipeline (legacy)

```
Frontend → POST /api/generate → generation_jobs (Postgres queue)
  → worker.py claims job
  → gpt.py: generate_script() via Ollama/OpenAI/Codex
  → search.py: Pexels API → stock clips
  → tiktokvoice.py / qwen_tts.py: TTS per sentence
  → video.py: combine + burn subtitles + merge audio
  → output.mp4
```

### Frontend <> Backend Communication
- **REST**: JSON payloads to Flask endpoints (`/api/generate`, `/api/jobs/:id`, `/api/jobs/:id/events`, `/api/jobs/:id/cancel`, `/api/models`, `/api/upload-songs`)
- **Polling**: frontend polls job status and persisted generation events.

### Key Backend Modules
| File | Responsibility |
|------|---------------|
| `cli.py` | CLI entry point: `veo`, `finalize`, `compose`, `generate`, `auth` subcommands |
| `veo.py` | Veo API client: single/multi-part video generation, extend, subtitle detection |
| `finalize.py` | Post-processing: crop, Whisper subtitles, subtitle correction, BGM mix, upload |
| `pipeline.py` | Stock footage generation pipeline (used by worker) |
| `main.py` | Flask app and queue/job endpoints |
| `worker.py` | Job consumer for stock footage pipeline |
| `gpt.py` | LLM client (Ollama/OpenAI/Codex): scripts, search terms, Veo prompts |
| `video.py` | Video processing: combine clips, burn subtitles, Whisper SRT |
| `ffmpeg_utils.py` | Shared ffmpeg wrappers: mux, render subtitled video |
| `tts_utils.py` | TTS provider routing (tiktok/qwen/clone) |
| `tiktokvoice.py` | TikTok TTS API (60+ voices, 300-char chunking) |
| `qwen_tts.py` | Qwen3-TTS local model |
| `narrate.py` | TTS narration overlay for Veo videos |
| `compose.py` | Narration + subtitles on existing video |
| `workflow.py` | Veo prompt part normalization |
| `search.py` | Pexels stock video search and download |
| `youtube.py` | YouTube upload via Google API with OAuth2 |
| `codex_auth.py` | OAuth2 PKCE auth for Codex/ChatGPT provider |
| `db.py`/`models.py`/`repository.py` | DB engine, ORM schema, queue/event persistence |
| `utils.py` | Path constants, env validation, ImageMagick detection |
| `logstream.py` | SSE-compatible log queue for frontend |

### Frontend
- `index.html`: UI with inline CSS, form fields, live log viewer
- `app.js`: API client (`apiRequest()`), job polling UI, localStorage persistence

### Output Directories
```
output/
  YYYY-MM-DD/
    raw/           # Veo original videos (per-part)
    final/         # Subtitled + BGM final videos
    prompts/       # Veo prompt JSON backups
    separated/     # demucs audio separation (if needed)
  temp/            # intermediate files (cleared each run)
  subtitles/       # generated .srt files
```

## Required Environment Variables

### Veo pipeline (primary)
- `GOOGLE_API_KEY` — Google AI API key for Veo
- `VEO_MODEL` — model ID (default: `veo-3.1-generate-preview`)

### Stock footage pipeline
- `PEXELS_API_KEY` — stock video API
- `TIKTOK_SESSION_ID` — TikTok cookie for TTS (if using tiktok TTS)
- `IMAGEMAGICK_BINARY` — leave empty to auto-detect from PATH

### Optional
- `AI_PROVIDER` — `ollama` (default), `openai`, or `codex`
- `TTS_PROVIDER` — `tiktok` (default), `qwen`, or `clone`
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `DATABASE_URL` — defaults to SQLite `moneyprinter.db`
- `VEO_MAX_WAIT_SECONDS` — API timeout (default: 600)
- `VEO_USE_VERTEX`, `GOOGLE_CLOUD_PROJECT` — for Vertex AI mode

## Conventions

- **Python**: 4-space indent, `snake_case`, type hints on all new/modified signatures, `pathlib.Path` for filesystem ops
- **JS**: `camelCase`, centralized API calls via `apiRequest()`
- **API responses**: `{"status": "success|error", ...}` with proper HTTP codes
- **Long-running work**: database-backed queue and separate worker process
- **Concurrency**: multiple jobs can be queued; worker processes them safely via DB locking
- Update `docs/` when setup, env vars, or runtime behavior changes
