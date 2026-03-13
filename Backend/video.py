import os
import uuid
from pathlib import Path
from typing import List

import assemblyai as aai
import requests
import srt_equalizer
from dotenv import load_dotenv
from logstream import log
from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.video.tools.subtitles import SubtitlesClip

from utils import ENV_FILE, FONTS_DIR, SUBTITLES_DIR, TEMP_DIR

load_dotenv(ENV_FILE)

ASSEMBLY_AI_API_KEY = os.getenv("ASSEMBLY_AI_API_KEY")
SUBTITLE_PROVIDER = os.getenv("SUBTITLE_PROVIDER", "whisper").strip().lower()
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "mlx-community/whisper-small-mlx")
FRAME_EPSILON = 1 / 120
DEFAULT_SUBTITLES_POSITION = "center,bottom"


def save_video(video_url: str, directory: str = str(TEMP_DIR)) -> str:
    """Save a remote video to disk and return the local path."""
    destination = Path(directory).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    video_path = destination / f"{uuid.uuid4()}.mp4"
    with open(video_path, "wb") as file:
        file.write(requests.get(video_url).content)

    return str(video_path)


def _subtitle_language_code(voice: str) -> str:
    language_mapping = {
        "br": "pt",
        "id": "en",
        "jp": "ja",
        "kr": "ko",
    }
    return language_mapping.get(voice, voice)


def __generate_subtitles_assemblyai(audio_path: str, voice: str) -> str:
    """Generate subtitles with AssemblyAI."""
    aai.settings.api_key = ASSEMBLY_AI_API_KEY
    config = aai.TranscriptionConfig(language_code=_subtitle_language_code(voice))
    config.speech_models = ["universal-2"]
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(audio_path)
    return transcript.export_subtitles_srt()


def _whisper_language_code(voice: str) -> str:
    language_mapping = {
        "en": "en",
        "zh": "zh",
        "ja": "ja",
        "ko": "ko",
        "fr": "fr",
        "de": "de",
        "es": "es",
        "pt": "pt",
        "ru": "ru",
    }
    return language_mapping.get(voice, "en")


def _whisper_words_to_srt_entries(words: List[dict], start_index: int) -> tuple[List[str], int]:
    entries = []
    chunk_words = []
    chunk_start = None
    entry_index = start_index

    for word in words:
        if chunk_start is None:
            chunk_start = word["start"]
        chunk_words.append(word["word"].strip())

        if len(chunk_words) < 4:
            continue

        entries.append(
            f"{entry_index}\n{_srt_time(chunk_start)} --> {_srt_time(word['end'])}\n{' '.join(chunk_words)}\n"
        )
        entry_index += 1
        chunk_words = []
        chunk_start = None

    if chunk_words and chunk_start is not None:
        entries.append(
            f"{entry_index}\n{_srt_time(chunk_start)} --> {_srt_time(words[-1]['end'])}\n{' '.join(chunk_words)}\n"
        )
        entry_index += 1

    return entries, entry_index


def __generate_subtitles_whisper(audio_path: str, voice: str) -> str:
    """Generate SRT subtitles using local mlx-whisper with word timestamps."""
    import mlx_whisper

    language = _whisper_language_code(voice)
    log(f"[+] Transcribing with Whisper ({WHISPER_MODEL})...", "info")

    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=WHISPER_MODEL,
        language=language,
        word_timestamps=True,
    )

    srt_entries = []
    next_index = 1
    for segment in result.get("segments", []):
        words = segment.get("words", [])
        if not words:
            srt_entries.append(
                f"{next_index}\n{_srt_time(segment['start'])} --> {_srt_time(segment['end'])}\n{segment['text'].strip()}\n"
            )
            next_index += 1
            continue

        word_entries, next_index = _whisper_words_to_srt_entries(words, next_index)
        srt_entries.extend(word_entries)

    return "\n".join(srt_entries)


def _srt_time(seconds: float) -> str:
    ms_total = int(round(seconds * 1000))
    hours, remainder = divmod(ms_total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def _parse_subtitles_position(subtitles_position: str | None) -> tuple[str, str]:
    raw_value = (subtitles_position or DEFAULT_SUBTITLES_POSITION).strip()
    if "," not in raw_value:
        raw_value = DEFAULT_SUBTITLES_POSITION

    horizontal, vertical = [part.strip().lower() for part in raw_value.split(",", 1)]

    if horizontal not in {"left", "center", "right"}:
        horizontal = "center"
    if vertical not in {"top", "center", "bottom"}:
        vertical = "bottom"

    return horizontal, vertical


def __generate_subtitles_locally(
    sentences: List[str],
    audio_clips: List[AudioFileClip],
) -> str:
    """Generate SRT subtitles from sentence and clip durations."""
    start_time = 0.0
    subtitles = []

    for index, (sentence, audio_clip) in enumerate(zip(sentences, audio_clips), start=1):
        end_time = start_time + audio_clip.duration
        subtitles.append(
            f"{index}\n{_srt_time(start_time)} --> {_srt_time(end_time)}\n{sentence}\n"
        )
        start_time = end_time

    return "\n".join(subtitles)


def _write_subtitles_file(subtitles: str) -> str:
    SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
    subtitles_path = SUBTITLES_DIR / f"{uuid.uuid4()}.srt"

    with open(subtitles_path, "w", encoding="utf-8") as file:
        file.write(subtitles)

    srt_equalizer.equalize_srt_file(str(subtitles_path), str(subtitles_path), 10)
    log("[+] Subtitles generated.", "success")
    return str(subtitles_path)


def generate_subtitles(
    audio_path: str,
    sentences: List[str],
    audio_clips: List[AudioFileClip],
    voice: str,
) -> str:
    """Generate subtitles and return the SRT path."""
    if SUBTITLE_PROVIDER == "whisper":
        log("[+] Creating subtitles using local Whisper", "info")
        subtitles = __generate_subtitles_whisper(audio_path, voice)
    elif ASSEMBLY_AI_API_KEY:
        log("[+] Creating subtitles using AssemblyAI", "info")
        subtitles = __generate_subtitles_assemblyai(audio_path, voice)
    else:
        log("[+] Creating subtitles locally", "info")
        subtitles = __generate_subtitles_locally(sentences, audio_clips)

    return _write_subtitles_file(subtitles)


def _trim_source_clip(
    clip: VideoFileClip,
    target_duration: float,
) -> VideoFileClip | None:
    max_safe_source_duration = clip.duration - FRAME_EPSILON
    if max_safe_source_duration <= 0:
        clip.close()
        return None

    final_duration = min(target_duration, max_safe_source_duration)
    if final_duration <= 0:
        clip.close()
        return None

    clip = clip.without_audio()
    if final_duration < clip.duration:
        clip = clip.subclipped(0, final_duration)
    return clip.with_fps(30)


def _crop_to_vertical_short(clip: VideoFileClip) -> VideoFileClip:
    if round((clip.w / clip.h), 4) < 0.5625:
        clip = clip.cropped(
            width=clip.w,
            height=round(clip.w / 0.5625),
            x_center=clip.w / 2,
            y_center=clip.h / 2,
        )
    else:
        clip = clip.cropped(
            width=round(0.5625 * clip.h),
            height=clip.h,
            x_center=clip.w / 2,
            y_center=clip.h / 2,
        )
    return clip.resized(new_size=(1080, 1920))


def _target_clip_duration(
    video_duration: float,
    clip_count: int,
    max_clip_duration: float,
    remaining_duration: float,
) -> float:
    required_duration = video_duration / clip_count
    return min(required_duration, max_clip_duration, remaining_duration)


def combine_videos(
    video_paths: List[str],
    max_duration: int,
    max_clip_duration: int,
    threads: int,
) -> str:
    """Combine stock videos into one vertical short."""
    if not video_paths:
        raise ValueError("No source videos were provided for concatenation.")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    combined_video_path = TEMP_DIR / f"{uuid.uuid4()}.mp4"
    max_duration = float(max_duration)
    max_clip_duration = float(max_clip_duration)
    required_duration = max_duration / len(video_paths)

    log("[+] Combining videos...", "info")
    log(f"[+] Each clip will be maximum {required_duration} seconds long.", "info")

    clips = []
    total_duration = 0.0

    while total_duration < (max_duration - FRAME_EPSILON):
        progressed = False
        for video_path in video_paths:
            remaining_duration = max_duration - total_duration
            if remaining_duration <= FRAME_EPSILON:
                break

            source_clip = VideoFileClip(video_path)
            clip_duration = _target_clip_duration(
                video_duration=max_duration,
                clip_count=len(video_paths),
                max_clip_duration=max_clip_duration,
                remaining_duration=remaining_duration,
            )
            trimmed_clip = _trim_source_clip(source_clip, clip_duration)
            if trimmed_clip is None:
                continue

            prepared_clip = _crop_to_vertical_short(trimmed_clip)
            clips.append(prepared_clip)
            total_duration += prepared_clip.duration
            progressed = True

        if not progressed:
            raise RuntimeError("Could not reach target duration from source videos.")

    if not clips:
        raise RuntimeError("No valid clips were produced for concatenation.")

    final_clip = concatenate_videoclips(clips, method="compose")
    final_clip = final_clip.with_fps(30).with_duration(max_duration)
    try:
        final_clip.write_videofile(
            str(combined_video_path),
            threads=threads,
            fps=30,
            codec="libx264",
            preset="medium",
            audio=False,
        )
    finally:
        final_clip.close()
        for clip in clips:
            clip.close()

    return str(combined_video_path)


def _text_clip_generator(font_path: str, font_size: int, text_color: str):
    def make_text_clip(text: str) -> TextClip:
        return TextClip(
            font=font_path,
            text=text,
            font_size=font_size,
            color=text_color,
            stroke_color="black",
            stroke_width=max(2, font_size // 20),
        )

    return make_text_clip


def _subtitle_vertical_position(video_height: int, vertical_alignment: str) -> int | str:
    if vertical_alignment == "top":
        return 80
    if vertical_alignment == "bottom":
        return int(video_height * 0.85)
    return vertical_alignment


def generate_video(
    combined_video_path: str,
    tts_path: str,
    subtitles_path: str,
    threads: int,
    subtitles_position: str | None,
    text_color: str,
    font_size: int = 100,
    custom_font: str = "",
) -> str:
    """Create the final video with subtitles and audio."""
    font_path = custom_font or str((FONTS_DIR / "bold_font.ttf").resolve())
    horizontal_alignment, vertical_alignment = _parse_subtitles_position(subtitles_position)

    make_text_clip = _text_clip_generator(font_path, font_size, text_color)
    subtitles = SubtitlesClip(subtitles_path, make_textclip=make_text_clip)
    base_video = VideoFileClip(str(combined_video_path))
    audio = AudioFileClip(tts_path)
    target_duration = min(base_video.duration, audio.duration)
    vertical_position = _subtitle_vertical_position(base_video.h, vertical_alignment)

    result = CompositeVideoClip(
        [
            base_video.subclipped(0, target_duration),
            subtitles.with_position((horizontal_alignment, vertical_position)).with_duration(
                target_duration
            ),
        ]
    )
    result = result.with_audio(audio.subclipped(0, target_duration)).with_duration(
        target_duration
    )

    output_name = f"{uuid.uuid4()}.mp4"
    output_path = TEMP_DIR / output_name
    try:
        result.write_videofile(
            str(output_path),
            threads=threads or 2,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
        )
    finally:
        result.close()
        subtitles.close()
        audio.close()
        base_video.close()

    return output_name
