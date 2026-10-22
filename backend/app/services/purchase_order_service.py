"""Purchase order logic (Feature 3).

The workflow this file implements:

    Low-stock alert (Feature 2)
      -> Decision logic: which supplier, how many units, what price
      -> Draft purchase order (nothing is ordered yet)
      -> Human approval: only the owner can approve or reject
      -> Activity log entry at every step

Rules (also written in docs/DECISIONS.md):
  * Reorder quantity: refill up to 2 x the reorder level, but never less than the
    supplier's minimum order.        e.g. milk 5 left, level 10 -> 20 - 5 = 15 cartons.
  * Supplier: the cheapest active supplier that sells the product (tie: shorter delivery time).
  * One draft per supplier: new products for the same supplier are added to the open draft.
  * No duplicates: a product can be on only ONE outstanding order (checked in code AND
    enforced by a database index).
  * Nothing is placed automatically. Drafts need the owner's approval.

Every function that changes data commits ONCE at the end, together with its audit-log row.
"""
import logging
import os
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import (
    ALERT_OPEN,
    PO_APPROVED,
    PO_AWAITING_DECISION,
    PO_DRAFT,
    PO_REJECTED,
    PO_SOURCE_AUTO,
    PO_STATUSES,
    RESTOCK_TARGET_MULTIPLIER,
)
from app.database import utcnow
from app.models import (
    InventoryItem,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierProduct,
    User,
)
from app.services.activity_service import log_activity
from app.services.alert_service import list_alerts
from app.schemas.purchase_order import OrderReject, OrderUpdate

logger = logging.getLogger(__name__)


class OrderError(Exception):
    """A rule was broken. `status_code` tells the router which HTTP error to send."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ------------------------------------------------------------------ small helpers

def rm(sen: int) -> float:
    """Sen (whole number) -> RM for display. Money is stored in sen to avoid rounding errors."""
    return round(sen / 100, 2)


def recommended_quantity(quantity: int, threshold: int, min_order_qty: int) -> int:
    """How many units to order.

    Refill up to RESTOCK_TARGET_MULTIPLIER x the reorder level (2 x), but at least 1
    unit and at least the supplier's minimum order. Feature 8 (forecasting) will improve this.
    """
    target = RESTOCK_TARGET_MULTIPLIER * threshold
    return max(target - quantity, 1, min_order_qty)


def _label(status: str) -> str:
    return status.replace("_", " ")


def _best_offer(db: Session, business_id: int, item_id: int) -> tuple[SupplierProduct, Supplier] | None:
    """Pick the supplier: cheapest active price; ties go to the shorter delivery time."""
    row = db.execute(
        select(SupplierProduct, Supplier)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.business_id == business_id,
            SupplierProduct.item_id == item_id,
            SupplierProduct.is_active.is_(True),
            Supplier.is_active.is_(True),
        )
        .order_by(SupplierProduct.unit_price_sen, Supplier.typical_lead_time_days, SupplierProduct.id)
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def _outstanding_order_for(db: Session, item_id: int) -> PurchaseOrder | None:
    return db.scalar(
        select(PurchaseOrder)
        .join(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .where(PurchaseOrderItem.item_id == item_id, PurchaseOrderItem.outstanding.is_(True))
    )


def _next_po_number(db: Session, business_id: int) -> str:
    count = db.scalar(select(func.count()).where(PurchaseOrder.business_id == business_id)) or 0
    return f"PO-{count + 1:04d}"


def _order_total_sen(order: PurchaseOrder) -> int:
    return sum(line.quantity_ordered * line.unit_price_sen for line in order.lines)


# ------------------------------------------------------------------ detecting needs

def _compute_needs(db: Session, business_id: int, item_ids: list[int] | None = None):
    """Products with an OPEN low-stock alert and no outstanding order yet.

    Returns a list of (need_dict, SupplierProduct | None, Supplier | None).
    The supplier part is None when no supplier price exists (the draft cannot be made).
    """
    results = []
    for alert in list_alerts(db, business_id, ALERT_OPEN):
        if item_ids is not None and alert["item_id"] not in item_ids:
            continue
        if _outstanding_order_for(db, alert["item_id"]) is not None:
            continue  # already covered by an order: no duplicate
        offer = _best_offer(db, business_id, alert["item_id"])
        need = {
            "item_id": alert["item_id"],
            "item_name": alert["item_name"],
            "sku": alert["sku"],
            "unit": alert["unit"],
            "quantity": alert["quantity"],
            "reorder_threshold": alert["reorder_threshold"],
            "urgency": alert["urgency"],
            "recommended_quantity": None,
            "supplier_id": None,
            "supplier_name": None,
            "unit_price": None,
            "estimated_total": None,
            "lead_time_days": None,
            "blocked_reason": None,
        }
        if offer is None:
            need["blocked_reason"] = "No supplier price on file for this product."
            results.append((need, None, None))
            continue
        product_offer, supplier = offer
        qty = recommended_quantity(alert["quantity"], alert["reorder_threshold"], product_offer.min_order_qty)
        need.update(
            recommended_quantity=qty,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            unit_price=rm(product_offer.unit_price_sen),
            estimated_total=rm(qty * product_offer.unit_price_sen),
            lead_time_days=supplier.typical_lead_time_days,
        )
        results.append((need, product_offer, supplier))
    return results


def list_needs(db: Session, business_id: int) -> list[dict]:
    return [need for need, _offer, _supplier in _compute_needs(db, business_id)]


# ------------------------------------------------------------------ reading orders

def _eligible_suppliers(db: Session, order: PurchaseOrder) -> list[dict]:
    """Suppliers that sell EVERY product on the order (so the supplier can be switched)."""
    item_ids = [line.item_id for line in order.lines]
    if not item_ids:
        return []
    rows = db.execute(
        select(SupplierProduct, Supplier)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.business_id == order.business_id,
            SupplierProduct.item_id.in_(item_ids),
            SupplierProduct.is_active.is_(True),
            Supplier.is_active.is_(True),
        )
    ).all()
    by_supplier: dict[int, dict] = {}
    for product_offer, supplier in rows:
        entry = by_supplier.setdefault(supplier.id, {"supplier": supplier, "offers": {}})
        entry["offers"][product_offer.item_id] = product_offer

    eligible = []
    for entry in by_supplier.values():
        offers = entry["offers"]
        if all(line.item_id in offers for line in order.lines):
            total = sum(line.quantity_ordered * offers[line.item_id].unit_price_sen for line in order.lines)
            eligible.append(
                {
                    "id": entry["supplier"].id,
                    "name": entry["supplier"].name,
                    "lead_time_days": entry["supplier"].typical_lead_time_days,
                    "total": rm(total),
                }
            )
    eligible.sort(key=lambda row: (row["total"], row["name"]))
    return eligible


def _order_dict(db: Session, order: PurchaseOrder) -> dict:
    supplier = db.get(Supplier, order.supplier_id)
    item_ids = [line.item_id for line in order.lines]
    items = {
        item.id: item
        for item in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids)))
    } if item_ids else {}
    min_orders = {
        offer.item_id: offer.min_order_qty
        for offer in db.scalars(
            select(SupplierProduct).where(
                SupplierProduct.supplier_id == order.supplier_id,
                SupplierProduct.item_id.in_(item_ids),
            )
        )
    } if item_ids else {}

    lines = []
    for line in order.lines:
        item = items[line.item_id]
        lines.append(
            {
                "id": line.id,
                "item_id": item.id,
                "item_name": item.name,
                "sku": item.sku,
                "unit": item.unit,
                "quantity_ordered": line.quantity_ordered,
                "recommended_quantity": line.recommended_quantity,
                "unit_price": rm(line.unit_price_sen),
                "line_total": rm(line.quantity_ordered * line.unit_price_sen),
                "min_order_qty": min_orders.get(line.item_id),
                "current_quantity": item.quantity,
                "reorder_threshold": item.reorder_threshold,
            }
        )

    creator = db.get(User, order.created_by_user_id) if order.created_by_user_id else None
    decider = db.get(User, order.decided_by_user_id) if order.decided_by_user_id else None
    editable = order.status in PO_AWAITING_DECISION
    return {
        "id": order.id,
        "po_number": order.po_number,
        "status": order.status,
        "source": order.source,
        "notes": order.notes,
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "contact_name": supplier.contact_name,
            "phone": supplier.phone,
            "email": supplier.email,
            "lead_time_days": supplier.typical_lead_time_days,
        },
        "estimated_delivery_date": order.estimated_delivery_date,
        "total": rm(_order_total_sen(order)),
        "lines": lines,
        "created_by_name": creator.name if creator else None,
        "decided_by_name": decider.name if decider else None,
        "decided_at": order.decided_at,
        "decision_note": order.decision_note,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "is_editable": editable,
        "eligible_suppliers": _eligible_suppliers(db, order) if editable else [],
    }


def _get_order_row(db: Session, business_id: int, order_id: int) -> PurchaseOrder:
    order = db.scalar(
        select(PurchaseOrder).where(PurchaseOrder.id == order_id, PurchaseOrder.business_id == business_id)
    )
    if order is None:
        raise OrderError("Purchase order not found.", 404)
    return order


def get_order(db: Session, business_id: int, order_id: int) -> dict:
    db.expire_all()  # make sure we read what is really in the database
    return _order_dict(db, _get_order_row(db, business_id, order_id))


def list_orders(db: Session, business_id: int, status: str = "all") -> list[dict]:
    """status: 'all', 'awaiting' (draft + pending approval) or one exact status."""
    query = select(PurchaseOrder).where(PurchaseOrder.business_id == business_id)
    if status == "awaiting":
        query = query.where(PurchaseOrder.status.in_(PO_AWAITING_DECISION))
    elif status != "all":
        if status not in PO_STATUSES:
            raise OrderError("Invalid status filter.", 422)
        query = query.where(PurchaseOrder.status == status)
    query = query.order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
    db.expire_all()
    return [_order_dict(db, order) for order in db.scalars(query)]


def get_summary(db: Session, business_id: int) -> dict:
    counts = dict(
        db.execute(
            select(PurchaseOrder.status, func.count())
            .where(PurchaseOrder.business_id == business_id)
            .group_by(PurchaseOrder.status)
        ).all()
    )
    awaiting_sen = db.scalar(
        select(func.coalesce(func.sum(PurchaseOrderItem.quantity_ordered * PurchaseOrderItem.unit_price_sen), 0))
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .where(PurchaseOrder.business_id == business_id, PurchaseOrder.status.in_(PO_AWAITING_DECISION))
    )
    needs = _compute_needs(db, business_id)
    return {
        "awaiting_approval": sum(counts.get(status, 0) for status in PO_AWAITING_DECISION),
        "approved": counts.get(PO_APPROVED, 0),
        "rejected": counts.get(PO_REJECTED, 0),
        "awaiting_value": rm(awaiting_sen or 0),
        "needs_ordering": sum(1 for _need, offer, _s in needs if offer is not None),
        "no_supplier": sum(1 for _need, offer, _s in needs if offer is None),
    }


# ------------------------------------------------------------------ generating drafts

def _generate_once(db: Session, user: User, source: str, item_ids: list[int] | None) -> dict:
    computed = _compute_needs(db, user.business_id, item_ids)

    skipped = [
        {"item_id": need["item_id"], "item_name": need["item_name"], "reason": need["blocked_reason"]}
        for need, offer, _supplier in computed
        if offer is None
    ]

    groups: dict[int, list] = {}
    for need, product_offer, supplier in computed:
        if product_offer is not None:
            groups.setdefault(supplier.id, []).append((need, product_offer, supplier))

    created_orders = 0
    lines_added = 0
    touched_ids: list[int] = []

    for supplier_id, entries in groups.items():
        supplier = entries[0][2]
        # One open DRAFT per supplier: add to it if it exists, otherwise start a new one.
        order = db.scalar(
            select(PurchaseOrder)
            .where(
                PurchaseOrder.business_id == user.business_id,
                PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.status == PO_DRAFT,
            )
            .order_by(PurchaseOrder.id.desc())
            .limit(1)
        )
        is_new = order is None
        old_total = 0 if is_new else rm(_order_total_sen(order))
        if is_new:
            order = PurchaseOrder(
                business_id=user.business_id,
                po_number=_next_po_number(db, user.business_id),
                supplier_id=supplier_id,
                status=PO_DRAFT,
                source=source,
                created_by_user_id=user.id,
                estimated_delivery_date=(utcnow() + timedelta(days=supplier.typical_lead_time_days)).date(),
            )
            db.add(order)
            db.flush()  # gives the order an id

        added = []
        for need, product_offer, _supplier in entries:
            qty = need["recommended_quantity"]
            db.add(
                PurchaseOrderItem(
                    business_id=user.business_id,
                    purchase_order_id=order.id,
                    item_id=need["item_id"],
                    quantity_ordered=qty,
                    recommended_quantity=qty,
                    unit_price_sen=product_offer.unit_price_sen,
                    outstanding=True,
                )
            )
            added.append(
                {"sku": need["sku"], "name": need["item_name"], "quantity": qty, "unit_price": need["unit_price"]}
            )
        db.flush()  # the unique index rejects a duplicate outstanding line right here
        db.expire(order, ["lines"])  # reload `lines` so the total includes the new rows
        new_total = rm(_order_total_sen(order))
        order.updated_at = utcnow()

        if is_new:
            log_activity(
                db, user, "po.generated", "purchase_order", order.id,
                f"Draft {order.po_number} prepared for {supplier.name}: {len(added)} product(s), RM {new_total:.2f}",
                new_value={
                    "po_number": order.po_number, "supplier": supplier.name, "status": PO_DRAFT,
                    "source": source, "lines": added, "total": new_total,
                },
            )
            created_orders += 1
        else:
            log_activity(
                db, user, "po.updated", "purchase_order", order.id,
                f"Added {len(added)} product(s) to draft {order.po_number} ({supplier.name}): "
                f"RM {old_total:.2f} -> RM {new_total:.2f}",
                old_value={"total": old_total},
                new_value={"added": added, "total": new_total, "source": source},
            )
        lines_added += len(added)
        touched_ids.append(order.id)

    db.commit()
    return {
        "created_orders": created_orders,
        "lines_added": lines_added,
        "skipped": skipped,
        "order_ids": touched_ids,
    }


def generate_drafts(db: Session, user: User, source: str, item_ids: list[int] | None = None) -> dict:
    """Create purchase order DRAFTS for products that need restocking. Never approves anything."""
    for attempt in (1, 2):
        try:
            result = _generate_once(db, user, source, item_ids)
            break
        except IntegrityError:
            # Another request created an order for the same product at the same moment.
            # Start over: the second pass sees that order and skips the product.
            db.rollback()
            if attempt == 2:
                raise OrderError("Could not prepare the order drafts. Please try again.", 409)
    db.expire_all()
    result["orders"] = [
        _order_dict(db, _get_order_row(db, user.business_id, order_id)) for order_id in result.pop("order_ids")
    ]
    return result


def auto_draft_for_item(db: Session, user: User, item_id: int) -> dict | None:
    """Called by the inventory routes after a stock change. If the product now has an open
    low-stock alert and no order yet, prepare a draft. Returns {'id', 'po_number'} when a
    line was added, otherwise None.

    This is best-effort: if anything goes wrong the stock change that already happened is
    NOT affected. Set AUTO_GENERATE_PO=false in .env to switch the automatic drafting off
    (the 'Check restocking needs' button still works)."""
    if os.getenv("AUTO_GENERATE_PO", "true").lower() != "true":
        return None
    try:
        result = generate_drafts(db, user, PO_SOURCE_AUTO, [item_id])
        if result["lines_added"] == 0:
            return None
        order = _outstanding_order_for(db, item_id)
        return {"id": order.id, "po_number": order.po_number} if order else None
    except Exception:  # noqa: BLE001 - must never break the stock change
        db.rollback()
        logger.exception("Automatic purchase order draft failed for item %s", item_id)
        return None


# ------------------------------------------------------------------ editing / deciding

def _require_editable(order: PurchaseOrder) -> None:
    if order.status not in PO_AWAITING_DECISION:
        raise OrderError(
            f"This order is already {_label(order.status)} and can no longer be edited.", 409
        )


def _guard_still_editable(db: Session, order: PurchaseOrder) -> None:
    """Last check inside the transaction: the order must STILL be waiting for a decision.
    Stops an edit from sneaking in after someone approved the order a moment earlier."""
    result = db.execute(
        update(PurchaseOrder)
        .where(
            PurchaseOrder.id == order.id,
            PurchaseOrder.business_id == order.business_id,
            PurchaseOrder.status.in_(PO_AWAITING_DECISION),
        )
        .values(updated_at=utcnow())
    )
    if result.rowcount == 0:
        db.rollback()
        raise OrderError("This order was just decided by someone else. Refresh the page.", 409)


def _snapshot(db: Session, order: PurchaseOrder) -> dict:
    supplier = db.get(Supplier, order.supplier_id)
    items = {i.id: i for i in db.scalars(select(InventoryItem).where(InventoryItem.business_id == order.business_id))}
    return {
        "supplier": supplier.name,
        "notes": order.notes,
        "lines": {items[line.item_id].sku: line.quantity_ordered for line in order.lines},
        "total": rm(_order_total_sen(order)),
    }


def update_order(db: Session, user: User, order_id: int, data: OrderUpdate) -> dict:
    order = _get_order_row(db, user.business_id, order_id)
    _require_editable(order)
    old = _snapshot(db, order)

    line_by_id = {line.id: line for line in order.lines}
    new_quantities = {line.id: line.quantity_ordered for line in order.lines}
    if data.lines is not None:
        seen: set[int] = set()
        for entry in data.lines:
            if entry.line_id not in line_by_id:
                raise OrderError("One of the order lines does not belong to this order.", 404)
            if entry.line_id in seen:
                raise OrderError("The same order line was sent twice.", 422)
            seen.add(entry.line_id)
            new_quantities[entry.line_id] = entry.quantity

    supplier = db.get(Supplier, order.supplier_id)
    supplier_changed = data.supplier_id is not None and data.supplier_id != order.supplier_id
    if supplier_changed:
        supplier = db.scalar(
            select(Supplier).where(
                Supplier.id == data.supplier_id,
                Supplier.business_id == user.business_id,
                Supplier.is_active.is_(True),
            )
        )
        if supplier is None:
            raise OrderError("Supplier not found.", 404)

    offers = {
        offer.item_id: offer
        for offer in db.scalars(
            select(SupplierProduct).where(
                SupplierProduct.supplier_id == supplier.id,
                SupplierProduct.business_id == user.business_id,
                SupplierProduct.is_active.is_(True),
            )
        )
    }
    items = {i.id: i for i in db.scalars(select(InventoryItem).where(InventoryItem.business_id == user.business_id))}

    for line in order.lines:
        offer = offers.get(line.item_id)
        name = items[line.item_id].name
        if supplier_changed and offer is None:
            raise OrderError(f"{supplier.name} does not sell {name}.", 422)
        quantity_changed = new_quantities[line.id] != line.quantity_ordered
        if offer is not None and (quantity_changed or supplier_changed) and new_quantities[line.id] < offer.min_order_qty:
            raise OrderError(
                f"The minimum order for {name} from {supplier.name} is {offer.min_order_qty}.", 422
            )

    for line in order.lines:
        line.quantity_ordered = new_quantities[line.id]
        if supplier_changed:
            line.unit_price_sen = offers[line.item_id].unit_price_sen
    if supplier_changed:
        order.supplier_id = supplier.id
        order.estimated_delivery_date = (utcnow() + timedelta(days=supplier.typical_lead_time_days)).date()
    if "notes" in data.model_fields_set:
        order.notes = data.notes or None

    new = _snapshot(db, order)
    if new == old:
        return _order_dict(db, order)  # nothing changed: no write, no log entry

    changed = [key for key in new if new[key] != old[key]]
    order.updated_at = utcnow()
    log_activity(
        db, user, "po.updated", "purchase_order", order.id,
        f"Edited draft {order.po_number}: {', '.join(changed)} (total RM {old['total']:.2f} -> RM {new['total']:.2f})",
        old_value={key: old[key] for key in changed},
        new_value={key: new[key] for key in changed},
    )
    _guard_still_editable(db, order)
    db.commit()
    return get_order(db, user.business_id, order_id)


def remove_line(db: Session, user: User, order_id: int, line_id: int) -> dict:
    order = _get_order_row(db, user.business_id, order_id)
    _require_editable(order)
    line = next((candidate for candidate in order.lines if candidate.id == line_id), None)
    if line is None:
        raise OrderError("Order line not found.", 404)
    if len(order.lines) == 1:
        raise OrderError("An order needs at least one product. Reject the order instead.", 409)

    item = db.get(InventoryItem, line.item_id)
    old_total = rm(_order_total_sen(order))
    removed = {"sku": item.sku, "name": item.name, "quantity": line.quantity_ordered}
    db.delete(line)
    db.flush()
    db.expire(order, ["lines"])
    new_total = rm(_order_total_sen(order))
    order.updated_at = utcnow()
    log_activity(
        db, user, "po.line_removed", "purchase_order", order.id,
        f"Removed {item.name} from draft {order.po_number} (total RM {old_total:.2f} -> RM {new_total:.2f})",
        old_value={"line": removed, "total": old_total},
        new_value={"total": new_total},
    )
    _guard_still_editable(db, order)
    db.commit()
    return get_order(db, user.business_id, order_id)


def approve_order(db: Session, user: User, order_id: int) -> dict:
    """OWNER ONLY (the router enforces it). Approving does NOT contact the supplier:
    placing the order with the supplier is a simulated action in Feature 5."""
    order = _get_order_row(db, user.business_id, order_id)
    if order.status not in PO_AWAITING_DECISION:
        raise OrderError(f"This order is already {_label(order.status)}.", 409)

    items = {i.id: i for i in db.scalars(select(InventoryItem).where(InventoryItem.business_id == user.business_id))}
    for line in order.lines:
        if items[line.item_id].is_archived:
            raise OrderError(
                f"{items[line.item_id].name} is archived. Remove it from the order or restore the product first.", 409
            )

    old_status = order.status
    total = rm(_order_total_sen(order))
    supplier = db.get(Supplier, order.supplier_id)
    now = utcnow()
    result = db.execute(
        update(PurchaseOrder)
        .where(
            PurchaseOrder.id == order.id,
            PurchaseOrder.business_id == user.business_id,
            PurchaseOrder.status.in_(PO_AWAITING_DECISION),  # decided only once
        )
        .values(status=PO_APPROVED, decided_by_user_id=user.id, decided_at=now, updated_at=now)
    )
    if result.rowcount == 0:
        db.rollback()
        raise OrderError("This order was just decided by someone else. Refresh the page.", 409)

    log_activity(
        db, user, "po.approved", "purchase_order", order.id,
        f"Approved {order.po_number} for {supplier.name}: RM {total:.2f}",
        old_value={"status": old_status},
        new_value={"status": PO_APPROVED, "total": total, "supplier": supplier.name, "decision": "approved"},
    )
    db.commit()
    return get_order(db, user.business_id, order_id)


def reject_order(db: Session, user: User, order_id: int, data: OrderReject) -> dict:
    """OWNER ONLY. A rejected order stops blocking its products, so a new draft can be made."""
    order = _get_order_row(db, user.business_id, order_id)
    if order.status not in PO_AWAITING_DECISION:
        raise OrderError(f"This order is already {_label(order.status)}.", 409)

    old_status = order.status
    total = rm(_order_total_sen(order))
    now = utcnow()
    result = db.execute(
        update(PurchaseOrder)
        .where(
            PurchaseOrder.id == order.id,
            PurchaseOrder.business_id == user.business_id,
            PurchaseOrder.status.in_(PO_AWAITING_DECISION),
        )
        .values(
            status=PO_REJECTED, decided_by_user_id=user.id, decided_at=now,
            decision_note=data.reason, updated_at=now,
        )
    )
    if result.rowcount == 0:
        db.rollback()
        raise OrderError("This order was just decided by someone else. Refresh the page.", 409)

    db.execute(
        update(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order.id).values(outstanding=False)
    )
    log_activity(
        db, user, "po.rejected", "purchase_order", order.id,
        f"Rejected {order.po_number} (RM {total:.2f}): {data.reason}"[:255],
        old_value={"status": old_status},
        new_value={"status": PO_REJECTED, "reason": data.reason, "decision": "rejected"},
    )
    db.commit()
    return get_order(db, user.business_id, order_id)
