"""Stream multipart uploads to disk with a byte cap."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

_CHUNK = 1024 * 1024


async def save_upload_stream_limited(
    file: UploadFile,
    dest: Path,
    max_bytes: int,
) -> bool:
    """Write upload body to ``dest`` without exceeding ``max_bytes``.

    Returns ``True`` if the full body was written. Returns ``False`` if the file
    would exceed the limit (``dest`` is removed). Always closes ``file``.
    """
    total = 0
    oversized = False
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                next_total = total + len(chunk)
                if next_total > max_bytes:
                    oversized = True
                    break
                out.write(chunk)
                total = next_total
    finally:
        await file.close()

    if oversized:
        dest.unlink(missing_ok=True)
        return False
    return True
