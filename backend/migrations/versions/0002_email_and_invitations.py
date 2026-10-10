"""Email accounts, sync, conversations, messages, and workspace invitations.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME, LONGTEXT

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def _timestamp(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, DATETIME(fsp=6), nullable=nullable)


def upgrade() -> None:
    # 1. workspace_invitations
    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_workspace_invitations_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("invited_by_user_id", sa.BigInteger, sa.ForeignKey("users.id", name="fk_workspace_invitations_invited_by_user", ondelete="SET NULL"), nullable=True),
        _timestamp("expires_at"),
        _timestamp("accepted_at", nullable=True),
        _timestamp("created_at"),
        sa.UniqueConstraint("token_hash", name="uq_workspace_invitations_token_hash"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_workspace_invitations_workspace_id", "workspace_invitations", ["workspace_id"])
    op.create_index("ix_workspace_invitations_invited_by_user_id", "workspace_invitations", ["invited_by_user_id"])
    op.create_index("ix_workspace_invitations_expires_at", "workspace_invitations", ["expires_at"])

    # 2. email_accounts
    op.create_table(
        "email_accounts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_email_accounts_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("email_address", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("incoming_host", sa.String(255), nullable=False),
        sa.Column("incoming_port", sa.Integer, nullable=False, server_default="993"),
        sa.Column("incoming_security", sa.String(16), nullable=False, server_default="ssl"),
        sa.Column("incoming_username", sa.String(320), nullable=False),
        sa.Column("outgoing_host", sa.String(255), nullable=False),
        sa.Column("outgoing_port", sa.Integer, nullable=False, server_default="587"),
        sa.Column("outgoing_security", sa.String(16), nullable=False, server_default="starttls"),
        sa.Column("outgoing_username", sa.String(320), nullable=False),
        sa.Column("credentials_encrypted", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="connected"),
        _timestamp("last_sync_at", nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("sync_cursor", sa.String(255), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.UniqueConstraint("workspace_id", "email_address", name="uq_email_accounts_workspace_email"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_email_accounts_workspace_id", "email_accounts", ["workspace_id"])

    # 3. folders
    op.create_table(
        "folders",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_folders_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("email_account_id", sa.BigInteger, sa.ForeignKey("email_accounts.id", name="fk_folders_email_account", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("system_folder", sa.String(32), nullable=False, server_default="custom"),
        _timestamp("created_at"),
        sa.UniqueConstraint("email_account_id", "name", name="uq_folders_account_name"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_folders_workspace_id", "folders", ["workspace_id"])
    op.create_index("ix_folders_email_account_id", "folders", ["email_account_id"])

    # 4. conversations
    op.create_table(
        "conversations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_conversations_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("email_account_id", sa.BigInteger, sa.ForeignKey("email_accounts.id", name="fk_conversations_email_account", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_thread_id", sa.String(255), nullable=True),
        sa.Column("subject", sa.String(500), nullable=False, server_default="(no subject)"),
        sa.Column("snippet", sa.String(500), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("is_starred", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        _timestamp("last_message_at"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_conversations_workspace_id", "conversations", ["workspace_id"])
    op.create_index("ix_conversations_email_account_id", "conversations", ["email_account_id"])
    op.create_index("ix_conversations_provider_thread_id", "conversations", ["provider_thread_id"])
    op.create_index("ix_conversations_is_read", "conversations", ["is_read"])
    op.create_index("ix_conversations_is_starred", "conversations", ["is_starred"])
    op.create_index("ix_conversations_is_archived", "conversations", ["is_archived"])
    op.create_index("ix_conversations_is_deleted", "conversations", ["is_deleted"])
    op.create_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])

    # 5. messages
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", name="fk_messages_workspace", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.BigInteger, sa.ForeignKey("conversations.id", name="fk_messages_conversation", ondelete="CASCADE"), nullable=False),
        sa.Column("email_account_id", sa.BigInteger, sa.ForeignKey("email_accounts.id", name="fk_messages_email_account", ondelete="CASCADE"), nullable=False),
        sa.Column("folder_id", sa.BigInteger, sa.ForeignKey("folders.id", name="fk_messages_folder", ondelete="SET NULL"), nullable=True),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        sa.Column("direction", sa.String(16), nullable=False, server_default="inbound"),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("sender_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False, server_default=""),
        sa.Column("body_text", LONGTEXT, nullable=True),
        sa.Column("body_html", LONGTEXT, nullable=True),
        sa.Column("in_reply_to", sa.String(500), nullable=True),
        sa.Column("message_references", LONGTEXT, nullable=True),
        _timestamp("sent_at"),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("is_starred", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("is_draft", sa.Boolean, nullable=False, server_default="0"),
        _timestamp("created_at"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_messages_workspace_id", "messages", ["workspace_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_email_account_id", "messages", ["email_account_id"])
    op.create_index("ix_messages_folder_id", "messages", ["folder_id"])
    op.create_index("ix_messages_provider_message_id", "messages", ["provider_message_id"])
    op.create_index("ix_messages_sent_at", "messages", ["sent_at"])

    # 6. message_recipients
    op.create_table(
        "message_recipients",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.BigInteger, sa.ForeignKey("messages.id", name="fk_message_recipients_message", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_message_recipients_message_id", "message_recipients", ["message_id"])

    # 7. attachments
    op.create_table(
        "attachments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.BigInteger, sa.ForeignKey("messages.id", name="fk_attachments_message", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False, server_default="application/octet-stream"),
        sa.Column("file_size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("storage_path", sa.String(500), nullable=True),
        _timestamp("created_at"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_attachments_message_id", "attachments", ["message_id"])


def downgrade() -> None:
    for table in ("attachments", "message_recipients", "messages", "conversations", "folders", "email_accounts", "workspace_invitations"):
        op.drop_table(table)
