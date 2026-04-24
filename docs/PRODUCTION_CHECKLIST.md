# Production checklist

Use this before pointing a public domain at Snaptix (or any deployment of this codebase).

## Data and storage

- Set **`UPLOAD_DIR`** to an **absolute path** on a **persistent volume** (e.g. Render Disk) so uploads and `{upload_id}_cleaned.parquet` survive redeploys. The default `./data/uploads` is ephemeral on many PaaS hosts.
- Use **PostgreSQL** (or another production-grade DB) for `DATABASE_URL`; run migrations / schema ensure as you do today on startup.
- Configure **CORS** (`CORS_ORIGINS`) to your real frontend origin(s).

## Auth and secrets

- Set strong **`NEXTAUTH_SECRET`** and production **`NEXTAUTH_URL`** / `NEXTAUTH_URL` equivalent.
- Restrict **`AUTH_TEST_LOGIN_*`** to dev only; disable or remove for production.

## Razorpay

- Register webhook URL: `https://<api-host>/api/billing/razorpay/webhook`.
- Set **`RAZORPAY_WEBHOOK_SECRET`** to match the dashboard secret.
- Confirm **test vs live** keys and plan IDs (`RAZORPAY_PLAN_*`) are consistent.
- After checkout, **`/api/billing/razorpay/verify-checkout`** must succeed for the client flow you ship.

## Email (Resend)

- Set **`RESEND_API_KEY`** and **`RESEND_FROM_EMAIL`** for OTP sign-in.
- Optional retention: schedule a job to send **weekly/monthly digest** email using stored `email_html_snapshot` (see `WorkspaceRecurringSummary`); the UI notes email is not sent automatically until you wire this.

## AI and limits

- Set **`OPENAI_API_KEY`** and review **`OPENAI_MODEL`** cost/latency.
- Ensure **plan limits** in the product copy match `subscription_usage` caps.

## Observability (recommended)

- **Backend:** structured logging, alerts on 5xx; track OpenAI and Razorpay failures.
- **Frontend:** optional **Sentry** (or similar) via `NEXT_PUBLIC_SENTRY_DSN` and SDK init in Next.js.
- **Product analytics:** optional GA4 / Plausible; the app includes a small `trackEvent` helper in `frontend/src/lib/analytics.ts` you can wire to `gtag` or your API.

## Legal

- Replace placeholder **Privacy** and **Terms** pages with counsel-approved documents for your entity and regions (`/privacy`, `/terms`).
