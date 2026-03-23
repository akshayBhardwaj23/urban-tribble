from __future__ import annotations

from typing import Set

import pandas as pd

DATE_HINTS = {"date", "time", "timestamp", "datetime", "day", "month", "year", "period"}
REVENUE_HINTS = {
    "price", "amount", "revenue", "sales", "income", "cost", "total",
    "profit", "fee", "payment", "earning", "expense", "budget", "spend",
}
CATEGORY_HINTS = {
    "product", "category", "customer", "region", "city", "state", "country",
    "department", "type", "group", "segment", "channel", "brand", "name",
    "status", "tier",
}


class ColumnDetector:
    def detect(self, df: pd.DataFrame) -> dict:
        date_cols = []
        revenue_cols = []
        category_cols = []
        numeric_cols = []
        text_cols = []

        for col in df.columns:
            col_lower = col.lower()
            dtype = df[col].dtype

            if pd.api.types.is_datetime64_any_dtype(df[col]):
                date_cols.append(col)
            elif self._matches_hints(col_lower, DATE_HINTS):
                date_cols.append(col)
            elif pd.api.types.is_numeric_dtype(dtype):
                if self._matches_hints(col_lower, REVENUE_HINTS):
                    revenue_cols.append(col)
                else:
                    numeric_cols.append(col)
            elif self._matches_hints(col_lower, CATEGORY_HINTS):
                category_cols.append(col)
            elif dtype == "object":
                nunique = df[col].nunique()
                if nunique < len(df) * 0.3 and nunique < 50:
                    category_cols.append(col)
                else:
                    text_cols.append(col)
            else:
                text_cols.append(col)

        return {
            "date_columns": date_cols,
            "revenue_columns": revenue_cols,
            "category_columns": category_cols,
            "numeric_columns": numeric_cols,
            "text_columns": text_cols,
        }

    def _matches_hints(self, col_name: str, hints: Set[str]) -> bool:
        return any(hint in col_name for hint in hints)

    def summary(self, df: pd.DataFrame, metadata: dict) -> dict:
        """Generate a text summary of the dataset for AI consumption."""
        stats: dict = {
            "rows": len(df),
            "columns": len(df.columns),
            "column_types": metadata,
        }

        for col in metadata.get("revenue_columns", []):
            if col in df.columns:
                stats[f"{col}_total"] = float(df[col].sum())
                stats[f"{col}_mean"] = float(df[col].mean())
                stats[f"{col}_min"] = float(df[col].min())
                stats[f"{col}_max"] = float(df[col].max())

        for col in metadata.get("numeric_columns", []):
            if col in df.columns:
                stats[f"{col}_mean"] = float(df[col].mean())

        for col in metadata.get("category_columns", []):
            if col in df.columns:
                top = df[col].value_counts().head(5).to_dict()
                stats[f"{col}_top_values"] = {str(k): int(v) for k, v in top.items()}

        return stats
