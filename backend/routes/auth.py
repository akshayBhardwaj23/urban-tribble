from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models.models import User, Workspace
from services.otp_email import send_otp_email, verify_otp_and_get_user
from utils.email_norm import normalize_email, user_by_email_ci

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _profile_billing_fields(user: User) -> dict:
    end = user.subscription_current_period_end
    return {
        "subscription_plan": getattr(user, "subscription_plan", None) or "free",
        "subscription_renews_at": end.isoformat() if end else None,
    }


class SyncUserRequest(BaseModel):
    email: str
    name: Optional[str] = None
    image: Optional[str] = None


class OtpSendRequest(BaseModel):
    email: EmailStr


class OtpVerifyRequest(BaseModel):
    email: EmailStr
    code: str


@router.post("/otp/send")
def otp_send(req: OtpSendRequest, db: Session = Depends(get_db)):
    """Send a 6-digit sign-in code to the email (Resend)."""
    ok, detail = send_otp_email(db, str(req.email))
    if detail == "rate_limited_send":
        raise HTTPException(
            429,
            f"Wait {settings.OTP_RESEND_SECONDS} seconds before requesting another code.",
        )
    if not ok:
        if detail == "RESEND_API_KEY not configured":
            raise HTTPException(
                503,
                "Email is not configured: add RESEND_API_KEY to backend .env and restart the API (see https://resend.com).",
            )
        raise HTTPException(
            503,
            f"Email could not be sent. {detail}",
        )
    return {"ok": True}


@router.post("/otp/verify")
def otp_verify(req: OtpVerifyRequest, db: Session = Depends(get_db)):
    """Validate code; returns user profile for NextAuth Credentials (server-side)."""
    user = verify_otp_and_get_user(db, str(req.email), req.code.strip())
    if not user:
        raise HTTPException(401, "Invalid or expired code.")
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "image": user.image,
        **_profile_billing_fields(user),
    }


@router.post("/sync")
def sync_user(req: SyncUserRequest, db: Session = Depends(get_db)):
    """Called by frontend after NextAuth login. Creates user if new."""
    email_norm = normalize_email(req.email)
    user = user_by_email_ci(db, email_norm)

    if not user:
        user = User(email=email_norm, name=req.name, image=req.image)
        db.add(user)
        db.commit()
        db.refresh(user)

    else:
        if req.name and req.name != user.name:
            user.name = req.name
        if req.image is not None and req.image != user.image:
            user.image = req.image
        db.commit()
        db.refresh(user)

    workspaces = (
        db.query(Workspace)
        .filter(Workspace.owner_id == user.id)
        .order_by(Workspace.created_at.asc())
        .all()
    )

    if not user.active_workspace_id and workspaces:
        user.active_workspace_id = workspaces[0].id
        db.commit()
        db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "image": user.image,
        "active_workspace_id": user.active_workspace_id,
        "needs_onboarding": len(workspaces) == 0,
        **_profile_billing_fields(user),
        "workspaces": [
            {"id": w.id, "name": w.name, "created_at": w.created_at.isoformat()}
            for w in workspaces
        ],
    }


@router.get("/me")
def get_me(
    x_user_email: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Get current user profile + workspaces."""
    if not x_user_email:
        raise HTTPException(401, "Not authenticated")

    user = user_by_email_ci(db, x_user_email)
    if not user:
        raise HTTPException(404, "User not found")

    workspaces = (
        db.query(Workspace).filter(Workspace.owner_id == user.id).all()
    )

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "image": user.image,
        "active_workspace_id": user.active_workspace_id,
        **_profile_billing_fields(user),
        "workspaces": [
            {"id": w.id, "name": w.name, "created_at": w.created_at.isoformat()}
            for w in workspaces
        ],
    }
