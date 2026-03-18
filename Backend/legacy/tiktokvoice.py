import base64
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import requests
from playsound import playsound

from logstream import log

VOICES = [
    "en_us_ghostface",
    "en_us_chewbacca",
    "en_us_c3po",
    "en_us_stitch",
    "en_us_stormtrooper",
    "en_us_rocket",
    "en_au_001",
    "en_au_002",
    "en_uk_001",
    "en_uk_003",
    "en_us_001",
    "en_us_002",
    "en_us_006",
    "en_us_007",
    "en_us_009",
    "en_us_010",
    "fr_001",
    "fr_002",
    "de_001",
    "de_002",
    "es_002",
    "es_mx_002",
    "br_001",
    "br_003",
    "br_004",
    "br_005",
    "id_001",
    "jp_001",
    "jp_003",
    "jp_005",
    "jp_006",
    "kr_002",
    "kr_003",
    "kr_004",
    "en_female_f08_salut_damour",
    "en_male_m03_lobby",
    "en_female_f08_warmy_breeze",
    "en_male_m03_sunshine_soon",
    "en_male_narration",
    "en_male_funny",
    "en_female_emotional",
]

ENDPOINTS = [
    "https://tiktok-tts.weilnet.workers.dev/api/generation",
    "https://tiktoktts.com/api/tiktok-tts",
]
current_endpoint = 0
_endpoint_lock = threading.Lock()
TEXT_BYTE_LIMIT = 300


def split_string(string: str, chunk_size: int) -> List[str]:
    words = string.split()
    chunks = []
    current_chunk = ""

    for word in words:
        next_chunk = f"{current_chunk} {word}".strip()
        if len(next_chunk) <= chunk_size:
            current_chunk = next_chunk
            continue

        if current_chunk:
            chunks.append(current_chunk)
        current_chunk = word

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _endpoint_healthcheck_url(endpoint_url: str) -> str:
    return endpoint_url.split("/a")[0]


def get_api_response() -> requests.Response:
    endpoint_url = ENDPOINTS[current_endpoint]
    return requests.get(_endpoint_healthcheck_url(endpoint_url), timeout=10)


def _select_available_endpoint() -> bool:
    global current_endpoint

    with _endpoint_lock:
        if get_api_response().status_code == 200:
            log("[+] TikTok TTS Service available!", "success")
            return True

        current_endpoint = (current_endpoint + 1) % len(ENDPOINTS)
        if get_api_response().status_code == 200:
            log("[+] TTS Service available!", "success")
            return True

    log(
        "[-] TTS Service not available and probably temporarily rate limited, try again later...",
        "error",
    )
    return False


def save_audio_file(base64_data: str, filename: str = "output.mp3") -> None:
    audio_bytes = base64.b64decode(base64_data)
    with open(filename, "wb") as file:
        file.write(audio_bytes)


def generate_audio(text: str, voice: str) -> dict:
    response = requests.post(
        ENDPOINTS[current_endpoint],
        headers={"Content-Type": "application/json"},
        json={"text": text, "voice": voice},
        timeout=120,
    )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as err:
        raise RuntimeError(
            f"TikTok TTS returned non-JSON response ({len(response.content)} bytes)"
        ) from err


def _extract_base64_audio(data: dict) -> str:
    # Endpoint 0 (weilnet): {"success": true, "data": "<base64>"}
    # Endpoint 1 (tiktoktts): {"data": "data:audio/mpeg;base64,<base64>"}
    raw = data.get("data")
    if not raw:
        error_msg = data.get("error", data.get("message", str(data)))
        raise RuntimeError(f"TikTok TTS error: {error_msg}")
    if "," in raw:
        return raw.split(",", 1)[1]
    return raw


def _validate_request(text: str, voice: str) -> bool:
    if voice == "none":
        log("[-] Please specify a voice", "error")
        return False
    if voice not in VOICES:
        log("[-] Voice not available", "error")
        return False
    if not text:
        log("[-] Please specify a text", "error")
        return False
    return True


def _generate_single_audio(text: str, voice: str) -> str:
    return _extract_base64_audio(generate_audio(text, voice))


def _generate_chunked_audio(text: str, voice: str) -> str:
    text_parts = split_string(text, TEXT_BYTE_LIMIT - 1)
    audio_parts = [""] * len(text_parts)

    with ThreadPoolExecutor(max_workers=len(text_parts)) as executor:
        futures = {
            executor.submit(_generate_single_audio, part, voice): idx
            for idx, part in enumerate(text_parts)
        }
        for future in as_completed(futures):
            idx = futures[future]
            audio_parts[idx] = future.result()  # raises on error

    return "".join(audio_parts)


def tts(
    text: str,
    voice: str = "none",
    filename: str = "output.mp3",
    play_sound: bool = False,
) -> None:
    global current_endpoint

    if not _select_available_endpoint():
        return
    if not _validate_request(text, voice):
        return

    try:
        if len(text) < TEXT_BYTE_LIMIT:
            audio_base64_data = _generate_single_audio(text, voice)
        else:
            audio_base64_data = _generate_chunked_audio(text, voice)

        if audio_base64_data == "error":
            log("[-] This voice is unavailable right now", "error")
            return

        save_audio_file(audio_base64_data, filename)
        log(f"[+] Audio file saved successfully as '{filename}'", "success")
        if play_sound:
            playsound(filename)
    except Exception as err:
        log(f"[-] An error occurred during TTS: {err}", "error")
