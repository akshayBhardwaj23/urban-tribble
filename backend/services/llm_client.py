"""One place where the backend talks to OpenAI.

Every call gets a timeout, bounded retries with backoff, and an optional TTL
cache. Callers receive ``None`` on any failure rather than an exception, so a
degraded model provider never takes an endpoint down — each caller is expected
to have a deterministic fallback.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import time
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()
_MAX_CACHE_ENTRIES = 512

# Errors worth retrying: transient transport and provider-side capacity.
_RETRYABLE = ("timeout", "rate limit", "429", "500", "502", "503", "504", "connection")


def cache_key(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


def _cache_get(key: str) -> Any | None:
    ttl = int(getattr(settings, "OPENAI_CACHE_TTL_SECONDS", 0) or 0)
    if ttl <= 0:
        return None
    with _cache_lock:
        hit = _cache.get(key)
        if not hit:
            return None
        stored_at, value = hit
        if time.time() - stored_at > ttl:
            _cache.pop(key, None)
            return None
        return value


def _cache_put(key: str, value: Any) -> None:
    ttl = int(getattr(settings, "OPENAI_CACHE_TTL_SECONDS", 0) or 0)
    if ttl <= 0:
        return
    with _cache_lock:
        if len(_cache) >= _MAX_CACHE_ENTRIES:
            oldest = sorted(_cache.items(), key=lambda kv: kv[1][0])[: _MAX_CACHE_ENTRIES // 4]
            for k, _ in oldest:
                _cache.pop(k, None)
        _cache[key] = (time.time(), value)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def is_configured() -> bool:
    return bool((getattr(settings, "OPENAI_API_KEY", "") or "").strip())


def _client():
    from openai import OpenAI

    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=float(getattr(settings, "OPENAI_TIMEOUT_SECONDS", 30.0)),
        max_retries=0,  # retries are handled here so backoff and logging are uniform
    )


def chat_json(
    messages: list[dict[str, str]],
    *,
    purpose: str,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    model: str | None = None,
    cache: bool = True,
    cache_salt: Any = None,
) -> dict[str, Any] | None:
    """Request a JSON object completion. Returns None if unavailable or invalid."""
    if not is_configured():
        return None

    chosen_model = model or settings.OPENAI_MODEL
    key = cache_key(purpose, chosen_model, temperature, messages, cache_salt)
    if cache:
        hit = _cache_get(key)
        if hit is not None:
            return hit

    attempts = max(1, int(getattr(settings, "OPENAI_MAX_RETRIES", 2)) + 1)
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            kwargs: dict[str, Any] = {
                "model": chosen_model,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            }
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            response = _client().chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                logger.info("llm %s returned non-object JSON", purpose)
                return None
            if cache:
                _cache_put(key, parsed)
            return parsed
        except json.JSONDecodeError as exc:
            logger.info("llm %s returned unparseable JSON: %s", purpose, exc)
            return None
        except Exception as exc:  # noqa: BLE001 — provider SDK raises many types
            last_error = exc
            if attempt == attempts - 1 or not _is_retryable(exc):
                break
            backoff = (2**attempt) * 0.5 + random.uniform(0, 0.25)
            logger.info(
                "llm %s attempt %d/%d failed (%s); retrying in %.2fs",
                purpose,
                attempt + 1,
                attempts,
                exc,
                backoff,
            )
            time.sleep(backoff)

    logger.warning("llm %s unavailable after %d attempts: %s", purpose, attempts, last_error)
    return None


def _is_retryable(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _RETRYABLE)
