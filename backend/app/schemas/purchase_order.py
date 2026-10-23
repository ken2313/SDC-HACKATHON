from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.inventory import MAX_QUANTITY, UTCDateTime

OrderStatus = Literal[
    "draft", "pending_approval", "approved", "ordered", "shipped",
    "delivered", "delayed", "cancelled", "rejected",
]
UrgencyLevel = Literal["critical", "urgent", "low"]


# ------------------------------------------------------------------ input

class OrderLineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: int
    quantity: Annotated[int, Field(ge=1, le=MAX_QUANTITY)]


class OrderUpdate(BaseModel):
    """Edit an order that is still waiting for a decision. Send only what changes.
    Prices are NOT editable here: they come from the supplier's price list."""

    model_config = ConfigDict(extra="forbid")

    supplier_id: int | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    lines: Annotated[list[OrderLineUpdate], Field(min_length=1, max_length=100)] | None = None


class OrderReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]

    @field_validator("reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A reason is required")
        return value


# ------------------------------------------------------------------ output

class SupplierRef(BaseModel):
    id: int
    name: str
    contact_name: str | None
    phone: str | None
    email: str | None
    lead_time_days: int


class OrderLineOut(BaseModel):
    id: int
    item_id: int
    item_name: str
    sku: str
    unit: str
    quantity_ordered: int
    recommended_quantity: int
    unit_price: float        # RM
    line_total: float        # RM
    min_order_qty: int | None
    current_quantity: int    # stock on hand right now
    reorder_threshold: int
    received_quantity: int = 0  # Feature 5: filled when a delivery is confirmed


class EligibleSupplier(BaseModel):
    id: int
    name: str
    lead_time_days: int
    total: float  # RM for the current quantities at this supplier's prices


class OrderOut(BaseModel):
    id: int
    po_number: str
    status: OrderStatus
    source: Literal["auto", "manual"]
    notes: str | None
    supplier: SupplierRef
    estimated_delivery_date: date | None
    total: float  # RM
    lines: list[OrderLineOut]
    created_by_name: str | None
    decided_by_name: str | None
    decided_at: UTCDateTime | None
    decision_note: str | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    is_editable: bool                       # still waiting for the owner's decision
    eligible_suppliers: list[EligibleSupplier]  # only filled while editable


class ExistingOrderRef(BaseModel):
    id: int
    po_number: str
    status: OrderStatus


class ReplenishmentNeed(BaseModel):
    item_id: int
    item_name: str
    sku: str
    unit: str
    quantity: int
    reorder_threshold: int
    urgency: UrgencyLevel
    recommended_quantity: int | None
    supplier_id: int | None
    supplier_name: str | None
    unit_price: float | None
    estimated_total: float | None
    lead_time_days: int | None
    blocked_reason: str | None  # why no draft can be made (e.g. no supplier price on file)


class SkippedItem(BaseModel):
    item_id: int
    item_name: str
    reason: str


class GenerateResult(BaseModel):
    created_orders: int
    lines_added: int
    skipped: list[SkippedItem]
    orders: list[OrderOut]  # the orders that were created or extended


class OrderSummary(BaseModel):
    awaiting_approval: int
    approved: int
    rejected: int
    awaiting_value: float   # RM total of orders waiting for a decision
    needs_ordering: int     # low products with no order yet and a supplier available
    no_supplier: int        # low products that cannot be ordered because no supplier price exists

