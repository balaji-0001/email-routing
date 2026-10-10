from typing import Any

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.email import Attachment, Conversation, ConversationLabel, EmailAccount, Label, Message


def list_conversations(
    db: Session,
    workspace_id: int,
    *,
    view: str = "inbox",
    account_id: int | None = None,
    search: str | None = None,
    unread: bool | None = None,
    starred: bool | None = None,
    has_attachments: bool | None = None,
    status: str | None = None,
    label_id: int | None = None,
    account_ids: list[int] | None = None,
    assignee_user_id: int | None = None,
    unassigned: bool = False,
    priority: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[Conversation, EmailAccount]], int]:
    stmt = (
        select(Conversation, EmailAccount)
        .join(EmailAccount, EmailAccount.id == Conversation.email_account_id)
        .where(Conversation.workspace_id == workspace_id)
    )

    if account_id:
        stmt = stmt.where(Conversation.email_account_id == account_id)
    if account_ids is not None:
        stmt = stmt.where(Conversation.email_account_id.in_(account_ids))

    # View filtering
    if view == "inbox":
        # Mail that came in; a conversation that only holds mail sent from here belongs to Sent Items.
        received = exists().where(Message.conversation_id == Conversation.id, Message.direction == "inbound")
        stmt = stmt.where(Conversation.is_archived.is_(False), Conversation.is_deleted.is_(False), received)
    elif view == "starred":
        stmt = stmt.where(Conversation.is_starred.is_(True), Conversation.is_deleted.is_(False))
    elif view == "archive":
        stmt = stmt.where(Conversation.is_archived.is_(True), Conversation.is_deleted.is_(False))
    elif view == "trash":
        stmt = stmt.where(Conversation.is_deleted.is_(True))
    elif view == "sent":
        # Any conversation with outbound messages
        has_outbound = (
            select(Message.conversation_id)
            .where(Message.direction == "outbound", Message.workspace_id == workspace_id)
            .distinct()
            .subquery()
        )
        stmt = stmt.join(has_outbound, has_outbound.c.conversation_id == Conversation.id).where(
            Conversation.is_deleted.is_(False)
        )
    elif view == "all":
        stmt = stmt.where(Conversation.is_deleted.is_(False))

    if unread is not None:
        stmt = stmt.where(Conversation.is_read.is_(not unread))
    if starred is not None:
        stmt = stmt.where(Conversation.is_starred.is_(starred))
    if has_attachments is not None:
        stmt = stmt.where(Conversation.has_attachments.is_(has_attachments))
    if status:
        stmt = stmt.where(Conversation.status == status)
    if assignee_user_id is not None:
        stmt = stmt.where(Conversation.assignee_user_id == assignee_user_id)
    if priority:
        stmt = stmt.where(Conversation.priority == priority)
    if unassigned:
        stmt = stmt.where(Conversation.assignee_user_id.is_(None))
    if label_id:
        stmt = stmt.where(
            exists().where(ConversationLabel.conversation_id == Conversation.id, ConversationLabel.label_id == label_id)
        )

    if search and search.strip():
        term = f"%{search.strip()}%"
        in_a_message = exists().where(
            Message.conversation_id == Conversation.id,
            or_(Message.sender_email.ilike(term), Message.sender_name.ilike(term), Message.subject.ilike(term), Message.body_text.ilike(term)),
        )
        stmt = stmt.where(
            or_(
                Conversation.subject.ilike(term),
                Conversation.snippet.ilike(term),
                Conversation.last_sender_name.ilike(term),
                Conversation.last_sender_email.ilike(term),
                in_a_message,
            )
        )

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    # Paged query
    paged_stmt = stmt.order_by(Conversation.last_message_at.desc(), Conversation.id.desc()).offset(offset).limit(limit)
    rows = db.execute(paged_stmt)
    return [(conv, acc) for conv, acc in rows], total


def get_conversation(db: Session, conversation_id: int, workspace_id: int, account_ids: list[int] | None = None) -> tuple[Conversation, EmailAccount] | None:
    row = db.execute(
        select(Conversation, EmailAccount)
        .join(EmailAccount, EmailAccount.id == Conversation.email_account_id)
        .where(Conversation.id == conversation_id, Conversation.workspace_id == workspace_id)
    ).first()
    if not row or (account_ids is not None and row[0].email_account_id not in account_ids):
        return None
    return (row[0], row[1])


def get_messages_for_conversation(db: Session, conversation_id: int, workspace_id: int) -> list[Message]:
    stmt = (
        select(Message)
        .options(selectinload(Message.recipients), selectinload(Message.attachments))
        .where(Message.conversation_id == conversation_id, Message.workspace_id == workspace_id)
        .order_by(Message.sent_at.asc())
    )
    return list(db.scalars(stmt).all())


def get_message(db: Session, message_id: int, workspace_id: int) -> Message | None:
    return db.scalar(
        select(Message).options(selectinload(Message.attachments)).where(Message.id == message_id, Message.workspace_id == workspace_id)
    )


def get_message_by_provider_id(db: Session, workspace_id: int, provider_message_id: str, account_id: int) -> Message | None:
    """A message by its own id, within one mailbox. Never across mailboxes: they have different readers."""
    return db.scalar(
        select(Message).where(Message.workspace_id == workspace_id, Message.email_account_id == account_id, Message.provider_message_id == provider_message_id).limit(1)
    )


def get_attachment(db: Session, attachment_id: int, workspace_id: int) -> tuple[Attachment, Message] | None:
    row = db.execute(
        select(Attachment, Message)
        .join(Message, Message.id == Attachment.message_id)
        .where(Attachment.id == attachment_id, Message.workspace_id == workspace_id)
    ).first()
    return (row[0], row[1]) if row else None


def attachment_position(db: Session, attachment: Attachment) -> int:
    """Which of its message's attachments this is, counting from 0 in the order they were recorded."""
    return int(db.scalar(select(func.count()).where(Attachment.message_id == attachment.message_id, Attachment.id < attachment.id)) or 0)


def update_conversation(db: Session, conversation: Conversation, changes: dict[str, Any]) -> Conversation:
    for k, v in changes.items():
        if hasattr(conversation, k):
            setattr(conversation, k, v)
    db.flush()
    return conversation


def batch_update_conversations(db: Session, workspace_id: int, conversation_ids: list[int], action: str, account_ids: list[int] | None = None) -> int:
    convs = list(
        db.scalars(
            select(Conversation).where(
                Conversation.id.in_(conversation_ids),
                Conversation.workspace_id == workspace_id,
            )
        ).all()
    )
    if account_ids is not None:
        convs = [conv for conv in convs if conv.email_account_id in account_ids]

    for conv in convs:
        if action == "mark_read":
            conv.is_read = True
        elif action == "mark_unread":
            conv.is_read = False
        elif action == "star":
            conv.is_starred = True
        elif action == "unstar":
            conv.is_starred = False
        elif action == "archive":
            conv.is_archived = True
        elif action == "unarchive":
            conv.is_archived = False
        elif action == "delete":
            conv.is_deleted = True
        elif action == "restore":
            conv.is_deleted = False
        elif action in ("status_open", "status_pending", "status_closed"):
            conv.status = action.removeprefix("status_")
        elif action in ("priority_low", "priority_normal", "priority_high", "priority_urgent"):
            conv.priority = action.removeprefix("priority_")

    db.flush()
    return len(convs)


def count_messages(db: Session, workspace_id: int, account_ids: list[int] | None) -> int:
    stmt = select(func.count()).select_from(Message).where(Message.workspace_id == workspace_id)
    if account_ids is not None:
        stmt = stmt.where(Message.email_account_id.in_(account_ids))
    return int(db.scalar(stmt) or 0)


def inbox_unread_by_account(db: Session, workspace_id: int, account_ids: list[int] | None = None) -> dict[int, int]:
    rows = db.execute(
        select(Conversation.email_account_id, func.count())
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.is_read.is_(False),
            Conversation.is_archived.is_(False),
            Conversation.is_deleted.is_(False),
        )
        .group_by(Conversation.email_account_id)
    )
    return {int(account_id): int(count) for account_id, count in rows if account_ids is None or account_id in account_ids}


# --- labels ---------------------------------------------------------------------

def list_labels(db: Session, workspace_id: int) -> list[tuple[Label, int]]:
    counts = select(ConversationLabel.label_id, func.count().label("cnt")).group_by(ConversationLabel.label_id).subquery()
    rows = db.execute(
        select(Label, func.coalesce(counts.c.cnt, 0))
        .outerjoin(counts, counts.c.label_id == Label.id)
        .where(Label.workspace_id == workspace_id)
        .order_by(Label.name)
    )
    return [(label, int(count)) for label, count in rows]


def get_label(db: Session, label_id: int, workspace_id: int) -> Label | None:
    return db.scalar(select(Label).where(Label.id == label_id, Label.workspace_id == workspace_id))


def find_label_by_name(db: Session, workspace_id: int, name: str) -> Label | None:
    return db.scalar(select(Label).where(Label.workspace_id == workspace_id, Label.name == name))


def add_label(db: Session, label: Label) -> Label:
    db.add(label)
    db.flush()
    return label


def delete_label(db: Session, label: Label) -> None:
    db.delete(label)
    db.flush()


def labels_for_conversations(db: Session, conversation_ids: list[int]) -> dict[int, list[Label]]:
    if not conversation_ids:
        return {}
    rows = db.execute(
        select(ConversationLabel.conversation_id, Label)
        .join(Label, Label.id == ConversationLabel.label_id)
        .where(ConversationLabel.conversation_id.in_(conversation_ids))
        .order_by(Label.name)
    )
    found: dict[int, list[Label]] = {}
    for conversation_id, label in rows:
        found.setdefault(int(conversation_id), []).append(label)
    return found


def set_conversation_labels(db: Session, conversation_id: int, label_ids: list[int]) -> None:
    db.execute(delete(ConversationLabel).where(ConversationLabel.conversation_id == conversation_id))
    for label_id in dict.fromkeys(label_ids):
        db.add(ConversationLabel(conversation_id=conversation_id, label_id=label_id))
    db.flush()
