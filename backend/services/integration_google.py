"""Google OAuth helpers for Sheets and Drive.

Deliberately parallel to ``integration_microsoft`` rather than sharing a base
class with it: the two providers agree on the broad OAuth2 shape but differ on
the details that actually bite (refresh-token issuance, how a native document
is downloaded), and a shared abstraction would have to be re-opened every time
one of them diverges.

Three Google-specific behaviours this module exists to get right:

1. **A refresh token is issued only on the first consent.** Google returns one
   only when the authorize URL asks for ``access_type=offline``, and reliably
   re-issues it on a repeat connect only with ``prompt=consent``. Without both,
   a reconnect yields an access token that expires in an hour and a connection
   that can never refresh itself again.
2. **The refresh response does not contain a refresh token.** Applying it
   naively would blank the stored one, so the token payload is merged, never
   substituted.
3. **A native Google Sheet is not a file you can download.** It has no bytes of
   its own and must be exported to a real format; only genuinely uploaded files
   (.xlsx/.csv sitting in Drive) can be fetched with ``alt=media``.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import pandas as pd

from config import settings
from services.file_processor import FileProcessor
from services.integration_connectors import (
    IntegrationFetchError,
    IntegrationNotConfiguredError,
)

_file_processor = FileProcessor()

DRIVE_BASE = "https://www.googleapis.com/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"

GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Reading a user's spreadsheets server-side needs Drive read access. This is a
# RESTRICTED scope in Google's classification: a production app using it needs
# OAuth verification and, above certain user counts, an annual third-party
# security assessment. The narrower alternative is drive.file, which only grants
# access to files the user hand-picks through Google's client-side Picker -- that
# avoids verification but cannot list files from the server, which is how this
# whole integration is shaped. See docs/INTEGRATIONS_PLAN.md before launch.
SCOPES = " ".join(
    [
        "https://www.googleapis.com/auth/drive.readonly",
        "openid",
        "email",
    ]
)

# Mime types worth offering: native Sheets plus spreadsheet-ish uploads.
_LISTABLE_MIMES = (
    GOOGLE_SHEET_MIME,
    XLSX_MIME,
    "application/vnd.ms-excel",
    "text/csv",
)


def google_oauth_configured() -> bool:
    return bool(
        settings.GOOGLE_CLIENT_ID
        and settings.GOOGLE_CLIENT_SECRET
        and settings.GOOGLE_REDIRECT_URI
    )


def build_google_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        # Both are required to reliably receive a refresh token -- see module docstring.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _token_expired(config: dict[str, Any]) -> bool:
    expires_at = config.get("access_token_expires_at")
    if not expires_at:
        return True
    try:
        dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    return dt <= datetime.now(UTC) + timedelta(minutes=2)


def _apply_token_payload(config: dict[str, Any], payload: dict[str, Any]) -> None:
    """Merge a token response into config.

    A refresh response carries no refresh_token, so the stored one is left in
    place rather than overwritten with nothing -- losing it would strand the
    connection permanently.
    """
    if payload.get("access_token"):
        config["access_token"] = payload["access_token"]
    if payload.get("refresh_token"):
        config["refresh_token"] = payload["refresh_token"]
    expires_in = int(payload.get("expires_in") or 3600)
    config["access_token_expires_at"] = (
        datetime.now(UTC) + timedelta(seconds=expires_in)
    ).isoformat()


async def google_exchange_code_for_tokens(code: str) -> dict[str, Any]:
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(TOKEN_URL, data=data)
    if resp.status_code >= 400:
        raise IntegrationFetchError(f"Google token exchange failed: {resp.text[:300]}")
    payload = resp.json()
    if not payload.get("refresh_token"):
        # Without this the connection works now and silently dies in an hour.
        raise IntegrationFetchError(
            "Google did not return a refresh token, so this connection could not "
            "stay signed in. Remove Snaptix from your Google account's third-party "
            "access list and connect again."
        )
    return payload


async def google_refresh_access_token(config: dict[str, Any]) -> None:
    refresh_token = str(config.get("refresh_token") or "").strip()
    if not refresh_token:
        raise IntegrationFetchError(
            "Google refresh token is missing. Reconnect this source."
        )
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(TOKEN_URL, data=data)
    if resp.status_code >= 400:
        # A revoked grant is the common case and is not retryable.
        raise IntegrationFetchError(
            "Google sign-in has expired or was revoked for this source. "
            f"Reconnect it. ({resp.text[:200]})"
        )
    _apply_token_payload(config, resp.json())


async def google_ensure_access_token(config: dict[str, Any]) -> str:
    if not google_oauth_configured():
        raise IntegrationNotConfiguredError(
            "Google OAuth is not configured on this deployment."
        )
    if _token_expired(config):
        await google_refresh_access_token(config)
    token = str(config.get("access_token") or "").strip()
    if not token:
        raise IntegrationFetchError("Google access token is missing.")
    return token


async def _drive_get_json(
    access_token: str, path: str, *, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{DRIVE_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code in (401, 403):
        raise IntegrationFetchError(
            "Google denied access to Drive. Reconnect the source and make sure "
            "you grant permission to view your files."
        )
    if resp.status_code >= 400:
        raise IntegrationFetchError(f"Google Drive request failed: {resp.text[:300]}")
    return resp.json()


async def google_list_spreadsheets(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Spreadsheets the signed-in account can read, most recently touched first."""
    token = await google_ensure_access_token(config)
    mime_clause = " or ".join(f"mimeType='{m}'" for m in _LISTABLE_MIMES)
    data = await _drive_get_json(
        token,
        "/files",
        params={
            "q": f"({mime_clause}) and trashed=false",
            "orderBy": "modifiedTime desc",
            "pageSize": 50,
            "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink,owners(emailAddress))",
            # Without this, files shared with the user but living in someone
            # else's Drive are invisible -- a common way teams share a sheet.
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        },
    )
    out: list[dict[str, Any]] = []
    for f in data.get("files", []):
        if not f.get("id"):
            continue
        out.append(
            {
                "id": f["id"],
                "name": f.get("name") or f["id"],
                "mime_type": f.get("mimeType"),
                "last_modified": f.get("modifiedTime"),
                "size": f.get("size"),
                "web_url": f.get("webViewLink"),
                "is_native_sheet": f.get("mimeType") == GOOGLE_SHEET_MIME,
            }
        )
    return out


def _dataframe_from_bytes(content: bytes, *, name: str, content_type: str) -> pd.DataFrame:
    head = content.lstrip()
    if head[:15].startswith(b"<!DOCTYPE") or head[:6].startswith(b"<html"):
        raise IntegrationFetchError(
            "Google returned a web page instead of spreadsheet data. "
            "Reconnect the source."
        )
    lower = name.lower()
    if lower.endswith(".csv") or "text/csv" in content_type:
        return pd.read_csv(io.BytesIO(content))

    import tempfile
    from pathlib import Path

    suffix = ".xls" if lower.endswith(".xls") else ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(content)
        path = fh.name
    try:
        return _file_processor.read(path)
    finally:
        Path(path).unlink(missing_ok=True)


async def google_download_item_as_dataframe(config: dict[str, Any]) -> pd.DataFrame:
    token = await google_ensure_access_token(config)
    file_id = str(config.get("item_id") or "").strip()
    if not file_id:
        raise IntegrationNotConfiguredError("No Google file is selected for this source.")

    mime_type = str(config.get("mime_type") or "")
    name = str(config.get("item_name") or file_id)

    if mime_type == GOOGLE_SHEET_MIME:
        # A native Sheet has no downloadable bytes; it has to be exported.
        # xlsx rather than CSV so multi-tab workbooks survive the round trip
        # and numeric/date typing is preserved.
        url = f"{DRIVE_BASE}/files/{file_id}/export"
        params: dict[str, Any] = {"mimeType": XLSX_MIME}
        name = f"{name}.xlsx"
    else:
        url = f"{DRIVE_BASE}/files/{file_id}"
        params = {"alt": "media", "supportsAllDrives": "true"}

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(
            url, params=params, headers={"Authorization": f"Bearer {token}"}
        )
    if resp.status_code in (401, 403):
        raise IntegrationFetchError(
            "Google denied access to this file. It may have been unshared, or the "
            "connection's permission revoked. Reconnect the source."
        )
    if resp.status_code == 404:
        raise IntegrationFetchError(
            "This Google file no longer exists, or was moved out of reach of the "
            "connected account."
        )
    if resp.status_code >= 400:
        raise IntegrationFetchError(f"Google download failed: {resp.text[:300]}")

    return _dataframe_from_bytes(
        resp.content, name=name, content_type=resp.headers.get("content-type", "")
    )
