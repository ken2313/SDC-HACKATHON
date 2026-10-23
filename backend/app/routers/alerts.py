from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.permissions import PERM_ALERTS_VIEW, require_permission
from app.database import get_db
from app.models import User
from app.schemas.alert import AlertOut, AlertSummary
from app.services import alert_service

router = APIRouter(prefix="/api/alerts", tags=["Stock Alerts"])

DbSession = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission(PERM_ALERTS_VIEW))]


# Alerts are created and resolved automatically when stock changes, so this
# router is read-only. To change a threshold, use PATCH /api/inventory/{id}.

@router.get("", response_model=list[AlertOut])
def list_alerts(db: DbSession, user: Viewer, status: Literal["open", "resolved", "all"] = "open"):
    return alert_service.list_alerts(db, user.business_id, status)


@router.get("/summary", response_model=AlertSummary)
def alerts_summary(db: DbSession, user: Viewer):
    return alert_service.get_alert_summary(db, user.business_id)
