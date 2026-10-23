"""Supplier management (Feature 6).

What this file does:
  * add, edit, deactivate and re-activate suppliers (contact details, typical delivery time)
  * keep each supplier's PRICE LIST: which products it sells, at what price, minimum order
  * show each supplier's order history and simple delivery statistics

How it connects to the rest of the system:
  * Purchase order drafts (Feature 3) pick "the cheapest ACTIVE supplier that sells the
    product". This file is where those prices and the active flag are maintained.
  * Changing a price only affects orders prepared AFTER the change. An order that already
    exists keeps the price it was prepared with, so the owner approves exactly what was shown.
  * Adding a price for a low product that had no supplier lets the system prepare a draft
    straight away (the same best-effort rule as a stock change).

Rules (also in docs/DECISIONS.md):
  * Supplier names are unique per business (not case-sensitive).
  * Suppliers are never deleted: their order history must stay. They are deactivated instead.
  * A supplier with unfinished orders cannot be deactivated (finish, reject or cancel them first).
  * A product can be on a supplier's price list once. Another business's product -> 404.
  * Every change writes an audit-log row in the same transaction.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import (
    PO_CANCELLED,
    PO_DELIVERED,
    PO_ORDERED,
    PO_OUTSTANDING,
    PO_REJECTED,
)
from app.database import utcnow
from app.models import (
    InventoryItem,
    OrderStatusHistory,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    SupplierProduct,
    User,
)
from app.schemas.supplier import (
    SupplierCreate,
    SupplierProductCreate,
    SupplierProductUpdate,
    SupplierUpdate,
    price_to_sen,
)
from app.services import purchase_order_service
from app.services.activity_service import log_activity

# Malaysia is UTC+8 all year. Used to turn stored UTC times into Malaysian calendar dates.
MALAYSIA_OFFSET = timedelta(hours=8)


class SupplierError(Exception):
    """A rule was broken. `status_code` tells the router which HTTP error to send."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ------------------------------------------------------------------ small helpers

def _rm(sen: int | None) -> float:
    return round((sen or 0) / 100, 2)


def _my_date(moment: datetime):
    return (moment + MALAYSIA_OFFSET).date()


def _snapshot(supplier: Supplier) -> dict:
    """The fields shown in the audit log (before / after)."""
    return {
        "name": supplier.name,
        "contact_name": supplier.contact_name,
        "phone": supplier.phone,
        "email": supplier.email,
        "address": supplier.address,
        "notes": supplier.notes,
        "lead_time_days": supplier.typical_lead_time_days,
        "is_active": supplier.is_active,
    }


def _get_supplier(db: Session, business_id: int, supplier_id: int) -> Supplier:
    supplier = db.scalar(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.business_id == business_id)
    )
    if supplier is None:
        raise SupplierError("Supplier not found.", 404)
    return supplier


def _name_taken(db: Session, business_id: int, name: str, ignore_id: int | None = None) -> bool:
    query = select(Supplier.id).where(
        Supplier.business_id == business_id, func.lower(Supplier.name) == name.lower()
    )
    if ignore_id is not None:
        query = query.where(Supplier.id != ignore_id)
    return db.scalar(query.limit(1)) is not None


def _order_counts(db: Session, business_id: int) -> dict[int, dict]:
    """Per supplier: open orders, delivered orders, value received, last order time."""
    stats: dict[int, dict] = {}
    rows = db.execute(
        select(PurchaseOrder.supplier_id, PurchaseOrder.status, func.count(), func.max(PurchaseOrder.created_at))
        .where(PurchaseOrder.business_id == business_id)
        .group_by(PurchaseOrder.supplier_id, PurchaseOrder.status)
    ).all()
    for supplier_id, status, count, last_created in rows:
        entry = stats.setdefault(
            supplier_id, {"open_orders": 0, "delivered_orders": 0, "delivered_sen": 0, "last_order_at": None}
        )
        if status in PO_OUTSTANDING:
            entry["open_orders"] += count
        if status == PO_DELIVERED:
            entry["delivered_orders"] += count
        if last_created is not None and (entry["last_order_at"] is None or last_created > entry["last_order_at"]):
            entry["last_order_at"] = last_created

    received = db.execute(
        select(
            PurchaseOrder.supplier_id,
            func.coalesce(func.sum(PurchaseOrderItem.received_quantity * PurchaseOrderItem.unit_price_sen), 0),
        )
        .join(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .where(PurchaseOrder.business_id == business_id, PurchaseOrder.status == PO_DELIVERED)
        .group_by(PurchaseOrder.supplier_id)
    ).all()
    for supplier_id, total_sen in received:
        stats.setdefault(
            supplier_id, {"open_orders": 0, "delivered_orders": 0, "delivered_sen": 0, "last_order_at": None}
        )["delivered_sen"] = total_sen or 0
    return stats


def _product_counts(db: Session, business_id: int) -> dict[int, int]:
    """Per supplier: products on the price list (archived products are not counted)."""
    rows = db.execute(
        select(SupplierProduct.supplier_id, func.count())
        .join(InventoryItem, InventoryItem.id == SupplierProduct.item_id)
        .where(
            SupplierProduct.business_id == business_id,
            SupplierProduct.is_active.is_(True),
            InventoryItem.is_archived.is_(False),
        )
        .group_by(SupplierProduct.supplier_id)
    ).all()
    return {supplier_id: count for supplier_id, count in rows}


def _list_dict(supplier: Supplier, orders: dict[int, dict], products: dict[int, int]) -> dict:
    entry = orders.get(supplier.id, {})
    return {
        "id": supplier.id,
        "name": supplier.name,
        "contact_name": supplier.contact_name,
        "phone": supplier.phone,
        "email": supplier.email,
        "address": supplier.address,
        "notes": supplier.notes,
        "lead_time_days": supplier.typical_lead_time_days,
        "is_active": supplier.is_active,
        "product_count": products.get(supplier.id, 0),
        "open_orders": entry.get("open_orders", 0),
        "delivered_orders": entry.get("delivered_orders", 0),
        "delivered_value": _rm(entry.get("delivered_sen", 0)),
        "last_order_at": entry.get("last_order_at"),
        "created_at": supplier.created_at,
        # Suppliers from before Feature 6 have no updated_at yet
        "updated_at": supplier.updated_at or supplier.created_at,
    }


# ------------------------------------------------------------------ reading

def list_suppliers(
    db: Session, business_id: int, include_inactive: bool = False, search: str | None = None
) -> list[dict]:
    db.expire_all()
    query = select(Supplier).where(Supplier.business_id == business_id)
    if not include_inactive:
        query = query.where(Supplier.is_active.is_(True))
    if search and search.strip():
        term = search.strip().lower()
        escaped = term.replace("/", "//").replace("%", "/%").replace("_", "/_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(
                func.lower(Supplier.name).like(pattern, escape="/"),
                func.lower(func.coalesce(Supplier.contact_name, "")).like(pattern, escape="/"),
                func.lower(func.coalesce(Supplier.email, "")).like(pattern, escape="/"),
                func.lower(func.coalesce(Supplier.phone, "")).like(pattern, escape="/"),
            )
        )
    query = query.order_by(Supplier.is_active.desc(), func.lower(Supplier.name))
    orders = _order_counts(db, business_id)
    products = _product_counts(db, business_id)
    return [_list_dict(supplier, orders, products) for supplier in db.scalars(query)]


def _supplied_item_ids(db: Session, business_id: int) -> set[int]:
    """Products that at least one ACTIVE supplier sells (so they can be reordered)."""
    return set(
        db.scalars(
            select(SupplierProduct.item_id)
            .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
            .where(
                SupplierProduct.business_id == business_id,
                SupplierProduct.is_active.is_(True),
                Supplier.is_active.is_(True),
            )
        )
    )


def products_without_supplier(db: Session, business_id: int) -> list[dict]:
    """Active products that no active supplier sells. They cannot get a purchase order draft."""
    db.expire_all()
    supplied = _supplied_item_ids(db, business_id)
    items = db.scalars(
        select(InventoryItem)
        .where(InventoryItem.business_id == business_id, InventoryItem.is_archived.is_(False))
        .order_by(func.lower(InventoryItem.name))
    )
    rows = [
        {
            "item_id": item.id,
            "item_name": item.name,
            "sku": item.sku,
            "category": item.category,
            "unit": item.unit,
            "quantity": item.quantity,
            "reorder_threshold": item.reorder_threshold,
            "stock_status": item.stock_status,
            "supplier_label": item.supplier_name,
        }
        for item in items
        if item.id not in supplied
    ]
    # Low and out-of-stock products first: those are the ones that cannot be reordered right now
    rows.sort(key=lambda row: (row["stock_status"] == "in_stock", row["item_name"].lower()))
    return rows


def get_summary(db: Session, business_id: int) -> dict:
    db.expire_all()
    suppliers = list(db.scalars(select(Supplier).where(Supplier.business_id == business_id)))
    active = [s for s in suppliers if s.is_active]
    items = list(
        db.scalars(
            select(InventoryItem).where(InventoryItem.business_id == business_id, InventoryItem.is_archived.is_(False))
        )
    )
    supplied = _supplied_item_ids(db, business_id)
    without = [item for item in items if item.id not in supplied]
    return {
        "active": len(active),
        "inactive": len(suppliers) - len(active),
        "products_with_supplier": len(items) - len(without),
        "products_without_supplier": len(without),
        "low_without_supplier": sum(1 for item in without if item.stock_status != "in_stock"),
        "average_lead_time_days": (
            round(sum(s.typical_lead_time_days for s in active) / len(active), 1) if active else None
        ),
    }


def _price_list(db: Session, supplier: Supplier) -> list[dict]:
    rows = db.execute(
        select(SupplierProduct, InventoryItem)
        .join(InventoryItem, InventoryItem.id == SupplierProduct.item_id)
        .where(
            SupplierProduct.supplier_id == supplier.id,
            SupplierProduct.business_id == supplier.business_id,
            SupplierProduct.is_active.is_(True),
        )
        .order_by(InventoryItem.is_archived, func.lower(InventoryItem.name))
    ).all()
    item_ids = [item.id for _link, item in rows]

    # How many OTHER active suppliers sell each product (one query)
    others: dict[int, int] = {}
    if item_ids:
        for item_id, count in db.execute(
            select(SupplierProduct.item_id, func.count())
            .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
            .where(
                SupplierProduct.business_id == supplier.business_id,
                SupplierProduct.item_id.in_(item_ids),
                SupplierProduct.supplier_id != supplier.id,
                SupplierProduct.is_active.is_(True),
                Supplier.is_active.is_(True),
            )
            .group_by(SupplierProduct.item_id)
        ):
            others[item_id] = count

    products = []
    for link, item in rows:
        # Same rule the purchase order drafts use, so this can never disagree with Feature 3
        best = purchase_order_service._best_offer(db, supplier.business_id, item.id)
        products.append(
            {
                "id": link.id,
                "item_id": item.id,
                "item_name": item.name,
                "sku": item.sku,
                "category": item.category,
                "unit": item.unit,
                "unit_price": _rm(link.unit_price_sen),
                "min_order_qty": link.min_order_qty,
                "current_quantity": item.quantity,
                "reorder_threshold": item.reorder_threshold,
                "stock_status": item.stock_status,
                "item_archived": item.is_archived,
                "other_suppliers": others.get(item.id, 0),
                "chosen_for_auto_orders": best is not None and best[1].id == supplier.id,
            }
        )
    return products


def _order_history(db: Session, supplier: Supplier) -> tuple[list[dict], dict]:
    orders = list(
        db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.business_id == supplier.business_id, PurchaseOrder.supplier_id == supplier.id)
            .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
        )
    )
    order_ids = [order.id for order in orders]

    # When each order was placed and delivered, from the order timeline (Feature 5)
    moments: dict[tuple[int, str], datetime] = {}
    if order_ids:
        for order_id, to_status, first_time in db.execute(
            select(OrderStatusHistory.purchase_order_id, OrderStatusHistory.to_status, func.min(OrderStatusHistory.created_at))
            .where(
                OrderStatusHistory.purchase_order_id.in_(order_ids),
                OrderStatusHistory.to_status.in_((PO_ORDERED, PO_DELIVERED)),
            )
            .group_by(OrderStatusHistory.purchase_order_id, OrderStatusHistory.to_status)
        ):
            moments[(order_id, to_status)] = first_time

    rows = []
    measured_days: list[int] = []
    late_count = 0
    delivered_sen_total = 0
    for order in orders:
        total_sen = sum(line.quantity_ordered * line.unit_price_sen for line in order.lines)
        received_sen = sum(line.received_quantity * line.unit_price_sen for line in order.lines)
        placed_at = moments.get((order.id, PO_ORDERED))
        delivered_at = moments.get((order.id, PO_DELIVERED)) if order.status == PO_DELIVERED else None
        days = late = None
        if order.status == PO_DELIVERED:
            delivered_sen_total += received_sen
            if placed_at is not None and delivered_at is not None:
                days = (_my_date(delivered_at) - _my_date(placed_at)).days
                late = days > supplier.typical_lead_time_days
                measured_days.append(days)
                late_count += 1 if late else 0
        rows.append(
            {
                "id": order.id,
                "po_number": order.po_number,
                "status": order.status,
                "total": _rm(total_sen),
                "received_value": _rm(received_sen),
                "line_count": len(order.lines),
                "created_at": order.created_at,
                "estimated_delivery_date": order.estimated_delivery_date,
                "placed_at": placed_at,
                "delivered_at": delivered_at,
                "delivery_days": days,
                "late": late,
            }
        )

    stats = {
        "total_orders": len(orders),
        "in_progress": sum(1 for o in orders if o.status in PO_OUTSTANDING),
        "delivered": sum(1 for o in orders if o.status == PO_DELIVERED),
        "cancelled_or_rejected": sum(1 for o in orders if o.status in (PO_CANCELLED, PO_REJECTED)),
        "delivered_value": _rm(delivered_sen_total),
        "measured_deliveries": len(measured_days),
        "average_delivery_days": round(sum(measured_days) / len(measured_days), 1) if measured_days else None,
        "late_deliveries": late_count,
    }
    return rows, stats


def get_supplier(db: Session, business_id: int, supplier_id: int) -> dict:
    db.expire_all()  # read what is really in the database
    supplier = _get_supplier(db, business_id, supplier_id)
    detail = _list_dict(supplier, _order_counts(db, business_id), _product_counts(db, business_id))
    orders, stats = _order_history(db, supplier)
    detail.update(products=_price_list(db, supplier), orders=orders, stats=stats)
    return detail


# ------------------------------------------------------------------ suppliers: add / edit / (de)activate

def create_supplier(db: Session, user: User, data: SupplierCreate) -> dict:
    """OWNER ONLY (the router enforces it)."""
    if _name_taken(db, user.business_id, data.name):
        raise SupplierError(f'A supplier called "{data.name}" already exists.', 409)
    now = utcnow()
    supplier = Supplier(
        business_id=user.business_id,
        name=data.name,
        contact_name=data.contact_name,
        phone=data.phone,
        email=data.email,
        address=data.address,
        notes=data.notes,
        typical_lead_time_days=data.lead_time_days,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    try:
        db.add(supplier)
        db.flush()  # gives the supplier an id
        log_activity(
            db, user, "supplier.created", "supplier", supplier.id,
            f"Added supplier {supplier.name} (typical delivery {supplier.typical_lead_time_days} day(s))",
            new_value=_snapshot(supplier),
        )
        db.commit()
    except IntegrityError:
        db.rollback()  # someone created the same name at the same moment
        raise SupplierError(f'A supplier called "{data.name}" already exists.', 409)
    return get_supplier(db, user.business_id, supplier.id)


def update_supplier(db: Session, user: User, supplier_id: int, data: SupplierUpdate) -> dict:
    """OWNER ONLY. Renaming a supplier also updates the supplier label on products that used
    the old name, so the Inventory page stays consistent."""
    supplier = _get_supplier(db, user.business_id, supplier_id)
    changes = data.model_dump(exclude_unset=True)
    if "lead_time_days" in changes:
        changes["typical_lead_time_days"] = changes.pop("lead_time_days")

    new_name = changes.get("name")
    if new_name is not None and new_name != supplier.name and _name_taken(db, user.business_id, new_name, supplier.id):
        raise SupplierError(f'A supplier called "{new_name}" already exists.', 409)

    old = _snapshot(supplier)
    old_name = supplier.name
    for field, value in changes.items():
        setattr(supplier, field, value)
    new = _snapshot(supplier)
    if new == old:
        db.rollback()  # nothing changed: no write, no log entry
        return get_supplier(db, user.business_id, supplier_id)

    changed = [key for key in new if new[key] != old[key]]
    new_value = {key: new[key] for key in changed}
    now = utcnow()
    if "name" in changed:
        relabelled = db.execute(
            update(InventoryItem)
            .where(InventoryItem.business_id == user.business_id, InventoryItem.supplier_name == old_name)
            .values(supplier_name=supplier.name, updated_at=now)
        ).rowcount
        if relabelled:
            new_value["products_relabelled"] = relabelled
    supplier.updated_at = now
    try:
        log_activity(
            db, user, "supplier.updated", "supplier", supplier.id,
            f"Edited supplier {supplier.name}: {', '.join(changed)}",
            old_value={key: old[key] for key in changed},
            new_value=new_value,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise SupplierError(f'A supplier called "{supplier.name}" already exists.', 409)
    return get_supplier(db, user.business_id, supplier_id)


def set_active(db: Session, user: User, supplier_id: int, active: bool) -> dict:
    """OWNER ONLY. Deactivated suppliers keep their history but are never picked for new orders."""
    supplier = _get_supplier(db, user.business_id, supplier_id)
    if supplier.is_active == active:
        raise SupplierError(f"{supplier.name} is already {'active' if active else 'inactive'}.", 409)

    if not active:
        unfinished = list(
            db.scalars(
                select(PurchaseOrder.po_number)
                .where(
                    PurchaseOrder.business_id == user.business_id,
                    PurchaseOrder.supplier_id == supplier.id,
                    PurchaseOrder.status.in_(PO_OUTSTANDING),
                )
                .order_by(PurchaseOrder.id)
            )
        )
        if unfinished:
            raise SupplierError(
                f"{supplier.name} still has unfinished orders ({', '.join(unfinished)}). "
                "Finish, reject or cancel them (or switch a draft to another supplier) first.",
                409,
            )

    supplier.is_active = active
    supplier.updated_at = utcnow()
    action = "supplier.activated" if active else "supplier.deactivated"
    log_activity(
        db, user, action, "supplier", supplier.id,
        f"{'Re-activated' if active else 'Deactivated'} supplier {supplier.name}",
        old_value={"is_active": not active},
        new_value={"is_active": active},
    )
    db.commit()
    return get_supplier(db, user.business_id, supplier_id)


# ------------------------------------------------------------------ price list

def _get_link(db: Session, supplier: Supplier, link_id: int) -> SupplierProduct:
    link = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.id == link_id,
            SupplierProduct.supplier_id == supplier.id,
            SupplierProduct.business_id == supplier.business_id,
            SupplierProduct.is_active.is_(True),
        )
    )
    if link is None:
        raise SupplierError("This product is not on the supplier's price list.", 404)
    return link


def add_product(db: Session, user: User, supplier_id: int, data: SupplierProductCreate) -> dict:
    """OWNER ONLY. Put a product on the supplier's price list. If the product is low and had
    no supplier, a purchase order DRAFT may be prepared right after (never approved)."""
    supplier = _get_supplier(db, user.business_id, supplier_id)
    item = db.scalar(
        select(InventoryItem).where(InventoryItem.id == data.item_id, InventoryItem.business_id == user.business_id)
    )
    if item is None:
        raise SupplierError("Product not found.", 404)
    if item.is_archived:
        raise SupplierError(f"{item.name} is archived. Restore it before adding a price.", 409)

    existing = db.scalar(
        select(SupplierProduct).where(SupplierProduct.supplier_id == supplier.id, SupplierProduct.item_id == item.id)
    )
    if existing is not None and existing.is_active:
        raise SupplierError(f"{item.name} is already on {supplier.name}'s price list. Edit the price instead.", 409)

    price_sen = price_to_sen(data.unit_price)
    if existing is not None:
        # An old, switched-off entry (none are created by this app, but be safe): reuse it
        existing.unit_price_sen = price_sen
        existing.min_order_qty = data.min_order_qty
        existing.is_active = True
        link = existing
    else:
        link = SupplierProduct(
            business_id=user.business_id,
            supplier_id=supplier.id,
            item_id=item.id,
            unit_price_sen=price_sen,
            min_order_qty=data.min_order_qty,
            is_active=True,
        )
        db.add(link)

    new_value = {
        "product": item.name,
        "sku": item.sku,
        "unit_price": _rm(price_sen),
        "min_order_qty": data.min_order_qty,
    }
    if not item.supplier_name:
        # Fill the product's supplier label so the Inventory page shows who supplies it
        item.supplier_name = supplier.name
        item.updated_at = utcnow()
        new_value["product_supplier_label"] = supplier.name
    supplier.updated_at = utcnow()
    try:
        db.flush()
        log_activity(
            db, user, "supplier.product_added", "supplier", supplier.id,
            f"{supplier.name} now supplies {item.name} at RM {_rm(price_sen):.2f} (min {data.min_order_qty})",
            new_value=new_value,
        )
        db.commit()
    except IntegrityError:
        db.rollback()  # the same product was added at the same moment
        raise SupplierError(f"{item.name} is already on {supplier.name}'s price list.", 409)

    # Feature 3 rule: a low product that can now be ordered gets a draft (best effort,
    # needs an open low-stock alert, no existing order, and AUTO_GENERATE_PO=true).
    draft = None
    if supplier.is_active and item.stock_status != "in_stock":
        draft = purchase_order_service.auto_draft_for_item(db, user, item.id)
    return {"supplier": get_supplier(db, user.business_id, supplier.id), "draft_purchase_order": draft}


def update_product(db: Session, user: User, supplier_id: int, link_id: int, data: SupplierProductUpdate) -> dict:
    """OWNER ONLY. New prices apply to orders prepared from now on, not to existing orders."""
    supplier = _get_supplier(db, user.business_id, supplier_id)
    link = _get_link(db, supplier, link_id)
    item = db.get(InventoryItem, link.item_id)

    old = {"unit_price": _rm(link.unit_price_sen), "min_order_qty": link.min_order_qty}
    if data.unit_price is not None:
        link.unit_price_sen = price_to_sen(data.unit_price)
    if data.min_order_qty is not None:
        link.min_order_qty = data.min_order_qty
    new = {"unit_price": _rm(link.unit_price_sen), "min_order_qty": link.min_order_qty}
    if new == old:
        db.rollback()
        return get_supplier(db, user.business_id, supplier_id)

    changed = [key for key in new if new[key] != old[key]]
    parts = []
    if "unit_price" in changed:
        parts.append(f"price RM {old['unit_price']:.2f} -> RM {new['unit_price']:.2f}")
    if "min_order_qty" in changed:
        parts.append(f"minimum {old['min_order_qty']} -> {new['min_order_qty']}")
    supplier.updated_at = utcnow()
    log_activity(
        db, user, "supplier.price_changed", "supplier", supplier.id,
        f"{supplier.name}, {item.name}: {', '.join(parts)}",
        old_value={"product": item.name, **{key: old[key] for key in changed}},
        new_value={"product": item.name, **{key: new[key] for key in changed}},
    )
    db.commit()
    return get_supplier(db, user.business_id, supplier_id)


def remove_product(db: Session, user: User, supplier_id: int, link_id: int) -> dict:
    """OWNER ONLY. Take a product off the price list. Orders already prepared are not changed
    (they keep their own copy of the price)."""
    supplier = _get_supplier(db, user.business_id, supplier_id)
    link = _get_link(db, supplier, link_id)
    item = db.get(InventoryItem, link.item_id)
    old = {
        "product": item.name,
        "sku": item.sku,
        "unit_price": _rm(link.unit_price_sen),
        "min_order_qty": link.min_order_qty,
    }
    db.delete(link)
    supplier.updated_at = utcnow()
    log_activity(
        db, user, "supplier.product_removed", "supplier", supplier.id,
        f"Removed {item.name} from {supplier.name}'s price list",
        old_value=old,
        new_value={"product": item.name, "on_price_list": False},
    )
    db.commit()
    return get_supplier(db, user.business_id, supplier_id)
