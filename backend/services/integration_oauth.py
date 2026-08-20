"""OAuth helpers for third-party integrations."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from config import settings
from models.models import IntegrationOauthSession

logger = logging.getLogger(__name__)

# How long a user has between the provider redirecting back and confirming
# which file to connect. Long enough for a slow picker, short enough that
# freshly-issued provider tokens are not sitting at rest for long.
OAUTH_SESSION_TTL_SECONDS = 3600


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
    body = dict(payload)
    # Short-lived so a leaked state cannot be replayed forever.
    body.setdefault(
        "exp",
        int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
    )
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
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
    data = json.loads(raw.decode("utf-8"))
    exp = data.get("exp")
    if exp is not None:
        try:
            if int(exp) < int(datetime.now(UTC).timestamp()):
                raise ValueError("OAuth state has expired; start the connection again.")
        except (TypeError, ValueError) as e:
            if "expired" in str(e).lower():
                raise
            raise ValueError("Invalid OAuth state expiry") from e
    return data


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


def prune_expired_oauth_sessions(db: Session) -> int:
    """Opportunistic cleanup so the table tracks in-flight attempts, not history."""
    result = db.execute(
        delete(IntegrationOauthSession).where(
            IntegrationOauthSession.expires_at <= datetime.utcnow()
        )
    )
    db.commit()
    return int(result.rowcount or 0)


def create_oauth_session(db: Session, payload: dict) -> str:
    """Persist OAuth handoff state and return its id.

    The payload carries the provider's freshly-issued access and refresh
    tokens, so it is sealed with the same envelope encryption used for stored
    integration credentials rather than written as readable JSON.
    """
    from services.integration_credentials import encrypt_config

    prune_expired_oauth_sessions(db)

    session_id = str(uuid4())
    now = datetime.utcnow()
    row = IntegrationOauthSession(
        id=session_id,
        workspace_id=str(payload["workspace_id"]),
        user_email=str(payload["user_email"]),
        provider=str(payload.get("provider") or ""),
        payload_json=encrypt_config(payload),
        expires_at=now + timedelta(seconds=OAUTH_SESSION_TTL_SECONDS),
        created_at=now,
    )
    db.add(row)
    db.commit()
    return session_id


def _decode_session(row: IntegrationOauthSession) -> dict | None:
    from services.integration_credentials import (
        IntegrationCredentialsError,
        decrypt_config,
    )

    try:
        return decrypt_config(row.payload_json)
    except IntegrationCredentialsError:
        # A rotated or lost INTEGRATION_CREDENTIALS_KEY makes this unreadable.
        # It is a throwaway, short-lived record: treat it as gone and let the
        # user start the connection again, rather than failing the request.
        logger.warning(
            "Discarding unreadable OAuth session %s; user must reconnect.", row.id
        )
        return None


def get_oauth_session(db: Session, session_id: str) -> dict | None:
    row = (
        db.query(IntegrationOauthSession)
        .filter(IntegrationOauthSession.id == session_id)
        .first()
    )
    if not row:
        return None
    if row.expires_at <= datetime.utcnow():
        db.delete(row)
        db.commit()
        return None
    payload = _decode_session(row)
    if payload is None:
        db.delete(row)
        db.commit()
        return None
    return payload


def pop_oauth_session(db: Session, session_id: str) -> dict | None:
    """Read and consume a session. Genuinely single-use across workers.

    The delete is what decides the winner, not the preceding read: two
    concurrent completions both see the row, but only the one whose DELETE
    reports a matched row gets the payload back. Without that, a double-submit
    could create the same integration twice.
    """
    row = (
        db.query(IntegrationOauthSession)
        .filter(IntegrationOauthSession.id == session_id)
        .first()
    )
    if not row:
        return None

    expired = row.expires_at <= datetime.utcnow()
    payload = None if expired else _decode_session(row)

    result = db.execute(
        delete(IntegrationOauthSession).where(IntegrationOauthSession.id == session_id)
    )
    db.commit()
    if result.rowcount != 1:
        return None
    return payload
