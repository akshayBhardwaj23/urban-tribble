# Excel Consultant

AI-powered business analytics SaaS. Upload Excel/CSV files and get automated dashboards, AI-generated insights, forecasting, and natural language data querying.

## Tech Stack

- **Frontend**: Next.js 14+, TypeScript, Tailwind CSS, shadcn/ui, Recharts
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

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full architecture details.
