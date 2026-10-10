from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow


class AuthSession(Base):
    """A signed-in browser. The cookie holds the token; only its hash is stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # The workspace this session is working in. Empty until the user has one.
    workspace_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="SET NULL"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    remember: Mapped[bool] = mapped_column(Boolean, default=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    used_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
