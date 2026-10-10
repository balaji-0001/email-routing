"""Follow-up reminders, and rules that act when an email has waited without a reply.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rules keep doing what they did: act when a new email arrives.
    op.add_column("rules", sa.Column("trigger", sa.String(16), nullable=False, server_default="new_mail"))
    op.add_column("rules", sa.Column("wait_hours", sa.Integer, nullable=True))
    op.create_table(
        "reminders",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_reminders_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_reminders_user", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.BigInteger, sa.ForeignKey("conversations.id", name="fk_reminders_conversation", ondelete="CASCADE"), nullable=False),
        sa.Column("due_at", DATETIME(fsp=6), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("only_if_no_reply", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("finished_at", DATETIME(fsp=6), nullable=True),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_reminders_due", "reminders", ["status", "due_at"])
    op.create_index("ix_reminders_user", "reminders", ["user_id", "status"])


def downgrade() -> None:
    op.drop_table("reminders")
    op.drop_column("rules", "wait_hours")
    op.drop_column("rules", "trigger")
