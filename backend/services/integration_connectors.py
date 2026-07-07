"""Fetch tabular data from connected providers."""

from __future__ import annotations

import io
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import pandas as pd

from services.file_processor import FileProcessor

_file_processor = FileProcessor()


class IntegrationFetchError(Exception):
    pass


class IntegrationNotConfiguredError(IntegrationFetchError):
    pass


def _resolve_google_sheets_url(config: dict[str, Any]) -> str:
    if config.get("export_url"):
        return str(config["export_url"]).strip()
    sid = config.get("spreadsheet_id")
    if not sid:
        raise IntegrationNotConfiguredError(
            "Provide a CSV export URL or spreadsheet ID for Google Sheets."
        )
    gid = str(config.get("gid") or "0").strip()
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}"


def _guess_extension(url: str, content_type: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".xlsx") or path.endswith(".xls"):
        return path[path.rfind(".") :]
    if "spreadsheetml" in content_type or "excel" in content_type:
        return ".xlsx"
    return ".csv"


async def fetch_from_export_url(config: dict[str, Any]) -> pd.DataFrame:
    url = str(config.get("export_url") or "").strip()
    if not url:
        raise IntegrationNotConfiguredError("Export URL is required.")
    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.content
        ctype = resp.headers.get("content-type", "")
    ext = _guess_extension(url, ctype)
    tmp = io.BytesIO(content)
    if ext == ".csv":
        return pd.read_csv(tmp)
    # Excel or unknown — use file processor on bytes via temp path pattern
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(content)
        path = f.name
    try:
        return _file_processor.read(path)
    finally:
        Path(path).unlink(missing_ok=True)


async def fetch_google_sheets(config: dict[str, Any]) -> pd.DataFrame:
    url = _resolve_google_sheets_url(config)
    return await fetch_from_export_url({"export_url": url})


async def fetch_stripe(config: dict[str, Any]) -> pd.DataFrame:
    secret = str(config.get("secret_key") or "").strip()
    if not secret:
        raise IntegrationNotConfiguredError("Stripe secret key is required.")
    days_back = int(config.get("days_back") or 90)
    since = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())
    rows: list[dict[str, Any]] = []
    url = "https://api.stripe.com/v1/charges"
    params: dict[str, Any] = {"limit": 100, "created[gte]": since}
    async with httpx.AsyncClient(timeout=60.0) as client:
        while url:
            resp = await client.get(
                url,
                params=params if url.endswith("/charges") else None,
                auth=(secret, ""),
            )
            if resp.status_code == 401:
                raise IntegrationFetchError("Invalid Stripe secret key.")
            resp.raise_for_status()
            data = resp.json()
            for ch in data.get("data", []):
                rows.append(
                    {
                        "charge_id": ch.get("id"),
                        "created_at": datetime.fromtimestamp(
                            ch.get("created", 0), tz=timezone.utc
                        ).isoformat(),
                        "amount": (ch.get("amount") or 0) / 100.0,
                        "currency": ch.get("currency"),
                        "status": ch.get("status"),
                        "paid": ch.get("paid"),
                        "customer": ch.get("customer"),
                        "description": ch.get("description"),
                    }
                )
            if not data.get("has_more"):
                break
            last_id = data["data"][-1]["id"]
            url = "https://api.stripe.com/v1/charges"
            params = {"limit": 100, "created[gte]": since, "starting_after": last_id}
    if not rows:
        raise IntegrationFetchError("No Stripe charges found for the selected period.")
    return pd.DataFrame(rows)


async def fetch_shopify(config: dict[str, Any]) -> pd.DataFrame:
    shop = str(config.get("shop_domain") or "").strip().rstrip("/")
    token = str(config.get("access_token") or "").strip()
    if not shop or not token:
        raise IntegrationNotConfiguredError("Shop domain and access token are required.")
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"
    days_back = int(config.get("days_back") or 90)
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()
    rows: list[dict[str, Any]] = []
    url = f"https://{shop}/admin/api/2024-01/orders.json"
    params: dict[str, Any] = {"status": "any", "limit": 250, "created_at_min": since}
    headers = {"X-Shopify-Access-Token": token}
    async with httpx.AsyncClient(timeout=60.0) as client:
        while url:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 401:
                raise IntegrationFetchError("Invalid Shopify access token or shop domain.")
            resp.raise_for_status()
            data = resp.json()
            for order in data.get("orders", []):
                rows.append(
                    {
                        "order_id": order.get("id"),
                        "order_number": order.get("order_number"),
                        "created_at": order.get("created_at"),
                        "total_price": float(order.get("total_price") or 0),
                        "currency": order.get("currency"),
                        "financial_status": order.get("financial_status"),
                        "fulfillment_status": order.get("fulfillment_status"),
                        "customer_email": (order.get("customer") or {}).get("email"),
                        "line_items_count": len(order.get("line_items") or []),
                    }
                )
            link = resp.headers.get("link", "")
            next_url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    m = re.search(r"<([^>]+)>", part)
                    if m:
                        next_url = m.group(1)
            if not next_url:
                break
            url = next_url
            params = None
    if not rows:
        raise IntegrationFetchError("No Shopify orders found for the selected period.")
    return pd.DataFrame(rows)


async def fetch_postgres(config: dict[str, Any]) -> pd.DataFrame:
    conn = str(config.get("connection_string") or "").strip()
    query = str(config.get("query") or "").strip()
    if not conn or not query:
        raise IntegrationNotConfiguredError("Connection string and SQL query are required.")
    if not query.lower().startswith("select"):
        raise IntegrationFetchError("Only SELECT queries are allowed.")
    try:
        import sqlalchemy

        engine = sqlalchemy.create_engine(conn)
        with engine.connect() as connection:
            df = pd.read_sql_query(query, connection)
    except Exception as e:
        raise IntegrationFetchError(f"Postgres query failed: {e}") from e
    if df.empty:
        raise IntegrationFetchError("Query returned no rows.")
    return df


_EXPORT_URL_PROVIDERS = {
    "excel_onedrive",
    "google_drive",
    "quickbooks",
    "hubspot",
    "slack",
    "ga4",
    "meta_ads",
    "salesforce",
    "bigquery",
    "snowflake",
    "power_bi",
    "teams",
}


async def fetch_provider_data(
    provider: str,
    connection_mode: str,
    config: dict[str, Any],
) -> pd.DataFrame:
    if connection_mode == "oauth":
        raise IntegrationNotConfiguredError(
            f"OAuth for {provider} is not enabled yet. Use an export link or API key mode."
        )

    if provider == "google_sheets":
        return await fetch_google_sheets(config)

    if provider == "stripe" and connection_mode == "api_key":
        return await fetch_stripe(config)

    if provider == "shopify" and connection_mode == "api_key":
        return await fetch_shopify(config)

    if provider == "postgres" and connection_mode == "api_key":
        return await fetch_postgres(config)

    if provider in _EXPORT_URL_PROVIDERS or connection_mode == "export_url":
        return await fetch_from_export_url(config)

    if connection_mode == "export_url":
        return await fetch_from_export_url(config)

    raise IntegrationNotConfiguredError(
        f"Connection mode '{connection_mode}' is not available for {provider} yet."
    )
