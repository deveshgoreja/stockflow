# Testing

All integration and concurrency tests run against a real PostgreSQL 16 database. Nothing is mocked
or replaced with SQLite. The test session rebuilds the schema from the Alembic migrations, and every
test starts from empty tables.

## Running the tests

The tests need a PostgreSQL database whose name ends in `_test` (a safety guard, because they drop
and recreate its schema). With the Docker Compose database running, `stockflow_test` is created
automatically:

```bash
pytest
```

The connection comes from `TEST_DATABASE_URL`, which defaults to
`postgresql+psycopg://stockflow:stockflow@localhost:5432/stockflow_test`.

Lint and format checks:

```bash
ruff check . && ruff format --check .
```

GitHub Actions runs all of this on every push, repeats the concurrency suite three times, builds the
dashboard, and starts the full Docker Compose stack as a smoke test.

## Results

Measured on Windows 11 with a local PostgreSQL 16.15 and Python 3.12.10, three consecutive runs of
the full suite:

```text
101 passed, 3 warnings in 41.55s
101 passed, 3 warnings in 43.70s
101 passed, 3 warnings in 42.59s
```

The 3 warnings are a third-party deprecation notice from Starlette's test client.

| Suite | Tests | What it covers |
|---|---|---|
| `tests/unit` | 43 | SKU and price validation, Decimal-exact totals, request-hash canonicalization, adjustment rules |
| `tests/integration` | 50 | Product CRUD and duplicate SKU, the 20 → 23 keyboard scenario, multi-item orders, insufficient stock leaving everything unchanged, forced mid-transaction rollback, cancellation, price history, idempotent replay and key reuse, append-only ledger, migrations matching the models, every endpoint documented |
| `tests/concurrency` | 8 | A live Uvicorn server receiving real parallel HTTP requests; the ledger invariant is checked after every test |

## Concurrency scenarios

Every one of these assertions passed in all three runs:

| Scenario | Result |
|---|---|
| 100 concurrent buyers, 1 unit in stock | 1 × `201`, 99 × `409`, final stock 0, 1 order, 1 purchase movement |
| 50 concurrent buyers × 2 units, 25 in stock | 12 × `201`, 38 × `409`, 1 unit left |
| 60 concurrent orders over 5 shared products, item order shuffled or reversed | 60 × `201`, no deadlocks, stock totals reconcile exactly |
| 40 overlapping multi-item orders over scarce stock | only `201`/`409`, no partial orders, totals reconcile |
| 20 concurrent cancellations of one order | 1 × `200`, 19 × `409`, stock restored once |
| 20 concurrent requests with one idempotency key | 1 × `201`, 19 × `200`, all the same order, stock decremented once |
| 20 concurrent requests, one key, two different bodies | 1 order; mismatching bodies get `409 IDEMPOTENCY_KEY_REUSED` |
| 45 mixed orders, cancellations and restocks | every response `200`/`201`/`409`; ledger balances |

## Do the tests actually catch races?

As a check, the `FOR UPDATE` was temporarily removed from the inventory lock query and the
concurrency suite re-run. It failed loudly:

- **10 of 100 buyers "bought" the single unit**;
- all 50 orders succeeded against 25 units of stock;
- the ledger invariant check failed on every test.

With the lock restored, everything passes.

## The ledger invariant

After each concurrency test, `tests/helpers.py::assert_inventory_matches_movements` checks two
properties for every product:

1. Current inventory quantity equals the sum of all its movement `change_quantity` values.
2. Ordered by `id`, each movement's `resulting_quantity` equals the running total up to that row.
