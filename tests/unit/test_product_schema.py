from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.product import ProductCreate, ProductUpdate


def make(**overrides):
    data = {"sku": "kb-001", "name": "Keyboard", "price": "49.99"} | overrides
    return ProductCreate(**data)


def test_sku_is_trimmed_and_uppercased():
    assert make(sku="  kb-001 ").sku == "KB-001"


@pytest.mark.parametrize("sku", ["", "kb 001", "-KB", "KB#1", "x" * 65])
def test_invalid_skus_are_rejected(sku):
    with pytest.raises(ValidationError):
        make(sku=sku)


def test_price_is_an_exact_decimal():
    product = make(price=19.99)
    assert product.price == Decimal("19.99")
    assert isinstance(product.price, Decimal)


@pytest.mark.parametrize("price", ["-0.01", "1.999", "12345678901.00"])
def test_invalid_prices_are_rejected(price):
    with pytest.raises(ValidationError):
        make(price=price)


def test_blank_name_is_rejected():
    with pytest.raises(ValidationError):
        make(name="   ")


def test_blank_category_becomes_none():
    assert make(category="  ").category is None


def test_negative_low_stock_threshold_is_rejected():
    with pytest.raises(ValidationError):
        make(low_stock_threshold=-1)


def test_defaults():
    product = make()
    assert product.is_active is True
    assert product.low_stock_threshold == 5


def test_update_tracks_only_provided_fields():
    update = ProductUpdate(price="5.00")
    assert update.model_dump(exclude_unset=True) == {"price": Decimal("5.00")}


@pytest.mark.parametrize("field", ["sku", "name", "price", "is_active", "low_stock_threshold"])
def test_update_rejects_null_for_required_fields(field):
    with pytest.raises(ValidationError):
        ProductUpdate(**{field: None})


def test_update_allows_clearing_optional_fields():
    update = ProductUpdate(description=None, category=None)
    assert update.model_dump(exclude_unset=True) == {"description": None, "category": None}
