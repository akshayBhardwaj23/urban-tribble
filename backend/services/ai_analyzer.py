from __future__ import annotations

import json
from typing import Optional

from openai import OpenAI

from config import settings

SYSTEM_PROMPT = """You are a senior business analyst advising an owner or general manager. Your job is not to describe the spreadsheet; it is to interpret what the numbers imply for revenue, cost, cash, and risk—and what to do next.

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

Tone and quality rules:
- Specific, concise, commercially relevant, decision-oriented. Plain English.
- Never use short label-style "findings" that only restate a pattern (e.g. avoid: "Balanced regional revenue distribution", "Significant customer spending", "High revenue from marketing campaigns").
- Instead write full-sentence takeaways that state the business implication, e.g. "Revenue is evenly distributed across regions, so growth is not dependent on a single geography." or "Customer spend is strong, but order frequency appears lower than expected."
- Every non-trivial claim should tie to a specific value, ratio, column, or time window from the summaries.
- If the data cannot support a claim, say what is missing instead of inventing.

"executive_summary": 1-2 sentences. Net situation + whether to act now, watch, or dig deeper. No bullet list.

"top_priorities": exactly 3 to 5 objects for a founder scanning the page in seconds. Order by operational urgency (most urgent first). Each object:
  {"kind": "risk|opportunity|inefficiency|anomaly|next_action", "priority": "high|medium|low", "title": "short decisive headline (max ~10 words)", "explanation": "one sentence only: practical consequence or what to do"}
  Rules: Cover the biggest risk, biggest opportunity, material inefficiency or waste (omit if unsupported), worst data/trust issue as anomaly (omit if none), and exactly one next_action for the single most important assigned move. Do not restate the executive_summary verbatim. No filler adjectives.

"key_metrics": 3-8 objects: {"label", "value" (formatted string), "trend": "up|down|stable", "note": "one line: how this number should change a decision (budget, hire, cut, reallocate)—not a restatement of the label", optional "trace": {"file_name", "sheet_name", "columns_used": ["col_a"], "date_range", "row_count", "caveats": ["string"]}}

"insights": 4-8 objects. EACH must include:
  "finding": "one or two short sentences: assertive takeaway with commercial meaning (not a stacked adjective phrase)",
  "why_it_matters": "1-2 sentences: consequence for planning, capital, accountability, or growth (e.g. what breaks if ignored)",
  "likely_cause": "specific hypothesis grounded in the data or domain; not vague 'market conditions'",
  "recommended_action": "one imperative an owner can assign this week",
  "confidence": "High|Medium|Low — short reason (e.g. 'Low — sparse months in Q2')",
  "source_reference": "exact stat, column, or comparison used",
  "type": "positive|negative|neutral",
  optional "trace": same shape as key_metrics trace — fill when the insight clearly depends on a specific file, columns, or time slice (workspace overviews: name the dataset file when possible)
  optional "caveats": 0-3 short strings if this insight is weakened by missing fields, duplicates, inconsistent column labels, incomplete attribution, thin sample, or mixed granularities—use [] when none

When the data allows, vary angles: growth vs profit, cost creep, concentration (product/region/campaign), margin vs volume, repeat or cohort behavior only if columns support it. Include at least one insight on data limits if there are gaps, duplicates, missing keys, or suspicious distributions.

"anomalies": {"description", "severity": "high|medium|low"} for issues that distort KPIs or trust.

"recommendations": 0-4 cross-cutting actions not already duplicated in an insight's recommended_action; use [] if none needed.

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
            "Produce the JSON: top_priorities (3–5 rows), headline for leadership, key figures with decision-linked notes, "
            "structured insights (full-sentence takeaways—not label-style headings), "
            "anomalies, and only non-duplicate cross-cutting recommendations."
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
                    "note": f"Average: {mean:,.2f}" if mean else "",
                })

        rows = data_summary.get("rows", 0)
        cols = data_summary.get("columns", 0)
        metrics.append({"label": "Dataset Size", "value": f"{rows} rows x {cols} columns", "trend": "stable", "note": ""})

        for col in column_metadata.get("category_columns", []):
            top_vals = data_summary.get(f"{col}_top_values", {})
            if top_vals:
                top_item = max(top_vals, key=top_vals.get) if top_vals else None
                if top_item:
                    count = top_vals[top_item]
                    insights.append({
                        "finding": (
                            f"`{col}` is heavily skewed to '{top_item}' ({count} rows), "
                            "so blended KPIs will read more like that segment than the full business."
                        ),
                        "why_it_matters": (
                            "If you plan off a single growth or margin number without slicing here, "
                            "you may misallocate spend or miss a weak tail in the mix."
                        ),
                        "likely_cause": "True mix skew, or repeated default / placeholder entries in the source system.",
                        "recommended_action": (
                            f"Break out performance by `{col}` before you lock targets; validate whether "
                            f"'{top_item}' is real volume or a data artifact."
                        ),
                        "confidence": "Medium — row counts only, not dollar impact",
                        "source_reference": f"summary `{col}_top_values['{top_item}']` = {count}",
                        "type": "neutral",
                        "caveats": [
                            "No dollar-weighted view—frequency skew may not match revenue skew.",
                        ],
                    })

        insights.insert(
            0,
            {
                "finding": (
                    "Structured AI analysis is off—this report is rule-based counts only, "
                    "not a commercial read across drivers or cohorts."
                ),
                "why_it_matters": (
                    "You should not use this output alone for pricing, cuts, or capital decisions; "
                    "turn on the model-backed pass when you need defensible interpretation."
                ),
                "likely_cause": "OPENAI_API_KEY is not set on the backend.",
                "recommended_action": "Set the key in backend/.env, restart the API, and re-run this analysis.",
                "confidence": "High",
                "source_reference": "Backend configuration",
                "type": "negative",
                "caveats": [
                    "Interpretation is not model-generated until OPENAI_API_KEY is configured.",
                ],
            },
        )

        top_priorities = [
            {
                "kind": "risk",
                "priority": "high",
                "title": "Full AI analysis is off",
                "explanation": (
                    "Counts and skew checks only—do not use this pass alone for pricing, cuts, or capital calls."
                ),
            },
            {
                "kind": "next_action",
                "priority": "high",
                "title": "Enable the model-backed pass",
                "explanation": (
                    "Set OPENAI_API_KEY in backend/.env, restart the API, and re-run for prioritized risks and moves."
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
                    "title": "Category mix may be distorting blended KPIs",
                    "explanation": skew.get("why_it_matters", "")[:220]
                    or "Segment before you lock targets so one label is not doing the work of the whole business.",
                },
            )

        return {
            "executive_summary": (
                f"{rows} rows × {cols} columns—mechanical summary only until the model is enabled. "
                + (
                    f"Revenue-style fields detected: {', '.join(column_metadata.get('revenue_columns', []))}. "
                    if column_metadata.get("revenue_columns")
                    else ""
                )
                + "Enable the API key and re-run for downside, upside, and next moves tied to your actuals."
            ),
            "top_priorities": top_priorities[:5],
            "key_metrics": metrics,
            "insights": insights,
            "anomalies": [],
            "recommendations": [],
        }
