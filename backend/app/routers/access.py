"""Who may do what (Feature 4). Any signed-in user may read the rules, so the screens can
explain why a button is missing. The rules themselves are enforced in auth/permissions.py."""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.permissions import PERMISSION_INFO, ROLE_PERMISSIONS, get_current_user
from app.constants import ROLE_EMPLOYEE, ROLE_OWNER
from app.models import User

router = APIRouter(prefix="/api/access", tags=["Access control"])

ROLE_LABELS = {ROLE_OWNER: "Owner / Admin", ROLE_EMPLOYEE: "Employee"}


@router.get("/matrix")
def permission_matrix(user: Annotated[User, Depends(get_current_user)]):
    return {
        "simulated": True,
        "note": "Roles are simulated (no passwords). The backend checks them on every request.",
        "your_role": user.role,
        "roles": [{"role": role, "label": ROLE_LABELS[role]} for role in (ROLE_OWNER, ROLE_EMPLOYEE)],
        "permissions": [
            {
                "key": key,
                "area": area,
                "description": text,
                "allowed": {role: key in ROLE_PERMISSIONS[role] for role in (ROLE_OWNER, ROLE_EMPLOYEE)},
            }
            for key, area, text in PERMISSION_INFO
        ],
    }
