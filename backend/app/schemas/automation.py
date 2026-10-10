from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import UtcDateTime

Priority = Literal["low", "normal", "high", "urgent"]
Text = Annotated[str, Field(max_length=200)]


class Conditions(BaseModel):
    """All that are filled in must match. An empty set matches every new email."""

    account_id: int | None = None
    sender: Text = ""
    recipient: Text = ""
    subject: Text = ""
    body: Text = ""
    has_attachments: bool | None = None
    # What the AI made of the email. A rule that asks this runs once the email has been analysed.
    ai_priority: Literal["low", "medium", "high"] | None = None


class AddLabel(BaseModel):
    type: Literal["add_label"]
    label_id: int


class SetPriority(BaseModel):
    type: Literal["set_priority"]
    value: Priority


class SetStatus(BaseModel):
    type: Literal["set_status"]
    value: Literal["open", "pending", "closed"]


class Assign(BaseModel):
    type: Literal["assign"]
    user_id: int


class AssignInTurn(BaseModel):
    type: Literal["assign_in_turn"]
    user_ids: list[int] = Field(min_length=1, max_length=50)


class Flag(BaseModel):
    type: Literal["flag"]


class Archive(BaseModel):
    type: Literal["archive"]


class Notify(BaseModel):
    type: Literal["notify"]
    user_id: int


Action = Annotated[AddLabel | SetPriority | SetStatus | Assign | AssignInTurn | Flag | Archive | Notify, Field(discriminator="type")]


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    conditions: Conditions = Conditions()
    # 'new_mail': when an email arrives. 'waiting': when an email has had no reply from us for `wait_hours`.
    trigger: Literal["new_mail", "waiting"] = "new_mail"
    wait_hours: int | None = Field(None, ge=1, le=24 * 60)
    actions: list[Action] = Field(min_length=1, max_length=10)


    @model_validator(mode="after")
    def _waiting_needs_a_time(self) -> "RuleIn":
        if self.trigger == "waiting" and not self.wait_hours:
            raise ValueError("Say how long the email should wait.")
        return self


class RuleOut(RuleIn):
    id: int
    position: int
    run_count: int
    failed_count: int = 0
    last_run_at: UtcDateTime | None
    created_by_name: str | None = None
    # The rule in one plain sentence, for lists and the dashboard.
    summary: str


class RuleToggle(BaseModel):
    enabled: bool


class ReorderIn(BaseModel):
    rule_ids: list[int] = Field(max_length=1000)


class RunOut(BaseModel):
    id: int
    rule_id: int
    rule_name: str
    conversation_id: int
    subject: str
    status: str
    attempts: int
    done: list[str]
    error: str | None
    created_at: UtcDateTime


class TestMatch(BaseModel):
    conversation_id: int
    subject: str
    sender: str
    sent_at: UtcDateTime


class TestOut(BaseModel):
    checked: int
    matches: list[TestMatch]


class MailboxSwitch(BaseModel):
    account_id: int
    email_address: str
    enabled: bool


class AutomationSettingsOut(BaseModel):
    enabled: bool
    mailboxes: list[MailboxSwitch]


class AutomationSettingsIn(BaseModel):
    enabled: bool | None = None
    # Mailbox id to on or off.
    mailboxes: dict[int, bool] = {}


class RunRecentIn(BaseModel):
    per_mailbox: int = Field(100, ge=1, le=500)


class RunRecentOut(BaseModel):
    checked: int
    runs: int


class AutomationSummary(BaseModel):
    enabled: bool
    rules_total: int
    rules_on: int
    runs_today: int
    failed_today: int
    rules: list[RuleOut]
    recent: list[RunOut]
