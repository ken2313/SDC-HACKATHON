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

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.constants import ROLE_EMPLOYEE, ROLE_OWNER
from app.database import get_db
from app.models import User
from app.services.activity_service import log_activity

PERM_INVENTORY_VIEW = "inventory:view"
PERM_INVENTORY_MANAGE = "inventory:manage"  # add / edit / archive products, change reorder levels
PERM_STOCK_RECORD = "stock:record"          # add or remove stock
PERM_ALERTS_VIEW = "alerts:view"            # see low-stock alerts (Feature 2)
PERM_ORDERS_VIEW = "orders:view"            # see purchase orders (Feature 3)
PERM_ORDERS_PREPARE = "orders:prepare"      # generate and edit order drafts (Feature 3)
PERM_ORDERS_APPROVE = "orders:approve"      # approve / reject orders: OWNER ONLY (Feature 3)
# Added in Feature 4. The ones marked "later" are enforced by the feature that builds the screen.
PERM_LOGS_VIEW = "logs:view"                # read the Activity Logs: OWNER ONLY (Feature 4)
PERM_REPORTS_VIEW = "reports:view"          # money totals on the dashboard: OWNER ONLY (Feature 7)
PERM_SUPPLIERS_VIEW = "suppliers:view"      # see suppliers, contacts, price lists, order history (Feature 6)
PERM_SUPPLIERS_MANAGE = "suppliers:manage"  # add / edit / deactivate suppliers, set prices: OWNER ONLY (Feature 6)
PERM_ORDERS_TRACK = "orders:track"          # update shipping / delay, confirm deliveries (Feature 5)
PERM_ORDERS_PLACE = "orders:place"          # place an approved order with the supplier, cancel: OWNER ONLY (Feature 5)

# One table drives everything: the permission checks, the /api/access/matrix endpoint
# and the "Roles & permissions" panel on the Activity Logs page.
# (permission, area, plain-English description)
PERMISSION_INFO: list[tuple[str, str, str]] = [
    (PERM_INVENTORY_VIEW, "Inventory", "View products and stock history"),
    (PERM_STOCK_RECORD, "Inventory", "Record stock added or removed"),
    (PERM_INVENTORY_MANAGE, "Inventory", "Add, edit, archive products and change reorder levels"),
    (PERM_ALERTS_VIEW, "Alerts", "View low-stock alerts"),
    (PERM_ORDERS_VIEW, "Purchase orders", "View purchase orders"),
    (PERM_ORDERS_PREPARE, "Purchase orders", "Prepare and edit purchase order requests"),
    (PERM_ORDERS_APPROVE, "Purchase orders", "Approve or reject purchase orders"),
    (PERM_ORDERS_TRACK, "Supplier orders", "Update shipping and delay status, confirm deliveries"),
    (PERM_ORDERS_PLACE, "Supplier orders", "Place an approved order with the supplier, cancel an order"),
    (PERM_SUPPLIERS_VIEW, "Suppliers", "View suppliers, contacts, price lists and order history"),
    (PERM_SUPPLIERS_MANAGE, "Suppliers", "Add, edit and deactivate suppliers, set product prices"),
    (PERM_REPORTS_VIEW, "Reports", "See money totals on the dashboard (stock value, orders, spending)"),
    (PERM_LOGS_VIEW, "Audit", "View the Activity Logs"),
]

ROLE_PERMISSIONS: dict[str, set[str]] = {
    # Owner / Admin: everything
    ROLE_OWNER: {permission for permission, _area, _text in PERMISSION_INFO},
    # Employee: can work with stock and prepare orders, can NOT approve, manage or audit
    ROLE_EMPLOYEE: {
        PERM_INVENTORY_VIEW, PERM_STOCK_RECORD, PERM_ALERTS_VIEW,
        PERM_ORDERS_VIEW, PERM_ORDERS_PREPARE, PERM_ORDERS_TRACK, PERM_SUPPLIERS_VIEW,
    },
}


def has_permission(user: User, permission: str) -> bool:
    """For a route that shows MORE to some roles (e.g. money totals on the dashboard)
    instead of refusing the whole request."""
    return permission in ROLE_PERMISSIONS.get(user.role, set())


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


def _record_denied_attempt(db: Session, user: User, permission: str, request: Request) -> None:
    """Write 'access.denied' to the audit log. Best effort: a logging problem must never
    change the answer the caller gets (still 403)."""
    try:
        log_activity(
            db, user, "access.denied", "permission", None,
            f"{user.name} ({user.role}) was blocked: {request.method} {request.url.path}",
            new_value={
                "permission_needed": permission,
                "role": user.role,
                "method": request.method,
                "path": request.url.path,
                "decision": "denied",
            },
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def require_permission(permission: str) -> Callable[..., User]:
    def checker(
        request: Request,
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> User:
        if permission not in ROLE_PERMISSIONS.get(user.role, set()):
            _record_denied_attempt(db, user, permission, request)
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Your role ({user.role}) is not allowed to do this.",
            )
        return user

    return checker
