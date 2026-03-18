"""Tests for tiktokvoice.py — chunking and endpoint fallback behavior."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestSplitString:
    def test_preserves_word_boundaries(self):
        from legacy.tiktokvoice import split_string

        chunks = split_string("alpha beta gamma delta", 10)

        assert chunks == ["alpha beta", "gamma", "delta"]


class TestTts:
    @patch("legacy.tiktokvoice.save_audio_file")
    @patch("legacy.tiktokvoice._generate_single_audio", return_value="ZmFrZQ==")
    @patch("legacy.tiktokvoice.requests.get")
    def test_falls_back_to_second_endpoint_when_first_is_down(
        self,
        mock_get,
        mock_generate_single,
        mock_save_audio,
    ):
        import legacy.tiktokvoice as tiktokvoice

        mock_get.side_effect = [
            MagicMock(status_code=500),
            MagicMock(status_code=200),
        ]

        with patch.object(tiktokvoice, "current_endpoint", 0):
            tiktokvoice.tts("hello", voice="en_us_001", filename="/tmp/test.mp3")
            assert tiktokvoice.current_endpoint == 1

        assert mock_generate_single.called
        assert mock_save_audio.called

    @patch("legacy.tiktokvoice.save_audio_file")
    @patch("legacy.tiktokvoice.requests.get", return_value=MagicMock(status_code=200))
    def test_rejects_unknown_voice(self, mock_get, mock_save_audio):
        import legacy.tiktokvoice as tiktokvoice

        tiktokvoice.tts("hello", voice="not_a_voice", filename="/tmp/test.mp3")

        assert not mock_save_audio.called
