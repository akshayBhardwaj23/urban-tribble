"""Generate, store, verify email OTPs; send via Resend."""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import secrets
from collections import defaultdict
from datetime import datetime, timedelta
from typing import DefaultDict, List

import httpx
from sqlalchemy.orm import Session

from config import settings
from models.models import LoginOtpChallenge, User
from utils.email_norm import normalize_email, user_by_email_ci

_CODE_RE = re.compile(r"^\d{6}$")

_verify_fails: DefaultDict[str, List[datetime]] = defaultdict(list)


def _hash_code(email: str, code: str) -> str:
    n = normalize_email(email)
    msg = f"{n}:{code}".encode()
    return hmac.new(
        settings.OTP_PEPPER.encode(),
        msg,
        hashlib.sha256,
    ).hexdigest()


def seconds_until_otp_resend_allowed(db: Session, email: str) -> int:
    """Seconds until another OTP may be sent (DB-backed; works across app instances)."""
    n = normalize_email(email)
    row = (
        db.query(LoginOtpChallenge)
        .filter(LoginOtpChallenge.email == n)
        .order_by(LoginOtpChallenge.created_at.desc())
        .first()
    )
    if not row:
        return 0
    elapsed = (datetime.utcnow() - row.created_at).total_seconds()
    remaining = settings.OTP_RESEND_SECONDS - elapsed
    if remaining <= 0:
        return 0
    return int(math.ceil(remaining))


def _verify_failures_prune(email: str) -> None:
    n = normalize_email(email)
    cutoff = datetime.utcnow() - timedelta(minutes=15)
    _verify_fails[n] = [t for t in _verify_fails[n] if t > cutoff]


def _verify_rate_limited(email: str) -> bool:
    _verify_failures_prune(email)
    n = normalize_email(email)
    return len(_verify_fails[n]) >= 8


def _record_verify_failure(email: str) -> None:
    _verify_fails[normalize_email(email)].append(datetime.utcnow())


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def send_otp_email(db: Session, email: str) -> tuple[bool, str, int]:
    """
    Send OTP via Resend, then persist challenge.

    Returns (ok, message_for_logs_or_error, retry_after_seconds).
    retry_after_seconds is > 0 only when rate-limited.
    """
    n = normalize_email(email)
    api_key = (settings.RESEND_API_KEY or "").strip()
    if not api_key:
        return False, "RESEND_API_KEY not configured", 0

    retry_after = seconds_until_otp_resend_allowed(db, n)
    if retry_after > 0:
        return False, "rate_limited_send", retry_after

    code = generate_code()
    code_hash = _hash_code(n, code)
    expires = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

    subject = "Your sign-in code"
    html = (
        f"<p>Your sign-in code is <strong>{code}</strong>.</p>"
        f"<p>It expires in {settings.OTP_EXPIRE_MINUTES} minutes. "
        "If you didn’t request this, you can ignore this email.</p>"
    )

    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.RESEND_FROM_EMAIL.strip(),
                "to": [n],
                "subject": subject,
                "html": html,
            },
            timeout=20.0,
        )
    except httpx.HTTPError as e:
        return False, f"network_error:{e!s}", 0

    if r.status_code >= 400:
        body = (r.text or "").strip()
        if len(body) > 500:
            body = body[:500] + "…"
        return False, f"resend_http_{r.status_code}:{body or 'no body'}", 0

    db.query(LoginOtpChallenge).filter(
        LoginOtpChallenge.email == n
    ).delete(synchronize_session=False)
    db.add(
        LoginOtpChallenge(
            email=n,
            code_hash=code_hash,
            expires_at=expires,
        )
    )
    db.commit()

    return True, "sent", settings.OTP_RESEND_SECONDS


def verify_otp_and_get_user(db: Session, email: str, code: str) -> User | None:
    """If code valid, delete challenge and return user (create if missing)."""
    n = normalize_email(email)
    if not _CODE_RE.match(code.strip()):
        _record_verify_failure(n)
        return None

    if _verify_rate_limited(n):
        return None

    row = (
        db.query(LoginOtpChallenge)
        .filter(LoginOtpChallenge.email == n)
        .order_by(LoginOtpChallenge.created_at.desc())
        .first()
    )
    if not row:
        _record_verify_failure(n)
        return None

    if datetime.utcnow() > row.expires_at:
        db.delete(row)
        db.commit()
        _record_verify_failure(n)
        return None

    expected = _hash_code(n, code.strip())
    if not hmac.compare_digest(expected, row.code_hash):
        _record_verify_failure(n)
        return None

    db.delete(row)
    db.commit()

    user = user_by_email_ci(db, n)
    if not user:
        user = User(email=n, name=None, image=None)
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
