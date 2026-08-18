"""Advisory LLM column role labelling — never blocks ingest, never parses data.

Input is the deterministic column profile only (names, dtypes, parse rates,
samples). Output is strict JSON with closed-enum roles. Any contradiction with
profile evidence is overridden by the deterministic result.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from services.column_profile import VALID_ROLES

logger = logging.getLogger(__name__)

_CACHE: dict[str, dict[str, Any]] = {}


def _cache_key(fingerprint: str, profiles: list[dict]) -> str:
    blob = json.dumps(
        {"fp": fingerprint, "names": [p.get("name") for p in profiles]},
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def propose_column_roles(
    profiles: list[dict[str, Any]],
    *,
    deterministic_roles: dict[str, str],
    schema_fingerprint: str,
    filename: str = "",
    user_description: str | None = None,
) -> dict[str, Any]:
    """Return {roles, meanings, source} with source in {llm, auto}.

    On any failure falls back to deterministic_roles.
    """
    key = _cache_key(schema_fingerprint, profiles)
    if key in _CACHE:
        cached = _CACHE[key]
        return {
            "roles": _validate_roles(cached.get("roles") or {}, profiles, deterministic_roles),
            "meanings": cached.get("meanings") or {},
            "source": cached.get("source", "llm"),
            "cached": True,
        }

    try:
        llm_out = _call_llm(profiles, filename=filename, user_description=user_description)
    except Exception as exc:
        logger.info("column_semantics LLM skipped/failed: %s", exc)
        return {
            "roles": dict(deterministic_roles),
            "meanings": {},
            "source": "auto",
            "cached": False,
        }

    if not llm_out:
        return {
            "roles": dict(deterministic_roles),
            "meanings": {},
            "source": "auto",
            "cached": False,
        }

    roles = _validate_roles(llm_out.get("roles") or {}, profiles, deterministic_roles)
    meanings = {
        k: str(v)[:200]
        for k, v in (llm_out.get("meanings") or {}).items()
        if k in {p["name"] for p in profiles}
    }
    result = {"roles": roles, "meanings": meanings, "source": "llm", "cached": False}
    _CACHE[key] = {"roles": roles, "meanings": meanings, "source": "llm"}
    return result


def _validate_roles(
    proposed: dict[str, Any],
    profiles: list[dict[str, Any]],
    deterministic: dict[str, str],
) -> dict[str, str]:
    by_name = {p["name"]: p for p in profiles}
    out = dict(deterministic)
    for name, role in proposed.items():
        if name not in by_name:
            continue
        role_s = str(role)
        if role_s not in VALID_ROLES:
            continue
        profile = by_name[name]
        # Hard gates: timeline requires date evidence
        if role_s == "timeline" and float(profile.get("date_parse_rate") or 0) < 0.95:
            if not str(profile.get("dtype", "")).startswith("datetime"):
                continue  # reject LLM timeline without evidence
        # amount roles require numeric evidence
        if role_s in ("amount_inflow", "amount_outflow", "quantity"):
            if float(profile.get("numeric_parse_rate") or 0) < 0.5 and not str(
                profile.get("dtype", "")
            ).startswith(("int", "float")):
                continue
        out[name] = role_s
    return out


def _call_llm(
    profiles: list[dict[str, Any]],
    *,
    filename: str,
    user_description: str | None,
) -> dict[str, Any] | None:
    from services import llm_client

    if not llm_client.is_configured():
        return None

    # Compact profile payload — never send full dataset. Drop raw cell samples
    # that could inject instructions; stats + names are enough for role labeling.
    compact = []
    for p in profiles:
        compact.append(
            {
                "name": p.get("name"),
                "dtype": p.get("dtype"),
                "null_rate": p.get("null_rate"),
                "distinct_ratio": p.get("distinct_ratio"),
                "numeric_parse_rate": p.get("numeric_parse_rate"),
                "date_parse_rate": p.get("date_parse_rate"),
            }
        )

    system = (
        "You assign semantic roles to spreadsheet columns. "
        "Return ONLY valid JSON: {\"roles\": {\"col\": \"role\"}, \"meanings\": {\"col\": \"one sentence\"}}. "
        f"Roles must be one of: {sorted(VALID_ROLES)}. "
        "timeline = a true time axis for charts (not durations like Delivery_Days). "
        "amount_inflow = money coming in; amount_outflow = costs/expenses. "
        "Do not invent columns. Prefer dimension for categories, quantity for counts."
    )
    user = json.dumps(
        {
            "filename": filename,
            "description": (user_description or "")[:500],
            "columns": compact,
        }
    )

    return llm_client.chat_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        purpose="column_semantics",
        temperature=0,
        model=None,
    )
