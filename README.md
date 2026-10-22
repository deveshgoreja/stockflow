# StockFlow

[![CI](https://github.com/__OWNER__/stockflow/actions/workflows/ci.yml/badge.svg)](https://github.com/__OWNER__/stockflow/actions/workflows/ci.yml)

**An inventory and order management system that stays correct when many requests hit it at once.**

StockFlow manages products, stock levels, multi-item orders, cancellations and a full audit trail
of every stock change, with a FastAPI backend, PostgreSQL, and a React dashboard.

### Why it's not just CRUD

The interesting part is what happens under real-world pressure:

- **100 people try to buy the last unit at the same moment.** Exactly one succeeds; 99 get a
  clean `409`, never a negative stock count.
- **Orders touching overlapping products arrive in different item orders.** No deadlocks, because
  every transaction locks rows in the same global order.
- **A customer double-clicks "Place order"** or a client retries after a timeout. The
  `Idempotency-Key` header guarantees a single order, even when the duplicates arrive concurrently.
- **Twenty cancel requests race for the same order.** Stock is restored exactly once.
- **Something fails half-way through an order.** The whole transaction rolls back: no partial
  order, no lost stock, no orphan ledger rows.

Each of these has an automated test that runs against a real PostgreSQL database and a real HTTP
server.

## Features

- **Products:** create, update, list, search (name/SKU), filter by category and status. SKUs are
  unique (enforced in the database); money is `NUMERIC(12,2)` / `Decimal`, never float.
- **Inventory:** a separate table with one row per product; restocks and positive or negative
  adjustments; a per-product low-stock threshold; `CHECK (quantity >= 0)`.
- **Orders:** multi-item, all-or-nothing; captures unit prices at purchase time (later price changes
  never alter history); rejects inactive products and insufficient stock, naming every short item.
- **Cancellation:** restores stock and records it in the ledger; safe under concurrent requests.
- **Idempotency:** the optional `Idempotency-Key` header; same key + same body replays the order,
  same key + different body is a `409`.
- **Audit ledger:** every stock change writes an append-only `stock_movements` row
  (`RESTOCK`, `ADJUSTMENT`, `PURCHASE`, `CANCELLATION`) with the resulting quantity. A database
  trigger forbids edits and deletes.
- **Reports:** product counts, low-stock count, units in stock, confirmed/cancelled orders, units
  sold and sales totals (confirmed orders only).
- **Dashboard:** React UI for all of the above, with API errors (such as insufficient stock or
  duplicate SKU) shown clearly.

## Tech stack

| | |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (2.0-style API), Pydantic v2, Uvicorn, psycopg 3 |
| Database | PostgreSQL 16, Alembic migrations |
| Frontend | React 18 + Vite, plain JavaScript and CSS |
| Tooling | pytest, Ruff, Docker, Docker Compose, GitHub Actions |

## Architecture

```mermaid
flowchart LR
    UI["React dashboard<br/>Vite · :5173"] -- "JSON / HTTP" --> R
    subgraph API["FastAPI · :8000"]
        R["Routers<br/>HTTP only"] --> S["Services<br/>business rules +<br/>transactions"]
        S --> M["SQLAlchemy models"]
    end
    M --> DB[("PostgreSQL 16<br/>CHECK constraints,<br/>row locks, unique keys,<br/>append-only trigger")]
```

Routers handle HTTP, services own the business rules and the transaction boundaries, and
PostgreSQL enforces the invariants. More detail is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
and every non-obvious choice is explained in [docs/DECISIONS.md](docs/DECISIONS.md).

```text
app/
  api/        routers: products, inventory, orders, reports
  services/   product_service, inventory_service, order_service, report_service
  models/     Product, Inventory, Order, OrderItem, StockMovement
  schemas/    Pydantic request/response models
  database/   engine, per-request session
  core/       settings, error types and handlers
migrations/   Alembic revisions
frontend/     React dashboard
tests/        unit/ integration/ concurrency/
scripts/      seed.py
```

## Quick start (Docker Compose)

```bash
git clone https://github.com/__OWNER__/stockflow.git
cd stockflow
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:5173 |
| API | http://localhost:8000 |
| Interactive API docs | http://localhost:8000/docs |

The API container applies migrations on start-up. To load the demo dataset (20 products, about 30
orders, a few cancellations and adjustments), run:

```bash
docker compose exec api python -m scripts.seed
```

Use `--reset` to wipe existing data first.

## Running locally without Docker

You need Python 3.12, Node 20+, and a PostgreSQL 16 server with a `stockflow` role and the
databases `stockflow` and `stockflow_test` (see `.env.example`).

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload
```

```bash
cd frontend && npm ci && npm run dev
```

## Running the tests

The tests need a PostgreSQL database whose name ends in `_test`; they drop and rebuild its schema
from the Alembic migrations. With the Compose database running (it creates `stockflow_test`
automatically):

```bash
pytest
```

The connection comes from `TEST_DATABASE_URL`, which defaults to
`postgresql+psycopg://stockflow:stockflow@localhost:5432/stockflow_test`. Lint and format:

```bash
ruff check . && ruff format --check .
```

### Test results

Measured on Windows 11 with a local PostgreSQL 16.15, Python 3.12.10, three consecutive runs of the
full suite:

```text
101 passed, 3 warnings in 41.55s
101 passed, 3 warnings in 43.70s
101 passed, 3 warnings in 42.59s
```

| Suite | Tests | What it proves |
|---|---|---|
| `tests/unit` | 43 | SKU/price validation, Decimal-exact totals, request-hash canonicalization, adjustment rules |
| `tests/integration` | 50 | CRUD, duplicate SKU, the 20 → 23 keyboard scenario, multi-item orders, insufficient stock leaves everything unchanged, forced mid-transaction rollback, cancellation, price history, idempotent replay and key reuse, append-only ledger, migrations match the models, every endpoint documented |
| `tests/concurrency` | 8 | Live Uvicorn server with real parallel HTTP requests (below); after **every** test, the ledger invariant is checked |

The 3 warnings are a third-party deprecation notice from Starlette's test client.

Concurrency results (every one of these assertions passed in all three runs):

| Scenario | Result |
|---|---|
| 100 concurrent buyers, 1 unit in stock | 1 × `201`, 99 × `409`, final stock 0, 1 order, 1 purchase movement |
| 50 concurrent buyers × 2 units, 25 in stock | 12 × `201`, 38 × `409`, 1 unit left |
| 60 concurrent orders over 5 shared products, shuffled/reversed item order | 60 × `201`, no deadlocks, stock totals reconcile exactly |
| 40 overlapping multi-item orders over scarce stock | only `201`/`409`, no partial orders, totals reconcile |
| 20 concurrent cancellations of one order | 1 × `200`, 19 × `409`, stock restored once |
| 20 concurrent requests, one idempotency key | 1 × `201`, 19 × `200`, all the same order, stock decremented once |
| 20 concurrent requests, one key, two different bodies | 1 order; mismatching bodies get `409 IDEMPOTENCY_KEY_REUSED` |
| 45 mixed orders / cancellations / restocks | every response `200`/`201`/`409`; ledger balances |

**Do the tests actually catch races?** As a check, the `FOR UPDATE` was temporarily removed from
the inventory lock query and the concurrency suite re-run. It failed loudly: **10 of 100 buyers
"bought" the single unit**, all 50 orders succeeded against 25 units of stock, and the ledger
invariant check failed on every test. With the lock restored, everything passes.

## API overview

All errors share one shape:
`{"error": {"code": "...", "message": "...", "details": {...}}}`.

| Method | Path | Notes |
|---|---|---|
| `POST` | `/products` | `201`; duplicate SKU → `409 DUPLICATE_SKU` |
| `GET` | `/products` | `?search=&category=&is_active=&limit=&offset=` |
| `GET` | `/products/{id}` | |
| `PATCH` | `/products/{id}` | partial update |
| `GET` | `/inventory` | `?low_stock=true&limit=&offset=` |
| `GET` | `/inventory/{product_id}` | |
| `POST` | `/inventory/adjustments` | `{product_id, change_quantity, movement_type: RESTOCK \| ADJUSTMENT, note}` |
| `GET` | `/inventory/movements` | `?product_id=&limit=&offset=`, newest first |
| `POST` | `/orders` | header `Idempotency-Key` (optional); `201` created, `200` replay |
| `GET` | `/orders` | `?status=CONFIRMED\|CANCELLED&limit=&offset=` |
| `GET` | `/orders/{id}` | |
| `POST` | `/orders/{id}/cancel` | `409 ORDER_ALREADY_CANCELLED` on repeat |
| `GET` | `/reports/summary` | counts, low-stock count, sales totals |
| `GET` | `/health` | `{"status": "ok", "database": "ok"}` |

Example:

```bash
curl -X POST localhost:8000/orders \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: checkout-7f3a' \
  -d '{"items": [{"product_id": 1, "quantity": 2}, {"product_id": 3, "quantity": 1}]}'
```

## How overselling is prevented

Several layers, each sufficient on its own for the case it covers:

1. **Row locks in a single transaction.** Order creation locks the inventory rows it needs with
   `SELECT … FOR UPDATE`, checks every line, then decrements. A competing transaction for the same
   product waits; when it gets the lock, PostgreSQL hands it the *updated* quantity, so the second
   buyer of the last unit sees 0 and gets a `409`.
2. **Deterministic lock order.** Rows are always locked in ascending `product_id` order (one
   `ORDER BY … FOR UPDATE` query), so two multi-item orders can never hold each other's rows in a
   cycle. Deadlocks are prevented, not retried.
3. **All-or-nothing.** The order, its items, the stock decrements and the ledger rows commit
   together or not at all.
4. **The database refuses negative stock.** `CHECK (quantity >= 0)` on `inventory` is a backstop
   that holds even if application code were wrong.
5. **Duplicate submissions are collapsed.** The `UNIQUE` idempotency key means retries and
   double-clicks cannot create a second order, even when they arrive in parallel.
6. **The ledger proves it.** Each product's stock always equals the sum of its movement rows, and
   the concurrency tests assert this after every run.

The full walkthrough, including why the lock order rules out deadlocks, is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Known limitations

- No authentication or roles, by design (out of scope). Idempotency keys are therefore global, not
  per client.
- Offset pagination; keyset pagination would suit very large movement histories better.
- Single warehouse, no payments or shipping, by design.
- The Compose frontend runs the Vite dev server rather than a production static build.
