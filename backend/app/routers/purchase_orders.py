from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.permissions import (
    PERM_ORDERS_APPROVE,
    PERM_ORDERS_PREPARE,
    PERM_ORDERS_VIEW,
    require_permission,
)
from app.constants import PO_SOURCE_MANUAL
from app.database import get_db
from app.models import User
from app.schemas.purchase_order import (
    GenerateResult,
    OrderOut,
    OrderReject,
    OrderSummary,
    OrderUpdate,
    ReplenishmentNeed,
)
from app.services import purchase_order_service as service
from app.services.purchase_order_service import OrderError

router = APIRouter(prefix="/api/purchase-orders", tags=["Purchase Orders"])

DbSession = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission(PERM_ORDERS_VIEW))]
Preparer = Annotated[User, Depends(require_permission(PERM_ORDERS_PREPARE))]
Approver = Annotated[User, Depends(require_permission(PERM_ORDERS_APPROVE))]  # OWNER ONLY

StatusFilter = Literal[
    "all", "awaiting", "draft", "pending_approval", "approved", "ordered",
    "shipped", "delivered", "delayed", "cancelled", "rejected",
]


def _http(error: OrderError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


# NOTE: fixed paths (/summary, /needs, /generate) must be declared before /{order_id}.

@router.get("", response_model=list[OrderOut])
def list_orders(db: DbSession, user: Viewer, status: StatusFilter = "all"):
    try:
        return service.list_orders(db, user.business_id, status)
    except OrderError as error:
        raise _http(error)


@router.get("/summary", response_model=OrderSummary)
def orders_summary(db: DbSession, user: Viewer):
    return service.get_summary(db, user.business_id)


@router.get("/needs", response_model=list[ReplenishmentNeed])
def replenishment_needs(db: DbSession, user: Viewer):
    """Products that are low, have no order yet, and what the system would recommend."""
    return service.list_needs(db, user.business_id)


@router.post("/generate", response_model=GenerateResult)
def generate_drafts(db: DbSession, user: Preparer):
    """Prepare DRAFT orders for every product that needs restocking. Nothing is placed."""
    try:
        return service.generate_drafts(db, user, PO_SOURCE_MANUAL)
    except OrderError as error:
        raise _http(error)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: DbSession, user: Viewer):
    try:
        return service.get_order(db, user.business_id, order_id)
    except OrderError as error:
        raise _http(error)


@router.patch("/{order_id}", response_model=OrderOut)
def edit_order(order_id: int, data: OrderUpdate, db: DbSession, user: Preparer):
    try:
        return service.update_order(db, user, order_id, data)
    except OrderError as error:
        raise _http(error)


@router.delete("/{order_id}/lines/{line_id}", response_model=OrderOut)
def remove_order_line(order_id: int, line_id: int, db: DbSession, user: Preparer):
    try:
        return service.remove_line(db, user, order_id, line_id)
    except OrderError as error:
        raise _http(error)


@router.post("/{order_id}/approve", response_model=OrderOut)
def approve_order(order_id: int, db: DbSession, user: Approver):
    try:
        return service.approve_order(db, user, order_id)
    except OrderError as error:
        raise _http(error)


@router.post("/{order_id}/reject", response_model=OrderOut)
def reject_order(order_id: int, data: OrderReject, db: DbSession, user: Approver):
    try:
        return service.reject_order(db, user, order_id, data)
    except OrderError as error:
        raise _http(error)
