"""Compose pipeline: overlay TTS narration and subtitles onto an existing video."""

import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    VideoFileClip,
    afx,
    concatenate_audioclips,
)

from ffmpeg_utils import render_subtitled_video
from logstream import log
from tts_utils import split_sentences, tts_extension, tts_generate, voice_language_prefix
from utils import OUTPUT_DIR, SUBTITLES_DIR, TEMP_DIR
from video import generate_subtitles

DEFAULT_VOICE = "Ryan"
DEFAULT_SUBTITLES_POSITION = "center,center"
DEFAULT_SUBTITLES_COLOR = "#FFFF00"


def _render_tts_audio(sentences: list[str], voice: str) -> tuple[str, list[AudioFileClip]]:
    audio_clips = []
    for sentence in sentences:
        clip_path = str(TEMP_DIR / f"{uuid4()}{tts_extension()}")
        tts_generate(sentence, voice, filename=clip_path)
        audio_clips.append(AudioFileClip(clip_path))

    final_audio = concatenate_audioclips(audio_clips)
    tts_path = str(TEMP_DIR / f"{uuid4()}.mp3")
    try:
        final_audio.write_audiofile(tts_path)
    finally:
        final_audio.close()

    return tts_path, audio_clips


def _close_audio_clips(audio_clips: list[AudioFileClip]) -> None:
    for clip in audio_clips:
        clip.close()


def _mix_original_audio(rendered_video_path: str, original_video_path: str, output_path: str) -> bool:
    original_video = VideoFileClip(original_video_path)
    rendered_video = None
    original_audio = None
    mixed_audio = None
    mixed_audio_path = str(TEMP_DIR / f"{uuid4()}_mixed.m4a")

    try:
        if original_video.audio is None:
            return False

        rendered_video = VideoFileClip(rendered_video_path)
        duration = rendered_video.duration
        original_audio = (
            original_video.audio.with_effects([afx.AudioLoop(duration=duration)])
            .with_volume_scaled(0.1)
            .with_fps(44100)
        )
        mixed_audio = CompositeAudioClip(
            [rendered_video.audio, original_audio]
        ).with_duration(duration)
        mixed_audio.write_audiofile(
            mixed_audio_path,
            fps=44100,
            codec="aac",
            bitrate="192k",
        )

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                rendered_video_path,
                "-i",
                mixed_audio_path,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    finally:
        original_video.close()
        if rendered_video is not None:
            rendered_video.close()
        if mixed_audio is not None:
            mixed_audio.close()
        if original_audio is not None:
            original_audio.close()
        if os.path.exists(mixed_audio_path):
            os.remove(mixed_audio_path)


def run_compose_pipeline(
    video_path: str,
    script: str,
    voice: str = DEFAULT_VOICE,
    keep_audio: bool = False,
    subs_position: str = DEFAULT_SUBTITLES_POSITION,
    subs_color: str = DEFAULT_SUBTITLES_COLOR,
    output_path: str = "output.mp4",
    on_log=None,
) -> str:
    def emit(message: str, level: str = "info") -> None:
        log(message, level)
        if on_log:
            on_log(message, level)

    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sentences = split_sentences(script)
    voice_prefix = voice_language_prefix(voice)

    emit("[1/4] Generating narration with TTS...", "info")
    tts_path, audio_clips = _render_tts_audio(sentences, voice)
    emit("[1/4] Narration generated!", "success")

    emit("[2/4] Generating subtitles with Whisper...", "info")
    subtitles_path = generate_subtitles(
        audio_path=tts_path,
        sentences=sentences,
        audio_clips=audio_clips,
        voice=voice_prefix,
    )
    _close_audio_clips(audio_clips)
    emit("[2/4] Subtitles generated!", "success")

    emit("[3/4] Rendering video with subtitles...", "info")
    rendered_video_path = render_subtitled_video(
        video_path,
        tts_path,
        subtitles_path,
        subs_position,
        subs_color,
    )
    emit("[3/4] Video rendered!", "success")

    final_output = str(OUTPUT_DIR / Path(output_path).name)
    if keep_audio:
        emit("[4/4] Mixing original audio as background...", "info")
        try:
            mixed = _mix_original_audio(rendered_video_path, video_path, final_output)
            if mixed:
                emit("[4/4] Audio mixed!", "success")
            else:
                shutil.copy2(rendered_video_path, final_output)
                emit("[4/4] No original audio found, skipping mix.", "info")
        except Exception as err:
            emit(f"[4/4] Audio mix failed ({err}), using narration only.", "warning")
            shutil.copy2(rendered_video_path, final_output)
    else:
        shutil.copy2(rendered_video_path, final_output)
        emit("[4/4] Done (no audio mix).", "info")

    emit(f"[+] Output: {output_path}", "success")
    return output_path
