"""Tests for video.py — subtitle generation, SRT formatting, video rendering."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from video import _srt_time, generate_subtitles, generate_video


# --- _srt_time ---

class TestSrtTime:
    def test_zero(self):
        assert _srt_time(0) == "00:00:00,000"

    def test_simple_seconds(self):
        assert _srt_time(1.5) == "00:00:01,500"

    def test_minutes(self):
        assert _srt_time(65.123) == "00:01:05,123"

    def test_hours(self):
        assert _srt_time(3661.999) == "01:01:01,999"

    def test_rounding(self):
        # 0.9999 seconds should round to 1.000
        assert _srt_time(0.9999) == "00:00:01,000"

    def test_large_value(self):
        assert _srt_time(7200.0) == "02:00:00,000"


# --- generate_subtitles ---

class TestGenerateSubtitles:
    def test_local_subtitles_from_sentences(self, tmp_path):
        """Local provider should use sentence/clip pairs for timing."""
        import video

        clip1 = MagicMock()
        clip1.duration = 2.0
        clip2 = MagicMock()
        clip2.duration = 3.0

        with patch.object(video, "SUBTITLE_PROVIDER", "local"):
            with patch.object(video, "ASSEMBLY_AI_API_KEY", None):
                with patch.object(video, "SUBTITLES_DIR", tmp_path):
                    with patch("srt_equalizer.equalize_srt_file"):
                        result = video.generate_subtitles(
                            audio_path="/fake/audio.wav",
                            sentences=["Hello world", "Goodbye"],
                            audio_clips=[clip1, clip2],
                            voice="en",
                        )

        srt = Path(result).read_text()
        assert "Hello world" in srt
        assert "Goodbye" in srt
        assert "00:00:00,000" in srt
        assert "00:00:02,000" in srt  # second sentence starts at 2s

    @patch.dict("os.environ", {"SUBTITLE_PROVIDER": "whisper"})
    def test_whisper_subtitles(self, tmp_path):
        """Whisper provider should call mlx_whisper.transcribe."""
        import importlib
        import video
        importlib.reload(video)

        fake_result = {
            "segments": [{
                "start": 0.0, "end": 2.0, "text": "Hello",
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.5},
                    {"word": "world", "start": 0.5, "end": 1.0},
                    {"word": "this", "start": 1.0, "end": 1.3},
                    {"word": "is", "start": 1.3, "end": 1.5},
                    {"word": "a", "start": 1.5, "end": 1.7},
                    {"word": "test", "start": 1.7, "end": 2.0},
                ],
            }]
        }

        with patch.object(video, "SUBTITLES_DIR", tmp_path):
            with patch("srt_equalizer.equalize_srt_file"):
                with patch.dict("sys.modules", {"mlx_whisper": MagicMock(transcribe=MagicMock(return_value=fake_result))}):
                    result = video.generate_subtitles(
                        audio_path="/fake/audio.wav",
                        sentences=[], audio_clips=[], voice="en",
                    )

        srt = Path(result).read_text()
        # Whisper groups 4 words at a time
        assert "Hello world this is" in srt
        assert "a test" in srt


# --- generate_video ---

class TestGenerateVideo:
    @patch("video.SubtitlesClip")
    @patch("video.AudioFileClip")
    @patch("video.VideoFileClip")
    @patch("video.CompositeVideoClip")
    def test_returns_output_filename(self, mock_comp, mock_vid, mock_audio, mock_subs, tmp_path):
        """generate_video should return 'output.mp4'."""
        import video
        with patch.object(video, "TEMP_DIR", tmp_path):
            with patch.object(video, "FONTS_DIR", tmp_path):
                # Create a fake font file
                (tmp_path / "bold_font.ttf").write_bytes(b"fake")

                mock_base = MagicMock()
                mock_base.duration = 5.0
                mock_base.h = 1920
                mock_vid.return_value = mock_base

                mock_aud = MagicMock()
                mock_aud.duration = 5.0
                mock_audio.return_value = mock_aud

                result = video.generate_video(
                    str(tmp_path / "video.mp4"),
                    str(tmp_path / "audio.wav"),
                    str(tmp_path / "subs.srt"),
                    2, "center,center", "#FFFF00",
                )

        assert result == "output.mp4"

    @patch("video.SubtitlesClip")
    @patch("video.AudioFileClip")
    @patch("video.VideoFileClip")
    @patch("video.CompositeVideoClip")
    def test_bottom_position_calculates_from_height(self, mock_comp, mock_vid, mock_audio, mock_subs, tmp_path):
        """'bottom' vertical position should be 85% of video height."""
        import video
        with patch.object(video, "TEMP_DIR", tmp_path):
            with patch.object(video, "FONTS_DIR", tmp_path):
                (tmp_path / "bold_font.ttf").write_bytes(b"fake")

                mock_base = MagicMock()
                mock_base.duration = 5.0
                mock_base.h = 1920
                mock_vid.return_value = mock_base

                mock_aud = MagicMock()
                mock_aud.duration = 5.0
                mock_audio.return_value = mock_aud

                video.generate_video(
                    str(tmp_path / "video.mp4"),
                    str(tmp_path / "audio.wav"),
                    str(tmp_path / "subs.srt"),
                    2, "center,bottom", "#FFFF00",
                )

        # Check that subtitle position was set to 85% of 1920 = 1632
        subs_clip = mock_subs.return_value
        pos_call = subs_clip.with_position.call_args[0][0]
        assert pos_call == ("center", 1632)

    @patch("video.SubtitlesClip")
    @patch("video.AudioFileClip")
    @patch("video.VideoFileClip")
    @patch("video.CompositeVideoClip")
    def test_missing_subtitles_position_uses_default_bottom(
        self, mock_comp, mock_vid, mock_audio, mock_subs, tmp_path
    ):
        """None subtitles_position should fall back to center,bottom."""
        import video

        with patch.object(video, "TEMP_DIR", tmp_path):
            with patch.object(video, "FONTS_DIR", tmp_path):
                (tmp_path / "bold_font.ttf").write_bytes(b"fake")

                mock_base = MagicMock()
                mock_base.duration = 5.0
                mock_base.h = 1920
                mock_vid.return_value = mock_base

                mock_aud = MagicMock()
                mock_aud.duration = 5.0
                mock_audio.return_value = mock_aud

                video.generate_video(
                    str(tmp_path / "video.mp4"),
                    str(tmp_path / "audio.wav"),
                    str(tmp_path / "subs.srt"),
                    2,
                    None,
                    "#FFFF00",
                )

        subs_clip = mock_subs.return_value
        pos_call = subs_clip.with_position.call_args[0][0]
        assert pos_call == ("center", 1632)
