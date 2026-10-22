from typing import Annotated

from fastapi import APIRouter, Query

from app.database.connection import SessionDep
from app.models import Inventory, StockMovement
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.inventory import InventoryAdjustmentCreate, InventoryRead, MovementRead
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"], responses=ERROR_RESPONSES)


@router.get("", response_model=Page[InventoryRead])
def list_inventory(
    session: SessionDep,
    low_stock: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[InventoryRead]:
    rows, total = inventory_service.list_inventory(
        session, low_stock=low_stock, limit=limit, offset=offset
    )
    return Page[InventoryRead](items=rows, total=total, limit=limit, offset=offset)


# Declared before /{product_id} so "movements" is never parsed as a product id.
@router.get("/movements", response_model=Page[MovementRead])
def list_movements(
    session: SessionDep,
    product_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[MovementRead]:
    movements, total = inventory_service.list_movements(
        session, product_id=product_id, limit=limit, offset=offset
    )
    return Page[MovementRead](items=movements, total=total, limit=limit, offset=offset)


@router.post("/adjustments", response_model=MovementRead, status_code=201)
def create_adjustment(payload: InventoryAdjustmentCreate, session: SessionDep) -> StockMovement:
    return inventory_service.adjust_inventory(session, payload)


@router.get("/{product_id}", response_model=InventoryRead)
def get_inventory(product_id: int, session: SessionDep) -> Inventory:
    return inventory_service.get_inventory(session, product_id)
