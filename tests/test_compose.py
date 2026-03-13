"""Tests for compose.py — narration overlay pipeline for existing videos."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestRunComposePipeline:
    def test_raises_on_missing_video(self):
        from compose import run_compose_pipeline

        with pytest.raises(FileNotFoundError, match="Video not found"):
            run_compose_pipeline(video_path="/missing.mp4", script="hello")

    @patch("compose.shutil.copy2")
    @patch("compose.render_subtitled_video", return_value="/tmp/rendered.mp4")
    @patch("compose.generate_subtitles", return_value="/tmp/subtitles.srt")
    @patch("compose.concatenate_audioclips")
    @patch("compose.AudioFileClip")
    @patch("compose.tts_generate")
    def test_uses_voice_prefix_for_subtitles(
        self,
        mock_tts,
        mock_audio_clip,
        mock_concat,
        mock_subtitles,
        mock_render,
        mock_copy,
        tmp_path,
    ):
        import compose
        import tts_utils

        video_path = tmp_path / "input.mp4"
        video_path.write_bytes(b"video")

        clip = MagicMock()
        mock_audio_clip.return_value = clip

        final_audio = MagicMock()
        mock_concat.return_value = final_audio

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with patch.object(compose, "TEMP_DIR", tmp_path), patch.object(
            compose, "SUBTITLES_DIR", tmp_path
        ), patch.object(compose, "OUTPUT_DIR", output_dir), patch.object(
            tts_utils, "TTS_PROVIDER", "tiktok"
        ):
            result = compose.run_compose_pipeline(
                video_path=str(video_path),
                script="Hello world. Another line.",
                voice="en_us_001",
                keep_audio=False,
                output_path="final.mp4",
            )

        assert result == "final.mp4"
        assert mock_subtitles.call_args[1]["voice"] == "en"
        assert final_audio.write_audiofile.called
        assert clip.close.called

