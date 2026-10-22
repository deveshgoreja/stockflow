import random
from collections import Counter

from app.database.connection import SessionLocal
from tests.helpers import count_rows, create_product, place_order, quantity_of


def test_100_buyers_for_the_last_unit_produce_exactly_one_sale(api, run_concurrently):
    product = create_product(api, stock=1)

    responses = run_concurrently(100, lambda c, _: place_order(c, [(product["id"], 1)]))

    statuses = Counter(r.status_code for r in responses)
    assert statuses == {201: 1, 409: 99}
    assert {r.json()["error"]["code"] for r in responses if r.status_code == 409} == {
        "INSUFFICIENT_STOCK"
    }
    with SessionLocal() as session:
        assert quantity_of(session, product["id"]) == 0
        assert count_rows(session, "orders") == 1
        assert count_rows(session, "order_items") == 1
        assert count_rows(session, "stock_movements", "movement_type = 'PURCHASE'") == 1


def test_contended_stock_is_never_oversold(api, run_concurrently):
    """50 buyers want 2 units each of a product with 25 in stock: exactly 12 succeed."""
    product = create_product(api, stock=25)

    responses = run_concurrently(50, lambda c, _: place_order(c, [(product["id"], 2)]))

    statuses = Counter(r.status_code for r in responses)
    assert statuses == {201: 12, 409: 38}
    with SessionLocal() as session:
        assert quantity_of(session, product["id"]) == 1


def test_overlapping_multi_product_orders_do_not_deadlock(api, run_concurrently):
    """Orders list the same products in different (shuffled/reversed) orders.

    Without a global lock order, transaction A could lock X then wait for Y while
    B holds Y and waits for X; PostgreSQL would abort one with a deadlock error
    (surfacing as a 500). Every order here must succeed.
    """
    products = [create_product(api, stock=1000) for _ in range(5)]
    ids = [p["id"] for p in products]
    rng = random.Random(1234)
    baskets = []
    for index in range(60):
        chosen = rng.sample(ids, k=rng.randint(2, 5))
        if index % 2:
            chosen.reverse()
        baskets.append([(pid, rng.randint(1, 3)) for pid in chosen])

    responses = run_concurrently(60, lambda c, i: place_order(c, baskets[i]))

    assert Counter(r.status_code for r in responses) == {201: 60}
    sold = Counter()
    for basket in baskets:
        for pid, qty in basket:
            sold[pid] += qty
    with SessionLocal() as session:
        for pid in ids:
            assert quantity_of(session, pid) == 1000 - sold[pid]
        assert count_rows(session, "orders") == 60


def test_overlapping_orders_competing_for_scarce_stock(api, run_concurrently):
    """Mixed baskets over scarce stock: some fail, none partially apply, totals reconcile."""
    products = [create_product(api, stock=10) for _ in range(3)]
    ids = [p["id"] for p in products]
    patterns = [
        [(ids[0], 1), (ids[1], 1)],
        [(ids[2], 1), (ids[1], 1), (ids[0], 1)],
        [(ids[1], 2), (ids[2], 1)],
    ]
    baskets = [patterns[i % 3] for i in range(40)]

    responses = run_concurrently(40, lambda c, i: place_order(c, baskets[i]))

    assert set(r.status_code for r in responses) <= {201, 409}
    sold = Counter()
    for basket, response in zip(baskets, responses, strict=True):
        if response.status_code == 201:
            for pid, qty in basket:
                sold[pid] += qty
    with SessionLocal() as session:
        for pid in ids:
            assert quantity_of(session, pid) == 10 - sold[pid]
            assert quantity_of(session, pid) >= 0
        assert count_rows(session, "orders") == sum(r.status_code == 201 for r in responses)
