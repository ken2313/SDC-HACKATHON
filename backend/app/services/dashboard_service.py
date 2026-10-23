"""Inventory dashboard (Feature 7). Read-only: this file never changes data.

Everything shown on the dashboard is calculated here from the database, for ONE business.

Who sees what:
  * Owner and Employee (inventory:view): stock counts, alerts, orders waiting, deliveries,
    recent stock activity, trends.
  * Owner only (reports:view): money totals (stock value, money waiting for approval,
    money on order, goods received in the last 30 days). For an employee `financials` is null.

Definitions (also on the page, so the numbers can be explained):
  * Stock value       = quantity x the price the system would order at today (cheapest active
                        supplier). Products with no supplier price are counted separately.
  * Pending orders    = purchase orders waiting for the owner's decision (draft / pending approval).
  * Delayed orders    = orders marked Delayed, plus orders past their expected date (overdue).
  * Trend             = for one product, the stock at the end of each day (Malaysia time) and
                        the units added and used that day, rebuilt from the stock movements.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import (
    ALERT_OPEN,
    MOVEMENT_IN,
    MOVEMENT_INITIAL,
    MOVEMENT_OUT,
    PO_APPROVED,
    PO_AWAITING_DECISION,
    PO_AWAITING_DELIVERY,
    PO_DELAYED,
    PO_DELIVERED,
    PO_IN_PROGRESS,
    STATUS_IN_STOCK,
    STATUS_LOW_STOCK,
    STATUS_OUT_OF_STOCK,
)
from app.database import utcnow
from app.models import (
    InventoryItem,
    OrderStatusHistory,
    PurchaseOrder,
    PurchaseOrderItem,
    StockMovement,
    Supplier,
    SupplierProduct,
    User,
)
from app.services.alert_service import list_alerts

MALAYSIA_OFFSET = timedelta(hours=8)
UPCOMING_DELIVERY_DAYS = 14
RECENT_ACTIVITY_LIMIT = 10
URGENT_LIMIT = 5
MIN_TREND_DAYS_WITH_DATA = 7  # fewer days with movements than this -> "not enough history" note


class DashboardError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _rm(sen: int | None) -> float:
    return round((sen or 0) / 100, 2)


def today_my() -> date:
    return (utcnow() + MALAYSIA_OFFSET).date()


def _my_date(moment: datetime) -> date:
    return (moment + MALAYSIA_OFFSET).date()


def _day_end_utc(day: date) -> datetime:
    """The moment a Malaysian calendar day ends, as naive UTC."""
    return datetime.combine(day + timedelta(days=1), datetime.min.time()) - MALAYSIA_OFFSET


# ------------------------------------------------------------------ pieces of the overview

def _stock_counts(items: list[InventoryItem]) -> dict:
    active = [item for item in items if not item.is_archived]
    return {
        "total_products": len(active),
        "in_stock": sum(1 for i in active if i.stock_status == STATUS_IN_STOCK),
        "low_stock": sum(1 for i in active if i.stock_status == STATUS_LOW_STOCK),
        "out_of_stock": sum(1 for i in active if i.stock_status == STATUS_OUT_OF_STOCK),
        "archived": len(items) - len(active),
    }


def _status_by_category(items: list[InventoryItem]) -> list[dict]:
    groups: dict[str, dict] = {}
    for item in items:
        if item.is_archived:
            continue
        row = groups.setdefault(item.category, {"category": item.category, "in_stock": 0, "low_stock": 0, "out_of_stock": 0})
        row[item.stock_status] += 1
    # Categories with problems first, then alphabetical
    return sorted(groups.values(), key=lambda r: (-(r["low_stock"] + r["out_of_stock"]), r["category"].lower()))


def _order_counts(orders: list[PurchaseOrder], today: date) -> dict:
    overdue = [
        o for o in orders
        if o.status in PO_AWAITING_DELIVERY and o.estimated_delivery_date and o.estimated_delivery_date < today
    ]
    delayed_or_overdue = {o.id for o in orders if o.status == PO_DELAYED} | {o.id for o in overdue}
    return {
        "pending_approval": sum(1 for o in orders if o.status in PO_AWAITING_DECISION),
        "approved_not_placed": sum(1 for o in orders if o.status == PO_APPROVED),
        "awaiting_delivery": sum(1 for o in orders if o.status in PO_AWAITING_DELIVERY),
        "delayed": sum(1 for o in orders if o.status == PO_DELAYED),
        "overdue": len(overdue),
        "delayed_or_overdue": len(delayed_or_overdue),
    }


def _upcoming_deliveries(db: Session, orders: list[PurchaseOrder], today: date) -> list[dict]:
    """Orders with the supplier (ordered / shipped / delayed): overdue ones and those due within 14 days."""
    waiting = [
        o for o in orders
        if o.status in PO_AWAITING_DELIVERY
        and o.estimated_delivery_date is not None
        and o.estimated_delivery_date <= today + timedelta(days=UPCOMING_DELIVERY_DAYS)
    ]
    waiting.sort(key=lambda o: (o.estimated_delivery_date, o.id))
    suppliers = {s.id: s.name for s in db.scalars(select(Supplier).where(Supplier.id.in_({o.supplier_id for o in waiting})))} if waiting else {}
    rows = []
    for order in waiting:
        days_until = (order.estimated_delivery_date - today).days
        rows.append({
            "id": order.id,
            "po_number": order.po_number,
            "status": order.status,
            "supplier_name": suppliers.get(order.supplier_id, "Unknown supplier"),
            "estimated_delivery_date": order.estimated_delivery_date,
            "days_until": days_until,          # negative = overdue by that many days
            "is_overdue": days_until < 0,
            "line_count": len(order.lines),
            "total": _rm(sum(line.quantity_ordered * line.unit_price_sen for line in order.lines)),
        })
    return rows


def _recent_activity(db: Session, business_id: int) -> list[dict]:
    rows = db.execute(
        select(StockMovement, InventoryItem.name, InventoryItem.unit, User.name)
        .join(InventoryItem, InventoryItem.id == StockMovement.item_id)
        .join(User, User.id == StockMovement.user_id)
        .where(StockMovement.business_id == business_id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(RECENT_ACTIVITY_LIMIT)
    ).all()
    return [
        {
            "id": movement.id,
            "item_id": movement.item_id,
            "item_name": item_name,
            "unit": unit,
            "movement_type": movement.movement_type,
            "quantity_change": movement.quantity_change,
            "quantity_before": movement.quantity_before,
            "quantity_after": movement.quantity_after,
            "reason": movement.reason,
            "user_name": user_name,
            "created_at": movement.created_at,
        }
        for movement, item_name, unit, user_name in rows
    ]


def _urgent_products(db: Session, business_id: int) -> list[dict]:
    """The most urgent open alerts, with the order that covers them (if any)."""
    alerts = list_alerts(db, business_id, ALERT_OPEN)[:URGENT_LIMIT]
    if not alerts:
        return []
    covering = {
        item_id: (po_number, status)
        for item_id, po_number, status in db.execute(
            select(PurchaseOrderItem.item_id, PurchaseOrder.po_number, PurchaseOrder.status)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
            .where(
                PurchaseOrderItem.item_id.in_([a["item_id"] for a in alerts]),
                PurchaseOrderItem.outstanding.is_(True),
            )
        )
    }
    return [
        {
            "item_id": alert["item_id"],
            "item_name": alert["item_name"],
            "sku": alert["sku"],
            "unit": alert["unit"],
            "quantity": alert["quantity"],
            "reorder_threshold": alert["reorder_threshold"],
            "urgency": alert["urgency"],
            "order_po_number": covering.get(alert["item_id"], (None, None))[0],
            "order_status": covering.get(alert["item_id"], (None, None))[1],
        }
        for alert in alerts
    ]


def _best_prices(db: Session, business_id: int) -> dict[int, int]:
    """item_id -> cheapest active price in sen (the price a new draft would use)."""
    rows = db.execute(
        select(SupplierProduct.item_id, func.min(SupplierProduct.unit_price_sen))
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.business_id == business_id,
            SupplierProduct.is_active.is_(True),
            Supplier.is_active.is_(True),
        )
        .group_by(SupplierProduct.item_id)
    ).all()
    return {item_id: price for item_id, price in rows}


def _financials(db: Session, business_id: int, items: list[InventoryItem], orders: list[PurchaseOrder]) -> dict:
    prices = _best_prices(db, business_id)
    active = [item for item in items if not item.is_archived]
    priced = [item for item in active if item.id in prices]
    stock_value_sen = sum(item.quantity * prices[item.id] for item in priced)

    def order_value(statuses) -> int:
        return sum(
            line.quantity_ordered * line.unit_price_sen
            for order in orders if order.status in statuses
            for line in order.lines
        )

    # Goods received in the last 30 days: delivered orders, by the time the delivery was confirmed
    since = utcnow() - timedelta(days=30)
    delivered_ids = set(
        db.scalars(
            select(OrderStatusHistory.purchase_order_id).where(
                OrderStatusHistory.business_id == business_id,
                OrderStatusHistory.to_status == PO_DELIVERED,
                OrderStatusHistory.created_at >= since,
            )
        )
    )
    received_sen = sum(
        line.received_quantity * line.unit_price_sen
        for order in orders if order.id in delivered_ids and order.status == PO_DELIVERED
        for line in order.lines
    )
    return {
        "stock_value": _rm(stock_value_sen),
        "products_without_price": len(active) - len(priced),
        "pending_approval_value": _rm(order_value(PO_AWAITING_DECISION)),
        "on_order_value": _rm(order_value(PO_IN_PROGRESS)),   # approved and not yet received
        "received_last_30_days": _rm(received_sen),
    }


def _trend_choices(db: Session, business_id: int, items: list[InventoryItem]) -> tuple[list[dict], int | None]:
    """Products to pick for the trend chart, and a sensible default (the busiest low product,
    otherwise the busiest product overall)."""
    active = [item for item in items if not item.is_archived]
    since = utcnow() - timedelta(days=30)
    counts = dict(
        db.execute(
            select(StockMovement.item_id, func.count())
            .where(
                StockMovement.business_id == business_id,
                StockMovement.created_at >= since,
                StockMovement.movement_type != MOVEMENT_INITIAL,
            )
            .group_by(StockMovement.item_id)
        ).all()
    )
    choices = sorted(
        ({"item_id": i.id, "item_name": i.name, "sku": i.sku, "unit": i.unit} for i in active),
        key=lambda row: row["item_name"].lower(),
    )
    if not active:
        return choices, None
    default = max(active, key=lambda i: (counts.get(i.id, 0), i.stock_status != STATUS_IN_STOCK, -i.id))
    return choices, default.id


# ------------------------------------------------------------------ public functions

def get_overview(db: Session, user: User, can_view_reports: bool) -> dict:
    db.expire_all()  # read what is really in the database
    business_id = user.business_id
    today = today_my()
    items = list(db.scalars(select(InventoryItem).where(InventoryItem.business_id == business_id)))
    orders = list(db.scalars(select(PurchaseOrder).where(PurchaseOrder.business_id == business_id)))
    alerts = list_alerts(db, business_id, ALERT_OPEN)
    choices, default_item = _trend_choices(db, business_id, items)

    return {
        "generated_at": utcnow(),
        "today": today,
        "stock": _stock_counts(items),
        "alerts": {
            "open": len(alerts),
            "critical": sum(1 for a in alerts if a["urgency"] == "critical"),
            "urgent": sum(1 for a in alerts if a["urgency"] == "urgent"),
        },
        "orders": _order_counts(orders, today),
        "financials": _financials(db, business_id, items, orders) if can_view_reports else None,
        "status_by_category": _status_by_category(items),
        "upcoming_deliveries": _upcoming_deliveries(db, orders, today),
        "recent_activity": _recent_activity(db, business_id),
        "urgent_products": _urgent_products(db, business_id),
        "trend_products": choices,
        "default_trend_item_id": default_item,
        # Feature 9 (AI anomaly detection on RunPod) is not built yet. Said plainly, not faked.
        "anomalies": {"available": False, "message": "AI anomaly detection arrives with Feature 9."},
    }


def get_trend(db: Session, business_id: int, item_id: int, days: int) -> dict:
    """End-of-day stock, units added and units used per day for the last `days` days (today included)."""
    item = db.scalar(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.business_id == business_id)
    )
    if item is None:
        raise DashboardError("Product not found.", 404)

    today = today_my()
    first_day = today - timedelta(days=days - 1)
    movements = list(
        db.scalars(
            select(StockMovement)
            .where(StockMovement.item_id == item.id, StockMovement.business_id == business_id)
            .order_by(StockMovement.created_at, StockMovement.id)
        )
    )

    added: dict[date, int] = defaultdict(int)
    used: dict[date, int] = defaultdict(int)
    for movement in movements:
        day = _my_date(movement.created_at)
        if day < first_day:
            continue
        if movement.movement_type == MOVEMENT_IN:
            added[day] += movement.quantity_change
        elif movement.movement_type == MOVEMENT_OUT:
            used[day] += -movement.quantity_change

    points = []
    index = 0
    quantity: int | None = None
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        end = _day_end_utc(day)
        while index < len(movements) and movements[index].created_at < end:
            quantity = movements[index].quantity_after
            index += 1
        if day == today:
            quantity = item.quantity  # today: what is on the shelf right now
        points.append({
            "date": day,
            "quantity": quantity,   # None before the product had any stock record
            "stock_in": added.get(day, 0),
            "stock_out": used.get(day, 0),
        })

    days_with_usage = sum(1 for p in points if p["stock_out"] > 0)
    total_used = sum(p["stock_out"] for p in points)
    return {
        "item_id": item.id,
        "item_name": item.name,
        "sku": item.sku,
        "unit": item.unit,
        "reorder_threshold": item.reorder_threshold,
        "current_quantity": item.quantity,
        "days": days,
        "points": points,
        "total_in": sum(p["stock_in"] for p in points),
        "total_out": total_used,
        "average_daily_usage": round(total_used / days, 1),
        "days_with_usage": days_with_usage,
        "enough_history": days_with_usage >= MIN_TREND_DAYS_WITH_DATA,
    }
