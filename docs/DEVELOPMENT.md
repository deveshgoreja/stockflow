# Running locally without Docker

You need Python 3.12, Node 20+, and a PostgreSQL 16 server with a `stockflow` role and two
databases, `stockflow` and `stockflow_test` (see `.env.example` for the connection strings).

## Backend

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m scripts.seed           # demo data; add --reset to wipe existing data first
uvicorn app.main:app --reload
```

The API is then at http://localhost:8000, with interactive docs at http://localhost:8000/docs.

## Dashboard

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. The dashboard reads `VITE_API_URL` from the repository's `.env`.

## Tests

See [TESTING.md](TESTING.md).
