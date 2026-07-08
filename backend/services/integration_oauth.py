"""OAuth helpers for third-party integrations."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from urllib.parse import urlencode

from config import settings

_oauth_sessions: dict[str, dict] = {}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _unb64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def microsoft_oauth_configured() -> bool:
    return bool(
        settings.MICROSOFT_CLIENT_ID
        and settings.MICROSOFT_CLIENT_SECRET
        and settings.MICROSOFT_REDIRECT_URI
    )


def build_signed_state(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(
        settings.INTEGRATION_OAUTH_STATE_SECRET.encode("utf-8"),
        raw,
        hashlib.sha256,
    ).digest()
    return f"{_b64url(raw)}.{_b64url(sig)}"


def parse_signed_state(state: str) -> dict:
    try:
        raw_b64, sig_b64 = state.split(".", 1)
        raw = _unb64url(raw_b64)
        sig = _unb64url(sig_b64)
    except Exception as e:  # pragma: no cover - defensive
        raise ValueError("Invalid OAuth state") from e
    expected = hmac.new(
        settings.INTEGRATION_OAUTH_STATE_SECRET.encode("utf-8"),
        raw,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Invalid OAuth state signature")
    return json.loads(raw.decode("utf-8"))


def build_microsoft_authorize_url(state: str) -> str:
    tenant = settings.MICROSOFT_TENANT_ID or "common"
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "response_mode": "query",
        "scope": "offline_access User.Read Files.Read",
        "state": state,
        "prompt": "select_account",
    }
    return (
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?"
        f"{urlencode(params)}"
    )


def create_oauth_session(payload: dict) -> str:
    session_id = str(uuid4())
    _oauth_sessions[session_id] = {
        **payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return session_id


def get_oauth_session(session_id: str) -> dict | None:
    session = _oauth_sessions.get(session_id)
    if not session:
        return None
    created_at = datetime.fromisoformat(session["created_at"].replace("Z", "+00:00"))
    if created_at < datetime.now(timezone.utc) - timedelta(hours=1):
        _oauth_sessions.pop(session_id, None)
        return None
    return session


def pop_oauth_session(session_id: str) -> dict | None:
    session = get_oauth_session(session_id)
    if session:
        _oauth_sessions.pop(session_id, None)
    return session
