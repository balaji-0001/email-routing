from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.collab import Draft, Note, Notification, Template
from app.models.email import Conversation, EmailAccount, Message, MessageRecipient
from app.models.user import User


def user_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    return {user.id: user.name for user in db.scalars(select(User).where(User.id.in_(user_ids)))}


# --- drafts ---------------------------------------------------------------------

def list_drafts(db: Session, workspace_id: int, user_id: int) -> list[tuple[Draft, EmailAccount]]:
    rows = db.execute(
        select(Draft, EmailAccount)
        .join(EmailAccount, EmailAccount.id == Draft.email_account_id)
        .where(Draft.workspace_id == workspace_id, Draft.user_id == user_id)
        .order_by(Draft.updated_at.desc())
    )
    return [(draft, account) for draft, account in rows]


def get_draft(db: Session, draft_id: int, workspace_id: int, user_id: int) -> Draft | None:
    return db.scalar(select(Draft).where(Draft.id == draft_id, Draft.workspace_id == workspace_id, Draft.user_id == user_id))


# --- notes ----------------------------------------------------------------------

def notes_for_conversation(db: Session, conversation_id: int) -> list[Note]:
    return list(db.scalars(select(Note).where(Note.conversation_id == conversation_id).order_by(Note.created_at, Note.id)))


def get_note(db: Session, note_id: int, workspace_id: int) -> Note | None:
    return db.scalar(select(Note).where(Note.id == note_id, Note.workspace_id == workspace_id))


def recent_notes(db: Session, workspace_id: int, account_ids: list[int] | None, limit: int) -> list[tuple[Note, Conversation]]:
    stmt = (
        select(Note, Conversation)
        .join(Conversation, Conversation.id == Note.conversation_id)
        .where(Note.workspace_id == workspace_id)
        .order_by(Note.created_at.desc(), Note.id.desc())
        .limit(limit)
    )
    if account_ids is not None:
        stmt = stmt.where(Conversation.email_account_id.in_(account_ids))
    return [(note, conversation) for note, conversation in db.execute(stmt)]


# --- notifications ---------------------------------------------------------------

def list_notifications(db: Session, workspace_id: int, user_id: int, limit: int) -> list[Notification]:
    return list(db.scalars(
        select(Notification).where(Notification.workspace_id == workspace_id, Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    ))


def unread_notifications(db: Session, workspace_id: int, user_id: int) -> int:
    return int(db.scalar(
        select(func.count()).select_from(Notification)
        .where(Notification.workspace_id == workspace_id, Notification.user_id == user_id, Notification.read_at.is_(None))
    ) or 0)


def mark_notifications_read(db: Session, workspace_id: int, user_id: int, ids: list[int], now: datetime) -> None:
    stmt = update(Notification).where(Notification.workspace_id == workspace_id, Notification.user_id == user_id, Notification.read_at.is_(None)).values(read_at=now)
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    db.execute(stmt)


# --- contacts ---------------------------------------------------------------------

def contacts(db: Session, workspace_id: int, account_ids: list[int] | None) -> dict[str, dict]:
    """Everyone the workspace has received mail from or sent mail to, keyed by address."""
    received = (
        select(Message.sender_email, func.max(Message.sender_name), func.count(), func.max(Message.sent_at))
        .where(Message.workspace_id == workspace_id, Message.direction == "inbound")
        .group_by(Message.sender_email)
    )
    sent = (
        select(MessageRecipient.email, func.max(MessageRecipient.name), func.count(), func.max(Message.sent_at))
        .join(Message, Message.id == MessageRecipient.message_id)
        .where(Message.workspace_id == workspace_id, Message.direction == "outbound")
        .group_by(MessageRecipient.email)
    )
    if account_ids is not None:
        received = received.where(Message.email_account_id.in_(account_ids))
        sent = sent.where(Message.email_account_id.in_(account_ids))

    people: dict[str, dict] = {}
    for kind, stmt in (("received", received), ("sent", sent)):
        for email, name, count, last in db.execute(stmt):
            address = (email or "").strip().lower()
            if not address:
                continue
            person = people.setdefault(address, {"email": address, "name": None, "received": 0, "sent": 0, "last_message_at": None})
            person[kind] += int(count)
            person["name"] = person["name"] or (name or None)
            if last and (person["last_message_at"] is None or last > person["last_message_at"]):
                person["last_message_at"] = last
    return people


# --- templates ---------------------------------------------------------------------

def list_templates(db: Session, workspace_id: int) -> list[Template]:
    return list(db.scalars(select(Template).where(Template.workspace_id == workspace_id).order_by(Template.name)))


def get_template(db: Session, template_id: int, workspace_id: int) -> Template | None:
    return db.scalar(select(Template).where(Template.id == template_id, Template.workspace_id == workspace_id))


def find_template(db: Session, workspace_id: int, name: str) -> Template | None:
    return db.scalar(select(Template).where(Template.workspace_id == workspace_id, Template.name == name))
