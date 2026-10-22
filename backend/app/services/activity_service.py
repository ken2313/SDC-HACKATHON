import json

from sqlalchemy.orm import Session

from app.models import ActivityLog, User


def log_activity(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    summary: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
    business_id: int | None = None,
) -> None:
    """Add an audit-log row to the current transaction.

    This does NOT commit. The caller commits, so the business change and its
    log entry are saved together or not at all.

    `user` may be None for automatic system actions (for example the start-up
    scan that opens alerts). In that case pass `business_id` and the row is
    stored with no user, which the Activity Logs page will show as "System".
    """
    if user is None and business_id is None:
        raise ValueError("business_id is required when there is no user")

    db.add(
        ActivityLog(
            business_id=user.business_id if user is not None else business_id,
            user_id=user.id if user is not None else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary[:255],
            old_value=json.dumps(old_value) if old_value is not None else None,
            new_value=json.dumps(new_value) if new_value is not None else None,
        )
    )
