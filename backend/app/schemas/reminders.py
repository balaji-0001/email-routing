from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import UtcDateTime


class ReminderIn(BaseModel):
    conversation_id: int
    due_at: datetime
    note: str = Field("", max_length=300)
    only_if_no_reply: bool = False


class ReminderOut(BaseModel):
    id: int
    conversation_id: int
    subject: str
    account_email: str
    due_at: UtcDateTime
    note: str
    only_if_no_reply: bool
    status: str
    created_at: UtcDateTime
    finished_at: UtcDateTime | None
