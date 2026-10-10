from datetime import datetime

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Always stored lower-case, so the unique index is the single source of truth.
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), default="")
    timezone: Mapped[str | None] = mapped_column(String(64))
    # Whether notifications are also sent to this person's email address.
    notify_by_email: Mapped[bool] = mapped_column(Boolean, default=True)
    password_changed_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow, onupdate=utcnow)

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
