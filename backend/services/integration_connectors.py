"""Fetch tabular data from connected providers."""

from __future__ import annotations

import io
import json
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


def _google_bearer_token(service_account_json: str | dict) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    if isinstance(service_account_json, str):
        sa_info = json.loads(service_account_json)
    else:
        sa_info = service_account_json
    creds = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    creds.refresh(Request())
    if not creds.token:
        raise IntegrationFetchError("Failed to obtain Google access token.")
    return creds.token


async def fetch_ga4(config: dict[str, Any]) -> pd.DataFrame:
    property_id = str(config.get("property_id") or "").strip()
    sa_json = config.get("service_account_json")
    if not property_id or not sa_json:
        raise IntegrationNotConfiguredError(
            "GA4 property ID and service account JSON are required."
        )
    days_back = int(config.get("days_back") or 90)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days_back)
    token = _google_bearer_token(sa_json)
    body = {
        "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
        "dimensions": [{"name": "date"}],
        "metrics": [
            {"name": "sessions"},
            {"name": "totalUsers"},
            {"name": "newUsers"},
            {"name": "screenPageViews"},
            {"name": "conversions"},
            {"name": "totalRevenue"},
        ],
    }
    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        if resp.status_code in (401, 403):
            raise IntegrationFetchError(
                "GA4 API access denied. Check service account has Viewer on the property."
            )
        if resp.status_code == 404:
            raise IntegrationFetchError("GA4 property not found. Check the property ID.")
        resp.raise_for_status()
        data = resp.json()

    rows: list[dict[str, Any]] = []
    for row in data.get("rows", []):
        dims = [d.get("value") for d in row.get("dimensionValues", [])]
        metrics = [m.get("value") for m in row.get("metricValues", [])]
        date_raw = dims[0] if dims else ""
        if len(date_raw) == 8 and date_raw.isdigit():
            date_fmt = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
        else:
            date_fmt = date_raw
        rows.append(
            {
                "date": date_fmt,
                "sessions": float(metrics[0] or 0) if len(metrics) > 0 else 0,
                "total_users": float(metrics[1] or 0) if len(metrics) > 1 else 0,
                "new_users": float(metrics[2] or 0) if len(metrics) > 2 else 0,
                "page_views": float(metrics[3] or 0) if len(metrics) > 3 else 0,
                "conversions": float(metrics[4] or 0) if len(metrics) > 4 else 0,
                "revenue": float(metrics[5] or 0) if len(metrics) > 5 else 0,
            }
        )
    if not rows:
        raise IntegrationFetchError("GA4 returned no data for the selected period.")
    return pd.DataFrame(rows)


async def fetch_meta_ads(config: dict[str, Any]) -> pd.DataFrame:
    token = str(config.get("access_token") or "").strip()
    account = str(config.get("ad_account_id") or "").strip().replace("act_", "")
    if not token or not account:
        raise IntegrationNotConfiguredError("Meta access token and ad account ID are required.")
    days_back = int(config.get("days_back") or 90)
    since = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    until = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://graph.facebook.com/v21.0/act_{account}/insights"
    params: dict[str, Any] = {
        "access_token": token,
        "fields": "date_start,date_stop,impressions,clicks,spend,reach,cpc,cpm,ctr",
        "time_range": json.dumps({"since": since, "until": until}),
        "time_increment": 1,
        "limit": 500,
    }
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=90.0) as client:
        while url:
            resp = await client.get(url, params=params)
            if resp.status_code in (401, 403):
                raise IntegrationFetchError(
                    "Meta API access denied. Check token permissions (ads_read) and ad account ID."
                )
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("data", []):
                rows.append(
                    {
                        "date": item.get("date_start"),
                        "impressions": float(item.get("impressions") or 0),
                        "clicks": float(item.get("clicks") or 0),
                        "spend": float(item.get("spend") or 0),
                        "reach": float(item.get("reach") or 0),
                        "cpc": float(item.get("cpc") or 0),
                        "cpm": float(item.get("cpm") or 0),
                        "ctr": float(item.get("ctr") or 0),
                    }
                )
            next_url = data.get("paging", {}).get("next")
            url = next_url
            params = None
    if not rows:
        raise IntegrationFetchError("Meta Ads returned no insights for the selected period.")
    return pd.DataFrame(rows)


async def fetch_hubspot(config: dict[str, Any]) -> pd.DataFrame:
    token = str(config.get("access_token") or "").strip()
    object_type = str(config.get("object_type") or "deals").strip().lower()
    if not token:
        raise IntegrationNotConfiguredError("HubSpot private app access token is required.")
    property_sets = {
        "deals": "dealname,amount,dealstage,closedate,createdate,pipeline",
        "contacts": "firstname,lastname,email,createdate,lastmodifieddate",
        "companies": "name,domain,createdate,annualrevenue,numberofemployees",
    }
    props = property_sets.get(object_type, "dealname,amount,dealstage,closedate,createdate")
    url = f"https://api.hubapi.com/crm/v3/objects/{object_type}"
    headers = {"Authorization": f"Bearer {token}"}
    params: dict[str, Any] = {"limit": 100, "properties": props}
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        while url:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code in (401, 403):
                raise IntegrationFetchError("Invalid HubSpot token or missing CRM scopes.")
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("results", []):
                flat = {"id": item.get("id"), "object_type": object_type}
                flat.update(item.get("properties") or {})
                rows.append(flat)
            next_link = data.get("paging", {}).get("next", {}).get("after")
            if not next_link:
                break
            params = {"limit": 100, "properties": props, "after": next_link}
    if not rows:
        raise IntegrationFetchError(f"HubSpot returned no {object_type}.")
    return pd.DataFrame(rows)


async def fetch_salesforce(config: dict[str, Any]) -> pd.DataFrame:
    instance = str(config.get("instance_url") or "").strip().rstrip("/")
    token = str(config.get("access_token") or "").strip()
    soql = str(config.get("soql") or "").strip()
    if not instance or not token or not soql:
        raise IntegrationNotConfiguredError(
            "Salesforce instance URL, access token, and SOQL are required."
        )
    if not soql.lower().startswith("select"):
        raise IntegrationFetchError("Only SELECT SOQL queries are allowed.")
    url = f"{instance}/services/data/v59.0/query"
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.get(
            url,
            params={"q": soql},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code in (401, 403):
            raise IntegrationFetchError("Salesforce access denied. Check token and instance URL.")
        resp.raise_for_status()
        data = resp.json()
    records = data.get("records", [])
    if not records:
        raise IntegrationFetchError("Salesforce query returned no rows.")
    cleaned = []
    for rec in records:
        row = {k: v for k, v in rec.items() if k != "attributes"}
        cleaned.append(row)
    return pd.DataFrame(cleaned)


def _bigquery_bearer_token(service_account_json: str | dict) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    sa_info = json.loads(service_account_json) if isinstance(service_account_json, str) else service_account_json
    creds = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
    )
    creds.refresh(Request())
    if not creds.token:
        raise IntegrationFetchError("Failed to obtain BigQuery access token.")
    return creds.token


async def fetch_bigquery(config: dict[str, Any]) -> pd.DataFrame:
    project_id = str(config.get("project_id") or "").strip()
    sa_json = config.get("service_account_json")
    query = str(config.get("query") or "").strip()
    if not project_id or not sa_json or not query:
        raise IntegrationNotConfiguredError(
            "BigQuery project ID, service account JSON, and SQL query are required."
        )
    if not query.lower().startswith("select"):
        raise IntegrationFetchError("Only SELECT queries are allowed.")
    token = _bigquery_bearer_token(sa_json)
    url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}/queries"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"query": query, "useLegacySql": False, "maxResults": 50000},
        )
        if resp.status_code in (401, 403):
            raise IntegrationFetchError("BigQuery access denied. Check service account IAM roles.")
        resp.raise_for_status()
        data = resp.json()
    if data.get("errors"):
        raise IntegrationFetchError(data["errors"][0].get("message", "BigQuery query failed"))
    schema = data.get("schema", {}).get("fields", [])
    columns = [f["name"] for f in schema]
    rows_raw = data.get("rows", [])
    if not rows_raw:
        raise IntegrationFetchError("BigQuery query returned no rows.")
    rows = []
    for r in rows_raw:
        vals = [c.get("v") for c in r.get("f", [])]
        rows.append(dict(zip(columns, vals)))
    df = pd.DataFrame(rows)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="ignore")
    return df


_EXPORT_URL_PROVIDERS = {
    "excel_onedrive",
    "google_drive",
    "power_bi",
}


async def fetch_provider_data(
    provider: str,
    connection_mode: str,
    config: dict[str, Any],
) -> pd.DataFrame:
    if connection_mode == "oauth":
        raise IntegrationNotConfiguredError(
            f"OAuth for {provider} is not enabled yet. Use API credentials where available."
        )

    if provider == "google_sheets":
        return await fetch_google_sheets(config)

    if provider == "stripe":
        return await fetch_stripe(config)

    if provider == "shopify":
        return await fetch_shopify(config)

    if provider == "postgres":
        return await fetch_postgres(config)

    if provider == "ga4" and connection_mode == "service_account":
        return await fetch_ga4(config)

    if provider == "meta_ads" and connection_mode == "api_key":
        return await fetch_meta_ads(config)

    if provider == "hubspot" and connection_mode == "api_key":
        return await fetch_hubspot(config)

    if provider == "salesforce" and connection_mode == "api_key":
        return await fetch_salesforce(config)

    if provider == "bigquery" and connection_mode == "service_account":
        return await fetch_bigquery(config)

    if provider in _EXPORT_URL_PROVIDERS or connection_mode == "export_url":
        return await fetch_from_export_url(config)

    raise IntegrationNotConfiguredError(
        f"Connection mode '{connection_mode}' is not available for {provider} yet."
    )
