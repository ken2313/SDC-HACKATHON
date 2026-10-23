"""Shapes for the inventory dashboard (Feature 7). Output only: the dashboard never changes data."""
from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.schemas.inventory import UTCDateTime


class StockCounts(BaseModel):
    total_products: int   # active (not archived) products
    in_stock: int
    low_stock: int
    out_of_stock: int
    archived: int


class AlertCounts(BaseModel):
    open: int
    critical: int
    urgent: int


class OrderCounts(BaseModel):
    pending_approval: int      # waiting for the owner's decision
    approved_not_placed: int
    awaiting_delivery: int     # ordered / shipped / delayed
    delayed: int               # marked Delayed
    overdue: int               # past the expected date
    delayed_or_overdue: int    # either (an order is counted once)


class Financials(BaseModel):
    """Owner only (reports:view). RM."""

    stock_value: float
    products_without_price: int
    pending_approval_value: float
    on_order_value: float
    received_last_30_days: float


class CategoryStatus(BaseModel):
    category: str
    in_stock: int
    low_stock: int
    out_of_stock: int


class UpcomingDelivery(BaseModel):
    id: int
    po_number: str
    status: str
    supplier_name: str
    estimated_delivery_date: date
    days_until: int
    is_overdue: bool
    line_count: int
    total: float


class RecentMovement(BaseModel):
    id: int
    item_id: int
    item_name: str
    unit: str
    movement_type: str
    quantity_change: int
    quantity_before: int
    quantity_after: int
    reason: str | None
    user_name: str
    created_at: UTCDateTime


class UrgentProduct(BaseModel):
    item_id: int
    item_name: str
    sku: str
    unit: str
    quantity: int
    reorder_threshold: int
    urgency: Literal["critical", "urgent", "low"]
    order_po_number: str | None   # the order that will restock it, if there is one
    order_status: str | None


class TrendProduct(BaseModel):
    item_id: int
    item_name: str
    sku: str
    unit: str


class AnomalyStatus(BaseModel):
    available: bool
    message: str


class DashboardOverview(BaseModel):
    generated_at: UTCDateTime
    today: date                     # Malaysia date
    stock: StockCounts
    alerts: AlertCounts
    orders: OrderCounts
    financials: Financials | None   # null for roles without reports:view
    status_by_category: list[CategoryStatus]
    upcoming_deliveries: list[UpcomingDelivery]
    recent_activity: list[RecentMovement]
    urgent_products: list[UrgentProduct]
    trend_products: list[TrendProduct]
    default_trend_item_id: int | None
    anomalies: AnomalyStatus


class TrendPoint(BaseModel):
    date: date
    quantity: int | None   # stock at the end of the day (None before the product existed)
    stock_in: int
    stock_out: int


class StockTrend(BaseModel):
    item_id: int
    item_name: str
    sku: str
    unit: str
    reorder_threshold: int
    current_quantity: int
    days: int
    points: list[TrendPoint]
    total_in: int
    total_out: int
    average_daily_usage: float
    days_with_usage: int
    enough_history: bool
