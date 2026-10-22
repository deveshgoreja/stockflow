from itertools import count
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

_sku_counter = count(1)


def create_product(
    client: httpx.Client,
    *,
    stock: int = 0,
    price: str = "10.00",
    sku: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload = {
        "sku": sku or f"SKU-{next(_sku_counter):05d}",
        "name": "Test product",
        "price": price,
    }
    payload.update(fields)
    response = client.post("/products", json=payload)
    assert response.status_code == 201, response.text
    product = response.json()
    if stock:
        restock(client, product["id"], stock)
        product["quantity"] = stock
    return product


def restock(client: httpx.Client, product_id: int, quantity: int) -> None:
    response = client.post(
        "/inventory/adjustments",
        json={"product_id": product_id, "change_quantity": quantity, "movement_type": "RESTOCK"},
    )
    assert response.status_code == 201, response.text


def place_order(
    client: httpx.Client, items: list[tuple[int, int]], idempotency_key: str | None = None
) -> httpx.Response:
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    body = {"items": [{"product_id": pid, "quantity": qty} for pid, qty in items]}
    return client.post("/orders", json=body, headers=headers)


def quantity_of(session: Session, product_id: int) -> int:
    return session.execute(
        text("SELECT quantity FROM inventory WHERE product_id = :pid"), {"pid": product_id}
    ).scalar_one()


def count_rows(session: Session, table: str, where: str = "TRUE", **params: Any) -> int:
    return session.execute(text(f"SELECT count(*) FROM {table} WHERE {where}"), params).scalar_one()


def assert_inventory_matches_movements(session: Session) -> None:
    """The ledger invariant: stock on hand equals the sum of all recorded movements.

    Also checks that each movement's resulting_quantity equals the running total
    at that point, which proves movements were written in lock order.
    """
    mismatched = session.execute(
        text(
            """
            SELECT i.product_id, i.quantity, COALESCE(SUM(m.change_quantity), 0) AS ledger
            FROM inventory i
            LEFT JOIN stock_movements m ON m.product_id = i.product_id
            GROUP BY i.product_id, i.quantity
            HAVING i.quantity <> COALESCE(SUM(m.change_quantity), 0)
            """
        )
    ).all()
    assert mismatched == [], f"inventory differs from movement ledger: {mismatched}"

    broken_chain = session.execute(
        text(
            """
            SELECT id, product_id, resulting_quantity, running_total FROM (
                SELECT id, product_id, resulting_quantity,
                       SUM(change_quantity)
                           OVER (PARTITION BY product_id ORDER BY id) AS running_total
                FROM stock_movements
            ) AS ledger
            WHERE resulting_quantity <> running_total
            """
        )
    ).all()
    assert broken_chain == [], f"resulting_quantity does not match running total: {broken_chain}"
