"""Tests for qwen_tts.py — voice mapping, language selection, TTS generation."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from legacy.qwen_tts import VOICES, VOICE_LANG_MAP, tts, tts_clone, DEFAULT_REF_AUDIO, DEFAULT_REF_TEXT


class TestVoiceConfig:
    def test_all_voices_have_lang_mapping(self):
        """Every voice in VOICES should have a language in VOICE_LANG_MAP."""
        for voice in VOICES:
            assert voice in VOICE_LANG_MAP, f"{voice} missing from VOICE_LANG_MAP"

    def test_english_voices(self):
        assert VOICE_LANG_MAP["Ryan"] == "en"
        assert VOICE_LANG_MAP["Aiden"] == "en"

    def test_korean_voice(self):
        assert VOICE_LANG_MAP["Sohee"] == "ko"

    def test_japanese_voice(self):
        assert VOICE_LANG_MAP["Ono_anna"] == "ja"

    def test_chinese_voices(self):
        for v in ["Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric"]:
            assert VOICE_LANG_MAP[v] == "zh"


class TestTts:
    @patch("legacy.qwen_tts._get_model")
    def test_skips_empty_text(self, mock_model):
        tts("", "Ryan", "/tmp/test.wav")
        mock_model.assert_not_called()

    @patch("legacy.qwen_tts._get_model")
    def test_skips_whitespace_only(self, mock_model):
        tts("   ", "Ryan", "/tmp/test.wav")
        mock_model.assert_not_called()

    @patch("legacy.qwen_tts.sf.write")
    @patch("legacy.qwen_tts._get_model")
    def test_uses_correct_language_for_korean_voice(self, mock_get_model, mock_write):
        import numpy as np

        model = MagicMock()
        model.sample_rate = 24000
        result = MagicMock()
        result.audio = np.zeros(100)
        model.generate_custom_voice.return_value = [result]
        mock_get_model.return_value = model

        tts("안녕하세요", "Sohee", "/tmp/test.wav")

        call_kwargs = model.generate_custom_voice.call_args
        assert call_kwargs[1]["language"] == "Korean"
        assert call_kwargs[1]["speaker"] == "Sohee"

    @patch("legacy.qwen_tts.sf.write")
    @patch("legacy.qwen_tts._get_model")
    def test_uses_english_for_ryan(self, mock_get_model, mock_write):
        import numpy as np

        model = MagicMock()
        model.sample_rate = 24000
        result = MagicMock()
        result.audio = np.zeros(100)
        model.generate_custom_voice.return_value = [result]
        mock_get_model.return_value = model

        tts("Hello world", "Ryan", "/tmp/test.wav")

        call_kwargs = model.generate_custom_voice.call_args
        assert call_kwargs[1]["language"] == "English"

    @patch("legacy.qwen_tts.sf.write")
    @patch("legacy.qwen_tts._get_model")
    def test_falls_back_to_ryan_for_unknown_voice(self, mock_get_model, mock_write):
        import numpy as np

        model = MagicMock()
        model.sample_rate = 24000
        result = MagicMock()
        result.audio = np.zeros(100)
        model.generate_custom_voice.return_value = [result]
        mock_get_model.return_value = model

        tts("text", "UnknownVoice", "/tmp/test.wav")

        call_kwargs = model.generate_custom_voice.call_args
        assert call_kwargs[1]["speaker"] == "Ryan"
        assert call_kwargs[1]["language"] == "English"

    @patch("legacy.qwen_tts._get_model")
    def test_raises_on_model_error(self, mock_get_model):
        model = MagicMock()
        model.generate_custom_voice.side_effect = RuntimeError("GPU error")
        mock_get_model.return_value = model

        with pytest.raises(RuntimeError, match="GPU error"):
            tts("text", "Ryan", "/tmp/test.wav")


class TestTtsClone:
    def test_default_ref_audio_path_exists(self):
        import os
        assert os.path.isfile(DEFAULT_REF_AUDIO), f"Reference audio not found: {DEFAULT_REF_AUDIO}"

    def test_default_ref_text_is_nonempty(self):
        assert len(DEFAULT_REF_TEXT) > 10

    @patch("legacy.qwen_tts._get_base_model")
    def test_skips_empty_text(self, mock_model):
        tts_clone("", filename="/tmp/test.wav")
        mock_model.assert_not_called()

    @patch("legacy.qwen_tts.sf.write")
    @patch("legacy.qwen_tts._get_base_model")
    def test_calls_generate_with_ref_audio(self, mock_get_base, mock_write):
        import numpy as np

        model = MagicMock()
        model.sample_rate = 24000
        result = MagicMock()
        result.audio = np.zeros(100)
        model.generate.return_value = [result]
        mock_get_base.return_value = model

        tts_clone("테스트 문장입니다.", filename="/tmp/test.wav")

        call_kwargs = model.generate.call_args[1]
        assert call_kwargs["ref_audio"] == DEFAULT_REF_AUDIO
        assert call_kwargs["ref_text"] == DEFAULT_REF_TEXT
        assert call_kwargs["lang_code"] == "ko"

    @patch("legacy.qwen_tts.sf.write")
    @patch("legacy.qwen_tts._get_base_model")
    def test_custom_ref_audio(self, mock_get_base, mock_write):
        import numpy as np

        model = MagicMock()
        model.sample_rate = 24000
        result = MagicMock()
        result.audio = np.zeros(100)
        model.generate.return_value = [result]
        mock_get_base.return_value = model

        tts_clone("Hello", ref_audio="/custom/ref.wav", ref_text="Custom text.", lang_code="en", filename="/tmp/test.wav")

        call_kwargs = model.generate.call_args[1]
        assert call_kwargs["ref_audio"] == "/custom/ref.wav"
        assert call_kwargs["ref_text"] == "Custom text."
        assert call_kwargs["lang_code"] == "en"

    @patch("legacy.qwen_tts._get_base_model")
    def test_raises_on_model_error(self, mock_get_base):
        model = MagicMock()
        model.generate.side_effect = RuntimeError("clone error")
        mock_get_base.return_value = model

        with pytest.raises(RuntimeError, match="clone error"):
            tts_clone("text", filename="/tmp/test.wav")
