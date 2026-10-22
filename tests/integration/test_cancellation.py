from tests.helpers import (
    assert_inventory_matches_movements,
    count_rows,
    create_product,
    place_order,
    quantity_of,
)


def test_cancellation_restores_stock_and_records_movements(client, db_session):
    a = create_product(client, stock=10)
    b = create_product(client, stock=10)
    order = place_order(client, [(a["id"], 4), (b["id"], 1)]).json()

    response = client.post(f"/orders/{order['id']}/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CANCELLED"
    assert body["updated_at"] > order["updated_at"]
    assert quantity_of(db_session, a["id"]) == 10
    assert quantity_of(db_session, b["id"]) == 10
    cancellations = client.get("/inventory/movements", params={"product_id": a["id"]}).json()
    latest = cancellations["items"][0]
    assert (latest["movement_type"], latest["change_quantity"], latest["order_id"]) == (
        "CANCELLATION",
        4,
        order["id"],
    )
    assert_inventory_matches_movements(db_session)


def test_cancelling_twice_is_a_409_and_restores_once(client, db_session):
    product = create_product(client, stock=5)
    order = place_order(client, [(product["id"], 2)]).json()

    assert client.post(f"/orders/{order['id']}/cancel").status_code == 200
    second = client.post(f"/orders/{order['id']}/cancel")

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ORDER_ALREADY_CANCELLED"
    assert quantity_of(db_session, product["id"]) == 5
    assert count_rows(db_session, "stock_movements", "movement_type = 'CANCELLATION'") == 1


def test_cancelling_missing_order_is_404(client):
    response = client.post("/orders/12345/cancel")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_cancelled_stock_can_be_sold_again(client):
    product = create_product(client, stock=1)
    order = place_order(client, [(product["id"], 1)]).json()
    assert place_order(client, [(product["id"], 1)]).status_code == 409
    client.post(f"/orders/{order['id']}/cancel")
    assert place_order(client, [(product["id"], 1)]).status_code == 201
