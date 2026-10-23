"""Low-stock alert logic (Feature 2).

The one rule:
    An item needs an alert when it is not archived AND its stock status is
    Low Stock or Out of Stock (quantity <= reorder threshold).

`sync_item_alert` is called from inventory_service inside the SAME database
transaction as the stock change, so the quantity, the movement, the alert and
the audit-log rows are saved together or not at all.

    needs alert + no open alert   -> open one          (alert.opened)
    needs alert + open alert      -> do nothing        (no duplicates)
    no alert needed + open alert  -> resolve it        (alert.resolved)
    no alert needed + no alert    -> do nothing
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import (
    ALERT_OPEN,
    ALERT_RESOLVED,
    RESOLUTION_ARCHIVED,
    RESOLUTION_REPLENISHED,
    RESOLUTION_THRESHOLD_CHANGED,
    STATUS_IN_STOCK,
    URGENCY_CRITICAL,
    URGENCY_LOW,
    URGENCY_URGENT,
)
from app.database import utcnow
from app.models import InventoryItem, StockAlert, User, compute_stock_status
from app.services.activity_service import log_activity

URGENCY_RANK = {URGENCY_CRITICAL: 0, URGENCY_URGENT: 1, URGENCY_LOW: 2}


def urgency_for(quantity: int, threshold: int) -> str:
    """How urgent is a low item?  (documented rule, used for sorting and colours)

    - quantity is 0                      -> critical  (out of stock)
    - quantity is half the threshold or less -> urgent
    - otherwise (still at/below threshold)   -> low
    """
    if quantity <= 0:
        return URGENCY_CRITICAL
    if threshold > 0 and quantity * 2 <= threshold:
        return URGENCY_URGENT
    return URGENCY_LOW


def item_needs_alert(item: InventoryItem) -> bool:
    if item.is_archived:
        return False
    return compute_stock_status(item.quantity, item.reorder_threshold) != STATUS_IN_STOCK


def _open_alert_for(db: Session, item_id: int) -> StockAlert | None:
    return db.scalar(
        select(StockAlert).where(StockAlert.item_id == item_id, StockAlert.status == ALERT_OPEN)
    )


def _resolution_reason(item: InventoryItem, trigger: str) -> str:
    if item.is_archived:
        return RESOLUTION_ARCHIVED
    if trigger == "threshold":
        return RESOLUTION_THRESHOLD_CHANGED
    return RESOLUTION_REPLENISHED


def sync_item_alert(db: Session, user: User | None, item: InventoryItem, trigger: str = "stock") -> None:
    """Make the alert table match the item's current state. Does NOT commit.

    `trigger` says what caused the check ("stock", "threshold", "archive",
    "restore", "create", "scan"). It only affects the wording of why an alert closed.
    """
    open_alert = _open_alert_for(db, item.id)
    needs_alert = item_needs_alert(item)

    if needs_alert and open_alert is None:
        alert = StockAlert(
            business_id=item.business_id,
            item_id=item.id,
            quantity_at_alert=item.quantity,
            threshold_at_alert=item.reorder_threshold,
        )
        db.add(alert)
        db.flush()  # gives the alert an id and enforces the one-open-alert rule now
        log_activity(
            db, user, "alert.opened", "stock_alert", alert.id,
            f"Low-stock alert opened for {item.name}: {item.quantity} {item.unit} left "
            f"(reorder at {item.reorder_threshold})",
            new_value={
                "item_id": item.id,
                "quantity": item.quantity,
                "reorder_threshold": item.reorder_threshold,
                "urgency": urgency_for(item.quantity, item.reorder_threshold),
            },
            business_id=item.business_id,
        )

    elif not needs_alert and open_alert is not None:
        reason = _resolution_reason(item, trigger)
        open_alert.status = ALERT_RESOLVED
        open_alert.resolved_at = utcnow()
        open_alert.resolution = reason
        log_activity(
            db, user, "alert.resolved", "stock_alert", open_alert.id,
            f"Low-stock alert resolved for {item.name} ({reason.replace('_', ' ')}): "
            f"{item.quantity} {item.unit}, reorder at {item.reorder_threshold}",
            old_value={"status": ALERT_OPEN},
            new_value={"status": ALERT_RESOLVED, "resolution": reason, "quantity": item.quantity},
            business_id=item.business_id,
        )


def reconcile_all(db: Session) -> None:
    """Start-up scan: bring alerts in line with every product's current stock.

    Needed because products that were already low before alerts existed (or
    changed outside the app) have no alert yet. Safe to run repeatedly: when
    everything already matches, it changes nothing.
    """
    items = list(db.scalars(select(InventoryItem)))  # load first, then write
    for item in items:
        sync_item_alert(db, None, item, "scan")
    db.commit()


# ---------------------------------------------------------------- reading alerts

def _alert_row(alert: StockAlert, item: InventoryItem) -> dict:
    is_open = alert.status == ALERT_OPEN
    return {
        "id": alert.id,
        "item_id": item.id,
        "item_name": item.name,
        "sku": item.sku,
        "category": item.category,
        "unit": item.unit,
        "supplier_name": item.supplier_name,
        "quantity": item.quantity,
        "reorder_threshold": item.reorder_threshold,
        "shortfall": max(item.reorder_threshold - item.quantity, 0),
        "stock_status": item.stock_status,
        "urgency": urgency_for(item.quantity, item.reorder_threshold) if is_open else None,
        "status": alert.status,
        "opened_at": alert.opened_at,
        "resolved_at": alert.resolved_at,
        "resolution": alert.resolution,
    }


def _ratio(row: dict) -> float:
    threshold = row["reorder_threshold"]
    return row["quantity"] / threshold if threshold > 0 else 0.0


def list_alerts(db: Session, business_id: int, status: str = "open") -> list[dict]:
    """status: 'open' (default), 'resolved' or 'all'.  Open alerts come back most urgent first."""
    query = (
        select(StockAlert, InventoryItem)
        .join(InventoryItem, InventoryItem.id == StockAlert.item_id)
        .where(StockAlert.business_id == business_id)
    )
    if status in (ALERT_OPEN, ALERT_RESOLVED):
        query = query.where(StockAlert.status == status)

    rows = [_alert_row(alert, item) for alert, item in db.execute(query).all()]

    open_rows = [row for row in rows if row["status"] == ALERT_OPEN]
    resolved_rows = [row for row in rows if row["status"] == ALERT_RESOLVED]
    # Most urgent first; within a level the emptiest first; then oldest alert first
    open_rows.sort(key=lambda row: (URGENCY_RANK[row["urgency"]], _ratio(row), row["opened_at"]))
    resolved_rows.sort(key=lambda row: row["resolved_at"], reverse=True)
    return open_rows + resolved_rows


def get_alert_summary(db: Session, business_id: int) -> dict:
    open_rows = list_alerts(db, business_id, ALERT_OPEN)
    resolved_total = db.scalar(
        select(func.count()).where(
            StockAlert.business_id == business_id, StockAlert.status == ALERT_RESOLVED
        )
    )
    return {
        "open": len(open_rows),
        "critical": sum(1 for row in open_rows if row["urgency"] == URGENCY_CRITICAL),
        "urgent": sum(1 for row in open_rows if row["urgency"] == URGENCY_URGENT),
        "low": sum(1 for row in open_rows if row["urgency"] == URGENCY_LOW),
        "resolved": resolved_total or 0,
    }
