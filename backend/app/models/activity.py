from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class ActivityLog(Base):
    """Audit trail: who did what, when, to which record, with old and new values.

    Feature 1 writes to this table. Feature 4 adds the Activity Logs page.
    """

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)  # e.g. "stock.out"
    entity_type: Mapped[str] = mapped_column(String(40))          # e.g. "inventory_item"
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    summary: Mapped[str] = mapped_column(String(255))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON text
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON text
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
