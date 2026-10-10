"""Drafts, assignment, internal notes, notifications, contacts and templates."""

import re

from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import AppError
from app.models.collab import Draft, Note, Notification, Template
from app.models.email import Conversation
from app.repositories import collab as repo
from app.repositories import conversations as conv_repo
from app.repositories import email as email_repo
from app.repositories import workspaces
from app.schemas.collab import DraftIn, TemplateIn
from app.services import audit, mailbox_access
from app.services.accounts import MANAGERS
from app.services.auth import Client, Identity

TEMPLATE_EDITORS = (*MANAGERS, "manager")


def _not_viewer(identity: Identity, what: str) -> None:
    if identity.role == "viewer":
        raise AppError(403, "FORBIDDEN", f"Viewers can read mail but not {what}.")


def _conversation(db: Session, identity: Identity, conversation_id: int) -> Conversation:
    found = conv_repo.get_conversation(db, conversation_id, identity.workspace.id, mailbox_access.allowed_account_ids(db, identity))
    if not found:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation not found.")
    return found[0]


def notify(db: Session, *, workspace_id: int, user_id: int, actor: Identity, kind: str, title: str, body: str | None, conversation_id: int | None) -> None:
    """Tell one person something. Nobody is notified about what they did themselves."""
    if user_id == actor.user.id:
        return
    db.add(Notification(workspace_id=workspace_id, user_id=user_id, actor_user_id=actor.user.id, kind=kind, title=title[:255], body=(body or "")[:500] or None, conversation_id=conversation_id))


# --- drafts ---------------------------------------------------------------------

def _check_draft(db: Session, identity: Identity, data: DraftIn) -> None:
    _not_viewer(identity, "write it")
    account = email_repo.get_account(db, data.email_account_id, identity.workspace.id)
    if not account or mailbox_access.permission(db, identity, account) is None:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Email account not found.")
    if data.conversation_id is not None:
        _conversation(db, identity, data.conversation_id)
    if data.forward_of_message_id is not None:
        message = conv_repo.get_message(db, data.forward_of_message_id, identity.workspace.id)
        allowed = mailbox_access.allowed_account_ids(db, identity)
        if not message or (allowed is not None and message.email_account_id not in allowed):
            raise AppError(404, "MESSAGE_NOT_FOUND", "Message not found.")


def _fill(draft: Draft, data: DraftIn) -> None:
    draft.email_account_id = data.email_account_id
    draft.mode = data.mode
    draft.conversation_id = data.conversation_id
    draft.in_reply_to = data.in_reply_to
    draft.forward_of_message_id = data.forward_of_message_id
    draft.to_addresses, draft.cc_addresses, draft.bcc_addresses = data.to, data.cc, data.bcc
    draft.subject = data.subject
    draft.body_text = data.body_text
    draft.updated_at = utcnow()


def create_draft(db: Session, identity: Identity, data: DraftIn) -> Draft:
    _check_draft(db, identity, data)
    draft = Draft(workspace_id=identity.workspace.id, user_id=identity.user.id)
    _fill(draft, data)
    db.add(draft)
    db.commit()
    return draft


def update_draft(db: Session, identity: Identity, draft_id: int, data: DraftIn) -> Draft:
    draft = repo.get_draft(db, draft_id, identity.workspace.id, identity.user.id)
    if not draft:
        raise AppError(404, "DRAFT_NOT_FOUND", "This draft is no longer here.")
    _check_draft(db, identity, data)
    _fill(draft, data)
    db.commit()
    return draft


def delete_draft(db: Session, identity: Identity, draft_id: int, *, missing_ok: bool = False) -> None:
    draft = repo.get_draft(db, draft_id, identity.workspace.id, identity.user.id)
    if not draft:
        if missing_ok:
            return
        raise AppError(404, "DRAFT_NOT_FOUND", "This draft is no longer here.")
    db.delete(draft)
    db.commit()


# --- assignment -------------------------------------------------------------------

def assign(db: Session, identity: Identity, conversation_id: int, assignee_user_id: int | None, client: Client) -> Conversation:
    _not_viewer(identity, "assign it")
    conversation = _conversation(db, identity, conversation_id)
    if conversation.assignee_user_id == assignee_user_id:
        return conversation
    # Agents take or give up their own conversations; managers and above assign anyone.
    taking = assignee_user_id == identity.user.id
    giving_up = assignee_user_id is None and conversation.assignee_user_id == identity.user.id
    if identity.role == "agent" and not (taking or giving_up):
        raise AppError(403, "FORBIDDEN", "Agents can assign conversations to themselves. A manager can assign them to someone else.")

    name = None
    if assignee_user_id is not None:
        member = workspaces.membership(db, identity.workspace.id, assignee_user_id)
        if not member:
            raise AppError(404, "MEMBER_NOT_FOUND", "That person is not in this workspace.")
        account = email_repo.get_account(db, conversation.email_account_id, identity.workspace.id)
        person = Identity(user=db.get(type(identity.user), assignee_user_id), session=identity.session, workspace=identity.workspace, role=member.role)
        if account is None or mailbox_access.permission(db, person, account) is None:
            raise AppError(409, "NO_MAILBOX_ACCESS", f"{person.user.name} cannot use this mailbox. Give them access on the Email accounts page first.")
        name = person.user.name
        notify(db, workspace_id=identity.workspace.id, user_id=assignee_user_id, actor=identity, kind="assigned",
               title=f"{identity.user.name} assigned you a conversation", body=conversation.subject, conversation_id=conversation.id)

    conversation.assignee_user_id = assignee_user_id
    audit.record(db, action="conversation.assigned", summary=(f"Assigned '{conversation.subject}' to {name}" if name else f"Unassigned '{conversation.subject}'")[:255],
                 actor=identity.user, workspace_id=identity.workspace.id, ip=client.ip)
    db.commit()
    return conversation


# --- notes ------------------------------------------------------------------------

def _mentioned(db: Session, workspace_id: int, text: str) -> set[int]:
    """People named after an @ in the note: by first name, full name or email address."""
    lowered = text.lower()
    found: set[int] = set()
    for _member, user, _seen in workspaces.members(db, workspace_id):
        names = {user.email.lower(), user.name.lower(), user.first_name.lower()}
        if any(name and re.search(r"@" + re.escape(name) + r"(?![\w.-])", lowered) for name in names):
            found.add(user.id)
    return found


def add_note(db: Session, identity: Identity, conversation_id: int, body: str) -> Note:
    _not_viewer(identity, "add notes")
    conversation = _conversation(db, identity, conversation_id)
    text = body.strip()
    if not text:
        raise AppError(422, "VALIDATION_ERROR", "Write something in the note.")
    note = Note(workspace_id=identity.workspace.id, conversation_id=conversation.id, author_user_id=identity.user.id, body=text)
    db.add(note)

    from app.automation.actions import _can_use_mailbox

    roles = {user.id: (user, member.role) for member, user, _seen in workspaces.members(db, identity.workspace.id)}
    # Naming someone must not hand them a copy of a note about mail they are not allowed to open.
    mentioned = {user_id for user_id in _mentioned(db, identity.workspace.id, text) if _can_use_mailbox(db, conversation, *roles[user_id])}
    for user_id in mentioned:
        notify(db, workspace_id=identity.workspace.id, user_id=user_id, actor=identity, kind="mentioned",
               title=f"{identity.user.name} mentioned you in a note", body=text, conversation_id=conversation.id)
    if conversation.assignee_user_id and conversation.assignee_user_id not in mentioned:
        notify(db, workspace_id=identity.workspace.id, user_id=conversation.assignee_user_id, actor=identity, kind="note",
               title=f"{identity.user.name} left a note on your conversation", body=text, conversation_id=conversation.id)
    db.commit()
    return note


def delete_note(db: Session, identity: Identity, note_id: int) -> None:
    note = repo.get_note(db, note_id, identity.workspace.id)
    if not note:
        raise AppError(404, "NOTE_NOT_FOUND", "Note not found.")
    _conversation(db, identity, note.conversation_id)
    if note.author_user_id != identity.user.id and identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only the person who wrote a note, or an owner or admin, can delete it.")
    db.delete(note)
    db.commit()


# --- notifications -----------------------------------------------------------------

def mark_read(db: Session, identity: Identity, ids: list[int]) -> None:
    repo.mark_notifications_read(db, identity.workspace.id, identity.user.id, ids, utcnow())
    db.commit()


# --- contacts ----------------------------------------------------------------------

def list_contacts(db: Session, identity: Identity, search: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    allowed = mailbox_access.allowed_account_ids(db, identity)
    people = repo.contacts(db, identity.workspace.id, allowed)
    # The workspace's own mailboxes are not contacts.
    for account, _count in email_repo.list_accounts(db, identity.workspace.id):
        people.pop(account.email_address.lower(), None)
    rows = list(people.values())
    if search and search.strip():
        term = search.strip().lower()
        rows = [p for p in rows if term in p["email"] or term in (p["name"] or "").lower()]
    rows.sort(key=lambda p: (p["last_message_at"] is not None, p["last_message_at"]), reverse=True)
    return rows[offset : offset + limit], len(rows)


# --- templates ---------------------------------------------------------------------

def _can_edit_templates(identity: Identity) -> None:
    if identity.role not in TEMPLATE_EDITORS:
        raise AppError(403, "FORBIDDEN", "Owners, admins and managers can change templates. Everyone else can use them.")


def create_template(db: Session, identity: Identity, data: TemplateIn) -> Template:
    _can_edit_templates(identity)
    name = " ".join(data.name.split())
    if repo.find_template(db, identity.workspace.id, name):
        raise AppError(409, "TEMPLATE_EXISTS", f"There is already a template called {name}.")
    template = Template(workspace_id=identity.workspace.id, created_by_user_id=identity.user.id, name=name, subject=data.subject.strip(), body=data.body)
    db.add(template)
    db.commit()
    return template


def update_template(db: Session, identity: Identity, template_id: int, data: TemplateIn) -> Template:
    _can_edit_templates(identity)
    template = repo.get_template(db, template_id, identity.workspace.id)
    if not template:
        raise AppError(404, "TEMPLATE_NOT_FOUND", "Template not found.")
    name = " ".join(data.name.split())
    other = repo.find_template(db, identity.workspace.id, name)
    if other and other.id != template.id:
        raise AppError(409, "TEMPLATE_EXISTS", f"There is already a template called {name}.")
    template.name, template.subject, template.body, template.updated_at = name, data.subject.strip(), data.body, utcnow()
    db.commit()
    return template


def delete_template(db: Session, identity: Identity, template_id: int) -> None:
    _can_edit_templates(identity)
    template = repo.get_template(db, template_id, identity.workspace.id)
    if not template:
        raise AppError(404, "TEMPLATE_NOT_FOUND", "Template not found.")
    db.delete(template)
    db.commit()
