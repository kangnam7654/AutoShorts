# Codex OAuth Integration Design

## Goal
Replace Ollama-only LLM backend with multi-provider support: Ollama (local), OpenAI API key, or Codex OAuth (ChatGPT subscription).

## Architecture

```
.env: AI_PROVIDER = ollama | openai | codex

gpt.py
  ├─ ollama  → ollama.Client (current, unchanged)
  ├─ openai  → openai.OpenAI(api_key=OPENAI_API_KEY)
  └─ codex   → openai.OpenAI + Codex OAuth Bearer token
```

## Codex OAuth Flow (PKCE)

1. User runs `cli.py auth` (one-time)
2. Generate code_verifier + code_challenge (S256)
3. Open browser → `https://auth.openai.com/oauth/authorize`
   - client_id: `app_EMoamEEZ73f0CkXaXp7hrann` (Codex public client)
   - response_type: code
   - code_challenge_method: S256
   - redirect_uri: `http://localhost:8098/callback`
4. Local HTTP server catches redirect with auth code
5. Exchange code → access_token + refresh_token at `https://auth.openai.com/oauth/token`
6. Store tokens at `~/.moneyprinter/codex-auth.json`
7. On subsequent runs: read token, auto-refresh if expired

## Files Changed

| File | Change |
|------|--------|
| `Backend/codex_auth.py` | NEW - OAuth PKCE flow, token storage, refresh |
| `Backend/gpt.py` | Multi-provider: ollama / openai / codex |
| `Backend/cli.py` | Add `auth` subcommand |
| `.env` | Add `AI_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL` |
| `pyproject.toml` | Add `openai` SDK dependency |

## Models Available via Codex OAuth

- gpt-5.1-codex-max (default in Codex CLI)
- gpt-5.1-codex-mini
- gpt-4o, gpt-4o-mini
- Other GPT-5.x variants

## env vars

```
AI_PROVIDER=codex          # ollama | openai | codex
OPENAI_API_KEY=            # for provider=openai only
OPENAI_MODEL=gpt-4o-mini   # model name for openai/codex
```
