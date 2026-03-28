from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# IDs match frontend DatasetClassificationId
CLASSIFICATIONS: Dict[str, str] = {
    "sales_data": "Sales data",
    "expenses": "Expenses",
    "marketing_campaigns": "Marketing campaigns",
    "customer_data": "Customer data",
    "inventory": "Inventory",
    "tax_accounting": "Tax / accounting",
    "unknown_dataset": "General dataset",
}

ALLOWED_CLASSIFICATION_IDS = frozenset(CLASSIFICATIONS.keys())

FILENAME_DESC_PATTERNS: List[Tuple[str, List[str]]] = [
    ("expenses", [r"expense", r"spend", r"vendor", r"payroll", r"reimburs", r"invoice", r"ap\b", r"accounts.?payable"]),
    ("marketing_campaigns", [r"campaign", r"marketing", r"cpc", r"ctr", r"impression", r"ad.?spend", r"ads?\b"]),
    ("customer_data", [r"customer", r"crm", r"contact", r"subscriber", r"lead"]),
    ("inventory", [r"inventory", r"sku", r"stock", r"warehouse", r"fulfill"]),
    ("tax_accounting", [r"tax", r"gst", r"vat", r"ledger", r"journal", r"gl\b", r"accrual", r"ebit"]),
    ("sales_data", [r"sales", r"revenue", r"order", r"transaction", r"pipeline", r"deal"]),
]


def _text_blob(filename: str, user_description: Optional[str]) -> str:
    parts = [filename or "", user_description or ""]
    return " ".join(parts).lower()


def _score_from_text(blob: str) -> Dict[str, int]:
    scores: Dict[str, int] = {k: 0 for k in CLASSIFICATIONS if k != "unknown_dataset"}
    for kind, patterns in FILENAME_DESC_PATTERNS:
        for pat in patterns:
            if re.search(pat, blob, re.I):
                scores[kind] = scores.get(kind, 0) + 2
                break
    return scores


def _column_blob(columns: List[str]) -> str:
    return " ".join(str(c).lower() for c in columns)


def _score_from_columns(col_blob: str, metadata: Dict[str, Any]) -> Dict[str, int]:
    scores: Dict[str, int] = {k: 0 for k in CLASSIFICATIONS if k != "unknown_dataset"}

    if metadata.get("date_columns") and metadata.get("revenue_columns"):
        scores["sales_data"] += 3

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


def _merge_scores(a: Dict[str, int], b: Dict[str, int]) -> Dict[str, int]:
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
    metadata: Dict[str, Any],
    clean_report: Dict[str, Any],
    columns: List[str],
) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []
    steps = clean_report.get("steps") or []

    for step in steps:
        s = str(step).lower()
        if "duplicate" in s:
            flags.append(
                {
                    "kind": "info",
                    "code": "duplicates_removed",
                    "message": "Duplicate rows were removed so totals stay reliable.",
                }
            )
        if "missing" in s:
            flags.append(
                {
                    "kind": "warning",
                    "code": "missing_values",
                    "message": "Some cells were empty—we filled or flagged gaps where it mattered.",
                }
            )
        if "date format" in s or "converted" in s and "date" in s:
            flags.append(
                {
                    "kind": "info",
                    "code": "dates_normalized",
                    "message": "Date columns were recognized and normalized for trends.",
                }
            )

    date_cols = metadata.get("date_columns") or []
    rev_cols = metadata.get("revenue_columns") or []
    if not date_cols and (rev_cols or (metadata.get("numeric_columns") or [])):
        flags.append(
            {
                "kind": "warning",
                "code": "no_date_column",
                "message": "No clear date column yet—trend charts may need you to point us to one later.",
            }
        )

    if not rev_cols and not (metadata.get("numeric_columns") or []):
        flags.append(
            {
                "kind": "warning",
                "code": "no_amount_column",
                "message": "We did not find an obvious amount column—KPIs may need a quick mapping.",
            }
        )

    if len(columns) <= 2:
        flags.append(
            {
                "kind": "warning",
                "code": "narrow_schema",
                "message": "Very few columns—if this is a fragment, consider joining with another file.",
            }
        )

    # Deduplicate by code
    seen: set[str] = set()
    unique: List[Dict[str, str]] = []
    for f in flags:
        c = f.get("code", "")
        if c in seen:
            continue
        seen.add(c)
        unique.append(f)
    return unique


def _interpretations(metadata: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    dc = metadata.get("date_columns") or []
    rc = metadata.get("revenue_columns") or []
    cc = metadata.get("category_columns") or []
    if dc:
        lines.append(f"Timeline fields: {', '.join(dc[:5])}{'…' if len(dc) > 5 else ''}")
    if rc:
        lines.append(f"Amount-style fields: {', '.join(rc[:5])}{'…' if len(rc) > 5 else ''}")
    if cc:
        lines.append(f"Breakdown fields: {', '.join(cc[:5])}{'…' if len(cc) > 5 else ''}")
    if not lines:
        lines.append("Columns are mostly text or numeric—we will infer roles as you explore.")
    return lines


def build_ingestion_profile(
    filename: str,
    user_description: Optional[str],
    metadata: Dict[str, Any],
    clean_report: Dict[str, Any],
    columns: List[str],
) -> Dict[str, Any]:
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
            "category_columns": list(metadata.get("category_columns") or []),
            "numeric_columns": list(metadata.get("numeric_columns") or []),
            "text_columns": list(metadata.get("text_columns") or []),
        },
        "interpretations": interpretations,
        "flags": flags,
    }
