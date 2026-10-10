import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import utcnow
from app.core.errors import AppError
from app.core.rate_limit import limiter
from app.core.security import burn_password_check, hash_password, hash_token, needs_rehash, new_token, verify_password
from app.models import AuthSession, PasswordResetToken, User, Workspace
from app.repositories import password_resets, sessions, users, workspaces
from app.services import audit, email

logger = logging.getLogger("app.auth")

LOGIN_ATTEMPTS, LOGIN_WINDOW = 8, 15 * 60
SIGNUP_ATTEMPTS, SIGNUP_WINDOW = 20, 60 * 60
RESET_ATTEMPTS, RESET_WINDOW = 5, 60 * 60
# How stale "last used" may get before it is written again, to avoid a write on every request.
TOUCH_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True)
class Client:
    """What is known about the browser making the request."""

    ip: str | None
    user_agent: str | None


@dataclass
class Identity:
    """A signed-in person, the session they came in on, and where they are working."""

    user: User
    session: AuthSession
    workspace: Workspace | None
    role: str | None


def normalize_email(email_address: str) -> str:
    return email_address.strip().lower()


def split_name(name: str) -> tuple[str, str]:
    first, _, last = " ".join(name.split()).partition(" ")
    return first, last


def _start_session(db: Session, user: User, *, remember: bool, client: Client, workspace_id: int | None) -> tuple[AuthSession, str]:
    settings = get_settings()
    token = new_token()
    now = utcnow()
    lifetime = timedelta(days=settings.remember_days) if remember else timedelta(hours=settings.session_hours)
    session = sessions.add(
        db,
        AuthSession(
            user_id=user.id,
            workspace_id=workspace_id,
            token_hash=hash_token(token),
            remember=remember,
            user_agent=(client.user_agent or "")[:255] or None,
            ip_address=client.ip,
            created_at=now,
            last_used_at=now,
            expires_at=now + lifetime,
        ),
    )
    return session, token


def register(db: Session, *, email_address: str, password: str, name: str, timezone: str | None, client: Client) -> tuple[Identity, str]:
    limit_key = f"signup:{client.ip}"
    limiter.check(limit_key, limit=SIGNUP_ATTEMPTS, window_seconds=SIGNUP_WINDOW)
    limiter.record(limit_key, window_seconds=SIGNUP_WINDOW)

    address = normalize_email(email_address)
    taken = AppError(409, "EMAIL_TAKEN", "An account with this email already exists. Sign in instead.")
    if users.get_by_email(db, address):
        raise taken

    first_name, last_name = split_name(name)
    try:
        user = users.add(db, User(email=address, password_hash=hash_password(password), first_name=first_name, last_name=last_name, timezone=timezone))
    except IntegrityError:
        # Two sign-ups for the same address raced; the unique index decided.
        db.rollback()
        raise taken from None

    session, token = _start_session(db, user, remember=False, client=client, workspace_id=None)
    user.last_login_at = session.created_at
    audit.record(db, action="account.created", summary="Created an account", actor=user, workspace_id=None, ip=client.ip)
    db.commit()
    return Identity(user=user, session=session, workspace=None, role=None), token


def login(db: Session, *, email_address: str, password: str, remember: bool, client: Client) -> tuple[Identity, str]:
    address = normalize_email(email_address)
    limit_key = f"login:{client.ip}:{address}"
    # Three limits: this address from this place, this address from anywhere (many machines guessing
    # one password), and this place against any address (one machine trying many accounts).
    by_address, by_place = f"login-address:{address}", f"login-place:{client.ip}"
    limiter.check(limit_key, limit=LOGIN_ATTEMPTS, window_seconds=LOGIN_WINDOW)
    limiter.check(by_address, limit=LOGIN_ATTEMPTS * 5, window_seconds=LOGIN_WINDOW)
    limiter.check(by_place, limit=LOGIN_ATTEMPTS * 10, window_seconds=LOGIN_WINDOW)

    user = users.get_by_email(db, address)
    if user is None:
        burn_password_check(password)
        correct = False
    else:
        correct = verify_password(user.password_hash, password)
    if not correct or user is None:
        for key in (limit_key, by_address, by_place):
            limiter.record(key, window_seconds=LOGIN_WINDOW)
        raise AppError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
    limiter.clear(limit_key)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    member = workspaces.first_membership(db, user.id)
    workspace = workspaces.get(db, member.workspace_id) if member else None
    session, token = _start_session(db, user, remember=remember, client=client, workspace_id=workspace.id if workspace else None)
    user.last_login_at = session.created_at
    audit.record(db, action="session.started", summary="Signed in", actor=user, workspace_id=session.workspace_id, ip=client.ip)
    db.commit()
    return Identity(user=user, session=session, workspace=workspace, role=member.role if member else None), token


def resolve(db: Session, token: str | None) -> Identity | None:
    """Turn a session cookie into the person behind it, or nothing if it is no longer good."""
    if not token:
        return None
    session = sessions.get_by_token_hash(db, hash_token(token))
    now = utcnow()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None
    user = users.get(db, session.user_id)
    if user is None:
        return None

    if now - session.last_used_at > TOUCH_INTERVAL:
        session.last_used_at = now
        db.commit()

    workspace, role = None, None
    if session.workspace_id is not None:
        member = workspaces.membership(db, session.workspace_id, user.id)
        if member is not None:
            workspace, role = workspaces.get(db, session.workspace_id), member.role
    return Identity(user=user, session=session, workspace=workspace, role=role)


def logout(db: Session, identity: Identity, client: Client) -> None:
    identity.session.revoked_at = utcnow()
    audit.record(db, action="session.ended", summary="Signed out", actor=identity.user, workspace_id=identity.session.workspace_id, ip=client.ip)
    db.commit()


def change_password(db: Session, identity: Identity, *, current_password: str, new_password: str, client: Client) -> None:
    user = identity.user
    limit_key = f"password:{user.id}"
    limiter.check(limit_key, limit=LOGIN_ATTEMPTS, window_seconds=LOGIN_WINDOW)
    if not verify_password(user.password_hash, current_password):
        limiter.record(limit_key, window_seconds=LOGIN_WINDOW)
        raise AppError(400, "WRONG_PASSWORD", "Your current password is incorrect.")
    limiter.clear(limit_key)
    if new_password == current_password:
        raise AppError(400, "PASSWORD_UNCHANGED", "Choose a password that is different from your current one.")

    now = utcnow()
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    # Whoever else was signed in with the old password is signed out; this browser stays.
    sessions.revoke_all(db, user.id, now, except_id=identity.session.id)
    password_resets.invalidate_for_user(db, user.id, now)
    audit.record(db, action="password.changed", summary="Changed the account password", actor=user, workspace_id=identity.session.workspace_id, ip=client.ip)
    db.commit()


def request_password_reset(db: Session, *, email_address: str, client: Client) -> None:
    """Email a reset link if the address has an account. Callers get the same answer either way."""
    settings = get_settings()
    if not settings.email_enabled:
        raise AppError(503, "EMAIL_NOT_CONFIGURED", "Password reset by email is not set up on this server yet.")

    address = normalize_email(email_address)
    limit_key = f"reset:{client.ip}:{address}"
    limiter.check(limit_key, limit=RESET_ATTEMPTS, window_seconds=RESET_WINDOW)
    limiter.record(limit_key, window_seconds=RESET_WINDOW)

    user = users.get_by_email(db, address)
    if user is None:
        return

    now = utcnow()
    token = new_token()
    password_resets.invalidate_for_user(db, user.id, now)
    password_resets.add(
        db,
        PasswordResetToken(user_id=user.id, token_hash=hash_token(token), created_at=now, expires_at=now + timedelta(minutes=settings.password_reset_minutes)),
    )
    member = workspaces.first_membership(db, user.id)
    audit.record(db, action="password.reset_requested", summary="Asked for a password reset link", actor=user, workspace_id=member.workspace_id if member else None, ip=client.ip)
    db.commit()

    link = f"{settings.app_url.rstrip('/')}/reset-password?token={token}"
    body = (
        f"Hi {user.first_name},\n\n"
        "Someone asked to reset the password for your account. Open this link to choose a new one:\n\n"
        f"{link}\n\n"
        f"The link works once and expires in {settings.password_reset_minutes} minutes. "
        "If you did not ask for it, you can ignore this email and your password stays the same.\n"
    )
    try:
        email.send_email(user.email, "Reset your password", body)
    except Exception:
        # Not reported to the caller: that would reveal which addresses have accounts.
        logger.exception("Could not send the password reset email to user %s", user.id)


def reset_password(db: Session, *, token: str, new_password: str, client: Client) -> None:
    now = utcnow()
    row = password_resets.get_by_token_hash(db, hash_token(token))
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise AppError(400, "RESET_LINK_INVALID", "This reset link is not valid any more. Ask for a new one.")
    user = users.get(db, row.user_id)
    if user is None:
        raise AppError(400, "RESET_LINK_INVALID", "This reset link is not valid any more. Ask for a new one.")

    row.used_at = now
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    # A reset means the old password may be known to someone else: sign out everywhere.
    sessions.revoke_all(db, user.id, now)
    member = workspaces.first_membership(db, user.id)
    audit.record(db, action="password.reset", summary="Reset the account password from an emailed link", actor=user, workspace_id=member.workspace_id if member else None, ip=client.ip)
    db.commit()


def list_sessions(db: Session, identity: Identity) -> list[AuthSession]:
    return sessions.active_for_user(db, identity.user.id, utcnow())


def revoke_other_sessions(db: Session, identity: Identity, client: Client) -> int:
    ended = sessions.revoke_all(db, identity.user.id, utcnow(), except_id=identity.session.id)
    if ended:
        audit.record(db, action="sessions.revoked", summary=f"Signed out of {ended} other session{'s' if ended != 1 else ''}", actor=identity.user, workspace_id=identity.session.workspace_id, ip=client.ip)
    db.commit()
    return ended
