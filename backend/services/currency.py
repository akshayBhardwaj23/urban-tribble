"""Currency resolution and formatting.

Currency is a workspace property rather than a build-time constant. When a
workspace has not chosen one, DEFAULT_CURRENCY applies.
"""

from __future__ import annotations

from typing import Any, Optional

from config import settings

SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AUD": "A$",
    "CAD": "C$",
    "SGD": "S$",
    "AED": "AED ",
    "JPY": "¥",
}

SUPPORTED = tuple(SYMBOLS)
SUPPORTED_CURRENCIES = frozenset(SYMBOLS)


def currency_symbol(code: Optional[str]) -> str:
    return SYMBOLS[normalize_currency(code)].strip()


def normalize_currency(code: Optional[str]) -> str:
    candidate = (code or "").strip().upper()
    if candidate in SYMBOLS:
        return candidate
    fallback = (getattr(settings, "DEFAULT_CURRENCY", "INR") or "INR").strip().upper()
    return fallback if fallback in SYMBOLS else "INR"


def workspace_currency(workspace: Any) -> str:
    """Currency for a workspace, falling back to the configured default."""
    return normalize_currency(getattr(workspace, "currency", None))


def format_money(value: Any, currency: Optional[str] = None) -> str:
    code = normalize_currency(currency)
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return f"{code} —"
    symbol = SYMBOLS[code]
    sign = "-" if amount < 0 else ""
    body = f"{abs(amount):,.2f}"
    if symbol.endswith(" "):
        return f"{sign}{symbol}{body}"
    return f"{sign}{symbol}{body}"


def format_money_compact(value: Any, currency: Optional[str] = None) -> str:
    """Short form for tiles: 1.2M, 340.5K."""
    code = normalize_currency(currency)
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return f"{SYMBOLS[code]}—"
    symbol = SYMBOLS[code]
    sign = "-" if amount < 0 else ""
    a = abs(amount)
    for cutoff, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if a >= cutoff:
            return f"{sign}{symbol}{a / cutoff:.1f}{suffix}"
    return f"{sign}{symbol}{a:,.2f}"
