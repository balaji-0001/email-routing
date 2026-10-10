"""Accounts, workspaces, sessions, password resets and the audit log.

Revision ID: 0001
Revises:
Create Date: 2026-10-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def _timestamp(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, DATETIME(fsp=6), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=True),
        _timestamp("password_changed_at"),
        _timestamp("last_login_at", nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        **TABLE_OPTIONS,
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("allow_invitations", sa.Boolean, nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_workspaces_created_by_user", ondelete="SET NULL"), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_workspaces_created_by_user_id", "workspaces", ["created_by_user_id"])

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_workspace_members_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_workspace_members_user", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        _timestamp("created_at"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_sessions_user", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_sessions_workspace", ondelete="SET NULL"), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("remember", sa.Boolean, nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        _timestamp("created_at"),
        _timestamp("last_used_at"),
        _timestamp("expires_at"),
        _timestamp("revoked_at", nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_workspace_id", "sessions", ["workspace_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_password_reset_tokens_user", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        _timestamp("created_at"),
        _timestamp("expires_at"),
        _timestamp("used_at", nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_audit_events_workspace", ondelete="CASCADE"), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_audit_events_actor_user", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("summary", sa.String(255), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        _timestamp("created_at"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_audit_events_workspace_created", "audit_events", ["workspace_id", "created_at"])
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])


def downgrade() -> None:
    for table in ("audit_events", "password_reset_tokens", "sessions", "workspace_members", "workspaces", "users"):
        op.drop_table(table)
