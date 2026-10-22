from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class MovementType(StrEnum):
    RESTOCK = "RESTOCK"
    ADJUSTMENT = "ADJUSTMENT"
    PURCHASE = "PURCHASE"
    CANCELLATION = "CANCELLATION"


class StockMovement(Base):
    """Append-only ledger row. A database trigger rejects UPDATE and DELETE."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("change_quantity <> 0", name="change_quantity_non_zero"),
        CheckConstraint("resulting_quantity >= 0", name="resulting_quantity_non_negative"),
        CheckConstraint(
            "movement_type IN ('RESTOCK', 'ADJUSTMENT', 'PURCHASE', 'CANCELLATION')",
            name="movement_type_valid",
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    change_quantity: Mapped[int]
    movement_type: Mapped[str] = mapped_column(String(20))
    resulting_quantity: Mapped[int]
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    product: Mapped["Product"] = relationship(lazy="joined")

    @property
    def product_sku(self) -> str:
        return self.product.sku

    @property
    def product_name(self) -> str:
        return self.product.name
