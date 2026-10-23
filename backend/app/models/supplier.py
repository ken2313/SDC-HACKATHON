from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class Supplier(Base):
    """A supplier of one business. Feature 3 uses it to pick a supplier and a price;
    Feature 6 adds the management screens (add / edit / price list / order history).

    `address`, `notes` and `updated_at` were added in Feature 6. Databases created earlier
    get these columns automatically at start-up (see app/schema_upgrade.py)."""

    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("business_id", "name", name="uq_supplier_business_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    typical_lead_time_days: Mapped[int] = mapped_column(Integer, default=3)
    # Inactive suppliers are kept (their order history stays) but are never picked for new orders
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=utcnow)


class SupplierProduct(Base):
    """'Supplier S sells product P at price X (minimum order M)'. Prices are stored in sen
    (1 RM = 100 sen) as whole numbers so money never suffers floating-point rounding."""

    __tablename__ = "supplier_products"
    __table_args__ = (
        UniqueConstraint("supplier_id", "item_id", name="uq_supplier_product"),
        CheckConstraint("unit_price_sen >= 0", name="ck_supplier_product_price"),
        CheckConstraint("min_order_qty >= 1", name="ck_supplier_product_moq"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    unit_price_sen: Mapped[int] = mapped_column(Integer)
    min_order_qty: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
