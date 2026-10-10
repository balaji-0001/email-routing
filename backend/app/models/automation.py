from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, utcnow


class Rule(Base):
    """When a new email arrives, if it matches the conditions, do the actions."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # 'new_mail': when an email arrives. 'waiting': when an email has had no reply from us for `wait_hours`.
    trigger: Mapped[str] = mapped_column(String(16), default="new_mail")
    wait_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conditions: Mapped[dict] = mapped_column(JSON)
    actions: Mapped[list] = mapped_column(JSON)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow, onupdate=utcnow)


class RuleRun(Base):
    """One rule acting on one email. `done` lists what it did and what it skipped, in plain words."""

    __tablename__ = "rule_runs"
    __table_args__ = (UniqueConstraint("rule_id", "message_id", name="uq_rule_runs_rule_message"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    rule_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("rules.id", ondelete="CASCADE"))
    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"))
    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))  # 'done', 'failed' (will retry), 'gave_up'
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class Reminder(Base):
    """A person asking to be reminded about a conversation at a set time."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"))
    due_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # When set, the reminder quietly cancels itself if the other side writes back first.
    only_if_no_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16))  # 'waiting', 'done', 'answered', 'cancelled'
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class AutomationSetting(Base):
    """An ON/OFF switch for automation at one level: the whole workspace, or one mailbox."""

    __tablename__ = "automation_settings"
    __table_args__ = (UniqueConstraint("workspace_id", "level", "level_id", name="uq_automation_settings_level"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(String(16))  # 'organization', 'email_account'
    level_id: Mapped[int] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(Boolean)
