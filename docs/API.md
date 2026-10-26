# API reference

With the API running, interactive documentation is at http://localhost:8000/docs.

| Method | Path | What it does |
|---|---|---|
| `POST` | `/products` | Create a product (duplicate SKU → `409`) |
| `GET` | `/products` | List; filter by `search`, `category`, `is_active` |
| `GET` | `/products/{id}` | Get one product |
| `PATCH` | `/products/{id}` | Partial update |
| `GET` | `/inventory` | Stock levels; `low_stock=true` for alerts only |
| `GET` | `/inventory/{product_id}` | Stock for one product |
| `POST` | `/inventory/adjustments` | Restock or adjust (`RESTOCK` / `ADJUSTMENT`) |
| `GET` | `/inventory/movements` | Ledger, newest first; filter by `product_id` |
| `POST` | `/orders` | Place an order; optional `Idempotency-Key` header |
| `GET` | `/orders` | List; filter by `status` (`CONFIRMED` / `CANCELLED`) |
| `GET` | `/orders/{id}` | Get one order |
| `POST` | `/orders/{id}/cancel` | Cancel and restore stock (repeat → `409`) |
| `GET` | `/reports/summary` | Counts, low-stock count, sales totals |
| `GET` | `/health` | API and database health |

All list endpoints accept `limit` (up to 200) and `offset`, and return
`{"items": [...], "total": n, "limit": n, "offset": n}`.

## Status codes

| Code | Meaning |
|---|---|
| `200` | Success, including an idempotent replay of `POST /orders` |
| `201` | Created |
| `400` | Invalid business request (inactive product, duplicate line, negative restock) |
| `404` | Not found |
| `409` | Conflict: insufficient stock, duplicate SKU, idempotency key reused, already cancelled |
| `422` | Validation error |

## Error format

Every error has the same shape:

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Insufficient stock for: DSK-STAND-140",
    "details": {
      "shortages": [
        {"product_id": 13, "sku": "DSK-STAND-140", "requested": 5, "available": 1}
      ]
    }
  }
}
```

## Example: placing an order

```bash
curl -X POST localhost:8000/orders \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: checkout-7f3a' \
  -d '{"items": [{"product_id": 1, "quantity": 2}, {"product_id": 3, "quantity": 1}]}'
```

Sending the same request again with the same key returns the same order with `200`. Sending a
different body with that key returns `409 IDEMPOTENCY_KEY_REUSED`.

Money is returned as decimal strings (`"19.99"`) so no precision is lost in JSON.
