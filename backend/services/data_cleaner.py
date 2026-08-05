from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

# Explicit formats tried in order; dayfirst evidence resolves DD/MM vs MM/DD.
_DATE_FORMATS_DAYFIRST = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
)
_DATE_FORMATS_MONTHFIRST = (
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m.%d.%Y",
    "%m/%d/%y",
    "%m-%d-%y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
)

_PARSE_RATE_THRESHOLD = 0.95
_DEFAULT_DAYFIRST = True  # Prefer DD/MM when ambiguous (common outside US)


class DataCleaner:
    def clean(
        self,
        df: pd.DataFrame,
        *,
        drop_duplicates: bool = False,
        dayfirst: Optional[bool] = None,
    ) -> tuple[pd.DataFrame, dict]:
        """Clean the dataframe and return (cleaned_df, report).

        By default this is non-destructive: missing values and duplicates are
        reported but not removed/filled. Date parsing uses explicit formats
        with a 95% parse-rate gate.
        """
        report: dict[str, Any] = {
            "steps": [],
            "original_shape": list(df.shape),
            "flags": [],
            "original_names": {},
            "date_formats": {},
            "duplicate_row_count": 0,
        }

        df, dropped_unnamed = self._drop_unnamed_columns(df)
        if dropped_unnamed:
            report["steps"].append(
                {
                    "code": "dropped_unnamed",
                    "kind": "info",
                    "message": f"Dropped {len(dropped_unnamed)} unnamed index columns",
                    "columns": dropped_unnamed,
                }
            )

        df, renamed = self._normalize_columns(df)
        report["original_names"] = renamed
        if renamed:
            report["steps"].append(
                {
                    "code": "normalized_columns",
                    "kind": "info",
                    "message": f"Normalized {len(renamed)} column names",
                    "renamed": renamed,
                }
            )

        df, numeric_fixes = self._coerce_numeric_strings(df)
        if numeric_fixes:
            report["steps"].append(
                {
                    "code": "numeric_coercion",
                    "kind": "info",
                    "message": f"Parsed currency/numeric strings in {len(numeric_fixes)} columns",
                    "columns": numeric_fixes,
                }
            )

        df, date_info = self._convert_dates(df, dayfirst=dayfirst)
        report["date_formats"] = {
            col: info for col, info in date_info.items() if info.get("format")
        }
        for col, info in date_info.items():
            if info.get("converted"):
                report["steps"].append(
                    {
                        "code": "dates_normalized",
                        "kind": "info",
                        "message": f"Converted {col} to dates using {info.get('format')}",
                        "column": col,
                        "format": info.get("format"),
                        "parse_rate": info.get("parse_rate"),
                    }
                )
            if info.get("ambiguous"):
                report["flags"].append(
                    {
                        "kind": "warning",
                        "code": "ambiguous_date_format",
                        "message": (
                            f"{col}: date order is ambiguous (all day-parts ≤ 12). "
                            f"Applied {'DD/MM' if info.get('dayfirst') else 'MM/DD'} by default."
                        ),
                        "column": col,
                        "format": info.get("format"),
                        "dayfirst": info.get("dayfirst"),
                    }
                )

        missing_report = self._report_missing(df)
        if missing_report:
            report["steps"].append(
                {
                    "code": "missing_values",
                    "kind": "warning",
                    "message": "Some cells are empty; values were left as blank (not filled)",
                    "columns": missing_report,
                }
            )
            for col, detail in missing_report.items():
                if detail.get("pct", 0) > 0.5:
                    report["flags"].append(
                        {
                            "kind": "warning",
                            "code": "sparse_column",
                            "message": (
                                f"{col} is mostly empty ({detail['pct']:.0%}); "
                                "kept as-is so you can decide whether to use it."
                            ),
                            "column": col,
                        }
                    )

        dupes = int(df.duplicated().sum())
        report["duplicate_row_count"] = dupes
        if dupes > 0:
            report["steps"].append(
                {
                    "code": "duplicates_detected",
                    "kind": "info",
                    "message": (
                        f"Found {dupes} duplicate row(s); left in place "
                        "(identical line items are common in exports)"
                    ),
                    "count": dupes,
                }
            )
            report["flags"].append(
                {
                    "kind": "info",
                    "code": "duplicates_detected",
                    "message": (
                        f"{dupes} duplicate row(s) detected and kept. "
                        "Remove them only if they are true copies."
                    ),
                }
            )
            if drop_duplicates:
                before = len(df)
                df = df.drop_duplicates()
                removed = before - len(df)
                report["steps"].append(
                    {
                        "code": "duplicates_removed",
                        "kind": "info",
                        "message": f"Removed {removed} duplicate rows (user policy)",
                        "count": removed,
                    }
                )

        df = self._stabilize_dtypes(df)

        report["cleaned_shape"] = list(df.shape)
        # Preserve structured steps, but expose legacy string list as "steps"
        # so existing UI (Schema tab) keeps working.
        structured = list(report["steps"])
        report["structured_steps"] = structured
        report["steps"] = [
            s["message"] if isinstance(s, dict) else str(s) for s in structured
        ]
        return df, report

    def _drop_unnamed_columns(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[str]]:
        """Drop unnamed columns only when they are entirely empty (index artifacts).

        Blank headers that carry data are renamed to column_N in normalize.
        """
        unnamed = [c for c in df.columns if str(c).lower().startswith("unnamed")]
        drop: list[str] = []
        for c in unnamed:
            if df[c].isna().all() or (df[c].astype(str).str.strip() == "").all():
                drop.append(c)
        if drop:
            df = df.drop(columns=drop)
        return df, drop

    def _normalize_columns(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, dict[str, str]]:
        """Normalize names, suffix collisions, map blanks → column_N.

        Returns (df, original_name_map) where keys are new names and values are
        the original header text (only entries that changed or were blank).
        """
        original_map: dict[str, str] = {}
        used: dict[str, int] = {}
        new_cols: list[str] = []

        for i, col in enumerate(df.columns):
            raw = str(col).strip() if col is not None else ""
            if raw == "" or raw.lower() in ("nan", "none"):
                base = f"column_{i + 1}"
            else:
                base = re.sub(r"\s+", "_", raw).lower()
                base = re.sub(r"[^\w]", "", base)
                if not base:
                    base = f"column_{i + 1}"

            if base in used:
                used[base] += 1
                new_name = f"{base}_{used[base]}"
            else:
                used[base] = 1
                new_name = base

            if new_name != raw:
                original_map[new_name] = raw
            new_cols.append(new_name)

        df = df.copy()
        df.columns = new_cols
        return df, original_map

    def _coerce_numeric_strings(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[str]]:
        """Coerce currency / thousands / parenthesised negatives / percents."""
        converted: list[str] = []
        df = df.copy()
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(
                df[col]
            ):
                continue
            if df[col].dtype != "object":
                continue
            coerced = self._try_coerce_numeric_series(df[col])
            if coerced is not None:
                df[col] = coerced
                converted.append(col)
        return df, converted

    def _try_coerce_numeric_series(self, series: pd.Series) -> Optional[pd.Series]:
        non_null = series.dropna()
        if len(non_null) == 0:
            return None

        def _parse_one(val: Any) -> Any:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return pd.NA
            s = str(val).strip()
            if s == "" or s.lower() in ("nan", "none", "null", "-", "—"):
                return pd.NA
            neg = False
            if s.startswith("(") and s.endswith(")"):
                neg = True
                s = s[1:-1].strip()
            pct = False
            if s.endswith("%"):
                pct = True
                s = s[:-1].strip()
            # Strip currency symbols and spaces
            s = re.sub(r"[€$£¥₹₽\s]", "", s)
            # EU thousands only when a decimal comma is present (1.234,56) or
            # there are multiple thousand groups (1.234.567). A bare "1.234"
            # must stay as the US decimal 1.234 — never 1234.
            if re.match(r"^-?\d{1,3}(\.\d{3})+,\d+$", s):
                s = s.replace(".", "").replace(",", ".")
            elif re.match(r"^-?\d{1,3}(\.\d{3}){2,}$", s):
                s = s.replace(".", "")
            elif re.match(r"^-?\d+,\d+$", s):
                s = s.replace(",", ".")
            else:
                # US / plain: drop thousands commas only (1,234.56 → 1234.56)
                s = s.replace(",", "")
            try:
                num = float(s)
            except ValueError:
                return pd.NA
            if neg:
                num = -num
            if pct:
                num = num / 100.0
            return num

        parsed = series.map(_parse_one)
        # Count successful parses among originally non-null values
        original_non_null = non_null
        parsed_non_null = parsed.loc[original_non_null.index]
        ok = parsed_non_null.notna().sum()
        rate = ok / len(original_non_null) if len(original_non_null) else 0
        if rate < _PARSE_RATE_THRESHOLD:
            return None
        return pd.to_numeric(parsed, errors="coerce")

    def _convert_dates(
        self,
        df: pd.DataFrame,
        *,
        dayfirst: Optional[bool] = None,
    ) -> tuple[pd.DataFrame, dict[str, dict]]:
        """Parse object columns as dates with explicit formats and 95% gate."""
        info: dict[str, dict] = {}
        df = df.copy()
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                info[col] = {
                    "converted": False,
                    "already_datetime": True,
                    "format": "datetime64",
                    "parse_rate": 1.0,
                    "ambiguous": False,
                    "dayfirst": None,
                }
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                # Excel serials only when the column name looks like a date field
                col_l = str(col).lower()
                dateish = any(
                    t in col_l
                    for t in ("date", "time", "timestamp", "datetime", "period")
                )
                if dateish:
                    serial = self._try_excel_serial(df[col])
                    if serial is not None:
                        df[col] = serial
                        info[col] = {
                            "converted": True,
                            "format": "excel_serial",
                            "parse_rate": 1.0,
                            "ambiguous": False,
                            "dayfirst": None,
                        }
                continue
            if df[col].dtype != "object":
                continue

            result = self._best_date_parse(df[col], dayfirst=dayfirst)
            if result is None:
                continue
            parsed, meta = result
            df[col] = parsed
            info[col] = meta
        return df, info

    def _try_excel_serial(self, series: pd.Series) -> Optional[pd.Series]:
        non_null = series.dropna()
        if len(non_null) == 0:
            return None
        # Excel serials typically 20000–60000 for modern dates
        vals = pd.to_numeric(non_null, errors="coerce")
        if vals.notna().sum() < len(non_null) * _PARSE_RATE_THRESHOLD:
            return None
        if vals.min() < 2000 or vals.max() > 80000:
            return None
        # Only convert if integer-like
        if not ((vals % 1).fillna(0).abs() < 1e-9).all():
            return None
        try:
            parsed = pd.to_datetime(series, unit="D", origin="1899-12-30", errors="coerce")
        except (ValueError, TypeError, OverflowError):
            return None
        if parsed.notna().sum() < len(non_null) * _PARSE_RATE_THRESHOLD:
            return None
        return parsed

    def _best_date_parse(
        self,
        series: pd.Series,
        *,
        dayfirst: Optional[bool] = None,
    ) -> Optional[tuple[pd.Series, dict]]:
        non_null = series.dropna()
        non_null = non_null[non_null.astype(str).str.strip() != ""]
        if len(non_null) == 0:
            return None

        evidence_dayfirst = self._dayfirst_evidence(non_null)
        ambiguous = evidence_dayfirst is None
        if dayfirst is not None:
            use_dayfirst = dayfirst
        elif evidence_dayfirst is not None:
            use_dayfirst = evidence_dayfirst
        else:
            use_dayfirst = _DEFAULT_DAYFIRST

        formats = _DATE_FORMATS_DAYFIRST if use_dayfirst else _DATE_FORMATS_MONTHFIRST
        best_parsed: Optional[pd.Series] = None
        best_fmt: Optional[str] = None
        best_rate = 0.0

        for fmt in formats:
            try:
                parsed = pd.to_datetime(series, format=fmt, errors="coerce")
            except (ValueError, TypeError):
                continue
            rate = parsed.loc[non_null.index].notna().sum() / len(non_null)
            if rate > best_rate:
                best_rate = rate
                best_parsed = parsed
                best_fmt = fmt

        # ISO / mixed fallback without infer_datetime_format silent swap
        if best_rate < _PARSE_RATE_THRESHOLD:
            try:
                parsed = pd.to_datetime(
                    series, errors="coerce", dayfirst=use_dayfirst, format="mixed"
                )
            except (ValueError, TypeError, TypeError):
                try:
                    parsed = pd.to_datetime(series, errors="coerce", dayfirst=use_dayfirst)
                except (ValueError, TypeError):
                    parsed = None
            if parsed is not None:
                rate = parsed.loc[non_null.index].notna().sum() / len(non_null)
                if rate > best_rate:
                    best_rate = rate
                    best_parsed = parsed
                    best_fmt = "mixed_dayfirst" if use_dayfirst else "mixed_monthfirst"

        if best_parsed is None or best_rate < _PARSE_RATE_THRESHOLD:
            return None

        meta = {
            "converted": True,
            "format": best_fmt,
            "parse_rate": round(float(best_rate), 4),
            "ambiguous": ambiguous and evidence_dayfirst is None,
            "dayfirst": use_dayfirst,
        }
        return best_parsed, meta

    def _dayfirst_evidence(self, non_null: pd.Series) -> Optional[bool]:
        """Return True if DD/MM proven, False if MM/DD proven, None if ambiguous.

        Pattern a/b/year:
        - If a > 12 → a is day → dayfirst True
        - If b > 12 → b is day → dayfirst False (month first)
        """
        first_gt_12 = False
        second_gt_12 = False
        for val in non_null.astype(str):
            m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.]\d{2,4}$", val.strip())
            if not m:
                continue
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12:
                first_gt_12 = True
            if b > 12:
                second_gt_12 = True

        if first_gt_12 and not second_gt_12:
            return True
        if second_gt_12 and not first_gt_12:
            return False
        return None

    def _report_missing(self, df: pd.DataFrame) -> dict[str, dict]:
        """Report missing values without filling or dropping columns."""
        out: dict[str, dict] = {}
        if len(df) == 0:
            return out
        for col in df.columns:
            missing = int(df[col].isna().sum())
            if missing == 0:
                # Also count empty strings for object cols
                if df[col].dtype == "object":
                    empty = int((df[col].astype(str).str.strip() == "").sum())
                    missing = empty
                if missing == 0:
                    continue
            pct = missing / len(df)
            out[col] = {"missing": missing, "pct": round(float(pct), 4)}
        return out

    def _stabilize_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure object columns have uniform string type for Parquet."""
        df = df.copy()
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].where(df[col].notna(), None)
                df[col] = df[col].apply(lambda x: None if x is None else str(x))
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                # Keep datetime64 — do not fillna("Unknown")
                pass
        return df
