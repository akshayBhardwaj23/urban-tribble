"""Content checks that run before a file is parsed or stored.

An extension is a claim by the client. These checks look at the bytes, and at
the shape of the parsed frame, so a renamed archive or a 40-million-row sheet is
rejected with a clear message instead of exhausting memory.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import settings

ZIP_MAGIC = b"PK\x03\x04"
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# Some tools emit an empty or spanned zip header for a valid xlsx.
ZIP_VARIANTS = (ZIP_MAGIC, b"PK\x05\x06", b"PK\x07\x08")


class FileValidationError(ValueError):
    """The uploaded bytes do not match the declared file type, or are too large."""


def sniff_kind(head: bytes) -> str:
    """Classify a file from its leading bytes: zip | ole2 | text | binary."""
    if head.startswith(ZIP_VARIANTS):
        return "zip"
    if head.startswith(OLE2_MAGIC):
        return "ole2"
    if b"\x00" in head[:2048]:
        return "binary"
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            head.decode(encoding)
            return "text"
        except UnicodeDecodeError:
            continue
    return "binary"


EXPECTED_KINDS = {
    ".xlsx": {"zip"},
    ".xlsm": {"zip"},
    ".xls": {"ole2", "zip", "text"},  # many ".xls" exports are really CSV or xlsx
    ".csv": {"text"},
    ".tsv": {"text"},
}


def resolve_reader_ext(path: Path, declared_ext: str) -> str:
    """Prefer sniffed content over the client-declared extension when they disagree safely.

    A ``.xls`` that is really a zip is read as xlsx; a ``.xls`` that is text is
    read as csv. Declared extension remains the default when the sniff agrees.
    """
    declared = (declared_ext or path.suffix).lower()
    try:
        with open(path, "rb") as fh:
            head = fh.read(8192)
    except OSError:
        return declared
    kind = sniff_kind(head)
    if kind == "zip" and declared in (".xls", ".xlsx", ".xlsm"):
        return ".xlsx"
    if kind == "ole2" and declared in (".xls", ".xlsx", ".xlsm"):
        return ".xls"
    if kind == "text" and declared in (".xls", ".xlsx", ".xlsm", ".csv", ".tsv"):
        # Heuristic: tab-heavy → tsv, else csv
        sample = head.decode("utf-8", errors="ignore")
        if sample.count("\t") > sample.count(",") and sample.count("\t") > 2:
            return ".tsv"
        return ".csv"
    return declared


def validate_magic_bytes(path: Path, ext: str) -> None:
    """Raise when the bytes contradict the declared extension."""
    ext = ext.lower()
    expected = EXPECTED_KINDS.get(ext)
    if not expected:
        raise FileValidationError(f"File type {ext} is not supported.")

    try:
        with open(path, "rb") as fh:
            head = fh.read(8192)
    except OSError as exc:
        raise FileValidationError(f"Could not read the uploaded file: {exc}") from exc

    if not head:
        raise FileValidationError("The uploaded file is empty.")

    kind = sniff_kind(head)
    if kind not in expected:
        raise FileValidationError(
            f"This file is named {ext} but its contents look like "
            f"{_human_kind(kind)}. Re-export it and try again."
        )

    if kind == "zip" and ext in (".xlsx", ".xlsm", ".xls"):
        _reject_zip_bomb(path)


def _human_kind(kind: str) -> str:
    return {
        "zip": "a zip archive",
        "ole2": "a legacy Excel or Office document",
        "text": "plain text",
        "binary": "an unrecognized binary format",
    }.get(kind, kind)


def _reject_zip_bomb(path: Path, max_ratio: int = 200, max_uncompressed_mb: int = 2048) -> None:
    """A workbook is a zip; refuse one that expands out of proportion."""
    import zipfile

    try:
        with zipfile.ZipFile(path) as zf:
            compressed = sum(i.compress_size for i in zf.infolist()) or 1
            uncompressed = sum(i.file_size for i in zf.infolist())
    except zipfile.BadZipFile as exc:
        raise FileValidationError("This workbook appears to be corrupt.") from exc

    if uncompressed > max_uncompressed_mb * 1024 * 1024:
        raise FileValidationError(
            f"This workbook expands to over {max_uncompressed_mb} MB, which is too large to process."
        )
    if uncompressed / compressed > max_ratio:
        raise FileValidationError("This workbook's compression ratio looks unsafe.")


def validate_frame_size(df: pd.DataFrame, *, filename: str | None = None) -> None:
    """Raise when a parsed frame exceeds the configured row or column caps."""
    max_rows = int(getattr(settings, "MAX_ROWS_PER_FILE", 1_000_000))
    max_cols = int(getattr(settings, "MAX_COLUMNS_PER_FILE", 512))
    label = f"{filename}: " if filename else ""

    if max_cols and len(df.columns) > max_cols:
        raise FileValidationError(
            f"{label}{len(df.columns):,} columns exceeds the limit of {max_cols:,}. "
            "This usually means the header row was misdetected."
        )
    if max_rows and len(df) > max_rows:
        raise FileValidationError(
            f"{label}{len(df):,} rows exceeds the limit of {max_rows:,} rows per file. "
            "Split the file or contact support to raise the limit."
        )
