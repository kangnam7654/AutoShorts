import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import httplib2
from apiclient.discovery import build
from apiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow

from logstream import log

httplib2.RETRIES = 1

MAX_RETRIES = 10
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError, httplib2.ServerNotFoundError)
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

BASE_DIR = Path(__file__).resolve().parent
CLIENT_SECRETS_FILE = str((BASE_DIR / "client_secret.json").resolve())

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtubepartner",
]
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

MISSING_CLIENT_SECRETS_MESSAGE = f"""
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

{os.path.abspath(os.path.join(os.path.dirname(__file__), CLIENT_SECRETS_FILE))}

with information from the API Console
https://console.cloud.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
"""

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")


def _oauth_store_path() -> Path:
    return BASE_DIR / "youtube-oauth2.json"


def _youtube_flow():
    return flow_from_clientsecrets(
        CLIENT_SECRETS_FILE,
        scope=SCOPES,
        message=MISSING_CLIENT_SECRETS_MESSAGE,
    )


def get_authenticated_service():
    """Return an authenticated YouTube API client."""
    flow = _youtube_flow()
    storage = Storage(str(_oauth_store_path()))
    credentials = storage.get()

    if credentials is None or credentials.invalid:
        flags = argparser.parse_args(args=["--auth_host_port", "8090", "8091"])
        credentials = run_flow(flow, storage, flags)

    return build(
        YOUTUBE_API_SERVICE_NAME,
        YOUTUBE_API_VERSION,
        http=credentials.authorize(httplib2.Http()),
    )


def _video_tags(keywords: str) -> list[str] | None:
    if not keywords:
        return None
    return keywords.split(",")


def _upload_body(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "snippet": {
            "title": options["title"],
            "description": options["description"],
            "tags": _video_tags(options["keywords"]),
            "categoryId": options["category"],
        },
        "status": {
            "privacyStatus": options["privacyStatus"],
            "madeForKids": False,
            "selfDeclaredMadeForKids": False,
        },
    }


def _insert_request(youtube: Any, options: dict[str, Any]):
    body = _upload_body(options)
    return youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(options["file"], chunksize=-1, resumable=True),
    )


def initialize_upload(youtube: Any, options: dict):
    """Start a resumable YouTube upload."""
    return resumable_upload(_insert_request(youtube, options))


def _retry_sleep_seconds(retry_count: int) -> float:
    return random.random() * (2**retry_count)


def resumable_upload(insert_request: MediaFileUpload):
    """Upload a file with exponential backoff for retriable failures."""
    response = None
    retry_count = 0

    while response is None:
        error_message = None
        try:
            log(" => Uploading file...", "info")
            _status, response = insert_request.next_chunk()
            if response and "id" in response:
                log(f"Video id '{response['id']}' was successfully uploaded.", "success")
                return response
        except HttpError as err:
            if err.resp.status not in RETRIABLE_STATUS_CODES:
                raise
            error_message = f"A retriable HTTP error {err.resp.status} occurred:\n{err.content}"
        except RETRIABLE_EXCEPTIONS as err:
            error_message = f"A retriable error occurred: {err}"

        if error_message is None:
            continue

        log(error_message, "error")
        retry_count += 1
        if retry_count > MAX_RETRIES:
            raise Exception("No longer attempting to retry.")

        sleep_seconds = _retry_sleep_seconds(retry_count)
        log(f" => Sleeping {sleep_seconds} seconds and then retrying...", "info")
        time.sleep(sleep_seconds)


def _log_channel_ids(youtube: Any) -> None:
    channels_response = youtube.channels().list(mine=True, part="id").execute()
    for channel in channels_response["items"]:
        log(f" => Channel ID: {channel['id']}", "info")


def _upload_options(
    video_path: str,
    title: str,
    description: str,
    category: str,
    keywords: str,
    privacy_status: str,
) -> dict[str, str]:
    return {
        "file": video_path,
        "title": title,
        "description": description,
        "category": category,
        "keywords": keywords,
        "privacyStatus": privacy_status,
    }


def _perform_upload(options: dict[str, str]):
    youtube = get_authenticated_service()
    _log_channel_ids(youtube)
    return initialize_upload(youtube, options)


def set_thumbnail(video_id: str, thumbnail_path: str) -> dict | None:
    """Upload a custom thumbnail for a video."""
    if not thumbnail_path or not Path(thumbnail_path).is_file():
        return None

    youtube = get_authenticated_service()
    try:
        response = youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
        ).execute()
        log(f"[+] Thumbnail set for video {video_id}", "success")
        return response
    except HttpError as err:
        log(f"[-] Thumbnail upload failed: {err.resp.status} {err.content}", "error")
        return None


def upload_video(
    video_path,
    title,
    description,
    category,
    keywords,
    privacy_status,
    thumbnail_path: str = "",
):
    options = _upload_options(
        video_path,
        title,
        description,
        category,
        keywords,
        privacy_status,
    )

    # Exactly one insert/upload session. Never start a fresh upload after an
    # error (including 401/403): the first attempt may already have created
    # the video, so a restart could publish a duplicate.
    try:
        response = _perform_upload(options)
    except HttpError as err:
        log(f"[-] An HTTP error {err.resp.status} occurred:\n{err.content}", "error")
        raise

    if response and thumbnail_path:
        video_id = response.get("id", "")
        if video_id:
            set_thumbnail(video_id, thumbnail_path)

    return response
