"""Tests for search.py — Pexels response parsing and URL selection."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestSearchForStockVideos:
    @patch("search.requests.get")
    def test_returns_best_resolution_urls(self, mock_get):
        from search import search_for_stock_videos

        mock_get.return_value = MagicMock(
            json=lambda: {
                "videos": [
                    {
                        "duration": 12,
                        "video_files": [
                            {"link": "https://cdn.com/video-files/small.mp4", "width": 320, "height": 180},
                            {"link": "https://cdn.com/video-files/large.mp4", "width": 1920, "height": 1080},
                        ],
                    },
                    {
                        "duration": 5,
                        "video_files": [
                            {"link": "https://cdn.com/video-files/short.mp4", "width": 1280, "height": 720},
                        ],
                    },
                ]
            }
        )

        urls = search_for_stock_videos("fortune", "key", 5, 10)

        assert urls == ["https://cdn.com/video-files/large.mp4"]

    @patch("search.requests.get")
    def test_returns_empty_list_on_bad_payload(self, mock_get):
        from search import search_for_stock_videos

        mock_get.return_value = MagicMock(json=lambda: {"videos": None})

        urls = search_for_stock_videos("fortune", "key", 5, 10)

        assert urls == []

