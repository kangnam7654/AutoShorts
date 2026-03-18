# Veo API Cost Estimation

## Per-Video Cost

Each MoneyPrinter video is 15 seconds (8s create + 7s extend = 2 API calls).

| Model | Cost/sec | Per video (15s) | Monthly (1/day) | Monthly (3/day) |
|-------|----------|-----------------|-----------------|-----------------|
| Standard | ~$0.40 | ~$6.00 | ~$180 | ~$540 |
| Fast | ~$0.15 | ~$2.25 | ~$68 | ~$203 |

**Use Standard for production.** Fast model has character consistency issues between parts.

## What You Pay For

- **Part 1 (create)**: 8 seconds of video generation
- **Part 2 (extend)**: 7 seconds added to Part 1
- Failed generations may still incur costs

## Cost Optimization Tips

1. **Perfect your prompt before generating** — Each failed attempt costs the same as a success
2. **Use the prompt tips** — Following the [prompt rules](../README.md#prompt-writing-tips) reduces re-generation
3. **Test with shorter prompts** — Use `--parts 1` for 8s test videos at ~$3.20
4. **Batch similar content** — Reuse prompt templates with dialogue changes only

## Other Costs (Free/Minimal)

| Component | Cost |
|-----------|------|
| Whisper subtitles | Free (runs locally via MLX) |
| FFmpeg processing | Free (runs locally) |
| YouTube upload | Free (YouTube Data API quota) |
| Ollama LLM | Free (runs locally) |

## Comparison with Alternatives

| Service | 15s video cost | Character consistency | Lip sync |
|---------|---------------|----------------------|----------|
| **Veo 3.1 Standard** | ~$6.00 | Good | Yes |
| **Veo 3.1 Fast** | ~$2.25 | Poor | Yes |
| Kling AI (official API) | ~$4.50 | Good | Yes |
| Kling AI (fal.ai proxy) | ~$1.00 | Good | Yes |
| Wan2.1 (local, RTX 3090) | Free (electricity) | Varies | No |

Prices are approximate and may change. Check provider pricing pages for current rates.
