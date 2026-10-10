from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas.collab import NoteOut
from app.schemas.common import UtcDateTime

Status = Literal["open", "pending", "closed"]
LabelColor = Literal["blue", "green", "amber", "red", "violet", "teal", "grey"]


class RecipientOut(BaseModel):
    kind: str
    email: str
    name: str | None = None


class AttachmentOut(BaseModel):
    id: int
    filename: str
    content_type: str
    file_size: int


class LabelOut(BaseModel):
    id: int
    name: str
    color: str


class LabelWithCountOut(LabelOut):
    conversation_count: int = 0


class LabelIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: LabelColor = "blue"


class LabelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: LabelColor | None = None


class MessageOut(BaseModel):
    id: int
    direction: str
    sender_name: str | None
    sender_email: str
    subject: str
    body_text: str | None
    body_html: str | None
    sent_at: UtcDateTime
    is_read: bool
    is_starred: bool
    # The email's own Message-ID, which a reply has to point at.
    provider_message_id: str | None = None
    recipients: list[RecipientOut] = []
    attachments: list[AttachmentOut] = []


class ConversationOut(BaseModel):
    id: int
    email_account_id: int
    account_email: str
    account_provider: str
    subject: str
    snippet: str | None
    is_read: bool
    is_starred: bool
    is_archived: bool
    is_deleted: bool
    status: str
    last_message_at: UtcDateTime
    last_sender_name: str | None = None
    last_sender_email: str | None = None
    has_attachments: bool = False
    message_count: int = 0
    labels: list[LabelOut] = []
    assignee_user_id: int | None = None
    assignee_name: str | None = None
    priority: str = "normal"


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    notes: list[NoteOut] = []


class UpdateConversationIn(BaseModel):
    is_read: bool | None = None
    is_starred: bool | None = None
    is_archived: bool | None = None
    is_deleted: bool | None = None
    status: Status | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    # Leave out to keep, null to unassign.
    assignee_user_id: int | None = None


class SetLabelsIn(BaseModel):
    label_ids: list[int] = Field(max_length=100)


class BatchConversationIn(BaseModel):
    conversation_ids: list[int] = Field(max_length=500)
    action: Literal[
        "mark_read", "mark_unread", "star", "unstar", "archive", "unarchive", "delete", "restore",
        "status_open", "status_pending", "status_closed", "priority_low", "priority_normal", "priority_high", "priority_urgent",
    ]


class MailCountsOut(BaseModel):
    # Unread conversations in the inbox: all together and per email account.
    inbox_unread: int
    inbox_unread_by_account: dict[int, int]


class SyncMailboxOut(BaseModel):
    email_address: str
    # 'importing' while older mail is still coming in, 'done', or 'problem' when it needs reconnecting or failed.
    state: str
    stored: int
    total: int | None = None


class SyncOut(BaseModel):
    # 'none' (no mailbox), 'syncing', 'complete' or 'attention' (something is stuck; the rest may be done).
    state: str
    stored: int
    total: int | None
    percent: int | None
    mailboxes: list[SyncMailboxOut]
    last_synced_at: UtcDateTime | None = None


class OverviewOut(BaseModel):
    sync: SyncOut
    # Everything counts only the mailboxes the signed-in person may use.
    connected_inboxes: int
    inboxes_needing_attention: int
    messages_stored: int
    open_conversations: int
    waiting_on_team: int
    unread_conversations: int
    needs_attention: list[ConversationOut]


class AttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = "application/octet-stream"
    content_base64: str


Address = Annotated[str, Field(max_length=400)]


class SendMessageIn(BaseModel):
    account_id: int
    to: list[Address] = Field(max_length=100)
    subject: str = Field(max_length=2000)
    body_text: str | None = Field(None, max_length=2_000_000)
    body_html: str | None = Field(None, max_length=4_000_000)
    cc: list[Address] | None = Field(None, max_length=100)
    bcc: list[Address] | None = Field(None, max_length=100)
    conversation_id: int | None = None
    # The Message-ID of the email being answered (reply, reply all).
    in_reply_to: str | None = Field(None, max_length=500)
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=25)
    # Forwarding: the id of the message whose attachments go along.
    forward_attachments_of: int | None = None
    # The saved draft this message was written in; it is removed once the message is sent.
    draft_id: int | None = None
