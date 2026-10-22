from typing import Annotated

from fastapi import APIRouter, Query

from app.database.connection import SessionDep
from app.models import Product
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services import product_service

router = APIRouter(prefix="/products", tags=["products"], responses=ERROR_RESPONSES)


@router.post("", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, session: SessionDep) -> Product:
    return product_service.create_product(session, payload)


@router.get("", response_model=Page[ProductRead])
def list_products(
    session: SessionDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    category: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ProductRead]:
    products, total = product_service.list_products(
        session, search=search, category=category, is_active=is_active, limit=limit, offset=offset
    )
    return Page[ProductRead](items=products, total=total, limit=limit, offset=offset)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, session: SessionDep) -> Product:
    return product_service.get_product(session, product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductUpdate, session: SessionDep) -> Product:
    return product_service.update_product(session, product_id, payload)
