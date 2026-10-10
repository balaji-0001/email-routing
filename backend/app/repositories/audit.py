from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, User


def add(db: Session, event: AuditEvent) -> AuditEvent:
    db.add(event)
    return event


def for_workspace(db: Session, workspace_id: int, limit: int) -> list[tuple[AuditEvent, User | None]]:
    """Newest first, each with the person who did it (if they still exist)."""
    rows = db.execute(
        select(AuditEvent, User)
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .where(AuditEvent.workspace_id == workspace_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    return [(event, actor) for event, actor in rows]
