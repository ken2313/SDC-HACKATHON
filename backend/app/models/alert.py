from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import ALERT_OPEN
from app.database import Base, utcnow


class StockAlert(Base):
    """One alert = one 'episode' of an item being at or below its threshold.

    When stock is replenished the alert is RESOLVED (kept for history). If the
    item runs low again later, a NEW alert row is created.
    """

    __tablename__ = "stock_alerts"
    __table_args__ = (
        # No duplicate alerts: the database allows only ONE open alert per item.
        # (A partial unique index: it only applies to rows where status = 'open'.)
        Index(
            "uq_stock_alert_one_open_per_item",
            "item_id",
            unique=True,
            sqlite_where=text("status = 'open'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=ALERT_OPEN, index=True)
    # Snapshot of the numbers when the alert opened (the live numbers come from the item)
    quantity_at_alert: Mapped[int] = mapped_column(Integer)
    threshold_at_alert: Mapped[int] = mapped_column(Integer)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(40), nullable=True)
