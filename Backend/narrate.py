"""Narrate: overlay TTS narration onto a Veo video while keeping ambient audio."""

import os
from pathlib import Path
from uuid import uuid4

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    VideoFileClip,
    afx,
    concatenate_audioclips,
)

from ffmpeg_utils import mux_video_audio
from logstream import log
from tts_utils import default_voice, tts_generate
from utils import OUTPUT_DIR, TEMP_DIR


def _narration_sentences(script: str) -> list[str]:
    sentences = []
    for sentence in script.replace("\n", " ").split(". "):
        cleaned = sentence.strip()
        if not cleaned:
            continue
        if cleaned[-1] not in ".?!요다":
            cleaned += "."
        sentences.append(cleaned)
    return sentences


def _render_narration_audio(
    sentences: list[str],
    voice: str,
    clone: bool,
    ref_audio: str,
    ref_text: str,
    language: str,
    emit,
) -> tuple[str, float]:
    audio_clips = []
    narration = None
    narration_path = str(TEMP_DIR / f"narration_{uuid4()}.mp3")

    try:
        for index, sentence in enumerate(sentences, start=1):
            clip_path = str(TEMP_DIR / f"narr_{uuid4()}.wav")
            emit(f"  TTS [{index}/{len(sentences)}]: {sentence[:50]}...", "info")
            tts_generate(
                sentence,
                voice,
                filename=clip_path,
                clone=clone,
                ref_audio=ref_audio,
                ref_text=ref_text,
                language=language,
            )
            audio_clips.append(AudioFileClip(clip_path))

        narration = concatenate_audioclips(audio_clips)
        narration.write_audiofile(narration_path)
        narration_duration = narration.duration
    finally:
        if narration is not None:
            narration.close()
        for clip in audio_clips:
            clip.close()

    return narration_path, narration_duration


def _mix_narration_with_ambient(
    video_path: str,
    narration_path: str,
    ambient_volume: float,
) -> str:
    video_clip = VideoFileClip(video_path)
    narration_audio = AudioFileClip(narration_path)
    ambient_audio = None
    mixed_audio = None
    mixed_path = str(TEMP_DIR / f"mixed_{uuid4()}.m4a")

    try:
        video_duration = video_clip.duration
        audio_layers = [narration_audio]

        if video_clip.audio is not None:
            ambient_audio = (
                video_clip.audio.with_effects([afx.AudioLoop(duration=video_duration)])
                .with_volume_scaled(ambient_volume)
                .with_fps(44100)
            )
            audio_layers.append(ambient_audio)

        mixed_audio = CompositeAudioClip(audio_layers).with_duration(video_duration)
        mixed_audio.write_audiofile(
            mixed_path,
            fps=44100,
            codec="aac",
            bitrate="192k",
        )
    finally:
        video_clip.close()
        narration_audio.close()
        if ambient_audio is not None:
            ambient_audio.close()
        if mixed_audio is not None:
            mixed_audio.close()

    return mixed_path


def add_narration(
    video_path: str,
    script: str,
    voice: str = "",
    ambient_volume: float = 0.15,
    clone: bool = False,
    ref_audio: str = "",
    ref_text: str = "",
    language: str = "ko",
    on_log=None,
) -> str:
    """Add TTS narration to a video and keep the original ambient sound."""

    def emit(message: str, level: str = "info") -> None:
        log(message, level)
        if on_log:
            on_log(message, level)

    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not voice and not clone:
        voice = default_voice("narration")

    sentences = _narration_sentences(script)
    mode_label = "voice-cloned" if clone else voice

    emit(f"[1/3] Generating Korean TTS narration ({mode_label})...", "info")
    narration_path, narration_duration = _render_narration_audio(
        sentences,
        voice,
        clone,
        ref_audio,
        ref_text,
        language,
        emit,
    )
    emit(f"[1/3] Narration generated ({narration_duration:.1f}s)", "success")

    emit("[2/3] Mixing narration with ambient audio...", "info")
    mixed_audio_path = _mix_narration_with_ambient(
        video_path,
        narration_path,
        ambient_volume,
    )
    emit("[2/3] Audio mixed!", "success")

    emit("[3/3] Muxing final video...", "info")
    narrated_dir = OUTPUT_DIR / "narrated"
    narrated_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(narrated_dir / f"{Path(video_path).stem}.mp4")
    try:
        mux_video_audio(video_path, mixed_audio_path, output_path)
    finally:
        if os.path.exists(narration_path):
            os.remove(narration_path)
        if os.path.exists(mixed_audio_path):
            os.remove(mixed_audio_path)

    emit(f"[3/3] Output: {output_path}", "success")
    return output_path
