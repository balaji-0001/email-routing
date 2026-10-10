from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints

from app.schemas.common import Schema, Timezone, UtcDateTime

Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class RegisterIn(BaseModel):
    email: EmailStr
    password: Password
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    # The browser's time zone, so times read correctly from the first screen.
    timezone: Timezone | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    remember: bool = False


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: Annotated[str, StringConstraints(min_length=10, max_length=200)]
    password: Password


class ChangePasswordIn(BaseModel):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Password


class ProfileIn(BaseModel):
    first_name: Name
    last_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    timezone: Timezone | None = None


class UserOut(Schema):
    id: int
    email: str
    first_name: str
    last_name: str
    name: str
    timezone: str | None
    created_at: UtcDateTime
    password_changed_at: UtcDateTime


class WorkspaceOut(Schema):
    id: int
    name: str
    domain: str | None
    timezone: str
    allow_invitations: bool
    created_at: UtcDateTime


class MeOut(BaseModel):
    user: UserOut
    workspace: WorkspaceOut | None
    role: str | None
    # False until outgoing email is configured, so the app can say so up front.
    password_reset_available: bool


class SessionOut(BaseModel):
    id: int
    current: bool
    user_agent: str | None
    ip_address: str | None
    created_at: UtcDateTime
    last_used_at: UtcDateTime
    expires_at: UtcDateTime


class OptionsOut(BaseModel):
    password_reset_available: bool
