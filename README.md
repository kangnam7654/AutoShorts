# MoneyPrinter

Automate YouTube Shorts creation with AI-generated video. Write a prompt, generate a video with Google Veo 3.1, add subtitles, and upload to YouTube — all from one CLI command.

> [Korean README (한국어)](docs/README.ko.md)

## What it does

```
Prompt JSON → Veo 3.1 API → 15s AI video → Whisper subtitles → YouTube upload
```

1. You write a prompt describing your character, scene, and dialogue
2. Veo 3.1 generates a 15-second vertical video (8s create + 7s extend) with lip-synced speech
3. Whisper transcribes the audio and corrects subtitles to match your script
4. The final video is uploaded to YouTube as a Short

**Supports any language** — dialogue and subtitles work in Korean, English, Japanese, Chinese, and more.

## Cost

Veo 3.1 is a paid API. Estimated cost per 15-second video:

| Model | Cost/sec | Per video (15s) | Notes |
|-------|----------|-----------------|-------|
| Standard (`veo-3.1-generate-preview`) | ~$0.40 | ~$6.00 | Recommended for production |
| Fast (`veo-3.1-fast-generate-preview`) | ~$0.15 | ~$2.25 | Lower quality, character inconsistency |

The Standard model is recommended. The Fast model often fails to maintain character consistency between parts.

See [Veo pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing#video-models) for current rates.

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- FFmpeg (`brew install ffmpeg` / `apt install ffmpeg`)
- Google Cloud project with [Veo API](https://cloud.google.com/vertex-ai/generative-ai/docs/video/overview) enabled

### 1. Install

```bash
git clone https://github.com/kangnam7654/AutoShorts.git
cd MoneyPrinter
uv sync
cp .env.example .env
```

### 2. Configure

Edit `.env`:
```env
GOOGLE_API_KEY="your-google-api-key"

# For Vertex AI (recommended for production):
VEO_USE_VERTEX="true"
GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
```

### 3. Create a prompt

Create `my_prompt.json`:

```json
[
  {
    "prompt": "A cinematic vertical short-form video, 9:16. 3D animated character style matching the reference image — NOT live action. She stands in a dark mystical space with golden particles floating around her. Close-up on her face. Camera slowly pulls back.\n\nExact spoken dialogue:\n\"Hello, I have something important to tell you.\"\n\"This might change everything.\"\n\nABSOLUTELY NO MUSIC. No subtitles. No on-screen text.",
    "dialogue": "Hello, I have something important to tell you.\nThis might change everything."
  },
  {
    "prompt": "Continue the same scene in the SAME style. She remains standing, wearing the EXACT same outfit and colors. The golden particles glow warmer. She looks directly at the camera.\n\nExact spoken dialogue:\n\"Remember this moment.\"\n\nABSOLUTELY NO MUSIC. No subtitles.",
    "dialogue": "Remember this moment."
  }
]
```

### 4. Generate

```bash
uv run python Backend/cli.py veo \
  --prompt-file my_prompt.json \
  --image path/to/your/character.png \
  --language en --font-size 55 \
  -o output/my_video.mp4
```

Add `--upload` to upload directly to YouTube (requires [YouTube OAuth setup](docs/youtube-setup.md)).

### What happens

```
[1/2] Generating 2-part video (8s + 7s)...
[Veo] Part 1 saved: output/raw/my_video_part1.mp4 (~8s)
[Veo] Part 2 saved: output/raw/my_video_part2.mp4 (~15s)
--- Finalizing (subtitles) ---
[1/6] Skipping crop.
[2/6] Extracting audio...
[3/6] Generating subtitles...
[4/6] Correcting subtitles...
[5/6] Burning subtitles...
[6/6] Restoring original audio...
Done! Output: output/my_video.mp4
```

## CLI Commands

### `veo` — Full pipeline

```bash
uv run python Backend/cli.py veo \
  --prompt-file prompts.json \
  --image character.png \
  --language ko \
  --font-size 55 \
  --upload \
  --upload-title "My Video Title" \
  -o output/final/video.mp4
```

| Option | Default | Description |
|--------|---------|-------------|
| `--prompt-file` | (required) | JSON file with prompts and dialogue |
| `--image` | none | Reference image for character consistency |
| `--language` | `ko` | Subtitle language code |
| `--font-size` | `55` | Subtitle font size |
| `--veo-model` | env `VEO_MODEL` | Veo model ID |
| `--upload` | false | Upload to YouTube after generation |
| `--upload-title` | auto | YouTube video title |
| `--no-finalize` | false | Skip subtitle/BGM post-processing |
| `-o` | auto | Output file path |

### `finalize` — Post-process existing video

```bash
uv run python Backend/cli.py finalize \
  --video raw_video.mp4 \
  --music bgm.mp3 --music-volume 0.10 \
  --script "Line 1\nLine 2" \
  --upload \
  -o output/final/video.mp4
```

### `auth` — YouTube OAuth setup

```bash
uv run python Backend/cli.py auth
```

See [YouTube Setup Guide](docs/youtube-setup.md) for full OAuth configuration.

## Architecture

```
CLI (cli.py)
  |
  v
Veo API (veo.py)
  |-- Part 1: create (8 seconds)
  |-- Part 2: extend (+7 seconds = 15s total)
  v
Finalize (finalize.py)
  |-- [1] Crop to 9:16 (if needed)
  |-- [2] Extract audio (ffmpeg)
  |-- [3] Generate subtitles (Whisper MLX)
  |-- [4] Correct subtitle text (match script to timing)
  |-- [5] Burn subtitles (ffmpeg drawtext)
  |-- [6] Mix BGM (optional, moviepy)
  v
YouTube Upload (youtube.py, OAuth2)
```

## Prompt Writing Tips

Rules based on production experience with Veo 3.1:

| Rule | Why |
|------|-----|
| Use "dark mystical space" for background | Concrete locations (ponds, forests) cause character placement errors |
| Character should always "stand" | Sitting/lying poses render incorrectly |
| Background effects: particles/dust/orbs only | Animals, buildings, furniture degrade quality |
| No water or liquid descriptions | Character gets submerged |
| Camera: close-up then pull back | Complex camera moves are unstable |
| Effects: "slowly glow", "gradually drift" | "Bursting/exploding" effects look cheap |
| Part 2: "wearing the EXACT same outfit" | Prevents costume color changes between parts |
| "ABSOLUTELY NO MUSIC" | Veo adds unwanted BGM otherwise |
| "No text, no subtitles, no captions" | Veo generates broken text overlays |
| Use Standard model, not Fast | Fast model breaks character consistency between parts |

See [Character Guide](docs/character-guide.md) for setting up your own character.

## Project Structure

```
Backend/
  cli.py              # CLI entry point
  veo.py              # Veo 3.1 API client
  finalize.py         # Post-processing pipeline
  workflow.py         # Prompt normalization
  youtube.py          # YouTube OAuth2 upload
  ffmpeg_utils.py     # FFmpeg wrappers
  video.py            # Video processing, Whisper SRT
  gpt.py              # LLM client (Ollama/OpenAI)
  logstream.py        # Logging
  utils.py            # Path constants, env validation
  legacy/             # Stock footage pipeline (not actively used)

output/
  YYYY-MM-DD/
    raw/              # Veo original videos
    final/            # Subtitled final videos
    prompts/          # Prompt JSON backups
```

## Configuration

Copy `.env.example` to `.env` and set your keys. See [docs/configuration.md](docs/configuration.md) for all variables.

### Required

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Google AI API key for Veo |
| `VEO_USE_VERTEX` | `true` for Vertex AI mode (recommended) |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (required if Vertex) |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `VEO_MODEL` | Veo model ID | `veo-3.1-generate-preview` |
| `VEO_MAX_WAIT_SECONDS` | API polling timeout | `600` |
| `AI_PROVIDER` | LLM provider (`ollama`/`openai`) | `ollama` |

## Docker (Legacy Stock Pipeline)

The Docker setup runs the legacy stock footage pipeline with a web UI:

```bash
cp .env.example .env   # Set POSTGRES_PASSWORD and API keys
docker compose up --build
# Frontend: http://localhost:3000
# Backend:  http://localhost:8080
```

## Tests

```bash
uv run python -m pytest tests/ -q                    # 398 tests
uv run python -m pytest --cov --cov-fail-under=90    # 91% coverage
```

## Documentation

- [Quickstart](docs/quickstart.md)
- [Configuration](docs/configuration.md)
- [YouTube Setup](docs/youtube-setup.md)
- [Character Guide](docs/character-guide.md)
- [Veo Cost Estimation](docs/veo-cost.md)
- [Architecture](docs/architecture.md)
- [Docker](docs/docker.md)
- [Testing](docs/testing.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Veo Workflow](docs/veo-workflow/design.md)
- [Production Pipeline](docs/veo-workflow/production-pipeline.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

See [LICENSE](LICENSE) file.

## Credits

Forked from [FujiwaraChoki/MoneyPrinter](https://github.com/FujiwaraChoki/MoneyPrinter). Extended with Veo 3.1 pipeline, Whisper subtitles, and YouTube automation.
