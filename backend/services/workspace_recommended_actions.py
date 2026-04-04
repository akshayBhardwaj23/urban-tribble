"""Prioritized, operator-style recommended actions merged from briefing, alerts, and signals."""

from __future__ import annotations

import re
from typing import Any, Optional

_PRI_RANK = {"high": 0, "medium": 1, "low": 2}

_FLUFF = re.compile(
    r"\b(interesting|notable|valuable insight|pay attention to the data|monitor closely|"
    r"stay tuned|keep an eye|be mindful|general observations?)\b",
    re.I,
)
_WEAK_LEAD = re.compile(
    r"^(the |this )?(data|dataset|analysis|situation|overall)\b",
    re.I,
)
_VERB_START = re.compile(
    r"^(review|investigate|reallocate|cut|pause|freeze|assign|schedule|validate|confirm|"
    r"reconcile|audit|triage|export|slice|break out|double-check|pull|compare|trim|"
    r"cap|redirect|escalate|align|pressure-test|dedupe|fix|re-run|hold|"
    r"stop|start|build|document|segment|rank|prioritize|meeting|call|walk)\b",
    re.I,
)


def _truncate(s: str, max_len: int = 220) -> str:
    t = " ".join(s.split())
    if len(t) <= max_len:
        return t
    cut = t[: max_len - 1].rsplit(" ", 1)[0]
    return cut + "…"


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()[:120]


def _is_weak(text: str) -> bool:
    t = text.strip()
    if len(t) < 18:
        return True
    if _FLUFF.search(t):
        return True
    if _WEAK_LEAD.search(t) and not _VERB_START.match(t):
        return True
    if re.match(r"^(the|this)\s+\w+\s+(shows|indicates|suggests)\b", t, re.I):
        return True
    return False


def _priority_from_str(p: str) -> str:
    p = (p or "medium").lower().strip()
    return p if p in _PRI_RANK else "medium"


def _priority_from_alert(a: dict[str, Any]) -> str:
    return _priority_from_str(str(a.get("priority", "medium")))


def _alert_to_action(alert: dict[str, Any]) -> Optional[str]:
    title = str(alert.get("title", "")).strip()
    detail = str(alert.get("detail", "")).strip()
    cat = str(alert.get("category", ""))
    if not title and not detail:
        return None

    tl = title.lower()
    if "spend is outpacing revenue" in tl or "outpacing revenue" in tl:
        return (
            "Review top spend owners and campaigns against revenue attribution; freeze "
            "incremental spend until finance signs off on the story."
        )
    if "duplicate rows" in tl or ("duplicate" in tl and cat == "data_issue"):
        return (
            "Dedupe or filter the flagged rows before the next leadership read so KPIs "
            "are not double-counted."
        )
    if "missing dates" in tl or "non-unique keys" in tl:
        return (
            "Fix source exports—dates and keys—before anyone bets on period-over-period "
            "comparisons from this workspace."
        )
    if "high spend" in tl and "weak return" in tl:
        return (
            "Review the top three segments by spend, cut or cap underperformers, and "
            "reallocate dollars toward higher-performing regions or campaigns."
        )
    if cat == "risk" or "pullback" in tl:
        base = detail if len(detail) > 40 else title
        if _is_weak(base):
            return None
        if not _VERB_START.match(base):
            return _truncate(f"Investigate and contain: {base}")
        return _truncate(base)
    if cat == "opportunity":
        base = detail if len(detail) > 48 else title
        if _is_weak(base):
            return None
        if not _VERB_START.match(base):
            return _truncate(f"Validate then scale: {base}")
        return _truncate(base)
    if cat == "efficiency" and detail and len(detail) > 35 and not _is_weak(detail):
        return _truncate(
            detail if _VERB_START.match(detail) else f"Triage and fix: {detail}",
        )
    if detail and len(detail) > 35 and not _is_weak(detail):
        return _truncate(
            detail if _VERB_START.match(detail) else f"Assign an owner to: {detail}",
        )
    return None


def _what_changed_actions(wc: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not wc.get("available"):
        return out
    cross = wc.get("cross_metric_note")
    if isinstance(cross, str) and cross.strip():
        cl = cross.lower()
        if "spend grew faster than revenue" in cl or "faster than revenue" in cl:
            out.append((
                "high",
                "Investigate rising employee and vendor expenses before the next billing "
                "cycle; pair HR or procurement with finance on the top five accounts.",
            ))
        elif "revenue outpaced spend" in cl:
            out.append((
                "medium",
                "Reallocate budget toward higher-performing regions or campaigns once "
                "you confirm the uplift is not a timing artifact.",
            ))
    for it in wc.get("highlights") or []:
        if it.get("is_favorable") is False:
            lab = str(it.get("label", ""))
            expl = str(it.get("explanation", "")).strip()
            if re.search(r"expense|spend|cost|payroll", lab + " " + expl, re.I):
                if expl and not _is_weak(expl):
                    out.append((
                        "medium",
                        _truncate(f"Investigate this cost move with your lead: {expl}"),
                    ))
            break
    return out


def _from_top_priority(raw: dict[str, Any]) -> Optional[tuple[str, str]]:
    kind = str(raw.get("kind", "")).lower().replace(" ", "_")
    title = str(raw.get("title", "")).strip()
    expl = str(raw.get("explanation", "")).strip()
    pri = _priority_from_str(str(raw.get("priority", "medium")))
    if not title or not expl:
        return None
    if kind in ("next_action", "nextaction"):
        action = title if _VERB_START.match(title) else _truncate(f"{title} — {expl}")
    elif kind == "risk":
        action = (
            title if _VERB_START.match(title) else _truncate(f"Address risk: {title}. {expl}")
        )
    elif kind == "opportunity":
        action = (
            title
            if _VERB_START.match(title)
            else _truncate(f"Stage the win: {title}. {expl}")
        )
    elif kind in ("inefficiency", "anomaly"):
        action = (
            title
            if _VERB_START.match(title)
            else _truncate(f"Resolve: {title}. {expl}")
        )
    else:
        action = _truncate(f"{title}. {expl}")
    if _is_weak(action):
        return None
    return pri, _truncate(action, 240)


def build_recommended_actions(
    analysis: Optional[dict[str, Any]],
    alerts: list[dict[str, Any]],
    what_changed: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[tuple[int, str, str, str]] = []
    seen: set[str] = set()

    def push(pri_s: str, action: str, source: str) -> None:
        action = action.strip()
        if not action or _is_weak(action):
            return
        k = _norm_key(action)
        if k in seen:
            return
        seen.add(k)
        rank = _PRI_RANK.get(pri_s, 1)
        candidates.append((rank, action, source, pri_s))

    if analysis and isinstance(analysis, dict):
        for raw in analysis.get("top_priorities") or []:
            if not isinstance(raw, dict):
                continue
            got = _from_top_priority(raw)
            if got:
                push(got[0], got[1], "briefing")

        for ins in analysis.get("insights") or []:
            if not isinstance(ins, dict):
                continue
            ra = str(ins.get("recommended_action", "")).strip()
            if not ra or _is_weak(ra):
                continue
            typ = str(ins.get("type", "neutral"))
            pri = "high" if typ == "negative" else "medium"
            push(pri, _truncate(ra, 240), "briefing")

        for rec in analysis.get("recommendations") or []:
            if isinstance(rec, str) and rec.strip() and not _is_weak(rec.strip()):
                push("medium", _truncate(rec.strip(), 240), "briefing")

    for pri_s, line in _what_changed_actions(what_changed):
        push(pri_s, line, "signal")

    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        act = _alert_to_action(alert)
        if act:
            push(_priority_from_alert(alert), act, str(alert.get("source", "signal")))

    candidates.sort(key=lambda x: (x[0], x[1][:40]))
    out: list[dict[str, Any]] = []
    for i, (_r, action, source, pri_s) in enumerate(candidates[:5]):
        out.append({
            "id": f"rec:{i}",
            "action": action,
            "priority": pri_s,
            "source": source,
        })
    return out
