"""Structured logging, error tracking and request correlation.

Errors used to vanish into stdout with no way to correlate a user report with a
traceback. Every request now carries an id that appears in the log line, in the
Sentry event, and in the response header, so a screenshot is enough to find it.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("snaptix.request")

# Never log these, whatever level is configured.
_REDACT_KEYS = {"authorization", "cookie", "x-internal-auth-secret", "x-razorpay-signature"}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key in ("method", "path", "status", "duration_ms", "user_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    level = getattr(logging, (settings.LOG_LEVEL or "INFO").upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if settings.LOG_JSON:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # These are chatty at INFO and say nothing the request log does not.
    for noisy in ("uvicorn.access", "botocore", "urllib3", "openai", "httpx"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def configure_sentry() -> bool:
    dsn = (settings.SENTRY_DSN or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; error tracking is off."
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.APP_ENV,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        before_send=_scrub_event,
    )
    return True


def _scrub_event(event: dict, _hint: dict) -> dict:
    headers = (event.get("request") or {}).get("headers") or {}
    for key in list(headers):
        if key.lower() in _REDACT_KEYS:
            headers[key] = "[redacted]"
    return event


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = (time.perf_counter() - started) * 1000
            logger.exception(
                "unhandled error",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": round(duration, 1),
                },
            )
            request_id_var.reset(token)
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Something went wrong on our side. "
                    f"Quote reference {request_id} if you contact support."
                },
                headers={"X-Request-ID": request_id},
            )

        duration = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        if response.status_code >= 500 or duration > 3000:
            level = logging.WARNING
        elif response.status_code >= 400:
            level = logging.INFO
        else:
            level = logging.DEBUG
        logger.log(
            level,
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration, 1),
            },
        )
        request_id_var.reset(token)
        return response
