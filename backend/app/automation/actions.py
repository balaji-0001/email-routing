"""What a rule can do to a conversation. Each action returns one plain sentence saying what happened.

Actions only ever change this workspace's own records. None of them sends email or calls a provider.
"""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.automation import Rule
from app.models.collab import Notification
from app.models.email import Conversation, ConversationLabel, EmailAccount, Label
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.services import mailbox_access
from app.services.auth import Identity


class Skipped(Exception):
    """The action could not sensibly be done; the reason is recorded and the rule carries on."""


def _member(db: Session, workspace_id: int, user_id: int) -> tuple[User, str]:
    row = db.execute(
        select(User, WorkspaceMember.role).join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id, User.id == user_id)
    ).first()
    if not row:
        raise Skipped("the person is no longer in the workspace")
    return row[0], row[1]


def _can_use_mailbox(db: Session, conversation: Conversation, user: User, role: str) -> bool:
    account = db.get(EmailAccount, conversation.email_account_id)
    workspace = type("W", (), {"id": conversation.workspace_id})()
    person = Identity(user=user, session=None, workspace=workspace, role=role)  # type: ignore[arg-type]
    return account is not None and mailbox_access.permission(db, person, account) is not None


def _notify(db: Session, conversation: Conversation, user_id: int, kind: str, title: str) -> None:
    db.add(Notification(workspace_id=conversation.workspace_id, user_id=user_id, actor_user_id=None, kind=kind, title=title[:255], body=conversation.subject[:500], conversation_id=conversation.id))


def add_label(db: Session, rule: Rule, conversation: Conversation, action: dict) -> str:
    label = db.scalar(select(Label).where(Label.id == action["label_id"], Label.workspace_id == conversation.workspace_id))
    if not label:
        raise Skipped("the label no longer exists")
    if not db.get(ConversationLabel, (conversation.id, label.id)):
        db.add(ConversationLabel(conversation_id=conversation.id, label_id=label.id))
    return f"Added the label {label.name}"


def set_priority(db: Session, rule: Rule, conversation: Conversation, action: dict) -> str:
    conversation.priority = action["value"]
    return f"Set priority to {action['value']}"


def set_status(db: Session, rule: Rule, conversation: Conversation, action: dict) -> str:
    conversation.status = action["value"]
    return f"Set status to {action['value']}"


def _assign_to(db: Session, rule: Rule, conversation: Conversation, user_id: int) -> str:
    user, role = _member(db, conversation.workspace_id, user_id)
    if not _can_use_mailbox(db, conversation, user, role):
        raise Skipped(f"{user.name} cannot use this mailbox")
    if conversation.assignee_user_id != user.id:
        conversation.assignee_user_id = user.id
        _notify(db, conversation, user.id, "assigned", f"The rule “{rule.name}” assigned you a conversation")
    return f"Assigned to {user.name}"


def assign(db: Session, rule: Rule, conversation: Conversation, action: dict) -> str:
    return _assign_to(db, rule, conversation, action["user_id"])


def assign_in_turn(db: Session, rule: Rule, conversation: Conversation, action: dict) -> str:
    """Share conversations out among the chosen people, one after another, passing over anyone who cannot take it."""
    people = action["user_ids"]
    start = rule.run_count % len(people)
    for offset in range(len(people)):
        try:
            return _assign_to(db, rule, conversation, people[(start + offset) % len(people)])
        except Skipped:
            continue
    raise Skipped("none of the chosen people can use this mailbox")


def flag(db: Session, rule: Rule, conversation: Conversation, action: dict) -> str:
    conversation.is_starred = True
    return "Flagged it"


def archive(db: Session, rule: Rule, conversation: Conversation, action: dict) -> str:
    conversation.is_archived = True
    return "Archived it"


def notify(db: Session, rule: Rule, conversation: Conversation, action: dict) -> str:
    user, role = _member(db, conversation.workspace_id, action["user_id"])
    if not _can_use_mailbox(db, conversation, user, role):
        raise Skipped(f"{user.name} cannot use this mailbox")
    _notify(db, conversation, user.id, "rule", f"The rule “{rule.name}” matched a new email")
    return f"Notified {user.name}"


ACTIONS: dict[str, Callable[[Session, Rule, Conversation, dict], str]] = {
    "add_label": add_label,
    "set_priority": set_priority,
    "set_status": set_status,
    "assign": assign,
    "assign_in_turn": assign_in_turn,
    "flag": flag,
    "archive": archive,
    "notify": notify,
}
