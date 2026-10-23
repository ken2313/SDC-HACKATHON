"""SIMULATED Orbyte integration layer (mock) - NOT a real Orbyte connection.

We do not have Orbyte API access, so this module simulates what our inventory
module needs from Orbyte:
  1. business workspace lookup (multi-business -> reusable by different SMEs)
  2. user identity and role
  3. permission checks (the backend must call these; never trust the frontend)
  4. reporting completed actions back to Orbyte (an activity feed)
Every result is labelled source="orbyte-simulated". If Orbyte exposes a real
API later, only this file needs replacing; callers stay the same.
All names and businesses are synthetic.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone

SOURCE = "orbyte-simulated"

BUSINESSES = {
    "BIZ-CAFE-001": {"name": "Kopi Kita Cafe (synthetic)", "type": "cafe"},
    "BIZ-MART-002": {"name": "Kedai Runcit Maju (synthetic)", "type": "mini-mart"},
}

USERS = {
    "u-owner-1": {"name": "Aisha (Owner)", "role": "owner", "business_id": "BIZ-CAFE-001"},
    "u-mgr-1": {"name": "Daniel (Manager)", "role": "manager", "business_id": "BIZ-CAFE-001"},
    "u-emp-1": {"name": "Ravi (Employee)", "role": "employee", "business_id": "BIZ-CAFE-001"},
    "u-owner-2": {"name": "Mei Ling (Owner)", "role": "owner", "business_id": "BIZ-MART-002"},
}

ROLE_PERMISSIONS = {
    "owner": {"inventory.view", "inventory.record_movement", "po.create_draft",
              "po.approve", "po.reject", "supplier.manage", "delivery.confirm",
              "anomaly.review", "dashboard.view", "activity_log.view"},
    "manager": {"inventory.view", "inventory.record_movement", "po.create_draft",
                "supplier.manage", "delivery.confirm", "anomaly.review",
                "dashboard.view", "activity_log.view"},
    "employee": {"inventory.view", "inventory.record_movement", "delivery.confirm",
                 "anomaly.review", "dashboard.view"},
}

_LOCK = threading.Lock()


class PermissionDenied(Exception):
    pass


def _log_path():
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "data", "orbyte_actions.jsonl")
    return os.environ.get("ORBYTE_MOCK_LOG", default)


def get_business(business_id):
    b = BUSINESSES.get(business_id)
    if b is None:
        return None
    return {"business_id": business_id, **b, "source": SOURCE}


def get_user_context(user_id):
    u = USERS.get(user_id)
    if u is None:
        return None
    return {"user_id": user_id, **u,
            "permissions": sorted(ROLE_PERMISSIONS.get(u["role"], set())),
            "source": SOURCE}


def has_permission(user_id, business_id, action):
    u = USERS.get(user_id)
    if u is None or u["business_id"] != business_id:
        return False  # unknown user, or user from a different business
    return action in ROLE_PERMISSIONS.get(u["role"], set())


def require_permission(user_id, business_id, action):
    if not has_permission(user_id, business_id, action):
        raise PermissionDenied(f"{user_id} may not '{action}' in {business_id}")


def log_completed_action(business_id, user_id, action, details=None, request_id=None):
    """Report a completed action to (simulated) Orbyte. Never raises.
    The same request_id is only logged once, so retries can't create duplicates."""
    request_id = request_id or str(uuid.uuid4())
    if business_id not in BUSINESSES or user_id not in USERS:
        return {"logged": False, "reason": "unknown business or user",
                "request_id": request_id, "source": SOURCE}
    entry = {"request_id": request_id, "business_id": business_id,
             "user_id": user_id, "role": USERS[user_id]["role"], "action": action,
             "details": details or {},
             "timestamp": datetime.now(timezone.utc).isoformat(), "source": SOURCE}
    path = _log_path()
    try:
        with _LOCK:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        try:
                            if json.loads(line).get("request_id") == request_id:
                                return {"logged": False, "reason": "duplicate request_id",
                                        "request_id": request_id, "source": SOURCE}
                        except ValueError:
                            continue
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
    except OSError as e:
        return {"logged": False, "reason": f"log write failed: {e}",
                "request_id": request_id, "source": SOURCE}
    return {"logged": True, **entry}


def get_actions(business_id):
    """Read the simulated Orbyte activity feed for one business."""
    path = _log_path()
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("business_id") == business_id:
                out.append(e)
    return out


if __name__ == "__main__":
    cafe = "BIZ-CAFE-001"
    print("Business:", get_business(cafe))
    print("Employee records milk OUT:", has_permission("u-emp-1", cafe, "inventory.record_movement"))
    print("Employee approves PO:     ", has_permission("u-emp-1", cafe, "po.approve"))
    print("Owner approves PO:        ", has_permission("u-owner-1", cafe, "po.approve"))
    print("Other shop's owner -> cafe:", has_permission("u-owner-2", cafe, "po.approve"))
    rid = f"demo-{uuid.uuid4()}"
    first = log_completed_action(cafe, "u-owner-1", "po.approve", {"po_id": "PO-001"}, rid)
    again = log_completed_action(cafe, "u-owner-1", "po.approve", {"po_id": "PO-001"}, rid)
    print("Log first time:", first["logged"])
    print("Log same request_id again:", again["logged"], "-", again.get("reason"))