"""Tests for finalize.py helper functions — SRT parsing, text wrapping, subtitle replacement."""

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from finalize import (
    _group_blocks_by_silence,
    _parse_srt_blocks,
    _srt_to_seconds,
    _wrap_text,
    _write_srt,
    _replace_subtitle_text,
)


class TestSrtToSeconds:
    def test_zero(self):
        assert _srt_to_seconds("00:00:00,000") == 0.0

    def test_simple(self):
        assert _srt_to_seconds("00:00:01,500") == 1.5

    def test_minutes_and_hours(self):
        assert _srt_to_seconds("01:02:03,456") == 3723.456


class TestParseSrtBlocks:
    def test_parses_basic_srt(self):
        srt = "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,500 --> 00:00:03,000\nWorld\n"
        blocks = _parse_srt_blocks(srt)
        assert len(blocks) == 2
        assert blocks[0]["text"] == "Hello"
        assert blocks[1]["start"] == "00:00:01,500"

    def test_empty_string(self):
        assert _parse_srt_blocks("") == []

    def test_skips_malformed_blocks(self):
        srt = "1\nnot a timestamp\nHello\n\n2\n00:00:00,000 --> 00:00:01,000\nGood\n"
        blocks = _parse_srt_blocks(srt)
        assert len(blocks) == 1
        assert blocks[0]["text"] == "Good"


class TestWriteSrt:
    def test_writes_correct_format(self, tmp_path):
        blocks = [
            {"start": "00:00:00,000", "end": "00:00:01,000", "text": "Hello"},
            {"start": "00:00:01,500", "end": "00:00:03,000", "text": "World"},
        ]
        path = str(tmp_path / "test.srt")
        _write_srt(blocks, path)

        content = Path(path).read_text()
        assert "1\n00:00:00,000 --> 00:00:01,000\nHello" in content
        assert "2\n00:00:01,500 --> 00:00:03,000\nWorld" in content


class TestWrapText:
    def test_short_text_unchanged(self):
        assert _wrap_text("Hello", 20) == "Hello"

    def test_long_text_wraps(self):
        result = _wrap_text("Hello world how are you doing today", 15)
        lines = result.split("\n")
        assert all(len(line) <= 16 for line in lines)  # +1 for boundary

    def test_korean_text(self):
        text = "재물운이 트이기 직전에 꼭 잃는 게 있어"
        result = _wrap_text(text, 12)
        lines = result.split("\n")
        assert len(lines) >= 2


class TestGroupBlocksBySilence:
    def test_single_block(self):
        blocks = [{"start": "00:00:00,000", "end": "00:00:01,000"}]
        groups = _group_blocks_by_silence(blocks)
        assert len(groups) == 1

    def test_groups_by_gap(self):
        blocks = [
            {"start": "00:00:00,000", "end": "00:00:01,000"},
            {"start": "00:00:01,100", "end": "00:00:02,000"},  # < 0.4s gap → same group
            {"start": "00:00:03,000", "end": "00:00:04,000"},  # > 0.4s gap → new group
        ]
        groups = _group_blocks_by_silence(blocks, gap_threshold=0.4)
        assert len(groups) == 2
        assert len(groups[0]) == 2
        assert len(groups[1]) == 1

    def test_empty_blocks(self):
        assert _group_blocks_by_silence([]) == []


class TestReplaceSubtitleText:
    def test_perfect_match_groups_and_lines(self, tmp_path):
        srt_path = str(tmp_path / "test.srt")
        Path(srt_path).write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nold1\n\n"
            "2\n00:00:02,000 --> 00:00:03,000\nold2\n\n"
        )

        _replace_subtitle_text(srt_path, "new line 1\nnew line 2")

        content = Path(srt_path).read_text()
        assert "new line 1" in content
        assert "new line 2" in content
        assert "old1" not in content

    def test_no_op_when_no_script(self, tmp_path):
        srt_path = str(tmp_path / "test.srt")
        original = "1\n00:00:00,000 --> 00:00:01,000\noriginal\n"
        Path(srt_path).write_text(original)

        _replace_subtitle_text(srt_path, "")

        assert Path(srt_path).read_text() == original

    def test_more_groups_than_lines(self, tmp_path):
        srt_path = str(tmp_path / "test.srt")
        Path(srt_path).write_text(
            "1\n00:00:00,000 --> 00:00:01,000\na\n\n"
            "2\n00:00:02,000 --> 00:00:03,000\nb\n\n"
            "3\n00:00:04,000 --> 00:00:05,000\nc\n\n"
            "4\n00:00:06,000 --> 00:00:07,000\nd\n\n"
        )

        _replace_subtitle_text(srt_path, "combined 1\ncombined 2")

        content = Path(srt_path).read_text()
        assert "combined 1" in content
        assert "combined 2" in content

    def test_wraps_text_with_max_chars(self, tmp_path):
        srt_path = str(tmp_path / "test.srt")
        Path(srt_path).write_text(
            "1\n00:00:00,000 --> 00:00:03,000\noriginal text here\n\n"
        )

        _replace_subtitle_text(srt_path, "이것은 아주 긴 한국어 대사입니다 줄바꿈이 필요합니다", max_chars=10)

        content = Path(srt_path).read_text()
        assert "\n" in content.split("-->")[1]  # wrapped text has newlines
