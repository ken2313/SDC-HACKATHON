"""Demand forecasting (Feature 8). Read-only.

  forecasts for all products / one product ... inventory:view (Owner, Employee)

Changing a reorder level after reading a forecast uses the existing owner-only
PATCH /api/inventory/{id} route, so no new permission is needed.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.permissions import PERM_INVENTORY_VIEW, require_permission
from app.database import get_db
from app.models import User
from app.schemas.forecast import ForecastDetail, ForecastList
from app.services import forecast_service as service
from app.services.forecast_service import ForecastError

router = APIRouter(prefix="/api/forecasts", tags=["Demand Forecasting"])

DbSession = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission(PERM_INVENTORY_VIEW))]


@router.get("", response_model=ForecastList)
def list_forecasts(db: DbSession, user: Viewer):
    """Every active product: daily demand forecast, run-out date, order-by date and quantity."""
    return service.list_forecasts(db, user.business_id)


@router.get("/{item_id}", response_model=ForecastDetail)
def get_forecast(item_id: int, db: DbSession, user: Viewer, horizon_days: int = Query(default=14, ge=7, le=60)):
    """One product, with the past 28 days (actual vs predicted) and the next `horizon_days`."""
    try:
        return service.get_forecast(db, user.business_id, item_id, horizon_days)
    except ForecastError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)
