from __future__ import annotations

import re
from typing import Any

import pandas as pd

DATE_HINTS = {
    "date",
    "time",
    "timestamp",
    "datetime",
    "period",
    "created",
    "updated",
    "ordered",
    "shipped",
    "invoice_date",
    "order_date",
    "trans_date",
    "transaction_date",
}
# Tokens that look date-like but are durations / ages / not timeline axes
DATE_NEGATIVE_PATTERNS = (
    r".*_days$",
    r"^days_.*",
    r".*_day$",
    r"^day_count$",
    r".*_count$",
    r"^count_.*",
    r"birthday",
    r"runtime",
    r"^age$",
    r".*_age$",
    r"lead_time",
    r"duration",
    r"tenure",
    r"days_to_",
    r"days_until_",
    r"days_since_",
    r"hours?",
    r"minutes?",
    r"seconds?",
)

REVENUE_HINTS = {
    "price",
    "amount",
    "revenue",
    "sales",
    "income",
    "total",
    "profit",
    "payment",
    "earning",
    "gmv",
    "net",
    "gross",
    "receipt",
    "billing",
}
EXPENSE_HINTS = {
    "cost",
    "expense",
    "spend",
    "budget",
    "fee",
    "outflow",
    "cogs",
    "overhead",
    "payroll",
    "salary",
    "tax",
    "refund",
    "discount",
}
CATEGORY_HINTS = {
    "product",
    "category",
    "customer",
    "region",
    "city",
    "state",
    "country",
    "department",
    "type",
    "group",
    "segment",
    "channel",
    "brand",
    "name",
    "status",
    "tier",
    "sku",
}

_PARSE_RATE = 0.95


class ColumnDetector:
    def detect(self, df: pd.DataFrame) -> dict:
        date_cols: list[str] = []
        revenue_cols: list[str] = []
        expense_cols: list[str] = []
        category_cols: list[str] = []
        numeric_cols: list[str] = []
        text_cols: list[str] = []

        date_candidates: list[tuple[str, float]] = []  # (col, hint_score)

        for col in df.columns:
            col_str = str(col)
            col_lower = col_str.lower()
            tokens = self._tokens(col_lower)

            if self._is_date_negative(col_lower, tokens):
                # Duration / age-like — treat as numeric or text, never date
                if pd.api.types.is_numeric_dtype(df[col]):
                    if self._matches_hints(tokens, EXPENSE_HINTS):
                        expense_cols.append(col_str)
                    elif self._matches_hints(tokens, REVENUE_HINTS):
                        revenue_cols.append(col_str)
                    else:
                        numeric_cols.append(col_str)
                else:
                    text_cols.append(col_str)
                continue

            if pd.api.types.is_datetime64_any_dtype(df[col]):
                score = 2.0 if self._matches_hints(tokens, DATE_HINTS) else 1.0
                date_candidates.append((col_str, score))
                continue

            # Numeric columns are never timeline candidates here — Excel serials
            # are converted to datetime64 in the cleaner when name-hinted.
            if pd.api.types.is_numeric_dtype(df[col]):
                if self._matches_hints(tokens, EXPENSE_HINTS):
                    expense_cols.append(col_str)
                elif self._matches_hints(tokens, REVENUE_HINTS):
                    if self._is_quantity_like(tokens, col_lower):
                        numeric_cols.append(col_str)
                    else:
                        revenue_cols.append(col_str)
                else:
                    numeric_cols.append(col_str)
                continue

            # Evidence-first: only treat object columns as dates if values parse
            date_rate = self._date_parse_rate(df[col])
            if date_rate >= _PARSE_RATE:
                score = 2.0 if self._matches_hints(tokens, DATE_HINTS) else 1.0
                score += date_rate
                date_candidates.append((col_str, score))
                continue

            # Name hint alone must NOT put a column in date_columns
            if self._matches_hints(tokens, CATEGORY_HINTS):
                category_cols.append(col_str)
            elif df[col].dtype == "object" or str(df[col].dtype) == "string":
                nunique = df[col].nunique(dropna=True)
                if len(df) > 0 and nunique < len(df) * 0.3 and nunique < 50:
                    category_cols.append(col_str)
                else:
                    text_cols.append(col_str)
            else:
                text_cols.append(col_str)

        # Order date columns by score (hints break ties), highest first
        date_candidates.sort(key=lambda x: -x[1])
        date_cols = [c for c, _ in date_candidates]

        return {
            "date_columns": date_cols,
            "revenue_columns": revenue_cols,
            "expense_columns": expense_cols,
            "category_columns": category_cols,
            "numeric_columns": numeric_cols,
            "text_columns": text_cols,
            "all_columns": [str(c) for c in df.columns],
        }

    def _tokens(self, col_lower: str) -> set[str]:
        parts = re.split(r"[_\s\-./]+", col_lower)
        return {p for p in parts if p}

    def _matches_hints(self, tokens: set[str], hints: set[str]) -> bool:
        """Whole-token match only (no bare substring)."""
        for hint in hints:
            if " " in hint or "_" in hint:
                # multi-word hints checked against joined name elsewhere
                continue
            if hint in tokens:
                return True
        # Also allow exact multi-token hints joined
        name = "_".join(tokens)
        for hint in hints:
            hint_n = hint.replace("-", "_")
            if "_" in hint_n and hint_n in name:
                return True
        return any(hint in tokens for hint in hints if "_" not in hint)

    def _is_date_negative(self, col_lower: str, tokens: set[str]) -> bool:
        for pat in DATE_NEGATIVE_PATTERNS:
            if re.search(pat, col_lower):
                return True
        if tokens & {"days", "runtime", "birthday", "duration", "tenure"}:
            return True
        return False

    def _is_quantity_like(self, tokens: set[str], col_lower: str) -> bool:
        qty = {"qty", "quantity", "count", "units", "unit", "volume", "items"}
        if tokens & qty:
            return True
        if re.search(r"(quantity|qty|units?|count)$", col_lower):
            return True
        return False

    def _date_parse_rate(self, series: pd.Series) -> float:
        if pd.api.types.is_datetime64_any_dtype(series):
            return 1.0
        non_null = series.dropna()
        if hasattr(non_null, "astype"):
            try:
                non_null = non_null[non_null.astype(str).str.strip() != ""]
            except Exception:
                pass
        if len(non_null) == 0:
            return 0.0
        try:
            parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
        except (ValueError, TypeError):
            try:
                parsed = pd.to_datetime(non_null, errors="coerce")
            except (ValueError, TypeError):
                return 0.0
        return float(parsed.notna().sum()) / len(non_null)

    def summary(self, df: pd.DataFrame, metadata: dict) -> dict:
        """Generate a text summary of the dataset for AI consumption."""
        stats: dict[str, Any] = {
            "rows": len(df),
            "columns": len(df.columns),
            "column_types": metadata,
        }

        for col in list(metadata.get("revenue_columns", [])) + list(
            metadata.get("expense_columns", [])
        ):
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                stats[f"{col}_total"] = float(df[col].sum(skipna=True))
                stats[f"{col}_mean"] = float(df[col].mean(skipna=True))
                stats[f"{col}_min"] = float(df[col].min(skipna=True))
                stats[f"{col}_max"] = float(df[col].max(skipna=True))

        for col in metadata.get("numeric_columns", []):
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                stats[f"{col}_mean"] = float(df[col].mean(skipna=True))

        for col in metadata.get("category_columns", []):
            if col in df.columns:
                top = df[col].value_counts(dropna=True).head(5).to_dict()
                stats[f"{col}_top_values"] = {str(k): int(v) for k, v in top.items()}

        # Compact daily series for the workspace overview so it does not need to
        # reopen every parquet on a cache miss.
        overview_series = self._overview_series(df, metadata)
        if overview_series:
            stats["overview_series"] = overview_series

        return stats

    def _overview_series(self, df: pd.DataFrame, metadata: dict) -> list[dict[str, Any]]:
        date_cols = list(metadata.get("date_columns") or [])
        rev_cols = list(metadata.get("revenue_columns") or [])
        primary_t = metadata.get("primary_timeline")
        primary_a = metadata.get("primary_amount")
        if primary_t and primary_t in date_cols:
            date_cols = [primary_t] + [c for c in date_cols if c != primary_t]
        if primary_a and primary_a in rev_cols:
            rev_cols = [primary_a] + [c for c in rev_cols if c != primary_a]
        if not date_cols or not rev_cols:
            return []
        date_col, rev_col = date_cols[0], rev_cols[0]
        if date_col not in df.columns or rev_col not in df.columns:
            return []
        try:
            w = df[[date_col, rev_col]].copy()
            w["_dt"] = pd.to_datetime(w[date_col], errors="coerce")
            w["_rev"] = pd.to_numeric(w[rev_col], errors="coerce")
            w = w.dropna(subset=["_dt", "_rev"])
            if w.empty:
                return []
            w["_day"] = w["_dt"].dt.normalize()
            grouped = w.groupby("_day", as_index=False)["_rev"].sum()
            grouped = grouped.sort_values("_day")
            # Cap to keep data_summary small; overview charts are overview-grade.
            if len(grouped) > 366:
                grouped = grouped.iloc[-366:]
            return [
                {
                    "x": row["_day"].strftime("%Y-%m-%d"),
                    "y": float(row["_rev"]),
                    "date_column": date_col,
                    "value_column": rev_col,
                }
                for _, row in grouped.iterrows()
            ]
        except Exception:
            return []
