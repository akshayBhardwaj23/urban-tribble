"""Threshold- and scan-based workspace alerts (signals), plus briefing hooks."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

import pandas as pd

from services.daily_metrics import resolve_date_column

_PRI_RANK = {"high": 0, "medium": 1, "low": 2}
_CAT_ORDER = {"risk": 0, "data_issue": 1, "efficiency": 2, "opportunity": 3}

_EXPENSE_PAT = re.compile(
    r"(expense|spend|cost|budget|campaign|marketing|payroll|overhead|fee|cpc|cpm)",
    re.I,
)
_ID_LIKE_PAT = re.compile(
    r"^(id|uuid|key|transaction_?id|order_?id|customer_?id|email)$", re.I
)


def _norm_priority(p: str) -> str:
    if p in _PRI_RANK:
        return p
    return "medium"


def _dedupe_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for a in alerts:
        key = f"{a.get('category')}:{str(a.get('title', '')).strip().lower()[:120]}"
        prev = seen.get(key)
        if not prev or _PRI_RANK.get(str(a.get("priority")), 1) < _PRI_RANK.get(
            str(prev.get("priority")), 1
        ):
            seen[key] = a
    return list(seen.values())


def _sort_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        alerts,
        key=lambda x: (
            _PRI_RANK.get(str(x.get("priority")), 1),
            _CAT_ORDER.get(str(x.get("category")), 9),
            str(x.get("title", "")),
        ),
    )


def _alerts_from_what_changed(wc: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not wc.get("available"):
        return out

    cross = wc.get("cross_metric_note")
    if isinstance(cross, str) and cross.strip():
        cl = cross.lower()
        if "spend grew faster than revenue" in cl or "faster than revenue" in cl:
            out.append({
                "id": "signal:spend_outpaces_revenue",
                "title": "Spend is outpacing revenue",
                "detail": cross.strip(),
                "category": "risk",
                "priority": "high",
                "source": "signal",
            })
        elif "revenue outpaced spend" in cl:
            out.append({
                "id": "signal:revenue_outpaced_spend",
                "title": "Revenue grew faster than spend",
                "detail": cross.strip(),
                "category": "opportunity",
                "priority": "medium",
                "source": "signal",
            })

    for idx, it in enumerate(wc.get("items") or []):
        unfav = it.get("is_favorable") is False
        pct = it.get("delta_pct")
        mag = abs(float(pct)) if pct is not None else 0.0
        label = str(it.get("label", ""))
        expl = str(it.get("explanation", "")).strip()
        if not expl:
            continue
        short_label = label.replace("(", "").replace(")", "")[:56]
        if unfav and mag >= 12:
            out.append({
                "id": f"signal:unfavorable:{idx}",
                "title": f"Pullback: {short_label}",
                "detail": expl,
                "category": "risk",
                "priority": "high" if mag >= 22 else "medium",
                "source": "signal",
            })
        elif it.get("is_favorable") is True and mag >= 15:
            out.append({
                "id": f"signal:favorable:{idx}",
                "title": f"Momentum: {short_label}",
                "detail": expl,
                "category": "opportunity",
                "priority": "medium" if mag < 28 else "high",
                "source": "signal",
            })

    return out


def _pick_expense_col(df: pd.DataFrame, metadata: dict[str, Any], exclude: set[str]) -> Optional[str]:
    for c in df.columns:
        if c in exclude or not _EXPENSE_PAT.search(str(c)):
            continue
        coerced = pd.to_numeric(df[c], errors="coerce")
        if coerced.notna().sum() > max(5, len(df) * 0.2):
            return c
    return None


def _scan_single_dataset(
    df: pd.DataFrame,
    dataset_name: str,
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = len(df)
    if n < 3:
        return out

    dup_n = int(df.duplicated().sum())
    if dup_n > 0:
        ratio = dup_n / n
        if ratio >= 0.02:
            out.append({
                "id": f"data:dup_full:{dataset_name[:24]}",
                "title": "Duplicate rows detected",
                "detail": (
                    f"{dataset_name}: {dup_n:,} exact duplicate rows ({ratio * 100:.1f}% of file). "
                    "Totals and pivots may be inflated—dedupe or filter before trusting headline metrics."
                ),
                "category": "data_issue",
                "priority": "high" if ratio >= 0.08 else "medium",
                "source": "data_quality",
            })

    id_candidates = [
        c for c in df.columns if _ID_LIKE_PAT.search(str(c).strip())
    ][:3]
    for col in id_candidates:
        if col not in df.columns:
            continue
        vc = df[col].astype(str).value_counts()
        dup_keys = int((vc > 1).sum())
        if dup_keys == 0:
            continue
        repeated = int((vc[vc > 1]).sum())
        if repeated >= max(3, n // 50):
            out.append({
                "id": f"data:dup_key:{dataset_name[:16]}:{col}",
                "title": f"Non-unique keys in `{col}`",
                "detail": (
                    f"{dataset_name}: `{col}` has {dup_keys} values repeated across rows. "
                    "Joins and revenue rollups can double-count—inspect before you report."
                ),
                "category": "data_issue",
                "priority": "high" if repeated > n * 0.05 else "medium",
                "source": "data_quality",
            })
            break

    date_col = resolve_date_column(df, metadata)
    if date_col and date_col in df.columns:
        parsed = pd.to_datetime(df[date_col], errors="coerce")
        null_pct = float(parsed.isna().mean()) * 100
        if null_pct >= 12:
            out.append({
                "id": f"data:sparse_dates:{dataset_name[:20]}",
                "title": "Many missing dates",
                "detail": (
                    f"{dataset_name}: {null_pct:.0f}% of `{date_col}` could not be parsed to dates. "
                    "Time comparisons and alerts will be unreliable until dates are cleaned."
                ),
                "category": "data_issue",
                "priority": "high" if null_pct >= 28 else "medium",
                "source": "data_quality",
            })

    rev_cols = [c for c in metadata.get("revenue_columns", []) if c in df.columns]
    cat_cols = [c for c in metadata.get("category_columns", []) if c in df.columns]
    exp_col = _pick_expense_col(df, metadata, set(rev_cols))

    if cat_cols and rev_cols and exp_col:
        cat_col = cat_cols[0]
        rev_col = rev_cols[0]
        sub = df[[cat_col, rev_col, exp_col]].copy()
        for c in (rev_col, exp_col):
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        sub = sub.dropna(subset=[cat_col])
        g = sub.groupby(cat_col, dropna=False)[[rev_col, exp_col]].sum()
        g = g[g[exp_col] > 0]
        if len(g) >= 2:
            tot_r, tot_e = g[rev_col].sum(), g[exp_col].sum()
            if tot_e > 0 and tot_r >= 0:
                g_share_e = g[exp_col] / tot_e
                g_share_r = g[rev_col] / max(tot_r, 1e-9)
                g["roi"] = g[rev_col] / g[exp_col]
                worst = g.sort_values("roi").iloc[0]
                worst_cat = str(worst.name)[:48]
                se = float(g_share_e.loc[worst.name])
                sr = float(g_share_r.loc[worst.name])
                med_roi = float(g["roi"].median())
                if worst["roi"] < med_roi * 0.45 and se >= 0.14 and sr <= 0.22:
                    out.append({
                        "id": f"efficiency:campaign:{dataset_name[:12]}:{worst_cat[:20]}",
                        "title": "High spend, weak return in one segment",
                        "detail": (
                            f"{dataset_name}: category “{worst_cat}” drives ~{se * 100:.0f}% of spend but only "
                            f"~{sr * 100:.0f}% of revenue—reallocate or prove incremental lift before scaling."
                        ),
                        "category": "efficiency",
                        "priority": "high" if se >= 0.28 else "medium",
                        "source": "signal",
                    })

    return out


def _map_insight_to_category(
    insight: dict[str, Any],
) -> tuple[str, str]:
    """Return (category, priority_hint)."""
    text = " ".join(
        str(insight.get(k, ""))
        for k in ("headline", "finding", "why_it_matters", "recommended_action")
    ).lower()
    typ = str(insight.get("type", "neutral"))

    if re.search(
        r"duplicate|null|missing|invalid|quality|schema|parse|nan|data issue|artifact",
        text,
    ):
        return "data_issue", "medium"
    if re.search(
        r"efficien|roi|conversion|waste|leak|throughput|bottleneck|utilization|cpc|cpa|campaign",
        text,
    ):
        return "efficiency", "medium"
    if typ == "negative":
        return "risk", "medium"
    if typ == "positive":
        return "opportunity", "medium"
    if re.search(r"concentration|exposure|risk|downside|pressure", text):
        return "risk", "medium"
    if re.search(r"growth|upside|expand|outperform", text):
        return "opportunity", "low"
    return "efficiency", "low"


def _confidence_to_priority(insight: dict[str, Any], base: str) -> str:
    conf = str(insight.get("confidence", "") or "")
    m = re.match(r"^\s*(high|medium|low)\b", conf, re.I)
    band = m.group(1).lower() if m else ""
    if band == "high":
        return "high" if base == "risk" or insight.get("type") == "negative" else "medium"
    if band == "low":
        return "low" if insight.get("type") == "positive" else "medium"
    return _norm_priority(base)


def _alerts_from_analysis(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for i, raw in enumerate(analysis.get("top_priorities") or []):
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind", "")).lower()
        title = str(raw.get("title", "")).strip()
        expl = str(raw.get("explanation", "")).strip()
        if not title or not expl:
            continue
        pri = _norm_priority(str(raw.get("priority", "medium")))
        if kind == "risk":
            cat = "risk"
        elif kind == "opportunity":
            cat = "opportunity"
        elif kind in ("inefficiency", "anomaly"):
            cat = "efficiency" if kind == "inefficiency" else "data_issue"
        else:
            cat = "opportunity"
        out.append({
            "id": f"briefing:priority:{i}",
            "title": title[:120],
            "detail": expl[:480],
            "category": cat,
            "priority": pri,
            "source": "briefing",
        })

    for i, raw in enumerate(analysis.get("anomalies") or []):
        if not isinstance(raw, dict):
            continue
        desc = str(raw.get("description", "")).strip()
        if not desc:
            continue
        sev = _norm_priority(str(raw.get("severity", "medium")))
        out.append({
            "id": f"briefing:anomaly:{i}",
            "title": "Data or metric anomaly",
            "detail": desc[:480],
            "category": "data_issue",
            "priority": sev,
            "source": "briefing",
        })

    insights_raw = [x for x in (analysis.get("insights") or []) if isinstance(x, dict)]

    def _ins_rank(x: dict[str, Any]) -> tuple[int, int]:
        t = x.get("type")
        tier = 0 if t == "negative" else 1 if t == "neutral" else 2
        conf = str(x.get("confidence", "") or "")
        m = re.match(r"^\s*(high|medium|low)\b", conf, re.I)
        pr = {"high": 0, "medium": 1, "low": 2}.get(m.group(1).lower() if m else "", 1)
        return tier, pr

    insights_raw.sort(key=_ins_rank)
    for i, raw in enumerate(insights_raw[:8]):
        headline = str(raw.get("headline", "")).strip()
        finding = str(raw.get("finding", "")).strip()
        why = str(raw.get("why_it_matters", "")).strip()
        action = str(raw.get("recommended_action", "")).strip()
        if not headline and not finding:
            continue
        title = headline or finding[:90]
        detail_parts = [x for x in (finding, why, action) if x]
        detail = " ".join(detail_parts)[:520]
        cat, _ = _map_insight_to_category(raw)
        pri = _confidence_to_priority(raw, "medium")
        if cat == "risk" and raw.get("type") == "negative":
            pri = "high" if pri == "medium" else pri
        out.append({
            "id": f"briefing:insight:{i}",
            "title": title[:120],
            "detail": detail,
            "category": cat,
            "priority": pri,
            "source": "briefing",
        })

    return out


def build_workspace_alerts(
    what_changed: dict[str, Any],
    dataset_pairs: list[tuple[Any, Any]],
    loader: Callable[[Any], pd.DataFrame],
    analysis_json: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Assemble actionable alerts for the workspace overview."""
    alerts: list[dict[str, Any]] = []
    alerts.extend(_alerts_from_what_changed(what_changed))

    for ds, up in dataset_pairs:
        try:
            df = loader(up)
        except Exception:
            continue
        meta: dict[str, Any] = {}
        try:
            meta = json.loads(ds.schema_json) if ds.schema_json else {}
        except Exception:
            meta = {}
        name = getattr(ds, "name", None) or "Dataset"
        alerts.extend(_scan_single_dataset(df, name, meta))

    if analysis_json and isinstance(analysis_json, dict):
        alerts.extend(_alerts_from_analysis(analysis_json))

    merged = _dedupe_alerts(alerts)
    return _sort_alerts(merged)[:24]
