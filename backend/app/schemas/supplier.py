"""Shapes for supplier management (Feature 6).

Money comes in as RM (for example 7.8) and is stored in sen (780), like everywhere else.
"""
import math
import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.inventory import MAX_QUANTITY, DraftOrderRef, UTCDateTime

MAX_LEAD_TIME_DAYS = 365
MAX_UNIT_PRICE_RM = 100_000  # RM per unit; a sanity limit for an SME price list

PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()\-]{5,38}$")
# Deliberately simple: something@something.something, no spaces. (No extra package needed.)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SupplierName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
PhoneText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
EmailText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]
AddressText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
NotesText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
LeadTime = Annotated[int, Field(ge=0, le=MAX_LEAD_TIME_DAYS)]
UnitPrice = Annotated[float, Field(ge=0, le=MAX_UNIT_PRICE_RM)]
MinOrder = Annotated[int, Field(ge=1, le=MAX_QUANTITY)]


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _check_phone(value: str | None) -> str | None:
    value = _blank_to_none(value)
    if value is not None and not PHONE_PATTERN.match(value):
        raise ValueError("Use digits, spaces, '+', '-' or brackets only (for example +60 3-5555 0101)")
    return value


def _check_email(value: str | None) -> str | None:
    value = _blank_to_none(value)
    if value is not None:
        if not EMAIL_PATTERN.match(value):
            raise ValueError("Enter a valid email address (for example orders@supplier.example)")
        value = value.lower()
    return value


def _check_price(value: float | None) -> float | None:
    """At most 2 decimal places (whole sen). 7.8 and 7.80 are fine, 7.805 is not."""
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError("Enter a valid price")
    if abs(value * 100 - round(value * 100)) > 1e-6:
        raise ValueError("Use at most 2 decimal places (whole sen)")
    return value


def price_to_sen(value: float) -> int:
    return int(round(value * 100))


# ------------------------------------------------------------------ input

class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SupplierName
    contact_name: ShortText | None = None
    phone: PhoneText | None = None
    email: EmailText | None = None
    address: AddressText | None = None
    notes: NotesText | None = None
    lead_time_days: LeadTime = 3  # typical days from placing an order to delivery

    @field_validator("contact_name", "address", "notes")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _check_phone(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return _check_email(value)


class SupplierUpdate(BaseModel):
    """Send only what changes. Send null (or an empty text) to clear an optional field."""

    model_config = ConfigDict(extra="forbid")

    name: SupplierName | None = None
    contact_name: ShortText | None = None
    phone: PhoneText | None = None
    email: EmailText | None = None
    address: AddressText | None = None
    notes: NotesText | None = None
    lead_time_days: LeadTime | None = None

    @field_validator("contact_name", "address", "notes")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _check_phone(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return _check_email(value)

    @model_validator(mode="after")
    def required_fields_not_cleared(self):
        for field in ("name", "lead_time_days"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be empty")
        return self


class SupplierProductCreate(BaseModel):
    """Put a product on this supplier's price list."""

    model_config = ConfigDict(extra="forbid")

    item_id: int
    unit_price: UnitPrice   # RM per unit
    min_order_qty: MinOrder = 1

    @field_validator("unit_price")
    @classmethod
    def validate_price(cls, value: float) -> float:
        return _check_price(value)


class SupplierProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_price: UnitPrice | None = None
    min_order_qty: MinOrder | None = None

    @field_validator("unit_price")
    @classmethod
    def validate_price(cls, value: float | None) -> float | None:
        return _check_price(value)

    @model_validator(mode="after")
    def something_to_change(self):
        for field in ("unit_price", "min_order_qty"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be empty")
        if not self.model_fields_set:
            raise ValueError("Send unit_price and/or min_order_qty")
        return self


# ------------------------------------------------------------------ output

class SupplierListItem(BaseModel):
    id: int
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    notes: str | None
    lead_time_days: int
    is_active: bool
    product_count: int        # products on the price list (archived products not counted)
    open_orders: int          # orders not finished yet (draft ... delayed)
    delivered_orders: int
    delivered_value: float    # RM value of goods received from this supplier
    last_order_at: UTCDateTime | None
    created_at: UTCDateTime
    updated_at: UTCDateTime


class SupplierProductOut(BaseModel):
    id: int                   # price list entry id
    item_id: int
    item_name: str
    sku: str
    category: str
    unit: str
    unit_price: float         # RM
    min_order_qty: int
    current_quantity: int
    reorder_threshold: int
    stock_status: Literal["in_stock", "low_stock", "out_of_stock"]
    item_archived: bool
    other_suppliers: int      # how many OTHER active suppliers also sell this product
    chosen_for_auto_orders: bool  # True if new drafts for this product would go to this supplier


class SupplierOrderRow(BaseModel):
    id: int
    po_number: str
    status: str
    total: float              # RM, ordered quantities x prices
    received_value: float     # RM, received quantities x prices (0 until delivered)
    line_count: int
    created_at: UTCDateTime
    estimated_delivery_date: date | None
    placed_at: UTCDateTime | None
    delivered_at: UTCDateTime | None
    delivery_days: int | None  # days from placing to delivery (Malaysia dates)
    late: bool | None          # delivered later than the supplier's typical delivery time


class SupplierStats(BaseModel):
    total_orders: int
    in_progress: int
    delivered: int
    cancelled_or_rejected: int
    delivered_value: float
    measured_deliveries: int        # delivered orders that have a placed date and a delivered date
    average_delivery_days: float | None
    late_deliveries: int


class SupplierDetail(SupplierListItem):
    products: list[SupplierProductOut]
    orders: list[SupplierOrderRow]
    stats: SupplierStats


class SupplierProductResult(BaseModel):
    supplier: SupplierDetail
    # Set when adding a price let the system prepare a draft for a low product (Feature 3 rule)
    draft_purchase_order: DraftOrderRef | None = None


class ProductWithoutSupplier(BaseModel):
    item_id: int
    item_name: str
    sku: str
    category: str
    unit: str
    quantity: int
    reorder_threshold: int
    stock_status: Literal["in_stock", "low_stock", "out_of_stock"]
    supplier_label: str | None  # the free-text supplier typed on the product, if any


class SupplierSummary(BaseModel):
    active: int
    inactive: int
    products_with_supplier: int       # active products that at least one active supplier sells
    products_without_supplier: int    # active products nobody sells: they cannot be reordered
    low_without_supplier: int         # ...of which are low right now (most urgent to fix)
    average_lead_time_days: float | None
