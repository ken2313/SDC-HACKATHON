"""Shapes for the Activity Logs API (Feature 4)."""
from typing import Any

from pydantic import BaseModel

from app.schemas.inventory import UTCDateTime


class FieldChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class ActivityLogOut(BaseModel):
    id: int
    created_at: UTCDateTime
    user_id: int | None
    user_name: str            # "System" when no person caused the action
    user_role: str | None
    action: str               # raw code, e.g. "po.approved"
    action_label: str         # readable, e.g. "Purchase order approved"
    category: str             # inventory | stock | alert | purchase_order | access | other
    entity_type: str
    entity_id: int | None
    entity_label: str | None  # product name or PO number, when it can be found
    summary: str
    approval_status: str | None  # "approved" | "rejected" | "denied" | None
    old_value: dict | None
    new_value: dict | None
    changes: list[FieldChange]


class ActivityLogPage(BaseModel):
    items: list[ActivityLogOut]
    total: int
    limit: int
    offset: int


class ActivityLogSummary(BaseModel):
    total: int
    last_24_hours: int
    approvals: int
    rejections: int
    blocked_attempts: int


class LogFilterUser(BaseModel):
    id: int
    name: str
    role: str


class LogFilterOptions(BaseModel):
    users: list[LogFilterUser]
    categories: list[dict]   # [{"value": "...", "label": "..."}]
    actions: list[dict]
