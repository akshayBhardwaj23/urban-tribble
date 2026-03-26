from __future__ import annotations

from typing import Any, Optional

import pandas as pd


ORDER_ID_HINTS = frozenset(
    {
        "order_id",
        "orderid",
        "order_number",
        "ordernumber",
        "order_no",
        "orderno",
        "transaction_id",
        "transactionid",
        "po_number",
        "ponumber",
    }
)


def _normalize_name(s: str) -> str:
    return s.lower().strip().replace(" ", "_").replace("-", "_")


def find_order_id_column(df: pd.DataFrame) -> Optional[str]:
    """Column likely to be one row per order (for nunique)."""
    for c in df.columns:
        n = _normalize_name(str(c))
        if n in ORDER_ID_HINTS:
            return c
        if "order_id" in n or "order_number" in n or "transaction_id" in n:
            return c
    return None


def resolve_revenue_column(df: pd.DataFrame, metadata: dict[str, Any]) -> Optional[str]:
    for c in metadata.get("revenue_columns") or []:
        if c not in df.columns:
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            return c
        coerced = pd.to_numeric(s, errors="coerce")
        if coerced.notna().sum() > len(df) * 0.5:
            return c
    for c in metadata.get("numeric_columns") or []:
        if c not in df.columns:
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            return c
        coerced = pd.to_numeric(s, errors="coerce")
        if coerced.notna().sum() > len(df) * 0.5:
            return c
    return None


def resolve_date_column(df: pd.DataFrame, metadata: dict[str, Any]) -> Optional[str]:
    for c in metadata.get("date_columns") or []:
        if c in df.columns:
            return c
    return None


def compute_daily_metrics_df(
    df: pd.DataFrame,
    date_col: str,
    revenue_col: str,
) -> Optional[pd.DataFrame]:
    """
    One row per calendar day:
      date (YYYY-MM-DD), revenue (sum), orders (count or nunique order id), aov (revenue/orders).
    """
    if date_col not in df.columns or revenue_col not in df.columns:
        return None

    w = df.copy()
    w["_dt"] = pd.to_datetime(w[date_col], errors="coerce")
    w = w.dropna(subset=["_dt"])
    if w.empty:
        return None

    w["_day"] = w["_dt"].dt.normalize()
    w["_rev"] = pd.to_numeric(w[revenue_col], errors="coerce").fillna(0.0)

    oid = find_order_id_column(df)
    if oid and oid in w.columns:
        out = (
            w.groupby("_day", as_index=False)
            .agg(revenue=("_rev", "sum"), orders=(oid, "nunique"))
        )
    else:
        out = (
            w.groupby("_day", as_index=False)
            .agg(revenue=("_rev", "sum"), orders=("_rev", "count"))
        )

    out["aov"] = out["revenue"] / out["orders"].replace(0, pd.NA)
    out["aov"] = out["aov"].fillna(0.0).astype(float)
    out["revenue"] = out["revenue"].astype(float)
    out["orders"] = out["orders"].astype(int)
    out = out.rename(columns={"_day": "date"})
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out = out.sort_values("date").reset_index(drop=True)
    return out


def compute_daily_metrics_for_dataset(
    df: pd.DataFrame,
    metadata: dict[str, Any],
) -> tuple[Optional[pd.DataFrame], Optional[str], Optional[str]]:
    """Returns (daily_df, date_col_used, revenue_col_used) or (None, None, None)."""
    date_col = resolve_date_column(df, metadata)
    revenue_col = resolve_revenue_column(df, metadata)
    if not date_col or not revenue_col:
        return None, None, None
    daily = compute_daily_metrics_df(df, date_col, revenue_col)
    if daily is None or daily.empty:
        return None, date_col, revenue_col
    return daily, date_col, revenue_col


def daily_metrics_to_records(daily: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in daily.iterrows():
        rows.append({
            "date": str(row["date"]),
            "revenue": float(row["revenue"]),
            "orders": int(row["orders"]),
            "aov": float(row["aov"]),
        })
    return rows


def metric_key_for_chart(
    title: str,
    y_column: str,
    agg: str,
    revenue_col: Optional[str],
) -> Optional[str]:
    """
    Map a planned chart to daily aggregate column: revenue | orders | aov.
    """
    t = (title or "").lower()
    agg = (agg or "sum").lower()

    if revenue_col and y_column == revenue_col:
        if agg == "count" or (
            "order" in t
            and "value" not in t
            and "aov" not in t
            and "average" not in t
        ):
            return "orders"
        if agg == "mean" or "aov" in t or "average order" in t or "avg order" in t:
            return "aov"
        return "revenue"

    if "order" in t and "count" in t:
        return "orders"
    if "aov" in t or "average order" in t:
        return "aov"
    if revenue_col and y_column != revenue_col:
        return None
    return None
