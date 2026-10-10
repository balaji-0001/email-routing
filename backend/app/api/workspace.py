from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_identity, get_client, workspace_identity, workspace_manager
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.auth import ProfileIn, UserOut, WorkspaceOut
from app.schemas.common import Envelope
from app.schemas.workspace import (
    AuditEventOut,
    InvitationCreateIn,
    InvitationOut,
    MemberOut,
    MemberRoleUpdateIn,
    WorkspaceCreateIn,
    WorkspaceUpdateIn,
)
from app.services import accounts
from app.services.auth import Client, Identity

router = APIRouter(tags=["workspace"])


@router.patch("/users/me", response_model=Envelope[UserOut])
def update_profile(body: ProfileIn, identity: Identity = Depends(current_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[UserOut]:
    user = accounts.update_profile(db, identity, first_name=body.first_name, last_name=body.last_name, timezone=body.timezone, client=client)
    return Envelope(data=UserOut.model_validate(user))


@router.post("/workspaces", response_model=Envelope[WorkspaceOut], status_code=201)
def create_workspace(body: WorkspaceCreateIn, identity: Identity = Depends(current_identity), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[WorkspaceOut]:
    workspace = accounts.create_workspace(db, identity, name=body.name, client=client)
    return Envelope(data=WorkspaceOut.model_validate(workspace))


@router.patch("/workspace", response_model=Envelope[WorkspaceOut])
def update_workspace(body: WorkspaceUpdateIn, identity: Identity = Depends(workspace_manager), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[WorkspaceOut]:
    changes = body.model_dump(exclude_unset=True)
    # A workspace always has a name, a time zone and an invitation setting; only the domain may be cleared.
    changes = {field: value for field, value in changes.items() if value is not None or field == "domain"}
    workspace = accounts.update_workspace(db, identity, changes, client)
    return Envelope(data=WorkspaceOut.model_validate(workspace))


@router.get("/workspace/members", response_model=Envelope[list[MemberOut]])
def list_members(identity: Identity = Depends(workspace_identity), db: Session = Depends(get_db)) -> Envelope[list[MemberOut]]:
    return Envelope(
        data=[
            MemberOut(
                id=member.id,
                user_id=user.id,
                name=user.name,
                email=user.email,
                role=member.role,
                is_you=user.id == identity.user.id,
                joined_at=member.created_at,
                last_active_at=last_active_at,
            )
            for member, user, last_active_at in accounts.list_members(db, identity)
        ]
    )


@router.patch("/workspace/members/{member_id}", response_model=Envelope[MemberOut])
def update_member_role(member_id: int, body: MemberRoleUpdateIn, identity: Identity = Depends(workspace_manager), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[MemberOut]:
    member = accounts.update_member_role(db, identity, member_id, body.role, client)
    # Return updated member representation
    members_list = accounts.list_members(db, identity)
    for m, u, last_active in members_list:
        if m.id == member.id:
            return Envelope(
                data=MemberOut(
                    id=m.id,
                    user_id=u.id,
                    name=u.name,
                    email=u.email,
                    role=m.role,
                    is_you=u.id == identity.user.id,
                    joined_at=m.created_at,
                    last_active_at=last_active,
                )
            )
    return Envelope(data=MemberOut(id=member.id, user_id=member.user_id, name="", email="", role=member.role, is_you=False, joined_at=member.created_at, last_active_at=None))


@router.delete("/workspace/members/{member_id}", status_code=204)
def remove_member(member_id: int, identity: Identity = Depends(workspace_manager), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> None:
    accounts.remove_member(db, identity, member_id, client)


@router.get("/workspace/invitations", response_model=Envelope[list[InvitationOut]])
def list_invitations(identity: Identity = Depends(workspace_manager), db: Session = Depends(get_db)) -> Envelope[list[InvitationOut]]:
    rows = accounts.list_invitations(db, identity)
    return Envelope(
        data=[
            InvitationOut(
                id=inv.id,
                email=inv.email,
                role=inv.role,
                invited_by_name=inviter.name if inviter else None,
                invite_url="",  # shown once, when the invitation is made; only a fingerprint of the link is stored
                expires_at=inv.expires_at,
                created_at=inv.created_at,
            )
            for inv, inviter in rows
        ]
    )


@router.post("/workspace/invitations", response_model=Envelope[InvitationOut], status_code=201)
def create_invitation(body: InvitationCreateIn, identity: Identity = Depends(workspace_manager), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> Envelope[InvitationOut]:
    settings = get_settings()
    invitation, raw_token = accounts.create_invitation(db, identity, email=body.email, role=body.role, client=client)
    return Envelope(
        data=InvitationOut(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role,
            invited_by_name=identity.user.name,
            invite_url=f"{settings.app_url.rstrip('/')}/invite/{raw_token}",
            token=raw_token,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )
    )


@router.delete("/workspace/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: int, identity: Identity = Depends(workspace_manager), client: Client = Depends(get_client), db: Session = Depends(get_db)) -> None:
    accounts.revoke_invitation(db, identity, invitation_id, client)


@router.get("/workspace/audit-events", response_model=Envelope[list[AuditEventOut]])
def list_audit_events(limit: int = Query(50, ge=1, le=200), identity: Identity = Depends(workspace_manager), db: Session = Depends(get_db)) -> Envelope[list[AuditEventOut]]:
    return Envelope(
        data=[
            AuditEventOut(
                id=event.id,
                action=event.action,
                summary=event.summary,
                actor_name=actor.name if actor else None,
                actor_is_you=bool(actor and actor.id == identity.user.id),
                ip_address=event.ip_address,
                created_at=event.created_at,
            )
            for event, actor in accounts.list_audit_events(db, identity, limit)
        ]
    )
