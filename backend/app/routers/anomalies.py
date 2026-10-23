"""AI anomaly flags (Feature 9): list them and let a person review them.

The AI never changes stock. A flag is a POTENTIAL anomaly; a person reviews it, and the
review is written to the activity log.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from app.auth.permissions import PERM_ANOMALIES_REVIEW, PERM_ANOMALIES_VIEW, require_permission
from app.database import get_db
from app.models import User
from app.schemas.anomaly import AnomalyFlagOut, AnomalyReview
from app.services import anomaly_service as service
from app.services.anomaly_service import AnomalyError

router = APIRouter(prefix="/api/anomalies", tags=["AI anomalies"])

DbSession = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission(PERM_ANOMALIES_VIEW))]
Reviewer = Annotated[User, Depends(require_permission(PERM_ANOMALIES_REVIEW))]


@router.get("", response_model=list[AnomalyFlagOut])
def list_anomalies(
    db: DbSession,
    user: Viewer,
    state: Literal["open", "reviewed", "all"] = "open",
    results: Literal["flags", "all"] = "flags",
):
    """Default: flags that still need a review. results=all also shows Normal checks
    (useful to prove the AI ran)."""
    return service.list_flags(db, user.business_id, state, results)


@router.get("/status")
def ai_status(user: Viewer):
    """Lets the dashboard show 'AI unavailable' instead of an empty card."""
    return {"ai_configured": service.ai_configured()}


@router.post("/{flag_id}/review", response_model=AnomalyFlagOut)
def review_anomaly(flag_id: int, data: AnomalyReview, db: DbSession, user: Reviewer):
    try:
        return service.review_flag(db, user, flag_id, data.note)
    except AnomalyError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)