"""Inventory business logic. Routers stay thin; the rules live here.

Every function that changes data commits ONCE at the end, so the change, its
stock-movement row and its audit-log row are saved together or not at all.
"""
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import (
    MOVEMENT_IN,
    MOVEMENT_INITIAL,
    MOVEMENT_OUT,
    STATUS_IN_STOCK,
    STATUS_LOW_STOCK,
    STATUS_OUT_OF_STOCK,
)
from app.database import utcnow
from app.models import InventoryItem, StockMovement, User
from app.schemas.inventory import ItemCreate, ItemUpdate, MovementCreate
from app.services.activity_service import log_activity


class InventoryError(Exception):
    """A rule was broken. `status_code` tells the router which HTTP error to send."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


SORTABLE_COLUMNS = {
    "name": InventoryItem.name,
    "sku": InventoryItem.sku,
    "category": InventoryItem.category,
    "quantity": InventoryItem.quantity,
    "updated_at": InventoryItem.updated_at,
}


def _snapshot(item: InventoryItem) -> dict:
    """Plain-dict copy of the editable fields, used for audit-log old/new values."""
    return {
        "sku": item.sku,
        "name": item.name,
        "category": item.category,
        "unit": item.unit,
        "quantity": item.quantity,
        "reorder_threshold": item.reorder_threshold,
        "supplier_name": item.supplier_name,
        "is_archived": item.is_archived,
    }


def get_item(db: Session, business_id: int, item_id: int) -> InventoryItem:
    """Fetch an item, but only if it belongs to the caller's business."""
    item = db.scalar(
        select(InventoryItem).where(
            InventoryItem.id == item_id, InventoryItem.business_id == business_id
        )
    )
    if item is None:
        raise InventoryError("Product not found.", 404)
    return item


def _status_condition(status: str):
    if status == STATUS_OUT_OF_STOCK:
        return InventoryItem.quantity <= 0
    if status == STATUS_LOW_STOCK:
        return and_(
            InventoryItem.quantity > 0,
            InventoryItem.quantity <= InventoryItem.reorder_threshold,
        )
    if status == STATUS_IN_STOCK:
        return InventoryItem.quantity > InventoryItem.reorder_threshold
    raise InventoryError("Invalid status filter.", 422)


def list_items(
    db: Session,
    business_id: int,
    search: str | None = None,
    category: str | None = None,
    status: str | None = None,
    include_archived: bool = False,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> list[InventoryItem]:
    query = select(InventoryItem).where(InventoryItem.business_id == business_id)

    if not include_archived:
        query = query.where(InventoryItem.is_archived.is_(False))

    if search and search.strip():
        term = search.strip().lower()
        # Escape LIKE wildcards so '%' and '_' typed by the user match literally.
        escaped = term.replace("/", "//").replace("%", "/%").replace("_", "/_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(
                func.lower(InventoryItem.name).like(pattern, escape="/"),
                func.lower(InventoryItem.sku).like(pattern, escape="/"),
                func.lower(InventoryItem.category).like(pattern, escape="/"),
                func.lower(func.coalesce(InventoryItem.supplier_name, "")).like(pattern, escape="/"),
            )
        )
    if category:
        query = query.where(InventoryItem.category == category)
    if status:
        query = query.where(_status_condition(status))

    column = SORTABLE_COLUMNS.get(sort_by)
    if column is None:
        raise InventoryError("Invalid sort column.", 422)
    ordering = column.desc() if sort_dir == "desc" else column.asc()
    query = query.order_by(ordering, InventoryItem.id)

    return list(db.scalars(query))


def list_categories(db: Session, business_id: int) -> list[str]:
    rows = db.scalars(
        select(InventoryItem.category)
        .where(InventoryItem.business_id == business_id)
        .distinct()
        .order_by(InventoryItem.category)
    )
    return list(rows)


def get_summary(db: Session, business_id: int) -> dict:
    """Counts for the page header. Archived products are counted separately."""
    row = db.execute(
        select(
            func.count(),
            func.sum(case((InventoryItem.quantity <= 0, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            InventoryItem.quantity > 0,
                            InventoryItem.quantity <= InventoryItem.reorder_threshold,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
        ).where(InventoryItem.business_id == business_id, InventoryItem.is_archived.is_(False))
    ).one()
    total, out_of_stock, low_stock = row[0] or 0, row[1] or 0, row[2] or 0
    archived = db.scalar(
        select(func.count()).where(
            InventoryItem.business_id == business_id, InventoryItem.is_archived.is_(True)
        )
    )
    return {
        "total_products": total,
        "in_stock": total - out_of_stock - low_stock,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "archived": archived or 0,
    }


def _ensure_sku_free(db: Session, business_id: int, sku: str, ignore_item_id: int | None = None) -> None:
    query = select(InventoryItem.id).where(
        InventoryItem.business_id == business_id, InventoryItem.sku == sku
    )
    if ignore_item_id is not None:
        query = query.where(InventoryItem.id != ignore_item_id)
    if db.scalar(query) is not None:
        raise InventoryError(f"SKU '{sku}' is already used by another product.", 409)


def create_item(db: Session, user: User, data: ItemCreate) -> InventoryItem:
    _ensure_sku_free(db, user.business_id, data.sku)

    item = InventoryItem(
        business_id=user.business_id,
        sku=data.sku,
        name=data.name,
        category=data.category,
        unit=data.unit,
        quantity=data.quantity,
        reorder_threshold=data.reorder_threshold,
        supplier_name=data.supplier_name,
    )
    try:
        db.add(item)
        db.flush()  # gives the item an id

        if data.quantity > 0:
            db.add(
                StockMovement(
                    business_id=user.business_id,
                    item_id=item.id,
                    user_id=user.id,
                    movement_type=MOVEMENT_INITIAL,
                    quantity_change=data.quantity,
                    quantity_before=0,
                    quantity_after=data.quantity,
                    reason="Opening quantity",
                )
            )
        log_activity(
            db, user, "item.created", "inventory_item", item.id,
            f"Created product {item.name} ({item.sku})",
            new_value=_snapshot(item),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise InventoryError(f"SKU '{data.sku}' is already used by another product.", 409)
    return item


def update_item(db: Session, user: User, item_id: int, data: ItemUpdate) -> InventoryItem:
    item = get_item(db, user.business_id, item_id)
    if item.is_archived:
        raise InventoryError("Archived products cannot be edited. Restore the product first.", 409)

    changes = data.model_dump(exclude_unset=True)
    # Required fields cannot be cleared by sending null.
    for required in ("name", "sku", "category", "unit", "reorder_threshold"):
        if required in changes and changes[required] is None:
            raise InventoryError(f"'{required}' cannot be empty.", 422)

    if "sku" in changes and changes["sku"] != item.sku:
        _ensure_sku_free(db, user.business_id, changes["sku"], ignore_item_id=item.id)

    old_values = _snapshot(item)
    for field, value in changes.items():
        setattr(item, field, value)

    new_values = _snapshot(item)
    if new_values == old_values:
        return item  # nothing changed: no log entry, no write

    item.updated_at = utcnow()
    changed_fields = [key for key in new_values if new_values[key] != old_values[key]]
    log_activity(
        db, user, "item.updated", "inventory_item", item.id,
        f"Updated {item.name}: {', '.join(changed_fields)}",
        old_value={key: old_values[key] for key in changed_fields},
        new_value={key: new_values[key] for key in changed_fields},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise InventoryError("That SKU is already used by another product.", 409)
    return item


def set_archived(db: Session, user: User, item_id: int, archived: bool) -> InventoryItem:
    """Archive = soft delete. The product and its history stay in the database
    (so old reports and audit logs still make sense) but it disappears from daily use."""
    item = get_item(db, user.business_id, item_id)
    if item.is_archived == archived:
        return item  # already in the requested state

    item.is_archived = archived
    item.updated_at = utcnow()
    log_activity(
        db, user,
        "item.archived" if archived else "item.restored",
        "inventory_item", item.id,
        f"{'Archived' if archived else 'Restored'} product {item.name} ({item.sku})",
        old_value={"is_archived": not archived},
        new_value={"is_archived": archived},
    )
    db.commit()
    return item


def _find_movement_by_request(db: Session, business_id: int, request_id: str) -> StockMovement | None:
    return db.scalar(
        select(StockMovement).where(
            StockMovement.business_id == business_id, StockMovement.request_id == request_id
        )
    )


def record_movement(
    db: Session, user: User, item_id: int, data: MovementCreate
) -> tuple[StockMovement, InventoryItem, bool]:
    """Add or remove stock. Returns (movement, item, already_applied).

    Safety rules:
    - Stock can never go below zero. The check is part of the UPDATE statement
      itself, so two simultaneous requests cannot both take the last units.
    - A repeated request_id returns the original result instead of changing
      the stock a second time.
    """
    item = get_item(db, user.business_id, item_id)
    if item.is_archived:
        raise InventoryError("This product is archived. Restore it before recording stock.", 409)

    if data.request_id:
        existing = _find_movement_by_request(db, user.business_id, data.request_id)
        if existing is not None:
            if existing.item_id != item.id:
                raise InventoryError("This request ID was already used for a different product.", 409)
            return existing, item, True

    delta = data.quantity if data.movement_type == MOVEMENT_IN else -data.quantity

    try:
        result = db.execute(
            update(InventoryItem)
            .where(
                InventoryItem.id == item.id,
                InventoryItem.business_id == user.business_id,
                InventoryItem.quantity + delta >= 0,
            )
            .values(quantity=InventoryItem.quantity + delta, updated_at=utcnow())
        )
        if result.rowcount == 0:
            db.rollback()
            db.refresh(item)
            raise InventoryError(
                f"Not enough stock. {item.name} has {item.quantity} {item.unit} "
                f"but you tried to remove {data.quantity}.",
                409,
            )

        db.refresh(item)  # reads the new quantity inside the same transaction
        quantity_after = item.quantity
        quantity_before = quantity_after - delta

        movement = StockMovement(
            business_id=user.business_id,
            item_id=item.id,
            user_id=user.id,
            movement_type=data.movement_type,  # already validated as "in" or "out"
            quantity_change=delta,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reason=data.reason,
            request_id=data.request_id,
        )
        db.add(movement)
        db.flush()

        verb = "Added" if delta > 0 else "Removed"
        log_activity(
            db, user,
            "stock.in" if delta > 0 else "stock.out",
            "inventory_item", item.id,
            f"{verb} {abs(delta)} {item.unit} of {item.name} ({quantity_before} -> {quantity_after})",
            old_value={"quantity": quantity_before},
            new_value={"quantity": quantity_after, "reason": data.reason},
        )
        db.commit()
    except IntegrityError:
        # Two identical requests raced each other and the other one won.
        db.rollback()
        if data.request_id:
            existing = _find_movement_by_request(db, user.business_id, data.request_id)
            if existing is not None:
                db.refresh(item)
                return existing, item, True
        raise InventoryError("Could not save the stock change. Please try again.", 409)

    return movement, item, False


def list_movements(db: Session, business_id: int, item_id: int, limit: int = 50) -> list[dict]:
    get_item(db, business_id, item_id)  # 404 if it is not this business's product
    rows = db.execute(
        select(StockMovement, User.name)
        .join(User, User.id == StockMovement.user_id)
        .where(StockMovement.business_id == business_id, StockMovement.item_id == item_id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(limit)
    ).all()
    result = []
    for movement, user_name in rows:
        movement.user_name = user_name  # attach for the response schema
        result.append(movement)
    return result
