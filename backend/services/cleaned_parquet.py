"""Resolve `{upload_id}_cleaned.parquet`; rebuild from the original file when parquet is missing."""

from __future__ import annotations

from pathlib import Path

from models.models import Upload
from services.data_cleaner import DataCleaner
from services.file_processor import FileProcessor

_file_processor = FileProcessor()
_data_cleaner = DataCleaner()


class CleanedDataMissingError(Exception):
    """Neither cleaned parquet nor the original upload file is available on disk."""

    def __init__(self, message: str = "Original upload file is missing from storage."):
        self.message = message
        super().__init__(message)


def cleaned_parquet_path(upload: Upload) -> Path:
    return Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"


def ensure_cleaned_parquet(upload: Upload) -> Path:
    """Return path to cleaned parquet, rebuilding from ``upload.file_url`` if parquet is absent."""
    p = cleaned_parquet_path(upload)
    if p.exists():
        return p
    original = Path(upload.file_url)
    if not original.exists():
        raise CleanedDataMissingError(
            "Original upload file is missing from storage. Re-upload the dataset."
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    df = _file_processor.read(str(original))
    df, _ = _data_cleaner.clean(df)
    df.to_parquet(str(p), index=False)
    return p
