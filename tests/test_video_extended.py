"""Extended tests for video.py — save_video, language codes, whisper SRT."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestSaveVideo:
    @patch("video.requests.get")
    def test_downloads_and_saves(self, mock_get, tmp_path):
        from video import save_video

        mock_get.return_value = MagicMock(content=b"video data")

        result = save_video("http://example.com/video.mp4", str(tmp_path))
        assert Path(result).exists()
        assert Path(result).read_bytes() == b"video data"

    @patch("video.requests.get")
    def test_creates_directory(self, mock_get, tmp_path):
        from video import save_video

        mock_get.return_value = MagicMock(content=b"data")
        target = str(tmp_path / "new_dir")

        result = save_video("http://example.com/v.mp4", target)
        assert Path(result).parent.exists()


class TestSubtitleLanguageCode:
    def test_korean_mapping(self):
        from video import _subtitle_language_code

        assert _subtitle_language_code("kr") == "ko"

    def test_japanese_mapping(self):
        from video import _subtitle_language_code

        assert _subtitle_language_code("jp") == "ja"

    def test_brazilian_mapping(self):
        from video import _subtitle_language_code

        assert _subtitle_language_code("br") == "pt"

    def test_passthrough(self):
        from video import _subtitle_language_code

        assert _subtitle_language_code("en") == "en"
        assert _subtitle_language_code("fr") == "fr"


class TestWhisperLanguageCode:
    def test_known_languages(self):
        from video import _whisper_language_code

        assert _whisper_language_code("ko") == "ko"
        assert _whisper_language_code("ja") == "ja"
        assert _whisper_language_code("en") == "en"

    def test_unknown_defaults_to_en(self):
        from video import _whisper_language_code

        assert _whisper_language_code("xx") == "en"


class TestWhisperWordsToSrtEntries:
    def test_groups_4_words(self):
        from video import _whisper_words_to_srt_entries

        words = [
            {"word": "Hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 0.5, "end": 1.0},
            {"word": "how", "start": 1.0, "end": 1.3},
            {"word": "are", "start": 1.3, "end": 1.5},
            {"word": "you", "start": 1.5, "end": 2.0},
        ]

        entries, next_idx = _whisper_words_to_srt_entries(words, 1)
        assert len(entries) == 2  # 4 words + 1 remaining
        assert "Hello world how are" in entries[0]
        assert "you" in entries[1]
        assert next_idx == 3

    def test_fewer_than_4_words(self):
        from video import _whisper_words_to_srt_entries

        words = [
            {"word": "Hi", "start": 0.0, "end": 0.5},
            {"word": "there", "start": 0.5, "end": 1.0},
        ]

        entries, next_idx = _whisper_words_to_srt_entries(words, 1)
        assert len(entries) == 1
        assert "Hi there" in entries[0]


class TestParseSubtitlesPosition:
    def test_valid_position(self):
        from video import _parse_subtitles_position

        h, v = _parse_subtitles_position("left,top")
        assert h == "left"
        assert v == "top"

    def test_none_defaults(self):
        from video import _parse_subtitles_position

        h, v = _parse_subtitles_position(None)
        assert h == "center"
        assert v == "bottom"

    def test_no_comma_defaults(self):
        from video import _parse_subtitles_position

        h, v = _parse_subtitles_position("center")
        assert h == "center"
        assert v == "bottom"

    def test_invalid_values_corrected(self):
        from video import _parse_subtitles_position

        h, v = _parse_subtitles_position("xyz,abc")
        assert h == "center"
        assert v == "bottom"
