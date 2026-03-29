from __future__ import annotations

import json
from typing import Optional

from openai import OpenAI

from config import settings

SYSTEM_PROMPT = """You are a sharp business analyst writing for founders, operators, finance owners, and line managers. They want conclusions and tradeoffs—not a tour of the file.

You receive: (1) optional user description of the file, (2) column metadata (date, revenue, category, numeric, etc.), (3) statistical summaries.

Return one JSON object only, with this structure:
{
  "executive_summary": "string",
  "top_priorities": [ ... ],
  "key_metrics": [ ... ],
  "insights": [ ... ],
  "anomalies": [ ... ],
  "recommendations": [ ... ]
}

Voice (non-negotiable):
- Calm, direct, plain English. Short sentences. Commercially aware.
- Always tie observations to a business implication where possible (revenue, margin, efficiency, risk, concentration, spend, growth).
- Avoid broad praise ("strong", "good", "healthy", "solid") unless you immediately add the mechanism, metric, or caveat.
- Avoid phrases that could describe any dataset ("interesting trend", "the data shows", "overall picture").
- Prefer neutral, evidence-based wording; use uncertainty honestly when the summaries are thin.
- Every sentence should help an owner decide, validate, or reallocate—not fill space.

Preferred frames when inference is partial or data is incomplete (use with substance, never as filler):
- "This may indicate…", "This suggests that…" (only when not fully provable from the numbers)
- "This reduces reliance on…" / "This increases exposure to…" for mix and concentration
- "This should be reviewed because…"
- "This is directionally positive, but…" for qualified upside
- "This is worth validating against…" for next checks
If something is certain from the summaries, state it plainly—do not hedge with "suggests" for fully supported facts.

Confidence calibration (non-negotiable—must match the evidence and the label you assign):
- Start every insight "confidence" field with exactly "High —", "Medium —", or "Low —" (capital H/M/L, em dash, space) so downstream parsing stays reliable.
- HIGH: In "finding" and "why_it_matters", use direct language ("is likely", "puts pressure on", "is reducing margin") only when the statistical summaries clearly support the claim. State well-supported facts plainly.
- MEDIUM: In "finding" and "why_it_matters", use measured language ("appears", "may be", "suggests", "tends to") and allow that another read is possible when fields, time range, or definitions are incomplete.
- LOW: In "finding" and/or "why_it_matters", use careful language ("may indicate", "could reflect"); explicitly say the takeaway should be validated with more complete or specific data and name what is missing (cost detail, longer history, segment split, dollar-weighting, etc.). Avoid definitive causal language.
- Do not sound more certain in the prose than the confidence label implies.

Banned vocabulary and patterns (do not use these or close paraphrases):
- "balanced distribution", "significant spending", "interesting trend", "notable pattern", "valuable insight"
- "strong performance" / "solid results" without naming the metric and why
- Headline-style stacks of adjectives ("robust diversified growth trajectory")
- Describing the dataset ("The file contains…", "This data shows columns…") instead of the business

Good vs bad (match the good style):
- BAD: "Balanced regional revenue distribution indicates stability."
- GOOD: "Revenue is spread relatively evenly across regions, so you are less dependent on a single geography."
- BAD: "Marketing channels are performing well."
- GOOD: "Campaign-attributed revenue is material; validate return against spend before you increase budget."

"executive_summary": 1-2 sentences. Net position + whether to act now, watch, or dig deeper. No bullets. Hedge only as much as your weakest material insight warrants—if several insights are Low confidence, keep the summary more cautious and name what data would tighten the read.

"top_priorities": exactly 3 to 5 objects. Order by operational urgency (most urgent first). Each object:
  {"kind": "risk|opportunity|inefficiency|anomaly|next_action", "priority": "high|medium|low", "title": "short decisive headline (max ~10 words)", "explanation": "one sentence: consequence or assigned move—no fluff"}
  Cover the main downside, main upside, material cost or process drag if supported, worst data/trust issue if any, and exactly one next_action for the single most important move. Do not paste the executive_summary.

"key_metrics": 3-8 objects: {"label", "value" (formatted string), "trend": "up|down|stable", "note": "one line: how this figure should change a hire, budget, cut, or reallocation decision—not repeating the label", optional "trace": {"file_name", "sheet_name", "columns_used": ["col_a"], "date_range", "row_count", "caveats": ["string"]}}

"insights": 4-8 objects. EACH must read like executive commentary, not a summary. Prefer ONE clear sentence per text field when possible.
  Structure each insight to answer: (1) What happened? (2) Why does it matter for revenue, margin, efficiency, risk, concentration, spend, or growth? (3) What should leadership watch or do?
  Fields:
  "headline": "4-9 words, operator-brief title—concrete and specific. GOOD: Revenue concentration risk, Margin pressure vs prior period, Uneven campaign efficiency, Cost growth outpacing sales, Data quality limiting confidence. BAD: Revenue analysis, Marketing insights, Business observations, Trend detection, Customer spending summary.",
  "finding": "one tight sentence: the fact and immediate read; complements the headline without repeating it verbatim—wording must match the confidence band (direct vs measured vs careful per calibration rules)",
  "why_it_matters": "business consequence if ignored—planning, capital, or accountability; tone must match the same confidence band",
  "likely_cause": "one short working hypothesis from the summaries, or what data would be needed to explain it—no vague 'market conditions'",
  "recommended_action": "one imperative: what to watch, validate, or assign this week",
  "confidence": "High|Medium|Low — short reason (thin time range, missing fields, etc.)",
  "source_reference": "the number, column, or comparison this rests on—not narration",
  "type": "positive|negative|neutral",
  optional "trace": same shape as key_metrics — when the insight depends on a specific file, columns, or time slice
  optional "caveats": 0-3 short strings—[] when none

Vary angles when the data allows: growth vs margin, concentration, cost creep, channel or campaign efficiency, repeat behavior only if columns support it. If the data has trust gaps, say so in at least one insight.

"anomalies": {"description", "severity": "high|medium|low"} for issues that distort KPIs or decisions.

"recommendations": 0-4 cross-cutting moves not duplicated in an insight's recommended_action; [] if none.

Valid JSON only."""


class AIAnalyzer:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    def analyze(
        self,
        data_summary: dict,
        column_metadata: dict,
        user_description: Optional[str] = None,
    ) -> dict:
        if not self.client:
            return self._fallback_analysis(data_summary, column_metadata)

        user_message = self._build_prompt(data_summary, column_metadata, user_description)

        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def _build_prompt(
        self,
        data_summary: dict,
        column_metadata: dict,
        user_description: Optional[str],
    ) -> str:
        parts = []
        if user_description:
            parts.append(f"File description: {user_description}")
        parts.append(f"Column metadata: {json.dumps(column_metadata, indent=2)}")
        parts.append(f"Data summary: {json.dumps(data_summary, indent=2)}")
        parts.append(
            "Produce the JSON: top_priorities (3–5), executive headline, key_metrics with decision-linked notes, "
            "insights as tight executive commentary (what happened, why it matters, what to watch—minimal filler), "
            "anomalies, and non-duplicate recommendations. Follow the tone rules in the system message."
        )
        return "\n\n".join(parts)

    def _fallback_analysis(self, data_summary: dict, column_metadata: dict) -> dict:
        """Basic analysis when no OpenAI key is configured."""
        metrics = []
        insights = []

        for col in column_metadata.get("revenue_columns", []):
            total = data_summary.get(f"{col}_total")
            mean = data_summary.get(f"{col}_mean")
            if total is not None:
                metrics.append({
                    "label": f"Total {col.replace('_', ' ').title()}",
                    "value": f"{total:,.2f}",
                    "trend": "stable",
                    "note": (
                        f"Ingest-level sum; mean row ≈ {mean:,.2f}—confirm gross vs net before you size bets."
                        if mean is not None
                        else "Ingest-level sum—confirm definition before committing spend or targets."
                    ),
                })

        rows = data_summary.get("rows", 0)
        cols = data_summary.get("columns", 0)
        metrics.append({
            "label": "Dataset size",
            "value": f"{rows} rows × {cols} columns",
            "trend": "stable",
            "note": "Scope only—pair with revenue or cost fields for a real decision read.",
        })

        for col in column_metadata.get("category_columns", []):
            top_vals = data_summary.get(f"{col}_top_values", {})
            if top_vals:
                top_item = max(top_vals, key=top_vals.get) if top_vals else None
                if top_item:
                    count = top_vals[top_item]
                    insights.append({
                        "headline": (
                            f"Category mix skews to '{str(top_item)[:32]}"
                            f"{'…' if len(str(top_item)) > 32 else ''}'"
                        ),
                        "finding": (
                            f"Row counts cluster on '{top_item}' in `{col}` ({count}), "
                            "which may indicate blended KPIs overweight that segment until you break the mix out."
                        ),
                        "why_it_matters": (
                            "This may increase exposure to mis-stated plans if one top-line number hides weaker pockets elsewhere."
                        ),
                        "likely_cause": "Real concentration, or defaults/duplicates in the export.",
                        "recommended_action": (
                            f"This should be reviewed because targets and budgets should be sliced by `{col}` "
                            f"before you lock them—confirm whether '{top_item}' is real volume or a data artifact."
                        ),
                        "confidence": "Medium — row counts only, not dollar-weighted",
                        "source_reference": f"`{col}_top_values['{top_item}']` = {count}",
                        "type": "neutral",
                        "caveats": [
                            "Row mix may not match revenue mix.",
                        ],
                    })

        insights.insert(
            0,
            {
                "headline": "Briefing running without model interpretation",
                "finding": (
                    "The API is in fallback mode (counts and rules only), which means drivers, cohorts, "
                    "and softer commercial signals are not interpreted in this pass."
                ),
                "why_it_matters": (
                    "This should be reviewed before pricing, cuts, or capital moves you would normally "
                    "pressure-test with a full briefing."
                ),
                "likely_cause": "OPENAI_API_KEY is not set on the backend.",
                "recommended_action": (
                    "Set OPENAI_API_KEY in backend/.env, restart the API, and re-run so tradeoffs surface with evidence."
                ),
                "confidence": "High — configuration state",
                "source_reference": "Backend configuration",
                "type": "negative",
                "caveats": [
                    "No model-generated interpretation until the key is set.",
                ],
            },
        )

        top_priorities = [
            {
                "kind": "risk",
                "priority": "high",
                "title": "Briefing is running without the model",
                "explanation": (
                    "This increases exposure to acting on structure checks alone—avoid pricing, cuts, or capital calls until the full pass runs."
                ),
            },
            {
                "kind": "next_action",
                "priority": "high",
                "title": "Enable the model-backed briefing",
                "explanation": (
                    "Set OPENAI_API_KEY, restart the API, and re-run so risks and moves tie to your actual summaries."
                ),
            },
        ]
        if len(insights) > 1:
            skew = insights[-1]
            top_priorities.insert(
                1,
                {
                    "kind": "inefficiency",
                    "priority": "medium",
                    "title": "Category mix may be bending headline KPIs",
                    "explanation": skew.get("why_it_matters", "")[:220]
                    or (
                        "This may indicate one segment label is doing the work of the whole business in blended metrics—"
                        "slice before you lock targets."
                    ),
                },
            )

        return {
            "executive_summary": (
                f"This extract covers {rows} rows × {cols} columns in mechanical scope only until the model is enabled. "
                + (
                    f"Revenue-style columns detected: {', '.join(column_metadata.get('revenue_columns', []))}. "
                    if column_metadata.get("revenue_columns")
                    else ""
                )
                + "This should be reviewed because strategic reads on downside, upside, and next moves require the full briefing."
            ),
            "top_priorities": top_priorities[:5],
            "key_metrics": metrics,
            "insights": insights,
            "anomalies": [],
            "recommendations": [],
        }
