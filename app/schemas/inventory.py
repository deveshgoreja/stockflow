from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models import MovementType


class InventoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    sku: str
    name: str
    category: str | None
    is_active: bool
    quantity: int
    low_stock_threshold: int
    is_low_stock: bool
    updated_at: datetime


class InventoryAdjustmentCreate(BaseModel):
    product_id: Annotated[int, Field(gt=0)]
    change_quantity: Annotated[int, Field(ge=-1_000_000, le=1_000_000)]
    movement_type: MovementType
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None

    @field_validator("change_quantity")
    @classmethod
    def reject_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("change_quantity must not be zero")
        return value


class MovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_sku: str
    product_name: str
    order_id: int | None
    change_quantity: int
    movement_type: MovementType
    resulting_quantity: int
    note: str | None
    created_at: datetime
