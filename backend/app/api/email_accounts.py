from typing import Any

from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_client, optional_identity, workspace_identity, workspace_manager
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.schemas.common import Envelope
from app.models.email import EmailAccount
from app.schemas.email import (
    AccessMemberOut,
    AccessRoleOut,
    ConnectEmailAccountIn,
    EmailAccountOut,
    EmailProvidersOut,
    MailboxAccessIn,
    MailboxAccessOut,
    OAuthStartOut,
    SyncResultOut,
)
from app.services import email_accounts, email_sync, google_oauth, mailbox_access
from app.services.auth import Client, Identity

router = APIRouter(prefix="/email-accounts", tags=["email-accounts"])


def _account_out(account: EmailAccount, message_count: int = 0, my_permission: str = "send") -> EmailAccountOut:
    return EmailAccountOut(
        id=account.id,
        provider=account.provider,
        auth_type=account.auth_type,
        email_address=account.email_address,
        display_name=account.display_name,
        status=account.status,
        incoming_host=account.incoming_host,
        outgoing_host=account.outgoing_host,
        last_sync_at=account.last_sync_at,
        last_error=account.last_error,
        message_count=message_count,
        import_state=account.import_state if account.auth_type == "oauth" else "done",
        import_total=account.import_total,
        access_mode=account.access_mode,
        my_permission=my_permission,
        created_at=account.created_at,
    )


@router.get("/providers", response_model=Envelope[EmailProvidersOut])
def providers(identity: Identity = Depends(workspace_identity)) -> Envelope[EmailProvidersOut]:
    settings = get_settings()
    return Envelope(data=EmailProvidersOut(google_oauth=settings.google_oauth_enabled, google_redirect_uri=settings.google_redirect_uri))


@router.post("/oauth/google/start", response_model=Envelope[OAuthStartOut])
def google_start(
    identity: Identity = Depends(workspace_manager),
    db: Session = Depends(get_db),
) -> Envelope[OAuthStartOut]:
    return Envelope(data=OAuthStartOut(authorization_url=google_oauth.start(db, identity)))


@router.get("/oauth/google/callback", include_in_schema=False)
def google_callback(
    background_tasks: BackgroundTasks,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    identity: Identity | None = Depends(optional_identity),
    client: Client = Depends(get_client),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Where Google sends the browser back. Always ends on the Email accounts page, which shows the outcome."""
    target = f"{get_settings().app_url.rstrip('/')}/accounts"
    try:
        account = google_oauth.complete(db, identity, code=code, state=state, error=error, client=client)
    except google_oauth.ConnectFailed as failure:
        return RedirectResponse(f"{target}?{urlencode({'gmail_error': failure.reason})}", status_code=303)
    background_tasks.add_task(email_sync.sync_account_task, account.id, account.workspace_id)
    return RedirectResponse(f"{target}?{urlencode({'gmail_connected': account.email_address})}", status_code=303)


@router.post("/connect", response_model=Envelope[EmailAccountOut], status_code=201)
def connect_account(
    body: ConnectEmailAccountIn,
    background_tasks: BackgroundTasks,
    identity: Identity = Depends(workspace_manager),
    client: Client = Depends(get_client),
    db: Session = Depends(get_db),
) -> Envelope[EmailAccountOut]:
    account = email_accounts.connect_account(db, identity, body, client, verify_live=True)
    assert identity.workspace is not None
    background_tasks.add_task(email_sync.sync_account_task, account.id, identity.workspace.id)
    return Envelope(data=_account_out(account))


@router.get("", response_model=Envelope[list[EmailAccountOut]])
def list_accounts(
    identity: Identity = Depends(workspace_identity),
    db: Session = Depends(get_db),
) -> Envelope[list[EmailAccountOut]]:
    rows = email_accounts.list_accounts(db, identity)
    return Envelope(data=[_account_out(acc, cnt, mailbox_access.permission(db, identity, acc) or "read") for acc, cnt in rows])


def _may_sync(identity: Identity, kind: str, limit: int) -> None:
    """Starting a sync talks to the mail provider, so it is for people who work the mail, a few times a minute."""
    if identity.role == "viewer":
        raise AppError(403, "FORBIDDEN", "Viewers cannot start a sync. New mail is fetched every minute anyway.")
    key = f"{kind}:{identity.user.id}"
    limiter.check(key, limit=limit, window_seconds=60)
    limiter.record(key, window_seconds=60)


@router.post("/sync-all", response_model=Envelope[dict[str, Any]])
def sync_all(
    identity: Identity = Depends(workspace_identity),
    db: Session = Depends(get_db),
) -> Envelope[dict[str, Any]]:
    assert identity.workspace is not None
    _may_sync(identity, "sync-all", limit=4)
    rows = email_accounts.list_accounts(db, identity)
    total_synced = 0
    errors = []
    for acc, _ in rows:
        synced, err = email_sync.sync_account(db, acc.id, identity.workspace.id)
        total_synced += synced
        if err:
            errors.append(f"{acc.email_address}: {err}")
    return Envelope(data={"synced_messages": total_synced, "errors": errors})


@router.post("/{account_id}/sync", response_model=Envelope[SyncResultOut])
def sync_account(
    account_id: int,
    identity: Identity = Depends(workspace_identity),
    db: Session = Depends(get_db),
) -> Envelope[SyncResultOut]:
    assert identity.workspace is not None
    _may_sync(identity, "sync", limit=12)
    allowed = mailbox_access.allowed_account_ids(db, identity)
    if allowed is not None and account_id not in allowed:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Email account not found.")
    synced, error = email_sync.sync_account(db, account_id, identity.workspace.id)
    return Envelope(
        data=SyncResultOut(
            account_id=account_id,
            synced_messages=synced,
            status=_status_after_sync(db, account_id, identity.workspace.id, error),
            error=error,
        )
    )


def _access_out(db: Session, identity: Identity, account_id: int) -> MailboxAccessOut:
    account, roles, people = mailbox_access.describe(db, identity, account_id)
    return MailboxAccessOut(
        access_mode=account.access_mode,
        roles=[AccessRoleOut(**role) for role in roles],
        members=[AccessMemberOut(**person) for person in people],
    )


@router.get("/{account_id}/access", response_model=Envelope[MailboxAccessOut])
def get_access(account_id: int, identity: Identity = Depends(workspace_manager), db: Session = Depends(get_db)) -> Envelope[MailboxAccessOut]:
    return Envelope(data=_access_out(db, identity, account_id))


@router.put("/{account_id}/access", response_model=Envelope[MailboxAccessOut])
def set_access(
    account_id: int,
    body: MailboxAccessIn,
    identity: Identity = Depends(workspace_manager),
    client: Client = Depends(get_client),
    db: Session = Depends(get_db),
) -> Envelope[MailboxAccessOut]:
    mailbox_access.update(db, identity, account_id, body.access_mode, [(m.user_id, m.permission) for m in body.members], [(r.role, r.permission) for r in body.roles], client)
    return Envelope(data=_access_out(db, identity, account_id))


@router.delete("/{account_id}", status_code=204)
def disconnect_account(
    account_id: int,
    identity: Identity = Depends(workspace_manager),
    client: Client = Depends(get_client),
    db: Session = Depends(get_db),
) -> None:
    email_accounts.disconnect_account(db, identity, account_id, client)



def _status_after_sync(db: Session, account_id: int, workspace_id: int, error: str | None) -> str:
    if not error:
        return "connected"
    account = email_accounts.email_repo.get_account(db, account_id, workspace_id)
    return account.status if account else "error"
