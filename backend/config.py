from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/app.db"
    UPLOAD_DIR: str = "./data/uploads"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    MAX_FILE_SIZE_MB: int = 20
    # Per authenticated user (X-User-Email). In-memory; use proxy limits for multi-worker.
    UPLOAD_RATE_BURST_PER_MINUTE: int = 5
    UPLOAD_RATE_MAX_PER_HOUR: int = 30
    ALLOWED_EXTENSIONS: List[str] = [".xlsx", ".xls", ".csv", ".tsv"]
    # Comma-separated. Browsers reject Access-Control-Allow-Origin: * when credentials are used.
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Legacy no-op when per-user subscription_plan is set; avoid relying on this in new code.
    SUBSCRIPTION_PLAN: str = "free"
    # QA only: when set to free|starter|pro, all users resolve to this plan (leave empty in production).
    FORCE_SUBSCRIPTION_PLAN: str = ""
    # Optional: passwordless test sign-in for one mailbox (see /api/auth/test-login). Never commit real values.
    AUTH_TEST_LOGIN_ENABLED: bool = False
    AUTH_TEST_LOGIN_EMAIL: str = ""
    # If set, /api/auth/test-login requires this secret; the web login flow does not send it—leave empty for email-only test sign-in.
    AUTH_TEST_LOGIN_SECRET: str = ""
    AUTH_TEST_LOGIN_NAME: str = "Test user"
    # Resend (https://resend.com) — email OTP
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "Clarus <onboarding@resend.dev>"
    # HMAC pepper for OTP hashes (set in production)
    OTP_PEPPER: str = "dev-otp-pepper-change-in-production"
    OTP_EXPIRE_MINUTES: int = 10
    OTP_RESEND_SECONDS: int = 60
    # Razorpay Subscriptions (https://razorpay.com/docs/subscriptions/) — leave key empty to disable checkout/webhooks.
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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
