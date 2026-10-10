from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import UtcDateTime


class DraftIn(BaseModel):
    email_account_id: int
    mode: Literal["new", "reply", "replyAll", "forward"] = "new"
    conversation_id: int | None = None
    in_reply_to: str | None = Field(default=None, max_length=500)
    forward_of_message_id: int | None = None
    to: str = Field(default="", max_length=20000)
    cc: str = Field(default="", max_length=20000)
    bcc: str = Field(default="", max_length=20000)
    subject: str = Field(default="", max_length=500)
    body_text: str = Field(default="", max_length=2_000_000)


class DraftOut(DraftIn):
    id: int
    account_email: str
    updated_at: UtcDateTime


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class NoteOut(BaseModel):
    id: int
    conversation_id: int
    author_user_id: int | None
    author_name: str | None
    is_yours: bool
    body: str
    created_at: UtcDateTime


class RecentNoteOut(NoteOut):
    conversation_subject: str


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str | None
    conversation_id: int | None
    actor_name: str | None
    is_read: bool
    created_at: UtcDateTime


class NotificationsOut(BaseModel):
    unread: int
    items: list[NotificationOut]


class MarkReadIn(BaseModel):
    # Empty means every notification.
    ids: list[int] = Field(default_factory=list, max_length=500)


class ContactOut(BaseModel):
    email: str
    name: str | None
    received: int
    sent: int
    last_message_at: UtcDateTime | None


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(default="", max_length=500)
    body: str = Field(min_length=1, max_length=50000)


class TemplateOut(TemplateIn):
    id: int
    created_by_name: str | None
    updated_at: UtcDateTime
