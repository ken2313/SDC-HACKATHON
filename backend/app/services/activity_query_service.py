"""Reading the audit log (Feature 4). Writing it is done by activity_service.log_activity.

Everything here is limited to ONE business: a user can never read another business's log.
The log is append-only: this module has no update or delete function on purpose.
"""
import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import ActivityLog, InventoryItem, PurchaseOrder, StockAlert, Supplier, User

# action code -> readable label. Unknown codes fall back to the code itself.
ACTION_LABELS = {
    "item.created": "Product added",
    "item.updated": "Product edited",
    "item.archived": "Product archived",
    "item.restored": "Product restored",
    "stock.in": "Stock added",
    "stock.out": "Stock removed",
    "alert.opened": "Low-stock alert opened",
    "alert.resolved": "Low-stock alert resolved",
    "po.generated": "Purchase order draft prepared",
    "po.updated": "Purchase order edited",
    "po.line_removed": "Product removed from order",
    "po.approved": "Purchase order approved",
    "po.rejected": "Purchase order rejected",
    "po.placed": "Order placed with supplier (simulated)",
    "po.shipped": "Order marked shipped",
    "po.delayed": "Order marked delayed",
    "po.delivered": "Delivery confirmed",
    "po.cancelled": "Order cancelled",
    "supplier.created": "Supplier added",
    "supplier.updated": "Supplier edited",
    "supplier.deactivated": "Supplier deactivated",
    "supplier.activated": "Supplier re-activated",
    "supplier.product_added": "Product added to price list",
    "supplier.price_changed": "Supplier price changed",
    "supplier.product_removed": "Product removed from price list",
    "business.updated": "Business settings changed",
    "access.denied": "Action blocked (no permission)",
}

# category value -> (label, action prefix)
CATEGORIES = {
    "inventory": ("Products", "item."),
    "stock": ("Stock movements", "stock."),
    "alert": ("Stock alerts", "alert."),
    "purchase_order": ("Purchase orders", "po."),
    "supplier": ("Suppliers", "supplier."),
    "settings": ("Settings", "business."),
    "access": ("Blocked attempts", "access."),
}

APPROVAL_FILTERS = {
    "approved": ["po.approved"],
    "rejected": ["po.rejected"],
    "denied": ["access.denied"],
    "decisions": ["po.approved", "po.rejected"],
}


def category_for(action: str) -> str:
    for value, (_label, prefix) in CATEGORIES.items():
        if action.startswith(prefix):
            return value
    return "other"


def approval_status_for(action: str) -> str | None:
    """The approval / rejection status shown in the log. Derived from the action code, so
    it can never disagree with what was actually decided."""
    return {"po.approved": "approved", "po.rejected": "rejected", "access.denied": "denied"}.get(action)


def _parse(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else {"value": value}


def _changes(old: dict | None, new: dict | None) -> list[dict]:
    """Field-by-field before/after list for the detail view. Fields that did not change
    are left out (when both sides have the field)."""
    old, new = old or {}, new or {}
    rows = []
    for key in list(old) + [key for key in new if key not in old]:
        before, after = old.get(key), new.get(key)
        if key in old and key in new and before == after:
            continue
        rows.append({"field": key, "old": before, "new": after})
    return rows


def _entity_labels(db: Session, business_id: int, logs: list[ActivityLog]) -> dict[tuple[str, int], str]:
    """Look up a readable name (product, PO number, supplier) for each affected record, one query per type."""
    ids: dict[str, set[int]] = {"inventory_item": set(), "purchase_order": set(), "stock_alert": set(), "supplier": set()}
    for log in logs:
        if log.entity_id is not None and log.entity_type in ids:
            ids[log.entity_type].add(log.entity_id)

    labels: dict[tuple[str, int], str] = {}
    if ids["inventory_item"]:
        for item_id, name in db.execute(
            select(InventoryItem.id, InventoryItem.name).where(
                InventoryItem.business_id == business_id, InventoryItem.id.in_(ids["inventory_item"])
            )
        ):
            labels[("inventory_item", item_id)] = name
    if ids["purchase_order"]:
        for order_id, po_number in db.execute(
            select(PurchaseOrder.id, PurchaseOrder.po_number).where(
                PurchaseOrder.business_id == business_id, PurchaseOrder.id.in_(ids["purchase_order"])
            )
        ):
            labels[("purchase_order", order_id)] = po_number
    if ids["stock_alert"]:
        for alert_id, name in db.execute(
            select(StockAlert.id, InventoryItem.name)
            .join(InventoryItem, InventoryItem.id == StockAlert.item_id)
            .where(StockAlert.business_id == business_id, StockAlert.id.in_(ids["stock_alert"]))
        ):
            labels[("stock_alert", alert_id)] = name
    if ids["supplier"]:
        for supplier_id, name in db.execute(
            select(Supplier.id, Supplier.name).where(
                Supplier.business_id == business_id, Supplier.id.in_(ids["supplier"])
            )
        ):
            labels[("supplier", supplier_id)] = name
    return labels


def _filters(
    business_id: int,
    category: str | None,
    action: str | None,
    approval: str | None,
    user_id: int | None,
    search: str | None,
    date_from: date | None,
    date_to: date | None,
) -> list:
    conditions = [ActivityLog.business_id == business_id]
    if category and category in CATEGORIES:
        conditions.append(ActivityLog.action.startswith(CATEGORIES[category][1]))
    if action:
        conditions.append(ActivityLog.action == action)
    if approval and approval in APPROVAL_FILTERS:
        conditions.append(ActivityLog.action.in_(APPROVAL_FILTERS[approval]))
    if user_id is not None:
        conditions.append(ActivityLog.user_id == user_id)
    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(ActivityLog.summary.ilike(term), ActivityLog.action.ilike(term)))
    # Dates are compared as UTC days (the log stores UTC). date_to is inclusive.
    if date_from:
        conditions.append(ActivityLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        conditions.append(ActivityLog.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    return conditions


def list_logs(
    db: Session,
    business_id: int,
    category: str | None = None,
    action: str | None = None,
    approval: str | None = None,
    user_id: int | None = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    conditions = _filters(business_id, category, action, approval, user_id, search, date_from, date_to)
    total = db.scalar(select(func.count()).select_from(ActivityLog).where(*conditions)) or 0
    logs = list(
        db.scalars(
            select(ActivityLog)
            .where(*conditions)
            .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )

    user_ids = {log.user_id for log in logs if log.user_id is not None}
    users = {}
    if user_ids:
        users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids)))}
    labels = _entity_labels(db, business_id, logs)

    items = []
    for log in logs:
        old, new = _parse(log.old_value), _parse(log.new_value)
        actor = users.get(log.user_id)
        items.append(
            {
                "id": log.id,
                "created_at": log.created_at,
                "user_id": log.user_id,
                "user_name": actor.name if actor else "System",
                "user_role": actor.role if actor else None,
                "action": log.action,
                "action_label": ACTION_LABELS.get(log.action, log.action),
                "category": category_for(log.action),
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "entity_label": labels.get((log.entity_type, log.entity_id)) if log.entity_id is not None else None,
                "summary": log.summary,
                "approval_status": approval_status_for(log.action),
                "old_value": old,
                "new_value": new,
                "changes": _changes(old, new),
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_summary(db: Session, business_id: int) -> dict:
    base = ActivityLog.business_id == business_id

    def count(*extra) -> int:
        return db.scalar(select(func.count()).select_from(ActivityLog).where(base, *extra)) or 0

    return {
        "total": count(),
        "last_24_hours": count(ActivityLog.created_at >= utcnow() - timedelta(hours=24)),
        "approvals": count(ActivityLog.action == "po.approved"),
        "rejections": count(ActivityLog.action == "po.rejected"),
        "blocked_attempts": count(ActivityLog.action == "access.denied"),
    }


def get_filter_options(db: Session, business_id: int) -> dict:
    users = db.scalars(select(User).where(User.business_id == business_id).order_by(User.name))
    return {
        "users": [{"id": u.id, "name": u.name, "role": u.role} for u in users],
        "categories": [{"value": value, "label": label} for value, (label, _prefix) in CATEGORIES.items()],
        "actions": [{"value": code, "label": label} for code, label in ACTION_LABELS.items()],
    }
