"""Qwen3-TTS helpers for local MLX inference on Apple Silicon."""

import os

import numpy as np
import soundfile as sf

from logstream import log

DEFAULT_MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16"
BASE_MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"

DEFAULT_REF_AUDIO = os.path.join(
    os.path.dirname(__file__),
    "ref_voices",
    "ref_elderly_woman.wav",
)
DEFAULT_REF_TEXT = (
    "There was once upon a time a King, who was so much beloved by his subjects "
    "that he thought himself the happiest monarch in the whole world."
)

VOICES = [
    "Ryan",
    "Aiden",
    "Vivian",
    "Serena",
    "Uncle_Fu",
    "Dylan",
    "Eric",
    "Ono_anna",
    "Sohee",
]

VOICE_LANG_MAP = {
    "Ryan": "en",
    "Aiden": "en",
    "Vivian": "zh",
    "Serena": "zh",
    "Uncle_Fu": "zh",
    "Dylan": "zh",
    "Eric": "zh",
    "Ono_anna": "ja",
    "Sohee": "ko",
}

LANGUAGE_NAME_MAP = {
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}

_model = None
_base_model = None


def _get_model():
    global _model
    if _model is None:
        log("[*] Loading Qwen3-TTS CustomVoice model...", "info")
        from mlx_audio.tts.utils import load_model

        _model = load_model(DEFAULT_MODEL_ID)
        log("[+] Qwen3-TTS CustomVoice model loaded!", "success")
    return _model


def _get_base_model():
    global _base_model
    if _base_model is None:
        log("[*] Loading Qwen3-TTS Base model (for voice cloning)...", "info")
        from mlx_audio.tts.utils import load_model

        _base_model = load_model(BASE_MODEL_ID)
        log("[+] Qwen3-TTS Base model loaded!", "success")
    return _base_model


def _is_blank_text(text: str) -> bool:
    return not text or not text.strip()


def _speaker_name(voice: str) -> str:
    if voice in VOICES:
        return voice
    return "Ryan"


def _language_name_for_voice(voice: str) -> str:
    speaker = _speaker_name(voice)
    lang_code = VOICE_LANG_MAP.get(speaker, "en")
    return LANGUAGE_NAME_MAP.get(lang_code, "English")


def _save_audio(results, sample_rate: int, filename: str, label: str) -> None:
    if not results or results[0].audio is None:
        log(f"[-] {label} returned empty audio", "error")
        return

    audio_data = np.array(results[0].audio)
    sf.write(filename, audio_data, sample_rate)


def tts(
    text: str,
    voice: str = "Ryan",
    filename: str = "output.wav",
    play_sound: bool = False,
) -> None:
    """Generate speech with a preset Qwen voice and save it to a file."""
    if _is_blank_text(text):
        log("[-] Empty text, skipping TTS", "warning")
        return

    speaker = _speaker_name(voice)
    language = _language_name_for_voice(speaker)
    model = _get_model()

    try:
        results = list(
            model.generate_custom_voice(
                text=text,
                speaker=speaker,
                language=language,
            )
        )
        _save_audio(results, model.sample_rate, filename, "Qwen3-TTS")
        log(f"[+] Audio saved: {filename}", "success")

        if play_sound:
            from playsound import playsound as _play

            _play(filename)
    except Exception as err:
        log(f"[-] Qwen3-TTS error: {err}", "error")
        raise


def _clone_reference(ref_audio: str, ref_text: str) -> tuple[str, str]:
    return ref_audio or DEFAULT_REF_AUDIO, ref_text or DEFAULT_REF_TEXT


def tts_clone(
    text: str,
    ref_audio: str = "",
    ref_text: str = "",
    lang_code: str = "ko",
    filename: str = "output.wav",
) -> None:
    """Generate speech with Qwen voice cloning and save it to a file."""
    if _is_blank_text(text):
        log("[-] Empty text, skipping TTS", "warning")
        return

    resolved_ref_audio, resolved_ref_text = _clone_reference(ref_audio, ref_text)
    model = _get_base_model()

    try:
        results = list(
            model.generate(
                text=text,
                ref_audio=resolved_ref_audio,
                ref_text=resolved_ref_text,
                lang_code=lang_code,
            )
        )
        _save_audio(results, model.sample_rate, filename, "Qwen3-TTS clone")
        log(f"[+] Audio saved (cloned voice): {filename}", "success")
    except Exception as err:
        log(f"[-] Qwen3-TTS clone error: {err}", "error")
        raise
