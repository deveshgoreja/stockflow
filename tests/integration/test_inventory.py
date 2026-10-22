import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.helpers import (
    assert_inventory_matches_movements,
    count_rows,
    create_product,
    place_order,
    quantity_of,
)


def adjust(client, product_id, change, movement_type="ADJUSTMENT", note=None):
    return client.post(
        "/inventory/adjustments",
        json={
            "product_id": product_id,
            "change_quantity": change,
            "movement_type": movement_type,
            "note": note,
        },
    )


def test_keyboard_scenario_20_sell_5_receive_10_damage_2_equals_23(client, db_session):
    keyboard = create_product(client, name="Keyboard")
    pid = keyboard["id"]

    assert adjust(client, pid, 20, "RESTOCK", "Initial delivery").status_code == 201
    assert place_order(client, [(pid, 5)]).status_code == 201
    assert adjust(client, pid, 10, "RESTOCK", "Supplier delivery").status_code == 201
    assert adjust(client, pid, -2, "ADJUSTMENT", "Damaged in warehouse").status_code == 201

    assert client.get(f"/inventory/{pid}").json()["quantity"] == 23
    movements = client.get("/inventory/movements", params={"product_id": pid}).json()
    assert movements["total"] == 4
    history = [
        (m["movement_type"], m["change_quantity"], m["resulting_quantity"])
        for m in reversed(movements["items"])
    ]
    assert history == [
        ("RESTOCK", 20, 20),
        ("PURCHASE", -5, 15),
        ("RESTOCK", 10, 25),
        ("ADJUSTMENT", -2, 23),
    ]
    assert_inventory_matches_movements(db_session)


def test_adjustment_returns_the_movement(client):
    product = create_product(client)
    response = adjust(client, product["id"], 7, "RESTOCK", "PO-1")
    assert response.status_code == 201
    body = response.json()
    assert body["product_sku"] == product["sku"]
    assert body["change_quantity"] == 7
    assert body["resulting_quantity"] == 7
    assert body["note"] == "PO-1"
    assert body["order_id"] is None


def test_adjustment_below_zero_is_rejected_and_changes_nothing(client, db_session):
    product = create_product(client, stock=3)
    response = adjust(client, product["id"], -4)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INSUFFICIENT_STOCK"
    assert error["details"]["shortages"][0]["available"] == 3
    assert quantity_of(db_session, product["id"]) == 3
    assert count_rows(db_session, "stock_movements") == 1


def test_negative_restock_is_a_400(client):
    product = create_product(client, stock=3)
    response = adjust(client, product["id"], -1, "RESTOCK")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ADJUSTMENT"


def test_purchase_movement_cannot_be_created_manually(client):
    product = create_product(client, stock=3)
    response = adjust(client, product["id"], -1, "PURCHASE")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_MOVEMENT_TYPE"


def test_adjusting_unknown_product_is_404(client):
    assert adjust(client, 999, 5, "RESTOCK").status_code == 404


def test_inventory_lookup(client):
    product = create_product(client, stock=4, low_stock_threshold=5)
    body = client.get(f"/inventory/{product['id']}").json()
    assert body["quantity"] == 4
    assert body["is_low_stock"] is True
    assert client.get("/inventory/999").status_code == 404


def test_low_stock_listing_only_includes_active_products_at_or_below_threshold(client):
    low = create_product(client, sku="LOW", stock=5, low_stock_threshold=5)
    create_product(client, sku="OK", stock=6, low_stock_threshold=5)
    create_product(client, sku="EMPTY-INACTIVE", stock=0, is_active=False)

    body = client.get("/inventory", params={"low_stock": "true"}).json()
    assert [row["product_id"] for row in body["items"]] == [low["id"]]
    assert body["total"] == 1
    assert client.get("/inventory").json()["total"] == 3


def test_movement_history_filters_and_paginates(client):
    first = create_product(client)
    second = create_product(client)
    for _ in range(3):
        adjust(client, first["id"], 1, "RESTOCK")
    adjust(client, second["id"], 1, "RESTOCK")

    all_movements = client.get("/inventory/movements").json()
    assert all_movements["total"] == 4
    page = client.get(
        "/inventory/movements", params={"product_id": first["id"], "limit": 2, "offset": 1}
    ).json()
    assert page["total"] == 3
    assert [m["resulting_quantity"] for m in page["items"]] == [2, 1]


def test_movements_are_append_only(client, db_session):
    product = create_product(client, stock=5)
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(text("UPDATE stock_movements SET change_quantity = 99"))
    db_session.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(text("DELETE FROM stock_movements"))
    db_session.rollback()
    assert count_rows(db_session, "stock_movements", "product_id = :pid", pid=product["id"]) == 1


def test_negative_stock_is_blocked_by_the_database_itself(client, db_session):
    product = create_product(client, stock=1)
    with pytest.raises(DBAPIError, match="ck_inventory_quantity_non_negative"):
        db_session.execute(
            text("UPDATE inventory SET quantity = -1 WHERE product_id = :pid"),
            {"pid": product["id"]},
        )
    db_session.rollback()
