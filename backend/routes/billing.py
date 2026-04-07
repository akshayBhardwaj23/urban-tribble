from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from razorpay.errors import SignatureVerificationError
from sqlalchemy.orm import Session

from database import get_db
from deps import require_user
from models.models import User
from services.razorpay_service import (
    create_subscription_checkout,
    process_webhook_request,
    razorpay_configured,
    webhook_configured,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])


class RazorpayCheckoutBody(BaseModel):
    tier: Literal["starter", "pro"] = Field(..., description="Subscription tier to purchase")


@router.post("/razorpay/checkout")
def razorpay_checkout(
    body: RazorpayCheckoutBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Create a Razorpay subscription and return the hosted `short_url` for payment."""
    if not razorpay_configured():
        raise HTTPException(
            503,
            "Billing is not configured. Set RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, "
            "RAZORPAY_PLAN_STARTER, and RAZORPAY_PLAN_PRO in the API environment.",
        )
    try:
        out = create_subscription_checkout(db, user, body.tier)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Razorpay error: {e!s}") from e
    return out


@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Razorpay webhooks — raw body + HMAC. Configure URL in Razorpay Dashboard."""
    if not razorpay_configured() or not webhook_configured():
        raise HTTPException(
            503,
            "Webhook handler disabled: configure RAZORPAY_KEY_* and RAZORPAY_WEBHOOK_SECRET.",
        )
    raw = await request.body()
    sig = (
        request.headers.get("X-Razorpay-Signature")
        or request.headers.get("x-razorpay-signature")
        or ""
    )
    if not sig:
        raise HTTPException(400, "Missing X-Razorpay-Signature")
    event_id: Optional[str] = request.headers.get("X-Razorpay-Event-Id") or request.headers.get(
        "x-razorpay-event-id"
    )
    try:
        process_webhook_request(db, raw, sig, event_id)
    except SignatureVerificationError:
        raise HTTPException(400, "Invalid webhook signature") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}
