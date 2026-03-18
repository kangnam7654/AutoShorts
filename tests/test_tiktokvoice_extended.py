"""Extended tests for tiktokvoice.py — TTS generation, validation, endpoint selection."""

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestValidateRequest:
    def test_none_voice_rejected(self):
        from legacy.tiktokvoice import _validate_request

        assert _validate_request("text", "none") is False

    def test_invalid_voice_rejected(self):
        from legacy.tiktokvoice import _validate_request

        assert _validate_request("text", "nonexistent_voice") is False

    def test_empty_text_rejected(self):
        from legacy.tiktokvoice import _validate_request

        assert _validate_request("", "en_us_001") is False

    def test_valid_request(self):
        from legacy.tiktokvoice import _validate_request

        assert _validate_request("hello world", "en_us_001") is True


class TestSaveAudioFile:
    def test_writes_decoded_audio(self, tmp_path):
        from legacy.tiktokvoice import save_audio_file

        data = base64.b64encode(b"fake audio data").decode()
        output = str(tmp_path / "test.mp3")
        save_audio_file(data, output)

        assert Path(output).read_bytes() == b"fake audio data"


class TestSelectAvailableEndpoint:
    @patch("legacy.tiktokvoice.get_api_response")
    def test_first_endpoint_available(self, mock_get):
        import legacy.tiktokvoice as tiktokvoice

        mock_get.return_value = MagicMock(status_code=200)
        tiktokvoice.current_endpoint = 0

        assert tiktokvoice._select_available_endpoint() is True

    @patch("legacy.tiktokvoice.get_api_response")
    def test_fallback_to_second_endpoint(self, mock_get):
        import legacy.tiktokvoice as tiktokvoice

        tiktokvoice.current_endpoint = 0
        mock_get.side_effect = [
            MagicMock(status_code=500),  # first fails
            MagicMock(status_code=200),  # second succeeds
        ]

        assert tiktokvoice._select_available_endpoint() is True

    @patch("legacy.tiktokvoice.get_api_response")
    def test_both_endpoints_fail(self, mock_get):
        import legacy.tiktokvoice as tiktokvoice

        tiktokvoice.current_endpoint = 0
        mock_get.return_value = MagicMock(status_code=500)

        assert tiktokvoice._select_available_endpoint() is False


class TestExtractBase64Audio:
    def test_endpoint_0_plain_base64(self):
        import legacy.tiktokvoice as tiktokvoice

        tiktokvoice.current_endpoint = 0
        data = {"success": True, "data": "base64audiodata"}
        result = tiktokvoice._extract_base64_audio(data)
        assert result == "base64audiodata"

    def test_endpoint_1_data_uri(self):
        import legacy.tiktokvoice as tiktokvoice

        tiktokvoice.current_endpoint = 1
        data = {"data": "data:audio/mpeg;base64,actual_data"}
        result = tiktokvoice._extract_base64_audio(data)
        assert result == "actual_data"

    def test_missing_data_raises(self):
        import legacy.tiktokvoice as tiktokvoice

        with pytest.raises(RuntimeError, match="TikTok TTS error"):
            tiktokvoice._extract_base64_audio({"error": "bad request"})


class TestTts:
    @patch("legacy.tiktokvoice._select_available_endpoint", return_value=False)
    def test_returns_early_if_no_endpoint(self, mock_endpoint):
        from legacy.tiktokvoice import tts

        tts("hello", "en_us_001", filename="/tmp/out.mp3")
        # Should return without error

    @patch("legacy.tiktokvoice.save_audio_file")
    @patch("legacy.tiktokvoice._generate_single_audio", return_value="base64audio")
    @patch("legacy.tiktokvoice._select_available_endpoint", return_value=True)
    def test_short_text_uses_single(self, mock_ep, mock_gen, mock_save):
        from legacy.tiktokvoice import tts

        tts("short", "en_us_001", filename="/tmp/out.mp3")
        mock_gen.assert_called_once()
        mock_save.assert_called_once()

    @patch("legacy.tiktokvoice.save_audio_file")
    @patch("legacy.tiktokvoice._generate_chunked_audio", return_value="base64audio")
    @patch("legacy.tiktokvoice._select_available_endpoint", return_value=True)
    def test_long_text_uses_chunked(self, mock_ep, mock_gen, mock_save):
        from legacy.tiktokvoice import tts

        long_text = "x " * 200  # > 300 chars
        tts(long_text, "en_us_001", filename="/tmp/out.mp3")
        mock_gen.assert_called_once()

    @patch("legacy.tiktokvoice._generate_single_audio", return_value="error")
    @patch("legacy.tiktokvoice._select_available_endpoint", return_value=True)
    def test_error_audio_logged(self, mock_ep, mock_gen):
        from legacy.tiktokvoice import tts

        tts("test", "en_us_001", filename="/tmp/out.mp3")
        # Should not raise, just log

    @patch("legacy.tiktokvoice._generate_single_audio", side_effect=Exception("network"))
    @patch("legacy.tiktokvoice._select_available_endpoint", return_value=True)
    def test_exception_logged(self, mock_ep, mock_gen):
        from legacy.tiktokvoice import tts

        tts("test", "en_us_001", filename="/tmp/out.mp3")
        # Should not raise


class TestGenerateChunkedAudio:
    @patch("legacy.tiktokvoice._generate_single_audio")
    def test_combines_chunks(self, mock_single):
        from legacy.tiktokvoice import _generate_chunked_audio

        mock_single.side_effect = ["part1", "part2"]
        result = _generate_chunked_audio("word " * 100, "en_us_001")
        assert "part1" in result
        assert "part2" in result
