import logging
import os
import random
import shutil
import sys
from pathlib import Path
from typing import Optional

from termcolor import colored

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
TEMP_DIR = PROJECT_ROOT / "temp"
SUBTITLES_DIR = PROJECT_ROOT / "subtitles"
SONGS_DIR = PROJECT_ROOT / "Songs"
FONTS_DIR = PROJECT_ROOT / "fonts"
OUTPUT_DIR = PROJECT_ROOT / "output"
FINAL_DIR = OUTPUT_DIR / "final"
PROMPTS_DIR = OUTPUT_DIR / "prompts"
ENV_FILE = PROJECT_ROOT / ".env"

REQUIRED_ENV_VARS = ["PEXELS_API_KEY", "TIKTOK_SESSION_ID"]
IMAGEMAGICK_CANDIDATES = ["magick", "magick.exe", "convert", "convert.exe"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        logger.info(f"Removed directory: {path}")
        return

    path.unlink(missing_ok=True)
    logger.info(f"Removed file: {path}")


def clean_dir(path: str) -> None:
    """Remove every file and directory inside the target directory."""
    try:
        directory = Path(path).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")

        for entry in directory.iterdir():
            _remove_path(entry)

        logger.info(colored(f"Cleaned {directory} directory", "green"))
    except Exception as err:
        logger.error(f"Error occurred while cleaning directory {path}: {err}")


def _song_candidates() -> list[Path]:
    if not SONGS_DIR.exists():
        return []

    return [
        song
        for song in SONGS_DIR.iterdir()
        if song.is_file() and song.suffix.lower() == ".mp3"
    ]


def choose_random_song() -> Optional[str]:
    """Choose a random MP3 file from `Songs/`."""
    try:
        songs = _song_candidates()
        if not songs:
            return None

        selected_song = random.choice(songs)
        logger.info(colored(f"Chose song: {selected_song}", "green"))
        return str(selected_song)
    except Exception as err:
        logger.error(colored(f"Error occurred while choosing random song: {err}", "red"))
        return None


def _configured_imagemagick_binary() -> Optional[str]:
    configured_binary = os.getenv("IMAGEMAGICK_BINARY", "").strip().strip('"')
    if not configured_binary:
        return None

    expanded_path = Path(configured_binary).expanduser()
    if expanded_path.exists():
        return str(expanded_path.resolve())

    logger.warning(
        colored("Configured IMAGEMAGICK_BINARY was not found on disk.", "yellow")
    )
    return None


def resolve_imagemagick_binary() -> Optional[str]:
    """Resolve an ImageMagick executable path."""
    configured_binary = _configured_imagemagick_binary()
    if configured_binary:
        return configured_binary

    for candidate in IMAGEMAGICK_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    return None


def _missing_env_vars() -> list[str]:
    missing = []
    for env_var in REQUIRED_ENV_VARS:
        value = os.getenv(env_var)
        if value is None or value == "":
            missing.append(env_var)
    return missing


def _abort_with_env_error(message: str, hint: str = "") -> None:
    logger.error(colored(message, "red"))
    if hint:
        logger.error(colored(hint, "yellow"))
    sys.exit(1)


def check_env_vars() -> None:
    """Fail fast when required runtime configuration is missing."""
    try:
        missing_vars = _missing_env_vars()
        if missing_vars:
            _abort_with_env_error(
                f"The following environment variables are missing: {', '.join(missing_vars)}",
                "Please consult 'docs/configuration.md' for setup instructions.",
            )

        imagemagick_binary = resolve_imagemagick_binary()
        if not imagemagick_binary:
            _abort_with_env_error(
                "IMAGEMAGICK_BINARY is not set and no ImageMagick executable was detected in PATH.",
                "Set IMAGEMAGICK_BINARY in .env or install ImageMagick and add it to PATH.",
            )

        os.environ["IMAGEMAGICK_BINARY"] = imagemagick_binary
    except SystemExit:
        raise
    except Exception as err:
        logger.error(f"Error occurred while checking environment variables: {err}")
        sys.exit(1)
