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
        from tiktokvoice import _validate_request

        assert _validate_request("text", "none") is False

    def test_invalid_voice_rejected(self):
        from tiktokvoice import _validate_request

        assert _validate_request("text", "nonexistent_voice") is False

    def test_empty_text_rejected(self):
        from tiktokvoice import _validate_request

        assert _validate_request("", "en_us_001") is False

    def test_valid_request(self):
        from tiktokvoice import _validate_request

        assert _validate_request("hello world", "en_us_001") is True


class TestSaveAudioFile:
    def test_writes_decoded_audio(self, tmp_path):
        from tiktokvoice import save_audio_file

        data = base64.b64encode(b"fake audio data").decode()
        output = str(tmp_path / "test.mp3")
        save_audio_file(data, output)

        assert Path(output).read_bytes() == b"fake audio data"


class TestSelectAvailableEndpoint:
    @patch("tiktokvoice.get_api_response")
    def test_first_endpoint_available(self, mock_get):
        import tiktokvoice

        mock_get.return_value = MagicMock(status_code=200)
        tiktokvoice.current_endpoint = 0

        assert tiktokvoice._select_available_endpoint() is True

    @patch("tiktokvoice.get_api_response")
    def test_fallback_to_second_endpoint(self, mock_get):
        import tiktokvoice

        tiktokvoice.current_endpoint = 0
        mock_get.side_effect = [
            MagicMock(status_code=500),  # first fails
            MagicMock(status_code=200),  # second succeeds
        ]

        assert tiktokvoice._select_available_endpoint() is True

    @patch("tiktokvoice.get_api_response")
    def test_both_endpoints_fail(self, mock_get):
        import tiktokvoice

        tiktokvoice.current_endpoint = 0
        mock_get.return_value = MagicMock(status_code=500)

        assert tiktokvoice._select_available_endpoint() is False


class TestExtractBase64Audio:
    def test_endpoint_0(self):
        import tiktokvoice

        tiktokvoice.current_endpoint = 0
        # Endpoint 0: 6th quote-delimited field (index 5)
        raw = b'{"data":"unused","status":"ok","audio":"base64data"}'
        result = tiktokvoice._extract_base64_audio(raw)
        assert isinstance(result, str)

    def test_endpoint_1(self):
        import tiktokvoice

        tiktokvoice.current_endpoint = 1
        raw = b'{"data":"audio/mp3;base64,actual_data"}'
        result = tiktokvoice._extract_base64_audio(raw)
        assert isinstance(result, str)


class TestTts:
    @patch("tiktokvoice._select_available_endpoint", return_value=False)
    def test_returns_early_if_no_endpoint(self, mock_endpoint):
        from tiktokvoice import tts

        tts("hello", "en_us_001", filename="/tmp/out.mp3")
        # Should return without error

    @patch("tiktokvoice.save_audio_file")
    @patch("tiktokvoice._generate_single_audio", return_value="base64audio")
    @patch("tiktokvoice._select_available_endpoint", return_value=True)
    def test_short_text_uses_single(self, mock_ep, mock_gen, mock_save):
        from tiktokvoice import tts

        tts("short", "en_us_001", filename="/tmp/out.mp3")
        mock_gen.assert_called_once()
        mock_save.assert_called_once()

    @patch("tiktokvoice.save_audio_file")
    @patch("tiktokvoice._generate_chunked_audio", return_value="base64audio")
    @patch("tiktokvoice._select_available_endpoint", return_value=True)
    def test_long_text_uses_chunked(self, mock_ep, mock_gen, mock_save):
        from tiktokvoice import tts

        long_text = "x " * 200  # > 300 chars
        tts(long_text, "en_us_001", filename="/tmp/out.mp3")
        mock_gen.assert_called_once()

    @patch("tiktokvoice._generate_single_audio", return_value="error")
    @patch("tiktokvoice._select_available_endpoint", return_value=True)
    def test_error_audio_logged(self, mock_ep, mock_gen):
        from tiktokvoice import tts

        tts("test", "en_us_001", filename="/tmp/out.mp3")
        # Should not raise, just log

    @patch("tiktokvoice._generate_single_audio", side_effect=Exception("network"))
    @patch("tiktokvoice._select_available_endpoint", return_value=True)
    def test_exception_logged(self, mock_ep, mock_gen):
        from tiktokvoice import tts

        tts("test", "en_us_001", filename="/tmp/out.mp3")
        # Should not raise


class TestGenerateChunkedAudio:
    @patch("tiktokvoice._generate_single_audio")
    def test_combines_chunks(self, mock_single):
        from tiktokvoice import _generate_chunked_audio

        mock_single.side_effect = ["part1", "part2"]
        result = _generate_chunked_audio("word " * 100, "en_us_001")
        assert "part1" in result
        assert "part2" in result
