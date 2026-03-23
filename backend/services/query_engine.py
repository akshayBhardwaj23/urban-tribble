from __future__ import annotations

import json
import traceback
from typing import Any, Dict, Optional

import pandas as pd
from openai import OpenAI

from config import settings

QUERY_SYSTEM_PROMPT = """You are a data analyst assistant. The user will ask a question about a pandas DataFrame.

You will receive:
1. The DataFrame schema (column names, types, sample values)
2. The user's question

Respond with ONLY a JSON object:
{
  "pandas_code": "single-line or multi-line pandas expression to answer the question. The DataFrame variable is `df`. The result must be assigned to a variable called `result`.",
  "explanation_hint": "brief note about what the code does"
}

Rules:
- Always assign the final answer to `result`
- For aggregations, make result a simple value or small DataFrame
- Use .to_dict() or .tolist() if the result is a Series/DataFrame so it's JSON-serializable
- Never use exec(), eval(), import, open(), or any system calls
- Never modify the DataFrame in place
- Keep code simple and readable"""

EXPLAIN_SYSTEM_PROMPT = """You are a friendly business data analyst. Given a user's question about their data and the computed result, provide a clear, concise natural language answer.

Be specific with numbers. If the result contains data suitable for a chart, also return chart configuration.

Respond with a JSON object:
{
  "answer": "your natural language answer",
  "chart_data": null or {"type": "bar|line|pie", "data": [...], "title": "chart title"}
}"""

FORBIDDEN_TOKENS = [
    "import ", "exec(", "eval(", "open(", "__", "subprocess",
    "os.", "sys.", "shutil", "pathlib", "glob",
]


class QueryEngine:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    def ask(
        self,
        question: str,
        df: pd.DataFrame,
        schema: Dict[str, Any],
        user_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.client:
            return self._fallback_answer(question, df, schema)

        schema_info = self._build_schema_info(df, schema, user_description)
        pandas_code = self._generate_query(question, schema_info)
        result = self._execute_query(pandas_code, df)
        answer = self._explain_result(question, result, pandas_code)
        return answer

    def _build_schema_info(
        self, df: pd.DataFrame, schema: Dict, user_description: Optional[str]
    ) -> str:
        parts = []
        if user_description:
            parts.append(f"Dataset description: {user_description}")
        parts.append(f"Columns: {list(df.columns)}")
        parts.append(f"Dtypes:\n{df.dtypes.to_string()}")
        parts.append(f"Shape: {df.shape}")
        parts.append(f"Sample (first 3 rows):\n{df.head(3).to_string()}")
        parts.append(f"Column metadata: {json.dumps(schema)}")
        return "\n\n".join(parts)

    def _generate_query(self, question: str, schema_info: str) -> str:
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": QUERY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Schema:\n{schema_info}\n\nQuestion: {question}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        code = parsed.get("pandas_code", "result = 'Could not generate query'")

        for token in FORBIDDEN_TOKENS:
            if token in code:
                raise ValueError(f"Generated code contains forbidden token: {token}")

        return code

    def _execute_query(self, code: str, df: pd.DataFrame) -> Any:
        safe_globals = {"__builtins__": {}}
        safe_locals = {"df": df.copy(), "pd": pd}

        try:
            exec(code, safe_globals, safe_locals)
        except Exception as e:
            return f"Query execution error: {str(e)}"

        result = safe_locals.get("result", "No result produced")

        if isinstance(result, pd.DataFrame):
            result = result.head(50).to_dict(orient="records")
        elif isinstance(result, pd.Series):
            result = result.head(50).to_dict()

        return result

    def _explain_result(self, question: str, result: Any, code: str) -> Dict[str, Any]:
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Question: {question}\nPandas code used: {code}\nResult: {json.dumps(result, default=str)}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def _fallback_answer(
        self, question: str, df: pd.DataFrame, schema: Dict
    ) -> Dict[str, Any]:
        """Basic keyword-based answers when no OpenAI key is available."""
        q = question.lower()
        answer_parts = []

        revenue_cols = schema.get("revenue_columns", [])
        date_cols = schema.get("date_columns", [])
        category_cols = schema.get("category_columns", [])

        if any(w in q for w in ["total", "sum", "overall"]):
            for col in revenue_cols:
                if col in df.columns:
                    total = df[col].sum()
                    answer_parts.append(f"Total {col}: {total:,.2f}")

        elif any(w in q for w in ["average", "mean", "avg"]):
            for col in revenue_cols:
                if col in df.columns:
                    avg = df[col].mean()
                    answer_parts.append(f"Average {col}: {avg:,.2f}")

        elif any(w in q for w in ["highest", "max", "best", "top"]):
            for col in revenue_cols:
                if col in df.columns:
                    idx = df[col].idxmax()
                    row = df.loc[idx]
                    answer_parts.append(
                        f"Highest {col}: {row[col]:,.2f}"
                    )
                    for cat in category_cols:
                        if cat in df.columns:
                            answer_parts.append(f"  {cat}: {row[cat]}")

        elif any(w in q for w in ["lowest", "min", "worst", "bottom"]):
            for col in revenue_cols:
                if col in df.columns:
                    idx = df[col].idxmin()
                    row = df.loc[idx]
                    answer_parts.append(
                        f"Lowest {col}: {row[col]:,.2f}"
                    )

        elif any(w in q for w in ["how many", "count", "rows"]):
            answer_parts.append(f"Total rows: {len(df)}")
            for cat in category_cols:
                if cat in df.columns:
                    answer_parts.append(
                        f"Unique {cat}: {df[cat].nunique()}"
                    )

        if not answer_parts:
            cols_info = ", ".join(df.columns)
            answer_parts.append(
                f"I can see your dataset has {len(df)} rows with columns: {cols_info}. "
                f"Configure OPENAI_API_KEY for intelligent Q&A over your data."
            )

        return {
            "answer": "\n".join(answer_parts),
            "chart_data": None,
        }
