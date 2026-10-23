"""Order timeline helper, shared by the purchase order and order tracking services
(kept in its own small file so those two modules do not import each other)."""
from sqlalchemy.orm import Session

from app.models import OrderStatusHistory, PurchaseOrder, User


def record_history(
    db: Session, order: PurchaseOrder, user: User | None, from_status: str | None, to_status: str,
    note: str | None = None,
) -> None:
    """Add a timeline row to the current transaction (does NOT commit)."""
    db.add(
        OrderStatusHistory(
            business_id=order.business_id,
            purchase_order_id=order.id,
            from_status=from_status,
            to_status=to_status,
            user_id=user.id if user is not None else None,
            note=note[:255] if note else None,
        )
    )
