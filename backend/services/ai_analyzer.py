from __future__ import annotations

import json
from typing import Optional

from openai import OpenAI

from config import settings

SYSTEM_PROMPT = """You are an expert business data analyst. You analyze datasets and provide actionable business insights.

You will receive:
1. A description of what the file represents (provided by the user)
2. Column metadata (detected types: date, revenue, category, numeric)
3. Statistical summary of the data

Respond with a JSON object containing:
{
  "executive_summary": "2-3 sentence overview of the dataset and its key takeaway",
  "key_metrics": [
    {"label": "metric name", "value": "formatted value", "trend": "up|down|stable", "note": "brief context"}
  ],
  "insights": [
    {"title": "insight title", "description": "detailed explanation", "type": "positive|negative|neutral"}
  ],
  "anomalies": [
    {"description": "what's unusual", "severity": "high|medium|low"}
  ],
  "recommendations": [
    "actionable recommendation 1",
    "actionable recommendation 2"
  ]
}

Be specific with numbers. Reference actual data values. Keep insights actionable and business-focused."""


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
        parts.append("Analyze this dataset and provide your insights as JSON.")
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
                    insights.append({
                        "title": f"Top {col.replace('_', ' ').title()}",
                        "description": f"'{top_item}' is the most frequent value with {top_vals[top_item]} occurrences.",
                        "type": "neutral",
                    })

        return {
            "executive_summary": f"Dataset contains {rows} rows across {cols} columns. "
            + (f"Revenue columns detected: {', '.join(column_metadata.get('revenue_columns', []))}. " if column_metadata.get("revenue_columns") else "")
            + "Configure OPENAI_API_KEY for full AI-powered analysis.",
            "key_metrics": metrics,
            "insights": insights,
            "anomalies": [],
            "recommendations": ["Configure your OpenAI API key in backend/.env for full AI analysis."],
        }
