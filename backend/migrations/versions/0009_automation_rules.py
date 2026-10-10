"""Automation: rules, their run history, the ON/OFF switches, and conversation priority.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-09
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

T = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def upgrade() -> None:
    op.add_column("conversations", sa.Column("priority", sa.String(16), nullable=False, server_default="normal"))

    op.create_table(
        "rules",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_rules_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_rules_created_by", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conditions", sa.JSON, nullable=False),
        sa.Column("actions", sa.JSON, nullable=False),
        sa.Column("run_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_run_at", DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
        **T,
    )
    op.create_index("ix_rules_workspace", "rules", ["workspace_id", "position"])

    op.create_table(
        "rule_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_rule_runs_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.BigInteger, sa.ForeignKey("rules.id", name="fk_rule_runs_rule", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.BigInteger, sa.ForeignKey("messages.id", name="fk_rule_runs_message", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.BigInteger, sa.ForeignKey("conversations.id", name="fk_rule_runs_conversation", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("done", sa.JSON, nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("next_attempt_at", DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("finished_at", DATETIME(fsp=6), nullable=True),
        # One run per rule per email, however often the same email is seen: this is what prevents duplicates.
        sa.UniqueConstraint("rule_id", "message_id", name="uq_rule_runs_rule_message"),
        **T,
    )
    op.create_index("ix_rule_runs_workspace_created", "rule_runs", ["workspace_id", "created_at"])
    op.create_index("ix_rule_runs_retry", "rule_runs", ["status", "next_attempt_at"])

    op.create_table(
        "automation_settings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_automation_settings_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("level_id", sa.BigInteger, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.UniqueConstraint("workspace_id", "level", "level_id", name="uq_automation_settings_level"),
        **T,
    )


def downgrade() -> None:
    for table in ("automation_settings", "rule_runs", "rules"):
        op.drop_table(table)
    op.drop_column("conversations", "priority")
