"""Business settings (Settings page).

  read the settings ......... any signed-in user of the business
  change them ............... settings:manage (OWNER ONLY), written to the Activity Log

Display preferences (start page) are kept in the browser and need no API.
"""
import os
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy.orm import Session

from app.auth.permissions import PERM_SETTINGS_MANAGE, get_current_user, has_permission, require_permission
from app.database import get_db
from app.models import Business, User
from app.services.activity_service import log_activity

router = APIRouter(prefix="/api/settings", tags=["Settings"])

DbSession = Annotated[Session, Depends(get_db)]
SignedInUser = Annotated[User, Depends(get_current_user)]
Owner = Annotated[User, Depends(require_permission(PERM_SETTINGS_MANAGE))]

APP_VERSION = "0.8.0"


class SettingsUpdate(BaseModel):
    """Send only what changes."""

    model_config = ConfigDict(extra="forbid")

    business_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)] | None = None
    auto_draft_orders: bool | None = None

    @model_validator(mode="after")
    def not_empty(self):
        if not self.model_fields_set:
            raise ValueError("Nothing to change")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be empty")
        return self


class SettingsOut(BaseModel):
    business_id: int
    business_name: str
    auto_draft_orders: bool            # this business's choice
    auto_draft_server_enabled: bool    # AUTO_GENERATE_PO in .env (if false, nothing is drafted automatically)
    can_edit: bool
    app_version: str
    simulated_integration: bool


def _settings(db: Session, user: User) -> dict:
    business = db.get(Business, user.business_id)
    return {
        "business_id": business.id,
        "business_name": business.name,
        "auto_draft_orders": business.auto_draft_orders is not False,  # NULL = on
        "auto_draft_server_enabled": os.getenv("AUTO_GENERATE_PO", "true").lower() == "true",
        "can_edit": has_permission(user, PERM_SETTINGS_MANAGE),
        "app_version": APP_VERSION,
        "simulated_integration": True,
    }


@router.get("", response_model=SettingsOut)
def get_settings(db: DbSession, user: SignedInUser):
    return _settings(db, user)


@router.patch("", response_model=SettingsOut)
def update_settings(data: SettingsUpdate, db: DbSession, user: Owner):
    business = db.get(Business, user.business_id)
    old = {"business_name": business.name, "auto_draft_orders": business.auto_draft_orders is not False}
    if data.business_name is not None:
        business.name = data.business_name
    if data.auto_draft_orders is not None:
        business.auto_draft_orders = data.auto_draft_orders
    new = {"business_name": business.name, "auto_draft_orders": business.auto_draft_orders is not False}
    changed = [key for key in new if new[key] != old[key]]
    if not changed:
        db.rollback()
        return _settings(db, user)

    labels = {
        "business_name": f"name '{old['business_name']}' -> '{new['business_name']}'",
        "auto_draft_orders": f"automatic order drafts {'on' if new['auto_draft_orders'] else 'off'}",
    }
    log_activity(
        db, user, "business.updated", "business", business.id,
        "Changed business settings: " + ", ".join(labels[key] for key in changed),
        old_value={key: old[key] for key in changed},
        new_value={key: new[key] for key in changed},
    )
    db.commit()
    return _settings(db, user)
