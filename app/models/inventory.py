from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class Inventory(Base):
    __tablename__ = "inventory"
    # The CHECK is the last line of defence: even a buggy code path cannot
    # commit negative stock.
    __table_args__ = (CheckConstraint("quantity >= 0", name="quantity_non_negative"),)
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True)
    quantity: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["Product"] = relationship(back_populates="inventory")

    @property
    def sku(self) -> str:
        return self.product.sku

    @property
    def name(self) -> str:
        return self.product.name

    @property
    def category(self) -> str | None:
        return self.product.category

    @property
    def is_active(self) -> bool:
        return self.product.is_active

    @property
    def low_stock_threshold(self) -> int:
        return self.product.low_stock_threshold

    @property
    def is_low_stock(self) -> bool:
        return self.quantity <= self.product.low_stock_threshold
