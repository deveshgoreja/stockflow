"""Force failures half-way through a transaction and prove nothing partial survives."""

import pytest
from fastapi.testclient import TestClient

from app.database.connection import SessionLocal
from app.main import app
from app.schemas.order import OrderCreate
from app.services import inventory_service, order_service
from tests.helpers import (
    assert_inventory_matches_movements,
    count_rows,
    create_product,
    place_order,
    quantity_of,
)


class SimulatedCrashError(RuntimeError):
    pass


def fail_on_call(monkeypatch, call_number: int) -> None:
    """Let apply_stock_change succeed until the given call, then blow up.

    Earlier calls have already flushed their UPDATE and INSERT to PostgreSQL, so
    the failure really happens mid-transaction with dirty rows in flight.
    """
    real = inventory_service.apply_stock_change
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == call_number:
            raise SimulatedCrashError("simulated failure after partial writes")
        return real(*args, **kwargs)

    monkeypatch.setattr(inventory_service, "apply_stock_change", flaky)


def test_order_creation_rolls_back_completely_on_mid_transaction_failure(
    client, db_session, monkeypatch
):
    a = create_product(client, stock=10)
    b = create_product(client, stock=10)
    movements_before = count_rows(db_session, "stock_movements")
    payload = OrderCreate(
        items=[{"product_id": a["id"], "quantity": 3}, {"product_id": b["id"], "quantity": 4}]
    )
    fail_on_call(monkeypatch, call_number=2)

    with SessionLocal() as session, pytest.raises(SimulatedCrashError):
        order_service.create_order(session, payload, idempotency_key="crash-key")

    assert quantity_of(db_session, a["id"]) == 10
    assert quantity_of(db_session, b["id"]) == 10
    assert count_rows(db_session, "orders") == 0
    assert count_rows(db_session, "order_items") == 0
    assert count_rows(db_session, "stock_movements") == movements_before
    assert_inventory_matches_movements(db_session)

    monkeypatch.undo()
    retry = place_order(client, [(a["id"], 3), (b["id"], 4)], idempotency_key="crash-key")
    assert retry.status_code == 201


def test_cancellation_rolls_back_completely_on_mid_transaction_failure(
    client, db_session, monkeypatch
):
    a = create_product(client, stock=10)
    b = create_product(client, stock=10)
    order = place_order(client, [(a["id"], 3), (b["id"], 4)]).json()
    movements_before = count_rows(db_session, "stock_movements")
    fail_on_call(monkeypatch, call_number=2)

    with SessionLocal() as session, pytest.raises(SimulatedCrashError):
        order_service.cancel_order(session, order["id"])

    assert client.get(f"/orders/{order['id']}").json()["status"] == "CONFIRMED"
    assert quantity_of(db_session, a["id"]) == 7
    assert quantity_of(db_session, b["id"]) == 6
    assert count_rows(db_session, "stock_movements") == movements_before

    monkeypatch.undo()
    assert client.post(f"/orders/{order['id']}/cancel").status_code == 200
    assert quantity_of(db_session, a["id"]) == 10


def test_unexpected_errors_return_500_with_error_shape(client, monkeypatch):
    product = create_product(client, stock=5)
    fail_on_call(monkeypatch, call_number=1)

    with TestClient(app, raise_server_exceptions=False) as crashing_client:
        response = place_order(crashing_client, [(product["id"], 1)])
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
