"""Provider catalog for self-serve integrations (Tier 1–3)."""

from __future__ import annotations

from typing import Any

ConnectionField = dict[str, Any]
ConnectionMode = dict[str, Any]
ProviderDef = dict[str, Any]

_EXPORT_URL_FIELDS: list[ConnectionField] = [
    {
        "key": "export_url",
        "label": "Export / share link (CSV)",
        "type": "url",
        "required": True,
        "placeholder": "https://docs.google.com/spreadsheets/d/.../export?format=csv",
        "help": "Use a direct CSV export URL. For Google Sheets: File → Share → Publish to web → CSV.",
    }
]

_SHEETS_FIELDS: list[ConnectionField] = [
    {
        "key": "export_url",
        "label": "CSV export URL",
        "type": "url",
        "required": False,
        "placeholder": "https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0",
    },
    {
        "key": "spreadsheet_id",
        "label": "Spreadsheet ID",
        "type": "text",
        "required": False,
        "placeholder": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    },
    {
        "key": "gid",
        "label": "Sheet GID",
        "type": "text",
        "required": False,
        "placeholder": "0",
        "help": "Tab id from the sheet URL (#gid=...). Defaults to 0.",
    },
]

_API_KEY_FIELD: list[ConnectionField] = [
    {
        "key": "api_key",
        "label": "API key",
        "type": "password",
        "required": True,
    }
]

_STRIPE_FIELDS: list[ConnectionField] = [
    {
        "key": "secret_key",
        "label": "Secret key",
        "type": "password",
        "required": True,
        "placeholder": "sk_live_... or sk_test_...",
    },
    {
        "key": "days_back",
        "label": "Days of history",
        "type": "number",
        "required": False,
        "default": 90,
    },
]

_SHOPIFY_FIELDS: list[ConnectionField] = [
    {
        "key": "shop_domain",
        "label": "Shop domain",
        "type": "text",
        "required": True,
        "placeholder": "your-store.myshopify.com",
    },
    {
        "key": "access_token",
        "label": "Admin API access token",
        "type": "password",
        "required": True,
    },
    {
        "key": "days_back",
        "label": "Days of orders",
        "type": "number",
        "required": False,
        "default": 90,
    },
]

_POSTGRES_FIELDS: list[ConnectionField] = [
    {
        "key": "connection_string",
        "label": "Connection string",
        "type": "password",
        "required": True,
        "placeholder": "postgresql://user:pass@host:5432/db",
    },
    {
        "key": "query",
        "label": "SQL query",
        "type": "textarea",
        "required": True,
        "placeholder": "SELECT * FROM sales LIMIT 50000",
    },
]

PROVIDERS: list[ProviderDef] = [
    {
        "id": "google_sheets",
        "name": "Google Sheets",
        "tier": 1,
        "category": "Spreadsheets",
        "description": "Sync a live sheet via CSV export or spreadsheet ID.",
        "connection_modes": [
            {"id": "export_url", "label": "CSV export link", "fields": _SHEETS_FIELDS, "available": True},
            {"id": "oauth", "label": "Google account", "fields": [], "available": False},
        ],
    },
    {
        "id": "excel_onedrive",
        "name": "Excel / OneDrive",
        "tier": 1,
        "category": "Spreadsheets",
        "description": "Import Excel exports hosted on OneDrive or SharePoint.",
        "connection_modes": [
            {"id": "export_url", "label": "Download / export link", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "oauth", "label": "Microsoft 365", "fields": [], "available": False},
        ],
    },
    {
        "id": "google_drive",
        "name": "Google Drive",
        "tier": 1,
        "category": "Files",
        "description": "Pull CSV or Excel files from a public Drive export link.",
        "connection_modes": [
            {"id": "export_url", "label": "File export link", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "oauth", "label": "Google Drive", "fields": [], "available": False},
        ],
    },
    {
        "id": "quickbooks",
        "name": "QuickBooks",
        "tier": 1,
        "category": "Accounting",
        "description": "Sync profit & loss or transaction reports.",
        "connection_modes": [
            {"id": "export_url", "label": "Report export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "oauth", "label": "QuickBooks Online", "fields": [], "available": False},
        ],
    },
    {
        "id": "hubspot",
        "name": "HubSpot",
        "tier": 1,
        "category": "CRM",
        "description": "Sync deals and pipeline exports.",
        "connection_modes": [
            {"id": "export_url", "label": "Report export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "api_key", "label": "Private app token", "fields": _API_KEY_FIELD, "available": False},
        ],
    },
    {
        "id": "slack",
        "name": "Slack",
        "tier": 1,
        "category": "Collaboration",
        "description": "Export channel metrics for operational dashboards.",
        "connection_modes": [
            {"id": "export_url", "label": "CSV export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "oauth", "label": "Slack workspace", "fields": [], "available": False},
        ],
    },
    {
        "id": "shopify",
        "name": "Shopify",
        "tier": 2,
        "category": "E-commerce",
        "description": "Pull recent orders via Admin API.",
        "connection_modes": [
            {"id": "api_key", "label": "Admin API token", "fields": _SHOPIFY_FIELDS, "available": True},
            {"id": "export_url", "label": "Orders export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
        ],
    },
    {
        "id": "stripe",
        "name": "Stripe",
        "tier": 2,
        "category": "Payments",
        "description": "Sync charges and payment volume.",
        "connection_modes": [
            {"id": "api_key", "label": "Secret key", "fields": _STRIPE_FIELDS, "available": True},
        ],
    },
    {
        "id": "ga4",
        "name": "Google Analytics 4",
        "tier": 2,
        "category": "Marketing",
        "description": "Import GA4 exploration or scheduled report exports.",
        "connection_modes": [
            {"id": "export_url", "label": "Report CSV URL", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "oauth", "label": "Google Analytics", "fields": [], "available": False},
        ],
    },
    {
        "id": "meta_ads",
        "name": "Meta Ads",
        "tier": 2,
        "category": "Marketing",
        "description": "Import ad performance exports.",
        "connection_modes": [
            {"id": "export_url", "label": "Report export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "oauth", "label": "Meta Business", "fields": [], "available": False},
        ],
    },
    {
        "id": "salesforce",
        "name": "Salesforce",
        "tier": 2,
        "category": "CRM",
        "description": "Sync report exports or SOQL query results.",
        "connection_modes": [
            {"id": "export_url", "label": "Report export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "oauth", "label": "Salesforce", "fields": [], "available": False},
        ],
    },
    {
        "id": "bigquery",
        "name": "BigQuery",
        "tier": 3,
        "category": "Warehouse",
        "description": "Run a saved SQL query against BigQuery (service account).",
        "connection_modes": [
            {"id": "export_url", "label": "Scheduled export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "api_key", "label": "Service account JSON", "fields": [], "available": False},
        ],
    },
    {
        "id": "snowflake",
        "name": "Snowflake",
        "tier": 3,
        "category": "Warehouse",
        "description": "Query Snowflake and sync results.",
        "connection_modes": [
            {"id": "export_url", "label": "Stage / export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "api_key", "label": "Connection", "fields": [], "available": False},
        ],
    },
    {
        "id": "postgres",
        "name": "Postgres",
        "tier": 3,
        "category": "Database",
        "description": "Run a read-only SQL query against Postgres.",
        "connection_modes": [
            {"id": "api_key", "label": "Connection + query", "fields": _POSTGRES_FIELDS, "available": True},
        ],
    },
    {
        "id": "power_bi",
        "name": "Power BI",
        "tier": 3,
        "category": "BI export",
        "description": "Import datasets exported from Power BI or sync to Snaptix.",
        "connection_modes": [
            {"id": "export_url", "label": "Dataset export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
        ],
    },
    {
        "id": "teams",
        "name": "Microsoft Teams",
        "tier": 3,
        "category": "Collaboration",
        "description": "Operational exports and alerts (CSV).",
        "connection_modes": [
            {"id": "export_url", "label": "Export URL", "fields": _EXPORT_URL_FIELDS, "available": True},
            {"id": "oauth", "label": "Microsoft Teams", "fields": [], "available": False},
        ],
    },
]

_PROVIDER_BY_ID = {p["id"]: p for p in PROVIDERS}


def get_provider(provider_id: str) -> ProviderDef | None:
    return _PROVIDER_BY_ID.get(provider_id)


def list_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "tier": p["tier"],
            "category": p["category"],
            "description": p["description"],
            "connection_modes": p["connection_modes"],
        }
        for p in PROVIDERS
    ]
