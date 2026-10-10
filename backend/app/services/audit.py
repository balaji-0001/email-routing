from sqlalchemy.orm import Session

from app.models import AuditEvent, User
from app.repositories import audit as audit_repo


def record(db: Session, *, action: str, summary: str, actor: User | None, workspace_id: int | None, ip: str | None) -> None:
    """Add an audit row to the current transaction. The caller commits."""
    audit_repo.add(
        db,
        AuditEvent(workspace_id=workspace_id, actor_user_id=actor.id if actor else None, action=action, summary=summary[:255], ip_address=ip),
    )
