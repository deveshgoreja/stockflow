from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.database.connection import violated_constraint
from app.models import Inventory, Product
from app.models.product import SKU_UNIQUE_CONSTRAINT
from app.schemas.product import ProductCreate, ProductUpdate


def create_product(session: Session, data: ProductCreate) -> Product:
    # The inventory row is created alongside the product so every product
    # always has exactly one row to lock when stock changes.
    product = Product(**data.model_dump(), inventory=Inventory(quantity=0))
    try:
        with session.begin():
            session.add(product)
    except IntegrityError as exc:
        _raise_if_duplicate_sku(exc, data.sku)
        raise
    return product


def get_product(session: Session, product_id: int) -> Product:
    with session.begin():
        return _get_product_or_404(session, product_id)


def update_product(session: Session, product_id: int, data: ProductUpdate) -> Product:
    changes = data.model_dump(exclude_unset=True)
    try:
        with session.begin():
            product = _get_product_or_404(session, product_id)
            for field, value in changes.items():
                setattr(product, field, value)
    except IntegrityError as exc:
        _raise_if_duplicate_sku(exc, changes.get("sku", ""))
        raise
    return product


def list_products(
    session: Session,
    *,
    search: str | None,
    category: str | None,
    is_active: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[Product], int]:
    conditions = _product_filters(search, category, is_active)
    with session.begin():
        total = session.scalar(select(func.count(Product.id)).where(*conditions)) or 0
        products = session.scalars(
            select(Product).where(*conditions).order_by(Product.id).limit(limit).offset(offset)
        ).all()
    return list(products), total


def _product_filters(
    search: str | None, category: str | None, is_active: bool | None
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        conditions.append(
            or_(Product.name.ilike(pattern, escape="\\"), Product.sku.ilike(pattern, escape="\\"))
        )
    if category:
        conditions.append(Product.category == category)
    if is_active is not None:
        conditions.append(Product.is_active.is_(is_active))
    return conditions


def _get_product_or_404(session: Session, product_id: int) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError(
            f"Product {product_id} not found",
            code="PRODUCT_NOT_FOUND",
            details={"product_id": product_id},
        )
    return product


def _raise_if_duplicate_sku(exc: IntegrityError, sku: str) -> None:
    if violated_constraint(exc) == SKU_UNIQUE_CONSTRAINT:
        raise ConflictError(
            f"A product with SKU '{sku}' already exists",
            code="DUPLICATE_SKU",
            details={"sku": sku},
        ) from exc
