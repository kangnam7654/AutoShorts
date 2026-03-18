from typing import List

import requests

from logstream import log


def _search_url(query: str, limit: int) -> str:
    return f"https://api.pexels.com/videos/search?query={query}&per_page={limit}"


def _video_resolution(video_file: dict) -> int:
    return int(video_file.get("width", 0)) * int(video_file.get("height", 0))


def _best_download_url(video_files: list[dict]) -> str:
    best_url = ""
    best_resolution = -1

    for video_file in video_files:
        link = str(video_file.get("link", ""))
        if ".com/video-files" not in link:
            continue

        resolution = _video_resolution(video_file)
        if resolution <= best_resolution:
            continue

        best_url = link
        best_resolution = resolution

    return best_url


def _matching_video_urls(videos: list[dict], min_duration: int) -> list[str]:
    urls = []
    for video in videos:
        if int(video.get("duration", 0)) < min_duration:
            continue

        best_url = _best_download_url(video.get("video_files", []))
        if best_url:
            urls.append(best_url)

    return urls


def search_for_stock_videos(
    query: str,
    api_key: str,
    it: int,
    min_dur: int,
) -> List[str]:
    """Search Pexels for stock videos and return the best download URLs."""
    headers = {"Authorization": api_key}
    response = requests.get(_search_url(query, it), headers=headers)

    try:
        payload = response.json()
        video_urls = _matching_video_urls(payload.get("videos", []), min_dur)
    except Exception as err:
        log("[-] No Videos found.", "error")
        log(str(err), "error")
        video_urls = []

    log(f'\t=> "{query}" found {len(video_urls)} Videos', "info")
    return video_urls
