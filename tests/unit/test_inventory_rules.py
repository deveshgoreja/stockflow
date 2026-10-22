import pytest
from pydantic import ValidationError

from app.core.errors import BusinessRuleError
from app.models import MovementType
from app.schemas.inventory import InventoryAdjustmentCreate
from app.services.inventory_service import validate_adjustment


def test_restock_must_be_positive():
    with pytest.raises(BusinessRuleError) as exc_info:
        validate_adjustment(MovementType.RESTOCK, -3)
    assert exc_info.value.code == "INVALID_ADJUSTMENT"


def test_restock_positive_is_allowed():
    validate_adjustment(MovementType.RESTOCK, 10)


@pytest.mark.parametrize("change", [-2, 7])
def test_adjustment_can_go_either_way(change):
    validate_adjustment(MovementType.ADJUSTMENT, change)


@pytest.mark.parametrize("movement_type", [MovementType.PURCHASE, MovementType.CANCELLATION])
def test_order_movement_types_are_reserved(movement_type):
    with pytest.raises(BusinessRuleError) as exc_info:
        validate_adjustment(movement_type, 1)
    assert exc_info.value.code == "INVALID_MOVEMENT_TYPE"


def test_zero_change_is_a_validation_error():
    with pytest.raises(ValidationError):
        InventoryAdjustmentCreate(product_id=1, change_quantity=0, movement_type="ADJUSTMENT")


def test_unknown_movement_type_is_a_validation_error():
    with pytest.raises(ValidationError):
        InventoryAdjustmentCreate(product_id=1, change_quantity=1, movement_type="THEFT")
