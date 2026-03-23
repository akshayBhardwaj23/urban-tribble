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
npm run dev
```

Frontend runs at http://localhost:3000.

## Project Structure

```
frontend/          Next.js app
backend/           FastAPI app
docs/              Architecture documentation
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full architecture details.
