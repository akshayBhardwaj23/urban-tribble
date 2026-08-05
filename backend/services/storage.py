"""Object storage for uploads, raw source files and the parquet cache.

Everything the app persists is addressed by a storage key such as
``uploads/<id>.xlsx``. With ``STORAGE_BACKEND=local`` keys map to files under
UPLOAD_DIR, which keeps development a plain directory. With ``s3`` they map to
objects in a bucket, so a redeploy or a second instance does not lose data.

Callers that need a real filesystem path (pandas readers, parquet writers) use
``materialize`` / ``open_write``, which transparently stage through a local
scratch directory when the backend is remote.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import IO, Iterator, Optional

from config import settings

logger = logging.getLogger(__name__)

_s3_client = None
_s3_lock = threading.Lock()


def backend() -> str:
    return (settings.STORAGE_BACKEND or "local").strip().lower()


def is_remote() -> bool:
    return backend() == "s3"


def _root() -> Path:
    root = Path(settings.UPLOAD_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _scratch() -> Path:
    path = _root() / ".cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _client():
    global _s3_client
    if _s3_client is not None:
        return _s3_client
    with _s3_lock:
        if _s3_client is None:
            import boto3

            kwargs = {}
            if settings.S3_REGION:
                kwargs["region_name"] = settings.S3_REGION
            if settings.S3_ENDPOINT_URL:
                kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
            if settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY:
                kwargs["aws_access_key_id"] = settings.S3_ACCESS_KEY_ID
                kwargs["aws_secret_access_key"] = settings.S3_SECRET_ACCESS_KEY
            _s3_client = boto3.client("s3", **kwargs)
    return _s3_client


def _object_key(key: str) -> str:
    prefix = (settings.S3_PREFIX or "").strip("/")
    return f"{prefix}/{key}" if prefix else key


def normalize_key(key_or_path: str) -> str:
    """Accept a storage key or a legacy absolute path and return a storage key.

    Rows written before object storage existed hold filesystem paths in
    ``file_url``; those keep resolving against the local root.
    """
    if not key_or_path:
        return ""
    if key_or_path.startswith("s3://"):
        return key_or_path
    candidate = Path(key_or_path)
    if candidate.is_absolute():
        try:
            return str(candidate.relative_to(_root().resolve()))
        except ValueError:
            return str(candidate)
    return key_or_path.lstrip("./")


def local_path(key: str) -> Path:
    """Filesystem location for a key under the local backend."""
    return _root() / normalize_key(key)


def exists(key: str) -> bool:
    key = normalize_key(key)
    if not key:
        return False
    if Path(key).is_absolute():
        return Path(key).exists()
    if not is_remote():
        return local_path(key).exists()
    try:
        _client().head_object(Bucket=settings.S3_BUCKET, Key=_object_key(key))
        return True
    except Exception:  # noqa: BLE001 — head_object raises ClientError for 404
        return False


def write_bytes(key: str, data: bytes) -> str:
    key = normalize_key(key)
    if not is_remote():
        dest = local_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return key
    _client().put_object(Bucket=settings.S3_BUCKET, Key=_object_key(key), Body=data)
    return key


def read_bytes(key: str) -> bytes:
    key = normalize_key(key)
    if Path(key).is_absolute() or not is_remote():
        return Path(key if Path(key).is_absolute() else local_path(key)).read_bytes()
    obj = _client().get_object(Bucket=settings.S3_BUCKET, Key=_object_key(key))
    return obj["Body"].read()


def upload_file(source: Path, key: str) -> str:
    """Move a locally staged file into storage and return its key."""
    key = normalize_key(key)
    if not is_remote():
        dest = local_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != dest.resolve():
            shutil.move(str(source), str(dest))
        return key
    _client().upload_file(str(source), settings.S3_BUCKET, _object_key(key))
    with contextlib.suppress(OSError):
        source.unlink()
    return key


def delete(key: str) -> None:
    key = normalize_key(key)
    if not key:
        return
    if Path(key).is_absolute() or not is_remote():
        target = Path(key) if Path(key).is_absolute() else local_path(key)
        with contextlib.suppress(OSError):
            target.unlink()
        _drop_cached(key)
        return
    with contextlib.suppress(Exception):
        _client().delete_object(Bucket=settings.S3_BUCKET, Key=_object_key(key))
    _drop_cached(key)


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return _scratch() / f"{digest}{''.join(Path(key).suffixes[-1:])}"


def _drop_cached(key: str) -> None:
    with contextlib.suppress(OSError):
        _cache_path(key).unlink()


def materialize(key: str) -> Path:
    """Return a readable local path for a key, downloading it if necessary."""
    key = normalize_key(key)
    if Path(key).is_absolute():
        return Path(key)
    if not is_remote():
        return local_path(key)

    cached = _cache_path(key)
    if cached.exists():
        return cached
    cached.parent.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(cached.suffix + ".part")
    _client().download_file(settings.S3_BUCKET, _object_key(key), str(tmp))
    tmp.replace(cached)
    return cached


@contextlib.contextmanager
def open_write(key: str, mode: str = "wb") -> Iterator[IO]:
    """Write to a local temp file, then publish it to storage on clean exit."""
    key = normalize_key(key)
    if not is_remote():
        dest = local_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, mode) as fh:
            yield fh
        return

    fd, tmp_name = tempfile.mkstemp(dir=str(_scratch()))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with open(tmp, mode) as fh:
            yield fh
        _client().upload_file(str(tmp), settings.S3_BUCKET, _object_key(key))
        _drop_cached(key)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


@contextlib.contextmanager
def staged_path(key: str, suffix: str = "") -> Iterator[Path]:
    """Yield a local path to write to; contents are published to ``key`` afterwards."""
    key = normalize_key(key)
    if not is_remote():
        dest = local_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        yield dest
        return

    fd, tmp_name = tempfile.mkstemp(dir=str(_scratch()), suffix=suffix or Path(key).suffix)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        yield tmp
        if tmp.exists() and tmp.stat().st_size > 0:
            _client().upload_file(str(tmp), settings.S3_BUCKET, _object_key(key))
            _drop_cached(key)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def upload_key(upload_id: str, suffix: str) -> str:
    return f"uploads/{upload_id}{suffix}"


def parquet_key(upload_id: str) -> str:
    return f"parquet/{upload_id}_cleaned.parquet"


def describe() -> dict:
    return {
        "backend": backend(),
        "bucket": settings.S3_BUCKET if is_remote() else None,
        "root": str(_root()) if not is_remote() else None,
    }
