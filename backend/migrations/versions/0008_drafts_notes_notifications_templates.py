"""Saved drafts, assignment, internal notes, notifications and templates.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME, LONGTEXT

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

T = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def _fk(table: str, column: str, target: str, ondelete: str) -> sa.ForeignKey:
    return sa.ForeignKey(f"{target}.id", name=f"fk_{table}_{column}", ondelete=ondelete)


def upgrade() -> None:
    op.add_column("conversations", sa.Column("assignee_user_id", sa.BigInteger, nullable=True))
    op.create_foreign_key("fk_conversations_assignee_user_id", "conversations", "users", ["assignee_user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_conversations_assignee_user_id", "conversations", ["assignee_user_id"])
    # Contacts are read from the people in the mail, by address.
    op.create_index("ix_messages_sender_email", "messages", ["sender_email"])

    op.create_table(
        "drafts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, _fk("drafts", "workspace_id", "workspaces", "CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger, _fk("drafts", "user_id", "users", "CASCADE"), nullable=False),
        sa.Column("email_account_id", sa.BigInteger, _fk("drafts", "email_account_id", "email_accounts", "CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.BigInteger, _fk("drafts", "conversation_id", "conversations", "SET NULL"), nullable=True),
        sa.Column("forward_of_message_id", sa.BigInteger, _fk("drafts", "forward_of_message_id", "messages", "SET NULL"), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False, server_default="new"),
        sa.Column("in_reply_to", sa.String(500), nullable=True),
        sa.Column("to_addresses", sa.Text, nullable=False),
        sa.Column("cc_addresses", sa.Text, nullable=False),
        sa.Column("bcc_addresses", sa.Text, nullable=False),
        sa.Column("subject", sa.String(500), nullable=False, server_default=""),
        sa.Column("body_text", LONGTEXT, nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
        **T,
    )
    op.create_index("ix_drafts_user_workspace", "drafts", ["user_id", "workspace_id"])

    op.create_table(
        "notes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, _fk("notes", "workspace_id", "workspaces", "CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.BigInteger, _fk("notes", "conversation_id", "conversations", "CASCADE"), nullable=False),
        sa.Column("author_user_id", sa.BigInteger, _fk("notes", "author_user_id", "users", "SET NULL"), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        **T,
    )
    op.create_index("ix_notes_conversation_id", "notes", ["conversation_id"])
    op.create_index("ix_notes_workspace_created", "notes", ["workspace_id", "created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, _fk("notifications", "workspace_id", "workspaces", "CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger, _fk("notifications", "user_id", "users", "CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger, _fk("notifications", "actor_user_id", "users", "SET NULL"), nullable=True),
        sa.Column("conversation_id", sa.BigInteger, _fk("notifications", "conversation_id", "conversations", "SET NULL"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.String(500), nullable=True),
        sa.Column("read_at", DATETIME(fsp=6), nullable=True),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        **T,
    )
    op.create_index("ix_notifications_user", "notifications", ["user_id", "workspace_id", "read_at"])

    op.create_table(
        "templates",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, _fk("templates", "workspace_id", "workspaces", "CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger, _fk("templates", "created_by_user_id", "users", "SET NULL"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False, server_default=""),
        sa.Column("body", LONGTEXT, nullable=False),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_templates_workspace_name"),
        **T,
    )


def downgrade() -> None:
    for table in ("templates", "notifications", "notes", "drafts"):
        op.drop_table(table)
    op.drop_index("ix_messages_sender_email", table_name="messages")
    op.drop_constraint("fk_conversations_assignee_user_id", "conversations", type_="foreignkey")
    op.drop_index("ix_conversations_assignee_user_id", table_name="conversations")
    op.drop_column("conversations", "assignee_user_id")
