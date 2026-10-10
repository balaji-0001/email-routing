from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuthSession


def add(db: Session, session: AuthSession) -> AuthSession:
    db.add(session)
    db.flush()
    return session


def get_by_token_hash(db: Session, token_hash: str) -> AuthSession | None:
    return db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))


def active_for_user(db: Session, user_id: int, now: datetime) -> list[AuthSession]:
    return list(
        db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
            .order_by(AuthSession.last_used_at.desc())
        )
    )


def revoke_all(db: Session, user_id: int, now: datetime, *, except_id: int | None = None) -> int:
    """End every active session of a user, optionally keeping one. Returns how many ended."""
    statement = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
    if except_id is not None:
        statement = statement.where(AuthSession.id != except_id)
    return db.execute(statement.values(revoked_at=now)).rowcount
