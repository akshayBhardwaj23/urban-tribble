"""Signed API access tokens (HS256 JWT) for authenticating browser → FastAPI calls.

Tokens are issued only after a verified sign-in path (OTP, test-login, or
server-to-server bootstrap from NextAuth). Clients must send
``Authorization: Bearer <token>``. Bare ``X-User-Email`` is not trusted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional

from config import settings


class TokenError(Exception):
    """Invalid or expired access token."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _signing_key() -> bytes:
    secret = (settings.API_JWT_SECRET or "").strip()
    default = "dev-api-jwt-secret-change-in-production"
    if settings.is_production:
        if not secret or secret == default or len(secret) < 24:
            raise TokenError(
                "API_JWT_SECRET is missing, default, or too short. "
                "Refusing to sign or verify tokens."
            )
        return secret.encode("utf-8")
    # Local/dev may still use the committed default.
    return (secret or default).encode("utf-8")


def issue_access_token(*, user_id: str, email: str) -> str:
    """Return a compact HS256 JWT with ``sub`` = user id and ``email`` claim."""
    now = int(time.time())
    expire_hours = max(1, int(settings.API_JWT_EXPIRE_HOURS))
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + expire_hours * 3600,
    }
    segments = (
        f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))}."
        f"{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))}"
    )
    sig = hmac.new(_signing_key(), segments.encode("ascii"), hashlib.sha256).digest()
    return f"{segments}.{_b64url_encode(sig)}"


def verify_access_token(token: str) -> dict[str, Any]:
    """Validate signature and expiry. Returns payload or raises TokenError."""
    parts = (token or "").strip().split(".")
    if len(parts) != 3:
        raise TokenError("Malformed token")

    header_b64, payload_b64, sig_b64 = parts
    segments = f"{header_b64}.{payload_b64}"
    expected = hmac.new(
        _signing_key(), segments.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        got = _b64url_decode(sig_b64)
    except Exception as exc:
        raise TokenError("Malformed token signature") from exc

    if not hmac.compare_digest(expected, got):
        raise TokenError("Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise TokenError("Malformed token payload") from exc

    if not isinstance(payload, dict):
        raise TokenError("Malformed token payload")

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or int(time.time()) >= int(exp):
        raise TokenError("Token expired")

    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise TokenError("Token missing subject")

    return payload


def bearer_from_authorization(authorization: Optional[str]) -> Optional[str]:
    """Extract raw token from an ``Authorization`` header value."""
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None
