import os
import shutil
import subprocess
from uuid import uuid4

from apiclient.errors import HttpError
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    VideoFileClip,
    afx,
    concatenate_audioclips,
)

from gpt import generate_metadata, generate_script, get_search_terms
from logstream import log
from search import search_for_stock_videos
from tts_utils import default_voice, split_sentences, tts_extension, tts_generate, voice_language_prefix
from utils import BASE_DIR, PROJECT_ROOT, TEMP_DIR, choose_random_song
from video import combine_videos, generate_subtitles, generate_video, save_video
from youtube import upload_video

DEFAULT_SUBTITLES_POSITION = "center,bottom"
DEFAULT_TEXT_COLOR = "#FFFF00"
DEFAULT_STOCK_SEARCH_LIMIT = 15
DEFAULT_STOCK_MIN_DURATION = 10


class PipelineCancelled(Exception):
    pass


def _emit_generation_summary(data: dict, emit) -> None:
    emit("[Video to be generated]", "info")
    emit("   Subject: " + data["videoSubject"], "info")
    emit("   AI Model: " + str(data.get("aiModel")), "info")
    emit("   Custom Prompt: " + data.get("customPrompt", ""), "info")


def _resolve_voice(data: dict, emit) -> str:
    voice = data.get("voice", "")
    if voice:
        return voice

    voice = default_voice("generation")
    emit(f'[!] No voice selected. Defaulting to "{voice}"', "warning")
    return voice


def _collect_video_urls(search_terms: list[str], guard_cancelled) -> list[str]:
    video_urls = []
    for search_term in search_terms:
        guard_cancelled()
        found_urls = search_for_stock_videos(
            search_term,
            os.getenv("PEXELS_API_KEY"),
            DEFAULT_STOCK_SEARCH_LIMIT,
            DEFAULT_STOCK_MIN_DURATION,
        )
        for url in found_urls:
            if url not in video_urls:
                video_urls.append(url)
                break
    return video_urls


def _download_video_paths(video_urls: list[str], guard_cancelled, emit) -> list[str]:
    emit(f"[+] Downloading {len(video_urls)} videos...", "info")

    video_paths = []
    for video_url in video_urls:
        guard_cancelled()
        try:
            video_paths.append(save_video(video_url))
        except Exception:
            emit(f"[-] Could not download video: {video_url}", "error")

    emit("[+] Videos downloaded!", "success")
    return video_paths


def _render_tts_audio(
    sentences: list[str],
    voice: str,
    voice_prefix: str,
    guard_cancelled,
    emit,
) -> tuple[str, str]:
    audio_clips = []
    tts_path = str(TEMP_DIR / f"{uuid4()}.mp3")
    final_audio = None

    try:
        for sentence in sentences:
            guard_cancelled()
            segment_path = str(TEMP_DIR / f"{uuid4()}{tts_extension()}")
            tts_generate(sentence, voice, filename=segment_path)
            audio_clips.append(AudioFileClip(segment_path))

        final_audio = concatenate_audioclips(audio_clips)
        final_audio.write_audiofile(tts_path)

        try:
            subtitles_path = generate_subtitles(
                audio_path=tts_path,
                sentences=sentences,
                audio_clips=audio_clips,
                voice=voice_prefix,
            )
        except Exception as err:
            emit(f"[-] Error generating subtitles: {err}", "error")
            subtitles_path = ""
    finally:
        if final_audio is not None:
            final_audio.close()
        for audio_clip in audio_clips:
            audio_clip.close()

    if not subtitles_path:
        raise RuntimeError(
            "Could not generate subtitles. Check AssemblyAI key or local subtitle settings."
        )

    return tts_path, subtitles_path


def _render_final_video(
    combined_video_path: str,
    tts_path: str,
    subtitles_path: str,
    threads: int,
    subtitles_position: str,
    text_color: str,
) -> str:
    try:
        return generate_video(
            combined_video_path,
            tts_path,
            subtitles_path,
            threads or 2,
            subtitles_position,
            text_color or DEFAULT_TEXT_COLOR,
        )
    except Exception as err:
        raise RuntimeError(
            f"Could not render final video. Check subtitle/font/ImageMagick setup. ({err})"
        ) from err


def _emit_metadata(title: str, description: str, keywords: list[str], emit) -> None:
    emit("[-] Metadata for YouTube upload:", "info")
    emit("   Title:", "info")
    emit(f"   {title}", "info")
    emit("   Description:", "info")
    emit(f"   {description}", "info")
    emit("   Keywords:", "info")
    emit(f"  {', '.join(keywords)}", "info")


def _youtube_client_secret_path() -> str:
    return str((BASE_DIR / "client_secret.json").resolve())


def _upload_to_youtube(
    final_video_path: str,
    title: str,
    description: str,
    keywords: list[str],
    emit,
) -> None:
    client_secrets_file = _youtube_client_secret_path()
    if not os.path.exists(client_secrets_file):
        emit(
            "[-] Client secrets file missing. YouTube upload will be skipped.",
            "warning",
        )
        emit(
            "[-] Please download the client_secret.json from Google Cloud Platform and store this inside the /Backend directory.",
            "error",
        )
        return

    try:
        video_response = upload_video(
            video_path=str((TEMP_DIR / final_video_path).resolve()),
            title=title,
            description=description,
            category="28",
            keywords=",".join(keywords),
            privacy_status="private",
        )
        emit(f"Uploaded video ID: {video_response.get('id')}", "success")
    except HttpError as err:
        emit(f"An HTTP error {err.resp.status} occurred:\n{err.content}", "error")


def _looped_song_clip(song_path: str, duration: float) -> AudioFileClip:
    song_clip = AudioFileClip(song_path).with_fps(44100)
    song_clip = song_clip.with_effects([afx.AudioLoop(duration=duration)])
    return song_clip.with_volume_scaled(0.1).with_fps(44100)


def _write_mixed_audio(video_path: str, song_path: str, mixed_audio_path: str) -> None:
    video_clip = VideoFileClip(video_path)
    song_clip = None
    mixed_audio = None

    try:
        original_duration = video_clip.duration
        original_audio = video_clip.audio
        song_clip = _looped_song_clip(song_path, original_duration)
        mixed_audio = CompositeAudioClip([original_audio, song_clip]).with_duration(
            original_duration
        )
        mixed_audio.write_audiofile(
            mixed_audio_path,
            fps=44100,
            codec="aac",
            bitrate="192k",
        )
    finally:
        video_clip.close()
        if mixed_audio is not None:
            mixed_audio.close()
        if song_clip is not None:
            song_clip.close()


def _remux_with_ffmpeg(
    rendered_video_path: str,
    mixed_audio_path: str,
    final_output_path: str,
) -> None:
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
            final_output_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _render_music_fallback(
    rendered_video_path: str,
    song_path: str,
    final_output_path: str,
    render_threads: int,
) -> None:
    video_clip = VideoFileClip(rendered_video_path)
    song_clip = None
    comp_audio = None

    try:
        original_duration = video_clip.duration
        original_audio = video_clip.audio
        song_clip = _looped_song_clip(song_path, original_duration)
        comp_audio = CompositeAudioClip([original_audio, song_clip]).with_duration(
            original_duration
        )
        video_clip = video_clip.with_audio(comp_audio).with_fps(30).with_duration(
            original_duration
        )
        video_clip.write_videofile(
            final_output_path,
            threads=render_threads,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
        )
    finally:
        video_clip.close()
        if comp_audio is not None:
            comp_audio.close()
        if song_clip is not None:
            song_clip.close()


def _apply_background_music(
    rendered_video_path: str,
    final_output_path: str,
    render_threads: int,
    emit,
) -> bool:
    song_path = choose_random_song()
    if not song_path:
        emit(
            "[-] Could not find songs in Songs/. Continuing without background music.",
            "warning",
        )
        return False

    mixed_audio_path = str(TEMP_DIR / f"{uuid4()}_mixed_audio.m4a")
    try:
        _write_mixed_audio(rendered_video_path, song_path, mixed_audio_path)
        try:
            _remux_with_ffmpeg(rendered_video_path, mixed_audio_path, final_output_path)
        except Exception:
            emit(
                "[!] ffmpeg remux failed. Falling back to MoviePy render for music mix.",
                "warning",
            )
            _render_music_fallback(
                rendered_video_path,
                song_path,
                final_output_path,
                render_threads,
            )
    finally:
        if os.path.exists(mixed_audio_path):
            os.remove(mixed_audio_path)

    return True


def _cleanup_ffmpeg_processes() -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/f", "/im", "ffmpeg.exe"],
            check=False,
            capture_output=True,
            text=True,
        )
        return

    if shutil.which("pkill"):
        subprocess.run(
            ["pkill", "-f", "ffmpeg"],
            check=False,
            capture_output=True,
            text=True,
        )


def run_generation_pipeline(
    data: dict,
    is_cancelled,
    on_log,
    amount_of_stock_videos: int = 5,
) -> str:
    def emit(message: str, level: str = "info") -> None:
        log(message, level)
        if on_log:
            on_log(message, level)

    def guard_cancelled() -> None:
        if is_cancelled and is_cancelled():
            raise PipelineCancelled("Video generation was cancelled.")

    paragraph_number = int(data.get("paragraphNumber", 1))
    ai_model = data.get("aiModel")
    n_threads = data.get("threads")
    subtitles_position = data.get("subtitlesPosition") or DEFAULT_SUBTITLES_POSITION
    text_color = data.get("color") or DEFAULT_TEXT_COLOR
    use_music = data.get("useMusic", False)
    automate_youtube_upload = data.get("automateYoutubeUpload", False)

    _emit_generation_summary(data, emit)
    guard_cancelled()

    voice = _resolve_voice(data, emit)
    voice_prefix = voice_language_prefix(voice)

    script = generate_script(
        data["videoSubject"],
        paragraph_number,
        ai_model,
        voice,
        data["customPrompt"],
    )
    if not script:
        raise RuntimeError("Could not generate a script. Try a different model or prompt.")

    search_terms = get_search_terms(
        data["videoSubject"],
        amount_of_stock_videos,
        script,
        ai_model,
    )
    video_urls = _collect_video_urls(search_terms, guard_cancelled)
    if not video_urls:
        raise RuntimeError("No videos found to download.")

    video_paths = _download_video_paths(video_urls, guard_cancelled, emit)
    emit("[+] Script generated!", "success")
    guard_cancelled()

    sentences = split_sentences(script)
    tts_path, subtitles_path = _render_tts_audio(
        sentences,
        voice,
        voice_prefix,
        guard_cancelled,
        emit,
    )

    temp_audio = AudioFileClip(tts_path)
    try:
        combined_video_path = combine_videos(
            video_paths,
            temp_audio.duration,
            5,
            n_threads or 2,
        )
    finally:
        temp_audio.close()

    final_video_path = _render_final_video(
        combined_video_path,
        tts_path,
        subtitles_path,
        n_threads or 2,
        subtitles_position,
        text_color,
    )

    title, description, keywords = generate_metadata(
        data["videoSubject"],
        script,
        ai_model,
    )
    _emit_metadata(title, description, keywords, emit)

    if automate_youtube_upload:
        _upload_to_youtube(final_video_path, title, description, keywords, emit)

    final_output_path = str(PROJECT_ROOT / final_video_path)
    rendered_video_path = str(TEMP_DIR / final_video_path)
    render_threads = n_threads or (os.cpu_count() or 2)

    guard_cancelled()
    if use_music:
        use_music = _apply_background_music(
            rendered_video_path,
            final_output_path,
            render_threads,
            emit,
        )

    if not use_music:
        shutil.copy2(rendered_video_path, final_output_path)

    emit(f"[+] Video generated: {final_video_path}!", "success")
    _cleanup_ffmpeg_processes()
    return final_video_path
