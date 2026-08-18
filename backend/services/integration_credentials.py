"""Encryption at rest for integration credentials.

``DataSourceIntegration.config_json`` holds live third-party secrets: Stripe
secret keys, Shopify admin tokens, HubSpot private-app tokens, Postgres
connection strings, Google service-account JSON, and Microsoft **refresh**
tokens. Held as cleartext, any database dump or read-only SQL leak is a full
compromise of every connected customer system, so the column is written as an
authenticated envelope instead.

Format is ``enc:v1:<fernet token>``. Anything without that prefix is read as
legacy cleartext JSON, so rows written before this change keep working and are
upgraded the next time they are written (or in bulk via
``scripts.encrypt_integration_credentials``).

When no key is configured the column stays cleartext, which is exactly the
behaviour that shipped before, so local development needs no setup. A
production deployment in that state is refused at boot by
``config.collect_runtime_setting_errors``.

``INTEGRATION_CREDENTIALS_KEY`` accepts a comma-separated list. The first key
encrypts; every key is tried on decrypt, which is what makes rotation a
two-deploy operation rather than an outage:

    1. deploy with ``new,old`` and run the backfill script
    2. deploy with ``new``
"""

from __future__ import annotations

import json
from typing import Any

from config import settings
from services.integration_connectors import IntegrationNotConfiguredError

ENVELOPE_PREFIX = "enc:v1:"


class IntegrationCredentialsError(IntegrationNotConfiguredError):
    """Stored credentials could not be read with the configured key(s).

    Subclasses ``IntegrationNotConfiguredError`` so the existing sync and route
    error handling reports it as a 422 with a readable message and parks the
    integration in ``error``, rather than surfacing a 500.
    """


_cipher_cache: tuple[str, Any] | None = None


def parse_keys(raw: str | None) -> list[str]:
    return [k.strip() for k in (raw or "").strip().split(",") if k.strip()]


def configured_keys() -> list[str]:
    return parse_keys(settings.INTEGRATION_CREDENTIALS_KEY)


def encryption_enabled() -> bool:
    return bool(configured_keys())


def generate_key() -> str:
    """A fresh key in the format ``INTEGRATION_CREDENTIALS_KEY`` expects."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("utf-8")


def _build_cipher(keys: list[str]) -> Any:
    from cryptography.fernet import Fernet, MultiFernet

    try:
        return MultiFernet([Fernet(k.encode("utf-8")) for k in keys])
    except (ValueError, TypeError) as e:
        raise IntegrationCredentialsError(
            "INTEGRATION_CREDENTIALS_KEY is not a valid key. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"`.'
        ) from e


def _cipher() -> Any | None:
    """MultiFernet over the configured keys, or None when encryption is off."""
    global _cipher_cache
    keys = configured_keys()
    if not keys:
        return None

    cache_key = "\x00".join(keys)
    if _cipher_cache is not None and _cipher_cache[0] == cache_key:
        return _cipher_cache[1]

    cipher = _build_cipher(keys)
    _cipher_cache = (cache_key, cipher)
    return cipher


def validate_configured_keys(raw: str | None = None) -> str | None:
    """Startup check. Returns an error message, or None when the config is usable.

    Takes the raw setting value so the production guard can validate the
    ``Settings`` instance it was handed rather than the process-wide one.
    """
    keys = parse_keys(raw) if raw is not None else configured_keys()
    if not keys:
        return None
    try:
        _build_cipher(keys)
    except IntegrationCredentialsError as e:
        return str(e)
    return None


def encrypt_config(config: dict[str, Any] | None) -> str:
    """Serialise a credential dict for storage in ``config_json``."""
    payload = json.dumps(config or {})
    cipher = _cipher()
    if cipher is None:
        return payload
    return ENVELOPE_PREFIX + cipher.encrypt(payload.encode("utf-8")).decode("utf-8")


def is_encrypted(raw: str | None) -> bool:
    return bool(raw) and str(raw).startswith(ENVELOPE_PREFIX)


def decrypt_config(raw: str | None) -> dict[str, Any]:
    """Read a stored ``config_json``, encrypted or legacy cleartext."""
    if not raw:
        return {}

    if not is_encrypted(raw):
        # Legacy cleartext row, or a deployment with encryption switched off.
        # Unreadable JSON has always been treated as "no credentials"; keep that.
        try:
            loaded = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    cipher = _cipher()
    if cipher is None:
        raise IntegrationCredentialsError(
            "This connection's credentials are encrypted but "
            "INTEGRATION_CREDENTIALS_KEY is not set on this deployment. "
            "Restore the key, or remove and reconnect the integration."
        )

    from cryptography.fernet import InvalidToken

    token = raw[len(ENVELOPE_PREFIX) :].encode("utf-8")
    try:
        decrypted = cipher.decrypt(token)
    except InvalidToken as e:
        raise IntegrationCredentialsError(
            "This connection's credentials could not be decrypted with the "
            "current INTEGRATION_CREDENTIALS_KEY. If the key was rotated, add "
            "the previous key to the list. Otherwise remove and reconnect the "
            "integration."
        ) from e

    try:
        loaded = json.loads(decrypted.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise IntegrationCredentialsError(
            "Stored credentials decrypted but are not readable JSON. "
            "Remove and reconnect the integration."
        ) from e
    return loaded if isinstance(loaded, dict) else {}
