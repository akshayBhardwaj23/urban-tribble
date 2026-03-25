from __future__ import annotations

import re
from typing import Dict, List, Tuple

import pandas as pd


class DataCleaner:
    def clean(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        """Clean the dataframe and return (cleaned_df, report)."""
        report: dict = {"steps": [], "original_shape": list(df.shape)}

        df, dropped_unnamed = self._drop_unnamed_columns(df)
        if dropped_unnamed:
            report["steps"].append(
                f"Dropped {len(dropped_unnamed)} unnamed index columns: {dropped_unnamed}"
            )

        df, dupes = self._remove_duplicates(df)
        if dupes > 0:
            report["steps"].append(f"Removed {dupes} duplicate rows")

        df, renamed = self._normalize_columns(df)
        if renamed:
            report["steps"].append(
                f"Normalized {len(renamed)} column names: {renamed}"
            )

        df, date_fixes = self._convert_dates(df)
        if date_fixes:
            report["steps"].append(
                f"Converted {len(date_fixes)} columns to date format: {date_fixes}"
            )

        df, missing_report = self._handle_missing(df)
        if missing_report:
            report["steps"].append(f"Handled missing values: {missing_report}")

        df = self._stabilize_dtypes(df)

        report["cleaned_shape"] = list(df.shape)
        return df, report

    def _drop_unnamed_columns(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[str]]:
        unnamed = [c for c in df.columns if str(c).lower().startswith("unnamed")]
        if unnamed:
            df = df.drop(columns=unnamed)
        return df, unnamed

    def _remove_duplicates(self, df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
        before = len(df)
        df = df.drop_duplicates()
        return df, before - len(df)

    def _normalize_columns(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, dict[str, str]]:
        renamed = {}
        new_cols = []
        for col in df.columns:
            new_name = re.sub(r"\s+", "_", str(col).strip()).lower()
            new_name = re.sub(r"[^\w]", "", new_name)
            if new_name != str(col):
                renamed[str(col)] = new_name
            new_cols.append(new_name)
        df.columns = new_cols
        return df, renamed

    def _convert_dates(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[str]]:
        converted = []
        for col in df.columns:
            if df[col].dtype == "object":
                try:
                    parsed = pd.to_datetime(df[col], infer_datetime_format=True)
                    if parsed.notna().sum() > len(df) * 0.5:
                        df[col] = parsed
                        converted.append(col)
                except (ValueError, TypeError):
                    continue
        return df, converted

    def _handle_missing(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        report = {}
        for col in df.columns:
            missing = df[col].isna().sum()
            if missing == 0:
                continue

            pct = missing / len(df)
            if pct > 0.5:
                report[col] = f"dropped ({missing} missing, {pct:.0%})"
                df = df.drop(columns=[col])
            elif df[col].dtype in ("float64", "int64"):
                median = df[col].median()
                df[col] = df[col].fillna(median)
                report[col] = f"filled {missing} with median ({median})"
            else:
                df[col] = df[col].fillna("Unknown")
                report[col] = f"filled {missing} with 'Unknown'"
        return df, report

    def _stabilize_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure object columns have uniform string type for Parquet."""
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str)
        return df
