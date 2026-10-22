from tests.helpers import count_rows, create_product, place_order, quantity_of


def test_replay_with_same_key_and_payload_returns_original_order(client, db_session):
    product = create_product(client, stock=10)

    first = place_order(client, [(product["id"], 3)], idempotency_key="checkout-1")
    replay = place_order(client, [(product["id"], 3)], idempotency_key="checkout-1")

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert count_rows(db_session, "orders") == 1
    assert quantity_of(db_session, product["id"]) == 7


def test_same_basket_in_different_item_order_is_the_same_request(client, db_session):
    a = create_product(client, stock=10)
    b = create_product(client, stock=10)
    first = place_order(client, [(a["id"], 1), (b["id"], 2)], idempotency_key="k")
    replay = place_order(client, [(b["id"], 2), (a["id"], 1)], idempotency_key="k")
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert count_rows(db_session, "orders") == 1


def test_reusing_key_with_different_payload_is_409(client, db_session):
    product = create_product(client, stock=10)
    place_order(client, [(product["id"], 1)], idempotency_key="checkout-2")

    response = place_order(client, [(product["id"], 2)], idempotency_key="checkout-2")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert count_rows(db_session, "orders") == 1
    assert quantity_of(db_session, product["id"]) == 9


def test_replay_still_returns_order_after_cancellation(client):
    product = create_product(client, stock=10)
    order = place_order(client, [(product["id"], 1)], idempotency_key="k-cancel").json()
    client.post(f"/orders/{order['id']}/cancel")
    replay = place_order(client, [(product["id"], 1)], idempotency_key="k-cancel")
    assert replay.status_code == 200
    assert replay.json()["status"] == "CANCELLED"


def test_requests_without_key_are_independent(client, db_session):
    product = create_product(client, stock=10)
    place_order(client, [(product["id"], 1)])
    place_order(client, [(product["id"], 1)])
    assert count_rows(db_session, "orders") == 2


def test_failed_attempt_does_not_consume_the_key(client, db_session):
    product = create_product(client, stock=1)
    assert place_order(client, [(product["id"], 2)], idempotency_key="retry").status_code == 409
    assert place_order(client, [(product["id"], 1)], idempotency_key="retry").status_code == 201
    assert count_rows(db_session, "orders") == 1
