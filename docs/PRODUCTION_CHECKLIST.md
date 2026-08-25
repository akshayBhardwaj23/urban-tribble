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

## Turning integrations on

> **`FRONTEND_APP_URL` must be set on the backend before any OAuth connect will work.**
> It is where the browser is sent after signing in with Google or Microsoft. Its default is
> `http://localhost:3000`, so leaving it unset in production completes the connect server-side and
> then strands the user on a dead localhost page — with nothing in the logs looking wrong. Production
> boot now refuses on a localhost, empty, or non-https value.


Four switches, all currently off or restricted. Nothing is user-visible until the first two are set.

1. **`INTEGRATIONS_ENABLED=true`** (backend). While false, every connect/refresh endpoint returns
   503 and the UI shows "not switched on yet". This is the master switch.
2. **Provider credentials** for whichever wave you are shipping — see the Google and Microsoft
   sections below. A provider with no credentials returns a clear 503 at sign-in time rather than
   failing mysteriously.
3. **`INTEGRATION_ENABLED_PROVIDERS`** (backend, defaults to `excel_onedrive,google_sheets`).
   Controls which providers can actually be connected, so a wave ships without dragging every
   built-but-unreviewed connector live with it. Widen it to add a wave; leave it empty to allow every
   provider whose connector is available. Enforced server-side, so a hand-rolled request is refused
   the same way the UI button is hidden.
4. **`INTEGRATION_AUTO_SYNC_ENABLED`** (backend, default false) — leave this off unless you have done
   the cost arithmetic below. Sources still refresh on demand while it is off.

Verify after enabling, in this order: the Integrations page lists providers with working Connect
buttons → sign-in redirects to the provider → the file picker lists real files → connecting produces a
dashboard → "Refresh now" on the dataset page works → an unchanged source reports "already up to date"
rather than re-processing.

## Integration refresh mode (cost control)

- **`INTEGRATION_AUTO_SYNC_ENABLED` defaults to `false`: sources refresh only when a user asks.**
  Nothing runs in the background, so no connected source can spend provider calls, model calls or
  storage without someone having clicked something. This is a deliberate cost decision, not an
  oversight — an unattended refresh costs per source per cycle, which is exactly the shape that
  erodes margin on a fixed monthly price.
- While it is off, three independent things hold: new sources are stored with **no due date**, the
  due-query **returns nothing** even for rows written earlier, and the cron endpoint **is a no-op**
  that reports why. Turning it on has to be deliberate.
- **Before enabling it**, work out the per-cycle cost: (sources per workspace) × (24 ÷ refresh hours)
  × (cost per sync). The unchanged-source check keeps an untouched sheet to a single metadata call,
  but a genuinely changing sheet pays full cleaning, profiling and — if `auto_analyze` is on — a
  briefing each time. Analyses are plan-capped; syncs themselves are not.
- To enable later: set `INTEGRATION_AUTO_SYNC_ENABLED=true`, then drive it with an **external cron**
  calling `POST /api/integrations/run-scheduled` with the `X-Integration-Cron-Secret` header. Prefer
  that over `INTEGRATION_SCHEDULER_ENABLED`, which runs a loop inside *every* API worker.

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
