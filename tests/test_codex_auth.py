"""Tests for codex_auth.py — token expiry, JWT parsing, and auth URL helpers."""

import base64
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _jwt(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"header.{encoded}.sig"


def test_decode_jwt_payload_returns_claims():
    import legacy.codex_auth as codex_auth

    payload = {"sub": "123", "https://api.openai.com/auth": {"chatgpt_account_id": "acct_1"}}
    token = _jwt(payload)

    assert codex_auth._decode_jwt_payload(token) == payload


def test_is_expired_respects_refresh_margin():
    import legacy.codex_auth as codex_auth

    tokens = {
        "saved_at": time.time() - 1000,
        "expires_in": 100,
    }

    assert codex_auth._is_expired(tokens) is True


def test_auth_url_contains_state_and_challenge():
    import legacy.codex_auth as codex_auth

    url = codex_auth._auth_url("challenge123", "state456")

    assert "challenge123" in url
    assert "state456" in url
    assert "code_challenge_method=S256" in url

