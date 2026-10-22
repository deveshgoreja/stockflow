from collections.abc import Iterable

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import Session, contains_eager

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.models import Inventory, MovementType, Product, StockMovement
from app.schemas.inventory import InventoryAdjustmentCreate

MANUAL_MOVEMENT_TYPES = {MovementType.RESTOCK, MovementType.ADJUSTMENT}


def validate_adjustment(movement_type: MovementType, change_quantity: int) -> None:
    """PURCHASE and CANCELLATION are produced only by the order workflow."""
    if movement_type not in MANUAL_MOVEMENT_TYPES:
        raise BusinessRuleError(
            f"{movement_type} movements are created by orders, not manual adjustments",
            code="INVALID_MOVEMENT_TYPE",
            details={"movement_type": movement_type},
        )
    if movement_type == MovementType.RESTOCK and change_quantity <= 0:
        raise BusinessRuleError(
            "A RESTOCK must increase stock; use ADJUSTMENT for decreases",
            code="INVALID_ADJUSTMENT",
            details={"change_quantity": change_quantity},
        )


def lock_inventory_rows(session: Session, product_ids: Iterable[int]) -> dict[int, Inventory]:
    """Take row locks on the inventory of the given products.

    Every writer in the system locks inventory through this function, so all of
    them acquire locks in ascending product_id order. A consistent global lock
    order makes a wait-for cycle (deadlock) between two transactions impossible.
    PostgreSQL locks rows as they leave the sort, so ORDER BY fixes the order.

    populate_existing refreshes any Inventory already in the session so we act
    on the quantity read *after* the lock was granted, never a stale copy.
    """
    stmt = (
        select(Inventory)
        .where(Inventory.product_id.in_(sorted(set(product_ids))))
        .order_by(Inventory.product_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {row.product_id: row for row in session.scalars(stmt)}


def apply_stock_change(
    session: Session,
    inventory: Inventory,
    change: int,
    movement_type: MovementType,
    *,
    order_id: int | None = None,
    note: str | None = None,
) -> StockMovement:
    """Change a *locked* inventory row and record the movement in the same transaction."""
    new_quantity = inventory.quantity + change
    if new_quantity < 0:
        raise ConflictError(
            f"Insufficient stock for product {inventory.product_id}",
            code="INSUFFICIENT_STOCK",
            details={
                "shortages": [
                    {
                        "product_id": inventory.product_id,
                        "requested": -change,
                        "available": inventory.quantity,
                    }
                ]
            },
        )
    inventory.quantity = new_quantity
    movement = StockMovement(
        product=inventory.product,
        order_id=order_id,
        change_quantity=change,
        movement_type=movement_type,
        resulting_quantity=new_quantity,
        note=note,
    )
    session.add(movement)
    session.flush()
    return movement


def adjust_inventory(session: Session, data: InventoryAdjustmentCreate) -> StockMovement:
    validate_adjustment(data.movement_type, data.change_quantity)
    with session.begin():
        inventory = lock_inventory_rows(session, [data.product_id]).get(data.product_id)
        if inventory is None:
            raise _product_not_found(data.product_id)
        return apply_stock_change(
            session, inventory, data.change_quantity, data.movement_type, note=data.note
        )


def get_inventory(session: Session, product_id: int) -> Inventory:
    with session.begin():
        inventory = session.scalars(
            _inventory_query().where(Inventory.product_id == product_id)
        ).one_or_none()
        if inventory is None:
            raise _product_not_found(product_id)
        return inventory


def list_inventory(
    session: Session, *, low_stock: bool, limit: int, offset: int
) -> tuple[list[Inventory], int]:
    conditions: list[ColumnElement[bool]] = []
    if low_stock:
        # Inactive products are not sellable, so they do not need restocking alerts.
        conditions = [
            Product.is_active.is_(True),
            Inventory.quantity <= Product.low_stock_threshold,
        ]
    with session.begin():
        total = (
            session.scalar(
                select(func.count(Inventory.id)).join(Inventory.product).where(*conditions)
            )
            or 0
        )
        rows = session.scalars(
            _inventory_query()
            .where(*conditions)
            .order_by(Inventory.product_id)
            .limit(limit)
            .offset(offset)
        ).all()
    return list(rows), total


def list_movements(
    session: Session, *, product_id: int | None, limit: int, offset: int
) -> tuple[list[StockMovement], int]:
    conditions = [StockMovement.product_id == product_id] if product_id is not None else []
    with session.begin():
        total = session.scalar(select(func.count(StockMovement.id)).where(*conditions)) or 0
        movements = session.scalars(
            select(StockMovement)
            .where(*conditions)
            .order_by(StockMovement.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    return list(movements), total


def _inventory_query() -> Select[tuple[Inventory]]:
    return select(Inventory).join(Inventory.product).options(contains_eager(Inventory.product))


def _product_not_found(product_id: int) -> NotFoundError:
    return NotFoundError(
        f"Product {product_id} not found",
        code="PRODUCT_NOT_FOUND",
        details={"product_id": product_id},
    )
