import json

from sqlalchemy.orm import Session

from app.models import ActivityLog, User


def log_activity(
    db: Session,
    user: User,
    action: str,
    entity_type: str,
    entity_id: int | None,
    summary: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    """Add an audit-log row to the current transaction.

    This does NOT commit. The caller commits, so the business change and its
    log entry are saved together or not at all.
    """
    db.add(
        ActivityLog(
            business_id=user.business_id,
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary[:255],
            old_value=json.dumps(old_value) if old_value is not None else None,
            new_value=json.dumps(new_value) if new_value is not None else None,
        )
    )
