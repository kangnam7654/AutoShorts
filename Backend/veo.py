"""Veo API client: generate and extend videos via Google GenAI SDK."""

import os
import shutil
import time
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from logstream import log
from utils import ENV_FILE, OUTPUT_DIR

load_dotenv(ENV_FILE)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-generate-preview")
VEO_ASPECT_RATIO = "9:16"
VEO_RESOLUTION = os.getenv("VEO_RESOLUTION", "720p")
POLL_INTERVAL = 10
MAX_WAIT_SECONDS = int(os.getenv("VEO_MAX_WAIT_SECONDS", "600"))

VEO_USE_VERTEX = os.getenv("VEO_USE_VERTEX", "").strip().lower() in ("1", "true", "yes")
VERTEX_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("GCLOUD_PROJECT", ""))
VERTEX_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
VEO_GCS_BUCKET = os.getenv("VEO_GCS_BUCKET", "moneyprinter-veo-output")


def _client():
    from google import genai

    if VEO_USE_VERTEX:
        if not VERTEX_PROJECT:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT is not set. Add it to .env for Vertex AI mode."
            )
        log(
            f"[Veo] Using Vertex AI (project={VERTEX_PROJECT}, location={VERTEX_LOCATION})",
            "info",
        )
        return genai.Client(
            vertexai=True,
            project=VERTEX_PROJECT,
            location=VERTEX_LOCATION,
        )

    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set. Add it to .env.")
    return genai.Client(api_key=GOOGLE_API_KEY)


def _emit(message: str, level: str = "info", on_log=None) -> None:
    log(message, level)
    if on_log:
        on_log(message, level)


def _raw_output_dir():
    raw_dir = OUTPUT_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def _slug_from_prompt(prompt: str) -> str:
    raw_slug = "".join(
        character
        for character in prompt[:40]
        if character.isalnum() or character in "-_ "
    ).strip()
    return raw_slug.replace(" ", "_") or "veo_output"


def _resolve_output_path(prompt: str, output_path: str) -> str:
    if output_path:
        return output_path
    return str(_raw_output_dir() / f"{_slug_from_prompt(prompt)}.mp4")


def _gcs_output_uri() -> str:
    return f"gs://{VEO_GCS_BUCKET}/veo/{uuid4()}.mp4"


def _download_from_gcs(gcs_uri: str, local_path: str) -> None:
    from google.cloud import storage

    bucket_name, _, blob_name = gcs_uri.replace("gs://", "").partition("/")
    client = storage.Client(project=VERTEX_PROJECT)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(local_path)


def _save_video(client, video_obj, output_path: str) -> None:
    """Save a generated video locally for both developer API and Vertex modes."""
    if VEO_USE_VERTEX:
        uri = getattr(video_obj, "uri", None) if video_obj else None
        if uri and uri.startswith("gs://"):
            _emit(f"[Veo] Downloading from GCS: {uri}")
            _download_from_gcs(uri, output_path)
            return

        video_obj.save(output_path)
        return

    client.files.download(file=video_obj)
    video_obj.save(output_path)


def _wait_for_operation(client, operation, on_log=None):
    """Poll an operation until it completes or times out."""
    elapsed = 0
    while not operation.done:
        if elapsed >= MAX_WAIT_SECONDS:
            raise TimeoutError(
                f"Veo operation did not complete within {MAX_WAIT_SECONDS}s."
            )
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        _emit(f"[Veo] Generating... ({elapsed}s elapsed)", on_log=on_log)
        operation = client.operations.get(operation)
    return operation


def _operation_error(operation):
    error = getattr(operation, "error", None)
    if error in (None, False):
        return None
    if hasattr(error, "code") or hasattr(error, "message"):
        return error
    if isinstance(error, str):
        return error
    return None


def _generated_videos(operation):
    response = getattr(operation, "response", None)
    if response is None:
        return []
    generated = getattr(response, "generated_videos", None)
    return generated or []


def _build_generate_config(types_module, *, resolution: str, duration: int | None = None):
    config_kwargs = {
        "resolution": resolution,
        "number_of_videos": 1,
        "aspect_ratio": VEO_ASPECT_RATIO,
    }
    if duration is not None:
        config_kwargs["duration_seconds"] = duration
    if VEO_USE_VERTEX:
        config_kwargs["output_gcs_uri"] = _gcs_output_uri()
    return types_module.GenerateVideosConfig(**config_kwargs)


def _validate_generation_result(operation, *, part_label: str, allow_partial: bool) -> bool:
    error = _operation_error(operation)
    if error:
        _emit(f"[Veo] {part_label} error: {error}", "warning")
        if not allow_partial:
            raise RuntimeError(f"Veo failed for {part_label}: {error}")
        return False

    generated = _generated_videos(operation)
    if generated:
        return True

    _emit(f"[Veo] {part_label} returned no videos.", "warning")
    if not allow_partial:
        raise RuntimeError(f"Veo returned no video for {part_label}.")
    return False


def detect_veo_subtitles(video_path: str, num_samples: int = 5) -> bool:
    """Detect broken Veo-rendered text using EasyOCR on sampled frames."""
    import cv2

    try:
        import easyocr
    except ImportError:
        _emit("[Veo] easyocr not installed, skipping subtitle detection.", "warning")
        return False

    reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
    cap = cv2.VideoCapture(video_path)
    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return False

        frames_with_text = 0
        for i in range(num_samples):
            frame_idx = int(total_frames * (i + 1) / (num_samples + 1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue
            results = reader.readtext(frame, paragraph=False)
            if any(conf > 0.3 for _, _, conf in results):
                frames_with_text += 1
    finally:
        cap.release()
    return frames_with_text >= 2


def clean_veo_subtitles(video_path: str, height: int = 200) -> str:
    """Remove broken Veo-rendered subtitles with a gradient fade to black."""
    input_path = Path(video_path)
    clean_path = input_path.with_stem(f"{input_path.stem}_clean")

    # Build gradient: stacked semi-transparent bands from transparent → opaque
    steps = 20
    step_h = height // steps
    bands = ",".join(
        f"drawbox=y=ih-{height - i * step_h}:w=iw:h={step_h}"
        f":color=black@{(i + 1) / steps:.2f}:t=fill"
        for i in range(steps)
    )

    from ffmpeg_utils import _run_ffmpeg

    _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", bands,
        "-c:a", "copy",
        str(clean_path),
    ])
    return str(clean_path)


def _load_reference_image(image_path: str):
    """Load a reference image for image-to-video generation."""
    from google.genai import types

    resolved = Path(image_path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Reference image not found: {resolved}")

    image_bytes = resolved.read_bytes()
    suffix = resolved.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(suffix, "image/png")

    return types.Image(image_bytes=image_bytes, mime_type=mime_type)


def generate_video(
    prompt: str,
    output_path: str = "",
    resolution: str = "",
    duration: str = "8",
    model: str = "",
    image_path: str = "",
    on_log=None,
) -> str:
    """Generate a single Veo video and return the saved file path."""
    from google.genai import types

    if not prompt.strip():
        raise ValueError("Prompt is required.")

    model_name = model or VEO_MODEL
    resolution_name = resolution or VEO_RESOLUTION
    resolved_output_path = _resolve_output_path(prompt, output_path)

    _emit(f"[Veo] Model: {model_name}", on_log=on_log)
    _emit(f"[Veo] Resolution: {resolution_name}, Duration: {duration}s", on_log=on_log)
    if image_path:
        _emit(f"[Veo] Reference image: {image_path}", on_log=on_log)
    _emit(
        f"[Veo] Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}",
        on_log=on_log,
    )
    _emit("[Veo] Submitting to Veo API...", on_log=on_log)

    client = _client()
    generate_kwargs = {
        "model": model_name,
        "prompt": prompt,
        "config": _build_generate_config(
            types,
            resolution=resolution_name,
            duration=int(float(duration)),
        ),
    }
    if image_path:
        generate_kwargs["image"] = _load_reference_image(image_path)

    operation = client.models.generate_videos(**generate_kwargs)

    operation = _wait_for_operation(client, operation, on_log)
    _validate_generation_result(operation, part_label="single video", allow_partial=False)

    final_video = _generated_videos(operation)[0]
    _save_video(client, final_video.video, resolved_output_path)
    _emit(f"[Veo] Video saved: {resolved_output_path}", "success", on_log=on_log)
    return resolved_output_path


def _create_initial_part(client, types_module, model_name: str, prompt: str, image=None):
    kwargs = {
        "model": model_name,
        "prompt": prompt,
        "config": _build_generate_config(types_module, resolution="720p", duration=8),
    }
    if image is not None:
        kwargs["image"] = image
    return client.models.generate_videos(**kwargs)


def _extend_part(client, types_module, model_name: str, previous_video, prompt: str):
    return client.models.generate_videos(
        model=model_name,
        video=previous_video,
        prompt=prompt,
        config=_build_generate_config(types_module, resolution="720p"),
    )


def generate_multi_part_video(
    prompts: list[dict],
    output_path: str = "",
    model: str = "",
    image_path: str = "",
    on_log=None,
) -> str:
    """Generate a multi-part video by creating part 1 and then extending it."""
    from google.genai import types

    if not prompts:
        raise ValueError("At least one Veo prompt is required.")

    model_name = model or VEO_MODEL
    first_prompt = str(prompts[0].get("prompt", "")).strip()
    if not first_prompt:
        raise ValueError("The first Veo prompt must not be empty.")

    resolved_output_path = _resolve_output_path(first_prompt, output_path)
    client = _client()
    current_video = None
    total_parts = len(prompts)

    # Load reference image for the first part only
    ref_image = _load_reference_image(image_path) if image_path else None

    # Build per-part output paths: base_part1.mp4, base_part2.mp4, ...
    base_stem = Path(resolved_output_path).stem
    parts_dir = _raw_output_dir()

    for index, part in enumerate(prompts, start=1):
        part_prompt = str(part.get("prompt", "")).strip()
        if not part_prompt:
            raise ValueError(f"Veo prompt for part {index} is empty.")

        _emit(
            f"[Veo] Part {index}/{total_parts}: {part_prompt[:80]}...",
            on_log=on_log,
        )

        if index == 1:
            _emit("[Veo] Creating initial video (8s)...", on_log=on_log)
            operation = _create_initial_part(client, types, model_name, part_prompt, image=ref_image)
        else:
            _emit("[Veo] Extending video (+7s)...", on_log=on_log)
            operation = _extend_part(client, types, model_name, current_video.video, part_prompt)

        operation = _wait_for_operation(client, operation, on_log)
        if not _validate_generation_result(
            operation,
            part_label=f"Part {index}",
            allow_partial=index > 1,
        ):
            _emit(
                f"[Veo] Extend failed at Part {index}. Saving {index - 1} part(s).",
                "warning",
                on_log=on_log,
            )
            break

        current_video = _generated_videos(operation)[0]
        expected_duration = 8 + (index - 1) * 7

        # Save each part separately
        part_path = str(parts_dir / f"{base_stem}_part{index}.mp4")
        _save_video(client, current_video.video, part_path)
        _emit(
            f"[Veo] Part {index} saved: {part_path} (~{expected_duration}s)",
            "success",
            on_log=on_log,
        )

    if current_video is None:
        raise RuntimeError("Veo did not produce a final video.")

    # Copy the last saved part as the final output (avoid re-downloading)
    last_part_path = str(parts_dir / f"{base_stem}_part{min(index, total_parts)}.mp4")
    if last_part_path != resolved_output_path:
        shutil.copy2(last_part_path, resolved_output_path)
    _emit(f"[Veo] Final video saved: {resolved_output_path}", "success", on_log=on_log)
    return resolved_output_path
