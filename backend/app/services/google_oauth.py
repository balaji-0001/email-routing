"""Connecting a Gmail mailbox by signing in at Google, and keeping its tokens fresh."""

import base64
import hashlib
import json
import logging
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode

import httpx2
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.database import utcnow
from app.core.errors import AppError
from app.models.email import EmailAccount, EmailOAuthState, Folder
from app.providers import gmail
from app.providers.gmail import GmailApiError, GmailProvider, ReconnectRequired
from app.repositories import email as email_repo
from app.services import audit
from app.services.accounts import MANAGERS
from app.services.auth import Client, Identity

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Read and change mail, and send it. Nothing beyond the mailbox.
SCOPES = ("https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send")

STATE_MINUTES = 10
GMAIL_HOST = "gmail.googleapis.com"


class ConnectFailed(Exception):
    """Why a return from Google did not end in a connected mailbox. `reason` is shown by the web app."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _require_configured() -> None:
    if not get_settings().google_oauth_enabled:
        raise AppError(503, "GOOGLE_NOT_CONFIGURED", "Connecting with Google isn't set up on this server yet.")


def start(db: Session, identity: Identity) -> str:
    """Record a sign-in attempt and return the Google address to send the browser to."""
    _require_configured()
    settings = get_settings()
    assert identity.workspace is not None

    now = utcnow()
    email_repo.delete_expired_oauth_states(db, now)

    state = security.new_token()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    email_repo.add_oauth_state(
        db,
        EmailOAuthState(
            state_hash=security.hash_token(state),
            provider="gmail",
            session_id=identity.session.id,
            workspace_id=identity.workspace.id,
            user_id=identity.user.id,
            code_verifier_encrypted=security.encrypt_secret(verifier),
            expires_at=now + timedelta(minutes=STATE_MINUTES),
        ),
    )
    db.commit()

    return AUTH_URL + "?" + urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # A refresh token is only issued with offline access, and only reliably when consent is shown.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    })


def _token_request(data: dict[str, str]) -> httpx2.Response:
    settings = get_settings()
    with gmail.http_client() as client:
        return client.post(TOKEN_URL, data={"client_id": settings.google_client_id or "", "client_secret": settings.google_client_secret or "", **data})


def _pack(*, refresh_token: str, access_token: str, expires_in: int, scope: str) -> str:
    return security.encrypt_secret(json.dumps({
        "refresh_token": refresh_token,
        "access_token": access_token,
        "expires_at": int(time.time()) + int(expires_in),
        "scope": scope,
    }))


def _unpack(account: EmailAccount) -> dict:
    return json.loads(security.decrypt_secret(account.credentials_encrypted))


def complete(db: Session, identity: Identity | None, *, code: str | None, state: str | None, error: str | None, client: Client) -> EmailAccount:
    """Finish a sign-in attempt after Google sends the browser back. Raises ConnectFailed with the reason."""
    attempt = email_repo.take_oauth_state(db, security.hash_token(state)) if state else None
    db.commit()  # the attempt is spent whatever happens next

    if attempt is None or attempt.expires_at < utcnow():
        raise ConnectFailed("expired")
    if identity is None:
        raise ConnectFailed("signed_out")
    workspace = identity.workspace
    if workspace is None or attempt.session_id != identity.session.id or attempt.user_id != identity.user.id or attempt.workspace_id != workspace.id:
        raise ConnectFailed("expired")
    if identity.role not in MANAGERS:
        raise ConnectFailed("forbidden")
    if error or not code:
        raise ConnectFailed("denied" if error == "access_denied" else "failed")
    if not get_settings().google_oauth_enabled:
        raise ConnectFailed("not_configured")

    try:
        response = _token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_settings().google_redirect_uri,
            "code_verifier": security.decrypt_secret(attempt.code_verifier_encrypted),
        })
    except httpx2.HTTPError as exc:
        raise ConnectFailed("failed") from exc
    if response.status_code != 200:
        logger.warning("Google refused the code exchange with status %s", response.status_code)
        raise ConnectFailed("failed")
    tokens = response.json()
    access_token = tokens.get("access_token")
    granted = set(str(tokens.get("scope", "")).split())
    if not access_token:
        raise ConnectFailed("failed")
    # Google lets people untick permissions on the consent screen.
    if not set(SCOPES) <= granted:
        raise ConnectFailed("missing_permission")

    provider = GmailProvider(token_source=lambda _force: access_token, from_address="")
    try:
        with gmail.http_client() as http:
            address = str(provider._call(http, "GET", "/profile").json().get("emailAddress", "")).strip().lower()
    except (GmailApiError, ReconnectRequired, httpx2.HTTPError) as exc:
        raise ConnectFailed("failed") from exc
    if not address:
        raise ConnectFailed("failed")

    account = email_repo.find_by_email(db, workspace.id, address)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token and account is not None and account.auth_type == "oauth":
        refresh_token = _unpack(account).get("refresh_token")
    if not refresh_token:
        raise ConnectFailed("failed")

    credentials = _pack(refresh_token=refresh_token, access_token=access_token, expires_in=tokens.get("expires_in", 3600), scope=" ".join(sorted(granted)))
    reconnected = account is not None
    if account is None:
        account = email_repo.add_account(
            db,
            EmailAccount(
                workspace_id=workspace.id,
                provider="gmail",
                email_address=address,
                display_name=address.split("@")[0],
                incoming_host=GMAIL_HOST,
                incoming_port=443,
                incoming_security="ssl",
                incoming_username=address,
                outgoing_host=GMAIL_HOST,
                outgoing_port=443,
                outgoing_security="ssl",
                outgoing_username=address,
                credentials_encrypted=credentials,
                auth_type="oauth",
                status="connected",
            ),
        )
    else:
        # The same address connected before, by password or by an earlier sign-in: this sign-in replaces it.
        account.provider = "gmail"
        account.auth_type = "oauth"
        account.incoming_host = account.outgoing_host = GMAIL_HOST
        account.incoming_port = account.outgoing_port = 443
        account.incoming_security = account.outgoing_security = "ssl"
        account.credentials_encrypted = credentials
        account.sync_cursor = None
        account.status = "connected"
        account.last_error = None

    try:
        folders = GmailProvider(token_source=lambda _force: access_token, from_address=address).list_folders()
    except (GmailApiError, ReconnectRequired, httpx2.HTTPError):
        folders = [{"name": "INBOX", "system_folder": "inbox"}]
    for folder in folders:
        if not email_repo.get_folder_by_name(db, account.id, folder["name"]):
            email_repo.add_folder(db, Folder(workspace_id=workspace.id, email_account_id=account.id, name=folder["name"], system_folder=folder["system_folder"]))

    audit.record(
        db,
        action="email_account.reconnected" if reconnected else "email_account.connected",
        summary=f"{'Reconnected' if reconnected else 'Connected'} Gmail account {address} with Google sign-in",
        actor=identity.user,
        workspace_id=workspace.id,
        ip=client.ip,
    )
    db.commit()
    return account


def access_token(account: EmailAccount, force: bool = False) -> str:
    """A valid access token for the account, refreshed when it is about to expire.

    A new token is written onto the account; the caller's transaction saves it.
    """
    credentials = _unpack(account)
    if not force and credentials.get("access_token") and int(credentials.get("expires_at", 0)) - 60 > time.time():
        return credentials["access_token"]

    _require_configured()
    try:
        response = _token_request({"grant_type": "refresh_token", "refresh_token": credentials.get("refresh_token", "")})
    except httpx2.HTTPError as exc:
        raise GmailApiError("Could not reach Google to renew the connection.") from exc
    if response.status_code in (400, 401):
        # Revoked, expired (7 days while the Google app is in "Testing") or the password changed.
        raise ReconnectRequired("Google no longer accepts this connection.")
    if response.status_code != 200:
        raise GmailApiError(f"Google could not renew the connection (status {response.status_code}).")

    tokens = response.json()
    account.credentials_encrypted = _pack(
        refresh_token=tokens.get("refresh_token") or credentials["refresh_token"],
        access_token=tokens["access_token"],
        expires_in=tokens.get("expires_in", 3600),
        scope=tokens.get("scope") or credentials.get("scope", ""),
    )
    return tokens["access_token"]


def provider_for(account: EmailAccount) -> GmailProvider:
    return GmailProvider(
        token_source=lambda force: access_token(account, force),
        from_address=account.email_address,
        from_name=account.display_name,
        cursor=account.sync_cursor,
    )


def revoke(account: EmailAccount) -> None:
    """Tell Google to forget the connection. Best effort: disconnecting must not fail because of it."""
    try:
        token = _unpack(account).get("refresh_token")
        if token:
            with gmail.http_client() as client:
                client.post(REVOKE_URL, data={"token": token})
    except Exception:  # noqa: BLE001 - nothing useful can be done about a failed revoke
        logger.warning("Could not revoke the Google connection for account %s", account.id)
