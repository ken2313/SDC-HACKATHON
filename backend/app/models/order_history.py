from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class OrderStatusHistory(Base):
    """One row each time a purchase order changes status: who, when, from what, to what.

    It is the timeline shown on the Supplier Orders page. (The Activity Log also records
    the same events for the audit trail.)
    """

    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # None = order created
    to_status: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # None = system
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
