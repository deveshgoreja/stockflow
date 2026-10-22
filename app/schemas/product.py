from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def _normalize_sku(value: object) -> object:
    # Runs before the pattern check, so "kb-001 " is accepted and stored as "KB-001".
    return value.strip().upper() if isinstance(value, str) else value


Sku = Annotated[
    str,
    BeforeValidator(_normalize_sku),
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Z0-9][A-Z0-9_-]*$"),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Category = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Price = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Threshold = Annotated[int, Field(ge=0, le=1_000_000)]


def _blank_to_none(value: str | None) -> str | None:
    return value or None


class ProductCreate(BaseModel):
    sku: Sku
    name: Name
    description: str | None = None
    price: Price
    category: Category | None = None
    is_active: bool = True
    low_stock_threshold: Threshold = 5

    _normalize_category = field_validator("category")(_blank_to_none)


class ProductUpdate(BaseModel):
    sku: Sku | None = None
    name: Name | None = None
    description: str | None = None
    price: Price | None = None
    category: Category | None = None
    is_active: bool | None = None
    low_stock_threshold: Threshold | None = None

    _normalize_category = field_validator("category")(_blank_to_none)

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> Self:
        required = {"sku", "name", "price", "is_active", "low_stock_threshold"}
        nulled = sorted(f for f in required & self.model_fields_set if getattr(self, f) is None)
        if nulled:
            raise ValueError(f"Fields cannot be null: {', '.join(nulled)}")
        return self


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str | None
    price: Decimal
    category: str | None
    is_active: bool
    low_stock_threshold: int
    quantity: int
    created_at: datetime
    updated_at: datetime
