"""Shapes for supplier order tracking (Feature 5)."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.inventory import MAX_QUANTITY, UTCDateTime

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


# ------------------------------------------------------------------ input

class StatusUpdate(BaseModel):
    """Mark an order Shipped or Delayed. (Delivered goes through /receive, Ordered through /place,
    Cancelled through /cancel, because each of those does more than change a label.)"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["shipped", "delayed"]
    estimated_delivery_date: date | None = None  # new expected date (required when delaying)
    note: Note | None = None


class ReceivedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: int
    received_quantity: Annotated[int, Field(ge=0, le=MAX_QUANTITY)]


class ReceiveDelivery(BaseModel):
    """Confirm a delivery. Send EVERY line of the order with the quantity that really arrived."""

    model_config = ConfigDict(extra="forbid")

    lines: Annotated[list[ReceivedLine], Field(min_length=1, max_length=100)]
    note: Note | None = None


class CancelOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]


# ------------------------------------------------------------------ output

class HistoryEntry(BaseModel):
    id: int
    from_status: str | None
    to_status: str
    user_name: str  # "System" when no person did it
    note: str | None
    created_at: UTCDateTime


class TrackedLine(BaseModel):
    id: int
    item_id: int
    item_name: str
    sku: str
    unit: str
    quantity_ordered: int
    received_quantity: int
    unit_price: float
    line_total: float


class TrackedOrder(BaseModel):
    id: int
    po_number: str
    status: str
    supplier_name: str
    supplier_contact: str | None
    supplier_phone: str | None
    lead_time_days: int
    total: float
    estimated_delivery_date: date | None
    is_overdue: bool
    days_overdue: int
    inventory_applied: bool            # True once the delivery has been added to stock
    lines: list[TrackedLine]
    next_statuses: list[str]           # which statuses this order may move to (any role)
    history: list[HistoryEntry]
    created_at: UTCDateTime
    updated_at: UTCDateTime


class TrackingSummary(BaseModel):
    awaiting_placement: int   # approved, not yet sent to the supplier
    in_transit: int           # ordered + shipped
    delayed: int
    overdue: int
    due_next_7_days: int
    delivered: int
    cancelled: int


class StockUpdate(BaseModel):
    item_name: str
    unit: str
    added: int
    new_quantity: int


class ReceiveResult(BaseModel):
    order: TrackedOrder
    stock_updates: list[StockUpdate]
    follow_up_drafts: list[str]  # PO numbers of drafts prepared because stock is still low
