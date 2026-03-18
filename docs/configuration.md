# Configuration

AutoShorts reads configuration from `.env` (project root).

Use `.env.example` as your template.

## Veo Pipeline (primary)

| Variable | Description | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Google AI API key for Veo video generation. | (required) |
| `VEO_MODEL` | Veo model ID. | `veo-3.1-generate-preview` |
| `VEO_MAX_WAIT_SECONDS` | API polling timeout in seconds. | `600` |
| `VEO_USE_VERTEX` | Use Vertex AI instead of developer API (`true`/`false`). | `false` |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (required if `VEO_USE_VERTEX=true`). | empty |
| `VEO_GCS_BUCKET` | GCS bucket for Vertex output. | `moneyprinter-veo-output` |

## Stock Footage Pipeline

| Variable | Description | Default |
|---|---|---|
| `TIKTOK_SESSION_ID` | TikTok session cookie (`sessionid`) used for TTS voice endpoint calls. | (required for tiktok TTS) |
| `PEXELS_API_KEY` | API key used to fetch stock video clips. | (required) |
| `IMAGEMAGICK_BINARY` | Absolute path to ImageMagick executable. If empty, auto-detected from `PATH`. | auto-detect |

## LLM / AI Provider

| Variable | Description | Default |
|---|---|---|
| `AI_PROVIDER` | LLM provider: `ollama`, `openai`, or `codex`. | `ollama` |
| `OLLAMA_BASE_URL` | Ollama server base URL. | `http://localhost:11434` |
| `OLLAMA_MODEL` | Fallback model if not specified. | `llama3.1:8b` |
| `OPENAI_API_KEY` | OpenAI API key (if `AI_PROVIDER=openai`). | empty |

## TTS Provider

| Variable | Description | Default |
|---|---|---|
| `TTS_PROVIDER` | TTS engine: `tiktok`, `qwen`, or `clone`. | `tiktok` |

## Database

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy DSN (`postgresql+psycopg://...` or `sqlite:///...`). | `sqlite:///moneyprinter.db` |
| `POSTGRES_DB` | Database name for Docker Postgres service. | `moneyprinter` |
| `POSTGRES_USER` | Database user for Docker Postgres service. | `moneyprinter` |
| `POSTGRES_PASSWORD` | Database password for Docker Postgres service. | `moneyprinter` |

## Notes

- Docker Postgres is exposed on host port `5433` (not 5432) to avoid conflicts.
- Ollama models shown in the frontend are fetched from `/api/models`, which queries `OLLAMA_BASE_URL/api/tags`.
- Pull models before use: `ollama pull llama3.1:8b`
- Database-backed job queue is used in Docker via `DATABASE_URL`.
