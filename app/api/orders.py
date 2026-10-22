from typing import Annotated

from fastapi import APIRouter, Header, Query, Response

from app.database.connection import SessionDep
from app.models import Order, OrderStatus
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.order import OrderCreate, OrderRead
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"], responses=ERROR_RESPONSES)


@router.post(
    "",
    response_model=OrderRead,
    status_code=201,
    responses={200: {"model": OrderRead, "description": "Idempotent replay of an existing order"}},
)
def create_order(
    payload: OrderCreate,
    response: Response,
    session: SessionDep,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> Order:
    order, created = order_service.create_order(session, payload, idempotency_key)
    if not created:
        response.status_code = 200
    return order


@router.get("", response_model=Page[OrderRead])
def list_orders(
    session: SessionDep,
    status: OrderStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[OrderRead]:
    orders, total = order_service.list_orders(session, status=status, limit=limit, offset=offset)
    return Page[OrderRead](items=orders, total=total, limit=limit, offset=offset)


@router.get("/{order_id}", response_model=OrderRead)
def get_order(order_id: int, session: SessionDep) -> Order:
    return order_service.get_order(session, order_id)


@router.post("/{order_id}/cancel", response_model=OrderRead)
def cancel_order(order_id: int, session: SessionDep) -> Order:
    return order_service.cancel_order(session, order_id)
