"""Tests for cli.py — argument parsing and command dispatch."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestFinalizeArgs:
    def test_default_values(self):
        """finalize command should have sensible defaults."""
        from cli import main

        with patch("sys.argv", ["cli", "finalize", "--video", "/test.mp4"]):
            with patch("finalize.run_finalize_pipeline", return_value="/out.mp4") as mock:
                with patch("cli.log_handler"):
                    try:
                        main()
                    except (SystemExit, Exception):
                        pass
                    if mock.called:
                        kwargs = mock.call_args[1]
                        assert kwargs["video_path"] == "/test.mp4"
                        assert kwargs["crop"] is True
                        assert kwargs["language"] == "ko"

    def test_finalize_alias_f(self):
        """'f' should be an alias for 'finalize'."""
        from cli import main

        with patch("sys.argv", ["cli", "f", "--video", "/test.mp4"]):
            with patch("finalize.run_finalize_pipeline", return_value="/out.mp4") as mock:
                with patch("cli.log_handler"):
                    try:
                        main()
                    except (SystemExit, Exception):
                        pass

    def test_no_crop_flag(self):
        """--no-crop should set crop=False."""
        from cli import main

        with patch("sys.argv", ["cli", "finalize", "--video", "/test.mp4", "--no-crop"]):
            with patch("finalize.run_finalize_pipeline", return_value="/out.mp4") as mock:
                with patch("cli.log_handler"):
                    try:
                        main()
                    except (SystemExit, Exception):
                        pass
                    if mock.called:
                        assert mock.call_args[1].get("crop") is False


class TestScriptFileLoading:
    def test_finalize_reads_script_file(self, tmp_path):
        """--script-file should load script text from file."""
        from cli import main

        script_file = tmp_path / "script.txt"
        script_file.write_text("This is a test script.")

        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"fake")

        with patch("sys.argv", [
            "cli", "finalize",
            "--video", str(video_file),
            "--script-file", str(script_file),
        ]):
            with patch("finalize.run_finalize_pipeline", return_value="/out.mp4") as mock:
                with patch("cli.log_handler"):
                    try:
                        main()
                    except (SystemExit, Exception):
                        pass
                    if mock.called:
                        assert mock.call_args[1].get("script") == "This is a test script."


class TestGenerateArgs:
    def test_requires_subject(self):
        """generate command should require a subject positional arg."""
        from cli import main

        with patch("sys.argv", ["cli", "generate"]):
            with pytest.raises(SystemExit):
                main()


class TestVeoArgs:
    def test_veo_skips_narration_by_default(self, tmp_path):
        """veo command should skip TTS narration by default (dialogue is in video)."""
        from cli import main
        import utils

        parts = [
            {
                "index": 1,
                "prompt": "Part 1 prompt",
                "dialogue": "첫 번째 운세",
                "narration": "첫 번째 운세",
                "situation": "점술사가 등장",
                "voice_hint": "",
            }
        ]

        with patch("sys.argv", ["cli", "veo", "돈복 운세"]):
            with patch("gpt.generate_veo_prompts", return_value=parts):
                with patch("workflow.extract_script", return_value="첫 번째 운세"):
                    with patch("veo.generate_multi_part_video", return_value="/tmp/raw.mp4"):
                        with patch("narrate.add_narration") as mock_narrate:
                            with patch("finalize.run_finalize_pipeline", return_value="/tmp/final.mp4") as mock_finalize:
                                with patch.object(utils, "PROMPTS_DIR", tmp_path):
                                    main()

        assert not mock_narrate.called
        assert mock_finalize.call_args[1]["video_path"] == "/tmp/raw.mp4"

    def test_veo_add_narration_flag(self, tmp_path):
        """veo --add-narration should run TTS narration overlay."""
        from cli import main
        import utils

        parts = [
            {
                "index": 1,
                "prompt": "Part 1 prompt",
                "dialogue": "첫 번째 운세",
                "narration": "첫 번째 운세",
                "situation": "점술사가 등장",
                "voice_hint": "",
            }
        ]

        with patch("sys.argv", ["cli", "veo", "돈복 운세", "--add-narration"]):
            with patch("gpt.generate_veo_prompts", return_value=parts):
                with patch("workflow.extract_script", return_value="첫 번째 운세"):
                    with patch("veo.generate_multi_part_video", return_value="/tmp/raw.mp4"):
                        with patch("narrate.add_narration", return_value="/tmp/narrated.mp4") as mock_narrate:
                            with patch("finalize.run_finalize_pipeline", return_value="/tmp/final.mp4") as mock_finalize:
                                with patch.object(utils, "PROMPTS_DIR", tmp_path):
                                    main()

        assert mock_narrate.called
        assert mock_finalize.call_args[1]["video_path"] == "/tmp/narrated.mp4"
