from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.permissions import (
    PERM_INVENTORY_MANAGE,
    PERM_INVENTORY_VIEW,
    PERM_STOCK_RECORD,
    require_permission,
)
from app.constants import MOVEMENT_OUT
from app.database import get_db
from app.models import User
from app.schemas.inventory import (
    DraftOrderRef,
    InventorySummary,
    ItemCreate,
    ItemOut,
    ItemUpdate,
    MovementCreate,
    MovementOut,
    MovementResult,
)
from app.services import inventory_service as service
from app.services import purchase_order_service
from app.services.anomaly_service import check_movement_for_anomaly
from app.services.inventory_service import InventoryError

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])

DbSession = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission(PERM_INVENTORY_VIEW))]
Manager = Annotated[User, Depends(require_permission(PERM_INVENTORY_MANAGE))]
StockRecorder = Annotated[User, Depends(require_permission(PERM_STOCK_RECORD))]


def _raise_http(error: InventoryError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


def _prepare_draft_if_low(db: Session, user: User, item) -> dict | None:
    """Feature 3: when a product is low after a change, the system prepares a purchase order
    DRAFT (never an approved order). Best-effort: it can never undo the stock change."""
    if item.is_archived or item.stock_status == "in_stock":
        return None
    return purchase_order_service.auto_draft_for_item(db, user, item.id)


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
        item = service.create_item(db, user, data)
    except InventoryError as error:
        raise _raise_http(error)
    _prepare_draft_if_low(db, user, item)
    return item


@router.get("/{item_id}", response_model=ItemOut)
def get_product(item_id: int, db: DbSession, user: Viewer):
    try:
        return service.get_item(db, user.business_id, item_id)
    except InventoryError as error:
        raise _raise_http(error)


@router.patch("/{item_id}", response_model=ItemOut)
def edit_product(item_id: int, data: ItemUpdate, db: DbSession, user: Manager):
    try:
        item = service.update_item(db, user, item_id, data)
    except InventoryError as error:
        raise _raise_http(error)
    _prepare_draft_if_low(db, user, item)  # a higher reorder level can make a product low
    return item


@router.post("/{item_id}/archive", response_model=ItemOut)
def archive_product(item_id: int, db: DbSession, user: Manager):
    try:
        return service.set_archived(db, user, item_id, archived=True)
    except InventoryError as error:
        raise _raise_http(error)


@router.post("/{item_id}/restore", response_model=ItemOut)
def restore_product(item_id: int, db: DbSession, user: Manager):
    try:
        item = service.set_archived(db, user, item_id, archived=False)
    except InventoryError as error:
        raise _raise_http(error)
    _prepare_draft_if_low(db, user, item)
    return item


@router.post("/{item_id}/movements", response_model=MovementResult, status_code=201)
def record_stock_movement(
    item_id: int,
    data: MovementCreate,
    db: DbSession,
    user: StockRecorder,
    background_tasks: BackgroundTasks,
):
    try:
        movement, item, already_applied = service.record_movement(db, user, item_id, data)
    except InventoryError as error:
        raise _raise_http(error)
    movement_user = db.get(User, movement.user_id)
    movement.user_name = movement_user.name if movement_user else None
    draft = None if already_applied else _prepare_draft_if_low(db, user, item)
    # Feature 9: AI anomaly check runs AFTER the response, so the stock change never
    # waits for (or depends on) the AI. Retries (already_applied) are not re-checked.
    if not already_applied and movement.movement_type == MOVEMENT_OUT:
        background_tasks.add_task(check_movement_for_anomaly, movement.id)
    return MovementResult(
        movement=MovementOut.model_validate(movement),
        item=ItemOut.model_validate(item),
        already_applied=already_applied,
        draft_purchase_order=DraftOrderRef(**draft) if draft else None,
    )


@router.get("/{item_id}/movements", response_model=list[MovementOut])
def stock_history(item_id: int, db: DbSession, user: Viewer, limit: int = Query(default=50, ge=1, le=200)):
    try:
        return service.list_movements(db, user.business_id, item_id, limit)
    except InventoryError as error:
        raise _raise_http(error)