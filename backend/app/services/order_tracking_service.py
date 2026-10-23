"""Supplier order tracking (Feature 5).

The workflow this file implements (after the owner approved an order in Feature 3):

    Approved
      -> Ordered      owner places it with the supplier (SIMULATED: no real message is sent)
      -> Shipped / Delayed   staff update what the supplier tells them
      -> Delivered    someone confirms what really arrived -> inventory is updated, ONCE
      (Cancelled      owner only, until the goods are received)

Rules (also in docs/DECISIONS.md):
  * Only the moves listed in constants.PO_TRANSITIONS are allowed.
  * Every move is a guarded UPDATE ("... WHERE status = <the status we read>"), so two people
    cannot both move the same order, and an order cannot skip a step.
  * Confirming a delivery changes the status, the received quantities, the stock, the alerts,
    the history and the audit log in ONE database transaction.
  * Inventory is updated only once per order. Three separate protections:
      1. the order must be in a receivable status,
      2. a guarded UPDATE flips `inventory_applied` from 0 to 1 (second attempt matches 0 rows),
      3. each stock movement carries a unique request_id ("po-receipt-<order>-<line>").
  * "Overdue" is calculated, not stored: not delivered and expected date before today (Malaysia time).
    Nothing changes status by itself. A person marks an order Delayed.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import (
    MOVEMENT_IN,
    PO_APPROVED,
    PO_AWAITING_DELIVERY,
    PO_CANCELLED,
    PO_DELAYED,
    PO_DELIVERED,
    PO_DRAFT,
    PO_IN_PROGRESS,
    PO_ORDERED,
    PO_RECEIVABLE,
    PO_TRANSITIONS,
)
from app.database import utcnow
from app.models import (
    InventoryItem,
    OrderStatusHistory,
    PurchaseOrder,
    PurchaseOrderItem,
    StockMovement,
    Supplier,
    User,
)
from app.schemas.tracking import CancelOrder, ReceiveDelivery, StatusUpdate
from app.services import purchase_order_service
from app.services.activity_service import log_activity
from app.services.alert_service import sync_item_alert
from app.services.order_history_helper import record_history

logger = logging.getLogger(__name__)

# Malaysia has no daylight saving, so a fixed UTC+8 offset is exact (and works on Windows
# without extra packages). Used only to decide what "today" means for overdue deliveries.
MALAYSIA_TZ = timezone(timedelta(hours=8))

TRACKED_STATUSES = PO_IN_PROGRESS + (PO_DELIVERED, PO_CANCELLED)


class TrackingError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def today_my() -> date:
    return datetime.now(MALAYSIA_TZ).date()


def _label(status: str) -> str:
    return status.replace("_", " ")


def _rm(sen: int) -> float:
    return round(sen / 100, 2)


# ------------------------------------------------------------------ history

def backfill_history(db: Session) -> int:
    """Orders created before Feature 5 have no timeline. Give each one a starting entry.
    Safe to repeat: orders that already have history are skipped."""
    have_history = set(db.scalars(select(OrderStatusHistory.purchase_order_id).distinct()))
    added = 0
    for order in db.scalars(select(PurchaseOrder)):
        if order.id in have_history:
            continue
        db.add(OrderStatusHistory(
            business_id=order.business_id, purchase_order_id=order.id, from_status=None,
            to_status=PO_DRAFT, user_id=order.created_by_user_id, note="Order created",
            created_at=order.created_at,
        ))
        if order.status != PO_DRAFT:
            db.add(OrderStatusHistory(
                business_id=order.business_id, purchase_order_id=order.id, from_status=PO_DRAFT,
                to_status=order.status, user_id=order.decided_by_user_id,
                note=(order.decision_note or "")[:255] or None,
                created_at=order.decided_at or order.updated_at,
            ))
        added += 1
    if added:
        db.commit()
    return added


# ------------------------------------------------------------------ reading

def _tracked_row(db: Session, business_id: int, order_id: int) -> PurchaseOrder:
    order = db.scalar(
        select(PurchaseOrder).where(PurchaseOrder.id == order_id, PurchaseOrder.business_id == business_id)
    )
    if order is None or order.status not in TRACKED_STATUSES:
        raise TrackingError("Supplier order not found. (Only approved orders are tracked here.)", 404)
    return order


def _overdue_days(order: PurchaseOrder, today: date) -> int:
    if order.status in PO_AWAITING_DELIVERY and order.estimated_delivery_date and order.estimated_delivery_date < today:
        return (today - order.estimated_delivery_date).days
    return 0


def _tracked_dict(db: Session, order: PurchaseOrder, today: date) -> dict:
    supplier = db.get(Supplier, order.supplier_id)
    item_ids = [line.item_id for line in order.lines]
    items = {i.id: i for i in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids)))} if item_ids else {}

    history_rows = db.execute(
        select(OrderStatusHistory, User.name)
        .outerjoin(User, User.id == OrderStatusHistory.user_id)
        .where(OrderStatusHistory.purchase_order_id == order.id)
        .order_by(OrderStatusHistory.created_at, OrderStatusHistory.id)
    ).all()

    lines = [
        {
            "id": line.id,
            "item_id": line.item_id,
            "item_name": items[line.item_id].name,
            "sku": items[line.item_id].sku,
            "unit": items[line.item_id].unit,
            "quantity_ordered": line.quantity_ordered,
            "received_quantity": line.received_quantity,
            "unit_price": _rm(line.unit_price_sen),
            "line_total": _rm(line.quantity_ordered * line.unit_price_sen),
        }
        for line in order.lines
    ]
    overdue = _overdue_days(order, today)
    return {
        "id": order.id,
        "po_number": order.po_number,
        "status": order.status,
        "supplier_name": supplier.name,
        "supplier_contact": supplier.contact_name,
        "supplier_phone": supplier.phone,
        "lead_time_days": supplier.typical_lead_time_days,
        "total": _rm(sum(line.quantity_ordered * line.unit_price_sen for line in order.lines)),
        "estimated_delivery_date": order.estimated_delivery_date,
        "is_overdue": overdue > 0,
        "days_overdue": overdue,
        "inventory_applied": order.inventory_applied,
        "lines": lines,
        "next_statuses": list(PO_TRANSITIONS.get(order.status, ())),
        "history": [
            {
                "id": row.id,
                "from_status": row.from_status,
                "to_status": row.to_status,
                "user_name": name or "System",
                "note": row.note,
                "created_at": row.created_at,
            }
            for row, name in history_rows
        ],
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def get_order(db: Session, business_id: int, order_id: int) -> dict:
    db.expire_all()  # read what is really in the database
    return _tracked_dict(db, _tracked_row(db, business_id, order_id), today_my())


def list_orders(db: Session, business_id: int, view: str = "active") -> list[dict]:
    """view: active (approved/ordered/shipped/delayed), overdue, delivered, cancelled, all."""
    statuses = {
        "active": PO_IN_PROGRESS,
        "overdue": PO_AWAITING_DELIVERY,
        "delivered": (PO_DELIVERED,),
        "cancelled": (PO_CANCELLED,),
        "all": TRACKED_STATUSES,
    }.get(view)
    if statuses is None:
        raise TrackingError("Invalid view.", 422)

    db.expire_all()
    today = today_my()
    orders = list(
        db.scalars(
            select(PurchaseOrder).where(PurchaseOrder.business_id == business_id, PurchaseOrder.status.in_(statuses))
        )
    )
    if view == "overdue":
        orders = [o for o in orders if _overdue_days(o, today) > 0]

    if view in ("active", "overdue"):
        # soonest expected delivery first; orders without a date last
        orders.sort(key=lambda o: (o.estimated_delivery_date is None, o.estimated_delivery_date or date.max, o.id))
    else:
        orders.sort(key=lambda o: (o.updated_at, o.id), reverse=True)
    return [_tracked_dict(db, order, today) for order in orders]


def get_summary(db: Session, business_id: int) -> dict:
    db.expire_all()
    today = today_my()
    orders = list(db.scalars(select(PurchaseOrder).where(PurchaseOrder.business_id == business_id)))

    def count(*statuses: str) -> int:
        return sum(1 for o in orders if o.status in statuses)

    waiting = [o for o in orders if o.status in PO_AWAITING_DELIVERY]
    return {
        "awaiting_placement": count(PO_APPROVED),
        "in_transit": count(PO_ORDERED, "shipped"),
        "delayed": count(PO_DELAYED),
        "overdue": sum(1 for o in waiting if _overdue_days(o, today) > 0),
        "due_next_7_days": sum(
            1 for o in waiting
            if o.estimated_delivery_date and today <= o.estimated_delivery_date <= today + timedelta(days=7)
        ),
        "delivered": count(PO_DELIVERED),
        "cancelled": count(PO_CANCELLED),
    }


# ------------------------------------------------------------------ changing status

def _move(db: Session, order: PurchaseOrder, to_status: str, **extra) -> str:
    """Guarded status change. Returns the old status. Does NOT commit."""
    old = order.status
    if to_status not in PO_TRANSITIONS.get(old, ()):
        raise TrackingError(f"An order that is {_label(old)} cannot be changed to {_label(to_status)}.", 409)
    result = db.execute(
        update(PurchaseOrder)
        .where(
            PurchaseOrder.id == order.id,
            PurchaseOrder.business_id == order.business_id,
            PurchaseOrder.status == old,   # nobody changed it since we read it
        )
        .values(status=to_status, updated_at=utcnow(), **extra)
    )
    if result.rowcount == 0:
        db.rollback()
        raise TrackingError("This order was just changed by someone else. Refresh the page.", 409)
    return old


def place_order(db: Session, user: User, order_id: int) -> dict:
    """OWNER ONLY. SIMULATED supplier action: nothing is sent to any real supplier."""
    order = _tracked_row(db, user.business_id, order_id)
    supplier = db.get(Supplier, order.supplier_id)
    old_date = order.estimated_delivery_date
    new_date = today_my() + timedelta(days=supplier.typical_lead_time_days)
    old = _move(db, order, PO_ORDERED, estimated_delivery_date=new_date)
    note = f"Simulated: order sent to {supplier.name}. No real message was sent."
    record_history(db, order, user, old, PO_ORDERED, note)
    log_activity(
        db, user, "po.placed", "purchase_order", order.id,
        f"Placed {order.po_number} with {supplier.name} (simulated). Expected {new_date.isoformat()}",
        old_value={"status": old, "estimated_delivery_date": old_date.isoformat() if old_date else None},
        new_value={"status": PO_ORDERED, "estimated_delivery_date": new_date.isoformat(), "simulated": True},
    )
    db.commit()
    return get_order(db, user.business_id, order_id)


def update_status(db: Session, user: User, order_id: int, data: StatusUpdate) -> dict:
    order = _tracked_row(db, user.business_id, order_id)
    new_date = data.estimated_delivery_date
    if data.status == PO_DELAYED and new_date is None:
        raise TrackingError("Enter the new expected delivery date for a delayed order.", 422)
    if new_date is not None and new_date < today_my():
        raise TrackingError("The expected delivery date cannot be in the past.", 422)

    old_date = order.estimated_delivery_date
    extra = {"estimated_delivery_date": new_date} if new_date is not None else {}
    old = _move(db, order, data.status, **extra)

    final_date = new_date or old_date
    detail = f"expected {final_date.isoformat()}" if final_date else "no expected date"
    record_history(db, order, user, old, data.status, data.note or f"Now {_label(data.status)}, {detail}")
    log_activity(
        db, user, f"po.{data.status}", "purchase_order", order.id,
        f"{order.po_number} marked {_label(data.status)} ({detail})" + (f": {data.note}" if data.note else ""),
        old_value={"status": old, "estimated_delivery_date": old_date.isoformat() if old_date else None},
        new_value={
            "status": data.status,
            "estimated_delivery_date": final_date.isoformat() if final_date else None,
            "note": data.note,
        },
    )
    db.commit()
    return get_order(db, user.business_id, order_id)


def cancel_order(db: Session, user: User, order_id: int, data: CancelOrder) -> dict:
    """OWNER ONLY. Allowed until the goods are received. Frees the products for a new order."""
    order = _tracked_row(db, user.business_id, order_id)
    old = _move(db, order, PO_CANCELLED)
    db.execute(
        update(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order.id).values(outstanding=False)
    )
    record_history(db, order, user, old, PO_CANCELLED, data.reason)
    log_activity(
        db, user, "po.cancelled", "purchase_order", order.id,
        f"Cancelled {order.po_number}: {data.reason}",
        old_value={"status": old},
        new_value={"status": PO_CANCELLED, "reason": data.reason},
    )
    db.commit()
    return get_order(db, user.business_id, order_id)


# ------------------------------------------------------------------ confirming a delivery

def _add_received_stock(
    db: Session, user: User, order: PurchaseOrder, line: PurchaseOrderItem, item: InventoryItem, quantity: int
) -> dict:
    """Add delivered goods to stock inside the caller's transaction (does NOT commit).
    Same safety rules as a normal stock-in, plus a unique request_id so this exact
    delivery line can never be added twice."""
    db.execute(
        update(InventoryItem)
        .where(InventoryItem.id == item.id, InventoryItem.business_id == order.business_id)
        .values(quantity=InventoryItem.quantity + quantity, updated_at=utcnow())
    )
    db.refresh(item)
    after = item.quantity
    before = after - quantity
    db.add(
        StockMovement(
            business_id=order.business_id,
            item_id=item.id,
            user_id=user.id,
            movement_type=MOVEMENT_IN,
            quantity_change=quantity,
            quantity_before=before,
            quantity_after=after,
            reason=f"Delivery {order.po_number}",
            request_id=f"po-receipt-{order.id}-{line.id}",
        )
    )
    db.flush()  # the unique request_id is checked right here
    log_activity(
        db, user, "stock.in", "inventory_item", item.id,
        f"Added {quantity} {item.unit} of {item.name} ({before} -> {after}) from delivery {order.po_number}",
        old_value={"quantity": before},
        new_value={"quantity": after, "reason": f"Delivery {order.po_number}"},
    )
    sync_item_alert(db, user, item, "stock")  # resolves the low-stock alert if stock is back above the level
    return {"item_name": item.name, "unit": item.unit, "added": quantity, "new_quantity": after}


def receive_delivery(db: Session, user: User, order_id: int, data: ReceiveDelivery) -> dict:
    order = _tracked_row(db, user.business_id, order_id)
    if order.inventory_applied or order.status == PO_DELIVERED:
        raise TrackingError("This delivery was already confirmed. Stock was updated once and cannot be added again.", 409)
    if order.status not in PO_RECEIVABLE:
        raise TrackingError(
            f"An order that is {_label(order.status)} cannot receive a delivery. "
            "Place the order with the supplier first.", 409,
        )

    lines = {line.id: line for line in order.lines}
    received: dict[int, int] = {}
    for entry in data.lines:
        if entry.line_id not in lines:
            raise TrackingError("One of the lines does not belong to this order.", 404)
        if entry.line_id in received:
            raise TrackingError("The same order line was sent twice.", 422)
        received[entry.line_id] = entry.received_quantity
    if set(received) != set(lines):
        raise TrackingError("Enter the received quantity for every line of the order.", 422)
    if sum(received.values()) < 1:
        raise TrackingError("Nothing was received. Enter at least one received item, or leave the order as it is.", 422)

    items = {i.id: i for i in db.scalars(select(InventoryItem).where(InventoryItem.id.in_([l.item_id for l in order.lines])))}
    for line in order.lines:
        if received[line.id] > 0 and items[line.item_id].is_archived:
            raise TrackingError(
                f"{items[line.item_id].name} is archived. Restore the product before receiving it.", 409
            )

    old_status = order.status
    ordered_total = sum(l.quantity_ordered for l in order.lines)
    received_total = sum(received.values())
    short = ordered_total > received_total
    stock_updates: list[dict] = []

    try:
        # Claim the delivery: only ONE request can flip inventory_applied from 0 to 1.
        claim = db.execute(
            update(PurchaseOrder)
            .where(
                PurchaseOrder.id == order.id,
                PurchaseOrder.business_id == order.business_id,
                PurchaseOrder.inventory_applied.is_(False),
                PurchaseOrder.status.in_(PO_RECEIVABLE),
            )
            .values(status=PO_DELIVERED, inventory_applied=True, updated_at=utcnow())
        )
        if claim.rowcount == 0:
            db.rollback()
            raise TrackingError("This delivery was just confirmed by someone else. Refresh the page.", 409)

        for line in order.lines:
            quantity = received[line.id]
            db.execute(
                update(PurchaseOrderItem)
                .where(PurchaseOrderItem.id == line.id)
                .values(received_quantity=quantity, outstanding=False)  # the product is free for a new order
            )
            if quantity > 0:
                stock_updates.append(_add_received_stock(db, user, order, line, items[line.item_id], quantity))

        note = data.note or ("Delivery confirmed (SHORT: less than ordered)" if short else "Delivery confirmed")
        record_history(db, order, user, old_status, PO_DELIVERED, note)
        log_activity(
            db, user, "po.delivered", "purchase_order", order.id,
            f"Delivery confirmed for {order.po_number}: {received_total} of {ordered_total} items received"
            + (" (short delivery)" if short else ""),
            old_value={"status": old_status},
            new_value={
                "status": PO_DELIVERED,
                "ordered": ordered_total,
                "received": received_total,
                "short_delivery": short,
                "lines": {items[lines[lid].item_id].sku: qty for lid, qty in received.items()},
                "note": data.note,
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise TrackingError("This delivery was already recorded. Stock was not changed again.", 409)

    # After the delivery is saved: if a short delivery left a product low, prepare a new DRAFT
    # (never an approved order). Best effort: it cannot affect the delivery that was saved.
    follow_ups: list[str] = []
    for line in order.lines:
        item = db.get(InventoryItem, line.item_id)
        db.refresh(item)
        if not item.is_archived and item.stock_status != "in_stock":
            draft = purchase_order_service.auto_draft_for_item(db, user, item.id)
            if draft and draft["po_number"] not in follow_ups:
                follow_ups.append(draft["po_number"])

    return {
        "order": get_order(db, user.business_id, order_id),
        "stock_updates": stock_updates,
        "follow_up_drafts": follow_ups,
    }
