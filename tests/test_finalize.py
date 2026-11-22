"""Tests for finalize.py — crop, face detection, pipeline orchestration."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from ffmpeg_utils import mux_video_audio
from finalize import (
    _detect_face_center_x,
    _get_video_dimensions,
    _crop_to_vertical,
    run_finalize_pipeline,
)


# --- _get_video_dimensions ---

class TestGetVideoDimensions:
    @patch("finalize.subprocess.run")
    def test_returns_width_height(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080},
                    {"codec_type": "audio"},
                ]
            })
        )
        w, h = _get_video_dimensions("/fake/video.mp4")
        assert (w, h) == (1920, 1080)

    @patch("finalize.subprocess.run")
    def test_skips_audio_streams(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=json.dumps({
                "streams": [
                    {"codec_type": "audio"},
                    {"codec_type": "video", "width": 1280, "height": 720},
                ]
            })
        )
        w, h = _get_video_dimensions("/fake/video.mp4")
        assert (w, h) == (1280, 720)


# --- _detect_face_center_x ---

class TestDetectFaceCenterX:
    @patch("cv2.CascadeClassifier")
    @patch("cv2.VideoCapture")
    def test_returns_none_when_no_frames(self, mock_cap_cls, mock_cc):
        cap = MagicMock()
        cap.get.side_effect = lambda prop: {3: 0, 7: 0}.get(prop, 0)  # width=0, count=0
        mock_cap_cls.return_value = cap

        result = _detect_face_center_x("/fake.mp4")
        assert result is None

    @patch("cv2.CascadeClassifier")
    @patch("cv2.VideoCapture")
    def test_returns_none_when_no_faces(self, mock_cap_cls, mock_cc):
        import numpy as np

        cap = MagicMock()
        cap.get.side_effect = lambda prop: {3: 1280, 7: 30}.get(prop, 0)
        cap.read.return_value = (True, np.zeros((720, 1280, 3), dtype=np.uint8))
        mock_cap_cls.return_value = cap

        cascade = MagicMock()
        cascade.detectMultiScale.return_value = []  # no faces
        mock_cc.return_value = cascade

        result = _detect_face_center_x("/fake.mp4", num_samples=1)
        assert result is None

    @patch("cv2.cvtColor")
    @patch("cv2.CascadeClassifier")
    @patch("cv2.VideoCapture")
    def test_returns_average_face_x(self, mock_cap_cls, mock_cc, mock_cvt):
        import numpy as np

        cap = MagicMock()
        cap.get.side_effect = lambda prop: {3: 1000, 7: 10}.get(prop, 0)  # width=1000, 10 frames
        cap.read.return_value = (True, np.zeros((500, 1000, 3), dtype=np.uint8))
        mock_cap_cls.return_value = cap

        mock_cvt.return_value = np.zeros((500, 1000), dtype=np.uint8)

        cascade = MagicMock()
        # Face at x=200, width=100 → center = 250/1000 = 0.25
        cascade.detectMultiScale.return_value = [(200, 100, 100, 100)]
        mock_cc.return_value = cascade

        result = _detect_face_center_x("/fake.mp4", num_samples=1)
        assert result == pytest.approx(0.25, abs=0.01)


# --- _crop_to_vertical ---

class TestCropToVertical:
    @patch("finalize._get_video_dimensions", return_value=(1080, 1920))
    def test_skips_already_vertical(self, mock_dims):
        result = _crop_to_vertical("/fake.mp4")
        assert result == "/fake.mp4"

    @patch("finalize.subprocess.run")
    @patch("finalize._detect_face_center_x", return_value=None)
    @patch("finalize._get_video_dimensions", return_value=(1280, 720))
    def test_center_crop_when_no_face(self, mock_dims, mock_face, mock_run, tmp_path):
        with patch("finalize.TEMP_DIR", tmp_path):
            result = _crop_to_vertical("/fake.mp4")

        # Should have called ffmpeg
        mock_run.assert_called_once()
        ffmpeg_args = mock_run.call_args[0][0]
        vf = ffmpeg_args[ffmpeg_args.index("-vf") + 1]
        # new_w = 720 * 9/16 = 405, x_offset = (1280-405)//2 = 437
        assert "crop=405:720:437:0" in vf

    @patch("finalize.subprocess.run")
    @patch("finalize._detect_face_center_x", return_value=0.75)
    @patch("finalize._get_video_dimensions", return_value=(1280, 720))
    def test_face_crop_shifts_offset(self, mock_dims, mock_face, mock_run, tmp_path):
        with patch("finalize.TEMP_DIR", tmp_path):
            _crop_to_vertical("/fake.mp4")

        ffmpeg_args = mock_run.call_args[0][0]
        vf = ffmpeg_args[ffmpeg_args.index("-vf") + 1]
        # face at 75% of 1280 = 960, new_w=405, x_offset = 960 - 202 = 758
        # clamped: min(758, 1280-405=875) = 758
        assert "crop=405:720:757:0" in vf


# --- _mux_video_audio ---

class TestMuxVideoAudio:
    @patch("ffmpeg_utils.subprocess.run")
    def test_calls_ffmpeg_with_correct_args(self, mock_run):
        mux_video_audio("/input.mp4", "/audio.m4a", "/output.mp4")

        args = mock_run.call_args[0][0]
        assert args[0] == "ffmpeg"
        assert "-shortest" in args
        assert "/input.mp4" in args
        assert "/audio.m4a" in args
        assert "/output.mp4" in args


# --- run_finalize_pipeline ---

class TestRunFinalizePipeline:
    def test_raises_on_missing_video(self):
        with pytest.raises(FileNotFoundError, match="Video not found"):
            run_finalize_pipeline(video_path="/nonexistent.mp4")

    def test_raises_on_missing_music(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        with pytest.raises(FileNotFoundError, match="Music file not found"):
            run_finalize_pipeline(
                video_path=str(video),
                music_path="/nonexistent.mp3",
            )

    @patch("finalize.mux_video_audio")
    @patch("finalize.render_subtitled_video", return_value="/fake/rendered.mp4")
    @patch("finalize.generate_subtitles", return_value="/fake/subs.srt")
    @patch("finalize.subprocess.run")
    @patch("finalize._crop_to_vertical", return_value="/fake/cropped.mp4")
    def test_full_pipeline_no_music(self, mock_crop, mock_ffmpeg, mock_subs, mock_render, mock_mux, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        with patch("finalize.TEMP_DIR", tmp_path):
            with patch("finalize.SUBTITLES_DIR", tmp_path):
                with patch("finalize.OUTPUT_DIR", tmp_path):
                    result = run_finalize_pipeline(
                        video_path=str(video),
                        crop=True,
                        output_path=str(tmp_path / "out.mp4"),
                    )

        mock_crop.assert_called_once()
        mock_subs.assert_called_once()
        mock_render.assert_called_once()
        mock_mux.assert_called_once()

    @patch("finalize.mux_video_audio")
    @patch("finalize.render_subtitled_video", return_value="/fake/rendered.mp4")
    @patch("finalize.generate_subtitles", return_value="/fake/subs.srt")
    @patch("finalize.subprocess.run")
    def test_no_crop_flag_skips_crop(self, mock_ffmpeg, mock_subs, mock_render, mock_mux, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        with patch("finalize.TEMP_DIR", tmp_path):
            with patch("finalize.SUBTITLES_DIR", tmp_path):
                with patch("finalize.OUTPUT_DIR", tmp_path):
                    run_finalize_pipeline(
                        video_path=str(video),
                        crop=False,
                        output_path=str(tmp_path / "out.mp4"),
                    )

        # Should NOT have called _crop_to_vertical (it's not patched, so if called it would fail)
        # Instead the working_video should be the original video path

    @patch("finalize.mux_video_audio")
    @patch("finalize.render_subtitled_video", return_value="/fake/rendered.mp4")
    @patch("finalize.subprocess.run")
    @patch("finalize.generate_subtitles")
    @patch("finalize._get_video_dimensions", return_value=(1080, 1920))
    def test_script_replacement_called_when_script_provided(self, mock_dims, mock_subs, mock_ffmpeg, mock_render, mock_mux, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        srt_file = tmp_path / "subs.srt"
        srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\ntest\n")
        mock_subs.return_value = str(srt_file)

        with patch("finalize.TEMP_DIR", tmp_path):
            with patch("finalize.SUBTITLES_DIR", tmp_path):
                with patch("finalize.OUTPUT_DIR", tmp_path):
                    run_finalize_pipeline(
                        video_path=str(video),
                        crop=False,
                        script="original text",
                        output_path=str(tmp_path / "out.mp4"),
                    )

        # Script text should replace the Whisper transcription
        replaced_srt = srt_file.read_text()
        assert "original text" in replaced_srt


# --- upload outcome ---

class TestMaybeUpload:
    def _call(self, path="/out/final.mp4"):
        from finalize import _maybe_upload

        logs = []
        result = _maybe_upload(path, "Title", "Desc", lambda m, lvl="info": logs.append((m, lvl)))
        return result, logs

    @patch("youtube.upload_video", return_value={"id": "abc123"})
    def test_success_returns_video_id(self, mock_upload):
        video_id, logs = self._call()

        assert video_id == "abc123"
        mock_upload.assert_called_once()
        kwargs = mock_upload.call_args[1]
        assert kwargs["video_path"] == "/out/final.mp4"
        assert kwargs["privacy_status"] == "public"
        assert ("[+] Uploaded! Video ID: abc123", "success") in logs

    @pytest.mark.parametrize(
        "response",
        [None, {}, {"id": ""}, {"id": "   "}, {"id": None}, {"id": 123}, "abc123", ["abc123"]],
    )
    def test_missing_or_invalid_id_raises_unknown_outcome(self, response):
        from finalize import UploadError

        with patch("youtube.upload_video", return_value=response) as mock_upload:
            with pytest.raises(UploadError) as excinfo:
                self._call()

        mock_upload.assert_called_once()
        err = excinfo.value
        assert err.final_output == "/out/final.mp4"
        assert err.remote_outcome_unknown is True
        assert "/out/final.mp4" in str(err)
        assert "unknown" in str(err)
        assert "Check YouTube" in str(err)

    def test_exception_raises_unknown_outcome_without_retry(self):
        from finalize import UploadError

        with patch("youtube.upload_video", side_effect=RuntimeError("connection reset")) as mock_upload:
            with pytest.raises(UploadError) as excinfo:
                self._call()

        assert mock_upload.call_count == 1
        err = excinfo.value
        assert err.remote_outcome_unknown is True
        assert "connection reset" in str(err)
        assert "/out/final.mp4" in str(err)
        assert "no automatic retry" in str(err)
        assert isinstance(err.__cause__, RuntimeError)


class TestRunFinalizePipelineUpload:
    def _run(self, tmp_path, upload_patch, logs):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")
        out = tmp_path / "final" / "out.mp4"
        out.parent.mkdir()

        def fake_mux(_video, _audio, output):
            Path(output).write_bytes(b"final-video")

        with patch("finalize.subprocess.run"), \
             patch("finalize.generate_subtitles", return_value=str(tmp_path / "subs.srt")), \
             patch("finalize.render_subtitled_video", return_value=str(tmp_path / "rendered.mp4")), \
             patch("finalize.mux_video_audio", side_effect=fake_mux), \
             patch("finalize.TEMP_DIR", tmp_path), \
             patch("finalize.SUBTITLES_DIR", tmp_path), \
             patch("finalize.FINAL_DIR", tmp_path / "final"), \
             upload_patch as mock_upload:
            result = run_finalize_pipeline(
                video_path=str(video),
                crop=False,
                output_path=str(out),
                upload=True,
                upload_title="T",
                on_log=lambda m, lvl: logs.append((m, lvl)),
            )
        return result, out, mock_upload

    def test_failed_upload_raises_and_preserves_local_video(self, tmp_path):
        from finalize import UploadError

        logs = []
        with pytest.raises(UploadError) as excinfo:
            self._run(tmp_path, patch("youtube.upload_video", side_effect=RuntimeError("boom")), logs)

        out = tmp_path / "final" / "out.mp4"
        assert out.read_bytes() == b"final-video"
        assert excinfo.value.final_output == str(out.resolve())
        assert str(out.resolve()) in str(excinfo.value)
        assert not any(m.startswith("[+] Output:") for m, _ in logs)

    def test_no_id_response_raises_and_preserves_local_video(self, tmp_path):
        from finalize import UploadError

        logs = []
        with pytest.raises(UploadError):
            self._run(tmp_path, patch("youtube.upload_video", return_value={"kind": "youtube#video"}), logs)

        assert (tmp_path / "final" / "out.mp4").read_bytes() == b"final-video"
        assert not any(m.startswith("[+] Output:") for m, _ in logs)

    def test_successful_upload_returns_output(self, tmp_path):
        logs = []
        result, out, mock_upload = self._run(
            tmp_path, patch("youtube.upload_video", return_value={"id": "vid42"}), logs
        )

        assert result == str(out.resolve())
        mock_upload.assert_called_once()
        assert ("[+] Uploaded! Video ID: vid42", "success") in logs
        assert (f"[+] Output: {result}", "success") in logs

    def test_upload_not_called_by_default(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"fake")

        with patch("finalize.subprocess.run"), \
             patch("finalize.generate_subtitles", return_value=str(tmp_path / "subs.srt")), \
             patch("finalize.render_subtitled_video", return_value=str(tmp_path / "rendered.mp4")), \
             patch("finalize.mux_video_audio"), \
             patch("finalize.TEMP_DIR", tmp_path), \
             patch("finalize.SUBTITLES_DIR", tmp_path), \
             patch("finalize.FINAL_DIR", tmp_path), \
             patch("youtube.upload_video") as mock_upload:
            run_finalize_pipeline(
                video_path=str(video),
                crop=False,
                output_path=str(tmp_path / "out.mp4"),
            )

        mock_upload.assert_not_called()
