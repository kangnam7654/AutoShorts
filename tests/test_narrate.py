"""Tests for narrate.py — TTS narration overlay for generated videos."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestAddNarration:
    def test_raises_on_missing_video(self):
        from narrate import add_narration

        with pytest.raises(FileNotFoundError, match="Video not found"):
            add_narration(video_path="/missing.mp4", script="hello")

    @patch("narrate.mux_video_audio")
    @patch("narrate._mix_narration_with_ambient")
    @patch("narrate._render_narration_audio")
    def test_uses_default_qwen_voice_when_none_provided(
        self,
        mock_render_audio,
        mock_mix_audio,
        mock_mux,
        tmp_path,
    ):
        import narrate
        import tts_utils

        video_path = tmp_path / "input.mp4"
        video_path.write_bytes(b"video")

        narration_path = tmp_path / "narration.mp3"
        narration_path.write_bytes(b"audio")
        mixed_path = tmp_path / "mixed.m4a"
        mixed_path.write_bytes(b"mixed")

        mock_render_audio.return_value = (str(narration_path), 2.5)
        mock_mix_audio.return_value = str(mixed_path)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with patch.object(narrate, "TEMP_DIR", tmp_path), patch.object(
            narrate, "OUTPUT_DIR", output_dir
        ), patch.object(tts_utils, "TTS_PROVIDER", "qwen"):
            result = narrate.add_narration(
                video_path=str(video_path),
                script="첫 번째 문장입니다.",
            )

        assert result == str(output_dir / "narrated" / "input.mp4")
        assert mock_render_audio.call_args[0][1] == "Sohee"
        assert mock_mix_audio.call_args[0][0] == str(video_path)
        assert mock_mux.called

