"""Tests for ffmpeg_utils.py — FFmpeg subprocess wrappers."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestRunFfmpeg:
    @patch("ffmpeg_utils.subprocess.run")
    def test_calls_subprocess(self, mock_run):
        from ffmpeg_utils import _run_ffmpeg

        _run_ffmpeg(["ffmpeg", "-version"])
        mock_run.assert_called_once_with(
            ["ffmpeg", "-version"], check=True, capture_output=True, text=True
        )

    @patch("ffmpeg_utils.subprocess.run")
    def test_raises_runtime_error_on_failure(self, mock_run):
        from ffmpeg_utils import _run_ffmpeg

        mock_run.side_effect = subprocess.CalledProcessError(
            1, "ffmpeg", stderr="codec not found"
        )

        with pytest.raises(RuntimeError, match="(?s)ffmpeg failed.*codec not found"):
            _run_ffmpeg(["ffmpeg", "-invalid"])


class TestMuxVideoAudio:
    @patch("ffmpeg_utils.subprocess.run")
    def test_passes_correct_ffmpeg_args(self, mock_run):
        from ffmpeg_utils import mux_video_audio

        mux_video_audio("/input.mp4", "/audio.wav", "/output.mp4")

        args = mock_run.call_args[0][0]
        assert args[0] == "ffmpeg"
        assert "-y" in args
        assert "/input.mp4" in args
        assert "/audio.wav" in args
        assert "/output.mp4" in args
        assert "-map" in args
        assert "0:v:0" in args
        assert "1:a:0" in args
        assert "-shortest" in args
        assert "-c:v" in args
        assert "copy" in args
        assert "-c:a" in args
        assert "aac" in args

    @patch("ffmpeg_utils.subprocess.run")
    def test_raises_on_failure(self, mock_run):
        from ffmpeg_utils import mux_video_audio

        mock_run.side_effect = subprocess.CalledProcessError(
            1, "ffmpeg", stderr="no such file"
        )

        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            mux_video_audio("/bad.mp4", "/bad.wav", "/out.mp4")


class TestRenderSubtitledVideo:
    @patch("ffmpeg_utils.generate_video", return_value="rendered_abc.mp4")
    @patch("ffmpeg_utils.shutil.copy2")
    def test_copies_video_and_renders(self, mock_copy, mock_gen_video, tmp_path):
        import ffmpeg_utils

        with patch.object(ffmpeg_utils, "TEMP_DIR", tmp_path):
            result = ffmpeg_utils.render_subtitled_video(
                "/input.mp4",
                "/audio.wav",
                "/subs.srt",
                "center,bottom",
                "#FFFFFF",
            )

        mock_copy.assert_called_once()
        mock_gen_video.assert_called_once()
        assert result.endswith("rendered_abc.mp4")

    @patch("ffmpeg_utils.generate_video", return_value="rendered.mp4")
    @patch("ffmpeg_utils.shutil.copy2")
    def test_passes_font_size_and_custom_font(self, mock_copy, mock_gen_video, tmp_path):
        import ffmpeg_utils

        with patch.object(ffmpeg_utils, "TEMP_DIR", tmp_path):
            ffmpeg_utils.render_subtitled_video(
                "/input.mp4",
                "/audio.wav",
                "/subs.srt",
                font_size=48,
                custom_font="/System/Library/Fonts/Test.ttc",
            )

        gen_kwargs = mock_gen_video.call_args
        assert gen_kwargs[1]["font_size"] == 48
        assert gen_kwargs[1]["custom_font"] == "/System/Library/Fonts/Test.ttc"

    @patch("ffmpeg_utils.generate_video", return_value="rendered.mp4")
    @patch("ffmpeg_utils.shutil.copy2")
    def test_default_values(self, mock_copy, mock_gen_video, tmp_path):
        import ffmpeg_utils

        with patch.object(ffmpeg_utils, "TEMP_DIR", tmp_path):
            ffmpeg_utils.render_subtitled_video(
                "/input.mp4",
                "/audio.wav",
                "/subs.srt",
            )

        gen_args = mock_gen_video.call_args
        # Default subs_position
        assert gen_args[0][4] == "center,bottom"
        # Default subs_color
        assert gen_args[0][5] == "#FFFFFF"
