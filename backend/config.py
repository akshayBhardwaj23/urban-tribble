
from pydantic_settings import BaseSettings

# Values that ship in source and must never reach production. validate_runtime_settings
# refuses to start when APP_ENV=production and any of these is still in effect.
INSECURE_DEFAULTS = {
    "OTP_PEPPER": "dev-otp-pepper-change-in-production",
    "API_JWT_SECRET": "dev-api-jwt-secret-change-in-production",
    "INTERNAL_AUTH_SECRET": "dev-internal-auth-secret-change-in-production",
    "INTEGRATION_OAUTH_STATE_SECRET": "dev-integration-oauth-state-change-in-production",
}


class Settings(BaseSettings):
    # development | production. Production enables the startup guard below.
    APP_ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./data/app.db"
    UPLOAD_DIR: str = "./data/uploads"
    # Object storage. When STORAGE_BACKEND=s3, uploads and parquet live in the
    # bucket and UPLOAD_DIR is used only as a scratch directory.
    STORAGE_BACKEND: str = "local"  # local | s3
    S3_BUCKET: str = ""
    S3_PREFIX: str = "snaptix"
    S3_REGION: str = ""
    S3_ENDPOINT_URL: str = ""  # set for Cloudflare R2 / MinIO
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    # Hard caps applied after a file parses, before it is profiled or stored.
    MAX_ROWS_PER_FILE: int = 1_000_000
    MAX_COLUMNS_PER_FILE: int = 512
    # Upload processing: run in a background worker thread and poll for status.
    UPLOAD_ASYNC_PROCESSING: bool = True
    UPLOAD_WORKER_THREADS: int = 2
    # Observability
    SENTRY_DSN: str = ""
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    # OpenAI resilience (applies to every call site)
    OPENAI_TIMEOUT_SECONDS: float = 30.0
    OPENAI_MAX_RETRIES: int = 2
    OPENAI_CACHE_TTL_SECONDS: int = 900
    # Display currency when a workspace has not set one.
    DEFAULT_CURRENCY: str = "INR"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    MAX_FILE_SIZE_MB: int = 20
    # Per authenticated user (Bearer token → user id). DB-backed across workers.
    UPLOAD_RATE_BURST_PER_MINUTE: int = 5
    UPLOAD_RATE_MAX_PER_HOUR: int = 30
    # OTP verify attempts (DB-backed). Eight failures in a 15-minute window locks the mailbox.
    OTP_VERIFY_MAX_FAILURES: int = 8
    OTP_VERIFY_WINDOW_SECONDS: int = 900
    ALLOWED_EXTENSIONS: list[str] = [".xlsx", ".xls", ".csv", ".tsv"]
    # Comma-separated. Browsers reject Access-Control-Allow-Origin: * when credentials are used.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Legacy no-op when per-user subscription_plan is set; avoid relying on this in new code.
    SUBSCRIPTION_PLAN: str = "free"
    # QA only: when set to free|starter|pro, all users resolve to this plan (leave empty in production).
    FORCE_SUBSCRIPTION_PLAN: str = ""
    # Optional: passwordless test sign-in for one mailbox (see /api/auth/test-login). Never commit real values.
    AUTH_TEST_LOGIN_ENABLED: bool = False
    AUTH_TEST_LOGIN_EMAIL: str = ""
    # Required whenever AUTH_TEST_LOGIN_ENABLED is true. Empty secret is always rejected.
    AUTH_TEST_LOGIN_SECRET: str = ""
    AUTH_TEST_LOGIN_NAME: str = "Test user"
    # Resend (https://resend.com) - email OTP
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "Snaptix <onboarding@resend.dev>"
    # HMAC pepper for OTP hashes (set in production)
    OTP_PEPPER: str = "dev-otp-pepper-change-in-production"
    OTP_EXPIRE_MINUTES: int = 10
    OTP_RESEND_SECONDS: int = 60
    # Signed API access tokens (Authorization: Bearer). Override in production.
    API_JWT_SECRET: str = "dev-api-jwt-secret-change-in-production"
    API_JWT_EXPIRE_HOURS: int = 72  # 3 days; shorter window if a token is stolen
    # Server-only secret for NextAuth → FastAPI bootstrap after Google / bypass sign-in.
    # Must match frontend INTERNAL_AUTH_SECRET (never NEXT_PUBLIC_).
    INTERNAL_AUTH_SECRET: str = "dev-internal-auth-secret-change-in-production"
    # Razorpay Subscriptions (https://razorpay.com/docs/subscriptions/) - leave key empty to disable checkout/webhooks.
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    # Plan IDs from Razorpay Dashboard → Subscriptions → Plans
    RAZORPAY_PLAN_STARTER: str = ""
    RAZORPAY_PLAN_PRO: str = ""
    # Billing cycles (e.g. 60 ≈ five years of monthly invoices)
    RAZORPAY_SUBSCRIPTION_TOTAL_COUNT: int = 60
    # Forecasting: prophet (with linear fallback) or linear only. Min points before trying Prophet.
    FORECAST_ENGINE: str = "prophet"
    FORECAST_PROPHET_MIN_POINTS: int = 24
    FORECAST_PROPHET_MAX_HISTORY_ROWS: int = 4000
    # Integrations: default refresh cadence and background scheduler.
    # When false, create/oauth/refresh endpoints return 503 (UI shows Coming soon).
    INTEGRATIONS_ENABLED: bool = False
    INTEGRATION_DEFAULT_REFRESH_HOURS: int = 24
    INTEGRATION_MIN_REFRESH_HOURS: int = 1
    INTEGRATION_MAX_REFRESH_HOURS: int = 168
    INTEGRATION_SCHEDULER_ENABLED: bool = False
    INTEGRATION_SCHEDULER_INTERVAL_SECONDS: int = 60
    # Required in production for POST /api/integrations/run-scheduled
    INTEGRATION_CRON_SECRET: str = ""
    # Encryption at rest for DataSourceIntegration.config_json (third-party secrets).
    # Comma-separated Fernet keys: the first encrypts, all are tried on decrypt so a
    # rotation is `new,old` -> backfill -> `new`. Empty leaves credentials in cleartext,
    # which the production guard below refuses.
    INTEGRATION_CREDENTIALS_KEY: str = ""
    # When false, lifespan skips alembic (use a release/init command instead).
    RUN_MIGRATIONS_ON_STARTUP: bool = True
    # Heuristic orphan upload→workspace backfill. Unsafe on multi-tenant DBs; off in prod.
    BACKFILL_ORPHAN_UPLOAD_WORKSPACES: bool = True
    # Microsoft 365 OAuth for Excel / OneDrive
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    MICROSOFT_TENANT_ID: str = "common"
    MICROSOFT_REDIRECT_URI: str = "http://localhost:8000/api/integrations/oauth/callback/microsoft"
    INTEGRATION_OAUTH_STATE_SECRET: str = "dev-integration-oauth-state-change-in-production"
    FRONTEND_APP_URL: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() in ("production", "prod")


settings = Settings()


def collect_runtime_setting_errors(s: "Settings") -> list[str]:
    """Configuration that is safe in development but unacceptable in production."""
    errors: list[str] = []
    if not s.is_production:
        return errors

    for field, insecure in INSECURE_DEFAULTS.items():
        value = (getattr(s, field, "") or "").strip()
        if not value:
            errors.append(f"{field} is empty. Set a unique secret of at least 24 characters.")
        elif value == insecure:
            errors.append(f"{field} is still the value committed in source. Set a unique secret.")
        elif len(value) < 24:
            errors.append(f"{field} is too short ({len(value)} chars). Use at least 24.")

    if s.AUTH_TEST_LOGIN_ENABLED:
        if not (s.AUTH_TEST_LOGIN_SECRET or "").strip():
            errors.append(
                "AUTH_TEST_LOGIN_ENABLED is on with an empty AUTH_TEST_LOGIN_SECRET, which lets "
                "anyone sign in as the test mailbox. Set a secret or disable test login."
            )
        if not (s.AUTH_TEST_LOGIN_EMAIL or "").strip():
            errors.append("AUTH_TEST_LOGIN_ENABLED is on with no AUTH_TEST_LOGIN_EMAIL allowlist.")

    if (s.FORCE_SUBSCRIPTION_PLAN or "").strip():
        errors.append("FORCE_SUBSCRIPTION_PLAN overrides every user's plan. Clear it in production.")

    if s.DATABASE_URL.startswith("sqlite"):
        errors.append("DATABASE_URL points at SQLite. Use Postgres in production.")

    if s.STORAGE_BACKEND.strip().lower() == "local":
        errors.append(
            "STORAGE_BACKEND=local keeps uploads on container disk, so a redeploy loses "
            "customer files. Set STORAGE_BACKEND=s3 with S3_BUCKET."
        )
    elif not s.S3_BUCKET.strip():
        errors.append("STORAGE_BACKEND=s3 requires S3_BUCKET.")

    if any("localhost" in o or "127.0.0.1" in o for o in s.CORS_ORIGINS.split(",")):
        errors.append("CORS_ORIGINS still allows localhost.")

    if not (s.INTEGRATION_CRON_SECRET or "").strip():
        errors.append(
            "INTEGRATION_CRON_SECRET is empty, so POST /api/integrations/run-scheduled is open "
            "to anyone. Set a secret or disable external cron."
        )

    if not (s.INTEGRATION_CREDENTIALS_KEY or "").strip():
        errors.append(
            "INTEGRATION_CREDENTIALS_KEY is empty, so third-party integration credentials "
            "(Stripe keys, Shopify tokens, Microsoft refresh tokens) are stored in the "
            "database as cleartext. Generate one with: python -c \"from cryptography.fernet "
            'import Fernet; print(Fernet.generate_key().decode())"'
        )
    else:
        from services.integration_credentials import validate_configured_keys

        key_error = validate_configured_keys(s.INTEGRATION_CREDENTIALS_KEY)
        if key_error:
            errors.append(key_error)

    if not (s.RESEND_API_KEY or "").strip():
        errors.append(
            "RESEND_API_KEY is empty. Email OTP sign-in will fail for every user in production."
        )

    return errors


def validate_runtime_settings(s: "Settings" = settings) -> None:
    errors = collect_runtime_setting_errors(s)
    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError(f"Refusing to start with APP_ENV=production:\n{joined}")
