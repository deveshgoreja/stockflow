import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.database.connection import violated_constraint
from app.models import Inventory, MovementType, Order, OrderItem, OrderStatus, Product
from app.models.order import IDEMPOTENCY_KEY_UNIQUE_CONSTRAINT
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services import inventory_service

CENT = Decimal("0.01")


def ensure_unique_products(items: Sequence[OrderItemCreate]) -> None:
    counts = Counter(item.product_id for item in items)
    duplicates = sorted(product_id for product_id, count in counts.items() if count > 1)
    if duplicates:
        raise BusinessRuleError(
            "Each product may appear only once per order; combine the quantities instead",
            code="DUPLICATE_ORDER_ITEM",
            details={"product_ids": duplicates},
        )


def compute_order_total(lines: Iterable[tuple[Decimal, int]]) -> Decimal:
    """Sum of unit_price * quantity, kept in Decimal so cents never drift."""
    total = sum((unit_price * quantity for unit_price, quantity in lines), Decimal("0"))
    return total.quantize(CENT)


def compute_request_hash(payload: OrderCreate) -> str:
    """Hash of the canonical request body used to detect idempotency-key reuse.

    Items are sorted by product_id so the same basket listed in a different
    order is treated as the same request.
    """
    items = sorted(
        ({"product_id": i.product_id, "quantity": i.quantity} for i in payload.items),
        key=lambda item: item["product_id"],
    )
    canonical = json.dumps({"items": items}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_order(
    session: Session, payload: OrderCreate, idempotency_key: str | None
) -> tuple[Order, bool]:
    """Place an order. Returns (order, created); created is False on an idempotent replay."""
    ensure_unique_products(payload.items)
    request_hash = compute_request_hash(payload)

    if idempotency_key is not None:
        existing = _find_order_by_idempotency_key(session, idempotency_key)
        if existing is not None:
            return _replay(existing, request_hash), False

    try:
        with session.begin():
            order = _place_order(session, payload, idempotency_key, request_hash)
    except IntegrityError as exc:
        # A concurrent request with the same key committed first. The unique
        # constraint made us wait for it and then fail; our transaction has been
        # rolled back, so answer with the order the winner created.
        if idempotency_key is None or violated_constraint(exc) != IDEMPOTENCY_KEY_UNIQUE_CONSTRAINT:
            raise
        existing = _find_order_by_idempotency_key(session, idempotency_key)
        if existing is None:
            raise
        return _replay(existing, request_hash), False
    return order, True


def cancel_order(session: Session, order_id: int) -> Order:
    with session.begin():
        # The order row lock serialises concurrent cancellations: the second
        # request blocks here and, once the first commits, re-reads the row and
        # sees CANCELLED. Stock is therefore restored exactly once.
        order = session.scalars(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        if order is None:
            raise _order_not_found(order_id)
        if order.status == OrderStatus.CANCELLED:
            raise ConflictError(
                f"Order {order_id} is already cancelled",
                code="ORDER_ALREADY_CANCELLED",
                details={"order_id": order_id},
            )
        inventory = inventory_service.lock_inventory_rows(
            session, (i.product_id for i in order.items)
        )
        for item in sorted(order.items, key=lambda i: i.product_id):
            inventory_service.apply_stock_change(
                session,
                inventory[item.product_id],
                item.quantity,
                MovementType.CANCELLATION,
                order_id=order.id,
            )
        order.status = OrderStatus.CANCELLED
    return order


def get_order(session: Session, order_id: int) -> Order:
    with session.begin():
        order = session.get(Order, order_id)
        if order is None:
            raise _order_not_found(order_id)
        return order


def list_orders(
    session: Session, *, status: OrderStatus | None, limit: int, offset: int
) -> tuple[list[Order], int]:
    conditions = [Order.status == status] if status is not None else []
    with session.begin():
        total = session.scalar(select(func.count(Order.id)).where(*conditions)) or 0
        orders = session.scalars(
            select(Order).where(*conditions).order_by(Order.id.desc()).limit(limit).offset(offset)
        ).all()
    return list(orders), total


def _place_order(
    session: Session, payload: OrderCreate, idempotency_key: str | None, request_hash: str
) -> Order:
    items = sorted(payload.items, key=lambda item: item.product_id)
    products = _load_orderable_products(session, [item.product_id for item in items])

    # Prices are captured now; later price edits never change this order.
    order = Order(
        status=OrderStatus.CONFIRMED,
        total_amount=compute_order_total((products[i.product_id].price, i.quantity) for i in items),
        idempotency_key=idempotency_key,
        request_hash=request_hash if idempotency_key is not None else None,
    )
    session.add(order)
    # Inserting the order first claims the idempotency key before any stock is
    # touched: a concurrent duplicate blocks on the unique index here, while it
    # holds no inventory locks, and fails once the first request commits.
    session.flush()

    inventory = inventory_service.lock_inventory_rows(session, products)
    _ensure_sufficient_stock(items, inventory)

    for item in items:
        product = products[item.product_id]
        order.items.append(
            OrderItem(product=product, quantity=item.quantity, unit_price=product.price)
        )
    session.flush()
    _deduct_stock(session, order, items, inventory)
    return order


def _load_orderable_products(session: Session, product_ids: list[int]) -> dict[int, Product]:
    products = {
        p.id: p for p in session.scalars(select(Product).where(Product.id.in_(product_ids)))
    }
    missing = [pid for pid in product_ids if pid not in products]
    if missing:
        raise NotFoundError(
            "One or more products do not exist",
            code="PRODUCT_NOT_FOUND",
            details={"product_ids": missing},
        )
    inactive = [pid for pid in product_ids if not products[pid].is_active]
    if inactive:
        raise BusinessRuleError(
            "Inactive products cannot be ordered",
            code="PRODUCT_INACTIVE",
            details={"product_ids": inactive},
        )
    return products


def _ensure_sufficient_stock(
    items: Sequence[OrderItemCreate], inventory: dict[int, Inventory]
) -> None:
    """Check every line against the locked rows so the error names all shortages at once."""
    shortages = [
        {
            "product_id": item.product_id,
            "sku": inventory[item.product_id].product.sku,
            "requested": item.quantity,
            "available": inventory[item.product_id].quantity,
        }
        for item in items
        if inventory[item.product_id].quantity < item.quantity
    ]
    if shortages:
        skus = ", ".join(s["sku"] for s in shortages)
        raise ConflictError(
            f"Insufficient stock for: {skus}",
            code="INSUFFICIENT_STOCK",
            details={"shortages": shortages},
        )


def _deduct_stock(
    session: Session,
    order: Order,
    items: Sequence[OrderItemCreate],
    inventory: dict[int, Inventory],
) -> None:
    for item in items:
        inventory_service.apply_stock_change(
            session,
            inventory[item.product_id],
            -item.quantity,
            MovementType.PURCHASE,
            order_id=order.id,
        )


def _find_order_by_idempotency_key(session: Session, key: str) -> Order | None:
    with session.begin():
        return session.scalars(select(Order).where(Order.idempotency_key == key)).one_or_none()


def _replay(order: Order, request_hash: str) -> Order:
    if order.request_hash != request_hash:
        raise ConflictError(
            "Idempotency-Key was already used with a different request body",
            code="IDEMPOTENCY_KEY_REUSED",
            details={"order_id": order.id},
        )
    return order


def _order_not_found(order_id: int) -> NotFoundError:
    return NotFoundError(
        f"Order {order_id} not found",
        code="ORDER_NOT_FOUND",
        details={"order_id": order_id},
    )
