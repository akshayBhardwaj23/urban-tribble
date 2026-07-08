"""Microsoft 365 / Graph helpers for Excel and OneDrive."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import io

import httpx
import pandas as pd

from config import settings
from services.file_processor import FileProcessor


class IntegrationFetchError(Exception):
    pass


_file_processor = FileProcessor()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _token_expired(config: dict[str, Any]) -> bool:
    expires_at = config.get("access_token_expires_at")
    if not expires_at:
        return True
    try:
        dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    return dt <= datetime.now(timezone.utc) + timedelta(minutes=2)


def _apply_token_payload(config: dict[str, Any], payload: dict[str, Any]) -> None:
    if payload.get("access_token"):
        config["access_token"] = payload["access_token"]
    if payload.get("refresh_token"):
        config["refresh_token"] = payload["refresh_token"]
    expires_in = int(payload.get("expires_in") or 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    config["access_token_expires_at"] = expires_at.isoformat()


async def microsoft_exchange_code_for_tokens(code: str) -> dict[str, Any]:
    tenant = settings.MICROSOFT_TENANT_ID or "common"
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "scope": "offline_access User.Read Files.Read",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(token_url, data=data)
    if resp.status_code >= 400:
        raise IntegrationFetchError(
            f"Microsoft token exchange failed: {resp.text[:300]}"
        )
    return resp.json()


async def microsoft_refresh_access_token(config: dict[str, Any]) -> None:
    refresh_token = str(config.get("refresh_token") or "").strip()
    if not refresh_token:
        raise IntegrationFetchError("Microsoft refresh token is missing.")
    tenant = settings.MICROSOFT_TENANT_ID or "common"
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "scope": "offline_access User.Read Files.Read",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(token_url, data=data)
    if resp.status_code >= 400:
        raise IntegrationFetchError(
            f"Microsoft token refresh failed: {resp.text[:300]}"
        )
    _apply_token_payload(config, resp.json())


async def microsoft_ensure_access_token(config: dict[str, Any]) -> str:
    if not settings.MICROSOFT_CLIENT_ID or not settings.MICROSOFT_CLIENT_SECRET:
        raise IntegrationFetchError("Microsoft OAuth is not configured on the server.")
    if _token_expired(config):
        await microsoft_refresh_access_token(config)
    token = str(config.get("access_token") or "").strip()
    if not token:
        raise IntegrationFetchError("Microsoft access token is missing.")
    return token


async def microsoft_graph_get_json(
    access_token: str, path: str, *, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{GRAPH_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code >= 400:
        raise IntegrationFetchError(f"Microsoft Graph request failed: {resp.text[:300]}")
    return resp.json()


def _normalize_drive_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        item_id = item.get("id")
        if not item_id or item_id in seen:
            continue
        name = str(item.get("name") or "")
        lower = name.lower()
        if not (lower.endswith(".xlsx") or lower.endswith(".xls") or lower.endswith(".csv")):
            continue
        seen.add(item_id)
        out.append(
            {
                "id": item_id,
                "name": name,
                "web_url": item.get("webUrl"),
                "size": item.get("size"),
                "last_modified": item.get("lastModifiedDateTime"),
                "drive_id": (item.get("parentReference") or {}).get("driveId"),
            }
        )
    return out


async def microsoft_list_excel_files(config: dict[str, Any]) -> list[dict[str, Any]]:
    token = await microsoft_ensure_access_token(config)
    recent = await microsoft_graph_get_json(token, "/me/drive/recent")
    search = await microsoft_graph_get_json(
        token,
        "/me/drive/root/search(q='.xlsx')",
        params={"$top": 50},
    )
    items = _normalize_drive_items((recent.get("value") or []) + (search.get("value") or []))
    return items[:50]


async def microsoft_download_item_as_dataframe(config: dict[str, Any]) -> Any:
    token = await microsoft_ensure_access_token(config)
    item_id = str(config.get("item_id") or "").strip()
    if not item_id:
        raise IntegrationFetchError("Microsoft workbook item is not selected.")
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(
            f"{GRAPH_BASE}/me/drive/items/{item_id}/content",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code >= 400:
        raise IntegrationFetchError(
            f"Microsoft workbook download failed: {resp.text[:300]}"
        )
    content = resp.content
    content_type = resp.headers.get("content-type", "")
    name = str(config.get("item_name") or item_id)
    if content[:15].lstrip().startswith(b"<!DOCTYPE") or content[:6].lstrip().startswith(b"<html"):
        raise IntegrationFetchError("Microsoft returned a web page instead of workbook bytes.")
    if name.lower().endswith(".csv") or "csv" in content_type:
        return pd.read_csv(io.BytesIO(content))
    import tempfile
    from pathlib import Path

    suffix = ".xlsx" if ".xls" not in name.lower() else name[name.lower().rfind(".") :]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
        path = f.name
    try:
        return _file_processor.read(path)
    finally:
        Path(path).unlink(missing_ok=True)
