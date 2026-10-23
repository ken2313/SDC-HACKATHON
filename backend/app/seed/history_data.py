"""Synthetic stock HISTORY for the demo businesses (Feature 7). Nothing here is real.

Why: a dashboard trend (and later the demand forecast, Feature 8) needs past stock
movements. A fresh demo database only has the opening quantities, so this file adds
about 30 days of made-up daily usage and supplier deliveries BEFORE today.

How it works (simple on purpose):
  * Each product has an average daily usage (cafés sell more at the weekend) and a
    usual delivery size.
  * We walk BACKWARDS from today's quantity, so the history always ends exactly at the
    quantity the product has now. Nothing about the current demo changes
    (Fresh Milk still has 20 cartons, reorder at 10).
  * Going back in time, a day "before usage" has more stock. When that would be more than
    a sensible maximum, that day gets a supplier delivery instead. This gives the usual
    saw-tooth stock pattern and the stock can never be negative.
  * Random numbers use a fixed seed per product, so every team member gets the same data.

Safe to repeat: a product only gets history if it still has nothing but its opening
quantity (so products you already used in a demo are left alone).
"""
import math
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import MOVEMENT_IN, MOVEMENT_INITIAL, MOVEMENT_OUT, ROLE_EMPLOYEE, ROLE_OWNER
from app.database import utcnow
from app.models import Business, InventoryItem, StockMovement, User
from app.seed.seed_data import SUPPLIERS_BY_BUSINESS

HISTORY_DAYS = 30
WEEKEND_FACTOR = 1.3      # Saturday and Sunday are busier
MALAYSIA_OFFSET = timedelta(hours=8)
DELIVERY_TIME = time(9, 0)   # deliveries arrive in the morning (Malaysia time)
USAGE_TIME = time(21, 0)     # usage is counted at closing time (Malaysia time)

# sku -> (average units used per day, usual delivery size)
USAGE = {
    # Kopi Kita Café: about 10 cartons of milk a day (the brief's example)
    "MILK-1L": (10, 20),
    "OATM-1L": (2, 12),
    "COFB-1KG": (1.5, 8),
    "COFB-ROB": (0.8, 4),
    "SUGR-1KG": (2, 20),
    "TEHT-500": (1.5, 8),
    "CHOC-500": (0.7, 4),
    "CUP-12OZ": (5, 25),
    "LID-12OZ": (5, 25),
    "CROI-FRZ": (1.2, 6),
    # Kedai Runcit Pak Din
    "RICE-10KG": (1.2, 10),
    "OIL-5L": (0.8, 6),
    "EGG-A30": (1.5, 6),
    "NOOD-5PK": (4, 30),
    "SOY-500": (0.8, 6),
    "FLOUR-1KG": (1.5, 12),
}


def _utc(day: date, at: time) -> datetime:
    """A Malaysian local time on `day`, stored as naive UTC like every other timestamp."""
    return datetime.combine(day, at) - MALAYSIA_OFFSET


def build_history(sku: str, current_quantity: int, threshold: int, today: date) -> tuple[int, list[dict]]:
    """Return (opening quantity, list of daily events) for the HISTORY_DAYS days before `today`.

    Each event: {"day", "kind": "in"|"out", "quantity"}. Pure function (no database), so it
    is easy to test. Events are in time order; applying them to the opening quantity ends
    exactly at `current_quantity`, and the running quantity is never negative.
    """
    average, delivery_size = USAGE[sku]
    rng = random.Random(f"orbyte-demo-history-{sku}")
    # The most stock we would expect to hold right before using a day's worth
    cap = threshold + delivery_size + math.ceil(average * 2)

    days = [today - timedelta(days=offset) for offset in range(HISTORY_DAYS, 0, -1)]  # oldest first
    per_day: list[tuple[date, int, int]] = []  # (day, delivered, used), filled newest first
    quantity_end = current_quantity
    for day in reversed(days):
        factor = WEEKEND_FACTOR if day.weekday() >= 5 else 1.0
        used = max(0, round(rng.gauss(average * factor, max(average * 0.3, 0.5))))
        quantity_start = quantity_end + used
        delivered = 0
        if quantity_start > cap:
            # Going backwards: earlier that morning a delivery arrived
            delivered = delivery_size
            quantity_start -= delivered
        per_day.append((day, delivered, used))
        quantity_end = quantity_start

    opening = quantity_end
    events = []
    for day, delivered, used in reversed(per_day):  # oldest first
        if delivered:
            events.append({"day": day, "kind": MOVEMENT_IN, "quantity": delivered})
        if used:
            events.append({"day": day, "kind": MOVEMENT_OUT, "quantity": used})
    return opening, events


def _today_my() -> date:
    return (utcnow() + MALAYSIA_OFFSET).date()


def seed_history_if_missing(db: Session, today: date | None = None) -> int:
    """Give demo products their synthetic history. Returns how many products got history."""
    today = today or _today_my()
    added = 0
    for business in db.scalars(select(Business)).all():
        if business.name not in SUPPLIERS_BY_BUSINESS:
            continue  # only the demo businesses we created
        users = {u.role: u for u in db.scalars(select(User).where(User.business_id == business.id).order_by(User.id))}
        owner = users.get(ROLE_OWNER)
        employee = users.get(ROLE_EMPLOYEE, owner)
        if owner is None:
            continue

        items = db.scalars(select(InventoryItem).where(InventoryItem.business_id == business.id)).all()
        for item in items:
            if item.sku not in USAGE or item.is_archived:
                continue
            movements = db.scalars(select(StockMovement).where(StockMovement.item_id == item.id)).all()
            untouched = (
                (len(movements) == 0 and item.quantity == 0)
                or (
                    len(movements) == 1
                    and movements[0].movement_type == MOVEMENT_INITIAL
                    and movements[0].quantity_after == item.quantity
                )
            )
            if not untouched:
                continue  # already used in a demo: leave its real history alone

            opening, events = build_history(item.sku, item.quantity, item.reorder_threshold, today)
            first_day = today - timedelta(days=HISTORY_DAYS)
            opened_at = _utc(first_day, time(8, 0))

            if movements:
                initial = movements[0]
                initial.quantity_change = opening
                initial.quantity_after = opening
                initial.created_at = opened_at
                initial.reason = "Opening quantity (demo data)"
            elif opening > 0:
                db.add(StockMovement(
                    business_id=business.id, item_id=item.id, user_id=owner.id,
                    movement_type=MOVEMENT_INITIAL, quantity_change=opening, quantity_before=0,
                    quantity_after=opening, reason="Opening quantity (demo data)", created_at=opened_at,
                ))
            item.created_at = min(item.created_at, opened_at)

            running = opening
            for number, event in enumerate(events, start=1):
                change = event["quantity"] if event["kind"] == MOVEMENT_IN else -event["quantity"]
                db.add(StockMovement(
                    business_id=business.id,
                    item_id=item.id,
                    user_id=owner.id if event["kind"] == MOVEMENT_IN else employee.id,
                    movement_type=event["kind"],
                    quantity_change=change,
                    quantity_before=running,
                    quantity_after=running + change,
                    reason="Supplier delivery (synthetic history)" if event["kind"] == MOVEMENT_IN
                    else "Daily usage (synthetic history)",
                    request_id=f"history-{item.id}-{number}",
                    created_at=_utc(event["day"], DELIVERY_TIME if event["kind"] == MOVEMENT_IN else USAGE_TIME),
                ))
                running += change
            if running != item.quantity:  # cannot happen; refuse to save inconsistent data
                db.rollback()
                raise RuntimeError(f"Synthetic history for {item.sku} does not end at the current quantity")
            added += 1
    if added:
        db.commit()
    return added


def history_movement_count(db: Session, business_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(StockMovement).where(
            StockMovement.business_id == business_id, StockMovement.request_id.like("history-%")
        )
    ) or 0
