#!/usr/bin/env python3
"""AutoShorts CLI - Generate YouTube Shorts from the terminal."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from utils import ENV_FILE

load_dotenv(ENV_FILE)


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def log_handler(message: str, level: str) -> None:
    prefix = {
        "info": color("[INFO]", "34"),
        "success": color("[OK]", "32"),
        "warning": color("[WARN]", "33"),
        "error": color("[ERR]", "31"),
    }.get(level, "[???]")
    print(f"{prefix} {message}")


# ---------------------------------------------------------------------------
# Commands — each handler is self-contained, readable top to bottom
# ---------------------------------------------------------------------------

def do_auth() -> None:
    from legacy.codex_auth import login

    print(color("Signing in with your ChatGPT account...", "1;36"))
    try:
        login()
        print(color("Done! You can now use AI_PROVIDER=codex", "1;32"))
    except Exception as e:
        print(color(f"Auth failed: {e}", "1;31"))
        sys.exit(1)


def list_models() -> None:
    from gpt import list_models as _list_models

    models, default = _list_models()
    provider = os.getenv("AI_PROVIDER", "ollama")
    print(f"Provider: {provider}")
    print("Available models:")
    for m in models:
        marker = " (default)" if m == default else ""
        print(f"  - {m}{marker}")


def list_voices() -> None:
    tts_provider = os.getenv("TTS_PROVIDER", "qwen").strip().lower()
    if tts_provider == "qwen":
        from legacy.qwen_tts import VOICES
    else:
        from legacy.tiktokvoice import VOICES
    print(f"Provider: {tts_provider}")
    print("Available voices:")
    for v in VOICES:
        print(f"  - {v}")


def generate(args: argparse.Namespace) -> None:
    from legacy.pipeline import run_generation_pipeline

    print(color("\n=== AutoShorts CLI ===", "1;36"))
    print(f"  Subject: {args.subject}")
    print(f"  Model:   {args.model}")
    print(f"  Voice:   {args.voice}")
    print(f"  Upload:  {'Yes' if args.upload else 'No'}")
    print(f"  Music:   {'Yes' if args.music else 'No'}")
    print()

    try:
        result = run_generation_pipeline(
            data={
                "videoSubject": args.subject,
                "paragraphNumber": args.paragraphs,
                "aiModel": args.model,
                "threads": args.threads,
                "subtitlesPosition": args.subs_position,
                "color": args.subs_color,
                "useMusic": args.music,
                "automateYoutubeUpload": args.upload,
                "voice": args.voice,
                "customPrompt": args.prompt or "",
            },
            is_cancelled=lambda: False,
            on_log=log_handler,
            amount_of_stock_videos=args.videos,
        )
        print(color(f"\nDone! Output: {result}", "1;32"))
    except KeyboardInterrupt:
        print(color("\nCancelled.", "33"))
        sys.exit(1)
    except Exception as e:
        print(color(f"\nFailed: {e}", "1;31"))
        sys.exit(1)


def compose(args: argparse.Namespace) -> None:
    from compose import run_compose_pipeline

    script = args.script
    if not script and args.script_file:
        with open(args.script_file, "r", encoding="utf-8") as f:
            script = f.read()
    if not script:
        print(color("Error: --script or --script-file required.", "1;31"))
        sys.exit(1)

    print(color("\n=== AutoShorts Compose ===", "1;36"))
    print(f"  Video:      {args.video}")
    print(f"  Voice:      {args.voice}")
    print(f"  Keep audio: {'Yes' if args.keep_audio else 'No'}")
    print(f"  Output:     {args.output}")
    print(f"  Script:     {script[:80]}{'...' if len(script) > 80 else ''}")
    print()

    try:
        result = run_compose_pipeline(
            video_path=args.video,
            script=script,
            voice=args.voice,
            keep_audio=args.keep_audio,
            subs_position=args.subs_position,
            subs_color=args.subs_color,
            output_path=args.output,
            on_log=log_handler,
        )
        print(color(f"\nDone! Output: {result}", "1;32"))
    except KeyboardInterrupt:
        print(color("\nCancelled.", "33"))
        sys.exit(1)
    except Exception as e:
        print(color(f"\nFailed: {e}", "1;31"))
        sys.exit(1)


def veo(args: argparse.Namespace) -> None:
    """Full Veo pipeline: [LLM prompts →] Veo video → narration → finalize."""
    # Preflight: upload runs inside finalize, so --no-finalize would silently
    # drop a requested upload. Reject before any prompt generation or paid call.
    if getattr(args, "no_finalize", False) and getattr(args, "upload", False):
        print(color(
            "Error: --upload requires finalization; remove --no-finalize or --upload. "
            "Nothing was generated.",
            "1;31",
        ))
        sys.exit(2)

    print(color("\n=== AutoShorts Veo ===", "1;36"))

    try:
        # --- Step 1: Generate video ---
        generated_prompts = None
        prompt_file = getattr(args, "prompt_file", "")
        if prompt_file:
            # --prompt-file: JSON array of per-part prompts
            import json as _json

            from veo import generate_multi_part_video

            with open(prompt_file, "r", encoding="utf-8") as f:
                prompts = _json.load(f)

            print(f"  Prompt file: {prompt_file} ({len(prompts)} parts)")
            print(f"  Model:  {args.veo_model or '(default)'}")
            if args.image:
                print(f"  Image:  {args.image}")
            print()

            for i, p in enumerate(prompts, 1):
                print(f"    Part {i}: {p['prompt'][:60]}...")

            print(color(f"[1/2] Generating {len(prompts)}-part video (8s + {len(prompts) - 1}x7s)...", "34"))
            video_path = generate_multi_part_video(
                prompts=prompts,
                output_path=args.output,
                model=args.veo_model,
                image_path=args.image,
                on_log=log_handler,
            )
            generated_prompts = prompts
            # Extract dialogue from prompts for subtitle generation
            dialogue_lines = [p.get("dialogue", "") for p in prompts if p.get("dialogue")]
            script = "\n".join(dialogue_lines)
        elif args.subject and not args.prompt:
            from gpt import generate_veo_prompts
            from veo import generate_multi_part_video
            from workflow import extract_script

            print(f"  Subject: {args.subject}")
            print(f"  Parts:   {args.parts}")

            print(color("[1/3] Generating Veo prompts...", "34"))
            parts = generate_veo_prompts(args.subject, args.ai_model, num_parts=args.parts)

            for i, p in enumerate(parts, 1):
                print(f"    Part {i}: {p['prompt'][:60]}...")
                if p.get("dialogue"):
                    print(f"            dialogue: {p['dialogue']}")

            generated_prompts = parts
            script = extract_script(parts)

            print(color(f"[2/3] Generating {len(parts)}-part video...", "34"))
            print(f"  Model:  {args.veo_model or '(default)'}")
            print()

            video_path = generate_multi_part_video(
                prompts=parts,
                output_path=args.output,
                model=args.veo_model,
                image_path=args.image,
                on_log=log_handler,
            )
        else:
            print(f"  Prompt: {args.prompt[:80]}...")
            print(f"  Model:  {args.veo_model or '(default)'}")
            if args.image:
                print(f"  Image:  {args.image}")
            print(f"  Parts:  {args.parts}")
            print()

            if args.parts > 1:
                from veo import generate_multi_part_video

                prompts = [{"prompt": args.prompt}] * args.parts
                generated_prompts = prompts
                print(color(f"[1/2] Generating {args.parts}-part video (8s + {args.parts - 1}x7s)...", "34"))
                video_path = generate_multi_part_video(
                    prompts=prompts,
                    output_path=args.output,
                    model=args.veo_model,
                    image_path=args.image,
                    on_log=log_handler,
                )
            else:
                from veo import generate_video as veo_generate

                generated_prompts = [{"prompt": args.prompt}]
                print(color("[1/2] Generating video...", "34"))
                video_path = veo_generate(
                    prompt=args.prompt,
                    output_path=args.output,
                    resolution=args.resolution,
                    duration=args.duration,
                    model=args.veo_model,
                    image_path=args.image,
                    on_log=log_handler,
                )
            script = ""

        # --- Step 1.5: Save prompts to prompts/ directory ---
        if generated_prompts:
            import json as _json2

            from utils import PROMPTS_DIR

            PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
            prompts_stem = Path(video_path).stem
            prompts_path = PROMPTS_DIR / f"{prompts_stem}.json"
            with open(prompts_path, "w", encoding="utf-8") as f:
                _json2.dump(generated_prompts, f, ensure_ascii=False, indent=2)
            print(color(f"[+] Prompts saved: {prompts_path}", "32"))

        # --- Step 1.6: Auto-detect and clean broken Veo subtitles ---
        if getattr(args, "clean_subs", False):
            from veo import clean_veo_subtitles, detect_veo_subtitles

            print(color("[*] Scanning for broken Veo subtitles...", "34"))
            if detect_veo_subtitles(video_path):
                print(color("[!] Broken subtitles detected. Cleaning...", "33"))
                video_path = clean_veo_subtitles(video_path)
                print(color(f"[+] Cleaned: {video_path}", "32"))
            else:
                print(color("[+] No broken subtitles detected. Skipping.", "32"))

        # --- Step 2: Add narration (only with --add-narration) ---
        if script and args.add_narration:
            from narrate import add_narration

            print(color("\n--- Adding narration ---", "1;36"))
            video_path = add_narration(
                video_path=video_path,
                script=script,
                voice=args.voice,
                clone=args.clone,
                ref_audio=getattr(args, "clone_ref_audio", ""),
                ref_text=getattr(args, "clone_ref_text", ""),
                language=args.language,
                on_log=log_handler,
            )

        # --- Step 3: Finalize subtitles (optional) ---
        if not args.no_finalize:
            from finalize import run_finalize_pipeline

            print(color("\n--- Finalizing (subtitles) ---", "1;36"))
            video_path = run_finalize_pipeline(
                video_path=video_path,
                subs_position="center,bottom",
                subs_color="#FFFFFF",
                font_size=args.font_size,
                language=args.language,
                crop=False,
                script=script,
                upload=args.upload,
                upload_title=getattr(args, "upload_title", ""),
                upload_description=getattr(args, "upload_description", ""),
                on_log=log_handler,
            )

        print(color(f"\nDone! Output: {video_path}", "1;32"))
    except KeyboardInterrupt:
        print(color("\nCancelled.", "33"))
        sys.exit(1)
    except Exception as e:
        print(color(f"\nFailed: {e}", "1;31"))
        sys.exit(1)


def finalize(args: argparse.Namespace) -> None:
    from finalize import run_finalize_pipeline

    script = args.script
    if not script and args.script_file:
        with open(args.script_file, "r", encoding="utf-8") as f:
            script = f.read()

    print(color("\n=== AutoShorts Finalize ===", "1;36"))
    print(f"  Video:  {args.video}")
    print(f"  Music:  {args.music or '(none)'}")
    if args.music:
        print(f"  Volume: {args.music_volume}")
    print(f"  Script: {'Yes (LLM correction)' if script else 'No (Whisper only)'}")
    print(f"  Upload: {'Yes' if args.upload else 'No'}")
    print(f"  Output: {args.output}")
    print()

    try:
        result = run_finalize_pipeline(
            video_path=args.video,
            music_path=args.music or "",
            music_volume=args.music_volume,
            subs_position=args.subs_position,
            subs_color=args.subs_color,
            font_size=args.font_size,
            language=args.language,
            crop=not args.no_crop,
            script=script,
            output_path=args.output,
            upload=args.upload,
            upload_title=getattr(args, "upload_title", ""),
            upload_description=getattr(args, "upload_description", ""),
            on_log=log_handler,
        )
        print(color(f"\nDone! Output: {result}", "1;32"))
    except KeyboardInterrupt:
        print(color("\nCancelled.", "33"))
        sys.exit(1)
    except Exception as e:
        print(color(f"\nFailed: {e}", "1;31"))
        sys.exit(1)


# ---------------------------------------------------------------------------
# Parser + main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="moneyprinter",
        description="Generate YouTube Shorts from the terminal.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- generate ---
    gen = sub.add_parser("generate", aliases=["g"], help="Generate a video")
    gen.add_argument("subject", help="Video topic/subject")
    gen.add_argument("-m", "--model", default="", help="AI model (auto-detected from AI_PROVIDER)")
    gen.add_argument("-v", "--voice", default="", help="TTS voice (auto-detected from TTS_PROVIDER)")
    gen.add_argument("-p", "--paragraphs", type=int, default=1, help="Number of paragraphs (default: 1)")
    gen.add_argument("-t", "--threads", type=int, default=4, help="Render threads (default: 4)")
    gen.add_argument("-n", "--videos", type=int, default=5, help="Number of stock videos (default: 5)")
    gen.add_argument("--subs-position", default="center,center", help="Subtitle position (default: center,center)")
    gen.add_argument("--subs-color", default="#FFFF00", help="Subtitle color (default: #FFFF00)")
    gen.add_argument("--music", action="store_true", help="Add background music from Songs/")
    gen.add_argument("--upload", action="store_true", help="Auto-upload to YouTube")
    gen.add_argument("--prompt", default="", help="Custom prompt (overrides default)")

    # --- compose ---
    comp = sub.add_parser("compose", aliases=["c"], help="Add narration + subtitles to an existing video")
    comp.add_argument("--video", required=True, help="Path to input video file")
    comp.add_argument("--script", default="", help="Narration text")
    comp.add_argument("--script-file", default="", help="Path to narration text file")
    comp.add_argument("-v", "--voice", default="Ryan", help="TTS voice (default: Ryan)")
    comp.add_argument("--keep-audio", action="store_true", help="Keep original audio as background (10%%)")
    comp.add_argument("--subs-position", default="center,center", help="Subtitle position")
    comp.add_argument("--subs-color", default="#FFFF00", help="Subtitle color")
    comp.add_argument("-o", "--output", default="output.mp4", help="Output file path")

    # --- veo ---
    v = sub.add_parser("veo", aliases=["v"], help="Generate video with Veo API (end-to-end)")
    v.add_argument("subject", nargs="?", default="", help="Video topic (LLM generates script + Veo prompt)")
    v.add_argument("--prompt", default="", help="Direct Veo prompt (skip LLM script generation)")
    v.add_argument("--prompt-file", default="", help="JSON file with per-part prompts [{\"prompt\": \"...\"}]")
    v.add_argument("--ai-model", default="", help="LLM model for script generation")
    v.add_argument("--veo-model", default="", help="Veo model ID (default: env VEO_MODEL)")
    v.add_argument("--image", default="", help="Reference image path for image-to-video generation")
    v.add_argument("--resolution", default="720p", help="Resolution: 720p, 1080p, 4k (default: 720p)")
    v.add_argument("--parts", type=int, default=3, help="Number of 8-second parts (default: 3 = 24s)")
    v.add_argument("--duration", default="8", help="Duration per part: 4, 6, 8 (default: 8)")
    v.add_argument("--language", default="ko", help="Subtitle language (default: ko)")
    v.add_argument("--font-size", type=int, default=55, help="Subtitle font size (default: 55)")
    v.add_argument("--no-finalize", action="store_true", help="Skip subtitle/music finalization")
    v.add_argument("--clean-subs", action="store_true", help="Auto-detect and remove broken Veo subtitles")
    v.add_argument("--add-narration", action="store_true", help="Add TTS narration overlay (default: dialogue is in video)")
    v.add_argument("--clone", action="store_true", help="Use voice cloning instead of preset voice (with --add-narration)")
    v.add_argument("--clone-ref-audio", default="", help="Reference audio path for voice cloning")
    v.add_argument("--clone-ref-text", default="", help="Transcript of the reference audio")
    v.add_argument("-v", "--voice", default="", help="TTS voice (used with --add-narration)")
    v.add_argument("--upload", action="store_true", help="Auto-upload to YouTube")
    v.add_argument("--upload-title", default="", help="YouTube video title (default: filename)")
    v.add_argument("--upload-description", default="", help="YouTube video description")
    v.add_argument("-o", "--output", default="", help="Output file path")

    # --- finalize ---
    fin = sub.add_parser("finalize", aliases=["f"], help="Crop 9:16 + subtitles + music for a Veo video")
    fin.add_argument("--video", required=True, help="Path to Veo video (with dialogue audio)")
    fin.add_argument("--music", default="", help="Path to background music file (Gemini Lyria)")
    fin.add_argument("--music-volume", type=float, default=0.10, help="Background music volume 0.0-1.0 (default: 0.10)")
    fin.add_argument("--script", default="", help="Original script text (for LLM subtitle correction)")
    fin.add_argument("--script-file", default="", help="Path to original script file")
    fin.add_argument("--language", default="ko", help="Subtitle language (default: ko)")
    fin.add_argument("--font-size", type=int, default=55, help="Subtitle font size (default: 55)")
    fin.add_argument("--subs-position", default="center,bottom", help="Subtitle position (default: center,bottom)")
    fin.add_argument("--subs-color", default="#FFFF00", help="Subtitle color")
    fin.add_argument("--no-crop", action="store_true", help="Skip 9:16 crop (keep original aspect ratio)")
    fin.add_argument("--upload", action="store_true", help="Auto-upload to YouTube")
    fin.add_argument("--upload-title", default="", help="YouTube video title (default: filename)")
    fin.add_argument("--upload-description", default="", help="YouTube video description")
    fin.add_argument("-o", "--output", default="", help="Output file path")

    # --- simple commands ---
    sub.add_parser("auth", help="Sign in with ChatGPT account (for AI_PROVIDER=codex)")
    sub.add_parser("models", help="List available AI models")
    sub.add_parser("voices", help="List available TTS voices")

    args = parser.parse_args()

    if args.command in ("generate", "g"):
        generate(args)
    elif args.command in ("veo", "v"):
        if not args.subject and not args.prompt and not getattr(args, "prompt_file", ""):
            print(color("Error: subject, --prompt, or --prompt-file required.", "1;31"))
            sys.exit(1)
        veo(args)
    elif args.command in ("compose", "c"):
        compose(args)
    elif args.command in ("finalize", "f"):
        finalize(args)
    elif args.command == "auth":
        do_auth()
    elif args.command == "models":
        list_models()
    elif args.command == "voices":
        list_voices()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
