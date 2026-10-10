from typing import Literal

from typing import Annotated

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import UtcDateTime


# A mail server's name: letters, digits, dots and hyphens. No addresses with schemes, paths or spaces.
HostName = Annotated[str, Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")]


class ConnectEmailAccountIn(BaseModel):
    provider: Literal["imap", "gmail", "microsoft"] = "imap"
    email_address: EmailStr
    display_name: str = Field("", max_length=120)
    incoming_host: HostName
    # Only the ports mail really uses: the form cannot be turned into a scanner for other services.
    incoming_port: Literal[993, 143] = 993
    # Always encrypted: "none" would send the mailbox password in the clear.
    incoming_security: Literal["ssl", "starttls"] = "ssl"
    incoming_username: str = Field(min_length=1, max_length=320)
    incoming_password: str = Field(min_length=1, max_length=1024)
    outgoing_host: HostName
    outgoing_port: Literal[465, 587, 25] = 587
    outgoing_security: Literal["ssl", "starttls"] = "starttls"
    outgoing_username: str = Field(max_length=320)
    outgoing_password: str = Field(max_length=1024)


class EmailAccountOut(BaseModel):
    id: int
    provider: str
    auth_type: str = "basic"  # "basic" (mailbox password) or "oauth" (signed in at the provider)
    email_address: str
    display_name: str
    status: str  # 'connected', 'syncing', 'error', 'needs_reconnect'
    incoming_host: str
    outgoing_host: str
    last_sync_at: UtcDateTime | None
    last_error: str | None
    message_count: int = 0
    # Older mail being brought in: 'pending', 'running' or 'done', and how many messages the inbox holds.
    import_state: str = "done"
    import_total: int | None = None
    # 'everyone' or 'restricted', and what the person asking may do: 'send' or 'read'.
    access_mode: str = "everyone"
    my_permission: str = "send"
    created_at: UtcDateTime


class SyncResultOut(BaseModel):
    account_id: int
    synced_messages: int
    status: str
    error: str | None = None



class EmailProvidersOut(BaseModel):
    # False until GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set, so the app can say so up front.
    google_oauth: bool
    google_redirect_uri: str


class OAuthStartOut(BaseModel):
    authorization_url: str


class AccessMemberOut(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    # Owners and admins always have full access.
    always: bool
    permission: str | None


class AccessRoleOut(BaseModel):
    role: str
    name: str
    description: str
    # Owners and admins always have full access.
    always: bool
    permission: str | None
    # How many people in the workspace have this role.
    people: int


class MailboxAccessOut(BaseModel):
    access_mode: str
    roles: list[AccessRoleOut]
    members: list[AccessMemberOut]


class AccessMemberIn(BaseModel):
    user_id: int
    permission: Literal["read", "send"]


class AccessRoleIn(BaseModel):
    role: Literal["owner", "admin", "manager", "agent", "viewer"]
    permission: Literal["read", "send"]


class MailboxAccessIn(BaseModel):
    access_mode: Literal["everyone", "restricted"]
    roles: list[AccessRoleIn] = []
    members: list[AccessMemberIn] = []
