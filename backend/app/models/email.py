from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, utcnow


class EmailAccount(Base):
    """A connected mailbox belonging to a workspace."""

    __tablename__ = "email_accounts"
    __table_args__ = (UniqueConstraint("workspace_id", "email_address", name="uq_email_accounts_workspace_email"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))  # 'imap', 'gmail', 'microsoft'
    email_address: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    incoming_host: Mapped[str] = mapped_column(String(255))
    incoming_port: Mapped[int] = mapped_column(Integer, default=993)
    incoming_security: Mapped[str] = mapped_column(String(16), default="ssl")  # 'ssl', 'starttls', 'none'
    incoming_username: Mapped[str] = mapped_column(String(320))
    outgoing_host: Mapped[str] = mapped_column(String(255))
    outgoing_port: Mapped[int] = mapped_column(Integer, default=587)
    outgoing_security: Mapped[str] = mapped_column(String(16), default="starttls")  # 'ssl', 'starttls', 'none'
    outgoing_username: Mapped[str] = mapped_column(String(320))
    credentials_encrypted: Mapped[str] = mapped_column(Text)
    # 'everyone' in the workspace, or 'restricted' to the people in email_account_members (owners and admins always).
    access_mode: Mapped[str] = mapped_column(String(16), default="everyone")
    auth_type: Mapped[str] = mapped_column(String(16), default="basic")  # 'basic' (mailbox password), 'oauth' (signed in at the provider)
    status: Mapped[str] = mapped_column(String(32), default="connected")  # 'connected', 'syncing', 'error', 'needs_reconnect'
    last_sync_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sync_cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Bringing in the mail that was already in the mailbox when it was connected.
    import_state: Mapped[str] = mapped_column(String(16), default="pending")  # 'pending', 'running', 'done'
    import_page_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    import_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow, onupdate=utcnow)


class EmailOAuthState(Base):
    """One attempt to connect a mailbox by signing in at the provider.

    Ties the provider's return to the session and workspace that started it.
    Used once, then deleted.
    """

    __tablename__ = "email_oauth_states"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    provider: Mapped[str] = mapped_column(String(32))
    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_verifier_encrypted: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), index=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)


class Folder(Base):
    """A mailbox folder/label synced from the email provider."""

    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("email_account_id", "name", name="uq_folders_account_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    email_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("email_accounts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    system_folder: Mapped[str] = mapped_column(String(32), default="custom")  # 'inbox', 'sent', 'drafts', 'trash', 'archive', 'custom'
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)


class Conversation(Base):
    """A thread of messages sharing a subject and history."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    email_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("email_accounts.id", ondelete="CASCADE"), index=True)
    provider_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(500), default="(no subject)")
    snippet: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open")  # 'open', 'pending', 'closed'
    # Shown in the list, so the list never has to read messages.
    last_sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_sender_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[str] = mapped_column(String(16), default="normal")  # 'low', 'normal', 'high', 'urgent'
    # The teammate responsible for it; empty means nobody yet.
    assignee_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    last_message_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.sent_at")


class Message(Base):
    """An individual inbound or outbound email message."""

    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("email_account_id", "provider_message_id", name="uq_messages_account_provider_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    email_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("email_accounts.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(16), default="inbound")  # 'inbound', 'outbound'
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_email: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500), default="")
    body_text: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    body_html: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(500), nullable=True)
    message_references: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    recipients: Mapped[list["MessageRecipient"]] = relationship("MessageRecipient", back_populates="message", cascade="all, delete-orphan")
    attachments: Mapped[list["Attachment"]] = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")


class MessageRecipient(Base):
    """A recipient of an email message (To, CC, or BCC)."""

    __tablename__ = "message_recipients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # 'to', 'cc', 'bcc'
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    message: Mapped["Message"] = relationship("Message", back_populates="recipients")


class Attachment(Base):
    """An attachment metadata linked to a message."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)

    message: Mapped["Message"] = relationship("Message", back_populates="attachments")


class Label(Base):
    """A workspace's own label for organizing conversations across every mailbox."""

    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_labels_workspace_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    color: Mapped[str] = mapped_column(String(16), default="blue")
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), default=utcnow)


class ConversationLabel(Base):
    __tablename__ = "conversation_labels"

    conversation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    label_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True, index=True)


class EmailAccountMember(Base):
    """One person's access to a restricted mailbox."""

    __tablename__ = "email_account_members"

    email_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("email_accounts.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    permission: Mapped[str] = mapped_column(String(16), default="send")  # 'read', 'send'


class EmailAccountRole(Base):
    """A whole role's access to a restricted mailbox."""

    __tablename__ = "email_account_roles"

    email_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("email_accounts.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), primary_key=True)
    permission: Mapped[str] = mapped_column(String(16), default="send")  # 'read', 'send'
