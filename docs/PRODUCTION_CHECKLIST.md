# Production checklist

Use this before pointing a public domain at Snaptix (or any deployment of this codebase).

**Manual QA:** See **[QA_RELEASE_CHECKLIST.md](QA_RELEASE_CHECKLIST.md)** for step-by-step test cases before release.

## Data and storage

- Set **`UPLOAD_DIR`** to an **absolute path** on a **persistent volume** (e.g. Render Disk) so uploads and `{upload_id}_cleaned.parquet` survive redeploys. The default `./data/uploads` is ephemeral on many PaaS hosts.
- Use **PostgreSQL** (or another production-grade DB) for `DATABASE_URL`; run migrations / schema ensure as you do today on startup.
- Configure **CORS** (`CORS_ORIGINS`) to your real frontend origin(s).

## Auth and secrets

- Set strong **`NEXTAUTH_SECRET`** and production **`NEXTAUTH_URL`**.
- Set strong unique **`API_JWT_SECRET`** (signs FastAPI Bearer tokens) and matching **`INTERNAL_AUTH_SECRET`** on backend + frontend (server-only; used by NextAuth to bootstrap Google sessions). Never expose `INTERNAL_AUTH_SECRET` as `NEXT_PUBLIC_*`.
- Override default **`OTP_PEPPER`** in production.
- Restrict **`AUTH_TEST_LOGIN_*`** to dev only; disable or remove for production.
- Set **`INTEGRATION_CREDENTIALS_KEY`** before any integration is connected. It encrypts
  `DataSourceIntegration.config_json`, which holds live third-party secrets (Stripe keys,
  Shopify tokens, Microsoft refresh tokens). Without it those sit in the database as cleartext
  and the app refuses to boot with `APP_ENV=production`. Generate one with:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  **Back this key up separately from the database.** Losing it means every connected integration
  must be removed and reconnected — the credentials are not recoverable.
- **Rotation** is two deploys: set `INTEGRATION_CREDENTIALS_KEY=<new>,<old>`, run
  `python -m scripts.encrypt_integration_credentials`, then drop `<old>` and redeploy.
  The same script backfills rows written before encryption existed.
- If any credential was ever written to a production database in cleartext, treat it as exposed:
  re-issue it at the provider. Rewriting the row does not scrub it from old pages, WAL, or backups.

## Google Sheets integration (OAuth)

- Create an **OAuth 2.0 Client ID (Web application)** in Google Cloud Console, in the same project
  where you enable the **Google Drive API**.
- Authorised redirect URI must be the **API** host, not the web app:
  `https://<your-api-host>/api/integrations/oauth/callback/google`
- Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` in the **backend** env.
  These are *separate* from the frontend's NextAuth Google sign-in credentials: different scopes,
  different redirect, different consent.
- **⚠️ Verification is required before public launch.** The connector uses
  `https://www.googleapis.com/auth/drive.readonly`, which Google classifies as a **restricted**
  scope. An unverified app is capped at 100 users and shows an "unverified app" warning screen.
  Verification requires a demo video, a privacy policy URL, and homepage domain verification; past
  a threshold Google also requires an annual third-party **CASA security assessment**, which is a
  real recurring cost. Budget weeks, not days, for this.
  - The alternative is `drive.file` (non-restricted, no assessment), which only grants access to
    files the user hand-picks through Google's **client-side Picker**. That would remove
    server-side file listing and change the connect UX, so it is a deliberate product decision,
    not a config switch. Revisit before launch if verification proves too slow or costly.
- Sanity-check the whole round trip on staging before launch: connect → pick sheets → first sync
  produces a dashboard → wait for a scheduled refresh → confirm the refresh token still works
  (this is the step that catches a missing `access_type=offline`).

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
- **Product analytics:** set `NEXT_PUBLIC_GA_MEASUREMENT_ID` (e.g. `G-67RYHHW462`) on the frontend; `GoogleAnalytics` in the root layout loads gtag and existing `trackEvent` calls in `frontend/src/lib/analytics.ts` send custom events.

## Contact (marketing site)

- Public inbox: **`hello@snaptix.ai`** (wired in `frontend/src/lib/brand.ts` as `CONTACT_EMAIL`).

## Demo video

- Upload to **YouTube (unlisted)** or Vimeo, then set on the frontend:
  - `NEXT_PUBLIC_DEMO_VIDEO_URL=https://www.youtube.com/watch?v=YOUR_ID`
- Embeds on **`/help`** (public) and **`/help`** inside the signed-in app (sidebar **Help**).
- Redeploy frontend after changing the env var.

## Legal

- Replace placeholder **Privacy** and **Terms** pages with counsel-approved documents for your entity and regions (`/privacy`, `/terms`).
