"""Integration tests: full pipeline flows with mocked external services.

Mocked boundaries:
- LLM (gpt.generate_response) — returns canned JSON/text
- Veo API (google.genai) — returns fake video objects
- ffmpeg/ffprobe (subprocess.run) — no-ops that create placeholder files
- Whisper (mlx_whisper) — returns fake transcription
- moviepy (VideoFileClip, TextClip, etc.) — lightweight mocks
- srt_equalizer — no-op
- YouTube upload — no-op

Everything between those boundaries runs for real:
  gpt.generate_veo_prompts → veo.generate_multi_part_video → finalize pipeline
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Backend"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def work_dirs(tmp_path):
    """Create isolated temp/subtitles/output directories."""
    temp = tmp_path / "temp"
    subs = tmp_path / "subtitles"
    output = tmp_path / "output"
    temp.mkdir()
    subs.mkdir()
    output.mkdir()
    return {"temp": temp, "subtitles": subs, "output": output}


@pytest.fixture
def fake_video(work_dirs):
    """Create a minimal placeholder video file."""
    video = work_dirs["output"] / "veo_test.mp4"
    video.write_bytes(b"\x00" * 1024)
    return str(video)


def _fake_subprocess_run(work_dirs):
    """Return a subprocess.run replacement that creates placeholder output files."""
    real_temp = work_dirs["temp"]

    def fake_run(cmd, **kwargs):
        # ffmpeg audio extraction: -vn ... output.wav
        if "ffmpeg" in cmd[0] and "-vn" in cmd:
            out = cmd[-1]
            Path(out).write_bytes(b"\x00" * 512)
            return MagicMock(returncode=0)

        # ffmpeg mux: -map 0:v:0 -map 1:a:0
        if "ffmpeg" in cmd[0] and "-map" in cmd:
            # output is the last arg
            out = cmd[-1]
            Path(out).write_bytes(b"\x00" * 512)
            return MagicMock(returncode=0)

        # ffmpeg crop
        if "ffmpeg" in cmd[0] and "crop=" in str(cmd):
            out = next(c for i, c in enumerate(cmd) if i > 0 and cmd[i - 1] != "-i" and c.endswith(".mp4"))
            Path(out).write_bytes(b"\x00" * 512)
            return MagicMock(returncode=0)

        # ffprobe
        if "ffprobe" in cmd[0]:
            return MagicMock(
                returncode=0,
                stdout=json.dumps({"streams": [{"codec_type": "video", "width": 1920, "height": 1080}]}),
            )

        return MagicMock(returncode=0)

    return fake_run


def _fake_whisper_transcribe(*args, **kwargs):
    """Return fake Whisper transcription result."""
    return {
        "segments": [
            {
                "start": 0.0,
                "end": 3.0,
                "text": "운명이 다가온다",
                "words": [
                    {"word": "운명이", "start": 0.0, "end": 1.0},
                    {"word": "다가온다", "start": 1.0, "end": 3.0},
                ],
            },
            {
                "start": 3.5,
                "end": 6.0,
                "text": "돈복이 열린다",
                "words": [
                    {"word": "돈복이", "start": 3.5, "end": 4.5},
                    {"word": "열린다", "start": 4.5, "end": 6.0},
                ],
            },
        ]
    }


# ---------------------------------------------------------------------------
# Veo mock helpers
# ---------------------------------------------------------------------------

def _make_veo_mock_client():
    """Create a mock google.genai client for Veo API."""
    mock_video_file = MagicMock()
    mock_video = MagicMock()
    mock_video.video = mock_video_file

    mock_operation = MagicMock()
    mock_operation.done = True
    mock_operation.error = None  # Must be explicit — MagicMock() is truthy
    mock_operation.response.generated_videos = [mock_video]

    mock_client = MagicMock()
    mock_client.models.generate_videos.return_value = mock_operation
    return mock_client, mock_video_file


# ---------------------------------------------------------------------------
# LLM response fixtures
# ---------------------------------------------------------------------------

VEO_PROMPTS_RESPONSE = json.dumps([
    {
        "prompt": "A mysterious fortune teller in a dark tent lit by candles. vertical 9:16 aspect ratio. no background music, dialogue and ambient sound only. Close-up on weathered hands spreading tarot cards. The fortune teller says in Korean: \"운명이 다가온다\"",
        "dialogue": "운명이 다가온다",
        "situation": "점술사가 타로 카드를 펼친다"
    },
    {
        "prompt": "Medium shot of the fortune teller revealing a golden card. vertical 9:16 aspect ratio. no background music, dialogue and ambient sound only. Dramatic candlelight flickers. The fortune teller says in Korean: \"돈복이 열린다\"",
        "dialogue": "돈복이 열린다",
        "situation": "황금 카드가 드러난다"
    },
    {
        "prompt": "Wide shot pulling back from the tent into a starry night. vertical 9:16 aspect ratio. no background music, dialogue and ambient sound only. The fortune teller whispers in Korean: \"다음 운명을 기다려라\"",
        "dialogue": "다음 운명을 기다려라",
        "situation": "텐트에서 빠져나가며 마무리"
    },
], ensure_ascii=False)

SUBTITLE_CORRECTION_RESPONSE = """1
00:00:00,000 --> 00:03:00,000
운명이 다가온다

2
00:03:500 --> 00:06:00,000
돈복이 열린다"""


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestVeoEndToEnd:
    """Test: subject → LLM prompts → Veo multi-part → finalize pipeline."""

    def test_full_pipeline_subject_to_final_video(self, work_dirs):
        """Subject input flows through LLM → Veo → finalize → output file."""
        import gpt
        import veo
        import finalize
        import video as video_mod
        import utils

        mock_client, mock_video_file = _make_veo_mock_client()

        # When save is called, create the file so finalize can find it
        output_video = work_dirs["output"] / "test_veo.mp4"

        def fake_save(path):
            Path(path).write_bytes(b"\x00" * 1024)
        mock_video_file.save.side_effect = fake_save

        # Track LLM calls
        llm_calls = []
        def fake_generate_response(prompt, model):
            llm_calls.append(prompt)
            if "Veo 3 prompt engineer" in prompt:
                return VEO_PROMPTS_RESPONSE
            if "subtitle proofreader" in prompt:
                return SUBTITLE_CORRECTION_RESPONSE
            return "fallback response"

        # Mock render_subtitled_video (ffmpeg_utils subtitle burn) to return a placeholder
        def fake_render_subtitled_video(video, audio, subs, pos="center,bottom", color="#FFFFFF", font_size=100, custom_font=""):
            out_path = work_dirs["temp"] / f"{uuid4()}.mp4"
            out_path.write_bytes(b"\x00" * 512)
            return str(out_path)

        # Mock mux_video_audio to create the output file
        def fake_mux(video_path, audio_path, output_path):
            Path(output_path).write_bytes(b"\x00" * 512)

        with (
            patch.object(gpt, "generate_response", side_effect=fake_generate_response),
            patch.object(veo, "_client", return_value=mock_client),
            patch.object(veo, "OUTPUT_DIR", work_dirs["output"]),
            patch.object(utils, "OUTPUT_DIR", work_dirs["output"]),
            patch.object(finalize, "TEMP_DIR", work_dirs["temp"]),
            patch.object(finalize, "SUBTITLES_DIR", work_dirs["subtitles"]),
            patch.object(finalize, "FINAL_DIR", work_dirs["output"] / "final"),
            patch.object(finalize, "OUTPUT_DIR", work_dirs["output"]),
            patch.object(finalize, "subprocess", MagicMock(run=_fake_subprocess_run(work_dirs))),
            patch.object(finalize, "generate_subtitles", return_value=str(work_dirs["subtitles"] / "test.srt")),
            patch.object(finalize, "render_subtitled_video", side_effect=fake_render_subtitled_video),
            patch.object(finalize, "mux_video_audio", side_effect=fake_mux),
        ):
            # Write a fake SRT for the correction step to read
            srt_path = work_dirs["subtitles"] / "test.srt"
            srt_path.write_text("1\n00:00:00,000 --> 00:03:000\nfake\n", encoding="utf-8")

            # Step 1: Generate prompts (real function, mocked LLM)
            parts = gpt.generate_veo_prompts("돈복 운세", "", num_parts=3)

            assert len(parts) == 3
            assert parts[0]["dialogue"] == "운명이 다가온다"

            # Step 2: Generate multi-part video (real function, mocked Veo API)
            video_path = veo.generate_multi_part_video(
                prompts=parts,
                output_path=str(output_video),
            )

            assert Path(video_path).exists()
            assert mock_client.models.generate_videos.call_count == 3

            # Step 3: Finalize (real function, mocked ffmpeg/whisper/moviepy)
            script = "\n".join(p["dialogue"] for p in parts)
            final = finalize.run_finalize_pipeline(
                video_path=video_path,
                crop=False,
                script=script,
                language="ko",
                font_size=55,
            )

            assert final.endswith(".mp4")

        # Verify LLM was called for prompt generation (subtitle correction now uses direct text replacement)
        assert any("Veo 3 prompt engineer" in c for c in llm_calls)

        # Verify archive was saved
        archive_path = work_dirs["output"] / "archive.json"
        assert archive_path.exists()
        archive = json.loads(archive_path.read_text())
        assert archive[0]["subject"] == "돈복 운세"

    def test_single_prompt_no_finalize(self, work_dirs):
        """Direct prompt mode with --no-finalize should only generate video."""
        import veo
        import utils

        mock_client, mock_video_file = _make_veo_mock_client()

        output_path = str(work_dirs["output"] / "single.mp4")

        def fake_save(path):
            Path(path).write_bytes(b"\x00" * 1024)
        mock_video_file.save.side_effect = fake_save

        with (
            patch.object(veo, "_client", return_value=mock_client),
            patch.object(veo, "OUTPUT_DIR", work_dirs["output"]),
        ):
            result = veo.generate_video(
                prompt="A wizard casting a spell",
                output_path=output_path,
            )

        assert result == output_path
        assert Path(result).exists()
        mock_client.models.generate_videos.call_count == 1

    def test_veo_extend_chain_passes_videos_correctly(self, work_dirs):
        """Each extension must receive the previous part's video object."""
        import veo

        videos = [MagicMock() for _ in range(3)]
        operations = []
        for v in videos:
            op = MagicMock()
            op.done = True
            op.error = None
            op.response.generated_videos = [v]
            operations.append(op)

        # Last video's file gets saved
        videos[-1].video = MagicMock()
        def fake_save(path):
            Path(path).write_bytes(b"\x00" * 512)
        videos[-1].video.save.side_effect = fake_save

        mock_client = MagicMock()
        mock_client.models.generate_videos.side_effect = operations

        prompts = [
            {"prompt": "Part 1 - hook"},
            {"prompt": "Part 2 - core"},
            {"prompt": "Part 3 - cta"},
        ]

        with (
            patch.object(veo, "_client", return_value=mock_client),
            patch.object(veo, "OUTPUT_DIR", work_dirs["output"]),
        ):
            veo.generate_multi_part_video(prompts=prompts)

        calls = mock_client.models.generate_videos.call_args_list

        # Call 0: initial, no video param
        assert "video" not in calls[0][1]

        # Call 1: extends from video 0
        assert calls[1][1]["video"] == videos[0].video

        # Call 2: extends from video 1
        assert calls[2][1]["video"] == videos[1].video

    def test_archive_prevents_duplicate_characters(self, work_dirs):
        """When archive has entries, LLM prompt includes them for dedup."""
        import gpt
        import utils

        # Pre-populate archive
        archive = [
            {
                "date": "2026-03-06",
                "subject": "돈복",
                "parts": [{"prompt": "wizard", "dialogue": "운명이다", "situation": "마법사"}],
            }
        ]
        archive_path = work_dirs["output"] / "archive.json"
        archive_path.write_text(json.dumps(archive, ensure_ascii=False))

        captured_prompt = {}
        def fake_response(prompt, model):
            captured_prompt["value"] = prompt
            return '[{"prompt":"x","dialogue":"y","situation":"z"}]'

        with (
            patch.object(gpt, "generate_response", side_effect=fake_response),
            patch.object(utils, "OUTPUT_DIR", work_dirs["output"]),
        ):
            gpt.generate_veo_prompts("돈복", "")

        assert "PREVIOUS VIDEOS" in captured_prompt["value"]
        assert "돈복" in captured_prompt["value"]
        assert "DIFFERENT" in captured_prompt["value"]

    def test_cli_veo_command_integration(self, work_dirs):
        """CLI `veo` subcommand wires everything together correctly."""
        import gpt
        import veo
        import finalize
        import video as video_mod
        import utils

        mock_client, mock_video_file = _make_veo_mock_client()

        def fake_save(path):
            Path(path).write_bytes(b"\x00" * 1024)
        mock_video_file.save.side_effect = fake_save

        def fake_generate_response(prompt, model):
            if "Veo 3 prompt engineer" in prompt:
                return VEO_PROMPTS_RESPONSE
            return "fallback"

        output_path = str(work_dirs["output"] / "cli_test.mp4")

        with (
            patch.object(gpt, "generate_response", side_effect=fake_generate_response),
            patch.object(veo, "_client", return_value=mock_client),
            patch.object(veo, "OUTPUT_DIR", work_dirs["output"]),
            patch.object(utils, "OUTPUT_DIR", work_dirs["output"]),
            patch("sys.argv", [
                "cli", "veo", "돈복 운세",
                "--no-finalize",
                "-o", output_path,
            ]),
        ):
            from cli import main
            try:
                main()
            except SystemExit:
                pass

        assert Path(output_path).exists()
        assert mock_client.models.generate_videos.call_count == 3
