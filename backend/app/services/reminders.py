"""Follow-up reminders: a person asks to be told about a conversation at a set time."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import AppError
from app.models.automation import Reminder
from app.models.collab import Notification
from app.models.email import Conversation, EmailAccount, Message
from app.services import mailbox_access
from app.services.auth import Identity

MAX_AHEAD = timedelta(days=366)


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


def _view(db: Session, reminder: Reminder) -> dict:
    conversation = db.get(Conversation, reminder.conversation_id)
    account = db.get(EmailAccount, conversation.email_account_id)
    return {
        "id": reminder.id, "conversation_id": reminder.conversation_id, "subject": conversation.subject or "(no subject)", "account_email": account.email_address,
        "due_at": reminder.due_at, "note": reminder.note or "", "only_if_no_reply": reminder.only_if_no_reply, "status": reminder.status,
        "created_at": reminder.created_at, "finished_at": reminder.finished_at,
    }


def _conversation(db: Session, identity: Identity, conversation_id: int) -> Conversation:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.workspace_id == identity.workspace.id))
    allowed = mailbox_access.allowed_account_ids(db, identity)
    if not conversation or (allowed is not None and conversation.email_account_id not in allowed):
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation not found.")
    return conversation


def create(db: Session, identity: Identity, conversation_id: int, due_at: datetime, note: str, only_if_no_reply: bool) -> dict:
    conversation = _conversation(db, identity, conversation_id)
    due = _naive_utc(due_at)
    if due <= utcnow():
        raise AppError(422, "VALIDATION_ERROR", "Choose a time in the future.")
    if due > utcnow() + MAX_AHEAD:
        raise AppError(422, "VALIDATION_ERROR", "A reminder can be set up to a year ahead.")
    # One waiting reminder per person per conversation: setting a new one replaces the old.
    for old in db.scalars(select(Reminder).where(Reminder.user_id == identity.user.id, Reminder.conversation_id == conversation.id, Reminder.status == "waiting")):
        old.status, old.finished_at = "cancelled", utcnow()
    reminder = Reminder(workspace_id=identity.workspace.id, user_id=identity.user.id, conversation_id=conversation.id, due_at=due, note=note.strip() or None, only_if_no_reply=only_if_no_reply, status="waiting")
    db.add(reminder)
    db.commit()
    return _view(db, reminder)


def mine(db: Session, identity: Identity, conversation_id: int | None = None) -> list[dict]:
    """The caller's reminders: waiting ones first by time, then the most recent finished ones."""
    allowed = mailbox_access.allowed_account_ids(db, identity)
    stmt = select(Reminder).join(Conversation, Conversation.id == Reminder.conversation_id).where(Reminder.workspace_id == identity.workspace.id, Reminder.user_id == identity.user.id)
    if allowed is not None:
        stmt = stmt.where(Conversation.email_account_id.in_(allowed))
    if conversation_id is not None:
        stmt = stmt.where(Reminder.conversation_id == conversation_id, Reminder.status == "waiting")
    rows = list(db.scalars(stmt.order_by(Reminder.id.desc()).limit(200)))
    waiting = sorted((r for r in rows if r.status == "waiting"), key=lambda r: r.due_at)
    return [_view(db, r) for r in [*waiting, *[r for r in rows if r.status != "waiting"][:30]]]


def cancel(db: Session, identity: Identity, reminder_id: int) -> None:
    reminder = db.scalar(select(Reminder).where(Reminder.id == reminder_id, Reminder.workspace_id == identity.workspace.id, Reminder.user_id == identity.user.id))
    if not reminder:
        raise AppError(404, "REMINDER_NOT_FOUND", "Reminder not found.")
    if reminder.status == "waiting":
        reminder.status, reminder.finished_at = "cancelled", utcnow()
        db.commit()


def fire_due(db: Session) -> int:
    """Tell people about the reminders that have come due. Each fires once."""
    due = db.scalars(select(Reminder).where(Reminder.status == "waiting", Reminder.due_at <= utcnow()).order_by(Reminder.due_at).limit(100)).all()
    fired = 0
    for reminder in due:
        conversation = db.get(Conversation, reminder.conversation_id)
        answered = reminder.only_if_no_reply and db.scalar(
            select(Message.id).where(Message.conversation_id == reminder.conversation_id, Message.direction == "inbound", Message.sent_at > reminder.created_at).limit(1))
        if answered:
            reminder.status = "answered"  # they wrote back, so there is nothing to chase
        else:
            reminder.status = "done"
            db.add(Notification(workspace_id=reminder.workspace_id, user_id=reminder.user_id, actor_user_id=None, kind="reminder",
                                title=f"Follow up: {conversation.subject or '(no subject)'}"[:255], body=reminder.note or ("No reply has come in." if reminder.only_if_no_reply else None), conversation_id=reminder.conversation_id))
            fired += 1
        reminder.finished_at = utcnow()
        db.commit()
    return fired
