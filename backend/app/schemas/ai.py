from pydantic import BaseModel, Field

from app.schemas.common import UtcDateTime


class AiMailbox(BaseModel):
    account_id: int
    email_address: str
    enabled: bool
    auto_send: bool = True


class AiSettingsOut(BaseModel):
    # False until GEMINI_API_KEY is set on the server.
    configured: bool
    model: str
    enabled: bool
    paused: bool
    business_info: str
    has_business_info: bool = False
    mailboxes: list[AiMailbox]
    # Automatic sending: off until switched on, separately for Low and Medium. Never for High.
    auto_send_low: bool = False
    auto_send_medium: bool = False
    daily_limit: int = 20
    auto_sent_today: int = 0


class AiSettingsIn(BaseModel):
    enabled: bool | None = None
    paused: bool | None = None
    business_info: str | None = Field(None, max_length=20000)
    mailboxes: dict[int, bool] = {}
    auto_send_low: bool | None = None
    auto_send_medium: bool | None = None
    daily_limit: int | None = Field(None, ge=1, le=500)
    mailbox_auto_send: dict[int, bool] = {}


class AnalysisOut(BaseModel):
    id: int
    conversation_id: int
    message_id: int
    account_email: str
    subject: str
    sender: str
    status: str
    attempts: int
    summary: str | None
    intent: str | None
    requested_actions: list[str]
    reply_required: bool | None
    priority: str | None
    confidence: float | None
    grounded: bool | None
    risk_flags: list[str]
    hold_reasons: list[str]
    reason: str | None
    error: str | None
    reply_id: int | None = None
    reply_status: str | None = None
    created_at: UtcDateTime
    finished_at: UtcDateTime | None


class ReplyOut(BaseModel):
    id: int
    conversation_id: int
    account_email: str
    to_email: str
    subject: str
    body: str
    body_hash: str
    edited: bool
    auto_sent: bool = False
    auto_note: list[str] = []
    status: str
    error: str | None
    decided_by_name: str | None
    provider_message_id: str | None
    created_at: UtcDateTime
    decided_at: UtcDateTime | None
    sent_at: UtcDateTime | None
    can_send: bool
    analysis: AnalysisOut


class ReplyEdit(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class ReplyApprove(BaseModel):
    # The fingerprint of the exact text the person read. Approval of any other text is refused.
    body_hash: str = Field(min_length=64, max_length=64)


class AnalyseRecentIn(BaseModel):
    per_mailbox: int = Field(100, ge=1, le=500)


class AnalyseRecentOut(BaseModel):
    looked_at: int
    queued: int
    automated: int
    already_done: int


class WriteIn(BaseModel):
    instruction: str = Field(min_length=2, max_length=1000)
    current: str = Field("", max_length=20000)
    # The conversation being answered, if any: its messages are given to the AI as context.
    conversation_id: int | None = None


class WriteOut(BaseModel):
    subject: str
    body: str


class AiStatus(BaseModel):
    configured: bool
    enabled: bool
    paused: bool
    waiting_for_approval: int
    waiting_for_analysis: int
    working_now: int = 0
    analysed_today: int
    failed_today: int
    sent_today: int
    auto_sent_today: int = 0
