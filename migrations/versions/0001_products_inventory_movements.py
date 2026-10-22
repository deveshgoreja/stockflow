"""products, inventory and stock movements

Revision ID: 0001
Revises:
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_column(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), server_default="5", nullable=False),
        timestamp_column("created_at"),
        timestamp_column("updated_at"),
        sa.CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
        sa.CheckConstraint(
            "low_stock_threshold >= 0", name="ck_products_low_stock_threshold_non_negative"
        ),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_is_active", "products", ["is_active"])

    op.create_table(
        "inventory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", name="fk_inventory_product_id_products"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        timestamp_column("updated_at"),
        sa.CheckConstraint("quantity >= 0", name="ck_inventory_quantity_non_negative"),
        sa.UniqueConstraint("product_id", name="uq_inventory_product_id"),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", name="fk_stock_movements_product_id_products"),
            nullable=False,
        ),
        sa.Column("change_quantity", sa.Integer(), nullable=False),
        sa.Column("movement_type", sa.String(20), nullable=False),
        sa.Column("resulting_quantity", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        timestamp_column("created_at"),
        sa.CheckConstraint(
            "change_quantity <> 0", name="ck_stock_movements_change_quantity_non_zero"
        ),
        sa.CheckConstraint(
            "resulting_quantity >= 0", name="ck_stock_movements_resulting_quantity_non_negative"
        ),
        sa.CheckConstraint(
            "movement_type IN ('RESTOCK', 'ADJUSTMENT', 'PURCHASE', 'CANCELLATION')",
            name="ck_stock_movements_movement_type_valid",
        ),
    )
    op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"])
    op.create_index("ix_stock_movements_created_at", "stock_movements", ["created_at"])

    # The movement ledger is append-only. Enforcing it in the database means no
    # code path (or ad-hoc SQL) can quietly rewrite stock history.
    op.execute(
        """
        CREATE FUNCTION reject_stock_movement_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'stock_movements is append-only (% rejected)', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER stock_movements_append_only
        BEFORE UPDATE OR DELETE ON stock_movements
        FOR EACH ROW EXECUTE FUNCTION reject_stock_movement_change()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER stock_movements_append_only ON stock_movements")
    op.execute("DROP FUNCTION reject_stock_movement_change()")
    op.drop_table("stock_movements")
    op.drop_table("inventory")
    op.drop_table("products")
