# Excel Consultant

AI-powered business analytics SaaS. Upload Excel/CSV files and get automated dashboards, AI-generated insights, forecasting, and natural language data querying.

## Tech Stack

- **Frontend**: Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, Recharts
- **Backend**: FastAPI, Python 3.11+, Pandas, OpenAI GPT-4o, SQLAlchemy
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
5. Copy Client ID and Client Secret to `frontend/.env.local`
6. Generate a NEXTAUTH_SECRET: `openssl rand -base64 32`

## Project Structure

```
frontend/          Next.js app
backend/           FastAPI app
docs/              Architecture documentation
```

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full system map: auth, storage, every major API, AI flows, and step-by-step examples.

### Razorpay (optional)

Subscriptions are wired to [Razorpay Plans](https://razorpay.com/docs/subscriptions/). In `backend/.env` set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_PLAN_STARTER`, and `RAZORPAY_PLAN_PRO` (plan ids from the Razorpay Dashboard). Register the webhook URL `https://<your-api-host>/api/billing/razorpay/webhook` and enable subscription events. Without these variables, checkout returns **503** and the app stays plan-testable via `FORCE_SUBSCRIPTION_PLAN` or SQL.

**Checkout UX:** The pricing page opens **Razorpay Standard Checkout** in a modal (`checkout.js`) using your public `key_id` and the new `subscription_id` (Razorpay’s documented flow). It only falls back to redirecting via `short_url` if the script cannot load. **If you still see “Hosted page is not available”** on a redirect URL, you are likely on the legacy `short_url` path—restart the API and hard-refresh the app—or the subscription is invalid (expired link, test/live mismatch, or plan not eligible). In Razorpay Dashboard ensure **Subscriptions** are enabled, **Plan IDs** match test vs live keys, and cancel stale `created` subscriptions when testing plan switches.
