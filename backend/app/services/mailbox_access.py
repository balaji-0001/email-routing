"""Who may use each mailbox.

Owners and admins can use every mailbox. Everyone else can use a mailbox that
is open to the workspace, or a restricted one that their role or they
themselves have been given. A grant is "read" or "send" (read and send); when
both a role and the person have one, the higher applies. Viewers never send.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.email import EmailAccount, EmailAccountMember, EmailAccountRole
from app.repositories import email as email_repo
from app.repositories import workspaces
from app.services import audit
from app.services.accounts import MANAGERS
from app.services.auth import Client, Identity

# In the order the app lists them, with what each is for.
ROLES = (
    ("owner", "Owner", "Created the workspace"),
    ("admin", "Admin", "Runs the workspace"),
    ("manager", "Manager", "Leads a team"),
    ("agent", "Agent", "Works conversations"),
    ("viewer", "Viewer", "Read-only access"),
)
_RANK = {None: 0, "read": 1, "send": 2}


def _best(*levels: str | None) -> str | None:
    return max(levels, key=lambda level: _RANK[level])


def allowed_account_ids(db: Session, identity: Identity) -> list[int] | None:
    """The mailboxes this person may see. None means all of them."""
    if identity.role in MANAGERS:
        return None
    mine = set(db.scalars(select(EmailAccountMember.email_account_id).where(EmailAccountMember.user_id == identity.user.id)))
    my_role = set(db.scalars(select(EmailAccountRole.email_account_id).where(EmailAccountRole.role == identity.role)))
    rows = db.execute(select(EmailAccount.id, EmailAccount.access_mode).where(EmailAccount.workspace_id == identity.workspace.id))
    return [int(account_id) for account_id, mode in rows if mode != "restricted" or account_id in mine or account_id in my_role]


def permission(db: Session, identity: Identity, account: EmailAccount) -> str | None:
    """'send', 'read' or None for this person on this mailbox."""
    if identity.role in MANAGERS:
        return "send"
    if account.access_mode != "restricted":
        return "read" if identity.role == "viewer" else "send"
    own = db.scalar(select(EmailAccountMember.permission).where(EmailAccountMember.email_account_id == account.id, EmailAccountMember.user_id == identity.user.id))
    by_role = db.scalar(select(EmailAccountRole.permission).where(EmailAccountRole.email_account_id == account.id, EmailAccountRole.role == identity.role))
    level = _best(own, by_role)
    if level is None:
        return None
    return "read" if identity.role == "viewer" else level


def require_send(db: Session, identity: Identity, account: EmailAccount) -> None:
    level = permission(db, identity, account)
    if level is None:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Sending email account not found.")
    if level != "send":
        raise AppError(403, "FORBIDDEN", f"You can read {account.email_address} but not send from it.")


def describe(db: Session, identity: Identity, account_id: int) -> tuple[EmailAccount, list[dict], list[dict]]:
    """The mailbox, what each role has, and what each person has."""
    account = email_repo.get_account(db, account_id, identity.workspace.id)
    if not account:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Email account not found.")
    by_role = dict(db.execute(select(EmailAccountRole.role, EmailAccountRole.permission).where(EmailAccountRole.email_account_id == account.id)).all())
    given = dict(db.execute(select(EmailAccountMember.user_id, EmailAccountMember.permission).where(EmailAccountMember.email_account_id == account.id)).all())
    people_in = workspaces.members(db, identity.workspace.id)
    roles = [
        {
            "role": key,
            "name": name,
            "description": description,
            "always": key in MANAGERS,
            "permission": "send" if key in MANAGERS else by_role.get(key),
            "people": sum(1 for member, _user, _seen in people_in if member.role == key),
        }
        for key, name, description in ROLES
    ]
    people = []
    for member, user, _last_active in people_in:
        always = member.role in MANAGERS
        people.append({
            "user_id": user.id,
            "name": user.name,
            "email": user.email,
            "role": member.role,
            "always": always,
            "permission": "send" if always else given.get(user.id),
        })
    return account, roles, people


def update(db: Session, identity: Identity, account_id: int, access_mode: str, members: list[tuple[int, str]], roles: list[tuple[str, str]], client: Client) -> None:
    account = email_repo.get_account(db, account_id, identity.workspace.id)
    if not account:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Email account not found.")
    in_workspace = {user.id: member.role for member, user, _ in workspaces.members(db, identity.workspace.id)}

    db.execute(delete(EmailAccountMember).where(EmailAccountMember.email_account_id == account.id))
    db.execute(delete(EmailAccountRole).where(EmailAccountRole.email_account_id == account.id))
    kept_people = 0
    for user_id, level in dict(members).items():
        if user_id not in in_workspace:
            raise AppError(404, "MEMBER_NOT_FOUND", "That person is not in this workspace.")
        if in_workspace[user_id] in MANAGERS:
            continue  # owners and admins always have access; nothing to store
        db.add(EmailAccountMember(email_account_id=account.id, user_id=user_id, permission=level))
        kept_people += 1
    kept_roles = []
    for role, level in dict(roles).items():
        if role in MANAGERS:
            continue
        # A viewer can never send, so that is all a viewer grant can mean.
        db.add(EmailAccountRole(email_account_id=account.id, role=role, permission="read" if role == "viewer" else level))
        kept_roles.append(role)
    account.access_mode = access_mode

    if access_mode == "restricted":
        who = [f"{role}s" for role in kept_roles] + ([f"{kept_people} selected {'person' if kept_people == 1 else 'people'}"] if kept_people else [])
        summary = f"Limited {account.email_address} to owners, admins" + (", " + ", ".join(who) if who else "")
    else:
        summary = f"Opened {account.email_address} to everyone in the workspace"
    audit.record(db, action="email_account.access_changed", summary=summary, actor=identity.user, workspace_id=identity.workspace.id, ip=client.ip)
    db.commit()
