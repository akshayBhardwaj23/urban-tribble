"""Workspace chat helpers: source catalog, grains, and safe cross-source answers."""

from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

DataframeRow = tuple[str, pd.DataFrame, dict[str, Any], Optional[str]]


def friendly_source_name(filename: str) -> str:
    """Turn 'monthly_revenue_and_profit_by_channel.xlsx' into a readable label."""
    base = filename.rsplit(".", 1)[0] if "." in filename else filename
    base = base.replace("_", " ").replace("-", " ")
    return " ".join(w.capitalize() for w in base.split() if w)


def _slug(name: str) -> str:
    import re as _re

    s = name.rsplit(".", 1)[0].lower()
    s = _re.sub(r"[^a-z0-9_]", "_", s)
    return _re.sub(r"_+", "_", s).strip("_") or "data"


def _infer_grain(name: str, df: pd.DataFrame, schema: dict[str, Any]) -> str:
    cols = {str(c).lower() for c in df.columns}
    n = name.lower()
    if "order_id" in cols or ("order_date" in cols and "case_name" in cols):
        return "transaction-level orders"
    if "campaign" in cols or "attributed_revenue" in cols or "spend_inr" in cols:
        return "marketing campaigns (attributed revenue)"
    if "sku" in cols or "cogs" in n:
        return "product / SKU level"
    if "customer_id" in cols and "lifetime" in cols:
        return "customer accounts"
    if "month" in cols and ("channel" in cols or "sales_channel" in cols):
        return "monthly by channel"
    if "month" in cols or "date" in cols:
        return "time series"
    if "opportunity" in cols or "pipeline" in n:
        return "sales pipeline"
    return "tabular export"


def _pick_primary_revenue_col(df: pd.DataFrame, schema: dict[str, Any]) -> Optional[str]:
    candidates = [c for c in (schema.get("revenue_columns") or []) if c in df.columns]
    if not candidates:
        return None

    def score(col: str) -> tuple[int, str]:
        low = col.lower()
        penalty = 0
        if "budget" in low or "spend" in low and "revenue" not in low:
            penalty += 10
        if "fee" in low and "revenue" not in low:
            penalty += 5
        if "order_count" in low or low.endswith("_count"):
            penalty += 8
        if "revenue" in low or "sales" in low or "gross" in low:
            penalty -= 5
        if "net" in low:
            penalty -= 1
        return (penalty, col)

    return min(candidates, key=score)


def _numeric_sum(df: pd.DataFrame, col: str) -> float:
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.fillna(0).sum())


def _date_range_label(df: pd.DataFrame, schema: dict[str, Any]) -> Optional[str]:
    date_cols = schema.get("date_columns") or []
    for dc in date_cols:
        if dc not in df.columns:
            continue
        ts = pd.to_datetime(df[dc], errors="coerce").dropna()
        if ts.empty:
            continue
        return f"{ts.min().date()} – {ts.max().date()}"
    return None


def build_source_catalog(
    dataframes: list[DataframeRow],
) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for name, df, schema, desc in dataframes:
        rev_col = _pick_primary_revenue_col(df, schema)
        catalog.append(
            {
                "file_name": name,
                "label": friendly_source_name(name),
                "slug": _slug(name),
                "rows": len(df),
                "grain": _infer_grain(name, df, schema),
                "revenue_column": rev_col,
                "revenue_total": _numeric_sum(df, rev_col) if rev_col else None,
                "date_range": _date_range_label(df, schema),
                "description": (desc or "").strip() or None,
                "has_revenue": rev_col is not None,
            }
        )
    return catalog


def _format_inr(value: float) -> str:
    return f"INR {value:,.2f}"


def catalog_with_revenue(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in catalog if c.get("has_revenue") and c.get("revenue_total") is not None]


def _catalog_with_revenue(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return catalog_with_revenue(catalog)


def _pick_canonical_revenue_source(catalog: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Best single source for company-level revenue (avoid double-counting)."""
    with_rev = _catalog_with_revenue(catalog)
    if not with_rev:
        return None

    def rank(c: dict[str, Any]) -> tuple[int, float]:
        grain = str(c.get("grain", "")).lower()
        label = str(c.get("label", "")).lower()
        score = 50
        if "monthly by channel" in grain:
            score = 0
        elif "time series" in grain and "month" in label:
            score = 5
        elif "product" in grain:
            score = 15
        elif "transaction" in grain:
            score = 25
        elif "marketing" in grain or "campaign" in grain:
            score = 40
        elif "customer" in grain:
            score = 60
        total = float(c.get("revenue_total") or 0)
        return (score, -total)

    return min(with_rev, key=rank)


_REVENUE_TOTAL_RE = re.compile(
    r"\b(total|sum|overall|aggregate)\b.*\b(revenue|sales|turnover)\b"
    r"|\b(revenue|sales)\b.*\b(across|all)\b.*\b(source|file|dataset|workspace)",
    re.I,
)
_SOURCES_COUNT_RE = re.compile(
    r"\bhow many\b.*\b(source|file|dataset)",
    re.I,
)
_REVENUE_BY_SOURCE_RE = re.compile(
    r"\b(which|what)\b.*\b(source|file|dataset).*\b(sale|sales|revenue)",
    re.I,
)
_LIST_SOURCES_RE = re.compile(
    r"\b(what|which|list)\b.*\b(source|file|dataset)",
    re.I,
)
_CANONICAL_RE = re.compile(
    r"\b(best|canonical|primary|official|true)\b.*\b(revenue|sales)\b"
    r"|\b(revenue|sales)\b.*\b(one source|single source|without double)",
    re.I,
)


def try_workspace_shortcut(
    question: str,
    dataframes: list[DataframeRow],
) -> Optional[dict[str, Any]]:
    """
    Deterministic answers for common workspace questions (no double-counting).
    Returns {answer, chart_data} or None to fall through to LLM.
    """
    if not dataframes:
        return None

    catalog = build_source_catalog(dataframes)
    q = question.strip()
    ql = q.lower()

    if _SOURCES_COUNT_RE.search(q) or (
        "how many" in ql and "source" in ql and "revenue" not in ql
    ):
        with_rev = _catalog_with_revenue(catalog)
        lines = [
            f"You have {len(catalog)} imported sources in this workspace "
            f"({sum(c['rows'] for c in catalog):,} rows total).",
            "",
            "Sources:",
        ]
        for c in catalog:
            rev_note = (
                f" - primary metric: {_format_inr(c['revenue_total'])} "
                f"({c['revenue_column']})"
                if c.get("has_revenue")
                else " - no revenue column detected"
            )
            lines.append(
                f"• {c['label']} ({c['rows']:,} rows, {c['grain']}){rev_note}"
            )
        lines.extend(
            [
                "",
                f"{len(with_rev)} of {len(catalog)} sources have a revenue-style column. "
                "They measure different grains - do not add those totals together.",
            ]
        )
        return {"answer": "\n".join(lines), "chart_data": chart_revenue_by_source(with_rev)}

    if _REVENUE_BY_SOURCE_RE.search(q) or (
        "each source" in ql and ("revenue" in ql or "sale" in ql)
    ):
        return _answer_revenue_by_source(catalog)

    if _CANONICAL_RE.search(q):
        return _answer_canonical_revenue(catalog)

    if _REVENUE_TOTAL_RE.search(q) or (
        "total revenue" in ql and ("all" in ql or "across" in ql or "workspace" in ql)
    ):
        return _answer_revenue_by_source(
            catalog,
            headline=(
                "There is no single “total revenue” number across all sources - "
                "they overlap (orders, monthly rollups, ads, SKUs). "
                "Here is revenue per source (one primary column each):"
            ),
        )

    if _LIST_SOURCES_RE.search(q) and len(ql) < 80:
        return try_workspace_shortcut(
            "how many sources are in this workspace", dataframes
        )

    return None


def _answer_revenue_by_source(
    catalog: list[dict[str, Any]],
    *,
    headline: Optional[str] = None,
) -> dict[str, Any]:
    with_rev = _catalog_with_revenue(catalog)
    if not with_rev:
        return {
            "answer": (
                "None of your imported sources have a column Snaptix recognizes as revenue. "
                "Open a source and confirm amount/revenue columns in the schema."
            ),
            "chart_data": None,
        }

    lines = [
        headline
        or "Here is one primary revenue metric per source (do not sum these - grains overlap):",
        "",
    ]
    for c in sorted(with_rev, key=lambda x: float(x["revenue_total"]), reverse=True):
        dr = f" · dates {c['date_range']}" if c.get("date_range") else ""
        lines.append(
            f"• {c['label']} - {_format_inr(float(c['revenue_total']))} "
            f"({c['revenue_column']}, {c['grain']}{dr})"
        )

    canonical = _pick_canonical_revenue_source(catalog)
    if canonical:
        lines.extend(
            [
                "",
                f"For a single company revenue figure, use “{canonical['label']}” "
                f"({_format_inr(float(canonical['revenue_total']))}) - "
                f"{canonical['grain']}. Other files are breakdowns or overlapping views.",
            ]
        )

    return {
        "answer": "\n".join(lines),
        "chart_data": chart_revenue_by_source(with_rev),
    }


def _answer_canonical_revenue(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = _pick_canonical_revenue_source(catalog)
    if not canonical:
        return {
            "answer": (
                "I could not pick a canonical revenue source. "
                "Import a file with a clear revenue or sales amount column (e.g. monthly P&L by channel)."
            ),
            "chart_data": None,
        }
    dr = f" Coverage: {canonical['date_range']}." if canonical.get("date_range") else ""
    return {
        "answer": (
            f"Use “{canonical['label']}” as your primary revenue view: "
            f"{_format_inr(float(canonical['revenue_total']))} "
            f"on column {canonical['revenue_column']} ({canonical['grain']}).{dr} "
            "Other sources overlap this - avoid adding their revenue totals."
        ),
        "chart_data": None,
    }


def chart_revenue_by_source(with_rev: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if len(with_rev) < 2:
        return None
    data = [
        {"name": c["label"], "value": float(c["revenue_total"])}
        for c in sorted(with_rev, key=lambda x: float(x["revenue_total"]), reverse=True)
    ]
    return {
        "type": "bar",
        "title": "Primary revenue metric by source (not additive)",
        "data": data[:12],
    }


def format_catalog_for_prompt(catalog: list[dict[str, Any]]) -> str:
    """Text block injected into LLM prompts."""
    lines = [
        "WORKSPACE SOURCE CATALOG (use for business answers - not file paths in user text):",
        "RULE: Never sum revenue totals across sources unless the user explicitly asks for a sum "
        "AND you explain double-counting risk. Prefer one canonical source for company revenue.",
        "",
    ]
    for c in catalog:
        rev = (
            f"primary revenue `{c['revenue_column']}` ≈ {_format_inr(float(c['revenue_total']))}"
            if c.get("has_revenue")
            else "no revenue column"
        )
        dr = f", dates {c['date_range']}" if c.get("date_range") else ""
        lines.append(
            f"- {c['label']} (variable df_{c['slug']}, {c['rows']} rows, {c['grain']}, "
            f"{rev}{dr})"
        )
    canonical = _pick_canonical_revenue_source(catalog)
    if canonical:
        lines.append(
            f"\nSuggested canonical revenue source: {canonical['label']} "
            f"({_format_inr(float(canonical['revenue_total']))})."
        )
    return "\n".join(lines)
