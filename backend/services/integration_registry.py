"""Provider catalog for self-serve integrations (Tier 1–3)."""

from __future__ import annotations

from typing import Any

ConnectionField = dict[str, Any]
ProviderDef = dict[str, Any]

# --- Shared field groups ---

_ONEDRIVE_FIELDS: list[ConnectionField] = [
    {
        "key": "export_url",
        "label": "OneDrive sharing link",
        "type": "url",
        "required": True,
        "placeholder": "https://1drv.ms/x/s!... or https://onedrive.live.com/...",
        "help": (
            "Copy the Share link from OneDrive (right-click file → Share → Copy link). "
            "Do not paste the excel.cloud.microsoft editor URL from your browser address bar."
        ),
    }
]

_EXPORT_URL_FIELDS: list[ConnectionField] = [
    {
        "key": "export_url",
        "label": "CSV / file download link",
        "type": "url",
        "required": True,
        "placeholder": "https://...",
        "help": "Fallback only: a direct link to a CSV or Excel file. Prefer API connection where available.",
    }
]

_SHEETS_FIELDS: list[ConnectionField] = [
    {
        "key": "export_url",
        "label": "CSV export URL",
        "type": "url",
        "required": False,
        "placeholder": "https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0",
        "help": "File → Share → Publish to web → CSV. Or use spreadsheet ID below.",
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

_GA4_SERVICE_ACCOUNT_FIELDS: list[ConnectionField] = [
    {
        "key": "property_id",
        "label": "GA4 Property ID",
        "type": "text",
        "required": True,
        "placeholder": "123456789",
        "help": "Admin → Property settings → Property ID (numeric).",
    },
    {
        "key": "service_account_json",
        "label": "Service account JSON key",
        "type": "textarea",
        "required": True,
        "placeholder": '{"type": "service_account", "project_id": "...", ...}',
        "help": "Google Cloud → IAM → Service accounts → Keys. Grant the service account Viewer on the GA4 property.",
    },
    {
        "key": "days_back",
        "label": "Days of history",
        "type": "number",
        "required": False,
        "default": 90,
    },
]

_META_ADS_FIELDS: list[ConnectionField] = [
    {
        "key": "access_token",
        "label": "System user access token",
        "type": "password",
        "required": True,
        "placeholder": "EAA...",
        "help": "Meta Business Settings → System users → Generate token with ads_read permission.",
    },
    {
        "key": "ad_account_id",
        "label": "Ad account ID",
        "type": "text",
        "required": True,
        "placeholder": "act_1234567890 or 1234567890",
        "help": "Ads Manager → Account settings → Ad account ID.",
    },
    {
        "key": "days_back",
        "label": "Days of history",
        "type": "number",
        "required": False,
        "default": 90,
    },
]

_HUBSPOT_FIELDS: list[ConnectionField] = [
    {
        "key": "access_token",
        "label": "Private app access token",
        "type": "password",
        "required": True,
        "help": "HubSpot → Settings → Integrations → Private apps → Create app with CRM scopes.",
    },
    {
        "key": "object_type",
        "label": "Object to sync",
        "type": "text",
        "required": False,
        "default": "deals",
        "placeholder": "deals",
        "help": "Usually deals, contacts, or companies.",
    },
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

_SALESFORCE_FIELDS: list[ConnectionField] = [
    {
        "key": "instance_url",
        "label": "Instance URL",
        "type": "url",
        "required": True,
        "placeholder": "https://yourcompany.my.salesforce.com",
    },
    {
        "key": "access_token",
        "label": "Access token",
        "type": "password",
        "required": True,
        "help": "From a connected app OAuth flow or session token with API access.",
    },
    {
        "key": "soql",
        "label": "SOQL query",
        "type": "textarea",
        "required": True,
        "placeholder": "SELECT Id, Name, Amount, CloseDate FROM Opportunity LIMIT 2000",
    },
]

_BIGQUERY_FIELDS: list[ConnectionField] = [
    {
        "key": "project_id",
        "label": "GCP project ID",
        "type": "text",
        "required": True,
    },
    {
        "key": "service_account_json",
        "label": "Service account JSON key",
        "type": "textarea",
        "required": True,
    },
    {
        "key": "query",
        "label": "SQL query",
        "type": "textarea",
        "required": True,
        "placeholder": "SELECT * FROM `dataset.table` LIMIT 50000",
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

_SNOWFLAKE_FIELDS: list[ConnectionField] = [
    {
        "key": "account",
        "label": "Account identifier",
        "type": "text",
        "required": True,
        "placeholder": "xy12345.us-east-1",
    },
    {
        "key": "user",
        "label": "Username",
        "type": "text",
        "required": True,
    },
    {
        "key": "password",
        "label": "Password",
        "type": "password",
        "required": True,
    },
    {
        "key": "warehouse",
        "label": "Warehouse",
        "type": "text",
        "required": True,
    },
    {
        "key": "database",
        "label": "Database",
        "type": "text",
        "required": True,
    },
    {
        "key": "schema",
        "label": "Schema",
        "type": "text",
        "required": False,
        "default": "PUBLIC",
    },
    {
        "key": "query",
        "label": "SQL query",
        "type": "textarea",
        "required": True,
        "placeholder": "SELECT * FROM orders LIMIT 50000",
    },
]


PROVIDERS: list[ProviderDef] = [
    {
        "id": "google_sheets",
        "name": "Google Sheets",
        "tier": 1,
        "category": "Spreadsheets",
        "description": "Sync a live Google Sheet into Snaptix.",
        "connection_modes": [
            {
                "id": "oauth",
                "label": "Google account",
                "fields": [],
                "available": False,
                "recommended": True,
                "help": "One-click sign-in with Google (coming soon).",
            },
            {
                "id": "export_url",
                "label": "Published CSV link",
                "fields": _SHEETS_FIELDS,
                "available": True,
                "help": "Works today if the sheet is published to web as CSV.",
            },
        ],
    },
    {
        "id": "excel_onedrive",
        "name": "Excel / OneDrive",
        "tier": 1,
        "category": "Spreadsheets",
        "description": "Connect Excel workbooks from Microsoft 365.",
        "connection_modes": [
            {
                "id": "oauth",
                "label": "Microsoft 365",
                "fields": [],
                "available": True,
                "recommended": True,
                "help": (
                    "Recommended path: sign in with Microsoft 365 and let Snaptix read "
                    "your workbook through Microsoft Graph."
                ),
            },
        ],
    },
    {
        "id": "google_drive",
        "name": "Google Drive",
        "tier": 1,
        "category": "Files",
        "description": "Pull CSV or Excel files from Google Drive.",
        "connection_modes": [
            {
                "id": "oauth",
                "label": "Google Drive",
                "fields": [],
                "available": False,
                "recommended": True,
            },
            {
                "id": "export_url",
                "label": "File download link",
                "fields": _EXPORT_URL_FIELDS,
                "available": True,
            },
        ],
    },
    {
        "id": "quickbooks",
        "name": "QuickBooks",
        "tier": 1,
        "category": "Accounting",
        "description": "Sync P&L, balance sheet, and transactions from QuickBooks Online.",
        "connection_modes": [
            {
                "id": "oauth",
                "label": "QuickBooks Online",
                "fields": [],
                "available": False,
                "recommended": True,
                "help": "OAuth connect to your QuickBooks company (coming soon).",
            },
        ],
    },
    {
        "id": "hubspot",
        "name": "HubSpot",
        "tier": 1,
        "category": "CRM",
        "description": "Sync deals, contacts, or companies via HubSpot API.",
        "connection_modes": [
            {
                "id": "api_key",
                "label": "Private app token",
                "fields": _HUBSPOT_FIELDS,
                "available": True,
                "recommended": True,
                "help": "Uses HubSpot CRM API with a private app access token.",
            },
            {
                "id": "oauth",
                "label": "HubSpot account",
                "fields": [],
                "available": False,
                "help": "One-click OAuth (coming soon).",
            },
        ],
    },
    {
        "id": "slack",
        "name": "Slack",
        "tier": 1,
        "category": "Collaboration",
        "description": "Operational metrics from your Slack workspace.",
        "connection_modes": [
            {
                "id": "oauth",
                "label": "Slack workspace",
                "fields": [],
                "available": False,
                "recommended": True,
                "help": "Install Snaptix to your workspace (coming soon).",
            },
        ],
    },
    {
        "id": "shopify",
        "name": "Shopify",
        "tier": 2,
        "category": "E-commerce",
        "description": "Pull orders and revenue via Shopify Admin API.",
        "connection_modes": [
            {
                "id": "api_key",
                "label": "Admin API token",
                "fields": _SHOPIFY_FIELDS,
                "available": True,
                "recommended": True,
            },
        ],
    },
    {
        "id": "stripe",
        "name": "Stripe",
        "tier": 2,
        "category": "Payments",
        "description": "Sync charges and payment volume via Stripe API.",
        "connection_modes": [
            {
                "id": "api_key",
                "label": "Secret API key",
                "fields": _STRIPE_FIELDS,
                "available": True,
                "recommended": True,
            },
        ],
    },
    {
        "id": "ga4",
        "name": "Google Analytics 4",
        "tier": 2,
        "category": "Marketing",
        "description": "Pull sessions, users, and conversions via the GA4 Data API.",
        "connection_modes": [
            {
                "id": "service_account",
                "label": "Service account",
                "fields": _GA4_SERVICE_ACCOUNT_FIELDS,
                "available": True,
                "recommended": True,
                "help": "Standard GA4 server-to-server setup: property ID + Google Cloud service account.",
            },
            {
                "id": "oauth",
                "label": "Google account",
                "fields": [],
                "available": False,
                "help": "Sign in with Google (coming soon).",
            },
        ],
    },
    {
        "id": "meta_ads",
        "name": "Meta Ads",
        "tier": 2,
        "category": "Marketing",
        "description": "Sync spend, impressions, and clicks via Meta Marketing API.",
        "connection_modes": [
            {
                "id": "api_key",
                "label": "Marketing API token",
                "fields": _META_ADS_FIELDS,
                "available": True,
                "recommended": True,
                "help": "System user token from Meta Business Manager with ads_read.",
            },
            {
                "id": "oauth",
                "label": "Meta Business login",
                "fields": [],
                "available": False,
                "help": "One-click Meta login (coming soon).",
            },
        ],
    },
    {
        "id": "salesforce",
        "name": "Salesforce",
        "tier": 2,
        "category": "CRM",
        "description": "Run SOQL queries against Salesforce objects.",
        "connection_modes": [
            {
                "id": "api_key",
                "label": "Access token + SOQL",
                "fields": _SALESFORCE_FIELDS,
                "available": True,
                "recommended": True,
            },
            {
                "id": "oauth",
                "label": "Salesforce login",
                "fields": [],
                "available": False,
            },
        ],
    },
    {
        "id": "bigquery",
        "name": "BigQuery",
        "tier": 3,
        "category": "Warehouse",
        "description": "Query BigQuery with a service account.",
        "connection_modes": [
            {
                "id": "service_account",
                "label": "Service account + SQL",
                "fields": _BIGQUERY_FIELDS,
                "available": True,
                "recommended": True,
            },
        ],
    },
    {
        "id": "snowflake",
        "name": "Snowflake",
        "tier": 3,
        "category": "Warehouse",
        "description": "Run read-only SQL against Snowflake.",
        "connection_modes": [
            {
                "id": "api_key",
                "label": "Connection + SQL",
                "fields": _SNOWFLAKE_FIELDS,
                "available": False,
                "recommended": True,
                "help": "Native Snowflake connector coming soon.",
            },
        ],
    },
    {
        "id": "postgres",
        "name": "Postgres",
        "tier": 3,
        "category": "Database",
        "description": "Run a read-only SQL query against Postgres.",
        "connection_modes": [
            {
                "id": "api_key",
                "label": "Connection + SQL",
                "fields": _POSTGRES_FIELDS,
                "available": True,
                "recommended": True,
            },
        ],
    },
    {
        "id": "power_bi",
        "name": "Power BI",
        "tier": 3,
        "category": "BI export",
        "description": "Import datasets exported from Power BI.",
        "connection_modes": [
            {
                "id": "oauth",
                "label": "Power BI / Microsoft 365",
                "fields": [],
                "available": False,
                "recommended": True,
                "help": "Direct dataset sync (coming soon).",
            },
            {
                "id": "export_url",
                "label": "Exported file link",
                "fields": _EXPORT_URL_FIELDS,
                "available": True,
                "help": "Fallback: link to a CSV/Excel export from Power BI.",
            },
        ],
    },
    {
        "id": "teams",
        "name": "Microsoft Teams",
        "tier": 3,
        "category": "Collaboration",
        "description": "Operational data from Microsoft Teams.",
        "connection_modes": [
            {
                "id": "oauth",
                "label": "Microsoft 365",
                "fields": [],
                "available": False,
                "recommended": True,
            },
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
