"""Extended tests for utils.py — env var checking, ImageMagick resolution."""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestMissingEnvVars:
    @patch.dict(os.environ, {"PEXELS_API_KEY": "key", "TIKTOK_SESSION_ID": "sid"})
    def test_no_missing(self):
        from utils import _missing_env_vars

        assert _missing_env_vars() == []

    @patch.dict(os.environ, {"PEXELS_API_KEY": ""}, clear=False)
    def test_empty_value_counts_as_missing(self):
        from utils import _missing_env_vars

        result = _missing_env_vars()
        assert "PEXELS_API_KEY" in result


class TestAbortWithEnvError:
    def test_exits_with_hint(self):
        from utils import _abort_with_env_error

        with pytest.raises(SystemExit):
            _abort_with_env_error("Error!", "Hint!")

    def test_exits_without_hint(self):
        from utils import _abort_with_env_error

        with pytest.raises(SystemExit):
            _abort_with_env_error("Error!")


class TestCheckEnvVars:
    @patch("utils._missing_env_vars", return_value=["PEXELS_API_KEY"])
    def test_exits_on_missing_vars(self, mock_missing):
        from utils import check_env_vars

        with pytest.raises(SystemExit):
            check_env_vars()

    @patch("utils.resolve_imagemagick_binary", return_value=None)
    @patch("utils._missing_env_vars", return_value=[])
    def test_exits_on_missing_imagemagick(self, mock_missing, mock_im):
        from utils import check_env_vars

        with pytest.raises(SystemExit):
            check_env_vars()

    @patch("utils.resolve_imagemagick_binary", return_value="/usr/local/bin/magick")
    @patch("utils._missing_env_vars", return_value=[])
    def test_success_sets_env(self, mock_missing, mock_im):
        from utils import check_env_vars

        check_env_vars()
        assert os.environ.get("IMAGEMAGICK_BINARY") == "/usr/local/bin/magick"


class TestConfiguredImagemagickBinary:
    @patch.dict(os.environ, {"IMAGEMAGICK_BINARY": ""})
    def test_empty_returns_none(self):
        from utils import _configured_imagemagick_binary

        assert _configured_imagemagick_binary() is None

    @patch.dict(os.environ, {"IMAGEMAGICK_BINARY": "/nonexistent/magick"})
    def test_nonexistent_path_returns_none(self):
        from utils import _configured_imagemagick_binary

        assert _configured_imagemagick_binary() is None

    def test_existing_path_returns_resolved(self, tmp_path):
        from utils import _configured_imagemagick_binary

        magick = tmp_path / "magick"
        magick.write_bytes(b"fake")

        with patch.dict(os.environ, {"IMAGEMAGICK_BINARY": str(magick)}):
            result = _configured_imagemagick_binary()
            assert result is not None


class TestLogstreamExtended:
    def test_queue_overflow_drops_oldest(self):
        from logstream import LogStream

        stream = LogStream(maxsize=2)
        stream.push("first")
        stream.push("second")
        stream.push("third")  # should drop "first"

        entries = []
        while True:
            try:
                entry = stream._queue.get_nowait()
                entries.append(entry)
            except Exception:
                break

        messages = [e["message"] for e in entries]
        assert "first" not in messages
        assert "third" in messages

    def test_clear_drains_queue(self):
        from logstream import LogStream

        stream = LogStream()
        stream.push("a")
        stream.push("b")
        stream.clear()

        assert stream._queue.empty()

    def test_keepalive_on_timeout(self):
        from logstream import LogStream

        stream = LogStream()
        gen = stream.stream(timeout=0.01)
        entry = next(gen)
        assert "keepalive" in entry
