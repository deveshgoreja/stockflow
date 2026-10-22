from collections import Counter

from app.database.connection import SessionLocal
from tests.helpers import count_rows, create_product, place_order, quantity_of


def test_20_concurrent_cancellations_restore_stock_exactly_once(api, run_concurrently):
    a = create_product(api, stock=10)
    b = create_product(api, stock=10)
    order = place_order(api, [(a["id"], 3), (b["id"], 5)]).json()

    responses = run_concurrently(20, lambda c, _: c.post(f"/orders/{order['id']}/cancel"))

    assert Counter(r.status_code for r in responses) == {200: 1, 409: 19}
    assert {r.json()["error"]["code"] for r in responses if r.status_code == 409} == {
        "ORDER_ALREADY_CANCELLED"
    }
    with SessionLocal() as session:
        assert quantity_of(session, a["id"]) == 10
        assert quantity_of(session, b["id"]) == 10
        assert count_rows(session, "stock_movements", "movement_type = 'CANCELLATION'") == 2


def test_20_concurrent_requests_with_one_idempotency_key_create_one_order(api, run_concurrently):
    product = create_product(api, stock=100)

    responses = run_concurrently(
        20, lambda c, _: place_order(c, [(product["id"], 3)], idempotency_key="double-click")
    )

    assert Counter(r.status_code for r in responses) == {201: 1, 200: 19}
    assert len({r.json()["id"] for r in responses}) == 1
    with SessionLocal() as session:
        assert count_rows(session, "orders") == 1
        assert quantity_of(session, product["id"]) == 97
        assert count_rows(session, "stock_movements", "movement_type = 'PURCHASE'") == 1


def test_concurrent_key_reuse_with_different_payloads(api, run_concurrently):
    """Same key, two different baskets racing: one order is created, the other basket gets 409."""
    product = create_product(api, stock=100)

    responses = run_concurrently(
        20,
        lambda c, i: place_order(c, [(product["id"], 1 + i % 2)], idempotency_key="shared"),
    )

    created = [r for r in responses if r.status_code == 201]
    assert len(created) == 1
    winning_quantity = created[0].json()["items"][0]["quantity"]
    for response in responses:
        if response.status_code == 409:
            assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        else:
            assert response.json()["id"] == created[0].json()["id"]
    with SessionLocal() as session:
        assert count_rows(session, "orders") == 1
        assert quantity_of(session, product["id"]) == 100 - winning_quantity


def test_mixed_workload_keeps_the_ledger_consistent(api, run_concurrently):
    """Orders, cancellations and restocks interleaved; the autouse fixture checks the invariant."""
    products = [create_product(api, stock=20) for _ in range(4)]
    ids = [p["id"] for p in products]
    existing = [
        place_order(api, [(ids[i % 4], 1), (ids[(i + 1) % 4], 1)]).json() for i in range(10)
    ]

    def action(client, i):
        kind = i % 3
        if kind == 0:
            return client.post(f"/orders/{existing[i % 10]['id']}/cancel")
        if kind == 1:
            return place_order(client, [(ids[i % 4], 2), (ids[(i + 2) % 4], 1)])
        return client.post(
            "/inventory/adjustments",
            json={"product_id": ids[i % 4], "change_quantity": 3, "movement_type": "RESTOCK"},
        )

    responses = run_concurrently(45, action)

    assert set(r.status_code for r in responses) <= {200, 201, 409}
    with SessionLocal() as session:
        cancelled = count_rows(session, "orders", "status = 'CANCELLED'")
        assert cancelled == 10
        assert count_rows(session, "stock_movements", "movement_type = 'CANCELLATION'") == 20
