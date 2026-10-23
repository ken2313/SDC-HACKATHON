"""SIMULATED Orbyte integration layer.

IMPORTANT: Everything in this file is a MOCK made for the hackathon.
These endpoints are NOT official Orbyte APIs. We do not have access to
Orbyte's real platform. This file shows WHERE and HOW a real integration
would plug in:

  1. Orbyte tells our module which business is calling   (business identification)
  2. Orbyte tells our module who the user is and their role (role information)
  3. Our module applies permissions based on that role     (permission mapping)
  4. Our module can return business info to Orbyte         (information exchange)
  5. Completed actions are written to the activity log     (action recording, see ActivityLogs)

In a real integration, step 1-2 would come from a verified Orbyte token instead
of the plain `X-User-Id` header used here.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import get_current_user, permissions_for
from app.database import get_db
from app.models import Business, User

router = APIRouter(prefix="/api/orbyte-mock", tags=["Orbyte (SIMULATED)"])

DISCLAIMER = (
    "SIMULATED integration for demonstration only. "
    "This is not an official Orbyte API."
)


@router.get("/users")
def list_demo_users(db: Annotated[Session, Depends(get_db)]):
    """Stands in for 'the people who can open this module from inside Orbyte'.
    The frontend uses it to power the demo user switcher."""
    rows = db.execute(
        select(User, Business.name)
        .join(Business, Business.id == User.business_id)
        .where(User.is_active.is_(True))
        .order_by(User.business_id, User.id)
    ).all()
    return {
        "simulated": True,
        "disclaimer": DISCLAIMER,
        "users": [
            {
                "id": user.id,
                "name": user.name,
                "role": user.role,
                "business_id": user.business_id,
                "business_name": business_name,
            }
            for user, business_name in rows
        ],
    }


@router.get("/context")
def get_session_context(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """What Orbyte would hand to our module when it opens: business, user, role."""
    business = db.get(Business, user.business_id)
    return {
        "simulated": True,
        "disclaimer": DISCLAIMER,
        "business": {"id": business.id, "name": business.name},
        "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role},
        "permissions": permissions_for(user.role),
    }
