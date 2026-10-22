from decimal import Decimal

from tests.helpers import (
    assert_inventory_matches_movements,
    count_rows,
    create_product,
    place_order,
    quantity_of,
)


def test_multi_product_order(client, db_session):
    keyboard = create_product(client, price="49.99", stock=10)
    mouse = create_product(client, price="19.50", stock=10)

    response = place_order(client, [(mouse["id"], 3), (keyboard["id"], 2)])

    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "CONFIRMED"
    assert Decimal(order["total_amount"]) == Decimal("49.99") * 2 + Decimal("19.50") * 3
    assert [(i["product_id"], i["quantity"], i["unit_price"]) for i in order["items"]] == [
        (keyboard["id"], 2, "49.99"),
        (mouse["id"], 3, "19.50"),
    ]
    assert order["items"][0]["line_total"] == "99.98"
    assert quantity_of(db_session, keyboard["id"]) == 8
    assert quantity_of(db_session, mouse["id"]) == 7
    assert (
        count_rows(
            db_session,
            "stock_movements",
            "order_id = :oid AND movement_type = 'PURCHASE'",
            oid=order["id"],
        )
        == 2
    )
    assert_inventory_matches_movements(db_session)


def test_insufficient_stock_rejects_whole_order_and_changes_nothing(client, db_session):
    plenty = create_product(client, sku="PLENTY", stock=10)
    scarce = create_product(client, sku="SCARCE", stock=1)
    movements_before = count_rows(db_session, "stock_movements")

    response = place_order(client, [(plenty["id"], 5), (scarce["id"], 2)])

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INSUFFICIENT_STOCK"
    assert "SCARCE" in error["message"]
    assert error["details"]["shortages"] == [
        {"product_id": scarce["id"], "sku": "SCARCE", "requested": 2, "available": 1}
    ]
    assert quantity_of(db_session, plenty["id"]) == 10
    assert quantity_of(db_session, scarce["id"]) == 1
    assert count_rows(db_session, "orders") == 0
    assert count_rows(db_session, "order_items") == 0
    assert count_rows(db_session, "stock_movements") == movements_before


def test_all_short_products_are_reported(client):
    a = create_product(client, sku="A", stock=1)
    b = create_product(client, sku="B", stock=1)
    response = place_order(client, [(a["id"], 2), (b["id"], 3)])
    shortages = response.json()["error"]["details"]["shortages"]
    assert [s["sku"] for s in shortages] == ["A", "B"]


def test_inactive_product_cannot_be_ordered(client, db_session):
    product = create_product(client, stock=5, is_active=False)
    response = place_order(client, [(product["id"], 1)])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PRODUCT_INACTIVE"
    assert quantity_of(db_session, product["id"]) == 5


def test_unknown_product_is_404(client, db_session):
    product = create_product(client, stock=5)
    response = place_order(client, [(product["id"], 1), (999, 1)])
    assert response.status_code == 404
    assert response.json()["error"]["details"] == {"product_ids": [999]}
    assert count_rows(db_session, "orders") == 0


def test_duplicate_product_lines_are_rejected(client):
    product = create_product(client, stock=5)
    response = place_order(client, [(product["id"], 1), (product["id"], 2)])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "DUPLICATE_ORDER_ITEM"


def test_empty_order_is_a_validation_error(client):
    assert client.post("/orders", json={"items": []}).status_code == 422


def test_price_change_after_ordering_does_not_alter_history(client):
    product = create_product(client, price="10.00", stock=5)
    order = place_order(client, [(product["id"], 2)]).json()

    client.patch(f"/products/{product['id']}", json={"price": "99.00"})

    stored = client.get(f"/orders/{order['id']}").json()
    assert stored["total_amount"] == "20.00"
    assert stored["items"][0]["unit_price"] == "10.00"
    assert place_order(client, [(product["id"], 1)]).json()["total_amount"] == "99.00"


def test_get_and_list_orders(client):
    product = create_product(client, stock=10)
    first = place_order(client, [(product["id"], 1)]).json()
    second = place_order(client, [(product["id"], 1)]).json()
    client.post(f"/orders/{first['id']}/cancel")

    listing = client.get("/orders").json()
    assert [o["id"] for o in listing["items"]] == [second["id"], first["id"]]
    confirmed = client.get("/orders", params={"status": "CONFIRMED"}).json()
    assert [o["id"] for o in confirmed["items"]] == [second["id"]]
    assert client.get(f"/orders/{first['id']}").json()["status"] == "CANCELLED"
    assert client.get("/orders/999").status_code == 404
