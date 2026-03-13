"""Extended tests for cli.py — command handlers and dispatch logic."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestColor:
    def test_wraps_text_with_ansi(self):
        from cli import color

        result = color("hello", "31")
        assert "\033[31m" in result
        assert "hello" in result
        assert "\033[0m" in result


class TestLogHandler:
    def test_prints_message(self, capsys):
        from cli import log_handler

        log_handler("test message", "info")
        output = capsys.readouterr().out
        assert "test message" in output

    def test_different_levels(self, capsys):
        from cli import log_handler

        for level in ("info", "success", "warning", "error"):
            log_handler(f"{level} msg", level)

        output = capsys.readouterr().out
        assert "info msg" in output
        assert "error msg" in output


class TestDoAuth:
    @patch("codex_auth.login")
    def test_successful_auth(self, mock_login, capsys):
        from cli import do_auth

        do_auth()
        mock_login.assert_called_once()
        output = capsys.readouterr().out
        assert "Done" in output

    @patch("codex_auth.login", side_effect=Exception("auth failed"))
    def test_failed_auth(self, mock_login):
        from cli import do_auth

        with pytest.raises(SystemExit):
            do_auth()


class TestListModels:
    @patch("gpt.list_models", return_value=(["m1", "m2"], "m1"))
    def test_prints_models(self, mock_list, capsys):
        from cli import list_models

        list_models()
        output = capsys.readouterr().out
        assert "m1" in output
        assert "m2" in output
        assert "(default)" in output


class TestListVoices:
    @patch.dict("os.environ", {"TTS_PROVIDER": "tiktok"})
    def test_lists_tiktok_voices(self, capsys):
        from cli import list_voices

        list_voices()
        output = capsys.readouterr().out
        assert "tiktok" in output

    @patch.dict("os.environ", {"TTS_PROVIDER": "qwen"})
    def test_lists_qwen_voices(self, capsys):
        from cli import list_voices

        list_voices()
        output = capsys.readouterr().out
        assert "qwen" in output


class TestMainDispatch:
    def test_auth_command(self):
        from cli import main

        with patch("sys.argv", ["cli", "auth"]):
            with patch("codex_auth.login"):
                main()

    def test_models_command(self):
        from cli import main

        with patch("sys.argv", ["cli", "models"]):
            with patch("gpt.list_models", return_value=(["m1"], "m1")):
                main()

    def test_voices_command(self):
        from cli import main

        with patch("sys.argv", ["cli", "voices"]):
            with patch.dict("os.environ", {"TTS_PROVIDER": "tiktok"}):
                main()

    def test_no_command_prints_help(self, capsys):
        from cli import main

        with patch("sys.argv", ["cli"]):
            main()

        output = capsys.readouterr().out
        assert "usage" in output.lower() or "moneyprinter" in output.lower()

    def test_veo_requires_subject_or_prompt(self):
        from cli import main

        with patch("sys.argv", ["cli", "veo"]):
            with pytest.raises(SystemExit):
                main()

    def test_generate_dispatches(self):
        from cli import main

        with patch("sys.argv", ["cli", "generate", "cats"]):
            with patch("pipeline.run_generation_pipeline", return_value="out.mp4"):
                main()

    def test_compose_dispatches(self, tmp_path):
        from cli import main

        video = tmp_path / "v.mp4"
        video.write_bytes(b"fake")

        with patch("sys.argv", [
            "cli", "compose",
            "--video", str(video),
            "--script", "Hello world.",
        ]):
            with patch("compose.run_compose_pipeline", return_value="out.mp4"):
                main()


class TestVeoPromptFile:
    def test_veo_with_prompt_file(self, tmp_path):
        import json

        from cli import main

        prompt_file = tmp_path / "prompts.json"
        prompt_file.write_text(json.dumps([{"prompt": "test prompt", "dialogue": "안녕"}]))

        with patch("sys.argv", [
            "cli", "veo",
            "--prompt-file", str(prompt_file),
            "--no-finalize",
            "-o", str(tmp_path / "out.mp4"),
        ]):
            with patch("veo.generate_multi_part_video", return_value=str(tmp_path / "out.mp4")):
                with patch("utils.PROMPTS_DIR", tmp_path):
                    (tmp_path / "out.mp4").write_bytes(b"video")
                    main()

    def test_veo_with_direct_prompt(self, tmp_path):
        from cli import main

        with patch("sys.argv", [
            "cli", "veo",
            "--prompt", "A wizard in a cave",
            "--no-finalize",
            "--parts", "1",
            "-o", str(tmp_path / "out.mp4"),
        ]):
            with patch("veo.generate_video", return_value=str(tmp_path / "out.mp4")) as mock_gen:
                with patch("utils.PROMPTS_DIR", tmp_path):
                    (tmp_path / "out.mp4").write_bytes(b"video")
                    main()

                mock_gen.assert_called_once()

    def test_veo_multi_part_direct_prompt(self, tmp_path):
        from cli import main

        with patch("sys.argv", [
            "cli", "veo",
            "--prompt", "A wizard",
            "--no-finalize",
            "--parts", "2",
            "-o", str(tmp_path / "out.mp4"),
        ]):
            with patch("veo.generate_multi_part_video", return_value=str(tmp_path / "out.mp4")):
                with patch("utils.PROMPTS_DIR", tmp_path):
                    (tmp_path / "out.mp4").write_bytes(b"video")
                    main()
