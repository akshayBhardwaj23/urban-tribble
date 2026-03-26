from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd


def _format_kpi_number(val: float, agg: str, is_row_count: bool) -> str:
    """Human-readable KPI string with comma grouping — never scientific notation."""
    if not math.isfinite(val):
        return "—"
    if is_row_count or agg == "count":
        return f"{int(round(val)):,}"
    s = f"{val:,.2f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _fmt_x(val: Any) -> str:
    if pd.isna(val):
        return "—"
    if hasattr(val, "strftime"):
        try:
            return val.strftime("%Y-%m-%d")
        except Exception:
            pass
    return str(val)


def _safe_float(x: Any) -> float:
    try:
        v = float(x)
        if pd.isna(v):
            return float("nan")
        return v
    except (TypeError, ValueError):
        return float("nan")


def compute_kpi_value(df: pd.DataFrame, column: str, agg: str) -> Optional[float]:
    if column == "__row_count__":
        return float(len(df))
    if column not in df.columns:
        return None
    agg = agg.lower()
    s = df[column]
    if agg == "count":
        return float(s.notna().sum())
    if not pd.api.types.is_numeric_dtype(s):
        return float(s.notna().sum()) if agg == "count" else None
    if agg == "sum":
        return float(s.sum())
    if agg == "mean":
        return float(s.mean())
    if agg == "max":
        return float(s.max())
    if agg == "min":
        return float(s.min())
    return None


def execute_plan(df: pd.DataFrame, plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn a stored dashboard plan into KPI payloads and Recharts-ready chart payloads."""
    kpi_specs = plan.get("kpis") or []
    chart_specs = plan.get("charts") or []

    kpis_out: list[dict[str, Any]] = []
    for k in kpi_specs:
        col = k.get("column")
        agg = str(k.get("agg") or "sum").lower()
        title = str(k.get("title") or "Metric")
        kid = str(k.get("id") or title)
        if col is None:
            continue
        val = compute_kpi_value(df, col, agg)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        formatted = _format_kpi_number(
            float(val),
            agg,
            col == "__row_count__",
        )
        kpis_out.append({
            "id": kid,
            "title": title,
            "value": val,
            "formatted": formatted,
        })

    charts_out: list[dict[str, Any]] = []
    for c in chart_specs:
        chart = _run_chart_spec(df, c)
        if chart:
            charts_out.append(chart)

    return kpis_out, charts_out


def _run_chart_spec(df: pd.DataFrame, spec: dict[str, Any]) -> Optional[dict[str, Any]]:
    cid = str(spec.get("id") or "chart")
    title = str(spec.get("title") or "Chart")
    ctype = str(spec.get("type") or "bar").lower()
    x_col = spec.get("x_column")
    y_col = spec.get("y_column")
    agg = str(spec.get("agg") or "sum").lower()

    if not isinstance(x_col, str) or x_col not in df.columns:
        return None

    if ctype == "pie":
        return _chart_pie(df, cid, title, x_col, y_col, agg)

    if y_col is None:
        if ctype == "bar" and agg == "count":
            return _chart_bar_count(df, cid, title, x_col)
        return None

    if not isinstance(y_col, str) or y_col not in df.columns:
        return None

    if ctype in ("line", "area"):
        return _chart_xy_series(df, cid, title, ctype, x_col, y_col, agg)
    if ctype == "bar":
        return _chart_bar_agg(df, cid, title, x_col, y_col, agg)

    return None


def _chart_pie(
    df: pd.DataFrame,
    cid: str,
    title: str,
    x_col: str,
    y_col: Optional[str],
    agg: str,
) -> Optional[dict[str, Any]]:
    if y_col is None or agg == "count":
        top = df[x_col].value_counts().head(12)
        data = [{"name": str(name), "value": int(cnt)} for name, cnt in top.items()]
    else:
        if y_col not in df.columns:
            return None
        if not pd.api.types.is_numeric_dtype(df[y_col]):
            top = df[x_col].value_counts().head(12)
            data = [{"name": str(name), "value": int(cnt)} for name, cnt in top.items()]
            if not data:
                return None
            return {"id": cid, "title": title, "type": "pie", "data": data}
        g = df.groupby(x_col, dropna=False)[y_col]
        if agg == "mean":
            summed = g.mean()
        else:
            summed = g.sum()
        summed = summed.sort_values(ascending=False).head(12)
        data = [{"name": str(name), "value": float(_safe_float(v))} for name, v in summed.items() if pd.notna(v)]

    if not data:
        return None
    return {"id": cid, "title": title, "type": "pie", "data": data}


def _chart_bar_count(df: pd.DataFrame, cid: str, title: str, x_col: str) -> Optional[dict[str, Any]]:
    top = df.groupby(x_col, dropna=False).size().sort_values(ascending=False).head(15)
    data = [{"name": str(name), "value": int(v)} for name, v in top.items()]
    if not data:
        return None
    return {"id": cid, "title": title, "type": "bar", "data": data}


def _chart_bar_agg(
    df: pd.DataFrame,
    cid: str,
    title: str,
    x_col: str,
    y_col: str,
    agg: str,
) -> Optional[dict[str, Any]]:
    g = df.groupby(x_col, dropna=False)[y_col]
    if agg == "mean":
        series = g.mean()
    elif agg == "count":
        series = g.count()
    else:
        series = g.sum()
    series = series.sort_values(ascending=False).head(15)
    data = [
        {"name": str(name), "value": float(_safe_float(v))}
        for name, v in series.items()
        if pd.notna(v)
    ]
    if not data:
        return None
    return {"id": cid, "title": title, "type": "bar", "data": data}


def _chart_xy_series(
    df: pd.DataFrame,
    cid: str,
    title: str,
    ctype: str,
    x_col: str,
    y_col: str,
    agg: str,
) -> Optional[dict[str, Any]]:
    g = df.groupby(x_col, dropna=False)[y_col]
    if agg == "mean":
        series = g.mean()
    elif agg == "count":
        series = g.count()
    else:
        series = g.sum()
    try:
        series = series.sort_index()
    except TypeError:
        series = series.sort_values()

    chart_data = []
    for idx, val in series.items():
        yv = _safe_float(val)
        if not pd.notna(yv):
            continue
        chart_data.append({"x": _fmt_x(idx), "y": yv})

    if len(chart_data) < 2:
        return None
    return {
        "id": cid,
        "title": title,
        "type": "line" if ctype == "line" else "area",
        "x_label": x_col,
        "y_label": y_col,
        "data": chart_data,
    }


def legacy_charts(df: pd.DataFrame, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Previous rule-based chart list (full cartesian product)."""
    charts: list[dict[str, Any]] = []
    date_cols = metadata.get("date_columns", [])
    revenue_cols = metadata.get("revenue_columns", [])
    category_cols = metadata.get("category_columns", [])
    numeric_cols = metadata.get("numeric_columns", [])

    for date_col in date_cols:
        for rev_col in revenue_cols:
            if date_col in df.columns and rev_col in df.columns:
                grouped = df.groupby(date_col)[rev_col].sum().reset_index()
                grouped = grouped.sort_values(date_col)
                chart_data = []
                for _, row in grouped.iterrows():
                    val = row[date_col]
                    if pd.api.types.is_datetime64_any_dtype(type(val)):
                        val = val.strftime("%Y-%m-%d")
                    chart_data.append({"x": str(val), "y": float(row[rev_col])})

                charts.append({
                    "id": f"{rev_col}_over_{date_col}",
                    "title": f"{rev_col.replace('_', ' ').title()} Over Time",
                    "type": "line",
                    "x_label": date_col,
                    "y_label": rev_col,
                    "data": chart_data,
                })

    for cat_col in category_cols:
        for rev_col in revenue_cols:
            if cat_col in df.columns and rev_col in df.columns:
                grouped = df.groupby(cat_col)[rev_col].sum().reset_index()
                grouped = grouped.sort_values(rev_col, ascending=False)
                chart_data = [
                    {"name": str(row[cat_col]), "value": float(row[rev_col])}
                    for _, row in grouped.iterrows()
                ]
                charts.append({
                    "id": f"{rev_col}_by_{cat_col}",
                    "title": f"{rev_col.replace('_', ' ').title()} by {cat_col.replace('_', ' ').title()}",
                    "type": "bar",
                    "data": chart_data,
                })

    for cat_col in category_cols[:1]:
        if cat_col in df.columns:
            counts = df[cat_col].value_counts().head(10)
            chart_data = [
                {"name": str(name), "value": int(count)}
                for name, count in counts.items()
            ]
            charts.append({
                "id": f"{cat_col}_distribution",
                "title": f"{cat_col.replace('_', ' ').title()} Distribution",
                "type": "pie",
                "data": chart_data,
            })

    for date_col in date_cols:
        for num_col in numeric_cols:
            if date_col in df.columns and num_col in df.columns:
                grouped = df.groupby(date_col)[num_col].sum().reset_index()
                grouped = grouped.sort_values(date_col)
                chart_data = []
                for _, row in grouped.iterrows():
                    val = row[date_col]
                    if pd.api.types.is_datetime64_any_dtype(type(val)):
                        val = val.strftime("%Y-%m-%d")
                    chart_data.append({"x": str(val), "y": float(row[num_col])})

                charts.append({
                    "id": f"{num_col}_over_{date_col}",
                    "title": f"{num_col.replace('_', ' ').title()} Over Time",
                    "type": "area",
                    "x_label": date_col,
                    "y_label": num_col,
                    "data": chart_data,
                })

    return charts
