"""Shared FFmpeg utilities: muxing, subtitle rendering."""

import shutil
import subprocess
from uuid import uuid4

from utils import FONTS_DIR, TEMP_DIR  # noqa: F401  FONTS_DIR re-exported for callers
from video import generate_video


def mux_video_audio(video_path: str, audio_path: str, output_path: str) -> None:
    """Mux the video stream from one file with audio from another file.

    Takes the video track from *video_path* and the audio track from
    *audio_path*, combines them, and writes the result to *output_path*.
    The output audio is re-encoded as AAC 192 kbps; the video stream is
    stream-copied without re-encoding.  The output is trimmed to the
    shorter of the two inputs (``-shortest``).
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-i",
            audio_path,
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


def render_subtitled_video(
    video_path: str,
    audio_path: str,
    subtitles_path: str,
    subs_position: str = "center,bottom",
    subs_color: str = "#FFFFFF",
    font_size: int = 100,
    custom_font: str = "",
) -> str:
    """Copy video to a temp file, burn subtitles, and return the rendered path.

    Parameters
    ----------
    video_path:
        Path to the source video file (will not be modified).
    audio_path:
        Path to the audio track that should accompany the rendered video.
    subtitles_path:
        Path to the ``.srt`` subtitle file to burn in.
    subs_position:
        Subtitle position expressed as ``"<horizontal>,<vertical>"``
        (e.g. ``"center,bottom"``).  Passed directly to
        :func:`video.generate_video`.
    subs_color:
        Subtitle text colour as a CSS hex string (e.g. ``"#FFFFFF"``).
    font_size:
        Font size in pixels for subtitle text.  Defaults to ``100``,
        matching :func:`video.generate_video`\'s own default.
    custom_font:
        Absolute path to a ``.ttf`` / ``.ttc`` font file.  When empty
        the default bold font from ``fonts/`` is used.

    Returns
    -------
    str
        Absolute path to the rendered video file inside ``TEMP_DIR``.
    """
    temp_video = str(TEMP_DIR / f"{uuid4()}.mp4")
    shutil.copy2(video_path, temp_video)

    rendered_name = generate_video(
        temp_video,
        audio_path,
        subtitles_path,
        2,
        subs_position,
        subs_color,
        font_size=font_size,
        custom_font=custom_font,
    )
    return str(TEMP_DIR / rendered_name)
