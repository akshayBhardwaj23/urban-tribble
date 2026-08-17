"""Resolve `{upload_id}_cleaned.parquet`; rebuild from durable raw sources when missing."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from models.models import Dataset, Upload
from services import storage
from services.column_profile import apply_mapping
from services.data_cleaner import DataCleaner
from services.file_processor import FileProcessor
from services.source_files import existing_source_paths

_file_processor = FileProcessor()
_data_cleaner = DataCleaner()


class CleanedDataMissingError(Exception):
    """Neither cleaned parquet nor the original upload file is available in storage."""

    def __init__(self, message: str = "Original upload file is missing from storage."):
        self.message = message
        super().__init__(message)


def cleaned_parquet_key(upload: Upload) -> str:
    return storage.parquet_key(upload.id)


def cleaned_parquet_path(upload: Upload) -> Path:
    """Local readable path for the cache, downloading it when storage is remote."""
    return storage.materialize(cleaned_parquet_key(upload))


def invalidate_cleaned_parquet(upload: Upload) -> None:
    storage.delete(cleaned_parquet_key(upload))


def write_cleaned_parquet(upload: Upload, df: pd.DataFrame) -> str:
    key = cleaned_parquet_key(upload)
    with storage.staged_path(key, suffix=".parquet") as path:
        df.to_parquet(str(path), index=False)
    return key


def _load_raw_combined(
    upload: Upload,
    *,
    sheet: str | None = None,
    header_row: int | None = None,
) -> pd.DataFrame:
    paths = existing_source_paths(upload)
    if not paths:
        raise CleanedDataMissingError(
            "Original upload file is missing from storage. Re-upload the dataset."
        )
    frames: list[pd.DataFrame] = []
    for i, path in enumerate(paths):
        # Sheet/header options apply to the first (primary) source
        if i == 0:
            df = _file_processor.read(
                str(path), sheet_name=sheet, header_row=header_row
            )
        else:
            df = _file_processor.read(str(path))
        # Align headers across sources (case/spacing) before concat
        df = df.copy()
        df.columns = [_light_norm(c) for c in df.columns]
        frames.append(df)
    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, ignore_index=True)


def _light_norm(col) -> str:
    import re

    raw = str(col).strip() if col is not None else ""
    if not raw or raw.lower() in ("nan", "none"):
        return "column"
    name = re.sub(r"\s+", "_", raw).lower()
    name = re.sub(r"[^\w]", "", name)
    return name or "column"


def ensure_cleaned_parquet(
    upload: Upload,
    *,
    dataset: Dataset | None = None,
) -> Path:
    """Return a local path to the cleaned parquet, rebuilding from sources if absent."""
    key = cleaned_parquet_key(upload)
    if storage.exists(key):
        return storage.materialize(key)

    spec = None
    if dataset and getattr(dataset, "mapping_spec_json", None):
        try:
            spec = json.loads(dataset.mapping_spec_json)
        except (json.JSONDecodeError, TypeError):
            spec = None

    sheet = (spec or {}).get("sheet")
    header_row = (spec or {}).get("header_row")
    raw = _load_raw_combined(upload, sheet=sheet, header_row=header_row)

    if spec:
        df, _ = apply_mapping(raw, spec, cleaner=_data_cleaner)
    else:
        df, _ = _data_cleaner.clean(raw)
    write_cleaned_parquet(upload, df)
    return storage.materialize(key)


def rebuild_from_sources(
    upload: Upload,
    *,
    dataset: Dataset | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Force re-derive cleaned dataframe from raw sources (ignores existing parquet)."""
    invalidate_cleaned_parquet(upload)
    spec = None
    if dataset and getattr(dataset, "mapping_spec_json", None):
        try:
            spec = json.loads(dataset.mapping_spec_json)
        except (json.JSONDecodeError, TypeError):
            spec = None
    sheet = (spec or {}).get("sheet")
    header_row = (spec or {}).get("header_row")
    raw = _load_raw_combined(upload, sheet=sheet, header_row=header_row)
    if spec:
        df, report = apply_mapping(raw, spec, cleaner=_data_cleaner)
    else:
        df, report = _data_cleaner.clean(raw)
    write_cleaned_parquet(upload, df)
    return df, report
