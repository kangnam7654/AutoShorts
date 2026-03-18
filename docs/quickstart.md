# Quickstart

AutoShorts has two pipelines: **Veo** (primary, CLI) and **Stock footage** (legacy, web UI).

## Veo Pipeline (Primary)

### Prerequisites
- Python 3.11+, [uv](https://docs.astral.sh/uv/), FFmpeg
- Google Cloud project with Veo API enabled

### Setup
```bash
uv sync
cp .env.example .env
# Set GOOGLE_API_KEY, VEO_USE_VERTEX, GOOGLE_CLOUD_PROJECT in .env
```

### Generate and upload
```bash
uv run python Backend/cli.py veo \
  --prompt-file output/2026-03-17/prompts/d05_공감_귀인.json \
  --image path/to/your/character.png \
  --language ko --font-size 55 --upload \
  -o output/2026-03-17/final/d05_공감_귀인.mp4
```

See [Veo Workflow](veo-workflow/design.md) and [Production Pipeline](veo-workflow/production-pipeline.md) for details.

---

## Stock Footage Pipeline (Legacy)

Run AutoShorts locally with an Ollama model.

## 1) Clone repository

```bash
git clone https://github.com/kangnam7654/AutoShorts.git
cd AutoShorts
```

## 2) Quick setup (recommended)

Run the interactive setup script:

```bash
./setup.sh
```

This script checks dependencies, sets up `.env`, installs Python packages with `uv`, and can optionally pull an Ollama model.

## 3) Manual setup

Use this path if you prefer to run each step yourself.

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- FFmpeg
- ImageMagick
- Ollama

### Install and create env file

```bash
uv sync
cp .env.example .env
```

Windows PowerShell for `.env` copy:

```powershell
Copy-Item .env.example .env
```

## 4) Configure environment

Set required values in `.env`:

- `TIKTOK_SESSION_ID`
- `PEXELS_API_KEY`

See [Configuration](configuration.md) for all variables.

## Optional: Run tests

```bash
uv sync --group dev
uv run pytest
```

## 5) Start Ollama and pull a model

```bash
ollama serve
ollama pull llama3.1:8b
```

If Ollama runs on another machine/port, set `OLLAMA_BASE_URL` in `.env`.

## 6) Run backend

```bash
uv run python Backend/main.py
```

## 7) Run worker

In a new terminal:

```bash
uv run python Backend/worker.py
```

## 8) Run frontend

In a new terminal:

```bash
python3 -m http.server 3000 --directory Frontend
```

Open `http://localhost:3000`.

## 9) Generate video

1. Enter a video subject.
2. Expand advanced options.
3. Choose an Ollama model from the dropdown (loaded dynamically from Ollama).
4. Click Generate.

Output file: `output.mp4` at project root.
