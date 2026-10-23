"""Demand forecasting (Feature 8). Read-only: this file never changes data.

THE METHOD (deliberately simple, as the brief asks, and shown on the page):

  1. Demand history. For each product, the units USED each day (stock "out" movements),
     by Malaysian calendar day. A day with no usage counts as 0. Today is left out because
     it is not finished yet.
  2. Forecast. The average daily usage over the last 7 complete days
     (a 7-day simple moving average). The forecast for every future day is that number.
  3. Run-out date. Today's stock divided by the daily forecast.
  4. Order by. The last day to order so the delivery arrives (supplier's usual delivery
     time) while a safety buffer of SAFETY_DAYS of demand is still on the shelf.
  5. Order quantity. Enough for the delivery time + COVER_DAYS + SAFETY_DAYS, minus the
     stock on hand and what is already on order, never below the supplier's minimum.
  6. Suggested reorder level. Demand during the delivery time + SAFETY_DAYS. If the
     product's reorder level is lower, stock can run out before a delivery arrives.
  7. Accuracy (predicted vs actual). For each of the last 14 days we pretend it is that
     morning, forecast with the 7 days before it, and compare with what was really used.
     Accuracy = 100% - (total absolute error / total actual usage), at least 0%.

  Not enough data: fewer than MIN_HISTORY_DAYS complete days -> no forecast at all.
  Fewer than RELIABLE_HISTORY_DAYS -> a forecast with a "limited history" warning.

Limitations are listed in the README (no trend, no holidays, every stock removal counts
as demand, the same daily number for every future day).
"""
import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import (
    MOVEMENT_OUT,
    PO_AWAITING_DECISION,
    PO_IN_PROGRESS,
)
from app.database import utcnow
from app.models import InventoryItem, PurchaseOrder, PurchaseOrderItem, StockMovement
from app.services import purchase_order_service

MALAYSIA_OFFSET = timedelta(hours=8)

WINDOW_DAYS = 7              # moving-average window
MIN_HISTORY_DAYS = 7         # below this: no forecast
RELIABLE_HISTORY_DAYS = 14   # below this: forecast with a warning
BACKTEST_DAYS = 14           # days used for "predicted vs actual"
CHART_HISTORY_DAYS = 28      # past days shown on the chart
SAFETY_DAYS = 2              # buffer of demand kept on the shelf
COVER_DAYS = 7               # an order should last this long after it arrives
LOW_ACCURACY_PCT = 50        # below this the forecast is marked "low accuracy"
ORDER_SOON_DAYS = 7          # "order this week"

METHOD = {
    "name": "7-day moving average",
    "window_days": WINDOW_DAYS,
    "min_history_days": MIN_HISTORY_DAYS,
    "reliable_history_days": RELIABLE_HISTORY_DAYS,
    "backtest_days": BACKTEST_DAYS,
    "safety_days": SAFETY_DAYS,
    "cover_days": COVER_DAYS,
    "low_accuracy_pct": LOW_ACCURACY_PCT,
    "summary": (
        "Daily demand = average units used per day over the last 7 complete days. "
        "Run-out = stock / daily demand. Order by = when stock would fall to the demand during "
        "the supplier's delivery time plus 2 safety days. Accuracy is checked on the last 14 days."
    ),
}


class ForecastError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def today_my() -> date:
    return (utcnow() + MALAYSIA_OFFSET).date()


def _ceil(value: float) -> int:
    """Round up, ignoring tiny floating-point noise (10.0000000001 -> 10)."""
    return max(0, math.ceil(value - 1e-9))


# ------------------------------------------------------------------ data loading

def _usage_by_item(db: Session, business_id: int, item_ids: list[int], since: date, until: date) -> dict[int, dict[date, int]]:
    """item_id -> {Malaysian day -> units used} for since <= day < until."""
    start_utc = _day_start_utc(since)
    end_utc = _day_start_utc(until)
    usage: dict[int, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    if not item_ids:
        return usage
    rows = db.execute(
        select(StockMovement.item_id, StockMovement.created_at, StockMovement.quantity_change).where(
            StockMovement.business_id == business_id,
            StockMovement.item_id.in_(item_ids),
            StockMovement.movement_type == MOVEMENT_OUT,
            StockMovement.created_at >= start_utc,
            StockMovement.created_at < end_utc,
        )
    ).all()
    for item_id, created_at, change in rows:
        usage[item_id][(created_at + MALAYSIA_OFFSET).date()] += -change
    return usage


def _day_start_utc(day: date) -> datetime:
    """The moment a Malaysian calendar day starts, as naive UTC."""
    return datetime.combine(day, datetime.min.time()) - MALAYSIA_OFFSET


def _first_days(db: Session, business_id: int, items: list[InventoryItem]) -> dict[int, date]:
    """The first Malaysian day each product has any stock record (or was created)."""
    firsts = dict(
        db.execute(
            select(StockMovement.item_id, func.min(StockMovement.created_at))
            .where(StockMovement.business_id == business_id, StockMovement.item_id.in_([i.id for i in items]))
            .group_by(StockMovement.item_id)
        ).all()
    ) if items else {}
    result = {}
    for item in items:
        first = firsts.get(item.id) or item.created_at
        if item.created_at and item.created_at < first:
            first = item.created_at
        result[item.id] = (first + MALAYSIA_OFFSET).date()
    return result


def _orders_for(db: Session, business_id: int) -> tuple[dict[int, int], dict[int, int]]:
    """item_id -> units on order (approved .. delayed, not yet received), and units in drafts."""
    on_order: dict[int, int] = defaultdict(int)
    in_drafts: dict[int, int] = defaultdict(int)
    rows = db.execute(
        select(PurchaseOrderItem.item_id, PurchaseOrderItem.quantity_ordered, PurchaseOrder.status)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.purchase_order_id)
        .where(
            PurchaseOrder.business_id == business_id,
            PurchaseOrderItem.outstanding.is_(True),
        )
    ).all()
    for item_id, quantity, status in rows:
        if status in PO_IN_PROGRESS:
            on_order[item_id] += quantity
        elif status in PO_AWAITING_DECISION:
            in_drafts[item_id] += quantity
    return on_order, in_drafts


# ------------------------------------------------------------------ the maths (pure functions)

def moving_average(usage: dict[date, int], end_day: date, window: int = WINDOW_DAYS) -> float:
    """Average usage over the `window` days BEFORE end_day (end_day itself not included)."""
    return sum(usage.get(end_day - timedelta(days=offset), 0) for offset in range(1, window + 1)) / window


def backtest(usage: dict[date, int], first_day: date, today: date, days: int = BACKTEST_DAYS) -> list[dict]:
    """For each of the last `days` complete days that has 7 days of history before it:
    what the method would have predicted that morning vs what was really used."""
    rows = []
    for offset in range(days, 0, -1):
        day = today - timedelta(days=offset)
        if day - timedelta(days=WINDOW_DAYS) < first_day:
            continue
        rows.append({"date": day, "predicted": moving_average(usage, day), "actual": usage.get(day, 0)})
    return rows


def accuracy(rows: list[dict]) -> tuple[float | None, float | None]:
    """(accuracy %, mean absolute error). Accuracy = 100 - WAPE, at least 0. None when no data."""
    if not rows:
        return None, None
    total_error = sum(abs(r["predicted"] - r["actual"]) for r in rows)
    total_actual = sum(r["actual"] for r in rows)
    mae = round(total_error / len(rows), 2)
    if total_actual == 0:
        return (100.0 if total_error == 0 else 0.0), mae
    return round(max(0.0, 100 * (1 - total_error / total_actual)), 1), mae


def plan(daily: float, quantity: int, threshold: int, lead_days: int, min_order: int, on_order: int, today: date) -> dict:
    """Run-out date, order-by date, quantity and reorder level from a daily forecast."""
    suggested_level = _ceil(daily * (lead_days + SAFETY_DAYS))
    if daily <= 0:
        return {
            "days_until_out": None, "run_out_date": None, "order_by_date": None,
            "recommended_quantity": 0, "suggested_reorder_level": 0,
        }
    days_until_out = quantity / daily
    run_out_date = today + timedelta(days=_ceil(days_until_out))
    order_by_date = today + timedelta(days=math.floor(days_until_out - lead_days - SAFETY_DAYS + 1e-9))
    target = _ceil(daily * (lead_days + COVER_DAYS + SAFETY_DAYS))
    needed = max(0, target - quantity - on_order)
    if needed > 0:
        needed = max(needed, min_order)
    return {
        "days_until_out": round(days_until_out, 1),
        "run_out_date": run_out_date,
        "order_by_date": order_by_date,
        "recommended_quantity": needed,
        "suggested_reorder_level": suggested_level,
    }


def _status(history_days: int, daily: float | None, order_by: date | None, on_order: int, today: date) -> str:
    if daily is None or history_days < MIN_HISTORY_DAYS:
        return "insufficient_data"
    if daily <= 0:
        return "no_demand"
    if order_by is not None and order_by <= today:
        return "on_order" if on_order > 0 else "order_now"
    if order_by is not None and order_by <= today + timedelta(days=ORDER_SOON_DAYS):
        return "order_soon"
    return "ok"


STATUS_RANK = {"order_now": 0, "order_soon": 1, "on_order": 2, "ok": 3, "no_demand": 4, "insufficient_data": 5}


# ------------------------------------------------------------------ building one product's forecast

def _forecast_row(db: Session, item: InventoryItem, usage: dict[date, int], first_day: date,
                  on_order: int, in_drafts: int, today: date) -> dict:
    history_days = max(0, (today - first_day).days)
    offer = purchase_order_service._best_offer(db, item.business_id, item.id)
    lead_days = offer[1].typical_lead_time_days if offer else None
    min_order = offer[0].min_order_qty if offer else 1
    rule_quantity = purchase_order_service.recommended_quantity(item.quantity, item.reorder_threshold, min_order)

    warnings = []
    daily = None
    plan_values = {
        "days_until_out": None, "run_out_date": None, "order_by_date": None,
        "recommended_quantity": None, "suggested_reorder_level": None,
    }
    accuracy_pct = mae = None
    backtest_rows: list[dict] = []

    if history_days < MIN_HISTORY_DAYS:
        warnings.append(
            f"Not enough history: {history_days} complete day(s) of records, at least {MIN_HISTORY_DAYS} needed. "
            "No forecast is made."
        )
    else:
        daily = round(moving_average(usage, today), 2)
        if history_days < RELIABLE_HISTORY_DAYS:
            warnings.append(
                f"Limited history: only {history_days} days of records. Treat this forecast as a rough guide."
            )
        if lead_days is None:
            warnings.append("No supplier price on file, so the delivery time is unknown (0 days assumed).")
        plan_values = plan(daily, item.quantity, item.reorder_threshold, lead_days or 0, min_order, on_order, today)
        backtest_rows = backtest(usage, first_day, today)
        accuracy_pct, mae = accuracy(backtest_rows)
        if accuracy_pct is not None and accuracy_pct < LOW_ACCURACY_PCT and daily > 0:
            warnings.append(
                f"Low accuracy ({accuracy_pct:.0f}% on the last {len(backtest_rows)} days): daily use varies a lot, "
                "so the dates are uncertain."
            )

    suggested = plan_values["suggested_reorder_level"]
    level_check = None
    if suggested is not None and daily:
        if item.reorder_threshold < suggested:
            level_check = "too_low"
            warnings.append(
                f"The reorder level ({item.reorder_threshold}) is below the expected use during delivery plus "
                f"{SAFETY_DAYS} safety days ({suggested}). Stock may run out before a delivery arrives."
            )
        elif item.reorder_threshold > 2 * suggested:
            level_check = "high"
        else:
            level_check = "ok"

    status = _status(history_days, daily, plan_values["order_by_date"], on_order, today)
    return {
        "item_id": item.id,
        "item_name": item.name,
        "sku": item.sku,
        "category": item.category,
        "unit": item.unit,
        "current_quantity": item.quantity,
        "reorder_threshold": item.reorder_threshold,
        "stock_status": item.stock_status,
        "history_days": history_days,
        "daily_forecast": daily,
        "weekly_forecast": round(daily * 7, 1) if daily is not None else None,
        "status": status,
        **plan_values,
        "rule_quantity": rule_quantity,
        "level_check": level_check,
        "supplier_name": offer[1].name if offer else None,
        "lead_time_days": lead_days,
        "min_order_qty": min_order if offer else None,
        "on_order": on_order,
        "in_drafts": in_drafts,
        "accuracy_pct": accuracy_pct,
        "mean_absolute_error": mae,
        "backtest_days": len(backtest_rows),
        "warnings": warnings,
        "_backtest": backtest_rows,  # used by the detail view, removed from the list response
    }


def _load(db: Session, business_id: int, items: list[InventoryItem], today: date):
    # enough past days for the chart AND the 7 days before its first day
    since = today - timedelta(days=max(CHART_HISTORY_DAYS, BACKTEST_DAYS) + WINDOW_DAYS + 1)
    usage = _usage_by_item(db, business_id, [i.id for i in items], since, today)
    firsts = _first_days(db, business_id, items)
    on_order, in_drafts = _orders_for(db, business_id)
    return usage, firsts, on_order, in_drafts


# ------------------------------------------------------------------ public functions

def list_forecasts(db: Session, business_id: int) -> dict:
    db.expire_all()
    today = today_my()
    items = list(
        db.scalars(
            select(InventoryItem).where(InventoryItem.business_id == business_id, InventoryItem.is_archived.is_(False))
        )
    )
    usage, firsts, on_order, in_drafts = _load(db, business_id, items, today)
    rows = []
    for item in items:
        row = _forecast_row(db, item, usage[item.id], firsts[item.id], on_order.get(item.id, 0), in_drafts.get(item.id, 0), today)
        row.pop("_backtest")
        rows.append(row)

    def sort_key(row):
        order_by = row["order_by_date"] or date.max
        return (STATUS_RANK[row["status"]], order_by, row["item_name"].lower())

    rows.sort(key=sort_key)
    accuracies = [r["accuracy_pct"] for r in rows if r["accuracy_pct"] is not None and (r["daily_forecast"] or 0) > 0]
    return {
        "today": today,
        "method": METHOD,
        "summary": {
            "order_now": sum(1 for r in rows if r["status"] == "order_now"),
            "order_soon": sum(1 for r in rows if r["status"] == "order_soon"),
            "on_order": sum(1 for r in rows if r["status"] == "on_order"),
            "run_out_within_7_days": sum(
                1 for r in rows if r["run_out_date"] is not None and r["run_out_date"] <= today + timedelta(days=7)
            ),
            "insufficient_data": sum(1 for r in rows if r["status"] == "insufficient_data"),
            "reorder_level_too_low": sum(1 for r in rows if r["level_check"] == "too_low"),
            "average_accuracy_pct": round(sum(accuracies) / len(accuracies), 1) if accuracies else None,
        },
        "items": rows,
    }


def get_forecast(db: Session, business_id: int, item_id: int, horizon_days: int) -> dict:
    db.expire_all()
    today = today_my()
    item = db.scalar(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.business_id == business_id)
    )
    if item is None:
        raise ForecastError("Product not found.", 404)
    usage, firsts, on_order, in_drafts = _load(db, business_id, [item], today)
    item_usage = usage[item.id]
    first_day = firsts[item.id]
    row = _forecast_row(db, item, item_usage, first_day, on_order.get(item.id, 0), in_drafts.get(item.id, 0), today)
    row.pop("_backtest")

    # Past days: actual usage, and what the method would have predicted that morning
    history = []
    for offset in range(CHART_HISTORY_DAYS, 0, -1):
        day = today - timedelta(days=offset)
        existed = day >= first_day
        can_predict = day - timedelta(days=WINDOW_DAYS) >= first_day
        history.append({
            "date": day,
            "actual": item_usage.get(day, 0) if existed else None,
            "predicted": round(moving_average(item_usage, day), 2) if can_predict else None,
        })

    # Future days: the forecast and the stock it implies (no new deliveries assumed)
    future = []
    daily = row["daily_forecast"]
    for offset in range(horizon_days):
        day = today + timedelta(days=offset)
        future.append({
            "date": day,
            "forecast": daily,
            "projected_stock": None if daily is None else max(0.0, round(item.quantity - daily * offset, 1)),
        })

    row.update(horizon_days=horizon_days, history=history, future=future, method=METHOD, today=today)
    return row
