from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow


class AiSetting(Base):
    """AI for a workspace. Off until an owner or admin switches it on; `paused` is the emergency stop."""

    __tablename__ = "ai_settings"

    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    # Automatic sending, one switch per priority. There is none for High: it always needs a person.
    auto_send_low: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_send_medium: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_limit: Mapped[int] = mapped_column(Integer, default=20)
    # Facts the team has approved for replies: hours, policies, prices. The only source of facts besides the thread.
    business_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow, onupdate=utcnow)


class AiAccountSetting(Base):
    __tablename__ = "ai_account_settings"

    email_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("email_accounts.id", ondelete="CASCADE"), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    enabled: Mapped[bool] = mapped_column(Boolean)
    auto_send: Mapped[bool] = mapped_column(Boolean, default=True)


class AiAnalysis(Base):
    """What the AI made of one email. Also the queue: 'pending' rows are waiting to be analysed."""

    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    email_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("email_accounts.id", ondelete="CASCADE"))
    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"))
    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(16))  # 'pending', 'working', 'done', 'skipped', 'failed' (will retry), 'gave_up'
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requested_actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reply_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 'low', 'medium', 'high'
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    grounded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    risk_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Why a person must look before anything is sent. Empty means nothing stood in the way.
    hold_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class AiReply(Base):
    """A reply the AI drafted. It is sent only when a person approves this exact text."""

    __tablename__ = "ai_replies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    email_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("email_accounts.id", ondelete="CASCADE"))
    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"))
    analysis_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ai_analyses.id", ondelete="CASCADE"), unique=True)
    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"))
    to_email: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    body_hash: Mapped[str] = mapped_column(String(64))
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    # True when the app sent it with no person approving. `auto_note` says why it was not, when it was not.
    auto_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_note: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # 'pending', 'sending', 'sent', 'rejected', 'failed'
    decided_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
