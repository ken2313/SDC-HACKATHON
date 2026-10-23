from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import STATUS_IN_STOCK, STATUS_LOW_STOCK, STATUS_OUT_OF_STOCK
from app.database import Base, utcnow


def compute_stock_status(quantity: int, reorder_threshold: int) -> str:
    """Stock status rules (one place, used everywhere):

    - quantity == 0                    -> Out of Stock
    - 0 < quantity <= reorder threshold -> Low Stock   (reaching the threshold counts)
    - quantity > reorder threshold     -> In Stock
    """
    if quantity <= 0:
        return STATUS_OUT_OF_STOCK
    if quantity <= reorder_threshold:
        return STATUS_LOW_STOCK
    return STATUS_IN_STOCK


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("business_id", "sku", name="uq_item_business_sku"),
        # Safety net: even a bug in our code cannot store negative stock.
        CheckConstraint("quantity >= 0", name="ck_item_quantity_not_negative"),
        CheckConstraint("reorder_threshold >= 0", name="ck_item_threshold_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    sku: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    unit: Mapped[str] = mapped_column(String(20), default="pcs")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    reorder_threshold: Mapped[int] = mapped_column(Integer, default=0)
    # A display label. The real product-supplier link is the supplier's price list
    # (supplier_products, managed on the Suppliers page since Feature 6).
    supplier_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def stock_status(self) -> str:
        return compute_stock_status(self.quantity, self.reorder_threshold)


class StockMovement(Base):
    """Every change to a quantity is recorded here (the stock 'ledger')."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        # Makes retries safe: the same request_id can only be applied once per business.
        UniqueConstraint("business_id", "request_id", name="uq_movement_business_request"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    movement_type: Mapped[str] = mapped_column(String(20))  # initial / in / out
    quantity_change: Mapped[int] = mapped_column(Integer)   # signed: +20, -15
    quantity_before: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
