"""AI triage: settings, one analysis per email, and reply drafts that wait for approval.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

T = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def _fk(table: str, column: str, target: str, ondelete: str = "CASCADE") -> sa.ForeignKey:
    return sa.ForeignKey(f"{target}.id", name=f"fk_{table}_{column}", ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        "ai_settings",
        sa.Column("workspace_id", sa.BigInteger, _fk("ai_settings", "workspace_id", "workspaces"), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("paused", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("business_info", sa.Text, nullable=True),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
        **T,
    )
    op.create_table(
        "ai_account_settings",
        sa.Column("email_account_id", sa.BigInteger, _fk("ai_account_settings", "email_account_id", "email_accounts"), primary_key=True),
        sa.Column("workspace_id", sa.BigInteger, _fk("ai_account_settings", "workspace_id", "workspaces"), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        **T,
    )
    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, _fk("ai_analyses", "workspace_id", "workspaces"), nullable=False),
        sa.Column("email_account_id", sa.BigInteger, _fk("ai_analyses", "email_account_id", "email_accounts"), nullable=False),
        sa.Column("conversation_id", sa.BigInteger, _fk("ai_analyses", "conversation_id", "conversations"), nullable=False),
        # One analysis per email, however often the email is seen or asked about.
        sa.Column("message_id", sa.BigInteger, _fk("ai_analyses", "message_id", "messages"), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", DATETIME(fsp=6), nullable=True),
        sa.Column("started_at", DATETIME(fsp=6), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("intent", sa.String(500), nullable=True),
        sa.Column("requested_actions", sa.JSON, nullable=True),
        sa.Column("reply_required", sa.Boolean, nullable=True),
        sa.Column("priority", sa.String(8), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("grounded", sa.Boolean, nullable=True),
        sa.Column("risk_flags", sa.JSON, nullable=True),
        sa.Column("hold_reasons", sa.JSON, nullable=True),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("finished_at", DATETIME(fsp=6), nullable=True),
        **T,
    )
    op.create_index("ix_ai_analyses_queue", "ai_analyses", ["status", "next_attempt_at"])
    op.create_index("ix_ai_analyses_conversation", "ai_analyses", ["conversation_id", "id"])
    op.create_index("ix_ai_analyses_workspace", "ai_analyses", ["workspace_id", "created_at"])
    op.create_table(
        "ai_replies",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, _fk("ai_replies", "workspace_id", "workspaces"), nullable=False),
        sa.Column("email_account_id", sa.BigInteger, _fk("ai_replies", "email_account_id", "email_accounts"), nullable=False),
        sa.Column("conversation_id", sa.BigInteger, _fk("ai_replies", "conversation_id", "conversations"), nullable=False),
        # One draft per analysis.
        sa.Column("analysis_id", sa.BigInteger, _fk("ai_replies", "analysis_id", "ai_analyses"), nullable=False, unique=True),
        sa.Column("message_id", sa.BigInteger, _fk("ai_replies", "message_id", "messages"), nullable=False),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("edited", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by_user_id", sa.BigInteger, _fk("ai_replies", "decided_by_user_id", "users", "SET NULL"), nullable=True),
        sa.Column("approved_hash", sa.String(64), nullable=True),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("sent_message_id", sa.BigInteger, nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("decided_at", DATETIME(fsp=6), nullable=True),
        sa.Column("sent_at", DATETIME(fsp=6), nullable=True),
        **T,
    )
    op.create_index("ix_ai_replies_queue", "ai_replies", ["workspace_id", "status", "created_at"])


def downgrade() -> None:
    for table in ("ai_replies", "ai_analyses", "ai_account_settings", "ai_settings"):
        op.drop_table(table)
