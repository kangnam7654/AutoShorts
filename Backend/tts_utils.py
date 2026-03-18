"""Shared TTS utilities: provider routing, voice defaults, text splitting."""

import os

from dotenv import load_dotenv

from utils import ENV_FILE

load_dotenv(ENV_FILE)

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "tiktok").strip().lower()

DEFAULT_VOICES: dict[str, dict[str, str]] = {
    "narration": {"qwen": "Sohee", "tiktok": "kr_003"},
    "generation": {"qwen": "Ryan", "tiktok": "en_us_001"},
}


def tts_generate(
    text: str,
    voice: str,
    filename: str,
    clone: bool = False,
    ref_audio: str = "",
    ref_text: str = "",
    language: str = "ko",
) -> None:
    """Unified TTS: routes to Qwen (with optional clone) or TikTok."""
    if clone:
        from legacy.qwen_tts import tts_clone

        tts_clone(
            text,
            ref_audio=ref_audio,
            ref_text=ref_text,
            lang_code=language,
            filename=filename,
        )
        return

    if TTS_PROVIDER == "qwen":
        from legacy.qwen_tts import tts

        tts(text, voice, filename=filename)
        return

    from legacy.tiktokvoice import tts

    tts(text, voice, filename=filename)


def tts_extension() -> str:
    """Return file extension for current TTS provider."""
    if TTS_PROVIDER == "qwen":
        return ".wav"
    return ".mp3"


def default_voice(purpose: str = "generation") -> str:
    """Return default voice for current provider. purpose: 'generation' or 'narration'."""
    voices = DEFAULT_VOICES.get(purpose, DEFAULT_VOICES["generation"])
    return voices.get(TTS_PROVIDER, voices["tiktok"])


def voice_language_prefix(voice: str) -> str:
    """Extract language prefix from voice name."""
    if TTS_PROVIDER == "qwen":
        from legacy.qwen_tts import VOICE_LANG_MAP

        return VOICE_LANG_MAP.get(voice, "en")
    return voice[:2]


def split_sentences(script: str) -> list[str]:
    """Split script into sentences. Based on compose.py's version (handles newlines)."""
    return [
        sentence.strip()
        for sentence in script.replace("\n", " ").split(". ")
        if sentence.strip()
    ]
