"""Labels, attachment downloads and the unread counts of the mail screens."""

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.email import Attachment, Label
from app.providers.gmail import GmailApiError, ReconnectRequired
from app.providers.mime import extract_attachments
from app.repositories import conversations as conv_repo
from app.repositories import email as email_repo
from app.services import email_accounts, mailbox_access
from app.services.auth import Identity


def _can_change(identity: Identity) -> None:
    if identity.role == "viewer":
        raise AppError(403, "FORBIDDEN", "Viewers can read mail but not change it.")


def create_label(db: Session, identity: Identity, name: str, color: str) -> Label:
    _can_change(identity)
    clean = " ".join(name.split())
    if conv_repo.find_label_by_name(db, identity.workspace.id, clean):
        raise AppError(409, "LABEL_EXISTS", f"There is already a label called {clean}.")
    label = conv_repo.add_label(db, Label(workspace_id=identity.workspace.id, name=clean, color=color))
    db.commit()
    return label


def update_label(db: Session, identity: Identity, label_id: int, name: str | None, color: str | None) -> Label:
    _can_change(identity)
    label = conv_repo.get_label(db, label_id, identity.workspace.id)
    if not label:
        raise AppError(404, "LABEL_NOT_FOUND", "Label not found.")
    if name is not None:
        clean = " ".join(name.split())
        other = conv_repo.find_label_by_name(db, identity.workspace.id, clean)
        if other and other.id != label.id:
            raise AppError(409, "LABEL_EXISTS", f"There is already a label called {clean}.")
        label.name = clean
    if color is not None:
        label.color = color
    db.commit()
    return label


def delete_label(db: Session, identity: Identity, label_id: int) -> None:
    _can_change(identity)
    label = conv_repo.get_label(db, label_id, identity.workspace.id)
    if not label:
        raise AppError(404, "LABEL_NOT_FOUND", "Label not found.")
    conv_repo.delete_label(db, label)
    db.commit()


def set_labels(db: Session, identity: Identity, conversation_id: int, label_ids: list[int]) -> None:
    _can_change(identity)
    if not conv_repo.get_conversation(db, conversation_id, identity.workspace.id, mailbox_access.allowed_account_ids(db, identity)):
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation not found.")
    for label_id in label_ids:
        if not conv_repo.get_label(db, label_id, identity.workspace.id):
            raise AppError(404, "LABEL_NOT_FOUND", "Label not found.")
    conv_repo.set_conversation_labels(db, conversation_id, label_ids)
    db.commit()


def original_attachments(db: Session, identity: Identity, message_id: int) -> list[tuple[str, str, bytes]]:
    """The attachments of a stored message, fetched from the mailbox it lives in."""
    message = conv_repo.get_message(db, message_id, identity.workspace.id)
    allowed = mailbox_access.allowed_account_ids(db, identity)
    if not message or (allowed is not None and message.email_account_id not in allowed):
        raise AppError(404, "MESSAGE_NOT_FOUND", "Message not found.")
    if not message.attachments:
        return []
    account = email_repo.get_account(db, message.email_account_id, identity.workspace.id)
    if not account or not message.provider_message_id:
        raise AppError(404, "ATTACHMENT_UNAVAILABLE", "This attachment is no longer available.")
    try:
        raw = email_accounts.get_provider_for_account(account).fetch_raw(message.provider_message_id)
        db.commit()  # keeps a renewed access token
    except ReconnectRequired as exc:
        raise AppError(409, "RECONNECT_REQUIRED", f"{account.email_address} needs to be reconnected before its attachments can be opened.") from exc
    except (GmailApiError, OSError) as exc:
        raise AppError(503, "MAILBOX_UNREACHABLE", "Could not reach the mailbox to get the attachment. Try again in a moment.") from exc
    except Exception as exc:  # noqa: BLE001 - IMAP libraries raise their own error types
        raise AppError(503, "MAILBOX_UNREACHABLE", "Could not reach the mailbox to get the attachment. Try again in a moment.") from exc
    if raw is None:
        raise AppError(404, "ATTACHMENT_UNAVAILABLE", "The original email is no longer in the mailbox, so its attachments cannot be opened.")
    return extract_attachments(raw)


def download_attachment(db: Session, identity: Identity, attachment_id: int) -> tuple[Attachment, bytes]:
    found = conv_repo.get_attachment(db, attachment_id, identity.workspace.id)
    if not found:
        raise AppError(404, "ATTACHMENT_NOT_FOUND", "Attachment not found.")
    attachment, message = found
    position = conv_repo.attachment_position(db, attachment)
    parts = original_attachments(db, identity, message.id)
    if position >= len(parts):
        raise AppError(404, "ATTACHMENT_UNAVAILABLE", "This attachment is no longer available.")
    return attachment, parts[position][2]
