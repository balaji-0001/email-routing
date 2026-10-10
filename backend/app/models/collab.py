from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow


class Draft(Base):
    """A message someone started and has not sent. Only its author sees it."""

    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    email_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("email_accounts.id", ondelete="CASCADE"))
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    forward_of_message_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="new")  # 'new', 'reply', 'replyAll', 'forward'
    in_reply_to: Mapped[str | None] = mapped_column(String(500), nullable=True)
    to_addresses: Mapped[str] = mapped_column(Text, default="")
    cc_addresses: Mapped[str] = mapped_column(Text, default="")
    bcc_addresses: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body_text: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow, onupdate=utcnow)


class Note(Base):
    """A private note on a conversation. Never sent to anyone outside the workspace."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    author_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)


class Notification(Base):
    """Something one person should know about: an assignment, a mention, a note on their conversation."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))  # 'assigned', 'mentioned', 'note'
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(String(500), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    # Whether it has also gone to the person by email: 'pending', 'sent', 'skipped', 'failed'.
    email_state: Mapped[str] = mapped_column(String(12), default="pending")
    email_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)


class Template(Base):
    """A reusable reply for the whole workspace."""

    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_templates_workspace_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(LONGTEXT)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow, onupdate=utcnow)
