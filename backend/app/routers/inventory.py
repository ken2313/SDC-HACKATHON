from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.permissions import (
    PERM_INVENTORY_MANAGE,
    PERM_INVENTORY_VIEW,
    PERM_STOCK_RECORD,
    require_permission,
)
from app.database import get_db
from app.models import User
from app.schemas.inventory import (
    InventorySummary,
    ItemCreate,
    ItemOut,
    ItemUpdate,
    MovementCreate,
    MovementOut,
    MovementResult,
)
from app.services import inventory_service as service
from app.services.inventory_service import InventoryError

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])

DbSession = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission(PERM_INVENTORY_VIEW))]
Manager = Annotated[User, Depends(require_permission(PERM_INVENTORY_MANAGE))]
StockRecorder = Annotated[User, Depends(require_permission(PERM_STOCK_RECORD))]


def _raise_http(error: InventoryError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


@router.get("", response_model=list[ItemOut])
def list_inventory(
    db: DbSession,
    user: Viewer,
    search: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=60),
    status: Literal["in_stock", "low_stock", "out_of_stock"] | None = None,
    include_archived: bool = False,
    sort_by: Literal["name", "sku", "category", "quantity", "updated_at"] = "name",
    sort_dir: Literal["asc", "desc"] = "asc",
):
    try:
        return service.list_items(
            db, user.business_id, search, category, status, include_archived, sort_by, sort_dir
        )
    except InventoryError as error:
        raise _raise_http(error)


# NOTE: fixed paths like /summary must be declared before /{item_id}.
@router.get("/summary", response_model=InventorySummary)
def inventory_summary(db: DbSession, user: Viewer):
    return service.get_summary(db, user.business_id)


@router.get("/categories", response_model=list[str])
def inventory_categories(db: DbSession, user: Viewer):
    return service.list_categories(db, user.business_id)


@router.post("", response_model=ItemOut, status_code=201)
def create_product(data: ItemCreate, db: DbSession, user: Manager):
    try:
        return service.create_item(db, user, data)
    except InventoryError as error:
        raise _raise_http(error)


@router.get("/{item_id}", response_model=ItemOut)
def get_product(item_id: int, db: DbSession, user: Viewer):
    try:
        return service.get_item(db, user.business_id, item_id)
    except InventoryError as error:
        raise _raise_http(error)


@router.patch("/{item_id}", response_model=ItemOut)
def edit_product(item_id: int, data: ItemUpdate, db: DbSession, user: Manager):
    try:
        return service.update_item(db, user, item_id, data)
    except InventoryError as error:
        raise _raise_http(error)


@router.post("/{item_id}/archive", response_model=ItemOut)
def archive_product(item_id: int, db: DbSession, user: Manager):
    try:
        return service.set_archived(db, user, item_id, archived=True)
    except InventoryError as error:
        raise _raise_http(error)


@router.post("/{item_id}/restore", response_model=ItemOut)
def restore_product(item_id: int, db: DbSession, user: Manager):
    try:
        return service.set_archived(db, user, item_id, archived=False)
    except InventoryError as error:
        raise _raise_http(error)


@router.post("/{item_id}/movements", response_model=MovementResult, status_code=201)
def record_stock_movement(item_id: int, data: MovementCreate, db: DbSession, user: StockRecorder):
    try:
        movement, item, already_applied = service.record_movement(db, user, item_id, data)
    except InventoryError as error:
        raise _raise_http(error)
    movement_user = db.get(User, movement.user_id)
    movement.user_name = movement_user.name if movement_user else None
    return MovementResult(
        movement=MovementOut.model_validate(movement),
        item=ItemOut.model_validate(item),
        already_applied=already_applied,
    )


@router.get("/{item_id}/movements", response_model=list[MovementOut])
def stock_history(item_id: int, db: DbSession, user: Viewer, limit: int = Query(default=50, ge=1, le=200)):
    try:
        return service.list_movements(db, user.business_id, item_id, limit)
    except InventoryError as error:
        raise _raise_http(error)
