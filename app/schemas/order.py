from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import OrderStatus


class OrderItemCreate(BaseModel):
    product_id: Annotated[int, Field(gt=0)]
    quantity: Annotated[int, Field(gt=0, le=10_000)]


class OrderCreate(BaseModel):
    items: Annotated[list[OrderItemCreate], Field(min_length=1, max_length=100)]


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    total_amount: Decimal
    idempotency_key: str | None
    items: list[OrderItemRead]
    created_at: datetime
    updated_at: datetime
