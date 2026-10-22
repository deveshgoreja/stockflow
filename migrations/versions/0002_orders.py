"""orders, order items and the movement -> order link

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('CONFIRMED', 'CANCELLED')", name="ck_orders_status_valid"),
        sa.CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_non_negative"),
        sa.UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
    )
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", name="fk_order_items_order_id_orders"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", name="fk_order_items_product_id_products"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
        # Also serves as the index for order_id lookups (leading column).
        sa.UniqueConstraint("order_id", "product_id", name="uq_order_items_order_id_product_id"),
    )
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"])

    op.add_column("stock_movements", sa.Column("order_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_stock_movements_order_id_orders", "stock_movements", "orders", ["order_id"], ["id"]
    )
    op.create_index("ix_stock_movements_order_id", "stock_movements", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_movements_order_id", table_name="stock_movements")
    op.drop_constraint("fk_stock_movements_order_id_orders", "stock_movements", type_="foreignkey")
    # The append-only trigger only fires on row changes, so dropping a column is allowed.
    op.drop_column("stock_movements", "order_id")
    op.drop_table("order_items")
    op.drop_table("orders")
