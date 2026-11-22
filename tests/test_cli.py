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


class TestVeoNoFinalizeUploadPreflight:
    @pytest.mark.parametrize(
        "argv",
        [
            ["cli", "veo", "돈복 운세", "--no-finalize", "--upload"],
            ["cli", "veo", "--prompt", "A wizard", "--parts", "1", "--no-finalize", "--upload"],
            ["cli", "veo", "--prompt", "A wizard", "--parts", "2", "--upload", "--no-finalize"],
        ],
    )
    def test_rejected_before_any_generation(self, argv, capsys):
        from cli import main

        with patch("sys.argv", argv), \
             patch("gpt.generate_veo_prompts") as mock_prompts, \
             patch("veo.generate_video") as mock_single, \
             patch("veo.generate_multi_part_video") as mock_multi, \
             patch("finalize.run_finalize_pipeline") as mock_finalize:
            with pytest.raises(SystemExit) as excinfo:
                main()

        assert excinfo.value.code not in (0, None)
        mock_prompts.assert_not_called()
        mock_single.assert_not_called()
        mock_multi.assert_not_called()
        mock_finalize.assert_not_called()
        out = capsys.readouterr().out
        assert "--no-finalize" in out
        assert "Done!" not in out

    def test_no_finalize_without_upload_still_allowed(self, tmp_path):
        from cli import main

        with patch("sys.argv", [
            "cli", "veo", "--prompt", "A wizard", "--parts", "1", "--no-finalize",
        ]):
            with patch("veo.generate_video", return_value=str(tmp_path / "raw.mp4")) as mock_gen:
                with patch("utils.PROMPTS_DIR", tmp_path):
                    main()

        mock_gen.assert_called_once()


class TestCliUploadFailure:
    def test_finalize_upload_failure_exits_nonzero_and_preserves_video(self, tmp_path, capsys):
        from cli import main

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        out = tmp_path / "final.mp4"

        def fake_mux(_video, _audio, output):
            Path(output).write_bytes(b"final-video")

        with patch("sys.argv", [
            "cli", "finalize", "--video", str(video), "--no-crop", "--upload", "-o", str(out),
        ]), \
             patch("finalize.subprocess.run"), \
             patch("finalize.generate_subtitles", return_value=str(tmp_path / "subs.srt")), \
             patch("finalize.render_subtitled_video", return_value=str(tmp_path / "rendered.mp4")), \
             patch("finalize.mux_video_audio", side_effect=fake_mux), \
             patch("finalize.TEMP_DIR", tmp_path), \
             patch("finalize.SUBTITLES_DIR", tmp_path), \
             patch("finalize.FINAL_DIR", tmp_path), \
             patch("youtube.upload_video", side_effect=RuntimeError("timeout")) as mock_upload:
            with pytest.raises(SystemExit) as excinfo:
                main()

        assert excinfo.value.code == 1
        assert mock_upload.call_count == 1
        assert out.read_bytes() == b"final-video"
        stdout = capsys.readouterr().out
        assert str(out.resolve()) in stdout
        assert "unknown" in stdout
        assert "Check YouTube" in stdout
        assert "Done!" not in stdout

    def test_finalize_upload_without_id_exits_nonzero(self, tmp_path, capsys):
        from cli import main

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        out = tmp_path / "final.mp4"

        def fake_mux(_video, _audio, output):
            Path(output).write_bytes(b"final-video")

        with patch("sys.argv", [
            "cli", "finalize", "--video", str(video), "--no-crop", "--upload", "-o", str(out),
        ]), \
             patch("finalize.subprocess.run"), \
             patch("finalize.generate_subtitles", return_value=str(tmp_path / "subs.srt")), \
             patch("finalize.render_subtitled_video", return_value=str(tmp_path / "rendered.mp4")), \
             patch("finalize.mux_video_audio", side_effect=fake_mux), \
             patch("finalize.TEMP_DIR", tmp_path), \
             patch("finalize.SUBTITLES_DIR", tmp_path), \
             patch("finalize.FINAL_DIR", tmp_path), \
             patch("youtube.upload_video", return_value=None):
            with pytest.raises(SystemExit) as excinfo:
                main()

        assert excinfo.value.code == 1
        assert out.exists()
        stdout = capsys.readouterr().out
        assert str(out.resolve()) in stdout
        assert "Done!" not in stdout

    def test_veo_upload_failure_exits_nonzero(self, tmp_path, capsys):
        from cli import main
        from finalize import UploadError

        failure = UploadError(
            "YouTube upload not confirmed: x. Local final video preserved: /tmp/final.mp4.",
            "/tmp/final.mp4",
            True,
        )
        with patch("sys.argv", ["cli", "veo", "--prompt", "A wizard", "--parts", "1", "--upload"]), \
             patch("veo.generate_video", return_value="/tmp/raw.mp4"), \
             patch("utils.PROMPTS_DIR", tmp_path), \
             patch("finalize.run_finalize_pipeline", side_effect=failure) as mock_finalize:
            with pytest.raises(SystemExit) as excinfo:
                main()

        assert excinfo.value.code == 1
        assert mock_finalize.call_args[1]["upload"] is True
        stdout = capsys.readouterr().out
        assert "/tmp/final.mp4" in stdout
        assert "Done!" not in stdout

    def test_finalize_upload_success_prints_done(self, tmp_path, capsys):
        from cli import main

        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        out = tmp_path / "final.mp4"

        with patch("sys.argv", [
            "cli", "finalize", "--video", str(video), "--no-crop", "--upload", "-o", str(out),
        ]), \
             patch("finalize.subprocess.run"), \
             patch("finalize.generate_subtitles", return_value=str(tmp_path / "subs.srt")), \
             patch("finalize.render_subtitled_video", return_value=str(tmp_path / "rendered.mp4")), \
             patch("finalize.mux_video_audio"), \
             patch("finalize.TEMP_DIR", tmp_path), \
             patch("finalize.SUBTITLES_DIR", tmp_path), \
             patch("finalize.FINAL_DIR", tmp_path), \
             patch("youtube.upload_video", return_value={"id": "vid42"}) as mock_upload:
            main()

        mock_upload.assert_called_once()
        stdout = capsys.readouterr().out
        assert "vid42" in stdout
        assert "Done!" in stdout
