"""Tests for Backend/veo.py and gpt.generate_veo_prompts"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Backend"))


def _make_operation(video_file=None, done=True):
    """Create a mock Veo operation with explicit error=None."""
    if video_file is None:
        video_file = MagicMock()
    mock_video = MagicMock()
    mock_video.video = video_file
    op = MagicMock()
    op.done = done
    op.error = None  # Must be explicit — MagicMock() is truthy
    op.response.generated_videos = [mock_video]
    return op


class TestGenerateVideo:
    def test_missing_api_key_raises(self):
        import veo

        with patch.object(veo, "GOOGLE_API_KEY", ""):
            with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
                veo._client()

    def test_generates_and_saves_video(self, tmp_path):
        import veo

        mock_video_file = MagicMock()
        operation = _make_operation(mock_video_file)

        mock_client = MagicMock()
        mock_client.models.generate_videos.return_value = operation

        output = str(tmp_path / "test.mp4")

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                result = veo.generate_video(prompt="A cat sitting", output_path=output)

        assert result == output
        mock_client.models.generate_videos.assert_called_once()
        mock_client.files.download.assert_called_once_with(file=mock_video_file)
        mock_video_file.save.assert_called_once_with(output)

    def test_polls_until_done(self, tmp_path):
        import veo

        mock_video_file = MagicMock()
        op_pending = MagicMock()
        op_pending.done = False
        op_done = _make_operation(mock_video_file)

        mock_client = MagicMock()
        mock_client.models.generate_videos.return_value = op_pending
        mock_client.operations.get.return_value = op_done

        output = str(tmp_path / "poll_test.mp4")

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "POLL_INTERVAL", 0):
                with patch("time.sleep"):
                    result = veo.generate_video(prompt="test", output_path=output)

        assert result == output
        mock_client.operations.get.assert_called_once()

    def test_timeout_raises(self):
        import veo

        op_pending = MagicMock()
        op_pending.done = False

        mock_client = MagicMock()
        mock_client.operations.get.return_value = op_pending

        with patch.object(veo, "MAX_WAIT_SECONDS", 5):
            with patch.object(veo, "POLL_INTERVAL", 2):
                with patch("time.sleep"):
                    with pytest.raises(TimeoutError, match="5s"):
                        veo._wait_for_operation(mock_client, op_pending)

    def test_default_output_path(self, tmp_path):
        import veo

        mock_video_file = MagicMock()
        operation = _make_operation(mock_video_file)

        mock_client = MagicMock()
        mock_client.models.generate_videos.return_value = operation

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                result = veo.generate_video(prompt="Hello world test")

        assert "Hello_world_test.mp4" in result

    def test_on_log_callback(self, tmp_path):
        import veo

        mock_video_file = MagicMock()
        operation = _make_operation(mock_video_file)

        mock_client = MagicMock()
        mock_client.models.generate_videos.return_value = operation

        log_messages = []

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                veo.generate_video(
                    prompt="test",
                    on_log=lambda msg, lvl: log_messages.append((msg, lvl)),
                )

        assert any("[Veo]" in msg for msg, _ in log_messages)
        assert any(lvl == "success" for _, lvl in log_messages)


class TestMultiPartVideo:
    def _make_mock_client(self):
        """Create a mock client that returns done operations."""
        mock_video_file = MagicMock()
        operation = _make_operation(mock_video_file)

        mock_client = MagicMock()
        mock_client.models.generate_videos.return_value = operation
        return mock_client, mock_video_file

    def test_generates_3_parts(self, tmp_path):
        import veo

        mock_client, mock_video_file = self._make_mock_client()
        output = str(tmp_path / "multi.mp4")

        prompts = [
            {"prompt": "Part 1 hook", "dialogue": "안녕"},
            {"prompt": "Part 2 core", "dialogue": "돈복"},
            {"prompt": "Part 3 cta", "dialogue": "구독"},
        ]

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                with patch("shutil.copy2"):
                    result = veo.generate_multi_part_video(prompts=prompts, output_path=output)

        assert result == output
        # 3 calls: 1 initial + 2 extensions
        assert mock_client.models.generate_videos.call_count == 3
        # 3 saves: per-part only (final uses shutil.copy2)
        assert mock_video_file.save.call_count == 3

    def test_first_part_has_duration_extensions_do_not(self, tmp_path):
        import veo

        mock_client, _ = self._make_mock_client()

        prompts = [
            {"prompt": "Part 1"},
            {"prompt": "Part 2"},
        ]

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                with patch("shutil.copy2"):
                    veo.generate_multi_part_video(prompts=prompts)

        calls = mock_client.models.generate_videos.call_args_list

        # First call should have duration_seconds (SDK may convert to int)
        first_config = calls[0][1]["config"]
        assert str(first_config.duration_seconds) == "8"

        # Second call (extension) should NOT have duration_seconds
        second_kwargs = calls[1][1]
        assert "video" in second_kwargs  # passes previous video

    def test_extension_passes_previous_video(self, tmp_path):
        import veo

        video1_obj = MagicMock()
        video2_file = MagicMock()

        op1 = _make_operation()
        op1.response.generated_videos[0].video = video1_obj

        op2 = _make_operation(video2_file)

        mock_client = MagicMock()
        mock_client.models.generate_videos.side_effect = [op1, op2]

        prompts = [{"prompt": "Part 1"}, {"prompt": "Part 2"}]

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                with patch("shutil.copy2"):
                    veo.generate_multi_part_video(prompts=prompts)

        # Second call should pass video1's video object
        second_call = mock_client.models.generate_videos.call_args_list[1]
        assert second_call[1]["video"] == video1_obj

    def test_single_part_no_extension(self, tmp_path):
        import veo

        mock_client, mock_video_file = self._make_mock_client()

        prompts = [{"prompt": "Only one part"}]

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                with patch("shutil.copy2"):
                    veo.generate_multi_part_video(prompts=prompts)

        assert mock_client.models.generate_videos.call_count == 1


def _writing_video_file(label: bytes):
    """Simulated SDK video whose .save() writes fake bytes (no real media)."""
    video_file = MagicMock()
    video_file.save.side_effect = lambda path: Path(path).write_bytes(label)
    return video_file


def _failed_operation(*, error=None):
    """Simulated completed operation with an error or with no generated videos."""
    op = MagicMock()
    op.done = True
    op.error = error
    op.response.generated_videos = []
    return op


class TestMultiPartFailClosed:
    """Offline simulations of partial Veo failures (no real API, no real media)."""

    @pytest.mark.parametrize(
        "failed_op, reason_text",
        [
            (_failed_operation(error="quota exceeded"), "quota exceeded"),
            (_failed_operation(error=None), "no video returned"),
        ],
        ids=["extension_error", "extension_empty_response"],
    )
    def test_extension_failure_keeps_last_good_part_and_raises(
        self, tmp_path, failed_op, reason_text
    ):
        import veo

        part1_file = _writing_video_file(b"part1")
        op1 = _make_operation(part1_file)

        mock_client = MagicMock()
        mock_client.models.generate_videos.side_effect = [op1, failed_op]

        output = tmp_path / "final_out.mp4"
        prompts = [{"prompt": "Part 1"}, {"prompt": "Part 2"}, {"prompt": "Part 3"}]

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                with pytest.raises(veo.VeoPartialFailureError) as exc_info:
                    veo.generate_multi_part_video(prompts=prompts, output_path=str(output))

        err = exc_info.value
        assert not isinstance(err, FileNotFoundError)
        assert err.failed_part == 2
        assert err.total_parts == 3

        expected_part1 = tmp_path / "raw" / "final_out_part1.mp4"
        assert err.last_good_path == str(expected_part1)
        assert str(expected_part1) in str(err)
        assert "part 2/3" in str(err)
        assert reason_text in str(err)

        # Last good part is preserved; no final output and no failed-part file.
        assert expected_part1.read_bytes() == b"part1"
        assert not output.exists()
        assert not (tmp_path / "raw" / "final_out_part2.mp4").exists()

        # No retry and no further extensions after the failure.
        assert mock_client.models.generate_videos.call_count == 2

    @pytest.mark.parametrize(
        "bad_part",
        [
            {"prompt": "   "},
            {"prompt": ""},
            {},
            {"prompt": None},
            {"prompt": 123},
            "not a dict",
            None,
        ],
        ids=["blank", "empty", "missing", "none", "non_string", "string_item", "none_item"],
    )
    def test_invalid_later_prompt_makes_no_api_calls(self, tmp_path, bad_part):
        import veo

        mock_client = MagicMock()
        client_factory = MagicMock(return_value=mock_client)
        prompts = [{"prompt": "Valid part 1"}, {"prompt": "Valid part 2"}, bad_part]

        with patch.object(veo, "_client", client_factory):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                with pytest.raises(ValueError, match="part 3"):
                    veo.generate_multi_part_video(prompts=prompts)

        client_factory.assert_not_called()
        mock_client.models.generate_videos.assert_not_called()
        assert not (tmp_path / "raw").exists()

    @pytest.mark.parametrize("bad_prompts", [[], None, {"prompt": "x"}])
    def test_invalid_prompt_container_makes_no_api_calls(self, tmp_path, bad_prompts):
        import veo

        client_factory = MagicMock()

        with patch.object(veo, "_client", client_factory):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                with pytest.raises(ValueError):
                    veo.generate_multi_part_video(prompts=bad_prompts)

        client_factory.assert_not_called()

    @pytest.mark.parametrize("part_count", [2, 3])
    def test_success_saves_all_parts_and_final_copy(self, tmp_path, part_count):
        import veo

        files = [_writing_video_file(f"part{i}".encode()) for i in range(1, part_count + 1)]
        ops = [_make_operation(f) for f in files]

        mock_client = MagicMock()
        mock_client.models.generate_videos.side_effect = ops

        output = tmp_path / "final_out.mp4"
        prompts = [{"prompt": f"Part {i}"} for i in range(1, part_count + 1)]

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                result = veo.generate_multi_part_video(prompts=prompts, output_path=str(output))

        assert result == str(output)
        assert output.read_bytes() == f"part{part_count}".encode()
        # Successful intermediate parts are kept.
        for i in range(1, part_count + 1):
            assert (tmp_path / "raw" / f"final_out_part{i}.mp4").read_bytes() == f"part{i}".encode()
        assert mock_client.models.generate_videos.call_count == part_count

    def test_timeout_during_extension_propagates_without_retry(self, tmp_path):
        import veo

        part1_file = _writing_video_file(b"part1")
        op1 = _make_operation(part1_file)
        pending = MagicMock()
        pending.done = False

        mock_client = MagicMock()
        mock_client.models.generate_videos.side_effect = [op1, pending]
        mock_client.operations.get.return_value = pending

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
                with patch.object(veo, "MAX_WAIT_SECONDS", 0):
                    with pytest.raises(TimeoutError):
                        veo.generate_multi_part_video(
                            prompts=[{"prompt": "Part 1"}, {"prompt": "Part 2"}],
                            output_path=str(tmp_path / "out.mp4"),
                        )

        assert mock_client.models.generate_videos.call_count == 2
        assert (tmp_path / "raw" / "out_part1.mp4").read_bytes() == b"part1"
        assert not (tmp_path / "out.mp4").exists()

    def test_cli_does_not_finalize_or_upload_on_partial_failure(self, tmp_path):
        import utils
        import veo
        from cli import main

        parts = [{"prompt": "Part 1", "dialogue": "a"}, {"prompt": "Part 2", "dialogue": "b"}]
        op1 = _make_operation(_writing_video_file(b"part1"))
        mock_client = MagicMock()
        mock_client.models.generate_videos.side_effect = [
            op1,
            _failed_operation(error=None),
        ]

        with patch("sys.argv", ["cli", "veo", "topic", "--parts", "2", "--upload"]):
            with patch("gpt.generate_veo_prompts", return_value=parts):
                with patch("workflow.extract_script", return_value="a\nb"):
                    with patch.object(veo, "_client", return_value=mock_client):
                        with patch.object(veo, "OUTPUT_DIR", tmp_path):
                            with patch("finalize.run_finalize_pipeline") as mock_finalize:
                                with patch.object(utils, "PROMPTS_DIR", tmp_path / "prompts"):
                                    with pytest.raises(SystemExit) as exc_info:
                                        main()

        assert exc_info.value.code == 1
        mock_finalize.assert_not_called()
        assert mock_client.models.generate_videos.call_count == 2
        assert (tmp_path / "raw" / "Part_1_part1.mp4").read_bytes() == b"part1"


class TestGenerateVeoPrompts:
    def test_returns_list_of_parts(self, tmp_path):
        import gpt
        import utils

        fake_response = '''[
            {"prompt": "A wizard in a dark room. vertical 9:16 aspect ratio. no background music.", "dialogue": "운명이다", "situation": "마법사가 등장"},
            {"prompt": "Close up shot. vertical 9:16.", "dialogue": "돈복이 온다", "situation": "카드를 펼침"},
            {"prompt": "Wide shot. vertical 9:16.", "dialogue": "구독하세요", "situation": "마무리"}
        ]'''

        with patch.object(gpt, "generate_response", return_value=fake_response):
            with patch.object(utils, "OUTPUT_DIR", tmp_path):
                result = gpt.generate_veo_prompts("돈복", "", num_parts=3)

        assert len(result) == 3
        assert result[0]["dialogue"] == "운명이다"
        assert "9:16" in result[0]["prompt"]

    def test_fallback_on_bad_json(self, tmp_path):
        import gpt
        import utils

        with patch.object(gpt, "generate_response", return_value="This is not JSON at all"):
            with patch.object(utils, "OUTPUT_DIR", tmp_path):
                result = gpt.generate_veo_prompts("test", "")

        assert len(result) == 1
        assert result[0]["prompt"] == "This is not JSON at all"

    def test_extracts_json_from_markdown(self, tmp_path):
        import gpt
        import utils

        fake_response = '''Here are the prompts:
```json
[{"prompt": "test prompt", "dialogue": "테스트", "situation": "장면"}]
```'''

        with patch.object(gpt, "generate_response", return_value=fake_response):
            with patch.object(utils, "OUTPUT_DIR", tmp_path):
                result = gpt.generate_veo_prompts("test", "")

        assert len(result) == 1
        assert result[0]["prompt"] == "test prompt"

    def test_num_parts_in_llm_prompt(self, tmp_path):
        import gpt
        import utils

        with patch.object(gpt, "generate_response", return_value='[{"prompt":"x","dialogue":"","situation":""}]') as mock:
            with patch.object(utils, "OUTPUT_DIR", tmp_path):
                gpt.generate_veo_prompts("topic", "model-1", num_parts=4)

        call_prompt = mock.call_args[0][0]
        assert "4-part" in call_prompt
        assert "32 seconds" in call_prompt

    def test_saves_to_archive(self, tmp_path):
        import gpt
        import utils

        fake_response = '[{"prompt": "test", "dialogue": "테스트", "situation": "장면"}]'

        with patch.object(gpt, "generate_response", return_value=fake_response):
            with patch.object(utils, "OUTPUT_DIR", tmp_path):
                gpt.generate_veo_prompts("돈복 테스트", "")

        archive_file = tmp_path / "archive.json"
        assert archive_file.exists()
        archive = json.loads(archive_file.read_text())
        assert len(archive) == 1
        assert archive[0]["subject"] == "돈복 테스트"
        assert archive[0]["parts"][0]["dialogue"] == "테스트"

    def test_archive_included_in_prompt(self, tmp_path):
        import gpt
        import utils

        # Pre-populate archive
        archive_file = tmp_path / "archive.json"
        archive_file.write_text(json.dumps([
            {"date": "2026-03-01", "subject": "사주팔자", "parts": [
                {"prompt": "old", "dialogue": "옛날", "situation": "한복 점술사"}
            ]}
        ], ensure_ascii=False))

        with patch.object(gpt, "generate_response", return_value='[{"prompt":"x","dialogue":"","situation":""}]') as mock:
            with patch.object(utils, "OUTPUT_DIR", tmp_path):
                gpt.generate_veo_prompts("돈복", "")

        call_prompt = mock.call_args[0][0]
        assert "사주팔자" in call_prompt
        assert "PREVIOUS VIDEOS" in call_prompt

    def test_archive_accumulates(self, tmp_path):
        import gpt
        import utils

        fake_response = '[{"prompt": "x", "dialogue": "y", "situation": "z"}]'

        with patch.object(gpt, "generate_response", return_value=fake_response):
            with patch.object(utils, "OUTPUT_DIR", tmp_path):
                gpt.generate_veo_prompts("주제1", "")
                gpt.generate_veo_prompts("주제2", "")

        archive = json.loads((tmp_path / "archive.json").read_text())
        assert len(archive) == 2
        assert archive[0]["subject"] == "주제1"
        assert archive[1]["subject"] == "주제2"
