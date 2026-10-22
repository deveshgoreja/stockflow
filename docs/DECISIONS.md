# Design decisions

Each entry gives the choice, the alternative considered, and why. They are written so they can be
explained and defended in an interview.

## Concurrency and transactions

### 1. Pessimistic row locks (`SELECT … FOR UPDATE`) instead of conditional `UPDATE`s

**Choice.** Every stock change first locks the affected `inventory` rows with
`SELECT … FOR UPDATE`, checks quantities in Python, then writes.

**Alternative.** An atomic conditional update per item:
`UPDATE inventory SET quantity = quantity - :q WHERE product_id = :p AND quantity >= :q RETURNING quantity`.

**Why.** Both approaches are correct under `READ COMMITTED`. Locking first lets the order service
check *every* line before writing anything, so a 409 can list all short products at once instead of
only the first. It also gives one locking helper (`inventory_service.lock_inventory_rows`) shared by
orders, cancellations and manual adjustments, so all three follow one rule. The conditional update
saves a round trip per item, but at this scale clarity beats a few milliseconds.

### 2. Locks are always taken in ascending `product_id` order

**Choice.** `lock_inventory_rows` runs a single
`SELECT … WHERE product_id IN (…) ORDER BY product_id FOR UPDATE`. PostgreSQL locks rows as they
come out of the sort, so the lock order is fixed by the `ORDER BY`.

**Alternative.** Lock rows in the order the client listed them, and retry when a deadlock occurs.

**Why.** A deadlock needs a cycle: A holds X and waits for Y while B holds Y and waits for X. If
every transaction acquires locks in the same global order, that cycle cannot form. Retry loops
treat the symptom and add latency under contention. `test_overlapping_multi_product_orders_do_not_deadlock`
sends 60 concurrent orders over 5 products in shuffled and reversed orders, and all 60 succeed.

### 3. Isolation level stays at `READ COMMITTED`

**Alternative.** `SERIALIZABLE`.

**Why.** Correctness comes from row locks, not snapshot isolation. Under `READ COMMITTED`, a
`SELECT … FOR UPDATE` that waited for a lock returns the *newly committed* row version, which is
exactly what the stock check needs. `SERIALIZABLE` would make every caller handle serialization
failures with retries, adding complexity without adding safety here.

### 4. The order row is inserted *before* inventory is locked

**Choice.** `_place_order` validates products, computes the total, `INSERT`s the order and flushes,
and only then locks inventory.

**Alternative.** The spec's literal order: lock inventory, then insert the order.

**Why.** Inserting first claims the idempotency key immediately. A concurrent duplicate with the same
key blocks on the unique index while it holds no inventory locks, then fails with an
`IntegrityError` once the first transaction commits. With the other order, duplicates would queue on
inventory locks, decrement stock, and only fail at the end, holding locks longer for nothing. Both
orders are atomic; this one wastes less work. It also introduces no new lock-order cycle, because a
transaction waiting on the key holds no inventory locks.

### 5. Each service function owns its transaction

**Choice.** Services wrap each unit of work in `with session.begin():`. Routers never commit. The
session uses `expire_on_commit=False`, so routers can serialize the returned objects without a
hidden reload query.

**Alternative.** Commit in the router or in a middleware that wraps each request.

**Why.** The transaction boundary sits next to the business logic that needs atomicity, and the
same functions are reused by the seed script and tests outside HTTP. FastAPI's `Depends(get_session)`
gives every request its own session and connection, so nothing is shared between requests.

### 6. Cancellation locks the order row, then inventory

The `FOR UPDATE` on the order row serializes concurrent cancellations. The loser wakes up after the
winner commits, re-reads the row (`populate_existing` makes sure the ORM does not reuse a stale
copy), sees `CANCELLED`, and returns 409. Order creation never locks *existing* orders, so the lock
order "order row, then inventory rows (ascending)" cannot form a cycle with order creation.

### 7. Prices are read without a lock

Order creation reads `products.price` with a plain `SELECT`. A concurrent price edit lands either
before or after the read, and either outcome is a valid price to charge; the captured `unit_price`
is then immutable. Locking product rows would block price edits behind every in-flight order for no
correctness gain. The same reasoning applies to a product being deactivated while an order is
in flight: the order may still succeed if it read the product as active.

## Idempotency

### 8. Replays return `200` with the stored order; a new order returns `201`

**Alternative.** Return the original `201` again.

**Why.** Both are defensible. `200` lets a client (and the tests) tell "created now" from "already
existed" without extra headers, while the body is identical. The replay returns the order's
*current* state, so a replay after cancellation shows `CANCELLED` and never a stale snapshot.

### 9. Request hash = SHA-256 of canonical JSON, items sorted by `product_id`

The same basket listed in a different order is the same request. The hash covers only the validated
body (`{"items": [...]}`), so formatting differences in the raw JSON do not matter. `request_hash`
is stored only when a key was supplied.

### 10. Concurrent duplicates are resolved by the unique constraint

There is no read-then-insert check alone: two requests can both see "no order with this key". The
`UNIQUE (idempotency_key)` constraint is the arbiter. The loser catches the `IntegrityError`,
confirms the violated constraint is `uq_orders_idempotency_key` (using the deterministic naming
convention), reloads the winner's order in a fresh transaction, and compares hashes. A failed attempt
(for example insufficient stock) rolls back fully, so it does not consume the key and the client can
retry with it.

### 11. Keys are global, up to 255 characters

There is no authentication, so there is no per-client namespace to scope keys to. With auth, the
unique constraint would become `(client_id, idempotency_key)`.

## Data model

### 12. Statuses and movement types are `VARCHAR` + `CHECK`, not PostgreSQL `ENUM`

Adding a value to a native enum needs `ALTER TYPE`, which is awkward in migrations and cannot run
inside a transaction on older versions. A `CHECK` constraint is equally strict and easy to change.
Python `StrEnum`s give type safety in the code.

### 13. The movement ledger is append-only, enforced by a trigger

A `BEFORE UPDATE OR DELETE` trigger on `stock_movements` raises an exception. "Never update or delete
movements" then holds even for ad-hoc SQL or a future bug, not just by convention.
`test_movements_are_append_only` checks it.

### 14. Extra constraints beyond the spec

- `CHECK (resulting_quantity >= 0)` on movements, `CHECK (total_amount >= 0)` on orders,
  `CHECK (unit_price >= 0)` on order items, `CHECK (low_stock_threshold >= 0)` on products.
- `UNIQUE (order_id, product_id)` on `order_items` backs the "one line per product" rule. Its
  leading column also serves as the index for `order_id` lookups, so no separate `order_id` index
  is created.
- Indexes on `products.category` and `products.is_active` for the list filters.

### 15. Duplicate product IDs in one order are rejected (`400 DUPLICATE_ORDER_ITEM`)

**Alternative.** Merge them by summing quantities.

**Why.** Duplicates usually mean a client bug, and silently merging hides it. Rejecting also keeps
the canonical request hash unambiguous.

### 16. Money is `NUMERIC(12,2)` / `Decimal`, and is sent over JSON as a string

Pydantic v2 serializes `Decimal` as a string (`"19.99"`), which avoids float rounding in JSON
parsers. The dashboard converts to `Number` only for display. Totals are computed as
`sum(unit_price * quantity)` in `Decimal`, which is exact for 2-decimal prices and integer
quantities.

### 17. SKUs are trimmed and upper-cased before validation

`kb-001` and `KB-001` are the same SKU, so normalization makes the unique constraint
case-insensitive in practice. Allowed characters: `A-Z 0-9 _ -`, starting with a letter or digit.

### 18. Products are never deleted

Orders and movements reference products, so deleting one would break history. Deactivating
(`is_active = false`) stops it being ordered; it can still be restocked or adjusted.

## API behaviour

### 19. Status code choices

- Inactive product in an order → `400 PRODUCT_INACTIVE` (the request is invalid as a business
  request; nothing conflicts with concurrent state).
- Unknown product in an order → `404 PRODUCT_NOT_FOUND`, listing every missing ID.
- Insufficient stock (orders and negative adjustments) → `409 INSUFFICIENT_STOCK` with a
  `shortages` list.
- Manual `PURCHASE`/`CANCELLATION` movements, or a negative `RESTOCK` → `400`. Those movement types
  are produced only by the order workflow.

### 20. Low stock means `quantity <= low_stock_threshold`, active products only

Inclusive, so a threshold of 5 alerts at 5 units. Inactive products are excluded, because no one
needs to restock what cannot be sold.

### 21. `limit`/`offset` pagination, `limit ≤ 200`, responses include `total`

This is simple and fine for an admin dashboard. Keyset pagination would scale better for very large
movement tables, and is noted as a limitation.

## Testing

### 22. Concurrency tests drive a real Uvicorn server over HTTP

**Alternative.** Call service functions from threads.

**Why.** Going through HTTP exercises everything a real client would hit: routing, per-request
sessions, error translation and the idempotency header. Each worker thread has its own HTTP client,
and a `threading.Barrier` releases them all at once.

### 23. The connection pool (10 + 20 overflow) is smaller than the request burst

With 100 simultaneous requests, up to 30 transactions run in PostgreSQL at once and the rest wait
for a connection. This keeps the app well below PostgreSQL's default `max_connections = 100` while
still producing heavy lock contention: in a run with the row lock deliberately removed, 10 of 100
buyers "bought" the single unit (see the README).

### 24. Tests rebuild the schema from migrations

The session fixture drops the `public` schema and runs `alembic upgrade head`, so every test run
proves the migrations build the schema from an empty database. A test also diffs the migrated schema
against the ORM models (`alembic.autogenerate.compare_metadata`), so they cannot drift apart. As a
safety guard, the test database URL must end in `_test`.

### 25. Forced mid-transaction failures use `monkeypatch`, not test hooks in production code

The rollback tests wrap `inventory_service.apply_stock_change` so its N-th call raises after earlier
calls have already flushed their `UPDATE` and `INSERT` to PostgreSQL. The production code carries no
testing switches.

## Frontend and packaging

### 26. No router or UI library

Four tabs held in React state cover the dashboard; `react-router` would add a dependency for no
benefit. Plain CSS keeps the bundle small (about 52 kB gzipped JS).

### 27. The dashboard generates one `Idempotency-Key` per checkout attempt

A double-click or a retry after a network error re-sends the same key, so the server creates the
order once. After a business rejection (for example a 409), the basket has to change, so a new key
is generated.

### 28. Compose runs the Vite dev server in a `node:20-alpine` container

The spec allows either the dev server or built static assets. Serving built assets would need a web
server such as nginx, which is not in the specified stack. The dev server also gives hot reload while
demoing.

### 29. Migrations run on API container start

`alembic upgrade head && uvicorn …` means `docker compose up` on an empty volume produces a working
schema with no manual step. It is idempotent on later starts.
