# MoneyPrinter Docs

This folder is the single source of truth for setup, configuration, and troubleshooting.

## Start Here

- [Quickstart](quickstart.md)
- [Configuration](configuration.md)
- [Architecture](architecture.md)
- [Docker](docker.md)
- [Testing](testing.md)
- [Troubleshooting](troubleshooting.md)

## Feature Design Documents

| Document | Status | Description |
|----------|--------|-------------|
| [Veo API](veo-api/design.md) | Completed | Veo API integration |
| [Veo Workflow](veo-workflow/design.md) | Completed | Veo CLI + finalize pipeline |
| [Veo Production Pipeline](veo-workflow/production-pipeline.md) | Active | End-to-end production workflow |
| [Veo Dialogue-in-Prompt](veo-dialogue-prompt/design.md) | Completed | Dialogue embedded in Veo prompts |
| [Output Structure](output-structure/design.md) | Completed | raw/final/prompts directory layout |
| [Shared Utils Refactor](refactor-shared-utils/design.md) | Completed | tts_utils.py + ffmpeg_utils.py extraction |
| [Qwen TTS](qwen-tts/design.md) | Completed | Qwen3-TTS local TTS provider |
| [Compose Pipeline](compose-pipeline/design.md) | Completed | Narration + subtitles on existing video |
| [Codex OAuth](codex-oauth/design.md) | Completed | OAuth2 PKCE for Codex/ChatGPT |
| [macOS App](macos-app/design.md) | WIP | SwiftUI wrapper app |
