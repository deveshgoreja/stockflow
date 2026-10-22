from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.errors import BusinessRuleError
from app.schemas.order import OrderCreate
from app.services.order_service import (
    compute_order_total,
    compute_request_hash,
    ensure_unique_products,
)


def order(*items: tuple[int, int]) -> OrderCreate:
    return OrderCreate(items=[{"product_id": pid, "quantity": qty} for pid, qty in items])


def test_total_is_decimal_exact():
    # 0.1 + 0.2 style errors would show up here with floats.
    total = compute_order_total([(Decimal("0.10"), 1), (Decimal("0.20"), 1)])
    assert total == Decimal("0.30")
    assert str(total) == "0.30"


def test_total_multiplies_price_by_quantity():
    total = compute_order_total([(Decimal("19.99"), 3), (Decimal("4.50"), 2)])
    assert total == Decimal("68.97")


def test_total_of_many_cents_does_not_drift():
    assert compute_order_total([(Decimal("0.01"), 1)] * 10_000) == Decimal("100.00")


def test_total_of_no_lines_is_zero():
    assert compute_order_total([]) == Decimal("0.00")


def test_request_hash_ignores_item_order():
    assert compute_request_hash(order((1, 2), (2, 5))) == compute_request_hash(
        order((2, 5), (1, 2))
    )


def test_request_hash_changes_with_quantity():
    assert compute_request_hash(order((1, 2))) != compute_request_hash(order((1, 3)))


def test_request_hash_changes_with_product():
    assert compute_request_hash(order((1, 2))) != compute_request_hash(order((2, 2)))


def test_request_hash_is_stable_sha256_hex():
    digest = compute_request_hash(order((1, 2)))
    assert len(digest) == 64
    assert digest == compute_request_hash(order((1, 2)))


def test_duplicate_products_in_one_order_are_rejected():
    with pytest.raises(BusinessRuleError) as exc_info:
        ensure_unique_products(order((1, 1), (2, 1), (1, 3)).items)
    assert exc_info.value.code == "DUPLICATE_ORDER_ITEM"
    assert exc_info.value.details == {"product_ids": [1]}


def test_distinct_products_are_accepted():
    ensure_unique_products(order((1, 1), (2, 1)).items)


@pytest.mark.parametrize("quantity", [0, -1, 10_001])
def test_item_quantity_bounds(quantity):
    with pytest.raises(ValidationError):
        order((1, quantity))


def test_order_needs_at_least_one_item():
    with pytest.raises(ValidationError):
        OrderCreate(items=[])
