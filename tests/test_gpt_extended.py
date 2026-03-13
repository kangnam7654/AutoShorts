"""Extended tests for gpt.py — LLM clients, response extraction, prompt builders."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# --- _openai_client ---

class TestOpenaiClient:
    @patch("gpt.AI_PROVIDER", "openai")
    @patch("gpt.OPENAI_API_KEY", "sk-test")
    def test_openai_provider(self):
        import gpt

        with patch("gpt.OpenAI", create=True) as mock_cls:
            mock_cls.return_value = MagicMock()
            with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_cls)}):
                client = gpt._openai_client()
                mock_cls.assert_called_once_with(api_key="sk-test")

    @patch("gpt.AI_PROVIDER", "openai")
    @patch("gpt.OPENAI_API_KEY", "")
    def test_openai_missing_key_raises(self):
        import gpt

        with patch.dict("sys.modules", {"openai": MagicMock()}):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                gpt._openai_client()

    @patch("gpt.AI_PROVIDER", "unknown")
    def test_unknown_provider_raises(self):
        import gpt

        with patch.dict("sys.modules", {"openai": MagicMock()}):
            with pytest.raises(RuntimeError, match="Unknown AI_PROVIDER"):
                gpt._openai_client()

    @patch("gpt.AI_PROVIDER", "codex")
    def test_codex_provider(self):
        import gpt

        mock_openai = MagicMock()
        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai)}):
            with patch("gpt.get_access_token", create=True, return_value="tok"):
                with patch.dict("sys.modules", {"codex_auth": MagicMock(get_access_token=MagicMock(return_value="tok"))}):
                    gpt._openai_client()


# --- _pick_default_model ---

class TestPickDefaultModel:
    def test_configured_in_list(self):
        from gpt import _pick_default_model

        assert _pick_default_model(["a", "b", "c"], "b") == "b"

    def test_configured_not_in_list(self):
        from gpt import _pick_default_model

        assert _pick_default_model(["a", "b"], "z") == "a"

    def test_empty_list(self):
        from gpt import _pick_default_model

        assert _pick_default_model([], "fallback") == "fallback"


# --- _extract_ollama_model_name ---

class TestExtractOllamaModelName:
    def test_model_attr(self):
        from gpt import _extract_ollama_model_name

        obj = MagicMock()
        obj.model = "llama3.1:8b"
        assert _extract_ollama_model_name(obj) == "llama3.1:8b"

    def test_name_attr(self):
        from gpt import _extract_ollama_model_name

        obj = MagicMock(spec=[])
        obj.name = "qwen2.5"
        obj.model = None
        assert _extract_ollama_model_name(obj) == "qwen2.5"

    def test_dict_model(self):
        from gpt import _extract_ollama_model_name

        assert _extract_ollama_model_name({"model": "phi3"}) == "phi3"

    def test_dict_name(self):
        from gpt import _extract_ollama_model_name

        assert _extract_ollama_model_name({"name": "phi3"}) == "phi3"

    def test_empty(self):
        from gpt import _extract_ollama_model_name

        assert _extract_ollama_model_name(42) == ""


# --- _extract_ollama_response_text ---

class TestExtractOllamaResponseText:
    def test_message_content_attr(self):
        from gpt import _extract_ollama_response_text

        resp = MagicMock()
        resp.message.content = "hello world"
        assert _extract_ollama_response_text(resp) == "hello world"

    def test_message_dict(self):
        from gpt import _extract_ollama_response_text

        resp = MagicMock(spec=[])
        resp.message = {"content": "dict content"}
        assert _extract_ollama_response_text(resp) == "dict content"

    def test_response_attr(self):
        from gpt import _extract_ollama_response_text

        resp = MagicMock(spec=[])
        resp.message = None
        resp.response = "generate response"
        assert _extract_ollama_response_text(resp) == "generate response"

    def test_dict_response(self):
        from gpt import _extract_ollama_response_text

        assert _extract_ollama_response_text({"response": "raw"}) == "raw"

    def test_dict_message_content(self):
        from gpt import _extract_ollama_response_text

        assert _extract_ollama_response_text({"message": {"content": "nested"}}) == "nested"

    def test_empty_response(self):
        from gpt import _extract_ollama_response_text

        resp = MagicMock(spec=[])
        resp.message = None
        resp.response = None
        assert _extract_ollama_response_text(resp) == ""


# --- _resolve_text_response ---

class TestResolveTextResponse:
    def test_normal(self):
        from gpt import _resolve_text_response

        assert _resolve_text_response("  hello  ", "Test") == "hello"

    def test_empty_raises(self):
        from gpt import _resolve_text_response

        with pytest.raises(RuntimeError, match="Test returned an empty"):
            _resolve_text_response("", "Test")

    def test_whitespace_only_raises(self):
        from gpt import _resolve_text_response

        with pytest.raises(RuntimeError, match="empty"):
            _resolve_text_response("   ", "Provider")


# --- _clean_script_response ---

class TestCleanScriptResponse:
    def test_removes_markdown(self):
        from gpt import _clean_script_response

        result = _clean_script_response("**Bold** and #heading", 1)
        assert "*" not in result
        assert "#" not in result

    def test_removes_brackets(self):
        from gpt import _clean_script_response

        result = _clean_script_response("Text [Music] and (Note) here", 1)
        assert "[Music]" not in result
        assert "(Note)" not in result

    def test_limits_paragraphs(self):
        from gpt import _clean_script_response

        result = _clean_script_response("Para1\n\nPara2\n\nPara3", 2)
        assert "Para1" in result
        assert "Para2" in result
        assert "Para3" not in result


# --- _parse_list_of_strings ---

class TestParseListOfStrings:
    def test_valid_json(self):
        from gpt import _parse_list_of_strings

        assert _parse_list_of_strings('["a", "b"]') == ["a", "b"]

    def test_embedded_json(self):
        from gpt import _parse_list_of_strings

        assert _parse_list_of_strings('Some text ["a", "b"] more text') == ["a", "b"]

    def test_no_json_extracts_quoted(self):
        from gpt import _parse_list_of_strings

        result = _parse_list_of_strings('Here are terms: "alpha" and "beta".')
        assert result == ["alpha", "beta"]

    def test_invalid_json_type(self):
        from gpt import _parse_list_of_strings

        # JSON parses but not a list of strings
        result = _parse_list_of_strings('{"key": "value"}')
        assert isinstance(result, list)


# --- _pick_title / _pick_description ---

class TestPickTitle:
    def test_picks_first_valid_line(self):
        from gpt import _pick_title

        assert _pick_title("Option 1\nMy Great Title\n", "fallback") == "My Great Title"

    def test_skips_long_lines(self):
        from gpt import _pick_title

        long = "x" * 101
        assert _pick_title(f"{long}\nShort Title\n", "fallback") == "Short Title"

    def test_falls_back(self):
        from gpt import _pick_title

        assert _pick_title("", "my fallback") == "my fallback"


class TestPickDescription:
    def test_picks_valid_lines(self):
        from gpt import _pick_description

        assert "Good description" in _pick_description("Good description\nMore.", "fb")

    def test_skips_option_lines(self):
        from gpt import _pick_description

        result = _pick_description("Option 1\nGood text", "fb")
        assert "Good text" in result

    def test_falls_back(self):
        from gpt import _pick_description

        assert _pick_description("", "fallback") == "fallback"


# --- _build_veo_structure_lines ---

class TestBuildVeoStructureLines:
    def test_2_parts(self):
        from gpt import _build_veo_structure_lines

        result = _build_veo_structure_lines(2)
        assert "Part 1" in result
        assert "Part 2" in result
        assert "Part 3" not in result

    def test_4_parts(self):
        from gpt import _build_veo_structure_lines

        result = _build_veo_structure_lines(4)
        assert "Part 4" in result
        assert "24-32s" in result


# --- _parse_veo_parts ---

class TestParseVeoParts:
    def test_valid_json(self):
        from gpt import _parse_veo_parts

        result = _parse_veo_parts('[{"prompt": "a"}]')
        assert result == [{"prompt": "a"}]

    def test_embedded_json(self):
        from gpt import _parse_veo_parts

        result = _parse_veo_parts('Here: [{"prompt": "x"}] end')
        assert result[0]["prompt"] == "x"

    def test_invalid_returns_none(self):
        from gpt import _parse_veo_parts

        assert _parse_veo_parts("no json here") is None

    def test_non_list_returns_none(self):
        from gpt import _parse_veo_parts

        assert _parse_veo_parts('{"prompt": "x"}') is None


# --- list_models ---

class TestListModels:
    @patch("gpt.AI_PROVIDER", "ollama")
    @patch("gpt._list_ollama_models", return_value=(["m1", "m2"], "m1"))
    def test_ollama_provider(self, mock_list):
        from gpt import list_models

        models, default = list_models()
        assert models == ["m1", "m2"]

    @patch("gpt.AI_PROVIDER", "openai")
    @patch("gpt._list_openai_models", return_value=(["gpt-4o"], "gpt-4o"))
    def test_openai_provider(self, mock_list):
        from gpt import list_models

        models, default = list_models()
        assert "gpt-4o" in models

    @patch("gpt.AI_PROVIDER", "codex")
    @patch("gpt._list_openai_models")
    def test_codex_provider(self, mock_list):
        from gpt import list_models

        mock_list.return_value = (["gpt-5"], "gpt-5")
        models, _ = list_models()
        assert "gpt-5" in models


# --- _list_ollama_models ---

class TestListOllamaModels:
    @patch("gpt._ollama_client")
    def test_parses_model_list(self, mock_client_fn):
        from gpt import _list_ollama_models

        mock_client = MagicMock()
        mock_resp = MagicMock()
        m1 = MagicMock()
        m1.model = "llama3.1:8b"
        m2 = MagicMock()
        m2.model = "qwen2.5"
        mock_resp.models = [m1, m2]
        mock_client.list.return_value = mock_resp
        mock_client_fn.return_value = mock_client

        models, default = _list_ollama_models()
        assert "llama3.1:8b" in models
        assert "qwen2.5" in models

    @patch("gpt._ollama_client")
    def test_connection_error_raises(self, mock_client_fn):
        from gpt import _list_ollama_models

        mock_client_fn.return_value.list.side_effect = ConnectionError("no connection")

        with pytest.raises(RuntimeError, match="Failed to fetch"):
            _list_ollama_models()


# --- _list_openai_models ---

class TestListOpenaiModels:
    @patch("gpt.AI_PROVIDER", "codex")
    def test_codex_returns_known(self):
        from gpt import _list_openai_models

        models, _ = _list_openai_models()
        assert "gpt-5" in models

    @patch("gpt.AI_PROVIDER", "openai")
    @patch("gpt._openai_client")
    def test_openai_api_error_fallback(self, mock_client_fn):
        from gpt import _list_openai_models

        mock_client_fn.side_effect = Exception("API error")
        models, default = _list_openai_models()
        assert len(models) >= 1


# --- generate_script ---

class TestGenerateScript:
    @patch("gpt.generate_response", return_value="A cat sits on a mat.")
    def test_generates_script(self, mock_gen):
        from gpt import generate_script

        result = generate_script("cats", 1, "model", "en", "")
        assert "cat" in result

    @patch("gpt.generate_response", return_value="")
    def test_empty_response_returns_none(self, mock_gen):
        from gpt import generate_script

        result = generate_script("cats", 1, "model", "en", "")
        assert result is None


# --- _generate_ollama ---

class TestGenerateOllama:
    @patch("gpt._ollama_client")
    def test_successful_chat(self, mock_client_fn):
        import gpt

        mock_client = MagicMock()
        resp = MagicMock()
        resp.message.content = "response text"
        mock_client.chat.return_value = resp
        mock_client_fn.return_value = mock_client

        result = gpt._generate_ollama("prompt", "llama3.1:8b")
        assert result == "response text"

    @patch("gpt._list_ollama_models", return_value=(["phi3"], "phi3"))
    @patch("gpt._ollama_client")
    def test_model_not_found_raises(self, mock_client_fn, mock_list):
        import gpt
        from unittest.mock import PropertyMock

        # Simulate ResponseError with status_code 404
        mock_err = MagicMock()
        mock_err.status_code = 404
        mock_err.__str__ = lambda self: "model not found"

        mock_client = MagicMock()

        # Import the actual ResponseError or mock it
        ResponseError = type("ResponseError", (Exception,), {"status_code": 404})
        err_instance = ResponseError("model not found")
        err_instance.status_code = 404

        # chat raises 404, generate also raises 404
        with patch.dict("sys.modules", {"ollama": MagicMock(
            Client=MagicMock(return_value=mock_client),
            ResponseError=ResponseError,
        )}):
            mock_client.chat.side_effect = err_instance
            mock_client.generate.side_effect = err_instance

            import importlib
            importlib.reload(gpt)

            with pytest.raises(RuntimeError, match="not installed"):
                gpt._generate_ollama("prompt", "nonexistent")


# --- _generate_openai ---

class TestGenerateOpenai:
    @patch("gpt.AI_PROVIDER", "openai")
    @patch("gpt._openai_client")
    def test_successful_completion(self, mock_client_fn):
        import gpt

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="AI response"))
        ]
        mock_client_fn.return_value = mock_client

        result = gpt._generate_openai("prompt", "gpt-4o")
        assert result == "AI response"

    @patch("gpt.AI_PROVIDER", "openai")
    @patch("gpt._openai_client")
    def test_api_error_raises(self, mock_client_fn):
        import gpt

        mock_client_fn.return_value.chat.completions.create.side_effect = Exception("timeout")

        with pytest.raises(RuntimeError, match="OpenAI API error"):
            gpt._generate_openai("prompt", "gpt-4o")


# --- _build_archive_section ---

class TestBuildArchiveSection:
    def test_empty(self):
        from gpt import _build_archive_section

        assert _build_archive_section("") == ""

    def test_with_content(self):
        from gpt import _build_archive_section

        result = _build_archive_section("- entry1\n- entry2")
        assert "PREVIOUS VIDEOS" in result
        assert "DIFFERENT" in result


# --- _format_archive_for_prompt ---

class TestFormatArchiveForPrompt:
    def test_empty_archive(self):
        from gpt import _format_archive_for_prompt

        assert _format_archive_for_prompt([]) == ""

    def test_formats_entries(self):
        from gpt import _format_archive_for_prompt

        archive = [{
            "date": "2026-03-10",
            "subject": "돈복",
            "parts": [{"situation": "마법사이 등장"}],
        }]
        result = _format_archive_for_prompt(archive)
        assert "돈복" in result
        assert "2026-03-10" in result
