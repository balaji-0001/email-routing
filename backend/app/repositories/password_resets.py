from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import PasswordResetToken


def add(db: Session, token: PasswordResetToken) -> PasswordResetToken:
    db.add(token)
    db.flush()
    return token


def get_by_token_hash(db: Session, token_hash: str) -> PasswordResetToken | None:
    return db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))


def invalidate_for_user(db: Session, user_id: int, now: datetime) -> None:
    """Make every outstanding link for a user unusable."""
    db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None)).values(used_at=now))
