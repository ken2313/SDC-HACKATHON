"""Shapes for demand forecasting (Feature 8). Output only."""
from datetime import date
from typing import Literal

from pydantic import BaseModel

ForecastStatus = Literal["order_now", "order_soon", "on_order", "ok", "no_demand", "insufficient_data"]


class ForecastMethod(BaseModel):
    name: str
    window_days: int
    min_history_days: int
    reliable_history_days: int
    backtest_days: int
    safety_days: int
    cover_days: int
    low_accuracy_pct: int
    summary: str


class ProductForecast(BaseModel):
    item_id: int
    item_name: str
    sku: str
    category: str
    unit: str
    current_quantity: int
    reorder_threshold: int
    stock_status: Literal["in_stock", "low_stock", "out_of_stock"]
    history_days: int                  # complete days of records before today
    daily_forecast: float | None       # units per day (None = not enough data)
    weekly_forecast: float | None
    status: ForecastStatus
    days_until_out: float | None
    run_out_date: date | None
    order_by_date: date | None         # may be in the past: "should have ordered already"
    recommended_quantity: int | None   # forecast-based
    rule_quantity: int                 # Feature 3 rule (refill to 2 x reorder level), for comparison
    suggested_reorder_level: int | None
    level_check: Literal["too_low", "ok", "high"] | None
    supplier_name: str | None          # the supplier new drafts would use
    lead_time_days: int | None
    min_order_qty: int | None
    on_order: int                      # approved .. delayed, not yet received
    in_drafts: int                     # waiting for the owner's approval
    accuracy_pct: float | None         # predicted vs actual on the last 14 days
    mean_absolute_error: float | None
    backtest_days: int
    warnings: list[str]


class ForecastSummary(BaseModel):
    order_now: int
    order_soon: int
    on_order: int
    run_out_within_7_days: int
    insufficient_data: int
    reorder_level_too_low: int
    average_accuracy_pct: float | None


class ForecastList(BaseModel):
    today: date
    method: ForecastMethod
    summary: ForecastSummary
    items: list[ProductForecast]


class HistoryPoint(BaseModel):
    date: date
    actual: int | None        # units used that day (None before the product existed)
    predicted: float | None   # what the 7-day average predicted that morning


class FuturePoint(BaseModel):
    date: date
    forecast: float | None
    projected_stock: float | None  # if nothing new is delivered


class ForecastDetail(ProductForecast):
    today: date
    horizon_days: int
    method: ForecastMethod
    history: list[HistoryPoint]
    future: list[FuturePoint]
