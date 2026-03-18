"""Tests for tts_utils.py — TTS provider routing, voice defaults, text splitting."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestTtsGenerate:
    @patch("tts_utils.TTS_PROVIDER", "tiktok")
    @patch("legacy.tiktokvoice.tts")
    def test_routes_to_tiktok(self, mock_tts):
        from tts_utils import tts_generate

        tts_generate("hello", "en_us_001", filename="/tmp/out.mp3")

        mock_tts.assert_called_once_with("hello", "en_us_001", filename="/tmp/out.mp3")

    @patch("tts_utils.TTS_PROVIDER", "qwen")
    @patch("legacy.qwen_tts.tts")
    def test_routes_to_qwen(self, mock_tts):
        from tts_utils import tts_generate

        tts_generate("hello", "Sohee", filename="/tmp/out.wav")

        mock_tts.assert_called_once_with("hello", "Sohee", filename="/tmp/out.wav")

    @patch("legacy.qwen_tts.tts_clone")
    def test_clone_mode_uses_qwen_clone(self, mock_clone):
        from tts_utils import tts_generate

        tts_generate(
            "hello",
            "ignored",
            filename="/tmp/out.wav",
            clone=True,
            ref_audio="/ref.wav",
            ref_text="ref text",
            language="ko",
        )

        mock_clone.assert_called_once_with(
            "hello",
            ref_audio="/ref.wav",
            ref_text="ref text",
            lang_code="ko",
            filename="/tmp/out.wav",
        )


class TestTtsExtension:
    @patch("tts_utils.TTS_PROVIDER", "tiktok")
    def test_tiktok_returns_mp3(self):
        from tts_utils import tts_extension

        assert tts_extension() == ".mp3"

    @patch("tts_utils.TTS_PROVIDER", "qwen")
    def test_qwen_returns_wav(self):
        from tts_utils import tts_extension

        assert tts_extension() == ".wav"


class TestDefaultVoice:
    @patch("tts_utils.TTS_PROVIDER", "tiktok")
    def test_tiktok_generation(self):
        from tts_utils import default_voice

        assert default_voice("generation") == "en_us_001"

    @patch("tts_utils.TTS_PROVIDER", "qwen")
    def test_qwen_generation(self):
        from tts_utils import default_voice

        assert default_voice("generation") == "Ryan"

    @patch("tts_utils.TTS_PROVIDER", "tiktok")
    def test_tiktok_narration(self):
        from tts_utils import default_voice

        assert default_voice("narration") == "kr_003"

    @patch("tts_utils.TTS_PROVIDER", "qwen")
    def test_qwen_narration(self):
        from tts_utils import default_voice

        assert default_voice("narration") == "Sohee"

    @patch("tts_utils.TTS_PROVIDER", "tiktok")
    def test_unknown_purpose_falls_back_to_generation(self):
        from tts_utils import default_voice

        assert default_voice("unknown") == "en_us_001"


class TestVoiceLanguagePrefix:
    @patch("tts_utils.TTS_PROVIDER", "tiktok")
    def test_tiktok_extracts_prefix(self):
        from tts_utils import voice_language_prefix

        assert voice_language_prefix("en_us_001") == "en"
        assert voice_language_prefix("kr_003") == "kr"

    @patch("tts_utils.TTS_PROVIDER", "qwen")
    def test_qwen_uses_voice_lang_map(self):
        from tts_utils import voice_language_prefix

        with patch.dict("sys.modules", {"qwen_tts": MagicMock(VOICE_LANG_MAP={"Sohee": "ko", "Ryan": "en"})}):
            import importlib
            import tts_utils
            importlib.reload(tts_utils)

            # Re-import after reload
            from tts_utils import voice_language_prefix as vlp

            with patch("tts_utils.TTS_PROVIDER", "qwen"):
                assert vlp("Sohee") == "ko"
                assert vlp("Ryan") == "en"
                assert vlp("Unknown") == "en"  # fallback


class TestSplitSentences:
    def test_basic_split(self):
        from tts_utils import split_sentences

        result = split_sentences("Hello world. Goodbye world.")
        assert result == ["Hello world", "Goodbye world."]

    def test_empty_string(self):
        from tts_utils import split_sentences

        assert split_sentences("") == []

    def test_newlines_replaced(self):
        from tts_utils import split_sentences

        result = split_sentences("Line one.\nLine two.")
        assert len(result) == 2

    def test_strips_whitespace(self):
        from tts_utils import split_sentences

        result = split_sentences("  Hello.   Bye.  ")
        assert all(s == s.strip() for s in result)
