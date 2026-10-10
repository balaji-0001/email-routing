from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.services import auth
from app.services.accounts import MANAGERS
from app.services.auth import Client, Identity


def get_client(request: Request) -> Client:
    return Client(ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"))


def optional_identity(request: Request, db: Session = Depends(get_db)) -> Identity | None:
    return auth.resolve(db, request.cookies.get(get_settings().session_cookie_name))


def current_identity(identity: Identity | None = Depends(optional_identity)) -> Identity:
    """Any signed-in person."""
    if identity is None:
        raise AppError(401, "NOT_SIGNED_IN", "Sign in to continue.")
    return identity


def workspace_identity(identity: Identity = Depends(current_identity)) -> Identity:
    """A signed-in person who is working in a workspace."""
    if identity.workspace is None:
        raise AppError(409, "WORKSPACE_REQUIRED", "Set up your workspace first.")
    return identity


def workspace_manager(identity: Identity = Depends(workspace_identity)) -> Identity:
    """An owner or admin of the current workspace."""
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only workspace owners and admins can do this.")
    return identity
