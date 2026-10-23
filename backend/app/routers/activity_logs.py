"""Activity Logs (Feature 4). OWNER ONLY, enforced by the backend.

The log is read-only through the API: there is no endpoint to create, edit or delete an entry.
Entries are written by the services that make the change, in the same transaction.
"""
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.permissions import PERM_LOGS_VIEW, require_permission
from app.database import get_db
from app.models import User
from app.schemas.activity import ActivityLogPage, ActivityLogSummary, LogFilterOptions
from app.services import activity_query_service as service

router = APIRouter(prefix="/api/activity-logs", tags=["Activity Logs"])

DbSession = Annotated[Session, Depends(get_db)]
LogViewer = Annotated[User, Depends(require_permission(PERM_LOGS_VIEW))]


@router.get("", response_model=ActivityLogPage)
def list_activity_logs(
    db: DbSession,
    user: LogViewer,
    category: Literal["inventory", "stock", "alert", "purchase_order", "supplier", "settings", "access"] | None = None,
    action: str | None = Query(default=None, max_length=60),
    approval: Literal["approved", "rejected", "denied", "decisions"] | None = None,
    user_id: int | None = None,
    search: str | None = Query(default=None, max_length=100),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return service.list_logs(
        db, user.business_id, category, action, approval, user_id, search, date_from, date_to, limit, offset
    )


# NOTE: fixed paths must be declared before any /{id} route.
@router.get("/summary", response_model=ActivityLogSummary)
def activity_summary(db: DbSession, user: LogViewer):
    return service.get_summary(db, user.business_id)


@router.get("/filters", response_model=LogFilterOptions)
def activity_filter_options(db: DbSession, user: LogViewer):
    return service.get_filter_options(db, user.business_id)
