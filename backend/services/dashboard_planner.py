from __future__ import annotations

import json
import re
from numbers import Integral, Real
from typing import Any, Optional

import pandas as pd
from openai import OpenAI

from config import settings

MAX_SAMPLE_ROWS = 25
MAX_CELL_STR = 120
MAX_KPIS = 4
MAX_CHARTS = 6

PLANNER_SYSTEM = """You are a data visualization expert. From a small sample of rows, column names, and dtypes, infer what the spreadsheet is about and design a concise dashboard.

Return JSON only with this shape:
{
  "dataset_brief": "1–2 sentences describing what the data likely represents (e.g. retail sales, clinic visits, SEO rankings).",
  "kpis": [
    { "id": "slug", "title": "Short label for the UI", "column": "exact_column_name", "agg": "sum|mean|count|max|min" }
  ],
  "charts": [
    { "id": "slug", "title": "Chart title", "type": "line|bar|pie|area", "x_column": "exact_column_name", "y_column": "exact_column_name or null", "agg": "sum|mean|count" }
  ]
}

Rules:
- Use ONLY column names from the "columns" list provided by the user.
- At most 4 KPIs and 6 charts total.
- Choose chart types that fit the domain (sales → trend + category breakdown; patient list → demographics counts; SEO → rankings distribution or trend if dates exist).
- line/area: need a meaningful x_column (prefer dates) and numeric y_column.
- bar: categorical x_column; numeric y_column with sum/mean, OR y_column null with agg count to show row counts per category.
- pie: categorical x_column; y_column null + agg count for frequencies, OR numeric y_column with agg sum.
- Titles must be human-friendly, not raw column names.
- If there is no date column, do not use line/area unless x_column is clearly an ordered period (e.g. week_1, week_2). Otherwise prefer bar/pie.
"""


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower())
    return s.strip("_") or "item"


def column_outline(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for c in df.columns:
        dtype = str(df[c].dtype)
        nn = df[c].notna().sum()
        out.append({"name": c, "dtype": dtype, "non_null_count": int(nn)})
    return out


def sample_rows_for_llm(df: pd.DataFrame, max_rows: int = MAX_SAMPLE_ROWS) -> list[dict[str, Any]]:
    sample = df.head(max_rows).copy()
    for col in sample.columns:
        if pd.api.types.is_datetime64_any_dtype(sample[col]):
            sample[col] = sample[col].dt.strftime("%Y-%m-%d")

    records: list[dict[str, Any]] = []
    for _, row in sample.iterrows():
        rec: dict[str, Any] = {}
        for c in sample.columns:
            v = row[c]
            if pd.isna(v):
                rec[c] = None
            elif isinstance(v, str):
                rec[c] = v if len(v) <= MAX_CELL_STR else v[: MAX_CELL_STR - 1] + "…"
            elif isinstance(v, bool):
                rec[c] = v
            elif isinstance(v, Integral):
                rec[c] = int(v)
            elif isinstance(v, Real):
                fv = float(v)
                rec[c] = int(fv) if fv.is_integer() else fv
            else:
                rec[c] = str(v)[:MAX_CELL_STR]
        records.append(rec)
    return records


class DashboardPlanner:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    def build_plan(
        self,
        df: pd.DataFrame,
        metadata: dict[str, Any],
        stats: dict[str, Any],
        user_description: Optional[str] = None,
    ) -> dict[str, Any]:
        if self._client:
            try:
                raw = self._call_llm(df, metadata, stats, user_description)
                return self._validate_plan(raw, set(df.columns))
            except Exception:
                fallback = heuristic_fallback_plan(df, metadata, stats)
                fallback["dataset_brief"] = (
                    fallback["dataset_brief"]
                    + " (AI planner unavailable; using heuristic layout.)"
                )
                return fallback
        return heuristic_fallback_plan(df, metadata, stats)

    def _call_llm(
        self,
        df: pd.DataFrame,
        metadata: dict[str, Any],
        stats: dict[str, Any],
        user_description: Optional[str],
    ) -> dict[str, Any]:
        columns = list(df.columns)
        payload = {
            "row_count": len(df),
            "column_count": len(columns),
            "columns": column_outline(df),
            "heuristic_schema": metadata,
            "summary_stats_keys": list(stats.keys())[:40],
            "sample_rows": sample_rows_for_llm(df),
        }
        parts = [
            json.dumps(payload, indent=2, default=str),
        ]
        if user_description:
            parts.insert(0, f"User description of the file: {user_description}")
        user_content = "\n\n".join(parts) + "\n\nPropose the dashboard JSON."

        response = self._client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
        )
        text = response.choices[0].message.content or "{}"
        return json.loads(text)

    def _validate_plan(self, raw: dict[str, Any], valid_cols: set[str]) -> dict[str, Any]:
        brief = str(raw.get("dataset_brief") or "").strip() or "Dataset overview"

        kpis_out: list[dict[str, Any]] = []
        for i, k in enumerate(raw.get("kpis") or []):
            if len(kpis_out) >= MAX_KPIS:
                break
            col = k.get("column")
            if col == "__row_count__" or (isinstance(col, str) and col in valid_cols):
                agg = str(k.get("agg") or "sum").lower()
                if agg not in ("sum", "mean", "count", "max", "min"):
                    agg = "sum"
                kid = str(k.get("id") or _slug(str(k.get("title") or f"kpi_{i}")))
                title = str(k.get("title") or col or "Metric")
                kpis_out.append({"id": kid, "title": title, "column": col, "agg": agg})

        charts_out: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for i, c in enumerate(raw.get("charts") or []):
            if len(charts_out) >= MAX_CHARTS:
                break
            ctype = str(c.get("type") or "bar").lower()
            if ctype not in ("line", "bar", "pie", "area"):
                ctype = "bar"
            x_col = c.get("x_column")
            y_col = c.get("y_column")
            if not isinstance(x_col, str) or x_col not in valid_cols:
                continue
            if y_col is not None and (not isinstance(y_col, str) or y_col not in valid_cols):
                continue
            agg = str(c.get("agg") or "sum").lower()
            if agg not in ("sum", "mean", "count"):
                agg = "sum"
            cid = str(c.get("id") or _slug(str(c.get("title") or f"chart_{i}")))
            if cid in seen_ids:
                cid = f"{cid}_{i}"
            seen_ids.add(cid)
            title = str(c.get("title") or f"{y_col or ''} by {x_col}".strip())
            charts_out.append({
                "id": cid,
                "title": title,
                "type": ctype,
                "x_column": x_col,
                "y_column": y_col,
                "agg": agg,
            })

        return {
            "source": "ai",
            "dataset_brief": brief,
            "kpis": kpis_out,
            "charts": charts_out,
        }


def heuristic_fallback_plan(
    df: pd.DataFrame,
    metadata: dict[str, Any],
    stats: dict[str, Any],
) -> dict[str, Any]:
    """Rule-based dashboard spec when OpenAI is unavailable."""
    date_cols = metadata.get("date_columns") or []
    revenue_cols = metadata.get("revenue_columns") or []
    category_cols = metadata.get("category_columns") or []
    numeric_cols = metadata.get("numeric_columns") or []
    cols = set(df.columns)

    kpis: list[dict[str, Any]] = []
    for rev in revenue_cols:
        if rev in cols and len(kpis) < MAX_KPIS:
            kpis.append({
                "id": f"total_{_slug(rev)}",
                "title": f"Total {rev.replace('_', ' ').title()}",
                "column": rev,
                "agg": "sum",
            })
    if len(kpis) < MAX_KPIS:
        kpis.append({
            "id": "row_count",
            "title": "Rows",
            "column": "__row_count__",
            "agg": "count",
        })

    charts: list[dict[str, Any]] = []

    def add_chart(item: dict[str, Any]) -> None:
        if len(charts) >= MAX_CHARTS:
            return
        charts.append(item)

    for date_col in date_cols:
        for rev_col in revenue_cols:
            if date_col in cols and rev_col in cols:
                add_chart({
                    "id": f"{_slug(rev_col)}_over_{_slug(date_col)}",
                    "title": f"{rev_col.replace('_', ' ').title()} over time",
                    "type": "line",
                    "x_column": date_col,
                    "y_column": rev_col,
                    "agg": "sum",
                })

    for cat_col in category_cols:
        for rev_col in revenue_cols:
            if cat_col in cols and rev_col in cols:
                add_chart({
                    "id": f"{_slug(rev_col)}_by_{_slug(cat_col)}",
                    "title": f"{rev_col.replace('_', ' ').title()} by {cat_col.replace('_', ' ').title()}",
                    "type": "bar",
                    "x_column": cat_col,
                    "y_column": rev_col,
                    "agg": "sum",
                })

    for cat_col in category_cols[:1]:
        if cat_col in cols:
            add_chart({
                "id": f"{_slug(cat_col)}_distribution",
                "title": f"{cat_col.replace('_', ' ').title()} distribution",
                "type": "pie",
                "x_column": cat_col,
                "y_column": None,
                "agg": "count",
            })

    for date_col in date_cols:
        for num_col in numeric_cols:
            if num_col in revenue_cols:
                continue
            if date_col in cols and num_col in cols:
                add_chart({
                    "id": f"{_slug(num_col)}_over_{_slug(date_col)}",
                    "title": f"{num_col.replace('_', ' ').title()} over time",
                    "type": "area",
                    "x_column": date_col,
                    "y_column": num_col,
                    "agg": "sum",
                })

    rows = stats.get("rows", len(df))
    return {
        "source": "heuristic",
        "dataset_brief": f"About {rows:,} rows × {len(df.columns)} columns. "
        "AI planner disabled; showing heuristic charts. Set OPENAI_API_KEY for tailored dashboards.",
        "kpis": kpis[:MAX_KPIS],
        "charts": charts[:MAX_CHARTS],
    }
