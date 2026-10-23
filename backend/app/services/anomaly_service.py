"""AI anomaly detection for stock OUT movements (Feature 9).

Flow (runs in the background AFTER the stock change is saved, so stock never waits for
or depends on the AI):
  1. Add up how much of the product was used that day (Malaysia time), including
     this movement.
  2. Work out normal daily usage from the previous 30 days that had usage
     (the synthetic history gives the demo products ~30 days).
  3. Ask the AI server (PyTorch autoencoder on a RunPod GPU) through ai_client.
  4. Save the answer in anomaly_flags. "Unusual" / "Highly Unusual" results are also
     written to the activity log as a System action, for a human to review.

If the AI is not configured (no AI_BASE_URL), nothing is saved and the app works as before.
If it is configured but down, the result is saved as "AI unavailable" so it is visible.
Nothing in this file ever changes stock.
"""
import os
import statistics
from datetime import date, datetime, time, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import MOVEMENT_OUT
from app.database import SessionLocal, utcnow
from app.integrations.ai_client import score_movement
from app.models import AnomalyFlag, InventoryItem, StockMovement, User
from app.services.activity_service import log_activity

FLAG_STATUSES = ("Unusual", "Highly Unusual")
HISTORY_WINDOW_DAYS = 30
LOCAL_OFFSET = timedelta(hours=8)  # Malaysia time, same as the synthetic history


class AnomalyError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def ai_configured() -> bool:
    return bool(os.environ.get("AI_BASE_URL", "").strip())


def _local_day(timestamp: datetime) -> date:
    return (timestamp + LOCAL_OFFSET).date()


def _utc_start_of(day: date) -> datetime:
    return datetime.combine(day, time.min) - LOCAL_OFFSET


def compute_usage_stats(db: Session, movement: StockMovement) -> dict:
    """Daily usage numbers for the AI. Days with no usage (e.g. closed) are skipped."""
    day = _local_day(movement.created_at)
    rows = db.scalars(
        select(StockMovement).where(
            StockMovement.business_id == movement.business_id,
            StockMovement.item_id == movement.item_id,
            StockMovement.movement_type == MOVEMENT_OUT,
            StockMovement.created_at >= _utc_start_of(day - timedelta(days=HISTORY_WINDOW_DAYS)),
            StockMovement.created_at < _utc_start_of(day + timedelta(days=1)),
        )
    ).all()

    past_days: dict[date, int] = {}
    day_total = 0
    for row in rows:
        used = abs(row.quantity_change)
        row_day = _local_day(row.created_at)
        if row_day == day:
            if row.id <= movement.id:  # count this movement and earlier ones that day
                day_total += used
        else:
            past_days[row_day] = past_days.get(row_day, 0) + used

    usage = [total for total in past_days.values() if total > 0]
    return {
        "day_total_out": day_total,
        "recent_avg_usage": round(statistics.fmean(usage), 3) if usage else 0.0,
        "usage_std": round(statistics.pstdev(usage), 3) if len(usage) > 1 else 0.0,
        "history_days": len(usage),
        "day_of_week": day.weekday(),  # 0 = Monday
    }


def check_movement_for_anomaly(movement_id: int, session_factory=SessionLocal) -> None:
    """Background task. Never raises: a problem here must never affect stock."""
    if not ai_configured():
        return
    try:
        with session_factory() as db:
            _check(db, movement_id)
    except Exception as error:  # noqa: BLE001
        print(f"AI anomaly check failed for movement {movement_id}: {error}")


def _check(db: Session, movement_id: int) -> None:
    movement = db.get(StockMovement, movement_id)
    if movement is None or movement.movement_type != MOVEMENT_OUT:
        return
    if db.scalar(select(AnomalyFlag.id).where(AnomalyFlag.movement_id == movement_id)) is not None:
        return  # already checked: retries never create a second result

    item = db.get(InventoryItem, movement.item_id)
    stats = compute_usage_stats(db, movement)
    request_id = f"mov-{movement.id}"
    result = score_movement({
        "request_id": request_id,
        "product_id": item.sku if item else str(movement.item_id),
        "movement_type": "OUT",
        "quantity": stats["day_total_out"],
        "day_of_week": stats["day_of_week"],
        "recent_avg_usage": stats["recent_avg_usage"],
        "usage_std": stats["usage_std"],
        "history_days": stats["history_days"],
    })

    expected = result.get("expected_range")
    if not (isinstance(expected, list) and len(expected) == 2):
        expected = [None, None]
    top = result.get("top_contributing_features") or []
    score = result.get("anomaly_score")

    flag = AnomalyFlag(
        business_id=movement.business_id,
        item_id=movement.item_id,
        movement_id=movement.id,
        request_id=request_id,
        day_total_out=stats["day_total_out"],
        recent_avg_usage=stats["recent_avg_usage"],
        usage_std=stats["usage_std"],
        history_days=stats["history_days"],
        status=str(result.get("status", "AI unavailable"))[:30],
        anomaly_score=float(score) if isinstance(score, (int, float)) else None,
        top_feature=str(top[0])[:120] if top else None,  # only the top one; later ones can be noise
        expected_low=expected[0],
        expected_high=expected[1],
        device=result.get("device"),
        model_version=result.get("model_version"),
        inference_ms=result.get("inference_ms"),
        reason=str(result["reason"])[:255] if result.get("reason") else None,
    )
    db.add(flag)
    try:
        db.flush()
        if flag.status in FLAG_STATUSES:
            name = item.name if item else f"item {movement.item_id}"
            unit = item.unit if item else "units"
            log_activity(
                db, None, "anomaly.flagged", "anomaly_flag", flag.id,
                f"AI flagged {name}: {stats['day_total_out']} {unit} used today vs usual "
                f"~{stats['recent_avg_usage']:.0f} ({flag.status}, needs human review)",
                new_value={
                    "status": flag.status,
                    "anomaly_score": flag.anomaly_score,
                    "expected_range": [flag.expected_low, flag.expected_high],
                    "movement_id": movement.id,
                    "device": flag.device,
                },
                business_id=movement.business_id,
            )
        db.commit()
    except IntegrityError:
        db.rollback()  # another worker saved this movement's result first


def _to_dict(flag: AnomalyFlag, item: InventoryItem, reviewer_name: str | None) -> dict:
    return {
        "id": flag.id,
        "item_id": flag.item_id,
        "sku": item.sku,
        "product_name": item.name,
        "unit": item.unit,
        "movement_id": flag.movement_id,
        "day_total_out": flag.day_total_out,
        "recent_avg_usage": flag.recent_avg_usage,
        "history_days": flag.history_days,
        "status": flag.status,
        "anomaly_score": flag.anomaly_score,
        "top_feature": flag.top_feature,
        "expected_low": flag.expected_low,
        "expected_high": flag.expected_high,
        "device": flag.device,
        "model_version": flag.model_version,
        "inference_ms": flag.inference_ms,
        "reason": flag.reason,
        "reviewed": flag.reviewed,
        "reviewed_by": flag.reviewed_by,
        "reviewed_by_name": reviewer_name,
        "reviewed_at": flag.reviewed_at,
        "review_note": flag.review_note,
        "created_at": flag.created_at,
    }


def list_flags(db: Session, business_id: int, state: str = "open", results: str = "flags") -> list[dict]:
    """state: open / reviewed / all. results: "flags" (Unusual + Highly Unusual) or "all" checks."""
    query = (
        select(AnomalyFlag, InventoryItem)
        .join(InventoryItem, InventoryItem.id == AnomalyFlag.item_id)
        .where(AnomalyFlag.business_id == business_id)
    )
    if results == "flags":
        query = query.where(AnomalyFlag.status.in_(FLAG_STATUSES))
    if state == "open":
        query = query.where(AnomalyFlag.reviewed.is_(False))
    elif state == "reviewed":
        query = query.where(AnomalyFlag.reviewed.is_(True))
    rows = db.execute(query.order_by(AnomalyFlag.created_at.desc(), AnomalyFlag.id.desc()).limit(100)).all()

    reviewer_ids = {flag.reviewed_by for flag, _ in rows if flag.reviewed_by}
    names = {}
    if reviewer_ids:
        names = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(reviewer_ids)))}
    return [_to_dict(flag, item, names.get(flag.reviewed_by)) for flag, item in rows]


def review_flag(db: Session, user: User, flag_id: int, note: str) -> dict:
    note = note.strip()
    if not note:
        raise AnomalyError(422, "Please write a short review note.")
    flag = db.get(AnomalyFlag, flag_id)
    if flag is None or flag.business_id != user.business_id:
        raise AnomalyError(404, "Anomaly not found.")
    if flag.status not in FLAG_STATUSES:
        raise AnomalyError(409, "Only flagged results can be reviewed.")

    reviewed_at = utcnow()
    # Atomic: only one review can ever win, even if two people click at the same time
    changed = db.execute(
        update(AnomalyFlag)
        .where(AnomalyFlag.id == flag_id, AnomalyFlag.reviewed.is_(False))
        .values(reviewed=True, reviewed_by=user.id, reviewed_at=reviewed_at, review_note=note)
    ).rowcount
    if changed == 0:
        db.rollback()
        raise AnomalyError(409, "This anomaly was already reviewed.")

    item = db.get(InventoryItem, flag.item_id)
    log_activity(
        db, user, "anomaly.reviewed", "anomaly_flag", flag.id,
        f"{user.name} reviewed the AI flag on {item.name}: {note}",
        old_value={"reviewed": False},
        new_value={"reviewed": True, "status": flag.status, "note": note},
    )
    db.commit()
    db.refresh(flag)
    return _to_dict(flag, item, user.name)