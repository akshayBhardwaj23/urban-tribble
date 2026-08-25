# Snaptix

AI-powered business analytics SaaS. Upload Excel/CSV files — or connect a live **Google Sheet** or **Microsoft 365 workbook** — and get automated dashboards, AI-generated insights, forecasting, and natural language data querying.

## Tech Stack

- **Frontend**: Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, Recharts
- **Backend**: FastAPI, Python 3.11+, Pandas, [Prophet](https://facebook.github.io/prophet/) (forecasting; CmdStan via `cmdstanpy` on first fit), OpenAI GPT-4o, SQLAlchemy
- **Database**: SQLite (dev) / PostgreSQL (prod), schema managed by Alembic
- **Integrations**: OAuth against Google Drive/Sheets and Microsoft Graph; stored credentials encrypted at rest

## Quick Start

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
touch .env  # add OPENAI_API_KEY, API_JWT_SECRET, INTERNAL_AUTH_SECRET (see below)
uvicorn main:app --reload
```

Backend runs at http://localhost:8000. Health check: http://localhost:8000/health

**Forecasting:** Dataset and workspace outlooks use **Prophet** when enough history is present (see `FORECAST_ENGINE`, `FORECAST_PROPHET_MIN_POINTS`, `FORECAST_PROPHET_MAX_HISTORY_ROWS` in `backend/config.py`). Shorter series, non-positive values, or failures fall back to **linear regression**. Installing `prophet` may download CmdStan the first time a Prophet model runs; allow network during `pip install` and on that first fit in CI or containers.

### Frontend

```bash
cd frontend
npm install
touch .env.local  # add Google OAuth credentials + NEXT_PUBLIC_API_URL (see below)
npm run dev
```

Frontend runs at http://localhost:3000.

### Google OAuth Setup (user sign-in)

This is the **frontend NextAuth** credential used to sign people in. Connecting a Google Sheet is a *separate* Google client on the backend — see [Live data integrations](#live-data-integrations-optional) below.

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new OAuth 2.0 Client ID (Web application)
3. Add `http://localhost:3000` to Authorized JavaScript origins
4. Add `http://localhost:3000/api/auth/callback/google` to Authorized redirect URIs
5. For production at **https://snaptix.ai**, also add `https://snaptix.ai` and `https://snaptix.ai/api/auth/callback/google`, and set `NEXTAUTH_URL=https://snaptix.ai` in `frontend/.env.local`
6. Copy Client ID and Client Secret to `frontend/.env.local`
7. Generate a NEXTAUTH_SECRET: `openssl rand -base64 32`
8. Set the same **`INTERNAL_AUTH_SECRET`** in `frontend/.env.local` and `backend/.env` (server-only). Also set a strong **`API_JWT_SECRET`** in `backend/.env`.

### Live data integrations (optional)

Instead of uploading a file, a user can **connect a source** that Snaptix re-reads: a **Google Sheet** or an **Excel workbook in Microsoft 365**. Each connected sheet becomes its own dataset with its own dashboard, and keeps that dataset's id, chat history and chart layout across refreshes. Everything is **off by default**; nothing is user-visible until you switch it on.

In `backend/.env`:

```bash
INTEGRATIONS_ENABLED=true                     # master switch; endpoints 503 while false
INTEGRATION_ENABLED_PROVIDERS=excel_onedrive,google_sheets
INTEGRATION_CREDENTIALS_KEY=<fernet key>      # encrypts stored provider tokens
INTEGRATION_OAUTH_STATE_SECRET=<random>
FRONTEND_APP_URL=http://localhost:3000        # where OAuth sends the browser back

# Google Sheets connector — a DIFFERENT client from the sign-in one above
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/integrations/oauth/callback/google

# Excel / OneDrive connector (optional)
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/integrations/oauth/callback/microsoft
```

Generate the credentials key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Back that key up separately from the database** — losing it means every connected source must be removed and reconnected.

Two things trip people up:

- The Sheets **redirect URI points at the API** (port 8000), not the web app, and needs the **Google Drive API** enabled in the same Cloud project. Add it to a *new* OAuth client rather than reusing the sign-in one; the scopes and consent are different.
- **Refreshes are manual by default.** `INTEGRATION_AUTO_SYNC_ENABLED=false` means a source only re-reads when someone clicks. This is a deliberate cost decision — read the cost arithmetic in the production checklist before turning it on, and drive it with an external cron on `POST /api/integrations/run-scheduled` rather than the in-process loop.

> **Before a public launch:** the Google connector uses `drive.readonly`, which Google classifies as a **restricted** scope. Unverified apps are capped at 100 users behind a warning screen, and verification can require an annual third-party security assessment. See **[docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md)**.

Full data flow, failure handling and the endpoint list are in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** §7.7.

## Project Structure

```
frontend/          Next.js app
backend/           FastAPI app
docs/              Architecture documentation
```

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full system map: auth, storage, every major API, AI flows, and step-by-step examples.

## Production deployment

- **[docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md)** — storage, DB, integrations (credential key, OAuth verification, refresh cost), Razorpay webhooks, email, observability, legal pages.
- **File uploads:** set **`UPLOAD_DIR`** to an **absolute path** on a **persistent volume** (not only the default `./data/uploads`) so user files survive API redeploys on PaaS hosts.

### Razorpay (optional)

Flow matches [Razorpay Subscriptions — integration guide](https://razorpay.com/docs/payments/subscriptions/integration-guide/): **(1)** define **Plans** in the Dashboard (`plan_…` ids) → **(2)** `POST /api/billing/razorpay/checkout` creates a **Subscription** (`sub_…`) → **(3)** `/pricing` opens **Standard Checkout** with `key_id` + `subscription_id` → **(4)** on success, `POST /api/billing/razorpay/verify-checkout` verifies the **payment signature** (mandatory step in Razorpay’s docs) → **(5)** webhooks on `/api/billing/razorpay/webhook` update `subscription_plan`. A **PWA `manifest`** is not required for Razorpay.

In `backend/.env` set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_PLAN_STARTER`, and `RAZORPAY_PLAN_PRO`. Register the webhook URL `https://<your-api-host>/api/billing/razorpay/webhook` and enable subscription events. Without these variables, checkout returns **503** and the app stays plan-testable via `FORCE_SUBSCRIPTION_PLAN` or SQL.

**Checkout UX:** The pricing page opens **Razorpay Standard Checkout** in a modal (`checkout.js`). Razorpay POSTs to **`/api/billing/razorpay/callback`**, which redirects to **`/pricing/success`** (verify plan + dashboard). Set `NEXT_PUBLIC_RAZORPAY_HOSTED_CHECKOUT=true` only if you must use Razorpay’s hosted `short_url` page.

**If checkout shows “This payment has failed due to an issue with the merchant”** (inside the Razorpay modal), that message comes from Razorpay’s servers, not the app. Typical causes: **(1)** Razorpay account not fully **activated / KYC-complete** for the mode you are using; **(2)** **`RAZORPAY_KEY_ID` / secret** are **test** but **plans** (`RAZORPAY_PLAN_*`) were created in **live** (or the opposite); **(3)** plan id wrong, plan **paused**, or **currency** does not match your account; **(4)** Subscriptions product not enabled for the merchant (Dashboard → **Subscriptions** / support). After fixing Dashboard or `.env`, redeploy the API and try again. Razorpay support can confirm hidden account flags for subscription checkout in production.

**Email vs checkout:** Until the merchant error above is fixed, Razorpay may still create a subscription in `created` and (if **customer_notify** were enabled) email a pay link—that can feel contradictory with a failing modal. This app sets **`customer_notify: false`** on subscription create so Razorpay does not send those extra “complete payment” emails while you use in-app Checkout; you can switch to `true` + `notify_info` in `razorpay_service.py` if you prefer email-first flows.
