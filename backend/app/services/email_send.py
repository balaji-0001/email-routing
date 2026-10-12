import base64
import binascii

import logging
import re
from email.utils import parseaddr

from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.core.errors import AppError
from app.models.email import Attachment, Conversation, Message, MessageRecipient
from app.providers.gmail import ReconnectRequired
from app.repositories import conversations as conv_repo
from app.repositories import email as email_repo
from app.schemas.conversations import AttachmentIn
from app.services import audit, email_accounts, mail, mailbox_access
from app.models.workspace import Workspace
from app.services.auth import Client, Identity

# Providers refuse messages much above this once attachments are encoded for sending.
MAX_ATTACHMENT_BYTES = 18 * 1024 * 1024


logger = logging.getLogger(__name__)
MAX_RECIPIENTS = 100
_ADDRESS = re.compile(r"^[^@\s<>,;:\"'()\[\]\\]+@[A-Za-z0-9.-]+\.[A-Za-z0-9-]{2,}$")


class SentButNotRecorded(AppError):
    """The provider accepted the email, but this app could not save its copy. It must not be sent again."""

    def __init__(self, provider_message_id: str | None):
        super().__init__(500, "SENT_NOT_RECORDED", "The email was sent, but it could not be saved here. Do not send it again; it will be in the mailbox's own Sent folder.")
        self.provider_message_id = provider_message_id


def _addresses(values: list[str], field: str) -> list[str]:
    """Plain, valid email addresses only. A name, a line break or a second address hidden in one entry is refused."""
    clean = []
    for value in values:
        value = (value or "").strip()
        if not value:
            continue
        address = parseaddr(value)[1] if "<" in value else value
        if len(address) > 320 or not _ADDRESS.match(address):
            raise AppError(422, "VALIDATION_ERROR", f"“{value[:80]}” in {field} is not a valid email address.")
        clean.append(address.lower())
    return list(dict.fromkeys(clean))


def _decode(attachments: list[AttachmentIn]) -> list[tuple[str, str, bytes]]:
    decoded = []
    for item in attachments:
        try:
            decoded.append((item.filename, item.content_type or "application/octet-stream", base64.b64decode(item.content_base64, validate=True)))
        except (binascii.Error, ValueError) as exc:
            raise AppError(422, "VALIDATION_ERROR", f"The file {item.filename} could not be read. Attach it again.") from exc
    return decoded


def send_message(
    db: Session,
    identity: Identity | None,
    *,
    account_id: int,
    to: list[str],
    subject: str,
    body_text: str | None = None,
    body_html: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    conversation_id: int | None = None,
    in_reply_to: str | None = None,
    attachments: list[AttachmentIn] | None = None,
    forward_attachments_of: int | None = None,
    client: Client,
    system_workspace: Workspace | None = None,
) -> Message:
    # With no person (`identity` is None) the workspace itself is sending: an automatic reply
    # that has already passed its own checks. Only the AI service calls it that way.
    workspace = identity.workspace if identity else system_workspace
    assert workspace is not None
    if identity and identity.role == "viewer":
        raise AppError(403, "FORBIDDEN", "Viewers can read mail but not send it.")

    # Everything is checked before the email leaves: a failure after sending cannot be undone.
    to, cc, bcc = _addresses(to, "To"), _addresses(cc or [], "Cc"), _addresses(bcc or [], "Bcc")
    if not to:
        raise AppError(422, "VALIDATION_ERROR", "Add at least one recipient.")
    if len(to) + len(cc) + len(bcc) > MAX_RECIPIENTS:
        raise AppError(422, "VALIDATION_ERROR", f"An email can go to at most {MAX_RECIPIENTS} addresses.")
    subject = " ".join((subject or "").split())
    if len(subject) > 500:
        raise AppError(422, "VALIDATION_ERROR", "The subject is too long. Keep it under 500 characters.")

    account = email_repo.get_account(db, account_id, workspace.id)
    if not account:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "Sending email account not found.")
    if identity:
        mailbox_access.require_send(db, identity, account)

    files = _decode(attachments or [])
    if forward_attachments_of:
        files = mail.original_attachments(db, identity, forward_attachments_of) + files
    if sum(len(content) for _, _, content in files) > MAX_ATTACHMENT_BYTES:
        raise AppError(413, "ATTACHMENTS_TOO_LARGE", "The attachments are too large to send. Keep them under 18 MB in total.")

    conversation = None
    if conversation_id:
        allowed = mailbox_access.allowed_account_ids(db, identity) if identity else None
        found = conv_repo.get_conversation(db, conversation_id, workspace.id, allowed)
        conversation = found[0] if found else None
        # It must be a conversation of the mailbox being sent from, and one the sender may open.
        if conversation is None or conversation.email_account_id != account.id:
            raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation not found.")

    # A reply carries the chain of Message-IDs before it, which is what keeps the thread together everywhere.
    references = None
    if in_reply_to:
        original = conv_repo.get_message_by_provider_id(db, workspace.id, in_reply_to, account.id)
        earlier = (original.message_references or "").split() if original else []
        references = " ".join([*earlier, in_reply_to])

    try:
        provider = email_accounts.get_provider_for_account(account)
        provider_msg_id = provider.send_message(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            in_reply_to=in_reply_to,
            references=references,
            attachments=files or None,
            thread_id=conversation.provider_thread_id if conversation and in_reply_to else None,
        )
    except ReconnectRequired as exc:
        db.rollback()
        account.status = "needs_reconnect"
        account.last_error = "Google no longer accepts this connection. Reconnect the account to keep it in sync."
        db.commit()
        raise AppError(409, "RECONNECT_REQUIRED", f"{account.email_address} needs to be reconnected before it can send.") from exc
    except Exception as exc:
        logger.warning("Sending from account %s failed: %s", account.id, type(exc).__name__)
        raise AppError(503, "SEND_FAILED", f"{account.email_address} could not send the email. Nothing was sent; check the account's connection and try again.") from exc

    # From here on the email has been accepted by the provider. If saving our record of it fails,
    # that must never look like a failed send: the caller would send it again.
    try:
        sender_name = account.display_name or (identity.user.name if identity else account.email_address)
        snippet = (body_text or body_html or "")[:200].replace("\n", " ").strip()
        if conversation:
            conversation.last_message_at = utcnow()
            conversation.snippet = snippet
            conversation.is_read = True
            conversation.last_sender_name = sender_name
            conversation.last_sender_email = account.email_address
        else:
            conversation = Conversation(
                workspace_id=workspace.id,
                email_account_id=account.id,
                subject=subject or "(no subject)",
                snippet=snippet,
                is_read=True,
                is_starred=False,
                is_archived=False,
                is_deleted=False,
                status="open",
                last_message_at=utcnow(),
                last_sender_name=sender_name,
                last_sender_email=account.email_address,
                message_count=0,
            )
            db.add(conversation)
            db.flush()
        conversation.message_count = (conversation.message_count or 0) + 1
        if files:
            conversation.has_attachments = True

        msg = Message(
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            email_account_id=account.id,
            provider_message_id=provider_msg_id,
            direction="outbound",
            sender_name=sender_name,
            sender_email=account.email_address,
            subject=subject or "",
            body_text=body_text,
            body_html=body_html,
            in_reply_to=in_reply_to,
            message_references=references,
            sent_at=utcnow(),
            is_read=True,
            is_starred=False,
        )
        db.add(msg)
        db.flush()

        for addr in to:
            db.add(MessageRecipient(message_id=msg.id, kind="to", email=addr.strip().lower()))
        for addr in (cc or []):
            db.add(MessageRecipient(message_id=msg.id, kind="cc", email=addr.strip().lower()))
        for addr in (bcc or []):
            db.add(MessageRecipient(message_id=msg.id, kind="bcc", email=addr.strip().lower()))
        for filename, content_type, content in files:
            db.add(Attachment(message_id=msg.id, filename=filename[:255], content_type=content_type[:128], file_size=len(content)))

        audit.record(
            db,
            action="message.sent",
            summary=f"Sent email '{subject}' to {', '.join(to)}" if identity else f"The AI automatically sent '{subject}' to {', '.join(to)}",
            actor=identity.user if identity else None,
            workspace_id=workspace.id,
            ip=client.ip,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("An email sent from account %s could not be saved: %s", account.id, type(exc).__name__)
        raise SentButNotRecorded(provider_msg_id) from exc
    db.refresh(msg)
    return msg
