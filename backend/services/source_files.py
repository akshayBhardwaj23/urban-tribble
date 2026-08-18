"""The durable, ordered list of raw files behind an upload.

Cleaned parquet is a cache; these are the system of record. Every entry is a
storage key (see services.storage), so the same code works against a local
directory or a bucket.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from models.models import Upload
from services import storage


def parse_source_files(upload: Upload) -> list[dict[str, Any]]:
    raw = getattr(upload, "source_files_json", None)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                return [_normalize_entry(e) for e in data if isinstance(e, dict)]
        except (json.JSONDecodeError, TypeError):
            pass
    # Legacy rows: file_url was the only source, and held a filesystem path.
    if upload.file_url:
        return [
            {
                "key": storage.normalize_key(upload.file_url),
                "path": upload.file_url,
                "filename": upload.filename,
                "kind": "original",
            }
        ]
    return []


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    key = entry.get("key") or storage.normalize_key(entry.get("path") or "")
    return {
        "key": key,
        "path": entry.get("path") or key,
        "filename": entry.get("filename") or Path(key).name,
        "kind": entry.get("kind") or "original",
    }


def set_source_files(upload: Upload, sources: list[dict[str, Any]]) -> None:
    normalized = [_normalize_entry(s) for s in sources]
    upload.source_files_json = json.dumps(normalized)
    # file_url stays pointed at the first raw source for backwards compatibility.
    if normalized:
        upload.file_url = normalized[0]["key"]


def append_source_file(
    upload: Upload,
    *,
    key: str,
    filename: str,
    kind: str = "append",
) -> list[dict[str, Any]]:
    sources = parse_source_files(upload)
    sources.append({"key": key, "path": key, "filename": filename, "kind": kind})
    set_source_files(upload, sources)
    return sources


def init_source_file(
    upload: Upload,
    *,
    key: str,
    filename: str,
    kind: str = "original",
) -> list[dict[str, Any]]:
    sources = [{"key": key, "path": key, "filename": filename, "kind": kind}]
    set_source_files(upload, sources)
    return sources


def source_keys(upload: Upload) -> list[str]:
    return [s["key"] for s in parse_source_files(upload) if s.get("key")]


def existing_source_paths(upload: Upload) -> list[Path]:
    """Local readable paths for each source, downloading from storage if needed."""
    out: list[Path] = []
    for key in source_keys(upload):
        if not storage.exists(key):
            continue
        try:
            out.append(storage.materialize(key))
        except Exception:  # noqa: BLE001 — a missing object must not break the rest
            continue
    return out


def delete_all_sources(upload: Upload) -> None:
    for key in source_keys(upload):
        storage.delete(key)
