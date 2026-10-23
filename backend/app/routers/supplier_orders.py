"""Supplier order tracking (Feature 5).

Who may do what (checked by the backend):
  view the orders ........................ orders:view   (Owner, Employee)
  mark shipped / delayed, confirm delivery orders:track  (Owner, Employee)
  place with supplier (simulated), cancel  orders:place  (OWNER ONLY)
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.permissions import (
    PERM_ORDERS_PLACE,
    PERM_ORDERS_TRACK,
    PERM_ORDERS_VIEW,
    require_permission,
)
from app.database import get_db
from app.models import User
from app.schemas.tracking import (
    CancelOrder,
    ReceiveDelivery,
    ReceiveResult,
    StatusUpdate,
    TrackedOrder,
    TrackingSummary,
)
from app.services import order_tracking_service as service
from app.services.order_tracking_service import TrackingError

router = APIRouter(prefix="/api/supplier-orders", tags=["Supplier Orders"])

DbSession = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission(PERM_ORDERS_VIEW))]
Tracker = Annotated[User, Depends(require_permission(PERM_ORDERS_TRACK))]
Placer = Annotated[User, Depends(require_permission(PERM_ORDERS_PLACE))]  # OWNER ONLY


def _http(error: TrackingError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


# NOTE: fixed paths (/summary) must be declared before /{order_id}.

@router.get("", response_model=list[TrackedOrder])
def list_supplier_orders(
    db: DbSession, user: Viewer, view: Literal["active", "overdue", "delivered", "cancelled", "all"] = "active"
):
    try:
        return service.list_orders(db, user.business_id, view)
    except TrackingError as error:
        raise _http(error)


@router.get("/summary", response_model=TrackingSummary)
def tracking_summary(db: DbSession, user: Viewer):
    return service.get_summary(db, user.business_id)


@router.get("/{order_id}", response_model=TrackedOrder)
def get_supplier_order(order_id: int, db: DbSession, user: Viewer):
    try:
        return service.get_order(db, user.business_id, order_id)
    except TrackingError as error:
        raise _http(error)


@router.post("/{order_id}/place", response_model=TrackedOrder)
def place_with_supplier(order_id: int, db: DbSession, user: Placer):
    """SIMULATED: marks the order as placed. No real supplier is contacted."""
    try:
        return service.place_order(db, user, order_id)
    except TrackingError as error:
        raise _http(error)


@router.post("/{order_id}/status", response_model=TrackedOrder)
def update_order_status(order_id: int, data: StatusUpdate, db: DbSession, user: Tracker):
    try:
        return service.update_status(db, user, order_id, data)
    except TrackingError as error:
        raise _http(error)


@router.post("/{order_id}/receive", response_model=ReceiveResult)
def confirm_delivery(order_id: int, data: ReceiveDelivery, db: DbSession, user: Tracker):
    """Confirm what arrived. Updates inventory exactly once."""
    try:
        return service.receive_delivery(db, user, order_id, data)
    except TrackingError as error:
        raise _http(error)


@router.post("/{order_id}/cancel", response_model=TrackedOrder)
def cancel_supplier_order(order_id: int, data: CancelOrder, db: DbSession, user: Placer):
    try:
        return service.cancel_order(db, user, order_id, data)
    except TrackingError as error:
        raise _http(error)
