"""Tests for gpt.py — AI response generation, metadata, subtitle correction."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# --- correct_subtitles ---

class TestCorrectSubtitles:
    @patch("gpt.generate_response")
    def test_returns_corrected_srt(self, mock_gen):
        from gpt import correct_subtitles

        mock_gen.return_value = "1\n00:00:00,000 --> 00:00:01,000\ncorrected text\n"

        result = correct_subtitles(
            "1\n00:00:00,000 --> 00:00:01,000\nwrong text\n",
            "corrected text",
            "",
        )
        assert "corrected text" in result
        assert "-->" in result

    @patch("gpt.generate_response")
    def test_falls_back_on_invalid_response(self, mock_gen):
        from gpt import correct_subtitles

        mock_gen.return_value = "I can't do that, sorry."

        original = "1\n00:00:00,000 --> 00:00:01,000\noriginal\n"
        result = correct_subtitles(original, "script", "")
        # Should return original since LLM response has no "-->"
        assert result == original

    @patch("gpt.generate_response")
    def test_prompt_includes_both_inputs(self, mock_gen):
        from gpt import correct_subtitles

        mock_gen.return_value = "1\n00:00:00,000 --> 00:00:01,000\nfixed\n"

        correct_subtitles("srt content here", "my script", "")

        prompt = mock_gen.call_args[0][0]
        assert "srt content here" in prompt
        assert "my script" in prompt


# --- generate_metadata ---

class TestGenerateMetadata:
    @patch("gpt.get_search_terms", return_value=["term1", "term2"])
    @patch("gpt.generate_response")
    def test_returns_title_desc_keywords(self, mock_gen, mock_terms):
        from gpt import generate_metadata

        mock_gen.side_effect = [
            "My Amazing Title",      # title response
            "A great description.",   # description response
        ]

        title, desc, keywords = generate_metadata("test subject", "test script", "")

        assert title == "My Amazing Title"
        assert "great description" in desc
        assert keywords == ["term1", "term2"]

    @patch("gpt.get_search_terms", return_value=[])
    @patch("gpt.generate_response")
    def test_title_strips_markdown(self, mock_gen, mock_terms):
        from gpt import generate_metadata

        mock_gen.side_effect = [
            "## **Bold Title Here**",
            "desc",
        ]

        title, desc, _ = generate_metadata("test", "script", "")
        assert "#" not in title
        assert "*" not in title

    @patch("gpt.get_search_terms", return_value=[])
    @patch("gpt.generate_response")
    def test_title_fallback_to_subject(self, mock_gen, mock_terms):
        from gpt import generate_metadata

        mock_gen.side_effect = [
            "",        # empty title
            "desc",
        ]

        title, _, _ = generate_metadata("fallback subject", "script", "")
        assert title == "fallback subject"


# --- generate_response ---

class TestGenerateResponse:
    def test_routes_to_ollama(self):
        import gpt

        with patch.object(gpt, "AI_PROVIDER", "ollama"):
            with patch.object(gpt, "_generate_ollama", return_value="ollama response") as mock_ollama:
                result = gpt.generate_response("prompt", "model")
                assert result == "ollama response"
                mock_ollama.assert_called_once_with("prompt", "model")

    def test_routes_to_openai(self):
        import gpt

        with patch.object(gpt, "AI_PROVIDER", "openai"):
            with patch.object(gpt, "_generate_openai", return_value="openai response") as mock_openai:
                result = gpt.generate_response("prompt", "model")
                assert result == "openai response"
                mock_openai.assert_called_once_with("prompt", "model")


# --- get_search_terms ---

class TestGetSearchTerms:
    @patch("gpt.generate_response")
    def test_extracts_quoted_terms(self, mock_gen):
        from gpt import get_search_terms

        mock_gen.return_value = '["ocean facts", "marine life", "deep sea"]'

        terms = get_search_terms("ocean", 3, "ocean script", "")
        assert len(terms) == 3
        assert "ocean facts" in terms

    @patch("gpt.generate_response")
    def test_retries_on_bad_json(self, mock_gen):
        from gpt import get_search_terms

        mock_gen.side_effect = [
            "not json at all",
            '["term1", "term2"]',
        ]

        terms = get_search_terms("topic", 2, "script", "")
        # Should have called generate_response twice
        assert mock_gen.call_count >= 1
