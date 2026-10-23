"""Inventory dashboard (Feature 7). Read-only.

  overview and trends ............ inventory:view  (Owner, Employee)
  money totals inside overview ... reports:view    (OWNER ONLY; null for others)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.permissions import PERM_INVENTORY_VIEW, PERM_REPORTS_VIEW, has_permission, require_permission
from app.database import get_db
from app.models import User
from app.schemas.dashboard import DashboardOverview, StockTrend
from app.services import dashboard_service as service
from app.services.dashboard_service import DashboardError

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

DbSession = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission(PERM_INVENTORY_VIEW))]


@router.get("", response_model=DashboardOverview)
def dashboard_overview(db: DbSession, user: Viewer):
    """All dashboard numbers in one request. Money totals only for roles with reports:view."""
    return service.get_overview(db, user, can_view_reports=has_permission(user, PERM_REPORTS_VIEW))


@router.get("/trend", response_model=StockTrend)
def stock_trend(
    db: DbSession,
    user: Viewer,
    item_id: int,
    days: int = Query(default=30, ge=7, le=90),
):
    """Stock at the end of each day, plus units added and used, for one product."""
    try:
        return service.get_trend(db, user.business_id, item_id, days)
    except DashboardError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)
