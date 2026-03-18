"""Codex OAuth PKCE authentication for ChatGPT subscription access."""

import base64
import hashlib
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import requests

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
REDIRECT_PORT = 1455
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/auth/callback"
SCOPE = "openid profile email offline_access"
TOKEN_FILE = Path.home() / ".moneyprinter" / "codex-auth.json"
REFRESH_MARGIN = 300
CALLBACK_PATH = "/auth/callback"
OAUTH_TIMEOUT_SECONDS = 120
FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


def _generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _save_tokens(data: dict) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["saved_at"] = time.time()
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    TOKEN_FILE.chmod(0o600)


def _load_tokens() -> Optional[dict]:
    if not TOKEN_FILE.exists():
        return None

    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _is_expired(tokens: dict) -> bool:
    saved_at = tokens.get("saved_at", 0)
    expires_in = tokens.get("expires_in", 0)
    return time.time() > (saved_at + expires_in - REFRESH_MARGIN)


def _post_token_request(payload: dict) -> dict:
    response = requests.post(
        TOKEN_URL,
        data=payload,
        headers=FORM_HEADERS,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Token request failed ({response.status_code}): {response.text}"
        )
    return response.json()


def _refresh_token(tokens: dict) -> dict:
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No refresh token available. Run `cli.py auth` again.")

    new_tokens = _post_token_request(
        {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": refresh_token,
        }
    )
    if "refresh_token" not in new_tokens:
        new_tokens["refresh_token"] = refresh_token
    _save_tokens(new_tokens)
    return new_tokens


def _decode_jwt_payload(token: str) -> dict:
    """Decode a JWT payload without signature verification."""
    parts = token.split(".")
    if len(parts) < 2:
        return {}

    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def get_access_token() -> str:
    """Get a valid access token, refreshing if needed."""
    tokens = _load_tokens()
    if not tokens:
        raise RuntimeError(
            "Not authenticated. Run `cli.py auth` to sign in with your ChatGPT account."
        )

    if _is_expired(tokens):
        tokens = _refresh_token(tokens)

    access_token = tokens.get("access_token")
    if not access_token:
        raise RuntimeError("No access token found. Run `cli.py auth` again.")

    return access_token


def get_account_id() -> str:
    """Extract ChatGPT account ID from the JWT access token."""
    payload = _decode_jwt_payload(get_access_token())
    auth_claim = payload.get("https://api.openai.com/auth", {})
    account_id = auth_claim.get("chatgpt_account_id", "")
    if not account_id:
        raise RuntimeError(
            "Could not extract account ID from token. Run `cli.py auth` again."
        )
    return account_id


def _callback_html(message: str) -> bytes:
    return f"<html><body><h2>{message}</h2></body></html>".encode()


def _auth_url(challenge: str, state: str) -> str:
    params = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": SCOPE,
            "state": state,
        }
    )
    return f"{AUTH_URL}?{params}"


def _callback_server(state: str, auth_code_holder: dict):
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return

            params = parse_qs(parsed.query)
            returned_state = params.get("state", [None])[0]
            if returned_state != state:
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(_callback_html("State mismatch"))
                return

            code = params.get("code", [None])[0]
            if code:
                auth_code_holder["code"] = code
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(_callback_html("Authenticated! You can close this tab."))
                return

            auth_code_holder["error"] = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_callback_html(f"Error: {auth_code_holder['error']}"))

        def log_message(self, _format, *_args):
            return

    return HTTPServer(("127.0.0.1", REDIRECT_PORT), CallbackHandler)


def _wait_for_callback(server: HTTPServer) -> threading.Thread:
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()
    return server_thread


def _validate_callback_result(auth_code_holder: dict) -> str:
    if "error" in auth_code_holder:
        raise RuntimeError(f"Authentication failed: {auth_code_holder['error']}")

    code = auth_code_holder.get("code")
    if not code:
        raise RuntimeError("Authentication timed out. Try again.")
    return code


def _exchange_code_for_tokens(code: str, verifier: str) -> dict:
    return _post_token_request(
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }
    )


def login() -> None:
    """Run the OAuth PKCE flow, then persist the returned tokens."""
    verifier, challenge = _generate_pkce()
    state = secrets.token_hex(16)
    auth_code_holder: dict = {}

    server = _callback_server(state, auth_code_holder)
    server_thread = _wait_for_callback(server)
    auth_url = _auth_url(challenge, state)

    print("Opening browser for authentication...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server_thread.join(timeout=OAUTH_TIMEOUT_SECONDS)
    server.server_close()

    code = _validate_callback_result(auth_code_holder)
    tokens = _exchange_code_for_tokens(code, verifier)
    _save_tokens(tokens)
    print("Authentication successful! Tokens saved.")
