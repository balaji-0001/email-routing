from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from sqlalchemy import delete, select, update

from app.core import security
from app.core.database import utcnow
from app.core.errors import AppError
from app.models import AuditEvent, User, Workspace, WorkspaceInvitation, WorkspaceMember
from app.repositories import audit as audit_repo
from app.repositories import users as users_repo
from app.repositories import workspaces
from app.services import audit
from app.services.auth import Client, Identity

# Who may change workspace settings, invite members, change roles, and read the audit log.
MANAGERS = ("owner", "admin")
VALID_ROLES = ("owner", "admin", "manager", "agent", "viewer")
INVITABLE_ROLES = ("admin", "manager", "agent", "viewer")


def update_profile(db: Session, identity: Identity, *, first_name: str, last_name: str, timezone: str | None, client: Client) -> User:
    user = identity.user
    user.first_name = first_name
    user.last_name = last_name
    user.timezone = timezone
    audit.record(db, action="profile.updated", summary="Updated profile details", actor=user, workspace_id=identity.session.workspace_id, ip=client.ip)
    db.commit()
    return user


def create_workspace(db: Session, identity: Identity, *, name: str, client: Client) -> Workspace:
    if identity.workspace is not None:
        raise AppError(409, "WORKSPACE_EXISTS", "You already belong to a workspace.")
    user = identity.user
    workspace = workspaces.add(db, Workspace(name=name, timezone=user.timezone or "UTC", created_by_user_id=user.id))
    workspaces.add_member(db, WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    identity.session.workspace_id = workspace.id
    identity.workspace, identity.role = workspace, "owner"
    audit.record(db, action="workspace.created", summary=f"Created the workspace {name}", actor=user, workspace_id=workspace.id, ip=client.ip)
    db.commit()
    return workspace


def update_workspace(db: Session, identity: Identity, changes: dict, client: Client) -> Workspace:
    """Apply the given fields to the current workspace. `changes` holds only what the caller sent."""
    workspace = identity.workspace
    assert workspace is not None
    changed = [field for field, value in changes.items() if getattr(workspace, field) != value]
    for field in changed:
        setattr(workspace, field, changes[field])
    if changed:
        summary = f"Renamed the workspace to {workspace.name}" if changed == ["name"] else "Updated the workspace settings"
        audit.record(db, action="workspace.updated", summary=summary, actor=identity.user, workspace_id=workspace.id, ip=client.ip)
    db.commit()
    return workspace


def list_members(db: Session, identity: Identity) -> list[tuple[WorkspaceMember, User, datetime | None]]:
    assert identity.workspace is not None
    return workspaces.members(db, identity.workspace.id)


def update_member_role(db: Session, identity: Identity, member_id: int, new_role: str, client: Client) -> WorkspaceMember:
    assert identity.workspace is not None
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only workspace owners and admins can change roles.")

    if new_role not in VALID_ROLES:
        raise AppError(400, "INVALID_ROLE", f"Role must be one of: {', '.join(VALID_ROLES)}")

    member = workspaces.get_member(db, member_id)
    if not member or member.workspace_id != identity.workspace.id:
        raise AppError(404, "MEMBER_NOT_FOUND", "Workspace member not found.")

    if member.user_id == identity.user.id and new_role != member.role:
        raise AppError(400, "CANNOT_CHANGE_OWN_ROLE", "You cannot change your own role.")

    # Owners are above admins: only an owner may make someone an owner, or change an owner's role.
    if (new_role == "owner" or member.role == "owner") and identity.role != "owner":
        raise AppError(403, "FORBIDDEN", "Only an owner can make someone an owner or change an owner's role.")

    # Protecting the last owner. The owner rows are locked so two changes at once cannot both pass.
    if member.role == "owner" and new_role != "owner":
        _lock_owners(db, identity.workspace.id)
        owners_count = workspaces.count_owners(db, identity.workspace.id)
        if owners_count <= 1:
            raise AppError(400, "LAST_OWNER_REQUIRED", "A workspace must have at least one owner.")

    old_role = member.role
    member.role = new_role
    target_user = users_repo.get(db, member.user_id)
    target_name = target_user.name if target_user else "Member"
    audit.record(
        db,
        action="member.role_updated",
        summary=f"Changed {target_name}'s role from {old_role} to {new_role}",
        actor=identity.user,
        workspace_id=identity.workspace.id,
        ip=client.ip,
    )
    db.commit()
    return member


def _lock_owners(db: Session, workspace_id: int) -> None:
    db.execute(select(WorkspaceMember.id).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == "owner").with_for_update()).all()


def _forget_person(db: Session, workspace_id: int, user_id: int) -> None:
    """Take back what a leaving person was given here: mailbox grants, assignments, reminders still waiting."""
    from app.models.automation import Reminder
    from app.models.email import Conversation, EmailAccount, EmailAccountMember

    own_accounts = select(EmailAccount.id).where(EmailAccount.workspace_id == workspace_id)
    db.execute(delete(EmailAccountMember).where(EmailAccountMember.user_id == user_id, EmailAccountMember.email_account_id.in_(own_accounts)))
    db.execute(update(Conversation).where(Conversation.workspace_id == workspace_id, Conversation.assignee_user_id == user_id).values(assignee_user_id=None))
    db.execute(update(Reminder).where(Reminder.workspace_id == workspace_id, Reminder.user_id == user_id, Reminder.status == "waiting").values(status="cancelled", finished_at=utcnow()))


def remove_member(db: Session, identity: Identity, member_id: int, client: Client) -> None:
    assert identity.workspace is not None
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only workspace owners and admins can remove members.")

    member = workspaces.get_member(db, member_id)
    if not member or member.workspace_id != identity.workspace.id:
        raise AppError(404, "MEMBER_NOT_FOUND", "Workspace member not found.")

    if member.user_id == identity.user.id:
        raise AppError(400, "CANNOT_REMOVE_SELF", "You cannot remove yourself from the workspace.")

    if member.role == "owner":
        if identity.role != "owner":
            raise AppError(403, "FORBIDDEN", "Only an owner can remove an owner.")
        _lock_owners(db, identity.workspace.id)
        owners_count = workspaces.count_owners(db, identity.workspace.id)
        if owners_count <= 1:
            raise AppError(400, "LAST_OWNER_REQUIRED", "The last owner cannot be removed.")

    target_user = users_repo.get(db, member.user_id)
    target_name = target_user.name if target_user else "Member"
    _forget_person(db, identity.workspace.id, member.user_id)
    workspaces.delete_member(db, member)
    audit.record(
        db,
        action="member.removed",
        summary=f"Removed {target_name} from the workspace",
        actor=identity.user,
        workspace_id=identity.workspace.id,
        ip=client.ip,
    )
    db.commit()


def create_invitation(db: Session, identity: Identity, email: str, role: str, client: Client) -> tuple[WorkspaceInvitation, str]:
    workspace = identity.workspace
    assert workspace is not None
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only workspace owners and admins can invite members.")

    if not workspace.allow_invitations:
        raise AppError(403, "INVITATIONS_DISABLED", "Invitations are disabled for this workspace.")

    if role not in INVITABLE_ROLES:
        raise AppError(400, "INVALID_ROLE", f"Invited role must be one of: {', '.join(INVITABLE_ROLES)}")

    email_normalized = email.strip().lower()
    existing_user = users_repo.get_by_email(db, email_normalized)
    if existing_user:
        current_membership = workspaces.membership(db, workspace.id, existing_user.id)
        if current_membership:
            raise AppError(409, "ALREADY_MEMBER", "This person is already a member of this workspace.")

    raw_token = security.new_token()
    token_hash = security.hash_token(raw_token)
    expires_at = utcnow() + timedelta(days=7)

    invitation = workspaces.add_invitation(
        db,
        WorkspaceInvitation(
            workspace_id=workspace.id,
            email=email_normalized,
            role=role,
            token_hash=token_hash,
            invited_by_user_id=identity.user.id,
            expires_at=expires_at,
        ),
    )
    audit.record(
        db,
        action="invitation.created",
        summary=f"Invited {email_normalized} as {role}",
        actor=identity.user,
        workspace_id=workspace.id,
        ip=client.ip,
    )
    db.commit()
    return invitation, raw_token


def list_invitations(db: Session, identity: Identity) -> list[tuple[WorkspaceInvitation, User | None]]:
    assert identity.workspace is not None
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only workspace owners and admins can view invitations.")
    return workspaces.pending_invitations(db, identity.workspace.id)


def revoke_invitation(db: Session, identity: Identity, invitation_id: int, client: Client) -> None:
    assert identity.workspace is not None
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only workspace owners and admins can revoke invitations.")

    invitation = workspaces.get_invitation(db, invitation_id)
    if not invitation or invitation.workspace_id != identity.workspace.id:
        raise AppError(404, "INVITATION_NOT_FOUND", "Invitation not found.")

    email = invitation.email
    workspaces.delete_invitation(db, invitation)
    audit.record(
        db,
        action="invitation.revoked",
        summary=f"Revoked invitation for {email}",
        actor=identity.user,
        workspace_id=identity.workspace.id,
        ip=client.ip,
    )
    db.commit()


def get_invitation_by_token(db: Session, raw_token: str) -> tuple[WorkspaceInvitation, Workspace, User | None]:
    token_hash = security.hash_token(raw_token)
    invitation = workspaces.get_invitation_by_token_hash(db, token_hash)
    if not invitation or invitation.accepted_at is not None:
        raise AppError(404, "INVITATION_INVALID", "This invitation link is invalid or has already been used.")

    if invitation.expires_at < utcnow():
        raise AppError(410, "INVITATION_EXPIRED", "This invitation has expired. Ask the workspace admin for a new link.")

    workspace = workspaces.get(db, invitation.workspace_id)
    if not workspace:
        raise AppError(404, "WORKSPACE_NOT_FOUND", "The invited workspace no longer exists.")

    inviter = users_repo.get(db, invitation.invited_by_user_id) if invitation.invited_by_user_id else None
    return invitation, workspace, inviter


def accept_invitation(db: Session, raw_token: str, user: User, client: Client) -> tuple[Workspace, str]:
    invitation, workspace, _ = get_invitation_by_token(db, raw_token)
    # The link is for the person it was sent to. Anyone else who gets hold of it cannot use it.
    if user.email.strip().lower() != invitation.email.strip().lower():
        raise AppError(403, "INVITATION_NOT_YOURS", f"This invitation was sent to {invitation.email}. Sign in with that address to accept it.")
    # Claimed in one step, so two people (or two clicks) cannot both use the same link.
    claimed = db.execute(update(WorkspaceInvitation).where(WorkspaceInvitation.id == invitation.id, WorkspaceInvitation.accepted_at.is_(None)).values(accepted_at=utcnow())).rowcount
    if claimed != 1:
        db.rollback()
        raise AppError(404, "INVITATION_INVALID", "This invitation link is invalid or has already been used.")

    existing_membership = workspaces.membership(db, workspace.id, user.id)
    if not existing_membership:
        workspaces.add_member(db, WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=invitation.role))

    audit.record(
        db,
        action="invitation.accepted",
        summary=f"{user.name} joined the workspace as {invitation.role}",
        actor=user,
        workspace_id=workspace.id,
        ip=client.ip,
    )
    db.commit()
    return workspace, invitation.role


def list_my_workspaces(db: Session, user_id: int, current_workspace_id: int | None) -> list[tuple[Workspace, str, bool]]:
    memberships = workspaces.user_memberships(db, user_id)
    return [(ws, member.role, ws.id == current_workspace_id) for member, ws in memberships]


def switch_workspace(db: Session, identity: Identity, target_workspace_id: int, client: Client) -> tuple[Workspace, str]:
    member = workspaces.membership(db, target_workspace_id, identity.user.id)
    if not member:
        raise AppError(403, "NOT_A_MEMBER", "You do not belong to this workspace.")

    target_workspace = workspaces.get(db, target_workspace_id)
    if not target_workspace:
        raise AppError(404, "WORKSPACE_NOT_FOUND", "Workspace not found.")

    identity.session.workspace_id = target_workspace_id
    identity.workspace = target_workspace
    identity.role = member.role

    audit.record(
        db,
        action="workspace.switched",
        summary=f"Switched to workspace {target_workspace.name}",
        actor=identity.user,
        workspace_id=target_workspace.id,
        ip=client.ip,
    )
    db.commit()
    return target_workspace, member.role


def list_audit_events(db: Session, identity: Identity, limit: int) -> list[tuple[AuditEvent, User | None]]:
    assert identity.workspace is not None
    return audit_repo.for_workspace(db, identity.workspace.id, limit)
