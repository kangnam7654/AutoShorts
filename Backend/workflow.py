"""Normalize Veo prompt parts from LLM output."""

from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_part(raw: dict, index: int) -> dict:
    """Normalize one Veo prompt part into a predictable shape."""
    dialogue = _clean_text(raw.get("dialogue"))
    narration = _clean_text(raw.get("narration")) or dialogue

    return {
        "index": index,
        "prompt": _clean_text(raw.get("prompt")),
        "dialogue": dialogue,
        "narration": narration,
        "situation": _clean_text(raw.get("situation")),
        "voice_hint": _clean_text(raw.get("voice_hint")),
    }


def normalize_parts(raw_parts: list[dict]) -> list[dict]:
    """Normalize all raw Veo prompt parts."""
    return [normalize_part(raw_part, index) for index, raw_part in enumerate(raw_parts, start=1)]


def extract_script(parts: list[dict]) -> str:
    """Join narration lines from normalized parts into one script."""
    lines = []
    for part in parts:
        text = _clean_text(part.get("narration")) or _clean_text(part.get("dialogue"))
        if text:
            lines.append(text)
    return "\n".join(lines)
