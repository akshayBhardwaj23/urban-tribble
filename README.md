# Snaptix

AI-powered business analytics SaaS. Upload Excel/CSV files and get automated dashboards, AI-generated insights, forecasting, and natural language data querying.

## Tech Stack

- **Frontend**: Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, Recharts
- **Backend**: FastAPI, Python 3.11+, Pandas, [Prophet](https://facebook.github.io/prophet/) (forecasting; CmdStan via `cmdstanpy` on first fit), OpenAI GPT-4o, SQLAlchemy
- **Database**: SQLite (dev) / PostgreSQL (prod)

## Quick Start

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add your OpenAI key
uvicorn main:app --reload
```

Backend runs at http://localhost:8000. Health check: http://localhost:8000/health

**Forecasting:** Dataset and workspace outlooks use **Prophet** when enough history is present (see `FORECAST_ENGINE`, `FORECAST_PROPHET_MIN_POINTS`, `FORECAST_PROPHET_MAX_HISTORY_ROWS` in `backend/config.py`). Shorter series, non-positive values, or failures fall back to **linear regression**. Installing `prophet` may download CmdStan the first time a Prophet model runs; allow network during `pip install` and on that first fit in CI or containers.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local  # add Google OAuth credentials
npm run dev
```

Frontend runs at http://localhost:3000.

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new OAuth 2.0 Client ID (Web application)
3. Add `http://localhost:3000` to Authorized JavaScript origins
4. Add `http://localhost:3000/api/auth/callback/google` to Authorized redirect URIs
5. For production at **https://snaptix.ai**, also add `https://snaptix.ai` and `https://snaptix.ai/api/auth/callback/google`, and set `NEXTAUTH_URL=https://snaptix.ai` in `frontend/.env.local`
6. Copy Client ID and Client Secret to `frontend/.env.local`
7. Generate a NEXTAUTH_SECRET: `openssl rand -base64 32`

## Project Structure

```
frontend/          Next.js app
backend/           FastAPI app
docs/              Architecture documentation
```

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full system map: auth, storage, every major API, AI flows, and step-by-step examples.

### Razorpay (optional)

Flow matches [Razorpay Subscriptions — integration guide](https://razorpay.com/docs/payments/subscriptions/integration-guide/): **(1)** define **Plans** in the Dashboard (`plan_…` ids) → **(2)** `POST /api/billing/razorpay/checkout` creates a **Subscription** (`sub_…`) → **(3)** `/pricing` opens **Standard Checkout** with `key_id` + `subscription_id` → **(4)** on success, `POST /api/billing/razorpay/verify-checkout` verifies the **payment signature** (mandatory step in Razorpay’s docs) → **(5)** webhooks on `/api/billing/razorpay/webhook` update `subscription_plan`. A **PWA `manifest`** is not required for Razorpay.

In `backend/.env` set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_PLAN_STARTER`, and `RAZORPAY_PLAN_PRO`. Register the webhook URL `https://<your-api-host>/api/billing/razorpay/webhook` and enable subscription events. Without these variables, checkout returns **503** and the app stays plan-testable via `FORCE_SUBSCRIPTION_PLAN` or SQL.

**Checkout UX:** The pricing page opens **Razorpay Standard Checkout** in a modal (`checkout.js`) using your public `key_id` and the new `subscription_id` (Razorpay’s documented flow). It only falls back to redirecting via `short_url` if the script cannot load.

**If checkout shows “This payment has failed due to an issue with the merchant”** (inside the Razorpay modal), that message comes from Razorpay’s servers, not the app. Typical causes: **(1)** Razorpay account not fully **activated / KYC-complete** for the mode you are using; **(2)** **`RAZORPAY_KEY_ID` / secret** are **test** but **plans** (`RAZORPAY_PLAN_*`) were created in **live** (or the opposite); **(3)** plan id wrong, plan **paused**, or **currency** does not match your account; **(4)** Subscriptions product not enabled for the merchant (Dashboard → **Subscriptions** / support). After fixing Dashboard or `.env`, redeploy the API and try again. Razorpay support can confirm hidden account flags for subscription checkout in production.

**Email vs checkout:** Until the merchant error above is fixed, Razorpay may still create a subscription in `created` and (if **customer_notify** were enabled) email a pay link—that can feel contradictory with a failing modal. This app sets **`customer_notify: false`** on subscription create so Razorpay does not send those extra “complete payment” emails while you use in-app Checkout; you can switch to `true` + `notify_info` in `razorpay_service.py` if you prefer email-first flows.
