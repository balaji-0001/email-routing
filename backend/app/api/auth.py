from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import current_identity, get_client, optional_identity
from app.core.config import get_settings
from app.core.database import get_db, utcnow
from app.schemas.auth import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    MeOut,
    OptionsOut,
    RegisterIn,
    ResetPasswordIn,
    SessionOut,
    UserOut,
    WorkspaceOut,
)
from app.schemas.common import Envelope
from app.schemas.workspace import MyWorkspaceOut, PublicInvitationOut
from app.services import accounts, auth
from app.services.auth import Client, Identity

router = APIRouter(prefix="/auth", tags=["auth"])


def me_payload(identity: Identity) -> MeOut:
    return MeOut(
        user=UserOut.model_validate(identity.user),
        workspace=WorkspaceOut.model_validate(identity.workspace) if identity.workspace else None,
        role=identity.role,
        password_reset_available=get_settings().email_enabled,
    )


def _set_session_cookie(response: Response, token: str, *, remember: bool) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        # Without "remember me" the cookie goes when the browser closes.
        max_age=settings.remember_days * 24 * 60 * 60 if remember else None,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/", httponly=True, samesite="lax", secure=settings.is_production)


@router.get("/options", response_model=Envelope[OptionsOut])
def options() -> Envelope[OptionsOut]:
    """What the sign-in screens can offer, readable before signing in."""
    return Envelope(data=OptionsOut(password_reset_available=get_settings().email_enabled))


@router.post("/register", response_model=Envelope[MeOut], status_code=201)
def register(body: RegisterIn, response: Response, client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[MeOut]:
    identity, token = auth.register(db, email_address=body.email, password=body.password, name=body.name, timezone=body.timezone, client=client)
    _set_session_cookie(response, token, remember=False)
    return Envelope(data=me_payload(identity))


@router.post("/login", response_model=Envelope[MeOut])
def login(body: LoginIn, response: Response, client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[MeOut]:
    identity, token = auth.login(db, email_address=body.email, password=body.password, remember=body.remember, client=client)
    _set_session_cookie(response, token, remember=body.remember)
    return Envelope(data=me_payload(identity))


@router.post("/logout", status_code=204)
def logout(response: Response, identity: Identity | None = Depends(optional_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> None:
    if identity is not None:
        auth.logout(db, identity, client)
    _clear_session_cookie(response)


@router.get("/me", response_model=Envelope[MeOut])
def me(identity: Identity = Depends(current_identity)) -> Envelope[MeOut]:
    return Envelope(data=me_payload(identity))


@router.post("/password/forgot", status_code=202)
def forgot_password(body: ForgotPasswordIn, client: Client = Depends(get_client), db: Session = Depends(get_db)) -> None:
    auth.request_password_reset(db, email_address=body.email, client=client)


@router.post("/password/reset", status_code=204)
def reset_password(body: ResetPasswordIn, response: Response, client: Client = Depends(get_client), db: Session = Depends(get_db)) -> None:
    auth.reset_password(db, token=body.token, new_password=body.password, client=client)
    _clear_session_cookie(response)


@router.post("/password/change", status_code=204)
def change_password(body: ChangePasswordIn, identity: Identity = Depends(current_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> None:
    auth.change_password(db, identity, current_password=body.current_password, new_password=body.new_password, client=client)


@router.get("/sessions", response_model=Envelope[list[SessionOut]])
def list_sessions(identity: Identity = Depends(current_identity), db: Session = Depends(get_db)) -> Envelope[list[SessionOut]]:
    rows = auth.list_sessions(db, identity)
    return Envelope(
        data=[
            SessionOut(
                id=row.id,
                current=row.id == identity.session.id,
                user_agent=row.user_agent,
                ip_address=row.ip_address,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
                expires_at=row.expires_at,
            )
            for row in rows
        ]
    )


@router.post("/sessions/revoke-others", response_model=Envelope[dict[str, int]])
def revoke_other_sessions(identity: Identity = Depends(current_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[dict[str, int]]:
    return Envelope(data={"ended": auth.revoke_other_sessions(db, identity, client)})


@router.get("/workspaces", response_model=Envelope[list[MyWorkspaceOut]])
def list_my_workspaces(identity: Identity = Depends(current_identity), db: Session = Depends(get_db)) -> Envelope[list[MyWorkspaceOut]]:
    current_ws_id = identity.workspace.id if identity.workspace else None
    rows = accounts.list_my_workspaces(db, identity.user.id, current_ws_id)
    return Envelope(
        data=[
            MyWorkspaceOut(
                id=ws.id,
                name=ws.name,
                role=role,
                is_current=is_current,
                created_at=ws.created_at,
            )
            for ws, role, is_current in rows
        ]
    )


@router.post("/workspaces/{workspace_id}/switch", response_model=Envelope[MeOut])
def switch_workspace(workspace_id: int, identity: Identity = Depends(current_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[MeOut]:
    accounts.switch_workspace(db, identity, workspace_id, client)
    return Envelope(data=me_payload(identity))


@router.get("/invitations/{token}", response_model=Envelope[PublicInvitationOut])
def view_invitation(token: str, db: Session = Depends(get_db)) -> Envelope[PublicInvitationOut]:
    invitation, workspace, inviter = accounts.get_invitation_by_token(db, token)
    return Envelope(
        data=PublicInvitationOut(
            workspace_name=workspace.name,
            inviter_name=inviter.name if inviter else None,
            email=invitation.email,
            role=invitation.role,
            is_expired=invitation.expires_at < utcnow(),
        )
    )


@router.post("/invitations/{token}/accept", response_model=Envelope[MeOut])
def accept_invitation(token: str, identity: Identity = Depends(current_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[MeOut]:
    workspace, role = accounts.accept_invitation(db, token, identity.user, client)
    identity.session.workspace_id = workspace.id
    db.commit()
    identity.workspace = workspace
    identity.role = role
    return Envelope(data=me_payload(identity))
