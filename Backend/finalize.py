"""Finalize pipeline: crop 9:16 -> extract audio -> subtitles -> correction -> render."""

import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from moviepy import AudioFileClip, CompositeAudioClip, VideoFileClip, afx

from ffmpeg_utils import mux_video_audio, render_subtitled_video
from logstream import log
from utils import FINAL_DIR, OUTPUT_DIR, SUBTITLES_DIR, TEMP_DIR
from video import generate_subtitles

KOREAN_FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def _detect_face_center_x(video_path: str, num_samples: int = 10) -> float | None:
    """Sample frames, detect faces, and return the average face center."""
    import cv2

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    if total_frames <= 0 or width <= 0:
        cap.release()
        return None

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    face_positions = []
    step = max(1, total_frames // num_samples)
    for frame_index in range(0, total_frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        success, frame = cap.read()
        if not success:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
        )
        for face_x, _face_y, face_w, _face_h in faces:
            face_positions.append((face_x + face_w / 2) / width)

    cap.release()
    if not face_positions:
        return None
    return sum(face_positions) / len(face_positions)


def _get_video_dimensions(video_path: str) -> tuple[int, int]:
    """Return (width, height) for a video file."""
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    video_stream = next(
        (s for s in streams if s["codec_type"] == "video"), None
    )
    if video_stream is None:
        raise ValueError(f"No video stream found in: {video_path}")
    return int(video_stream["width"]), int(video_stream["height"])


def _crop_to_vertical(video_path: str) -> str:
    """Crop to 9:16, preferring the detected face position when available."""
    width, height = _get_video_dimensions(video_path)
    if width <= height:
        return video_path

    cropped_width = int(height * 9 / 16)
    face_center = _detect_face_center_x(video_path)
    if face_center is None:
        x_offset = (width - cropped_width) // 2
        log("[+] No face detected, using center crop", "info")
    else:
        x_offset = max(0, min(int(face_center * width - cropped_width / 2), width - cropped_width))
        log(f"[+] Face detected at {face_center:.0%} -> crop offset {x_offset}px", "info")

    output_path = str(TEMP_DIR / f"{uuid4()}_cropped.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vf",
            f"crop={cropped_width}:{height}:{x_offset}:0,scale=1080:1920",
            "-c:a",
            "copy",
            output_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _ensure_input_files(video_path: str, music_path: str) -> None:
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if music_path and not os.path.isfile(music_path):
        raise FileNotFoundError(f"Music file not found: {music_path}")


def _ensure_runtime_dirs() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_output_path(video_path: str, output_path: str) -> str:
    if output_path:
        return str(Path(output_path).resolve())
    return str((FINAL_DIR / f"{Path(video_path).stem}.mp4").resolve())


def _extract_audio_track(video_path: str) -> str:
    extracted_audio = str(TEMP_DIR / f"{uuid4()}.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            extracted_audio,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return extracted_audio


def _parse_srt_blocks(srt_content: str) -> list[dict]:
    """Parse SRT into list of {index, start, end, text} blocks."""
    import re

    blocks = []
    for block in re.split(r"\n\n+", srt_content.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        time_match = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[1])
        if not time_match:
            continue
        blocks.append({
            "index": lines[0],
            "start": time_match.group(1),
            "end": time_match.group(2),
            "text": "\n".join(lines[2:]),
        })
    return blocks


def _write_srt(blocks: list[dict], path: str) -> None:
    """Write SRT blocks back to file."""
    entries = []
    for i, b in enumerate(blocks, 1):
        entries.append(f"{i}\n{b['start']} --> {b['end']}\n{b['text']}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(entries) + "\n\n")


def _wrap_text(text: str, max_chars: int) -> str:
    """Wrap a line by inserting newlines so no line exceeds max_chars."""
    if len(text) <= max_chars:
        return text
    lines: list[str] = []
    while text:
        if len(text) <= max_chars:
            lines.append(text)
            break
        # Look for a natural break (Korean punctuation, comma, space)
        break_at = max_chars
        for i in range(max_chars, max(max_chars - 6, 0), -1):
            if text[i] in " ,，.。!！?？~":
                break_at = i + 1
                break
        lines.append(text[:break_at].rstrip())
        text = text[break_at:].lstrip()
    return "\n".join(lines)


def _srt_to_seconds(time_str: str) -> float:
    """Convert SRT time string (HH:MM:SS,mmm) to seconds."""
    h, m, rest = time_str.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _group_blocks_by_silence(blocks: list[dict], gap_threshold: float = 0.4) -> list[list[dict]]:
    """Group SRT blocks by detecting silence gaps between them."""
    if not blocks:
        return []
    groups: list[list[dict]] = [[blocks[0]]]
    for block in blocks[1:]:
        prev_end = _srt_to_seconds(groups[-1][-1]["end"])
        curr_start = _srt_to_seconds(block["start"])
        if curr_start - prev_end > gap_threshold:
            groups.append([block])
        else:
            groups[-1].append(block)
    return groups


def _replace_subtitle_text(subtitles_path: str, script: str, max_chars: int = 0) -> None:
    """Replace Whisper subtitle text with the original script lines, keeping timing."""
    if not script:
        return

    with open(subtitles_path, "r", encoding="utf-8") as f:
        srt_content = f.read()

    blocks = _parse_srt_blocks(srt_content)
    if not blocks:
        return

    lines = [line.strip() for line in script.split("\n") if line.strip()]
    if not lines:
        return

    def _maybe_wrap(text: str) -> str:
        return _wrap_text(text, max_chars) if max_chars > 0 else text

    # Group Whisper blocks by silence gaps → one group per utterance
    groups = _group_blocks_by_silence(blocks)

    if len(groups) == len(lines):
        # Perfect match: each silence-separated group maps to one script line
        result_blocks = []
        for group, line in zip(groups, lines):
            result_blocks.append({
                "index": group[0]["index"],
                "start": group[0]["start"],
                "end": group[-1]["end"],
                "text": _maybe_wrap(line),
            })
    elif len(groups) > len(lines):
        # More speech groups than script lines → merge groups by ratio
        ratio = len(groups) / len(lines)
        result_blocks = []
        for i, line in enumerate(lines):
            start_idx = int(i * ratio)
            end_idx = int((i + 1) * ratio)
            merged_start = groups[start_idx][0]["start"]
            merged_end = groups[min(end_idx, len(groups)) - 1][-1]["end"]
            result_blocks.append({
                "index": str(i + 1),
                "start": merged_start,
                "end": merged_end,
                "text": _maybe_wrap(line),
            })
    else:
        # More script lines than speech groups → distribute lines across groups by ratio
        ratio = len(lines) / len(groups)
        result_blocks = []
        for i, group in enumerate(groups):
            start_idx = int(i * ratio)
            end_idx = int((i + 1) * ratio)
            combined = "\n".join(lines[start_idx:end_idx])
            result_blocks.append({
                "index": group[0]["index"],
                "start": group[0]["start"],
                "end": group[-1]["end"],
                "text": _maybe_wrap(combined),
            })

    _write_srt(result_blocks, subtitles_path)
    log(
        f"[+] Subtitle text replaced: {len(lines)} lines, "
        f"{len(blocks)} whisper blocks → {len(groups)} speech groups → {len(result_blocks)} subs",
        "info",
    )


def _correct_subtitles_if_needed(subtitles_path: str, script: str, max_chars: int = 0) -> None:
    if not script:
        return

    # Use direct text replacement instead of LLM correction
    _replace_subtitle_text(subtitles_path, script, max_chars=max_chars)


def _loop_music_clip(music_path: str, duration: float, music_volume: float) -> AudioFileClip:
    music_clip = AudioFileClip(music_path)
    music_clip = music_clip.with_effects([afx.AudioLoop(duration=duration)])
    return music_clip.with_volume_scaled(music_volume).with_fps(44100)


def _mix_background_music(
    rendered_video_path: str,
    music_path: str,
    music_volume: float,
) -> str:
    rendered_video = VideoFileClip(rendered_video_path)
    mixed_audio = None
    music_clip = None
    mixed_path = str(TEMP_DIR / f"{uuid4()}_mixed.m4a")

    try:
        duration = rendered_video.duration
        music_clip = _loop_music_clip(music_path, duration, music_volume)
        mixed_audio = CompositeAudioClip([rendered_video.audio, music_clip]).with_duration(
            duration
        )
        mixed_audio.write_audiofile(
            mixed_path,
            fps=44100,
            codec="aac",
            bitrate="192k",
        )
    finally:
        rendered_video.close()
        if mixed_audio is not None:
            mixed_audio.close()
        if music_clip is not None:
            music_clip.close()

    return mixed_path


class UploadError(RuntimeError):
    """An explicitly requested upload could not be confirmed.

    The local final video is preserved at ``final_output``. When
    ``remote_outcome_unknown`` is True the upload request may have reached
    YouTube, so the operator must check the channel before retrying manually.
    """

    def __init__(self, message: str, final_output: str, remote_outcome_unknown: bool):
        super().__init__(message)
        self.final_output = final_output
        self.remote_outcome_unknown = remote_outcome_unknown


def _upload_failure(final_output: str, reason: str, remote_outcome_unknown: bool) -> UploadError:
    message = f"YouTube upload not confirmed: {reason}. Local final video preserved: {final_output}."
    if remote_outcome_unknown:
        message += (
            " The upload request may have been sent, so the remote outcome is unknown."
            " Check YouTube Studio for this video before retrying manually;"
            " no automatic retry was attempted."
        )
    else:
        message += " The upload was not dispatched; fix the cause and retry manually."
    return UploadError(message, final_output, remote_outcome_unknown)


def _confirmed_video_id(response) -> str:
    if not isinstance(response, Mapping):
        return ""
    video_id = response.get("id")
    if isinstance(video_id, str) and video_id.strip():
        return video_id.strip()
    return ""


def _maybe_upload(final_output: str, title: str, description: str, emit) -> str:
    """Upload once and return the confirmed video ID, or raise UploadError."""
    emit("[+] Uploading to YouTube...", "info")
    try:
        from youtube import upload_video
    except Exception as err:
        failure = _upload_failure(final_output, f"uploader unavailable ({err})", False)
        emit(f"[!] {failure}", "error")
        raise failure from err

    try:
        response = upload_video(
            video_path=final_output,
            title=title or Path(final_output).stem,
            description=description or "",
            category="22",
            keywords="",
            privacy_status="public",
        )
    except Exception as err:
        failure = _upload_failure(final_output, f"upload raised {type(err).__name__}: {err}", True)
        emit(f"[!] {failure}", "error")
        raise failure from err

    video_id = _confirmed_video_id(response)
    if not video_id:
        failure = _upload_failure(final_output, "response did not contain a video ID", True)
        emit(f"[!] {failure}", "error")
        raise failure

    emit(f"[+] Uploaded! Video ID: {video_id}", "success")
    return video_id


def run_finalize_pipeline(
    video_path: str,
    music_path: str = "",
    music_volume: float = 0.10,
    subs_position: str = "center,bottom",
    subs_color: str = "#FFFF00",
    font_size: int = 55,
    language: str = "ko",
    crop: bool = True,
    script: str = "",
    output_path: str = "",
    upload: bool = False,
    upload_title: str = "",
    upload_description: str = "",
    on_log=None,
) -> str:
    """Finalize a Veo video with subtitles, optional music, and optional upload.

    With ``upload=True`` this raises UploadError (carrying the preserved local
    output path) unless YouTube returns a response with a nonempty video ID.
    """

    def emit(message: str, level: str = "info") -> None:
        log(message, level)
        if on_log:
            on_log(message, level)

    _ensure_input_files(video_path, music_path)
    _ensure_runtime_dirs()

    final_output = _resolve_output_path(video_path, output_path)

    if crop:
        emit("[1/6] Cropping to 9:16...", "info")
        working_video = _crop_to_vertical(video_path)
    else:
        emit("[1/6] Skipping crop.", "info")
        working_video = video_path

    emit("[2/6] Extracting audio...", "info")
    extracted_audio = _extract_audio_track(working_video)

    emit("[3/6] Generating subtitles...", "info")
    subtitles_path = generate_subtitles(
        audio_path=extracted_audio,
        sentences=[],
        audio_clips=[],
        voice=language,
    )

    script = script.strip() if script else ""
    if script:
        emit("[4/6] Correcting subtitles...", "info")
        video_w, _ = _get_video_dimensions(working_video)
        max_chars = int(video_w * 0.85 / (font_size * 0.9)) if font_size > 0 else 0
        _correct_subtitles_if_needed(subtitles_path, script, max_chars=max_chars)
    else:
        emit("[4/6] No script provided, skipping correction.", "info")

    emit("[5/6] Burning subtitles...", "info")
    rendered_video_path = render_subtitled_video(
        working_video,
        extracted_audio,
        subtitles_path,
        subs_position,
        subs_color,
        font_size=font_size,
        custom_font=KOREAN_FONT,
    )

    if music_path:
        emit(f"[6/6] Mixing background music (vol={music_volume})...", "info")
        mixed_audio_path = ""
        try:
            mixed_audio_path = _mix_background_music(
                rendered_video_path,
                music_path,
                music_volume,
            )
            mux_video_audio(rendered_video_path, mixed_audio_path, final_output)
        except Exception as err:
            emit(f"[6/6] Music mix failed ({err}), using original audio.", "warning")
            mux_video_audio(rendered_video_path, working_video, final_output)
        finally:
            if mixed_audio_path and os.path.exists(mixed_audio_path):
                os.remove(mixed_audio_path)
    else:
        emit("[6/6] Restoring original audio...", "info")
        mux_video_audio(rendered_video_path, working_video, final_output)

    if upload:
        _maybe_upload(final_output, upload_title, upload_description, emit)

    emit(f"[+] Output: {final_output}", "success")
    return final_output
