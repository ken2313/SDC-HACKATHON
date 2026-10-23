from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import PO_DRAFT, PO_SOURCE_AUTO
from app.database import Base, utcnow


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (UniqueConstraint("business_id", "po_number", name="uq_po_business_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    po_number: Mapped[str] = mapped_column(String(20))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=PO_DRAFT, index=True)
    source: Mapped[str] = mapped_column(String(10), default=PO_SOURCE_AUTO)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    estimated_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)  # rejection reason
    # Used by Feature 5 so a delivery can only add stock once
    inventory_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lines: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="order", order_by="PurchaseOrderItem.id", cascade="all, delete-orphan"
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        CheckConstraint("quantity_ordered >= 1", name="ck_po_item_quantity"),
        CheckConstraint("unit_price_sen >= 0", name="ck_po_item_price"),
        # NO DUPLICATE ORDERS: a product may be on only ONE outstanding order.
        # `outstanding` is switched off when the order is rejected / cancelled / delivered.
        Index(
            "uq_po_item_one_outstanding_per_product",
            "item_id",
            unique=True,
            sqlite_where=text("outstanding = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    quantity_ordered: Mapped[int] = mapped_column(Integer)
    recommended_quantity: Mapped[int] = mapped_column(Integer)  # what the system suggested
    unit_price_sen: Mapped[int] = mapped_column(Integer)
    received_quantity: Mapped[int] = mapped_column(Integer, default=0)  # Feature 5
    outstanding: Mapped[bool] = mapped_column(Boolean, default=True)

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
