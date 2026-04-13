"""Razorpay Subscriptions: checkout creation and webhook-driven plan updates."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import razorpay
from razorpay.errors import SignatureVerificationError
from sqlalchemy.orm import Session

from config import settings
from models.models import ProcessedBillingWebhookEvent, User

logger = logging.getLogger(__name__)

PLAN_TIERS = frozenset({"starter", "pro"})


def razorpay_configured() -> bool:
    return bool(
        settings.RAZORPAY_KEY_ID.strip()
        and settings.RAZORPAY_KEY_SECRET.strip()
        and settings.RAZORPAY_PLAN_STARTER.strip()
        and settings.RAZORPAY_PLAN_PRO.strip()
    )


def webhook_configured() -> bool:
    return bool(settings.RAZORPAY_WEBHOOK_SECRET.strip())


def _client() -> razorpay.Client:
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _plan_id_for_tier(tier: str) -> str:
    if tier == "starter":
        return settings.RAZORPAY_PLAN_STARTER.strip()
    if tier == "pro":
        return settings.RAZORPAY_PLAN_PRO.strip()
    raise ValueError("tier must be starter or pro")


def _tier_from_razorpay_plan_id(plan_id: Optional[str]) -> Optional[str]:
    if not plan_id:
        return None
    pid = plan_id.strip()
    if pid == settings.RAZORPAY_PLAN_STARTER.strip():
        return "starter"
    if pid == settings.RAZORPAY_PLAN_PRO.strip():
        return "pro"
    return None


def _normalize_subscription_short_url(short_url: str) -> str:
    """Razorpay sometimes returns ``api.razorpay.com`` ``short_url`` values that render
    *Hosted page is not available* in a normal browser session. The subscription auth UI
    is served from ``checkout.razorpay.com`` — swap the host when the path is a checkout link.
    """
    u = short_url.strip()
    parsed = urlparse(u)
    if parsed.netloc == "api.razorpay.com" and "/subscriptions/" in parsed.path:
        return urlunparse(parsed._replace(netloc="checkout.razorpay.com"))
    return u


def _ensure_customer(db: Session, user: User) -> str:
    if user.billing_customer_id:
        return user.billing_customer_id
    client = _client()
    payload: dict[str, Any] = {
        "email": user.email,
        "fail_existing": 0,
        "notes": {
            "clarus_user_id": str(user.id),
        },
    }
    if user.name:
        payload["name"] = user.name
    cust = client.customer.create(payload)
    cid = cust.get("id")
    if not cid:
        raise RuntimeError("Razorpay customer.create returned no id")
    user.billing_customer_id = cid
    user.billing_provider = "razorpay"
    db.add(user)
    db.flush()
    return cid


def create_subscription_checkout(db: Session, user: User, tier: str) -> dict[str, str]:
    if tier not in PLAN_TIERS:
        raise ValueError("Invalid tier")
    if not razorpay_configured():
        raise RuntimeError("Razorpay is not configured")

    plan_id = _plan_id_for_tier(tier)
    # Ensure Razorpay customer exists for support / future invoices (not required on subscription.create).
    _ensure_customer(db, user)
    client = _client()
    now = int(time.time())
    expire_by = now + 7 * 86400
    total = max(1, int(settings.RAZORPAY_SUBSCRIPTION_TOTAL_COUNT))

    # Do not pass customer_id here: linking a pre-created customer to a new subscription before
    # mandate auth can trigger Razorpay "issue with the merchant" in Standard Checkout for some
    # accounts. Customer is attached after authorisation; webhooks still resolve user via `notes`.
    sub = client.subscription.create(
        {
            "plan_id": plan_id,
            "total_count": total,
            "quantity": 1,
            "customer_notify": True,
            "expire_by": expire_by,
            "notify_info": {
                "notify_email": user.email,
            },
            "notes": {
                "clarus_user_id": str(user.id),
                "clarus_plan": str(tier),
            },
        }
    )
    raw_short = sub.get("short_url")
    sub_id = sub.get("id")
    if not raw_short or not sub_id:
        raise RuntimeError("Razorpay subscription.create missing short_url or id")
    short_url = _normalize_subscription_short_url(str(raw_short))
    if short_url != raw_short:
        logger.info("Normalized Razorpay subscription short_url host for browser checkout")

    user.billing_subscription_id = sub_id
    user.billing_provider = "razorpay"
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "short_url": str(short_url),
        "subscription_id": str(sub_id),
        # Public key — required for Razorpay Standard Checkout (subscription auth); do not use short_url redirect alone.
        "key_id": settings.RAZORPAY_KEY_ID.strip(),
    }


def verify_and_parse_webhook(raw_body: bytes, signature: str) -> dict[str, Any]:
    if not webhook_configured():
        raise RuntimeError("Webhook secret not configured")
    body_str = raw_body.decode("utf-8")
    client = _client()
    client.utility.verify_webhook_signature(
        body_str,
        signature,
        settings.RAZORPAY_WEBHOOK_SECRET.strip(),
    )
    return json.loads(body_str)


def _subscription_entity(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    p = payload.get("payload")
    if not isinstance(p, dict):
        return None
    sub = p.get("subscription")
    if not isinstance(sub, dict):
        return None
    ent = sub.get("entity")
    return ent if isinstance(ent, dict) else None


def _resolve_user(db: Session, entity: dict[str, Any]) -> Optional[User]:
    notes = entity.get("notes")
    uid: Optional[str] = None
    if isinstance(notes, dict):
        raw = notes.get("clarus_user_id")
        if raw is not None:
            uid = str(raw).strip() or None
    if uid:
        u = db.query(User).filter(User.id == uid).first()
        if u:
            return u
    cust_id = entity.get("customer_id")
    if cust_id:
        u = (
            db.query(User)
            .filter(User.billing_customer_id == str(cust_id))
            .first()
        )
        if u:
            return u
    sub_id = entity.get("id")
    if sub_id:
        u = (
            db.query(User)
            .filter(User.billing_subscription_id == str(sub_id))
            .first()
        )
        if u:
            return u
    return None


def _apply_period_end(user: User, entity: dict[str, Any]) -> None:
    ce = entity.get("current_end")
    if ce is None:
        return
    try:
        user.subscription_current_period_end = datetime.utcfromtimestamp(int(ce))
    except (TypeError, ValueError, OSError):
        pass


def _resolve_tier(entity: dict[str, Any]) -> Optional[str]:
    notes = entity.get("notes")
    if isinstance(notes, dict):
        raw = notes.get("clarus_plan")
        if raw is not None:
            t = str(raw).strip().lower()
            if t in PLAN_TIERS:
                return t
    return _tier_from_razorpay_plan_id(entity.get("plan_id"))


def apply_subscription_webhook(db: Session, data: dict[str, Any], event_id: str) -> None:
    if (
        db.query(ProcessedBillingWebhookEvent)
        .filter(ProcessedBillingWebhookEvent.event_id == event_id)
        .first()
    ):
        return

    event_type = data.get("event")
    entity = _subscription_entity(data)
    if not entity:
        db.add(ProcessedBillingWebhookEvent(event_id=event_id))
        db.commit()
        return

    user = _resolve_user(db, entity)
    if not user:
        logger.warning("Razorpay webhook: no user for subscription event %s", event_type)
        db.add(ProcessedBillingWebhookEvent(event_id=event_id))
        db.commit()
        return

    status = (entity.get("status") or "").lower()
    sub_id = entity.get("id")
    if sub_id:
        user.billing_subscription_id = str(sub_id)
    user.billing_provider = "razorpay"
    _apply_period_end(user, entity)

    upgrade_events = frozenset(
        {
            "subscription.activated",
            "subscription.charged",
            "subscription.resumed",
        }
    )
    downgrade_events = frozenset(
        {
            "subscription.cancelled",
            "subscription.completed",
            "subscription.halted",
            "subscription.expired",
        }
    )

    if event_type in upgrade_events:
        if status == "active":
            tier = _resolve_tier(entity)
            if tier:
                user.subscription_plan = tier
        db.add(user)
        db.add(ProcessedBillingWebhookEvent(event_id=event_id))
        db.commit()
        return

    if event_type in downgrade_events:
        user.subscription_plan = "free"
        user.billing_subscription_id = None
        user.subscription_current_period_end = None
        db.add(user)
        db.add(ProcessedBillingWebhookEvent(event_id=event_id))
        db.commit()
        return

    if event_type == "subscription.paused":
        db.add(user)
        db.add(ProcessedBillingWebhookEvent(event_id=event_id))
        db.commit()
        return

    db.add(user)
    db.add(ProcessedBillingWebhookEvent(event_id=event_id))
    db.commit()


def process_webhook_request(db: Session, raw_body: bytes, signature: str, event_id_header: Optional[str]) -> None:
    try:
        data = verify_and_parse_webhook(raw_body, signature)
    except SignatureVerificationError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError, RuntimeError) as e:
        raise ValueError(str(e)) from e

    event_id = event_id_header or data.get("id")
    if not event_id:
        raise ValueError("Missing webhook event id")

    apply_subscription_webhook(db, data, str(event_id))
