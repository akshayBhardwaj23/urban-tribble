"""Column profiles and versioned mapping specs for spreadsheet ingestion.

MappingSpec is the source of truth; cleaned parquet is a cache derived from it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Optional

import pandas as pd

ColumnRole = Literal[
    "timeline",
    "amount_inflow",
    "amount_outflow",
    "quantity",
    "identifier",
    "dimension",
    "text",
    "ignore",
]

VALID_ROLES = frozenset(
    {
        "timeline",
        "amount_inflow",
        "amount_outflow",
        "quantity",
        "identifier",
        "dimension",
        "text",
        "ignore",
    }
)

MappingSource = Literal["auto", "llm", "user"]


def schema_fingerprint(columns: list[str], dtypes: dict[str, str]) -> str:
    payload = json.dumps(
        {"columns": sorted(columns), "dtypes": {k: dtypes[k] for k in sorted(dtypes)}},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def profile_column(df: pd.DataFrame, col: str) -> dict[str, Any]:
    s = df[col]
    n = len(df)
    nulls = int(s.isna().sum())
    non_null = n - nulls
    distinct = int(s.nunique(dropna=True))
    samples = [ _jsonable(v) for v in s.dropna().head(5).tolist() ]
    dtype = str(s.dtype)

    numeric_rate = 0.0
    date_rate = 0.0
    if pd.api.types.is_numeric_dtype(s):
        numeric_rate = 1.0 if non_null else 0.0
    elif non_null:
        coerced = pd.to_numeric(s, errors="coerce")
        numeric_rate = float(coerced.notna().sum()) / n if n else 0.0

    if pd.api.types.is_datetime64_any_dtype(s):
        date_rate = 1.0 if non_null else 0.0
    elif non_null:
        try:
            parsed = pd.to_datetime(s, errors="coerce", format="mixed")
        except (ValueError, TypeError):
            try:
                parsed = pd.to_datetime(s, errors="coerce")
            except (ValueError, TypeError):
                parsed = None
        if parsed is not None:
            date_rate = float(parsed.notna().sum()) / n if n else 0.0

    mn = mx = None
    if pd.api.types.is_numeric_dtype(s) and non_null:
        mn = float(s.min(skipna=True))
        mx = float(s.max(skipna=True))
    elif pd.api.types.is_datetime64_any_dtype(s) and non_null:
        mn = str(s.min())
        mx = str(s.max())

    return {
        "name": col,
        "dtype": dtype,
        "null_rate": round(nulls / n, 4) if n else 0.0,
        "distinct_ratio": round(distinct / non_null, 4) if non_null else 0.0,
        "distinct_count": distinct,
        "numeric_parse_rate": round(numeric_rate, 4),
        "date_parse_rate": round(date_rate, 4),
        "min": mn,
        "max": mx,
        "samples": samples,
        "is_unique": bool(non_null > 0 and distinct == non_null),
    }


def build_column_profiles(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [profile_column(df, str(c)) for c in df.columns]


def roles_from_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Map legacy detector metadata lists → per-column roles."""
    roles: dict[str, str] = {}
    for c in metadata.get("date_columns") or []:
        roles[str(c)] = "timeline"
    for c in metadata.get("revenue_columns") or []:
        roles[str(c)] = "amount_inflow"
    for c in metadata.get("expense_columns") or []:
        roles[str(c)] = "amount_outflow"
    for c in metadata.get("category_columns") or []:
        roles.setdefault(str(c), "dimension")
    for c in metadata.get("numeric_columns") or []:
        roles.setdefault(str(c), "quantity")
    for c in metadata.get("text_columns") or []:
        roles.setdefault(str(c), "text")
    for c in metadata.get("all_columns") or []:
        roles.setdefault(str(c), "text")
    return roles


def build_mapping_spec(
    df: pd.DataFrame,
    metadata: dict[str, Any],
    *,
    clean_report: Optional[dict] = None,
    source: MappingSource = "auto",
    sheet: Optional[str] = None,
    header_row: int = 0,
    date_formats: Optional[dict[str, str]] = None,
    drop_duplicates: bool = False,
    dayfirst: Optional[bool] = None,
    primary_timeline: Optional[str] = None,
    primary_amount: Optional[str] = None,
    ingestion_profile: Optional[dict] = None,
    llm_meanings: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    profiles = build_column_profiles(df)
    roles = roles_from_metadata(metadata)
    dtypes = {str(c): str(df[c].dtype) for c in df.columns}
    columns_spec = []
    for p in profiles:
        name = p["name"]
        columns_spec.append(
            {
                "name": name,
                "role": roles.get(name, "text"),
                "date_format": (date_formats or {}).get(name)
                or ((clean_report or {}).get("date_formats") or {}).get(name),
                "original_name": ((clean_report or {}).get("original_names") or {}).get(
                    name
                ),
                "meaning": (llm_meanings or {}).get(name),
                "profile": p,
            }
        )

    date_cols = metadata.get("date_columns") or []
    rev_cols = metadata.get("revenue_columns") or []
    return {
        "version": 1,
        "source": source,
        "schema_fingerprint": schema_fingerprint(list(map(str, df.columns)), dtypes),
        "sheet": sheet,
        "header_row": header_row,
        "drop_duplicates": drop_duplicates,
        "dayfirst": dayfirst,
        "primary_timeline": primary_timeline or (date_cols[0] if date_cols else None),
        "primary_amount": primary_amount or (rev_cols[0] if rev_cols else None),
        "columns": columns_spec,
        "ingestion_profile": ingestion_profile,
    }


def metadata_from_mapping_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Derive legacy schema_json keys from a MappingSpec (compat shim)."""
    date_columns: list[str] = []
    revenue_columns: list[str] = []
    expense_columns: list[str] = []
    category_columns: list[str] = []
    numeric_columns: list[str] = []
    text_columns: list[str] = []
    all_columns: list[str] = []

    primary_timeline = spec.get("primary_timeline")
    primary_amount = spec.get("primary_amount")

    for col in spec.get("columns") or []:
        name = col.get("name")
        if not name:
            continue
        all_columns.append(name)
        role = col.get("role") or "text"
        if role == "timeline":
            date_columns.append(name)
        elif role == "amount_inflow":
            revenue_columns.append(name)
        elif role == "amount_outflow":
            expense_columns.append(name)
        elif role == "dimension":
            category_columns.append(name)
        elif role in ("quantity", "identifier"):
            numeric_columns.append(name)
        elif role == "ignore":
            continue
        else:
            text_columns.append(name)

    # Ensure primaries lead their lists
    if primary_timeline and primary_timeline in date_columns:
        date_columns = [primary_timeline] + [c for c in date_columns if c != primary_timeline]
    if primary_amount and primary_amount in revenue_columns:
        revenue_columns = [primary_amount] + [
            c for c in revenue_columns if c != primary_amount
        ]
    elif primary_amount and primary_amount in expense_columns:
        # Primary amount may be an outflow for expense datasets
        pass
    elif primary_amount and primary_amount in numeric_columns:
        revenue_columns = [primary_amount] + revenue_columns
        numeric_columns = [c for c in numeric_columns if c != primary_amount]

    return {
        "date_columns": date_columns,
        "revenue_columns": revenue_columns,
        "expense_columns": expense_columns,
        "category_columns": category_columns,
        "numeric_columns": numeric_columns,
        "text_columns": text_columns,
        "all_columns": all_columns,
        "primary_timeline": primary_timeline,
        "primary_amount": primary_amount,
    }


def apply_mapping(
    raw_df: pd.DataFrame,
    spec: dict[str, Any],
    *,
    cleaner: Any = None,
) -> tuple[pd.DataFrame, dict]:
    """Materialize a cleaned dataframe from raw data + MappingSpec."""
    from services.data_cleaner import DataCleaner

    cleaner = cleaner or DataCleaner()
    drop_dupes = bool(spec.get("drop_duplicates"))
    dayfirst = spec.get("dayfirst")
    df, report = cleaner.clean(
        raw_df, drop_duplicates=drop_dupes, dayfirst=dayfirst
    )

    # Drop ignored columns if still present under normalized names
    ignore = {
        c["name"]
        for c in (spec.get("columns") or [])
        if c.get("role") == "ignore"
    }
    # Also match by original_name → normalized
    orig_map = report.get("original_names") or {}
    reverse = {v: k for k, v in orig_map.items()}
    drop_cols = set()
    for c in (spec.get("columns") or []):
        if c.get("role") != "ignore":
            continue
        name = c.get("name")
        if name in df.columns:
            drop_cols.add(name)
        orig = c.get("original_name")
        if orig and reverse.get(orig) in df.columns:
            drop_cols.add(reverse[orig])
    if drop_cols:
        df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    return df, report


def _jsonable(v: Any) -> Any:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    if isinstance(v, (str, int, float, bool)):
        return v
    return str(v)
