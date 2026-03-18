"""Extended tests for codex_auth.py — PKCE, token management, OAuth helpers."""

import base64
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestGeneratePkce:
    def test_returns_verifier_and_challenge(self):
        from legacy.codex_auth import _generate_pkce

        verifier, challenge = _generate_pkce()
        assert len(verifier) > 20
        assert len(challenge) > 20
        assert verifier != challenge


class TestSaveTokens:
    def test_saves_json_to_file(self, tmp_path):
        import legacy.codex_auth as codex_auth

        token_file = tmp_path / "tokens.json"
        with patch.object(codex_auth, "TOKEN_FILE", token_file):
            codex_auth._save_tokens({"access_token": "abc", "expires_in": 3600})

        data = json.loads(token_file.read_text())
        assert data["access_token"] == "abc"
        assert "saved_at" in data


class TestLoadTokens:
    def test_returns_none_when_missing(self, tmp_path):
        import legacy.codex_auth as codex_auth

        with patch.object(codex_auth, "TOKEN_FILE", tmp_path / "nonexistent.json"):
            assert codex_auth._load_tokens() is None

    def test_loads_existing_tokens(self, tmp_path):
        import legacy.codex_auth as codex_auth

        token_file = tmp_path / "tokens.json"
        token_file.write_text(json.dumps({"access_token": "xyz"}))

        with patch.object(codex_auth, "TOKEN_FILE", token_file):
            result = codex_auth._load_tokens()
            assert result["access_token"] == "xyz"

    def test_returns_none_on_bad_json(self, tmp_path):
        import legacy.codex_auth as codex_auth

        token_file = tmp_path / "tokens.json"
        token_file.write_text("not json{{{")

        with patch.object(codex_auth, "TOKEN_FILE", token_file):
            assert codex_auth._load_tokens() is None


class TestIsExpired:
    def test_not_expired(self):
        from legacy.codex_auth import _is_expired

        tokens = {"saved_at": time.time(), "expires_in": 3600}
        assert _is_expired(tokens) is False

    def test_expired(self):
        from legacy.codex_auth import _is_expired

        tokens = {"saved_at": time.time() - 7200, "expires_in": 3600}
        assert _is_expired(tokens) is True

    def test_within_refresh_margin(self):
        from legacy.codex_auth import REFRESH_MARGIN, _is_expired

        # Expires in exactly REFRESH_MARGIN seconds → should be expired
        tokens = {"saved_at": time.time() - 3600 + REFRESH_MARGIN - 1, "expires_in": 3600}
        assert _is_expired(tokens) is True


class TestPostTokenRequest:
    @patch("legacy.codex_auth.requests.post")
    def test_success(self, mock_post):
        from legacy.codex_auth import _post_token_request

        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"access_token": "new"}),
        )
        result = _post_token_request({"grant_type": "refresh_token"})
        assert result["access_token"] == "new"

    @patch("legacy.codex_auth.requests.post")
    def test_failure_raises(self, mock_post):
        from legacy.codex_auth import _post_token_request

        mock_post.return_value = MagicMock(status_code=400, text="Bad request")

        with pytest.raises(RuntimeError, match="Token request failed"):
            _post_token_request({})


class TestRefreshToken:
    @patch("legacy.codex_auth._save_tokens")
    @patch("legacy.codex_auth._post_token_request")
    def test_refreshes_and_saves(self, mock_post, mock_save):
        from legacy.codex_auth import _refresh_token

        mock_post.return_value = {"access_token": "refreshed", "refresh_token": "new_rt"}
        result = _refresh_token({"refresh_token": "old_rt"})
        assert result["access_token"] == "refreshed"
        mock_save.assert_called_once()

    @patch("legacy.codex_auth._save_tokens")
    @patch("legacy.codex_auth._post_token_request")
    def test_preserves_old_refresh_token(self, mock_post, mock_save):
        from legacy.codex_auth import _refresh_token

        mock_post.return_value = {"access_token": "new"}  # no refresh_token in response
        result = _refresh_token({"refresh_token": "old_rt"})
        assert result["refresh_token"] == "old_rt"

    def test_no_refresh_token_raises(self):
        from legacy.codex_auth import _refresh_token

        with pytest.raises(RuntimeError, match="No refresh token"):
            _refresh_token({})


class TestGetAccessToken:
    @patch("legacy.codex_auth._load_tokens")
    def test_not_authenticated_raises(self, mock_load):
        from legacy.codex_auth import get_access_token

        mock_load.return_value = None
        with pytest.raises(RuntimeError, match="Not authenticated"):
            get_access_token()

    @patch("legacy.codex_auth._load_tokens")
    def test_returns_valid_token(self, mock_load):
        from legacy.codex_auth import get_access_token

        mock_load.return_value = {
            "access_token": "valid_token",
            "saved_at": time.time(),
            "expires_in": 3600,
        }
        assert get_access_token() == "valid_token"

    @patch("legacy.codex_auth._refresh_token")
    @patch("legacy.codex_auth._load_tokens")
    def test_refreshes_expired_token(self, mock_load, mock_refresh):
        from legacy.codex_auth import get_access_token

        mock_load.return_value = {
            "access_token": "old",
            "saved_at": time.time() - 7200,
            "expires_in": 3600,
        }
        mock_refresh.return_value = {
            "access_token": "refreshed",
            "saved_at": time.time(),
            "expires_in": 3600,
        }
        assert get_access_token() == "refreshed"

    @patch("legacy.codex_auth._load_tokens")
    def test_missing_access_token_raises(self, mock_load):
        from legacy.codex_auth import get_access_token

        mock_load.return_value = {
            "saved_at": time.time(),
            "expires_in": 3600,
        }
        with pytest.raises(RuntimeError, match="No access token"):
            get_access_token()


class TestGetAccountId:
    @patch("legacy.codex_auth.get_access_token")
    def test_extracts_account_id(self, mock_token):
        from legacy.codex_auth import get_account_id

        # Create a JWT with chatgpt_account_id
        payload = {"https://api.openai.com/auth": {"chatgpt_account_id": "acct_123"}}
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        fake_jwt = f"header.{payload_b64}.signature"

        mock_token.return_value = fake_jwt
        assert get_account_id() == "acct_123"

    @patch("legacy.codex_auth.get_access_token")
    def test_missing_account_id_raises(self, mock_token):
        from legacy.codex_auth import get_account_id

        payload = {"sub": "user"}
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        mock_token.return_value = f"h.{payload_b64}.s"

        with pytest.raises(RuntimeError, match="account ID"):
            get_account_id()


class TestDecodeJwtPayload:
    def test_valid_jwt(self):
        from legacy.codex_auth import _decode_jwt_payload

        payload = {"sub": "user123"}
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        result = _decode_jwt_payload(f"header.{encoded}.sig")
        assert result["sub"] == "user123"

    def test_invalid_jwt(self):
        from legacy.codex_auth import _decode_jwt_payload

        assert _decode_jwt_payload("not-a-jwt") == {}


class TestCallbackHtml:
    def test_returns_html_bytes(self):
        from legacy.codex_auth import _callback_html

        result = _callback_html("Success!")
        assert b"Success!" in result
        assert b"<html>" in result


class TestAuthUrl:
    def test_builds_correct_url(self):
        from legacy.codex_auth import _auth_url

        url = _auth_url("challenge123", "state456")
        assert "challenge123" in url
        assert "state456" in url
        assert "authorize" in url


class TestValidateCallbackResult:
    def test_success(self):
        from legacy.codex_auth import _validate_callback_result

        assert _validate_callback_result({"code": "abc"}) == "abc"

    def test_error_raises(self):
        from legacy.codex_auth import _validate_callback_result

        with pytest.raises(RuntimeError, match="Authentication failed"):
            _validate_callback_result({"error": "access_denied"})

    def test_timeout_raises(self):
        from legacy.codex_auth import _validate_callback_result

        with pytest.raises(RuntimeError, match="timed out"):
            _validate_callback_result({})


class TestExchangeCodeForTokens:
    @patch("legacy.codex_auth._post_token_request")
    def test_exchanges_code(self, mock_post):
        from legacy.codex_auth import _exchange_code_for_tokens

        mock_post.return_value = {"access_token": "new_token"}
        result = _exchange_code_for_tokens("code123", "verifier456")
        assert result["access_token"] == "new_token"
        assert mock_post.call_args[0][0]["code"] == "code123"
