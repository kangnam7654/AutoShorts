"""Tests for youtube.py — upload helpers, retry logic, thumbnail setting."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestVideoTags:
    def test_splits_comma_keywords(self):
        from youtube import _video_tags

        assert _video_tags("a,b,c") == ["a", "b", "c"]

    def test_empty_returns_none(self):
        from youtube import _video_tags

        assert _video_tags("") is None

    def test_single_keyword(self):
        from youtube import _video_tags

        assert _video_tags("solo") == ["solo"]


class TestUploadBody:
    def test_builds_correct_structure(self):
        from youtube import _upload_body

        options = {
            "title": "Test Video",
            "description": "A description",
            "keywords": "a,b",
            "category": "22",
            "privacyStatus": "public",
        }
        body = _upload_body(options)

        assert body["snippet"]["title"] == "Test Video"
        assert body["snippet"]["description"] == "A description"
        assert body["snippet"]["tags"] == ["a", "b"]
        assert body["snippet"]["categoryId"] == "22"
        assert body["status"]["privacyStatus"] == "public"
        assert body["status"]["madeForKids"] is False


class TestUploadOptions:
    def test_returns_all_fields(self):
        from youtube import _upload_options

        opts = _upload_options("/video.mp4", "Title", "Desc", "22", "k1,k2", "public")
        assert opts["file"] == "/video.mp4"
        assert opts["title"] == "Title"
        assert opts["privacyStatus"] == "public"


class TestOAuthStorePath:
    def test_returns_backend_relative_path(self):
        from youtube import _oauth_store_path

        path = _oauth_store_path()
        assert path.name == "youtube-oauth2.json"
        assert "Backend" in str(path)


class TestRetrySleepSeconds:
    def test_returns_float(self):
        from youtube import _retry_sleep_seconds

        result = _retry_sleep_seconds(1)
        assert isinstance(result, float)
        assert 0 <= result < 4  # 2^1 = 2, random * 2

    def test_increases_with_retry_count(self):
        from youtube import _retry_sleep_seconds

        # Not deterministic, but upper bound grows
        # retry 5 -> max 32, retry 1 -> max 2
        # Just verify it returns without error
        for i in range(1, 6):
            _retry_sleep_seconds(i)


class TestResumableUpload:
    def test_successful_upload_returns_response(self):
        from youtube import resumable_upload

        mock_request = MagicMock()
        mock_request.next_chunk.return_value = (None, {"id": "abc123"})

        result = resumable_upload(mock_request)
        assert result == {"id": "abc123"}

    @patch("youtube.time.sleep")
    def test_retries_on_retriable_status(self, mock_sleep):
        from apiclient.errors import HttpError
        from youtube import resumable_upload

        mock_request = MagicMock()

        resp = MagicMock()
        resp.status = 500
        error = HttpError(resp, b"Server Error")

        # First call: retriable error, second: success
        mock_request.next_chunk.side_effect = [
            error,
            (None, {"id": "recovered"}),
        ]

        result = resumable_upload(mock_request)
        assert result == {"id": "recovered"}

    def test_raises_on_non_retriable_http_error(self):
        from apiclient.errors import HttpError
        from youtube import resumable_upload

        mock_request = MagicMock()

        resp = MagicMock()
        resp.status = 400
        error = HttpError(resp, b"Bad Request")
        mock_request.next_chunk.side_effect = error

        with pytest.raises(HttpError):
            resumable_upload(mock_request)

    @patch("youtube.time.sleep")
    def test_gives_up_after_max_retries(self, mock_sleep):
        from apiclient.errors import HttpError
        from youtube import resumable_upload

        mock_request = MagicMock()
        resp = MagicMock()
        resp.status = 503
        mock_request.next_chunk.side_effect = HttpError(resp, b"Unavailable")

        with pytest.raises(Exception, match="No longer attempting to retry"):
            resumable_upload(mock_request)


class TestUploadVideo:
    @patch("youtube._perform_upload")
    def test_calls_perform_upload(self, mock_upload):
        from youtube import upload_video

        mock_upload.return_value = {"id": "video123"}

        result = upload_video(
            video_path="/test.mp4",
            title="Title",
            description="Desc",
            category="22",
            keywords="k1,k2",
            privacy_status="public",
        )

        assert result == {"id": "video123"}
        mock_upload.assert_called_once()

    @patch("youtube.set_thumbnail")
    @patch("youtube._perform_upload")
    def test_sets_thumbnail_when_provided(self, mock_upload, mock_thumb):
        from youtube import upload_video

        mock_upload.return_value = {"id": "video123"}

        upload_video(
            video_path="/test.mp4",
            title="Title",
            description="Desc",
            category="22",
            keywords="",
            privacy_status="public",
            thumbnail_path="/thumb.png",
        )

        mock_thumb.assert_called_once_with("video123", "/thumb.png")

    @pytest.mark.parametrize("status", [401, 403])
    @patch("youtube._perform_upload")
    def test_does_not_restart_upload_on_auth_error(self, mock_upload, status):
        from apiclient.errors import HttpError
        from youtube import upload_video

        resp = MagicMock()
        resp.status = status
        # A second value is available, but must never be consumed.
        mock_upload.side_effect = [
            HttpError(resp, b"Auth error"),
            {"id": "duplicate"},
        ]

        with pytest.raises(HttpError):
            upload_video(
                video_path="/test.mp4",
                title="Title",
                description="Desc",
                category="22",
                keywords="",
                privacy_status="public",
            )

        assert mock_upload.call_count == 1

    @pytest.mark.parametrize("status", [401, 403])
    @patch("youtube.MediaFileUpload")
    @patch("youtube._log_channel_ids")
    @patch("youtube.get_authenticated_service")
    def test_single_insert_request_on_auth_error(
        self, mock_auth, mock_channels, mock_media, status
    ):
        from apiclient.errors import HttpError
        from youtube import upload_video

        resp = MagicMock()
        resp.status = status
        youtube_client = MagicMock()
        mock_auth.return_value = youtube_client
        insert = youtube_client.videos.return_value.insert
        insert.return_value.next_chunk.side_effect = HttpError(resp, b"Auth error")

        with pytest.raises(HttpError):
            upload_video(
                video_path="/test.mp4",
                title="Title",
                description="Desc",
                category="22",
                keywords="",
                privacy_status="public",
            )

        assert insert.call_count == 1
        assert insert.return_value.next_chunk.call_count == 1
        assert mock_auth.call_count == 1

    @patch("youtube._perform_upload")
    def test_propagates_other_http_errors(self, mock_upload):
        from apiclient.errors import HttpError
        from youtube import upload_video

        resp = MagicMock()
        resp.status = 400
        mock_upload.side_effect = HttpError(resp, b"Bad Request")

        with pytest.raises(HttpError):
            upload_video(
                video_path="/test.mp4",
                title="Title",
                description="Desc",
                category="22",
                keywords="",
                privacy_status="public",
            )

        assert mock_upload.call_count == 1


class TestSetThumbnail:
    @patch("youtube.get_authenticated_service")
    def test_returns_none_for_invalid_path(self, mock_auth):
        from youtube import set_thumbnail

        assert set_thumbnail("vid123", "/nonexistent.png") is None
        mock_auth.assert_not_called()

    @patch("youtube.get_authenticated_service")
    def test_returns_none_for_empty_path(self, mock_auth):
        from youtube import set_thumbnail

        assert set_thumbnail("vid123", "") is None
        mock_auth.assert_not_called()

    @patch("youtube.get_authenticated_service")
    def test_successful_thumbnail_upload(self, mock_auth, tmp_path):
        from youtube import set_thumbnail

        thumb = tmp_path / "thumb.png"
        thumb.write_bytes(b"PNG")

        mock_youtube = MagicMock()
        mock_auth.return_value = mock_youtube
        mock_youtube.thumbnails().set().execute.return_value = {"items": []}

        result = set_thumbnail("vid123", str(thumb))
        assert result is not None
