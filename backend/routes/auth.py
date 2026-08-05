from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from deps import require_user
from models.models import User, Workspace
from services.account_deletion import delete_user_account
from services.api_tokens import issue_access_token
from services.otp_email import send_otp_email, verify_otp_and_get_user
from services.subscription_usage import get_effective_plan
from utils.email_norm import normalize_email, user_by_email_ci

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _const_time_str_eq(a: str, b: str) -> bool:
    """Compare two strings in constant time (length-safe via SHA-256 digests)."""
    da = hashlib.sha256(a.encode("utf-8")).digest()
    db = hashlib.sha256(b.encode("utf-8")).digest()
    return hmac.compare_digest(da, db)


def _profile_billing_fields(db: Session, user: User) -> dict:
    end = user.subscription_current_period_end
    return {
        "subscription_plan": get_effective_plan(db, user),
        "subscription_renews_at": end.isoformat() if end else None,
    }


def _workspace_json(w: Workspace) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "created_at": w.created_at.isoformat(),
        "outlook_forecast_dataset_id": w.outlook_forecast_dataset_id,
        "outlook_forecast_date_column": w.outlook_forecast_date_column,
        "outlook_forecast_value_column": w.outlook_forecast_value_column,
    }


def _token_payload(db: Session, user: User) -> dict:
    return {
        "access_token": issue_access_token(user_id=user.id, email=user.email),
        "token_type": "bearer",
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "image": user.image,
        **_profile_billing_fields(db, user),
    }


def _ensure_active_workspace(db: Session, user: User, workspaces: list[Workspace]) -> User:
    if not user.active_workspace_id and workspaces:
        user.active_workspace_id = workspaces[0].id
        db.commit()
        db.refresh(user)
    return user


def _workspaces_for_user(db: Session, user: User) -> list[Workspace]:
    return (
        db.query(Workspace)
        .filter(Workspace.owner_id == user.id)
        .order_by(Workspace.created_at.asc())
        .all()
    )


def _upsert_user(
    db: Session,
    *,
    email: str,
    name: Optional[str],
    image: Optional[str],
) -> User:
    email_norm = normalize_email(email)
    user = user_by_email_ci(db, email_norm)
    if not user:
        user = User(email=email_norm, name=name, image=image)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    changed = False
    if name and name != user.name:
        user.name = name
        changed = True
    if image is not None and image != user.image:
        user.image = image
        changed = True
    if changed:
        db.commit()
        db.refresh(user)
    return user


def _require_internal_auth_secret(x_internal_auth_secret: Optional[str]) -> None:
    expected = (settings.INTERNAL_AUTH_SECRET or "").strip()
    provided = (x_internal_auth_secret or "").strip()
    if not expected or not provided or not _const_time_str_eq(provided, expected):
        raise HTTPException(401, "Unauthorized")


class SyncUserRequest(BaseModel):
    name: Optional[str] = None
    image: Optional[str] = None


class BootstrapUserRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    image: Optional[str] = None


class OtpSendRequest(BaseModel):
    email: EmailStr


class OtpVerifyRequest(BaseModel):
    email: EmailStr
    code: str


class TestLoginRequest(BaseModel):
    email: EmailStr
    secret: str = ""


@router.post("/otp/send")
def otp_send(
    req: OtpSendRequest,
    db: Session = Depends(get_db),
    x_forwarded_for: Optional[str] = Header(default=None),
):
    """Send a 6-digit sign-in code to the email (Resend)."""
    from services.upload_rate_limit import check_rate_limit

    # Global / per-IP budgets so a spray of addresses cannot burn the Resend quota.
    client_ip = (x_forwarded_for or "").split(",")[0].strip() or "unknown"
    try:
        check_rate_limit(
            db,
            client_ip,
            scope="otp_send_ip",
            per_minute=10,
            per_hour=60,
        )
        check_rate_limit(
            db,
            "global",
            scope="otp_send_global",
            per_minute=120,
            per_hour=2000,
        )
    except HTTPException:
        raise

    ok, detail, retry_after = send_otp_email(db, str(req.email))
    if detail == "rate_limited_send":
        wait = retry_after or settings.OTP_RESEND_SECONDS
        raise HTTPException(
            status_code=429,
            detail=f"Wait {wait} seconds before requesting another code.",
            headers={"Retry-After": str(wait)},
        )
    if not ok:
        if detail == "RESEND_API_KEY not configured":
            raise HTTPException(
                503,
                "Email sign-in is temporarily unavailable. Try again later.",
            )
        raise HTTPException(
            503,
            "Email could not be sent. Try again in a few minutes.",
        )
    return {
        "ok": True,
        "resend_after_seconds": settings.OTP_RESEND_SECONDS,
    }


@router.post("/otp/verify")
def otp_verify(req: OtpVerifyRequest, db: Session = Depends(get_db)):
    """Validate code; returns signed access token + user profile for NextAuth."""
    user = verify_otp_and_get_user(db, str(req.email), req.code.strip())
    if not user:
        raise HTTPException(401, "Invalid or expired code.")
    return _token_payload(db, user)


@router.post("/test-login")
def auth_test_login(req: TestLoginRequest, db: Session = Depends(get_db)):
    """Server-only test sign-in for one allowlisted mailbox (NextAuth credentials).

    Requires AUTH_TEST_LOGIN_ENABLED, an allowlisted AUTH_TEST_LOGIN_EMAIL, and a matching
    non-empty AUTH_TEST_LOGIN_SECRET. An unset secret disables the endpoint rather than
    waiving the check, and it is refused outright in production.
    """
    if settings.is_production or not settings.AUTH_TEST_LOGIN_ENABLED:
        raise HTTPException(401, "Unauthorized")
    allowed = (settings.AUTH_TEST_LOGIN_EMAIL or "").strip()
    expected = (settings.AUTH_TEST_LOGIN_SECRET or "").strip()
    if not allowed or not expected:
        raise HTTPException(401, "Unauthorized")
    if normalize_email(str(req.email)) != normalize_email(allowed):
        raise HTTPException(401, "Unauthorized")
    if not _const_time_str_eq(req.secret.strip(), expected):
        raise HTTPException(401, "Unauthorized")

    email_norm = normalize_email(str(req.email))
    user = user_by_email_ci(db, email_norm)
    if not user:
        user = User(
            email=email_norm,
            name=(settings.AUTH_TEST_LOGIN_NAME or "Test user").strip() or "Test user",
            image=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return _token_payload(db, user)


@router.post("/bootstrap")
def bootstrap_user(
    req: BootstrapUserRequest,
    db: Session = Depends(get_db),
    x_internal_auth_secret: Optional[str] = Header(None),
):
    """Server-to-server user upsert after Google / NextAuth sign-in.

    Requires ``X-Internal-Auth-Secret``. Never call this from the browser.
    """
    _require_internal_auth_secret(x_internal_auth_secret)
    user = _upsert_user(
        db,
        email=str(req.email),
        name=req.name,
        image=req.image,
    )
    workspaces = _workspaces_for_user(db, user)
    user = _ensure_active_workspace(db, user, workspaces)
    return {
        **_token_payload(db, user),
        "active_workspace_id": user.active_workspace_id,
        "needs_onboarding": len(workspaces) == 0,
        "workspaces": [_workspace_json(w) for w in workspaces],
    }


@router.post("/sync")
def sync_user(
    req: SyncUserRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Refresh profile + workspaces for the Bearer-authenticated user."""
    changed = False
    if req.name and req.name != user.name:
        user.name = req.name
        changed = True
    if req.image is not None and req.image != user.image:
        user.image = req.image
        changed = True
    if changed:
        db.commit()
        db.refresh(user)

    workspaces = _workspaces_for_user(db, user)
    user = _ensure_active_workspace(db, user, workspaces)

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "image": user.image,
        "active_workspace_id": user.active_workspace_id,
        "needs_onboarding": len(workspaces) == 0,
        **_profile_billing_fields(db, user),
        "workspaces": [_workspace_json(w) for w in workspaces],
    }


@router.get("/me")
def get_me(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Get current user profile + workspaces."""
    workspaces = _workspaces_for_user(db, user)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "image": user.image,
        "active_workspace_id": user.active_workspace_id,
        "needs_onboarding": len(workspaces) == 0,
        **_profile_billing_fields(db, user),
        "workspaces": [_workspace_json(w) for w in workspaces],
    }


class DeleteAccountRequest(BaseModel):
    confirmation: str = Field(
        ...,
        description='Must be the exact phrase "DELETE" to confirm irreversible deletion.',
    )


@router.delete("/me")
def delete_me(
    body: DeleteAccountRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Permanently delete the signed-in user, all owned workspaces, uploads, and related data."""
    if (body.confirmation or "").strip() != "DELETE":
        raise HTTPException(
            400,
            'Type DELETE (all caps) in the confirmation field to permanently delete your account.',
        )
    delete_user_account(db, user)
    return {"ok": True, "deleted": True}
