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
    read_body_limited,
)

_file_processor = FileProcessor()

DRIVE_BASE = "https://www.googleapis.com/drive/v3"
SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
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


def _dataframe_from_bytes(
    content: bytes, *, name: str, sheet_name: str | None = None
) -> pd.DataFrame:
    head = content.lstrip()
    if head[:15].startswith(b"<!DOCTYPE") or head[:6].startswith(b"<html"):
        raise IntegrationFetchError(
            "Google returned a web page instead of spreadsheet data. "
            "Reconnect the source."
        )
    lower = name.lower()
    if lower.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content))

    import tempfile
    from pathlib import Path

    suffix = ".xls" if lower.endswith(".xls") else ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(content)
        path = fh.name
    try:
        try:
            return _file_processor.read(path, sheet_name=sheet_name)
        except ValueError as e:
            # A chosen tab can be renamed or deleted in Google after connecting.
            # Saying which tab is missing is more use than pandas' raw error.
            if sheet_name and sheet_name in str(e):
                raise IntegrationFetchError(
                    f"The tab \"{sheet_name}\" no longer exists in this spreadsheet. "
                    "Choose a different tab for this source."
                ) from e
            raise
    finally:
        Path(path).unlink(missing_ok=True)


# How much of each tab to sample when deciding which one holds the data. Enough
# to tell a populated table from a cover page, small enough that the check stays
# cheap on a workbook with many tabs.
_TAB_SAMPLE_RANGE = "A1:J20"
# A tab scoring at or below this is treated as not a data table (a cover sheet,
# notes, an empty tab), so it does not make a workbook look ambiguous.
_TAB_DATA_SCORE_FLOOR = 1.0


def _score_sampled_rows(rows: list[list[Any]]) -> tuple[float, int, int]:
    """Score a sampled tab with the same heuristic used for uploaded workbooks."""
    if not rows:
        return 0.0, 0, 0
    width = max((len(r) for r in rows), default=0)
    if width == 0:
        return 0.0, 0, 0
    padded = [list(r) + [None] * (width - len(r)) for r in rows]
    frame = pd.DataFrame(padded).replace("", None)
    return (
        float(_file_processor.score_sheet_as_table(frame)),
        int(len(frame)),
        int(width),
    )


async def _sheets_get_json(
    access_token: str, path: str, *, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{SHEETS_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code in (401, 403):
        raise IntegrationFetchError(
            "Google denied access to this spreadsheet's tabs. If this deployment has "
            "only just enabled the Google Sheets API, reconnect the source."
        )
    if resp.status_code >= 400:
        raise IntegrationFetchError(f"Google Sheets request failed: {resp.text[:300]}")
    return resp.json()


async def _native_sheet_tabs(config: dict[str, Any], file_id: str) -> list[dict[str, Any]]:
    """Tabs of a native Google Sheet, without exporting the workbook.

    Two bounded calls regardless of tab count. Deliberately does not use
    gridProperties: that reports the sheet's canvas (1000x26 by default whether
    or not anything is in it), so it cannot distinguish a populated tab from an
    empty one. A small sample of real cells can.
    """
    token = await google_ensure_access_token(config)
    meta = await _sheets_get_json(
        token, f"/{file_id}", params={"fields": "sheets.properties.title"}
    )
    titles = [
        str((sheet.get("properties") or {}).get("title") or "")
        for sheet in meta.get("sheets", [])
    ]
    titles = [t for t in titles if t]
    if not titles:
        return []

    values = await _sheets_get_json(
        token,
        f"/{file_id}/values:batchGet",
        params={
            "ranges": [f"'{t.replace(chr(39), chr(39) * 2)}'!{_TAB_SAMPLE_RANGE}" for t in titles],
            "majorDimension": "ROWS",
        },
    )
    ranges = values.get("valueRanges", [])

    tabs: list[dict[str, Any]] = []
    for index, title in enumerate(titles):
        rows = ranges[index].get("values", []) if index < len(ranges) else []
        score, sampled_rows, cols = _score_sampled_rows(rows)
        tabs.append(
            {"name": title, "score": score, "sampled_rows": sampled_rows, "cols": cols}
        )
    return tabs


async def _uploaded_workbook_tabs(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Tabs of an .xlsx/.xls uploaded to Drive.

    There is no metadata API for these, so the file has to come down. Reuses the
    same scoring the upload path applies to a workbook.
    """
    import tempfile
    from pathlib import Path as _Path

    name = str(config.get("item_name") or "")
    if name.lower().endswith(".csv"):
        return []

    content = await _download_file_bytes(config)
    suffix = ".xls" if name.lower().endswith(".xls") else ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(content)
        path = fh.name
    try:
        return [
            {
                "name": entry["name"],
                "score": float(entry["score"]),
                "sampled_rows": int(entry["rows"]),
                "cols": int(entry["cols"]),
            }
            for entry in _file_processor.list_sheets(path)
        ]
    except Exception:
        return []
    finally:
        _Path(path).unlink(missing_ok=True)


async def google_list_sheet_tabs(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Every tab in the connected workbook, scored by how much it looks like data."""
    file_id = str(config.get("item_id") or "").strip()
    if not file_id:
        return []
    if str(config.get("mime_type") or "") == GOOGLE_SHEET_MIME:
        return await _native_sheet_tabs(config, file_id)
    return await _uploaded_workbook_tabs(config)


def data_tabs(tabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tabs that plausibly hold a table, best first."""
    candidates = [t for t in tabs if float(t.get("score") or 0) > _TAB_DATA_SCORE_FLOOR]
    return sorted(candidates, key=lambda t: -float(t.get("score") or 0))


def tab_choice_is_ambiguous(tabs: list[dict[str, Any]]) -> bool:
    """Whether the user should be asked which tab to use.

    Only when more than one tab actually looks like a data table. A workbook
    with a cover page and one table is not a decision worth interrupting for --
    the cover page scores below the floor and the table is taken automatically.
    """
    return len(data_tabs(tabs)) > 1


def default_tab_name(tabs: list[dict[str, Any]]) -> str | None:
    best = data_tabs(tabs)
    return best[0]["name"] if best else None


async def google_remote_change_stamp(config: dict[str, Any]) -> str | None:
    """Drive's ``modifiedTime`` for the connected file, or None if unknowable.

    One cheap metadata call, so a scheduled refresh of a sheet nobody has
    touched can stop before downloading and re-processing the whole thing.

    Returns None rather than raising on any problem: this is an optimisation,
    and a failed probe must fall through to a normal sync rather than turning a
    working connection into an error.
    """
    file_id = str(config.get("item_id") or "").strip()
    if not file_id:
        return None
    try:
        token = await google_ensure_access_token(config)
        data = await _drive_get_json(
            token,
            f"/files/{file_id}",
            params={"fields": "modifiedTime", "supportsAllDrives": "true"},
        )
    except Exception:
        return None
    stamp = data.get("modifiedTime")
    return str(stamp) if stamp else None


def _download_target(config: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    """URL, query and filename for fetching the connected file's bytes."""
    file_id = str(config.get("item_id") or "").strip()
    if not file_id:
        raise IntegrationNotConfiguredError("No Google file is selected for this source.")
    name = str(config.get("item_name") or file_id)

    if str(config.get("mime_type") or "") == GOOGLE_SHEET_MIME:
        # A native Sheet has no downloadable bytes; it has to be exported.
        # xlsx rather than CSV so multi-tab workbooks survive the round trip
        # and numeric/date typing is preserved.
        return (
            f"{DRIVE_BASE}/files/{file_id}/export",
            {"mimeType": XLSX_MIME},
            f"{name}.xlsx",
        )
    return (
        f"{DRIVE_BASE}/files/{file_id}",
        {"alt": "media", "supportsAllDrives": "true"},
        name,
    )


async def _download_file_bytes(config: dict[str, Any]) -> bytes:
    """Fetch the connected file's bytes, refusing anything past the fetch cap.

    Streamed rather than buffered: an uploaded .xlsx in Drive is served through
    ``alt=media``, which has no size ceiling of Google's own, so without a cap
    here a large workbook would be pulled entirely into memory and only rejected
    afterwards by the row/column caps in ingest.
    """
    token = await google_ensure_access_token(config)
    url, params, _ = _download_target(config)

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        async with client.stream(
            "GET", url, params=params, headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            if resp.status_code >= 400:
                # On an error the body is a small JSON payload, not file bytes,
                # so reading it in full is safe and makes resp.text usable.
                await resp.aread()
                _raise_for_download_error(resp)
            return await read_body_limited(resp, source="Google")


def _raise_for_download_error(resp: httpx.Response) -> None:
    body = resp.text or ""
    if "exportSizeLimitExceeded" in body:
        # Google's own ceiling on exporting a native Sheet, which it reports as
        # a 403. Saying "denied access, reconnect" here would send someone off
        # to re-authorise a connection that is working fine.
        raise IntegrationFetchError(
            "This Google Sheet is too large for Google to export in one piece. "
            "Split it into smaller sheets, or connect a specific tab."
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
    raise IntegrationFetchError(f"Google download failed: {body[:300]}")


async def google_download_item_as_dataframe(config: dict[str, Any]) -> pd.DataFrame:
    """Read the connected workbook.

    When the user picked a tab at connect time it is read explicitly; otherwise
    the reader's own auto-pick chooses the most table-like tab, which is what
    happens for single-tab workbooks and for anything connected before tab
    selection existed.
    """
    content = await _download_file_bytes(config)
    _, _, name = _download_target(config)
    sheet_name = str(config.get("sheet_name") or "").strip() or None
    return _dataframe_from_bytes(content, name=name, sheet_name=sheet_name)
