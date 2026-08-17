from __future__ import annotations

import re
from typing import Any

# IDs match frontend DatasetClassificationId
CLASSIFICATIONS: dict[str, str] = {
    "sales_data": "Sales data",
    "expenses": "Expenses",
    "marketing_campaigns": "Marketing campaigns",
    "customer_data": "Customer data",
    "inventory": "Inventory",
    "tax_accounting": "Tax / accounting",
    "unknown_dataset": "General dataset",
}

ALLOWED_CLASSIFICATION_IDS = frozenset(CLASSIFICATIONS.keys())

FILENAME_DESC_PATTERNS: list[tuple[str, list[str]]] = [
    ("expenses", [r"expense", r"spend", r"vendor", r"payroll", r"reimburs", r"invoice", r"ap\b", r"accounts.?payable"]),
    ("marketing_campaigns", [r"campaign", r"marketing", r"cpc", r"ctr", r"impression", r"ad.?spend", r"ads?\b"]),
    ("customer_data", [r"customer", r"crm", r"contact", r"subscriber", r"lead"]),
    ("inventory", [r"inventory", r"sku", r"stock", r"warehouse", r"fulfill"]),
    ("tax_accounting", [r"tax", r"gst", r"vat", r"ledger", r"journal", r"gl\b", r"accrual", r"ebit"]),
    ("sales_data", [r"sales", r"revenue", r"order", r"transaction", r"pipeline", r"deal"]),
]


def _text_blob(filename: str, user_description: str | None) -> str:
    parts = [filename or "", user_description or ""]
    return " ".join(parts).lower()


def _score_from_text(blob: str) -> dict[str, int]:
    scores: dict[str, int] = {k: 0 for k in CLASSIFICATIONS if k != "unknown_dataset"}
    for kind, patterns in FILENAME_DESC_PATTERNS:
        for pat in patterns:
            if re.search(pat, blob, re.I):
                scores[kind] = scores.get(kind, 0) + 2
                break
    return scores


def _column_blob(columns: list[str]) -> str:
    return " ".join(str(c).lower() for c in columns)


def _score_from_columns(col_blob: str, metadata: dict[str, Any]) -> dict[str, int]:
    scores: dict[str, int] = {k: 0 for k in CLASSIFICATIONS if k != "unknown_dataset"}

    if metadata.get("date_columns") and metadata.get("revenue_columns"):
        scores["sales_data"] += 3

    if metadata.get("expense_columns"):
        scores["expenses"] += 4
        scores["sales_data"] -= 1

    rev_cols = " ".join(metadata.get("revenue_columns") or [])
    if re.search(r"expense|cost|spend|budget|payment|fee", rev_cols, re.I):
        scores["expenses"] += 4
        scores["sales_data"] -= 2

    if re.search(r"campaign|impression|click|cpc|ctr|channel|ad\b", col_blob, re.I):
        scores["marketing_campaigns"] += 4

    if re.search(
        r"customer|client|email|phone|address|user_id|account_id|subscriber",
        col_blob,
        re.I,
    ):
        scores["customer_data"] += 3

    if re.search(r"sku|stock|quantity|on_hand|warehouse|reorder|unit_cost", col_blob, re.I):
        scores["inventory"] += 4

    if re.search(r"tax|gst|vat|debit|credit|ledger|journal|fiscal|period", col_blob, re.I):
        scores["tax_accounting"] += 3

    if scores["sales_data"] < 0:
        scores["sales_data"] = 0

    return scores


def _merge_scores(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return out


def _confidence(best: int, second: int) -> str:
    if best >= 6 and best - second >= 3:
        return "high"
    if best >= 3 and best - second >= 2:
        return "medium"
    return "low"


def _flags(
    metadata: dict[str, Any],
    clean_report: dict[str, Any],
    columns: list[str],
) -> list[dict[str, str]]:
    """Factual flags — observations, not reassurances."""
    flags: list[dict[str, str]] = []

    # Prefer structured flags from the cleaner
    for f in clean_report.get("flags") or []:
        if isinstance(f, dict) and f.get("code"):
            flags.append(
                {
                    "kind": str(f.get("kind") or "info"),
                    "code": str(f["code"]),
                    "message": str(f.get("message") or f["code"]),
                }
            )

    # Also scan structured_steps / legacy string steps for gaps the cleaner
    # may not have flagged explicitly
    structured = clean_report.get("structured_steps") or []
    steps = clean_report.get("steps") or []
    step_texts = []
    for s in structured:
        if isinstance(s, dict):
            step_texts.append(str(s.get("message") or ""))
        else:
            step_texts.append(str(s))
    for s in steps:
        if isinstance(s, str):
            step_texts.append(s)

    codes = {f.get("code") for f in flags}

    for text in step_texts:
        low = text.lower()
        if "duplicate" in low and "duplicates_detected" not in codes and "duplicates_removed" not in codes:
            flags.append(
                {
                    "kind": "info",
                    "code": "duplicates_detected",
                    "message": text if text else "Duplicate rows were detected.",
                }
            )
            codes.add("duplicates_detected")
        if "missing" in low and "missing_values" not in codes:
            flags.append(
                {
                    "kind": "warning",
                    "code": "missing_values",
                    "message": text
                    if text
                    else "Some cells are empty; values were left blank.",
                }
            )
            codes.add("missing_values")
        if ("date" in low and "converted" in low) and "dates_normalized" not in codes:
            flags.append(
                {
                    "kind": "info",
                    "code": "dates_normalized",
                    "message": text if text else "Date columns were normalized.",
                }
            )
            codes.add("dates_normalized")

    date_cols = metadata.get("date_columns") or []
    rev_cols = metadata.get("revenue_columns") or []
    exp_cols = metadata.get("expense_columns") or []
    if not date_cols and (rev_cols or exp_cols or (metadata.get("numeric_columns") or [])):
        flags.append(
            {
                "kind": "warning",
                "code": "no_date_column",
                "message": "No timeline column detected — trend charts need you to pick one.",
            }
        )

    if not rev_cols and not exp_cols and not (metadata.get("numeric_columns") or []):
        flags.append(
            {
                "kind": "warning",
                "code": "no_amount_column",
                "message": "No amount column detected — KPIs need a mapping.",
            }
        )

    if len(columns) <= 2:
        flags.append(
            {
                "kind": "warning",
                "code": "narrow_schema",
                "message": "Very few columns — if this is a fragment, consider joining another file.",
            }
        )

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for f in flags:
        c = f.get("code", "")
        if c in seen:
            continue
        seen.add(c)
        unique.append(f)
    return unique


def _interpretations(metadata: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    dc = metadata.get("date_columns") or []
    rc = metadata.get("revenue_columns") or []
    ec = metadata.get("expense_columns") or []
    cc = metadata.get("category_columns") or []
    if dc:
        lines.append(f"Timeline fields: {', '.join(dc[:5])}{'…' if len(dc) > 5 else ''}")
    if rc:
        lines.append(f"Amount (inflow) fields: {', '.join(rc[:5])}{'…' if len(rc) > 5 else ''}")
    if ec:
        lines.append(f"Amount (outflow) fields: {', '.join(ec[:5])}{'…' if len(ec) > 5 else ''}")
    if cc:
        lines.append(f"Breakdown fields: {', '.join(cc[:5])}{'…' if len(cc) > 5 else ''}")
    if not lines:
        lines.append("Columns are mostly text or numeric — we will infer roles as you explore.")
    return lines


def build_ingestion_profile(
    filename: str,
    user_description: str | None,
    metadata: dict[str, Any],
    clean_report: dict[str, Any],
    columns: list[str],
) -> dict[str, Any]:
    blob = _text_blob(filename, user_description)
    col_blob = _column_blob(columns)
    scores = _merge_scores(_score_from_text(blob), _score_from_columns(col_blob, metadata))

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    best_id, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    if best_score == 0:
        chosen = "unknown_dataset"
        conf = "low"
    else:
        chosen = best_id
        conf = _confidence(best_score, second_score)

    flags = _flags(metadata, clean_report, columns)
    interpretations = _interpretations(metadata)

    return {
        "classification": {
            "id": chosen,
            "label": CLASSIFICATIONS.get(chosen, CLASSIFICATIONS["unknown_dataset"]),
            "confidence": conf,
        },
        "column_highlights": {
            "date_columns": list(metadata.get("date_columns") or []),
            "revenue_columns": list(metadata.get("revenue_columns") or []),
            "expense_columns": list(metadata.get("expense_columns") or []),
            "category_columns": list(metadata.get("category_columns") or []),
            "numeric_columns": list(metadata.get("numeric_columns") or []),
            "text_columns": list(metadata.get("text_columns") or []),
        },
        "interpretations": interpretations,
        "flags": flags,
    }
