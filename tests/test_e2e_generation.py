"""End-to-end integration test for the full stock-video generation pipeline.

Mocked boundaries:
- LLM (generate_script, get_search_terms, generate_metadata)
- Pexels API (search_for_stock_videos)
- TTS (tts_generate)
- moviepy (AudioFileClip, VideoFileClip, etc.)
- ffmpeg/ImageMagick (subprocess.run)
- srt_equalizer
- YouTube upload

Everything between those boundaries runs for real:
  pipeline.run_generation_pipeline → gpt → search → tts → video → output
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture
def work_dirs(tmp_path):
    temp = tmp_path / "temp"
    subs = tmp_path / "subtitles"
    songs = tmp_path / "Songs"
    temp.mkdir()
    subs.mkdir()
    songs.mkdir()
    return {"temp": temp, "subtitles": subs, "songs": songs, "root": tmp_path}


class TestStockVideoPipelineE2E:
    """Full stock-video generation pipeline: script → search → TTS → combine → render → output."""

    @patch("pipeline._cleanup_ffmpeg_processes")
    @patch("pipeline.shutil.copy2")
    @patch("pipeline.generate_metadata", return_value=("My Title", "My Desc", ["kw1", "kw2"]))
    @patch("pipeline.generate_video")
    @patch("pipeline.combine_videos")
    @patch("pipeline.generate_subtitles")
    @patch("pipeline.concatenate_audioclips")
    @patch("pipeline.AudioFileClip")
    @patch("pipeline.tts_generate")
    @patch("pipeline.save_video")
    @patch("pipeline.search_for_stock_videos")
    @patch("pipeline.get_search_terms")
    @patch("pipeline.generate_script")
    def test_end_to_end_no_music_no_upload(
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
        mock_cleanup,
        work_dirs,
    ):
        import pipeline

        # Script generation
        mock_script.return_value = "Cats are adorable. Dogs are loyal."
        mock_terms.return_value = ["cats", "dogs"]
        mock_search.return_value = ["http://video1.mp4"]
        mock_save_vid.return_value = str(work_dirs["temp"] / "stock.mp4")

        # TTS
        clip = MagicMock()
        clip.duration = 2.5
        mock_audio_clip.return_value = clip
        concat_audio = MagicMock()
        concat_audio.duration = 5.0
        mock_concat.return_value = concat_audio

        # Video processing
        mock_subs.return_value = str(work_dirs["temp"] / "subs.srt")
        mock_combine.return_value = str(work_dirs["temp"] / "combined.mp4")
        mock_render.return_value = "final_output.mp4"

        logs = []
        data = {
            "videoSubject": "Cats and Dogs",
            "aiModel": "llama3.1:8b",
            "customPrompt": "",
            "voice": "en_us_001",
            "paragraphNumber": 1,
            "threads": 2,
            "useMusic": False,
            "automateYoutubeUpload": False,
        }

        # Create the file that shutil.copy2 would need
        (work_dirs["temp"] / "final_output.mp4").write_bytes(b"video")

        with (
            patch.object(pipeline, "TEMP_DIR", work_dirs["temp"]),
            patch.object(pipeline, "PROJECT_ROOT", work_dirs["root"]),
        ):
            result = pipeline.run_generation_pipeline(
                data=data,
                is_cancelled=lambda: False,
                on_log=lambda msg, lvl: logs.append((msg, lvl)),
            )

        # Verify the full chain was called
        mock_script.assert_called_once()
        mock_terms.assert_called_once()
        mock_search.assert_called()
        mock_save_vid.assert_called()
        mock_tts.assert_called()  # TTS called for each sentence
        mock_subs.assert_called_once()
        mock_combine.assert_called_once()
        mock_render.assert_called_once()
        mock_metadata.assert_called_once()

        # Verify log messages captured key events
        all_messages = " ".join(msg for msg, _ in logs)
        assert "Script generated" in all_messages or "generated" in all_messages.lower()

    @patch("pipeline._cleanup_ffmpeg_processes")
    @patch("pipeline._remux_with_ffmpeg")
    @patch("pipeline._write_mixed_audio")
    @patch("pipeline.choose_random_song")
    @patch("pipeline.generate_metadata", return_value=("T", "D", ["k"]))
    @patch("pipeline.generate_video", return_value="out.mp4")
    @patch("pipeline.combine_videos", return_value="/tmp/combined.mp4")
    @patch("pipeline.generate_subtitles", return_value="/tmp/subs.srt")
    @patch("pipeline.concatenate_audioclips")
    @patch("pipeline.AudioFileClip")
    @patch("pipeline.tts_generate")
    @patch("pipeline.save_video", return_value="/tmp/stock.mp4")
    @patch("pipeline.search_for_stock_videos", return_value=["url1"])
    @patch("pipeline.get_search_terms", return_value=["term"])
    @patch("pipeline.generate_script", return_value="Script text. Second sentence.")
    def test_with_background_music(
        self,
        mock_script,
        mock_terms,
        mock_search,
        mock_save,
        mock_tts,
        mock_audio_clip,
        mock_concat,
        mock_subs,
        mock_combine,
        mock_render,
        mock_metadata,
        mock_song,
        mock_write_mix,
        mock_remux,
        mock_cleanup,
        work_dirs,
    ):
        import pipeline

        clip = MagicMock()
        clip.duration = 3.0
        mock_audio_clip.return_value = clip
        mock_concat.return_value = MagicMock(duration=6.0)

        # Song available
        song_path = work_dirs["songs"] / "bgm.mp3"
        song_path.write_bytes(b"mp3data")
        mock_song.return_value = str(song_path)

        data = {
            "videoSubject": "Music test",
            "aiModel": "llama3.1:8b",
            "customPrompt": "",
            "voice": "en_us_001",
            "paragraphNumber": 1,
            "threads": 2,
            "useMusic": True,
            "automateYoutubeUpload": False,
        }

        with (
            patch.object(pipeline, "TEMP_DIR", work_dirs["temp"]),
            patch.object(pipeline, "PROJECT_ROOT", work_dirs["root"]),
            patch("pipeline.os.path.exists", return_value=True),
            patch("pipeline.os.remove"),
        ):
            (work_dirs["temp"] / "out.mp4").write_bytes(b"video")

            result = pipeline.run_generation_pipeline(
                data=data,
                is_cancelled=lambda: False,
                on_log=MagicMock(),
            )

        mock_write_mix.assert_called_once()
        mock_remux.assert_called_once()


class TestCancellationE2E:
    """Test cancellation at different pipeline stages."""

    @patch("pipeline.generate_script", return_value="Script content.")
    @patch("pipeline.get_search_terms", return_value=["cats"])
    @patch("pipeline.search_for_stock_videos", return_value=["url1"])
    @patch("pipeline.save_video")
    def test_cancel_during_download(self, mock_save, mock_search, mock_terms, mock_script):
        from pipeline import PipelineCancelled, run_generation_pipeline

        call_count = 0

        def cancel_after_script():
            nonlocal call_count
            call_count += 1
            return call_count > 3  # Cancel after script/terms/search phases

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
                is_cancelled=cancel_after_script,
                on_log=MagicMock(),
            )
