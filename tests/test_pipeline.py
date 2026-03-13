"""Tests for pipeline.py — video generation pipeline orchestration."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# --- PipelineCancelled ---

class TestPipelineCancelled:
    def test_is_exception(self):
        from pipeline import PipelineCancelled

        with pytest.raises(PipelineCancelled):
            raise PipelineCancelled("cancelled")


# --- _resolve_voice ---

class TestResolveVoice:
    def test_returns_provided_voice(self):
        from pipeline import _resolve_voice

        emit = MagicMock()
        result = _resolve_voice({"voice": "en_us_001"}, emit)
        assert result == "en_us_001"
        emit.assert_not_called()

    @patch("pipeline.default_voice", return_value="en_us_001")
    def test_returns_default_when_empty(self, mock_default):
        from pipeline import _resolve_voice

        emit = MagicMock()
        result = _resolve_voice({"voice": ""}, emit)
        assert result == "en_us_001"
        emit.assert_called()  # warning emitted

    @patch("pipeline.default_voice", return_value="en_us_001")
    def test_returns_default_when_missing(self, mock_default):
        from pipeline import _resolve_voice

        emit = MagicMock()
        result = _resolve_voice({}, emit)
        assert result == "en_us_001"


# --- _collect_video_urls ---

class TestCollectVideoUrls:
    @patch("pipeline.search_for_stock_videos")
    def test_collects_one_unique_url_per_term(self, mock_search):
        from pipeline import _collect_video_urls

        # Each search returns candidates; function picks first unused per term
        mock_search.side_effect = [
            ["url1", "url2"],    # term1 → takes url1
            ["url1", "url3"],    # term2 → url1 already used, takes url3
            ["url4"],            # term3 → takes url4
        ]

        result = _collect_video_urls(["term1", "term2", "term3"], lambda: None)
        assert result == ["url1", "url3", "url4"]

    @patch("pipeline.search_for_stock_videos")
    def test_returns_empty_when_no_results(self, mock_search):
        from pipeline import _collect_video_urls

        mock_search.return_value = []
        result = _collect_video_urls(["term1"], lambda: None)
        assert result == []

    @patch("pipeline.search_for_stock_videos")
    def test_cancellation_check(self, mock_search):
        from pipeline import _collect_video_urls, PipelineCancelled

        mock_search.return_value = ["url1"]

        def cancel():
            raise PipelineCancelled("stop")

        with pytest.raises(PipelineCancelled):
            _collect_video_urls(["t1", "t2"], cancel)


# --- _download_video_paths ---

class TestDownloadVideoPaths:
    @patch("pipeline.save_video")
    def test_downloads_all_videos(self, mock_save):
        from pipeline import _download_video_paths

        mock_save.side_effect = ["/path/1.mp4", "/path/2.mp4"]
        emit = MagicMock()

        result = _download_video_paths(["url1", "url2"], lambda: None, emit)
        assert result == ["/path/1.mp4", "/path/2.mp4"]

    @patch("pipeline.save_video")
    def test_skips_failed_downloads(self, mock_save):
        from pipeline import _download_video_paths

        mock_save.side_effect = ["/path/1.mp4", Exception("network error"), "/path/3.mp4"]
        emit = MagicMock()

        result = _download_video_paths(["url1", "url2", "url3"], lambda: None, emit)
        assert result == ["/path/1.mp4", "/path/3.mp4"]


# --- _upload_to_youtube ---

class TestUploadToYoutube:
    @patch("pipeline.upload_video")
    @patch("pipeline.os.path.exists", return_value=True)
    def test_successful_upload(self, mock_exists, mock_upload):
        from pipeline import _upload_to_youtube

        mock_upload.return_value = {"id": "abc123"}
        emit = MagicMock()

        _upload_to_youtube("/video.mp4", "Title", "Desc", ["kw1"], emit)

        mock_upload.assert_called_once()
        assert any("abc123" in str(c) for c in emit.call_args_list)

    @patch("pipeline.os.path.exists", return_value=False)
    def test_skips_when_no_client_secret(self, mock_exists):
        from pipeline import _upload_to_youtube

        emit = MagicMock()
        _upload_to_youtube("/video.mp4", "Title", "Desc", ["kw1"], emit)

        # Should warn about missing secrets
        assert any("missing" in str(c).lower() for c in emit.call_args_list)

    @patch("pipeline.upload_video")
    @patch("pipeline.os.path.exists", return_value=True)
    def test_handles_http_error(self, mock_exists, mock_upload):
        from apiclient.errors import HttpError
        from pipeline import _upload_to_youtube

        resp = MagicMock()
        resp.status = 403
        resp.content = b"Forbidden"
        mock_upload.side_effect = HttpError(resp, b"Forbidden")

        emit = MagicMock()
        _upload_to_youtube("/video.mp4", "Title", "Desc", [], emit)

        assert any("error" in str(c).lower() or "403" in str(c) for c in emit.call_args_list)


# --- _apply_background_music ---

class TestApplyBackgroundMusic:
    @patch("pipeline.choose_random_song", return_value=None)
    def test_returns_false_when_no_songs(self, mock_song):
        from pipeline import _apply_background_music

        emit = MagicMock()
        result = _apply_background_music("/rendered.mp4", "/output.mp4", 2, emit)
        assert result is False

    @patch("pipeline.os.path.exists", return_value=True)
    @patch("pipeline.os.remove")
    @patch("pipeline._remux_with_ffmpeg")
    @patch("pipeline._write_mixed_audio")
    @patch("pipeline.choose_random_song", return_value="/songs/bgm.mp3")
    def test_uses_ffmpeg_remux(self, mock_song, mock_write, mock_remux, mock_remove, mock_exists):
        from pipeline import _apply_background_music

        emit = MagicMock()
        result = _apply_background_music("/rendered.mp4", "/output.mp4", 2, emit)
        assert result is True
        mock_write.assert_called_once()
        mock_remux.assert_called_once()

    @patch("pipeline.os.path.exists", return_value=True)
    @patch("pipeline.os.remove")
    @patch("pipeline._render_music_fallback")
    @patch("pipeline._remux_with_ffmpeg", side_effect=Exception("ffmpeg fail"))
    @patch("pipeline._write_mixed_audio")
    @patch("pipeline.choose_random_song", return_value="/songs/bgm.mp3")
    def test_falls_back_to_moviepy_on_ffmpeg_failure(
        self, mock_song, mock_write, mock_remux, mock_fallback, mock_remove, mock_exists
    ):
        from pipeline import _apply_background_music

        emit = MagicMock()
        result = _apply_background_music("/rendered.mp4", "/output.mp4", 2, emit)
        assert result is True
        mock_fallback.assert_called_once()


# --- _emit_generation_summary ---

class TestEmitGenerationSummary:
    def test_emits_subject_and_model(self):
        from pipeline import _emit_generation_summary

        emit = MagicMock()
        data = {"videoSubject": "cats", "aiModel": "llama3.1:8b", "customPrompt": "be funny"}
        _emit_generation_summary(data, emit)

        messages = " ".join(str(c) for c in emit.call_args_list)
        assert "cats" in messages
        assert "llama3.1:8b" in messages


# --- _emit_metadata ---

class TestEmitMetadata:
    def test_emits_all_fields(self):
        from pipeline import _emit_metadata

        emit = MagicMock()
        _emit_metadata("My Title", "My Desc", ["kw1", "kw2"], emit)

        messages = " ".join(str(c) for c in emit.call_args_list)
        assert "My Title" in messages
        assert "My Desc" in messages
        assert "kw1" in messages


# --- run_generation_pipeline (E2E with mocks) ---

class TestRunGenerationPipeline:
    @patch("pipeline.shutil.copy2")
    @patch("pipeline.generate_metadata", return_value=("Title", "Desc", ["kw"]))
    @patch("pipeline.generate_video", return_value="output.mp4")
    @patch("pipeline.combine_videos", return_value="/tmp/combined.mp4")
    @patch("pipeline.generate_subtitles", return_value="/tmp/subs.srt")
    @patch("pipeline.concatenate_audioclips")
    @patch("pipeline.AudioFileClip")
    @patch("pipeline.tts_generate")
    @patch("pipeline.save_video", return_value="/tmp/video.mp4")
    @patch("pipeline.search_for_stock_videos", return_value=["http://example.com/v.mp4"])
    @patch("pipeline.get_search_terms", return_value=["cat", "dog"])
    @patch("pipeline.generate_script", return_value="A cat sits. A dog runs.")
    def test_full_pipeline_no_upload_no_music(
        self,
        mock_script,
        mock_terms,
        mock_search,
        mock_save_vid,
        mock_tts,
        mock_audio_clip,
        mock_concat,
        mock_subs,
        mock_combine,
        mock_render,
        mock_metadata,
        mock_copy,
        tmp_path,
    ):
        import pipeline

        clip = MagicMock()
        clip.duration = 5.0
        mock_audio_clip.return_value = clip
        mock_concat.return_value = MagicMock(duration=10.0)

        data = {
            "videoSubject": "Funny cats",
            "aiModel": "llama3.1:8b",
            "customPrompt": "",
            "voice": "en_us_001",
            "paragraphNumber": 1,
            "threads": 2,
            "useMusic": False,
            "automateYoutubeUpload": False,
        }

        with (
            patch.object(pipeline, "TEMP_DIR", tmp_path),
            patch.object(pipeline, "PROJECT_ROOT", tmp_path),
        ):
            # Create the expected output file
            (tmp_path / "output.mp4").write_bytes(b"video")

            result = pipeline.run_generation_pipeline(
                data=data,
                is_cancelled=lambda: False,
                on_log=MagicMock(),
            )

        assert result == "output.mp4"
        mock_script.assert_called_once()
        mock_terms.assert_called_once()

    @patch("pipeline.generate_script", return_value="")
    def test_raises_on_empty_script(self, mock_script):
        from pipeline import run_generation_pipeline

        data = {
            "videoSubject": "test",
            "aiModel": "llama3.1:8b",
            "customPrompt": "",
            "voice": "en_us_001",
            "paragraphNumber": 1,
        }

        with pytest.raises(RuntimeError, match="Could not generate a script"):
            run_generation_pipeline(
                data=data,
                is_cancelled=lambda: False,
                on_log=MagicMock(),
            )

    @patch("pipeline.generate_script", return_value="test script")
    @patch("pipeline.get_search_terms", return_value=["term"])
    @patch("pipeline.search_for_stock_videos", return_value=[])
    def test_raises_on_no_videos(self, mock_search, mock_terms, mock_script):
        from pipeline import run_generation_pipeline

        data = {
            "videoSubject": "test",
            "aiModel": "llama3.1:8b",
            "customPrompt": "",
            "voice": "en_us_001",
            "paragraphNumber": 1,
        }

        with pytest.raises(RuntimeError, match="No videos found"):
            run_generation_pipeline(
                data=data,
                is_cancelled=lambda: False,
                on_log=MagicMock(),
            )

    @patch("pipeline.generate_script", return_value="test script")
    def test_cancellation_stops_pipeline(self, mock_script):
        from pipeline import PipelineCancelled, run_generation_pipeline

        data = {
            "videoSubject": "test",
            "aiModel": "llama3.1:8b",
            "customPrompt": "",
            "voice": "en_us_001",
            "paragraphNumber": 1,
        }

        with pytest.raises(PipelineCancelled):
            run_generation_pipeline(
                data=data,
                is_cancelled=lambda: True,  # Immediately cancelled
                on_log=MagicMock(),
            )
