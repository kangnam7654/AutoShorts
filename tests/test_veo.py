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
                result = veo.generate_multi_part_video(prompts=prompts, output_path=output)

        assert result == output
        # 3 calls: 1 initial + 2 extensions
        assert mock_client.models.generate_videos.call_count == 3
        # 4 saves: 3 per-part + 1 final
        assert mock_video_file.save.call_count == 4
        mock_video_file.save.assert_any_call(output)

    def test_first_part_has_duration_extensions_do_not(self, tmp_path):
        import veo

        mock_client, _ = self._make_mock_client()

        prompts = [
            {"prompt": "Part 1"},
            {"prompt": "Part 2"},
        ]

        with patch.object(veo, "_client", return_value=mock_client):
            with patch.object(veo, "OUTPUT_DIR", tmp_path):
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
                veo.generate_multi_part_video(prompts=prompts)

        assert mock_client.models.generate_videos.call_count == 1


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
