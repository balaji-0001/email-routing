import json

from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.models.email import EmailAccount, Folder
from app.providers.base import EmailProvider
from app.providers.imap_smtp import ImapSmtpProvider
from app.repositories import email as email_repo
from app.schemas.email import ConnectEmailAccountIn
from app.services import audit
from app.services.accounts import MANAGERS
from app.services.auth import Client, Identity


def get_provider_for_account(account: EmailAccount) -> EmailProvider:
    if account.auth_type == "oauth":
        # Imported here because the Google service itself builds on this module's repository and audit imports.
        from app.services import google_oauth

        return google_oauth.provider_for(account)

    creds = json.loads(security.decrypt_secret(account.credentials_encrypted))
    return ImapSmtpProvider(
        incoming_host=account.incoming_host,
        incoming_port=account.incoming_port,
        incoming_security=account.incoming_security,
        incoming_username=account.incoming_username,
        incoming_password=creds.get("incoming_password", ""),
        outgoing_host=account.outgoing_host,
        outgoing_port=account.outgoing_port,
        outgoing_security=account.outgoing_security,
        outgoing_username=account.outgoing_username,
        outgoing_password=creds.get("outgoing_password", ""),
        from_address=account.email_address,
        from_name=account.display_name,
    )


def connect_account(db: Session, identity: Identity, data: ConnectEmailAccountIn, client: Client, verify_live: bool = True) -> EmailAccount:
    workspace = identity.workspace
    assert workspace is not None
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only workspace owners and admins can connect email accounts.")

    email_clean = data.email_address.strip().lower()
    existing = email_repo.find_by_email(db, workspace.id, email_clean)
    if existing:
        raise AppError(409, "ACCOUNT_EXISTS", f"Account {email_clean} is already connected to this workspace.")

    provider = ImapSmtpProvider(
        incoming_host=data.incoming_host,
        incoming_port=data.incoming_port,
        incoming_security=data.incoming_security,
        incoming_username=data.incoming_username,
        incoming_password=data.incoming_password,
        outgoing_host=data.outgoing_host,
        outgoing_port=data.outgoing_port,
        outgoing_security=data.outgoing_security,
        outgoing_username=data.outgoing_username,
        outgoing_password=data.outgoing_password,
        from_address=email_clean,
        from_name=data.display_name,
    )

    if verify_live:
        # Each attempt opens connections from this server, so it is limited per person.
        attempts = f"connect-mailbox:{identity.user.id}"
        limiter.check(attempts, limit=10, window_seconds=600)
        limiter.record(attempts, window_seconds=600)
        ok, err = provider.test_connection()
        if not ok:
            raise AppError(400, "CONNECTION_FAILED", f"Could not connect. {err}")

    credentials_json = json.dumps({
        "incoming_password": data.incoming_password,
        "outgoing_password": data.outgoing_password,
    })
    credentials_encrypted = security.encrypt_secret(credentials_json)

    account = email_repo.add_account(
        db,
        EmailAccount(
            workspace_id=workspace.id,
            provider=data.provider,
            email_address=email_clean,
            display_name=data.display_name or email_clean.split("@")[0],
            incoming_host=data.incoming_host,
            incoming_port=data.incoming_port,
            incoming_security=data.incoming_security,
            incoming_username=data.incoming_username,
            outgoing_host=data.outgoing_host,
            outgoing_port=data.outgoing_port,
            outgoing_security=data.outgoing_security,
            outgoing_username=data.outgoing_username,
            credentials_encrypted=credentials_encrypted,
            status="connected",
        ),
    )

    # Initial folders creation
    folders_to_create = [
        {"name": "INBOX", "system_folder": "inbox"},
        {"name": "Sent", "system_folder": "sent"},
        {"name": "Trash", "system_folder": "trash"},
        {"name": "Drafts", "system_folder": "drafts"},
    ]
    if verify_live:
        try:
            live_folders = provider.list_folders()
            if live_folders:
                folders_to_create = live_folders
        except Exception:
            pass

    for f in folders_to_create:
        if not email_repo.get_folder_by_name(db, account.id, f["name"]):
            email_repo.add_folder(
                db,
                Folder(
                    workspace_id=workspace.id,
                    email_account_id=account.id,
                    name=f["name"],
                    system_folder=f.get("system_folder", "custom"),
                ),
            )

    audit.record(
        db,
        action="email_account.connected",
        summary=f"Connected email account {email_clean}",
        actor=identity.user,
        workspace_id=workspace.id,
        ip=client.ip,
    )
    db.commit()
    return account


def list_accounts(db: Session, identity: Identity) -> list[tuple[EmailAccount, int]]:
    assert identity.workspace is not None
    from app.services import mailbox_access

    allowed = mailbox_access.allowed_account_ids(db, identity)
    rows = email_repo.list_accounts(db, identity.workspace.id)
    return rows if allowed is None else [(account, count) for account, count in rows if account.id in allowed]


def disconnect_account(db: Session, identity: Identity, account_id: int, client: Client) -> None:
    workspace = identity.workspace
    assert workspace is not None
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only workspace owners and admins can disconnect email accounts.")

    account = email_repo.get_account(db, account_id, workspace.id)
    if not account:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Email account not found.")

    addr = account.email_address
    if account.auth_type == "oauth":
        from app.services import google_oauth

        google_oauth.revoke(account)
    email_repo.delete_account(db, account)
    audit.record(
        db,
        action="email_account.disconnected",
        summary=f"Disconnected email account {addr}",
        actor=identity.user,
        workspace_id=workspace.id,
        ip=client.ip,
    )
    db.commit()

