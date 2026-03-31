from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from openai import OpenAI

from config import settings

QUERY_SYSTEM_PROMPT = """You are a data analyst assistant. The user will ask a question about a pandas DataFrame.

You will receive:
1. The DataFrame schema (column names, types, sample values)
2. The user's question (and possibly earlier Q&A in the same thread)

Follow-up questions may refer to prior answers (e.g. "break that down by region", "what about last quarter"). Use the conversation when the latest question is ambiguous.

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

MULTI_DF_SYSTEM_PROMPT = """You are a data analyst assistant. The user has MULTIPLE pandas DataFrames from different business datasets.

You will receive:
1. Schema info for each DataFrame (name, columns, types, sample rows)
2. The user's question (and possibly earlier Q&A in the same thread)

Follow-up questions may refer to prior answers. Use the conversation when the latest question is ambiguous.

Each DataFrame is available as a variable named by its sanitized dataset name (e.g. `df_sales`, `df_expenses`).
A dict called `datasets` maps dataset names to their DataFrames: datasets["sales"] = df_sales, etc.

Respond with ONLY a JSON object:
{
  "pandas_code": "pandas code to answer the question. Use the named df variables (df_sales, df_expenses, etc.) or the datasets dict. The result must be assigned to a variable called `result`.",
  "explanation_hint": "brief note about what the code does"
}

Rules:
- Always assign the final answer to `result`
- You can merge/join DataFrames if they share common columns
- For aggregations, make result a simple value or small DataFrame
- Use .to_dict() or .tolist() if the result is a Series/DataFrame so it's JSON-serializable
- Never use exec(), eval(), import, open(), or any system calls
- Never modify any DataFrame in place
- Keep code simple and readable
- If the question is about a specific dataset, use only that DataFrame
- If the question spans multiple datasets, merge or concatenate as needed"""

EXPLAIN_SYSTEM_PROMPT = """You are a friendly business data analyst. Given a user's question about their data and the computed result, provide a clear, concise natural language answer.

If there is prior conversation, keep answers consistent with what was already said when relevant.

Be specific with numbers. If the result contains data suitable for a chart, also return chart configuration.

Respond with a JSON object:
{
  "answer": "your natural language answer",
  "chart_data": null or {"type": "bar|line|pie", "data": [...], "title": "chart title"}
}"""

FORBIDDEN_TOKENS = [
    "import ", "exec(", "eval(", "open(", "subprocess",
    "os.", "sys.", "shutil", "pathlib", "glob",
]

SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "format": format,
    "frozenset": frozenset, "int": int, "isinstance": isinstance, "len": len,
    "list": list, "map": map, "max": max, "min": min, "print": print,
    "range": range, "reversed": reversed, "round": round, "set": set,
    "slice": slice, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
    "type": type, "zip": zip, "True": True, "False": False, "None": None,
}


def _sanitize_name(name: str) -> str:
    """Turn a dataset name into a valid Python variable suffix."""
    import re
    name = name.rsplit(".", 1)[0]
    name = re.sub(r"[^a-z0-9_]", "_", name.lower())
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "data"


class QueryEngine:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    def ask(
        self,
        question: str,
        df: pd.DataFrame,
        schema: Dict[str, Any],
        user_description: Optional[str] = None,
        history: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        if not self.client:
            return self._fallback_answer(question, df, schema)

        schema_info = self._build_schema_info(df, schema, user_description)
        history = history or []
        pandas_code = self._generate_query(question, schema_info, history)
        result = self._execute_query(pandas_code, df)
        answer = self._explain_result(question, result, pandas_code, history)
        return answer

    def ask_multi(
        self,
        question: str,
        dataframes: List[Tuple[str, pd.DataFrame, Dict[str, Any], Optional[str]]],
        history: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Query across multiple named DataFrames.

        dataframes: list of (name, df, schema, description) tuples
        """
        if not self.client:
            return self._fallback_multi(question, dataframes)

        schema_info = self._build_multi_schema_info(dataframes)
        history = history or []
        pandas_code = self._generate_multi_query(question, schema_info, history)
        result = self._execute_multi_query(pandas_code, dataframes)
        answer = self._explain_result(question, result, pandas_code, history)
        return answer

    # ── single-df helpers ──

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

    def _messages_codegen_single(
        self,
        question: str,
        schema_info: str,
        history: List[Tuple[str, str]],
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": QUERY_SYSTEM_PROMPT},
        ]
        for i, (uq, aa) in enumerate(history):
            if i == 0:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Schema:\n{schema_info}\n\nQuestion: {uq}",
                    }
                )
            else:
                messages.append({"role": "user", "content": uq})
            messages.append({"role": "assistant", "content": aa})
        messages.append(
            {
                "role": "user",
                "content": f"Schema:\n{schema_info}\n\nQuestion: {question}",
            }
        )
        return messages

    def _generate_query(
        self,
        question: str,
        schema_info: str,
        history: List[Tuple[str, str]],
    ) -> str:
        messages = self._messages_codegen_single(question, schema_info, history)
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
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
        safe_globals = {"__builtins__": SAFE_BUILTINS}
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

    # ── multi-df helpers ──

    def _build_multi_schema_info(
        self, dataframes: List[Tuple[str, pd.DataFrame, Dict[str, Any], Optional[str]]]
    ) -> str:
        parts = [f"You have {len(dataframes)} datasets available:\n"]

        for name, df, schema, desc in dataframes:
            var_name = f"df_{_sanitize_name(name)}"
            section = [f"--- DataFrame: {var_name} (from \"{name}\") ---"]
            if desc:
                section.append(f"Description: {desc}")
            section.append(f"Columns: {list(df.columns)}")
            section.append(f"Dtypes:\n{df.dtypes.to_string()}")
            section.append(f"Shape: {df.shape}")
            section.append(f"Sample (first 3 rows):\n{df.head(3).to_string()}")
            section.append(f"Column metadata: {json.dumps(schema)}")
            parts.append("\n".join(section))

        return "\n\n".join(parts)

    def _messages_codegen_multi(
        self,
        question: str,
        schema_info: str,
        history: List[Tuple[str, str]],
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": MULTI_DF_SYSTEM_PROMPT},
        ]
        block = f"Available DataFrames:\n{schema_info}\n\nQuestion:"
        for i, (uq, aa) in enumerate(history):
            if i == 0:
                messages.append(
                    {"role": "user", "content": f"{block} {uq}"},
                )
            else:
                messages.append({"role": "user", "content": uq})
            messages.append({"role": "assistant", "content": aa})
        messages.append({"role": "user", "content": f"{block} {question}"})
        return messages

    def _generate_multi_query(
        self,
        question: str,
        schema_info: str,
        history: List[Tuple[str, str]],
    ) -> str:
        messages = self._messages_codegen_multi(question, schema_info, history)
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
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

    def _execute_multi_query(
        self,
        code: str,
        dataframes: List[Tuple[str, pd.DataFrame, Dict[str, Any], Optional[str]]],
    ) -> Any:
        safe_globals = {"__builtins__": SAFE_BUILTINS}
        safe_locals = {"pd": pd, "datasets": {}}

        for name, df, _schema, _desc in dataframes:
            var_name = f"df_{_sanitize_name(name)}"
            safe_locals[var_name] = df.copy()
            safe_locals["datasets"][_sanitize_name(name)] = safe_locals[var_name]

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

    # ── shared helpers ──

    def _explain_history_pairs(
        self,
        history: List[Tuple[str, str]],
        max_pairs: int = 8,
        max_assistant_chars: int = 6000,
    ) -> List[Tuple[str, str]]:
        """Recent turns for the explain pass; trim long assistant answers."""
        if not history:
            return []
        sel = history[-max_pairs:]
        out: List[Tuple[str, str]] = []
        for uq, aa in sel:
            if len(aa) > max_assistant_chars:
                aa = aa[: max_assistant_chars - 1] + "…"
            out.append((uq, aa))
        return out

    def _explain_result(
        self,
        question: str,
        result: Any,
        code: str,
        history: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        history = history or []
        hist_use = self._explain_history_pairs(history)
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
        ]
        for uq, aa in hist_use:
            messages.append({"role": "user", "content": uq})
            messages.append({"role": "assistant", "content": aa})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n"
                    f"Pandas code used: {code}\n"
                    f"Result: {json.dumps(result, default=str)}"
                ),
            }
        )
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
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

    def _fallback_multi(
        self,
        question: str,
        dataframes: List[Tuple[str, pd.DataFrame, Dict[str, Any], Optional[str]]],
    ) -> Dict[str, Any]:
        """Basic multi-dataset fallback when no OpenAI key is available."""
        q = question.lower()
        answer_parts = []

        for name, df, schema, _desc in dataframes:
            revenue_cols = schema.get("revenue_columns", [])
            if any(w in q for w in ["total", "sum", "overall"]):
                for col in revenue_cols:
                    if col in df.columns:
                        total = df[col].sum()
                        answer_parts.append(f"[{name}] Total {col}: {total:,.2f}")
            elif any(w in q for w in ["how many", "count", "rows"]):
                answer_parts.append(f"[{name}] {len(df)} rows, {len(df.columns)} columns")

        if not answer_parts:
            summary = ", ".join(f"{name} ({len(df)} rows)" for name, df, _, _ in dataframes)
            answer_parts.append(
                f"Available datasets: {summary}. "
                f"Configure OPENAI_API_KEY for intelligent cross-dataset Q&A."
            )

        return {
            "answer": "\n".join(answer_parts),
            "chart_data": None,
        }
