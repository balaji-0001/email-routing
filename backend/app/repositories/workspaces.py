from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuthSession, User, Workspace, WorkspaceInvitation, WorkspaceMember


def get(db: Session, workspace_id: int) -> Workspace | None:
    return db.get(Workspace, workspace_id)


def add(db: Session, workspace: Workspace) -> Workspace:
    db.add(workspace)
    db.flush()
    return workspace


def add_member(db: Session, member: WorkspaceMember) -> WorkspaceMember:
    db.add(member)
    db.flush()
    return member


def get_member(db: Session, member_id: int) -> WorkspaceMember | None:
    return db.get(WorkspaceMember, member_id)


def delete_member(db: Session, member: WorkspaceMember) -> None:
    db.delete(member)
    db.flush()


def count_owners(db: Session, workspace_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == "owner",
        )
    ) or 0


def membership(db: Session, workspace_id: int, user_id: int) -> WorkspaceMember | None:
    return db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id))


def user_memberships(db: Session, user_id: int) -> list[tuple[WorkspaceMember, Workspace]]:
    rows = db.execute(
        select(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.created_at, Workspace.id)
    )
    return [(member, ws) for member, ws in rows]


def first_membership(db: Session, user_id: int) -> WorkspaceMember | None:
    """The workspace a person lands in when they sign in: the one they joined first."""
    return db.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == user_id).order_by(WorkspaceMember.created_at, WorkspaceMember.id).limit(1))


def members(db: Session, workspace_id: int) -> list[tuple[WorkspaceMember, User, datetime | None]]:
    """Every member with the last time any of their sessions was used."""
    last_active = (
        select(AuthSession.user_id, func.max(AuthSession.last_used_at).label("last_active_at"))
        .group_by(AuthSession.user_id)
        .subquery()
    )
    rows = db.execute(
        select(WorkspaceMember, User, last_active.c.last_active_at)
        .join(User, User.id == WorkspaceMember.user_id)
        .outerjoin(last_active, last_active.c.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.created_at, WorkspaceMember.id)
    )
    return [(member, user, seen) for member, user, seen in rows]


def add_invitation(db: Session, invitation: WorkspaceInvitation) -> WorkspaceInvitation:
    db.add(invitation)
    db.flush()
    return invitation


def get_invitation(db: Session, invitation_id: int) -> WorkspaceInvitation | None:
    return db.get(WorkspaceInvitation, invitation_id)


def get_invitation_by_token_hash(db: Session, token_hash: str) -> WorkspaceInvitation | None:
    return db.scalar(select(WorkspaceInvitation).where(WorkspaceInvitation.token_hash == token_hash))


def pending_invitations(db: Session, workspace_id: int) -> list[tuple[WorkspaceInvitation, User | None]]:
    rows = db.execute(
        select(WorkspaceInvitation, User)
        .outerjoin(User, User.id == WorkspaceInvitation.invited_by_user_id)
        .where(WorkspaceInvitation.workspace_id == workspace_id, WorkspaceInvitation.accepted_at.is_(None))
        .order_by(WorkspaceInvitation.created_at.desc())
    )
    return [(invitation, user) for invitation, user in rows]


def delete_invitation(db: Session, invitation: WorkspaceInvitation) -> None:
    db.delete(invitation)
    db.flush()
