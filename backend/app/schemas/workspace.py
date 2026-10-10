from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

from app.schemas.common import Timezone, UtcDateTime

WorkspaceName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class WorkspaceCreateIn(BaseModel):
    name: WorkspaceName


class WorkspaceUpdateIn(BaseModel):
    """Only the fields that are sent are changed."""

    name: WorkspaceName | None = None
    domain: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=255)] | None = None
    timezone: Timezone | None = None
    allow_invitations: bool | None = None

    @field_validator("domain")
    @classmethod
    def _blank_domain_clears_it(cls, value: str | None) -> str | None:
        return value or None


class MemberOut(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    role: str
    is_you: bool
    joined_at: UtcDateTime
    last_active_at: UtcDateTime | None


class MemberRoleUpdateIn(BaseModel):
    role: Annotated[str, StringConstraints(strip_whitespace=True)]


class InvitationCreateIn(BaseModel):
    email: EmailStr
    role: Annotated[str, StringConstraints(strip_whitespace=True)] = "agent"


class InvitationOut(BaseModel):
    id: int
    email: str
    role: str
    invited_by_name: str | None
    invite_url: str
    token: str | None = None
    expires_at: UtcDateTime
    created_at: UtcDateTime


class PublicInvitationOut(BaseModel):
    workspace_name: str
    inviter_name: str | None
    email: str
    role: str
    is_expired: bool


class MyWorkspaceOut(BaseModel):
    id: int
    name: str
    role: str
    is_current: bool
    created_at: UtcDateTime


class AuditEventOut(BaseModel):
    id: int
    action: str
    summary: str
    actor_name: str | None
    actor_is_you: bool
    ip_address: str | None
    created_at: UtcDateTime
