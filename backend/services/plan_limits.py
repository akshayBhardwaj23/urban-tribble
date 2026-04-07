"""HTTP errors for subscription / plan enforcement (403 plan_limit)."""

from __future__ import annotations

from fastapi import HTTPException


def raise_plan_limit(plan: str, limit_key: str, message: str) -> None:
    raise HTTPException(
        status_code=403,
        detail={
            "code": "plan_limit",
            "plan": plan,
            "limit": limit_key,
            "message": message,
        },
    )
