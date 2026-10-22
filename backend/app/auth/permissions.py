"""Simulated login + permission checks, enforced on the BACKEND.

How the simulation works:
  The (simulated) Orbyte host tells us who is using the module by sending the
  header `X-User-Id`. We look that user up, which gives us their business and
  role. There are no passwords: this is a hackathon simulation, NOT real security.
  In a real Orbyte integration this header would be replaced by Orbyte's own
  verified session/token.

Hiding a button in the GUI is not security. Every route that changes data
declares the permission it needs, and this file rejects the request if the
user's role does not have it.
"""
from typing import Annotated, Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.constants import ROLE_EMPLOYEE, ROLE_OWNER
from app.database import get_db
from app.models import User

PERM_INVENTORY_VIEW = "inventory:view"
PERM_INVENTORY_MANAGE = "inventory:manage"  # add / edit / archive products
PERM_STOCK_RECORD = "stock:record"          # add or remove stock
PERM_ALERTS_VIEW = "alerts:view"            # see low-stock alerts (Feature 2)
# Changing a reorder threshold needs PERM_INVENTORY_MANAGE (owner only).

# Feature 4 will extend this table (orders, approvals, logs, reports).
ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_OWNER: {PERM_INVENTORY_VIEW, PERM_INVENTORY_MANAGE, PERM_STOCK_RECORD, PERM_ALERTS_VIEW},
    ROLE_EMPLOYEE: {PERM_INVENTORY_VIEW, PERM_STOCK_RECORD, PERM_ALERTS_VIEW},
}


def permissions_for(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, set()))


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    x_user_id: Annotated[int | None, Header()] = None,
) -> User:
    if x_user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-User-Id header (simulated session).")
    user = db.get(User, x_user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown or inactive user.")
    return user


def require_permission(permission: str) -> Callable[..., User]:
    def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if permission not in ROLE_PERMISSIONS.get(user.role, set()):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Your role ({user.role}) is not allowed to do this.",
            )
        return user

    return checker
