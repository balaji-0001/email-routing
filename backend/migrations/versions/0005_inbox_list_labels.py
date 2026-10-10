"""What the inbox list shows per conversation, and labels.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def upgrade() -> None:
    # Kept on the conversation so the list never has to read messages.
    op.add_column("conversations", sa.Column("last_sender_name", sa.String(255), nullable=True))
    op.add_column("conversations", sa.Column("last_sender_email", sa.String(320), nullable=True))
    op.add_column("conversations", sa.Column("has_attachments", sa.Boolean, nullable=False, server_default="0"))
    op.add_column("conversations", sa.Column("message_count", sa.Integer, nullable=False, server_default="0"))
    op.create_index("ix_conversations_workspace_last_message", "conversations", ["workspace_id", "last_message_at"])

    op.execute("UPDATE conversations c SET c.message_count = (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id)")
    op.execute(
        "UPDATE conversations c SET c.has_attachments = EXISTS ("
        "SELECT 1 FROM attachments a JOIN messages m ON m.id = a.message_id WHERE m.conversation_id = c.id)"
    )
    op.execute(
        "UPDATE conversations c JOIN messages m ON m.id = ("
        "SELECT m2.id FROM messages m2 WHERE m2.conversation_id = c.id ORDER BY m2.sent_at DESC, m2.id DESC LIMIT 1) "
        "SET c.last_sender_name = m.sender_name, c.last_sender_email = m.sender_email"
    )

    op.create_table(
        "labels",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_labels_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("color", sa.String(16), nullable=False, server_default="blue"),
        sa.Column("created_at", DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_labels_workspace_name"),
        **TABLE_OPTIONS,
    )
    op.create_table(
        "conversation_labels",
        sa.Column("conversation_id", sa.BigInteger, sa.ForeignKey("conversations.id", name="fk_conversation_labels_conversation", ondelete="CASCADE"), primary_key=True),
        sa.Column("label_id", sa.BigInteger, sa.ForeignKey("labels.id", name="fk_conversation_labels_label", ondelete="CASCADE"), primary_key=True),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_conversation_labels_label_id", "conversation_labels", ["label_id"])


def downgrade() -> None:
    op.drop_table("conversation_labels")
    op.drop_table("labels")
    op.drop_index("ix_conversations_workspace_last_message", table_name="conversations")
    for column in ("message_count", "has_attachments", "last_sender_email", "last_sender_name"):
        op.drop_column("conversations", column)
