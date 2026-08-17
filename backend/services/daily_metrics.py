from __future__ import annotations

from typing import Any

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


def find_order_id_column(df: pd.DataFrame) -> str | None:
    """Column likely to be one row per order (for nunique)."""
    for c in df.columns:
        n = _normalize_name(str(c))
        if n in ORDER_ID_HINTS:
            return c
        if "order_id" in n or "order_number" in n or "transaction_id" in n:
            return c
    return None


def resolve_revenue_column(df: pd.DataFrame, metadata: dict[str, Any]) -> str | None:
    # Prefer explicit primary from mapping-spec-derived metadata
    primary = metadata.get("primary_amount")
    if primary and primary in df.columns:
        s = df[primary]
        if pd.api.types.is_numeric_dtype(s):
            return primary
        coerced = pd.to_numeric(s, errors="coerce")
        if coerced.notna().sum() > len(df) * 0.5:
            return primary

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


def resolve_date_column(df: pd.DataFrame, metadata: dict[str, Any]) -> str | None:
    primary = metadata.get("primary_timeline")
    if primary and primary in df.columns:
        return primary
    for c in metadata.get("date_columns") or []:
        if c in df.columns:
            return c
    return None


def compute_daily_metrics_df(
    df: pd.DataFrame,
    date_col: str,
    revenue_col: str,
) -> pd.DataFrame | None:
    """
    One row per calendar day:
      date (YYYY-MM-DD), revenue (sum), orders, aov (revenue/orders).

    ``orders`` counts distinct values of an order-id column when one exists. When
    none does it counts rows, which is only the order count if the file is one
    row per order. ``daily.attrs["orders_basis"]`` records which happened so the
    label can say "rows per day" instead of silently claiming orders.
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
        basis = {"kind": "order_id", "column": oid, "label": "Orders"}
        out["aov"] = out["revenue"] / out["orders"].replace(0, pd.NA)
        out["aov"] = out["aov"].fillna(0.0).astype(float)
    else:
        # No order-id column: do not invent an "orders" series or AOV. Counting
        # rows as orders deflates AOV whenever a file has multiple lines per order.
        out = (
            w.groupby("_day", as_index=False)
            .agg(revenue=("_rev", "sum"))
        )
        basis = {
            "kind": "unavailable",
            "column": None,
            "label": "Orders",
            "caveat": (
                "No order-id column was found, so order count and AOV are omitted "
                "rather than approximated from row count."
            ),
        }

    out["revenue"] = out["revenue"].astype(float)
    if "orders" in out.columns:
        out["orders"] = out["orders"].astype(int)
    out = out.rename(columns={"_day": "date"})
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out = out.sort_values("date").reset_index(drop=True)
    out.attrs["orders_basis"] = basis
    return out

def orders_basis(daily: pd.DataFrame | None) -> dict[str, Any]:
    if daily is None:
        return {"kind": "unknown", "label": "Records"}
    return daily.attrs.get("orders_basis") or {"kind": "unknown", "label": "Records"}


# Aggregating a rate by averaging its per-period values weights a day with three
# orders the same as a day with three thousand. Anything listed here must be
# recomputed from its numerator and denominator instead.
RATIO_METRICS = {
    "aov": ("revenue", "orders"),
}


def aggregate_metric(daily: pd.DataFrame, metric: str) -> float | None:
    """Correctly aggregate a daily metric over the whole frame."""
    if daily is None or daily.empty or metric not in daily.columns:
        return None
    if metric in RATIO_METRICS:
        numerator_col, denominator_col = RATIO_METRICS[metric]
        numerator = float(daily[numerator_col].sum())
        denominator = float(daily[denominator_col].sum())
        return numerator / denominator if denominator else None
    return float(daily[metric].sum())


def compute_daily_metrics_for_dataset(
    df: pd.DataFrame,
    metadata: dict[str, Any],
) -> tuple[pd.DataFrame | None, str | None, str | None]:
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
    has_orders = "orders" in daily.columns
    has_aov = "aov" in daily.columns
    for _, row in daily.iterrows():
        rec: dict[str, Any] = {
            "date": str(row["date"]),
            "revenue": float(row["revenue"]),
        }
        if has_orders:
            rec["orders"] = int(row["orders"])
        if has_aov:
            rec["aov"] = float(row["aov"])
        rows.append(rec)
    return rows


def metric_key_for_chart(
    title: str,
    y_column: str,
    agg: str,
    revenue_col: str | None,
) -> str | None:
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
