from typing import Literal

from pydantic import BaseModel

from app.schemas.inventory import UTCDateTime


class AlertOut(BaseModel):
    id: int
    item_id: int
    item_name: str
    sku: str
    category: str
    unit: str
    supplier_name: str | None
    quantity: int            # the item's CURRENT quantity
    reorder_threshold: int   # the item's CURRENT threshold
    shortfall: int           # how far below the threshold (0 when exactly at it)
    stock_status: Literal["in_stock", "low_stock", "out_of_stock"]
    urgency: Literal["critical", "urgent", "low"] | None  # only for open alerts
    status: Literal["open", "resolved"]
    opened_at: UTCDateTime
    resolved_at: UTCDateTime | None
    resolution: str | None


class AlertSummary(BaseModel):
    open: int
    critical: int
    urgent: int
    low: int
    resolved: int
