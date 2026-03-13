"""Tests for workflow.py — part normalization and script extraction."""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from workflow import normalize_part, normalize_parts, extract_script


class TestNormalizePart:
    def test_fills_missing_keys_with_empty_strings(self):
        result = normalize_part({"prompt": "test"}, 1)
        assert result["prompt"] == "test"
        assert result["dialogue"] == ""
        assert result["narration"] == ""
        assert result["situation"] == ""
        assert result["index"] == 1

    def test_narration_defaults_to_dialogue(self):
        result = normalize_part({"prompt": "p", "dialogue": "대사입니다"}, 1)
        assert result["narration"] == "대사입니다"

    def test_narration_overrides_dialogue(self):
        result = normalize_part(
            {"prompt": "p", "dialogue": "대사", "narration": "나레이션"},
            1,
        )
        assert result["narration"] == "나레이션"
        assert result["dialogue"] == "대사"


class TestNormalizeParts:
    def test_indexes_start_at_1(self):
        parts = normalize_parts([
            {"prompt": "A"},
            {"prompt": "B"},
        ])
        assert parts[0]["index"] == 1
        assert parts[1]["index"] == 2


class TestExtractScript:
    def test_joins_narration_from_parts(self):
        parts = [
            {"narration": "첫 번째 문장", "dialogue": "첫 번째 문장"},
            {"narration": "두 번째 문장", "dialogue": "두 번째 문장"},
        ]
        assert extract_script(parts) == "첫 번째 문장\n두 번째 문장"

    def test_falls_back_to_dialogue(self):
        parts = [
            {"dialogue": "대사만 있음"},
        ]
        assert extract_script(parts) == "대사만 있음"

    def test_skips_empty_parts(self):
        parts = [
            {"narration": "있음"},
            {"narration": "", "dialogue": ""},
            {"narration": "또 있음"},
        ]
        assert extract_script(parts) == "있음\n또 있음"
