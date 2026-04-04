"""Compare metrics between current and previous time windows for executive-style summaries."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import pandas as pd

from services.daily_metrics import resolve_date_column, resolve_revenue_column

_EXPENSE_NAME = re.compile(
    r"(expense|spend|spending|cost|budget|marketing|campaign|payroll|overhead)",
    re.I,
)
_PROFIT_NAME = re.compile(r"(profit|margin|ebit|net_income|net income|p\/l)", re.I)


def _pct_change(prev: float, cur: float) -> Optional[float]:
    if prev == 0 and cur == 0:
        return 0.0
    if prev == 0:
        return None
    return round(100.0 * (cur - prev) / abs(prev), 1)


def _direction(prev: float, cur: float, eps_ratio: float = 0.005) -> str:
    if prev == 0 and cur == 0:
        return "flat"
    if prev == 0:
        return "up" if cur > 0 else "down" if cur < 0 else "flat"
    delta = (cur - prev) / abs(prev)
    if abs(delta) < eps_ratio:
        return "flat"
    return "up" if cur > prev else "down"


def _arrow(d: str) -> str:
    return "↑" if d == "up" else "↓" if d == "down" else "→"


def _fmt_money(v: float) -> str:
    av = abs(v)
    if av >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if av >= 1_000:
        return f"{v / 1_000:.2f}K"
    return f"{v:,.0f}"


def _window_mask(
    df: pd.DataFrame,
    date_col: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    ts = pd.to_datetime(df[date_col], errors="coerce")
    s = start.normalize()
    e = end.normalize()
    return ts.notna() & (ts.dt.normalize() >= s) & (ts.dt.normalize() <= e)


def _pick_expense_column(
    df: pd.DataFrame,
    metadata: dict[str, Any],
    exclude: set[str],
) -> Optional[str]:
    for col in df.columns:
        if col in exclude or col not in df.columns:
            continue
        if not _EXPENSE_NAME.search(str(col)):
            continue
        if pd.api.types.is_numeric_dtype(df[col]) or df[col].dtype == object:
            coerced = pd.to_numeric(df[col], errors="coerce")
            if coerced.notna().sum() > len(df) * 0.3:
                return col
    return None


def _pick_profit_column(df: pd.DataFrame, exclude: set[str]) -> Optional[str]:
    for col in df.columns:
        if col in exclude:
            continue
        if not _PROFIT_NAME.search(str(col)):
            continue
        coerced = pd.to_numeric(df[col], errors="coerce")
        if coerced.notna().sum() > len(df) * 0.3:
            return col
    return None


def _numeric_series_sum(df: pd.DataFrame, col: str, mask: pd.Series) -> float:
    if col not in df.columns:
        return 0.0
    sub = df.loc[mask, col]
    s = pd.to_numeric(sub, errors="coerce")
    return float(s.fillna(0).sum())


def _resolve_comparison_windows(
    df: pd.DataFrame,
    date_col: str,
    *,
    start_ts: Optional[pd.Timestamp],
    end_ts: Optional[pd.Timestamp],
    last_n_days: Optional[int],
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp, str]:
    """Returns cur_start, cur_end, prev_start, prev_end, description."""
    ts = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if ts.empty:
        raise ValueError("No valid dates")

    dmin = ts.min().normalize()
    dmax = ts.max().normalize()
    span_days = int((dmax - dmin).days) + 1

    if last_n_days is not None and last_n_days >= 1:
        cur_end = dmax
        cur_start = (cur_end - pd.Timedelta(days=int(last_n_days) - 1)).normalize()
        if cur_start < dmin:
            cur_start = dmin
        n = int((cur_end - cur_start).days) + 1
    elif start_ts is not None and end_ts is not None:
        cur_start = start_ts.normalize()
        cur_end = end_ts.normalize()
        if cur_start > cur_end:
            cur_start, cur_end = cur_end, cur_start
        n = int((cur_end - cur_start).days) + 1
    else:
        if span_days >= 14:
            n = min(30, max(7, span_days // 2))
        else:
            n = max(1, span_days // 2 or 1)
        cur_end = dmax
        cur_start = (cur_end - pd.Timedelta(days=n - 1)).normalize()
        if cur_start < dmin:
            cur_start = dmin
        n = int((cur_end - cur_start).days) + 1

    prev_end = (cur_start - pd.Timedelta(days=1)).normalize()
    prev_start = (prev_end - pd.Timedelta(days=n - 1)).normalize()
    if prev_start < dmin:
        prev_start = dmin

    desc = (
        f"{cur_start.strftime('%Y-%m-%d')}–{cur_end.strftime('%Y-%m-%d')} "
        f"vs {prev_start.strftime('%Y-%m-%d')}–{prev_end.strftime('%Y-%m-%d')}"
    )
    return cur_start, cur_end, prev_start, prev_end, desc


def _build_change_item(
    label: str,
    prev_v: float,
    cur_v: float,
    *,
    higher_is_better: bool = True,
    source_dataset: Optional[str] = None,
) -> dict[str, Any]:
    direction = _direction(prev_v, cur_v)
    good = (
        (direction == "up" and higher_is_better)
        or (direction == "down" and not higher_is_better)
        or direction == "flat"
    )
    pct = _pct_change(prev_v, cur_v)
    arrow = _arrow(direction)

    if direction == "flat":
        expl = f"{label} was steady compared to the previous period."
    elif pct is not None:
        adv = "increased" if direction == "up" else "decreased"
        delta_abs = cur_v - prev_v
        expl = (
            f"{label} {adv} {abs(pct)}% compared to the previous period "
            f"(about {_fmt_money(abs(delta_abs))})."
        )
    else:
        expl = (
            f"{label} moved from {_fmt_money(prev_v)} to {_fmt_money(cur_v)} vs the prior period "
            f"(prior period near zero—% change not shown)."
        )

    item: dict[str, Any] = {
        "label": label,
        "direction": direction,
        "arrow": arrow,
        "delta_pct": pct,
        "previous_value": prev_v,
        "current_value": cur_v,
        "explanation": expl.strip(),
        "higher_is_better": higher_is_better,
        "is_favorable": good,
    }
    if source_dataset:
        item["source_dataset"] = source_dataset
    return item


def build_what_changed_for_dataframe(
    df: pd.DataFrame,
    metadata: dict[str, Any],
    *,
    start_ts: Optional[pd.Timestamp] = None,
    end_ts: Optional[pd.Timestamp] = None,
    last_n_days: Optional[int] = None,
    source_dataset: Optional[str] = None,
) -> dict[str, Any]:
    """Return structured period-over-period deltas for one dataset."""
    empty: dict[str, Any] = {
        "period_description": "",
        "items": [],
        "highlights": [],
        "cross_metric_note": None,
        "available": False,
    }
    if df is None or len(df) < 2:
        return empty

    date_col = resolve_date_column(df, metadata)
    if not date_col:
        return empty

    try:
        c0, c1, p0, p1, desc = _resolve_comparison_windows(
            df, date_col, start_ts=start_ts, end_ts=end_ts, last_n_days=last_n_days
        )
    except ValueError:
        return empty

    m_cur = _window_mask(df, date_col, c0, c1)
    m_prev = _window_mask(df, date_col, p0, p1)
    if not m_cur.any() or not m_prev.any():
        return empty

    rev_col = resolve_revenue_column(df, metadata)
    exclude: set[str] = set()
    if rev_col:
        exclude.add(rev_col)

    items: list[dict[str, Any]] = []

    if rev_col:
        p_sum = _numeric_series_sum(df, rev_col, m_prev)
        c_sum = _numeric_series_sum(df, rev_col, m_cur)
        pretty = rev_col.replace("_", " ").title()
        items.append(
            _build_change_item(
                f"Revenue ({pretty})",
                p_sum,
                c_sum,
                higher_is_better=True,
                source_dataset=source_dataset,
            )
        )

    exp_col = _pick_expense_column(df, metadata, exclude)
    if exp_col:
        p_sum = _numeric_series_sum(df, exp_col, m_prev)
        c_sum = _numeric_series_sum(df, exp_col, m_cur)
        pretty = exp_col.replace("_", " ").title()
        items.append(
            _build_change_item(
                f"Expense ({pretty})",
                p_sum,
                c_sum,
                higher_is_better=False,
                source_dataset=source_dataset,
            )
        )

    prof_col = _pick_profit_column(df, exclude | ({exp_col} if exp_col else set()))
    if prof_col:
        p_sum = _numeric_series_sum(df, prof_col, m_prev)
        c_sum = _numeric_series_sum(df, prof_col, m_cur)
        pretty = prof_col.replace("_", " ").title()
        items.append(
            _build_change_item(
                f"Profit ({pretty})",
                p_sum,
                c_sum,
                higher_is_better=True,
                source_dataset=source_dataset,
            )
        )
    elif rev_col and exp_col:
        p_prof = _numeric_series_sum(df, rev_col, m_prev) - _numeric_series_sum(
            df, exp_col, m_prev
        )
        c_prof = _numeric_series_sum(df, rev_col, m_cur) - _numeric_series_sum(
            df, exp_col, m_cur
        )
        items.append(
            _build_change_item(
                "Profit (revenue − expense)",
                p_prof,
                c_prof,
                higher_is_better=True,
                source_dataset=source_dataset,
            )
        )

    if rev_col and exp_col:
        p_rev = _numeric_series_sum(df, rev_col, m_prev)
        c_rev = _numeric_series_sum(df, rev_col, m_cur)
        if p_rev > 0 or c_rev > 0:
            p_margin = (
                (p_rev - _numeric_series_sum(df, exp_col, m_prev)) / p_rev if p_rev else None
            )
            c_margin = (
                (c_rev - _numeric_series_sum(df, exp_col, m_cur)) / c_rev if c_rev else None
            )
            if p_margin is not None and c_margin is not None and p_margin == p_margin and c_margin == c_margin:
                delta_pts = round(100 * (c_margin - p_margin), 1)
                d = _direction(p_margin, c_margin, eps_ratio=0.002)
                arrow = _arrow(d)
                if abs(delta_pts) < 0.1:
                    margin_expl = "Profit margin was steady between this period and the last."
                elif delta_pts < 0:
                    margin_expl = (
                        f"Profit margin tightened by {abs(delta_pts)} points—costs or "
                        f"mix may be pressuring returns."
                    )
                else:
                    margin_expl = (
                        f"Profit margin widened by {delta_pts} points compared to the previous period."
                    )
                items.append({
                    "label": "Profit margin",
                    "direction": d,
                    "arrow": arrow,
                    "delta_pct": delta_pts,
                    "previous_value": round(100 * p_margin, 2),
                    "current_value": round(100 * c_margin, 2),
                    "explanation": margin_expl,
                    "higher_is_better": True,
                    "is_favorable": c_margin >= p_margin,
                })

    # Other significant numeric shifts (not duplicate labels)
    used_lower = {str(it["label"]).lower() for it in items}
    candidates: list[tuple[str, float, float, float]] = []
    for col in df.columns:
        if col == date_col or col in exclude:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        base = str(col).replace("_", " ").title()
        key = base.lower()
        if any(k in key for k in ("id", "index")):
            continue
        if key in used_lower:
            continue
        p_sum = _numeric_series_sum(df, col, m_prev)
        c_sum = _numeric_series_sum(df, col, m_cur)
        if p_sum == 0 and c_sum == 0:
            continue
        pct = _pct_change(p_sum, c_sum)
        if pct is None:
            sig = abs(c_sum - p_sum)
        else:
            sig = abs(pct)
        if sig >= 10 or (p_sum != 0 and abs((c_sum - p_sum) / max(abs(p_sum), 1)) >= 0.15):
            candidates.append((base, p_sum, c_sum, float(sig if pct is None else pct)))

    candidates.sort(key=lambda x: -x[3])
    for base, p_sum, c_sum, _ in candidates[:4]:
        pct = _pct_change(p_sum, c_sum)
        direction = _direction(p_sum, c_sum)
        arrow = _arrow(direction)
        if pct is not None:
            expl = (
                f"{base} moved {direction} about {abs(pct)}% period-over-period."
            )
        else:
            expl = (
                f"{base} shifted from {_fmt_money(p_sum)} to {_fmt_money(c_sum)} vs the prior window."
            )
        items.append({
            "label": base,
            "direction": direction,
            "arrow": arrow,
            "delta_pct": pct,
            "previous_value": p_sum,
            "current_value": c_sum,
            "explanation": expl,
            "higher_is_better": True,
            "is_favorable": True,
            **({"source_dataset": source_dataset} if source_dataset else {}),
        })

    def _score(it: dict[str, Any]) -> float:
        pct = it.get("delta_pct")
        if pct is None:
            return abs(float(it.get("current_value", 0)) - float(it.get("previous_value", 0)))
        return abs(float(pct))

    ranked = sorted(items, key=_score, reverse=True)
    priority = ("revenue", "expense", "profit", "margin")

    def _pri(it: dict[str, Any]) -> int:
        l = str(it.get("label", "")).lower()
        for i, p in enumerate(priority):
            if p in l:
                return -10 + i
        return 0

    ranked.sort(key=lambda it: (_pri(it), -_score(it)))
    highlights = ranked[:3]

    cross_note = _compose_cross_metric_line(items)

    return {
        "period_description": desc,
        "items": items,
        "highlights": highlights[:3],
        "cross_metric_note": cross_note or None,
        "available": True,
    }


def _compose_cross_metric_line(items: list[dict[str, Any]]) -> str:
    rev_i = next((i for i in items if "revenue" in str(i.get("label", "")).lower()), None)
    exp_i = next((i for i in items if "expense" in str(i.get("label", "")).lower()), None)
    if not rev_i or not exp_i:
        return ""
    rp = rev_i.get("delta_pct")
    ep = exp_i.get("delta_pct")
    if rp is None or ep is None:
        return ""
    if ep > rp + 3:
        return (
            "Spend grew faster than revenue—review campaign efficiency and "
            "fixed cost creep before you scale."
        )
    if rp > ep + 5 and ep >= 0:
        return (
            "Revenue outpaced spend this period—sanity-check attribution before you lock in the story."
        )
    return ""


def build_workspace_what_changed(
    dataset_pairs: list[tuple[Any, Any]],
    loader,
    *,
    start_ts: Optional[pd.Timestamp] = None,
    end_ts: Optional[pd.Timestamp] = None,
    last_n_days: Optional[int] = None,
) -> dict[str, Any]:
    """Merge what_changed across datasets; `loader(upload)->df`.

    When ``start_ts``/``end_ts`` (or ``last_n_days``) are set, each dataset is compared
    for that window vs the immediately preceding window of equal length.
    """
    all_items: list[dict[str, Any]] = []
    descriptions: list[str] = []
    for ds, up in dataset_pairs:
        try:
            df = loader(up)
        except Exception:
            continue
        meta = {}
        try:
            meta = json.loads(ds.schema_json) if ds.schema_json else {}
        except Exception:
            meta = {}
        block = build_what_changed_for_dataframe(
            df,
            meta,
            start_ts=start_ts if last_n_days is None else None,
            end_ts=end_ts if last_n_days is None else None,
            last_n_days=last_n_days,
            source_dataset=getattr(ds, "name", None) or "dataset",
        )
        if not block.get("available"):
            continue
        descriptions.append(block["period_description"])
        for it in block["items"]:
            all_items.append(it)

    if not all_items:
        return {
            "period_description": "",
            "items": [],
            "highlights": [],
            "cross_metric_note": None,
            "available": False,
        }

    by_key: dict[str, dict[str, Any]] = {}
    for it in all_items:
        key = f"{it.get('source_dataset', '')}:{it['label']}"
        if key not in by_key or abs(it.get("delta_pct") or 0) > abs(by_key[key].get("delta_pct") or 0):
            by_key[key] = it

    merged = list(by_key.values())

    def _score(it: dict[str, Any]) -> float:
        pct = it.get("delta_pct")
        if pct is None:
            return abs(float(it.get("current_value", 0)) - float(it.get("previous_value", 0)))
        return abs(float(pct))

    merged.sort(key=_score, reverse=True)
    highlights = merged[:3]
    period_note = descriptions[0] if descriptions else ""

    cross = _compose_cross_metric_line(merged)
    return {
        "period_description": period_note,
        "items": merged[:12],
        "highlights": highlights,
        "cross_metric_note": cross or None,
        "available": True,
    }
