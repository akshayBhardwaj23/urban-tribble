"""Declarative query plans that replace LLM-generated pandas code.

The model proposes a JSON plan drawn from a fixed operation set; the server
validates every field against the real schema and then executes it with pandas.
No generated text is ever evaluated, so a prompt injection can at worst produce
an invalid plan, which is rejected.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

MAX_RESULT_ROWS = 200
MAX_FILTERS = 12
MAX_GROUP_BY = 3
MAX_AGGREGATES = 6

AGG_FUNCS = frozenset(
    {"sum", "mean", "median", "min", "max", "count", "nunique", "std"}
)

# Comparison operators and the arity they expect.
FILTER_OPS = {
    "eq": 1,
    "ne": 1,
    "gt": 1,
    "gte": 1,
    "lt": 1,
    "lte": 1,
    "contains": 1,
    "not_contains": 1,
    "in": "list",
    "not_in": "list",
    "between": 2,
    "is_null": 0,
    "not_null": 0,
}

TIME_FREQS = {
    "day": "D",
    "week": "W-MON",
    "month": "MS",
    "quarter": "QS",
    "year": "YS",
}

PLAN_SCHEMA_DOC = """Respond with ONLY a JSON object describing a query plan. Never write code.

{
  "source": "<one of the source keys listed above; omit when there is only one>",
  "per_source": false,
  "filters": [
    {"column": "<column>", "op": "eq|ne|gt|gte|lt|lte|contains|not_contains|in|not_in|between|is_null|not_null", "value": <scalar, or [a, b] for between, or [..] for in>}
  ],
  "time_bucket": {"column": "<date column>", "freq": "day|week|month|quarter|year"},
  "group_by": ["<column>", "..."],
  "aggregate": [
    {"column": "<numeric column>", "func": "sum|mean|median|min|max|count|nunique|std", "alias": "<output name>"}
  ],
  "sort": {"by": "<alias or column>", "ascending": false},
  "limit": 20,
  "explanation_hint": "one short sentence about what this computes"
}

Rules:
- Every column name must appear verbatim in the schema. Never invent one.
- Use time_bucket instead of trying to format dates yourself. It adds a `period` column you can group by.
- With no group_by and one or more aggregates you get a single row of totals.
- With no aggregate at all you get filtered rows (capped).
- Set per_source to true to run the same plan against every source and get a
  per-source breakdown. Do this for workspace-wide revenue questions rather than
  adding sources together, because different sources double-count each other.
- Never use sum on a rate, percentage, ratio, margin, or average column — use mean
  (or omit it). Summing those produces nonsense.
"""


class QueryPlanError(ValueError):
    """The proposed plan does not fit the operation set or the real schema."""


_RATE_NAME_RE = re.compile(
    r"(^|_)(rate|ratio|pct|percent|percentage|margin|avg|average|aov|cvr|ctr|cpc|cpm|roas|rpm)(_|$)|%$",
    re.IGNORECASE,
)


def looks_like_rate_column(name: str) -> bool:
    """Heuristic: column names that must not be summed across rows."""
    n = (name or "").strip().lower().replace(" ", "_")
    if not n:
        return False
    return bool(_RATE_NAME_RE.search(n))


def _fail(msg: str) -> None:
    raise QueryPlanError(msg)


def _resolve_column(name: Any, columns: List[str]) -> str:
    """Match a model-proposed column to a real one, tolerating case and spacing."""
    if not isinstance(name, str) or not name.strip():
        _fail("A column name is missing.")
    if name in columns:
        return name
    lowered = {c.lower(): c for c in columns}
    key = name.strip().lower()
    if key in lowered:
        return lowered[key]
    squashed = {c.lower().replace(" ", "_"): c for c in columns}
    key2 = key.replace(" ", "_")
    if key2 in squashed:
        return squashed[key2]
    _fail(f"Unknown column {name!r}. Available: {', '.join(columns[:40])}")
    return ""  # unreachable


def validate_plan(plan: Any, frames: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Return a normalized plan or raise QueryPlanError."""
    if not isinstance(plan, dict):
        _fail("Plan must be a JSON object.")
    if not frames:
        _fail("No data sources are available.")

    per_source = bool(plan.get("per_source"))
    source = plan.get("source")
    if per_source:
        source = None
    elif source is None:
        if len(frames) != 1:
            _fail("Plan must name a source when several are available.")
        source = next(iter(frames))
    elif source not in frames:
        lowered = {k.lower(): k for k in frames}
        if str(source).lower() in lowered:
            source = lowered[str(source).lower()]
        else:
            _fail(f"Unknown source {source!r}. Available: {', '.join(frames)}")

    # Columns must be valid for every frame the plan will touch.
    targets = list(frames) if per_source else [source]

    normalized_by_source: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    for key in targets:
        try:
            normalized_by_source[key] = _validate_against(plan, frames[key])
        except QueryPlanError as exc:
            errors.append(f"{key}: {exc}")
    if not normalized_by_source:
        _fail("; ".join(errors) or "Plan does not apply to any source.")

    return {
        "per_source": per_source,
        "source": source,
        "by_source": normalized_by_source,
        "skipped": errors,
        "explanation_hint": str(plan.get("explanation_hint") or "")[:300],
    }


def _validate_against(plan: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    columns = [str(c) for c in df.columns]

    raw_filters = plan.get("filters") or []
    if not isinstance(raw_filters, list):
        _fail("filters must be a list.")
    if len(raw_filters) > MAX_FILTERS:
        _fail(f"Too many filters (max {MAX_FILTERS}).")
    filters = [_validate_filter(f, columns) for f in raw_filters]

    time_bucket = None
    raw_bucket = plan.get("time_bucket")
    if isinstance(raw_bucket, dict) and raw_bucket.get("column"):
        col = _resolve_column(raw_bucket.get("column"), columns)
        freq = str(raw_bucket.get("freq") or "month").lower()
        if freq not in TIME_FREQS:
            _fail(f"Unknown time bucket {freq!r}. Use one of {', '.join(TIME_FREQS)}.")
        if not pd.api.types.is_datetime64_any_dtype(df[col]):
            parsed = pd.to_datetime(df[col], errors="coerce")
            if len(df) and parsed.notna().mean() < 0.8:
                _fail(f"Column {col!r} is not a usable date column.")
        time_bucket = {"column": col, "freq": freq}

    raw_group = plan.get("group_by") or []
    if isinstance(raw_group, str):
        raw_group = [raw_group]
    if not isinstance(raw_group, list):
        _fail("group_by must be a list of column names.")
    if len(raw_group) > MAX_GROUP_BY:
        _fail(f"Too many group_by columns (max {MAX_GROUP_BY}).")
    group_by: List[str] = []
    for g in raw_group:
        if isinstance(g, str) and g.strip().lower() == "period" and time_bucket:
            group_by.append("period")
        else:
            group_by.append(_resolve_column(g, columns))
    if time_bucket and "period" not in group_by:
        group_by.insert(0, "period")

    raw_aggs = plan.get("aggregate") or []
    if isinstance(raw_aggs, dict):
        raw_aggs = [raw_aggs]
    if not isinstance(raw_aggs, list):
        _fail("aggregate must be a list.")
    if len(raw_aggs) > MAX_AGGREGATES:
        _fail(f"Too many aggregates (max {MAX_AGGREGATES}).")
    aggregates = [_validate_aggregate(a, columns, df) for a in raw_aggs]

    sort = None
    raw_sort = plan.get("sort")
    if isinstance(raw_sort, dict) and raw_sort.get("by"):
        by = str(raw_sort["by"])
        known = {a["alias"] for a in aggregates} | set(group_by) | set(columns)
        if by not in known:
            lowered = {k.lower(): k for k in known}
            if by.lower() in lowered:
                by = lowered[by.lower()]
            else:
                by = aggregates[0]["alias"] if aggregates else group_by[0] if group_by else None
        if by:
            sort = {"by": by, "ascending": bool(raw_sort.get("ascending", False))}

    limit = plan.get("limit")
    try:
        limit = int(limit) if limit is not None else 50
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, MAX_RESULT_ROWS))

    return {
        "filters": filters,
        "time_bucket": time_bucket,
        "group_by": group_by,
        "aggregate": aggregates,
        "sort": sort,
        "limit": limit,
    }


def _validate_filter(f: Any, columns: List[str]) -> Dict[str, Any]:
    if not isinstance(f, dict):
        _fail("Each filter must be an object.")
    col = _resolve_column(f.get("column"), columns)
    op = str(f.get("op") or "eq").lower()
    if op not in FILTER_OPS:
        _fail(f"Unknown filter operator {op!r}.")
    arity = FILTER_OPS[op]
    value = f.get("value")
    if arity == 0:
        value = None
    elif arity == "list":
        if not isinstance(value, list) or not value:
            _fail(f"Operator {op!r} needs a non-empty list value.")
        value = [_scalar(v) for v in value[:200]]
    elif arity == 2:
        if not isinstance(value, list) or len(value) != 2:
            _fail("Operator 'between' needs a two-element list value.")
        value = [_scalar(v) for v in value]
    else:
        if isinstance(value, (list, dict)):
            _fail(f"Operator {op!r} needs a scalar value.")
        value = _scalar(value)
    return {"column": col, "op": op, "value": value}


def _validate_aggregate(a: Any, columns: List[str], df: pd.DataFrame) -> Dict[str, Any]:
    if not isinstance(a, dict):
        _fail("Each aggregate must be an object.")
    func = str(a.get("func") or "sum").lower()
    if func not in AGG_FUNCS:
        _fail(f"Unknown aggregate function {func!r}.")
    col = _resolve_column(a.get("column"), columns)
    if func in ("sum", "mean", "median", "std") and not pd.api.types.is_numeric_dtype(df[col]):
        _fail(f"Cannot apply {func} to non-numeric column {col!r}.")
    if func == "sum" and looks_like_rate_column(col):
        _fail(
            f"Cannot sum rate/ratio column {col!r}. Use mean, or recompute from "
            "numerator and denominator."
        )
    alias = a.get("alias")
    if not isinstance(alias, str) or not alias.strip():
        alias = f"{func}_{col}"
    alias = alias.strip()[:80]
    return {"column": col, "func": func, "alias": alias}


def _scalar(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def execute_plan(
    normalized: Dict[str, Any], frames: Dict[str, pd.DataFrame]
) -> Dict[str, Any]:
    """Run a validated plan. Returns a JSON-safe result envelope."""
    if normalized.get("per_source"):
        breakdown: Dict[str, Any] = {}
        for key, spec in normalized["by_source"].items():
            breakdown[key] = _run_one(spec, frames[key])
        return {
            "kind": "per_source",
            "sources": breakdown,
            "note": (
                "Reported separately for each source. These are different views of the "
                "business and must not be added together."
            ),
        }

    source = normalized["source"]
    spec = normalized["by_source"][source]
    return {"kind": "single", "source": source, "result": _run_one(spec, frames[source])}


def _run_one(spec: Dict[str, Any], df: pd.DataFrame) -> Any:
    work = df

    for f in spec["filters"]:
        work = work[_filter_mask(work, f)]
        if work.empty:
            break

    if work.empty:
        return {"rows": [], "row_count": 0, "note": "No rows matched the filters."}

    bucket = spec["time_bucket"]
    if bucket:
        series = work[bucket["column"]]
        if not pd.api.types.is_datetime64_any_dtype(series):
            series = pd.to_datetime(series, errors="coerce")
        work = work.assign(period=series.dt.to_period(_period_alias(bucket["freq"])).astype(str))
        work = work[work["period"].notna() & (work["period"] != "NaT")]
        if work.empty:
            return {"rows": [], "row_count": 0, "note": "No rows had a usable date."}

    aggregates = spec["aggregate"]
    group_by = spec["group_by"]

    if aggregates and group_by:
        named = {a["alias"]: (a["column"], a["func"]) for a in aggregates}
        out = work.groupby(group_by, dropna=False, as_index=False).agg(**named)
    elif aggregates:
        row = {a["alias"]: _apply_agg(work[a["column"]], a["func"]) for a in aggregates}
        return {"totals": {k: _jsonable(v) for k, v in row.items()}, "row_count": int(len(work))}
    elif group_by:
        out = work.groupby(group_by, dropna=False, as_index=False).size().rename(
            columns={"size": "row_count"}
        )
    else:
        out = work

    sort = spec["sort"]
    if sort and sort["by"] in out.columns:
        out = out.sort_values(sort["by"], ascending=sort["ascending"], kind="mergesort")
    elif aggregates and aggregates[0]["alias"] in out.columns:
        out = out.sort_values(aggregates[0]["alias"], ascending=False, kind="mergesort")

    total_rows = int(len(out))
    out = out.head(spec["limit"])

    return {
        "rows": [_jsonable(r) for r in out.to_dict(orient="records")],
        "row_count": total_rows,
        "truncated": total_rows > len(out),
    }


def _period_alias(freq: str) -> str:
    return {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}[freq]


def _apply_agg(series: pd.Series, func: str) -> Any:
    if func == "count":
        return int(series.notna().sum())
    if func == "nunique":
        return int(series.nunique(dropna=True))
    value = getattr(series, func)(skipna=True)
    return value


def _filter_mask(df: pd.DataFrame, f: Dict[str, Any]) -> pd.Series:
    col = df[f["column"]]
    op = f["op"]
    value = f["value"]

    if op == "is_null":
        return col.isna()
    if op == "not_null":
        return col.notna()
    if op == "in":
        return col.isin(value)
    if op == "not_in":
        return ~col.isin(value)
    if op in ("contains", "not_contains"):
        hit = col.astype(str).str.contains(str(value), case=False, na=False, regex=False)
        return ~hit if op == "not_contains" else hit

    comparable, value = _coerce_for_compare(col, value)
    if op == "between":
        lo, hi = sorted(value, key=lambda v: (v is None, v))
        return comparable.between(lo, hi)
    return {
        "eq": lambda: comparable == value,
        "ne": lambda: comparable != value,
        "gt": lambda: comparable > value,
        "gte": lambda: comparable >= value,
        "lt": lambda: comparable < value,
        "lte": lambda: comparable <= value,
    }[op]()


def _coerce_for_compare(col: pd.Series, value: Any) -> Tuple[pd.Series, Any]:
    """Align the comparison value with the column dtype so eq/gt behave sensibly."""
    if pd.api.types.is_datetime64_any_dtype(col):
        if isinstance(value, list):
            return col, [pd.to_datetime(v, errors="coerce") for v in value]
        return col, pd.to_datetime(value, errors="coerce")
    if pd.api.types.is_numeric_dtype(col):
        if isinstance(value, list):
            return col, [pd.to_numeric(v, errors="coerce") for v in value]
        return col, pd.to_numeric(value, errors="coerce")
    if isinstance(value, list):
        return col.astype(str).str.lower(), [str(v).lower() for v in value]
    return col.astype(str).str.lower(), str(value).lower()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, bool):
        return value
    # numpy scalars subclass float/int, so coerce rather than pass through.
    if isinstance(value, float):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else round(f, 6)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (ValueError, TypeError):
            return str(value)
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except (ValueError, AttributeError):
            pass
    if pd.isna(value):
        return None
    return str(value)


def describe_frames(
    frames: Dict[str, pd.DataFrame], schemas: Optional[Dict[str, Dict]] = None
) -> str:
    """Compact schema block for the planning prompt. Sends no cell values."""
    schemas = schemas or {}
    parts: List[str] = []
    for key, df in frames.items():
        lines = [f'Source "{key}" ({len(df)} rows):']
        for c in df.columns:
            col = df[c]
            desc = f"  - {c} ({col.dtype})"
            if pd.api.types.is_numeric_dtype(col) and col.notna().any():
                desc += f" range {_jsonable(col.min())}..{_jsonable(col.max())}"
            elif pd.api.types.is_datetime64_any_dtype(col) and col.notna().any():
                desc += f" range {_jsonable(col.min())}..{_jsonable(col.max())}"
            else:
                n = int(col.nunique(dropna=True))
                desc += f" {n} distinct"
                if 0 < n <= 12:
                    vals = [str(v)[:30] for v in col.dropna().unique()[:12]]
                    desc += f" [{', '.join(vals)}]"
            lines.append(desc)
        meta = schemas.get(key) or {}
        roles = {
            k: meta.get(k)
            for k in ("primary_timeline", "primary_amount")
            if meta.get(k)
        }
        if roles:
            lines.append(f"  roles: {roles}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
