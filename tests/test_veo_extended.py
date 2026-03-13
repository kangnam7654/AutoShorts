"""Extended tests for veo.py — Vertex AI branches, validation, helpers."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestOperationError:
    def test_none_error(self):
        from veo import _operation_error

        op = MagicMock()
        op.error = None
        assert _operation_error(op) is None

    def test_false_error(self):
        from veo import _operation_error

        op = MagicMock()
        op.error = False
        assert _operation_error(op) is None

    def test_error_with_code(self):
        from veo import _operation_error

        error_obj = MagicMock()
        error_obj.code = 400
        error_obj.message = "bad request"
        op = MagicMock()
        op.error = error_obj
        assert _operation_error(op) == error_obj

    def test_string_error(self):
        from veo import _operation_error

        op = MagicMock(spec=[])
        op.error = "Something went wrong"
        assert _operation_error(op) == "Something went wrong"


class TestGeneratedVideos:
    def test_returns_videos(self):
        from veo import _generated_videos

        op = MagicMock()
        op.response.generated_videos = ["v1", "v2"]
        assert _generated_videos(op) == ["v1", "v2"]

    def test_no_response(self):
        from veo import _generated_videos

        op = MagicMock(spec=[])
        op.response = None
        assert _generated_videos(op) == []

    def test_no_generated_videos(self):
        from veo import _generated_videos

        op = MagicMock()
        op.response.generated_videos = None
        assert _generated_videos(op) == []


class TestValidateGenerationResult:
    def test_error_raises_when_not_partial(self):
        from veo import _validate_generation_result

        op = MagicMock()
        op.error = MagicMock(code=500, message="fail")

        with pytest.raises(RuntimeError, match="Veo failed"):
            _validate_generation_result(op, part_label="Part 1", allow_partial=False)

    def test_error_returns_false_when_partial(self):
        from veo import _validate_generation_result

        op = MagicMock()
        op.error = MagicMock(code=500, message="fail")

        assert _validate_generation_result(op, part_label="Part 2", allow_partial=True) is False

    def test_no_videos_raises_when_not_partial(self):
        from veo import _validate_generation_result

        op = MagicMock()
        op.error = None
        op.response.generated_videos = []

        with pytest.raises(RuntimeError, match="no video"):
            _validate_generation_result(op, part_label="single", allow_partial=False)

    def test_success(self):
        from veo import _validate_generation_result

        op = MagicMock()
        op.error = None
        op.response.generated_videos = [MagicMock()]

        assert _validate_generation_result(op, part_label="Part 1", allow_partial=False) is True


class TestBuildGenerateConfig:
    def test_with_duration(self):
        import veo

        types_module = MagicMock()
        config = veo._build_generate_config(types_module, resolution="720p", duration=8)
        call_kwargs = types_module.GenerateVideosConfig.call_args[1]
        assert call_kwargs["duration_seconds"] == 8
        assert call_kwargs["resolution"] == "720p"
        assert call_kwargs["aspect_ratio"] == "9:16"

    def test_without_duration(self):
        import veo

        types_module = MagicMock()
        config = veo._build_generate_config(types_module, resolution="1080p")
        call_kwargs = types_module.GenerateVideosConfig.call_args[1]
        assert "duration_seconds" not in call_kwargs

    @patch("veo.VEO_USE_VERTEX", True)
    def test_vertex_includes_gcs_uri(self):
        import veo

        types_module = MagicMock()
        veo._build_generate_config(types_module, resolution="720p")
        call_kwargs = types_module.GenerateVideosConfig.call_args[1]
        assert "output_gcs_uri" in call_kwargs


class TestSlugFromPrompt:
    def test_basic_slug(self):
        from veo import _slug_from_prompt

        assert _slug_from_prompt("Hello world test") == "Hello_world_test"

    def test_special_chars_removed(self):
        from veo import _slug_from_prompt

        result = _slug_from_prompt("Hello@#$% world!")
        assert "@" not in result
        assert "#" not in result

    def test_empty_prompt(self):
        from veo import _slug_from_prompt

        assert _slug_from_prompt("@#$") == "veo_output"


class TestCleanVeoSubtitles:
    def test_generates_clean_path(self):
        import veo

        with patch("ffmpeg_utils._run_ffmpeg") as mock_ffmpeg:
            result = veo.clean_veo_subtitles("/tmp/video.mp4", height=200)

        assert "_clean" in result
        assert result.endswith(".mp4")


class TestSaveVideo:
    def test_developer_api_mode(self):
        import veo

        with patch.object(veo, "VEO_USE_VERTEX", False):
            mock_client = MagicMock()
            video_obj = MagicMock()

            veo._save_video(mock_client, video_obj, "/tmp/out.mp4")

            mock_client.files.download.assert_called_once_with(file=video_obj)
            video_obj.save.assert_called_once_with("/tmp/out.mp4")

    def test_vertex_with_gcs(self):
        import veo

        with patch.object(veo, "VEO_USE_VERTEX", True):
            with patch.object(veo, "_download_from_gcs") as mock_dl:
                video_obj = MagicMock()
                video_obj.uri = "gs://bucket/path/video.mp4"

                veo._save_video(MagicMock(), video_obj, "/tmp/out.mp4")
                mock_dl.assert_called_once()

    def test_vertex_without_gcs(self):
        import veo

        with patch.object(veo, "VEO_USE_VERTEX", True):
            video_obj = MagicMock(spec=[])
            video_obj.uri = None
            video_obj.save = MagicMock()

            veo._save_video(MagicMock(), video_obj, "/tmp/out.mp4")
            video_obj.save.assert_called_once()


class TestLoadReferenceImage:
    def test_loads_png(self, tmp_path):
        import veo

        img_path = tmp_path / "ref.png"
        img_path.write_bytes(b"\x89PNG\r\n")

        with patch.dict("sys.modules", {"google.genai": MagicMock(), "google": MagicMock()}):
            with patch("veo.types", create=True) as mock_types:
                mock_types.Image = MagicMock()
                result = veo._load_reference_image(str(img_path))

    def test_file_not_found(self):
        import veo

        with pytest.raises(FileNotFoundError):
            veo._load_reference_image("/nonexistent/image.png")
