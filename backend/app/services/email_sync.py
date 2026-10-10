import logging
import re
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.automation import engine
from app.models.email import Attachment, Conversation, EmailAccount, Message, MessageRecipient
from app.providers.gmail import GmailRateLimited, ReconnectRequired
from app.repositories import email as email_repo
from app.services import email_accounts

logger = logging.getLogger(__name__)


def _normalize_subject(subject: str) -> str:
    clean = re.sub(r"^((re|fwd|fw):\s*)+", "", subject or "", flags=re.IGNORECASE).strip()
    return clean or "(no subject)"


def _store_messages(db: Session, account: EmailAccount, workspace_id: int, raw_messages: list[dict[str, Any]], new_ids: list[int] | None = None) -> int:
    """Store messages that are not in the database yet, each in the right conversation. Returns how many were new."""
    stored = 0
    for item in raw_messages:
        p_msg_id = (item.get("provider_message_id") or "")[:255]
        if not p_msg_id:
            continue

        try:
            with db.begin_nested():
                # Check duplicate
                existing = db.scalar(
                    select(Message).where(Message.email_account_id == account.id, Message.provider_message_id == p_msg_id)
                )
                if existing:
                    continue

                # Conversation matching: the provider's own thread first, then In-Reply-To, then subject
                conversation = None
                thread_id = item.get("provider_thread_id")
                if thread_id:
                    conversation = db.scalar(
                        select(Conversation).where(
                            Conversation.email_account_id == account.id,
                            Conversation.provider_thread_id == thread_id,
                        )
                    )
                in_reply_to = item.get("in_reply_to")
                if not conversation and in_reply_to:
                    # Only within this mailbox: a reply must never be filed into another mailbox's
                    # conversation, where people without access to this one could read it.
                    prev_msg = db.scalar(
                        select(Message).where(
                            Message.workspace_id == workspace_id,
                            Message.email_account_id == account.id,
                            Message.provider_message_id == in_reply_to[:255],
                        ).limit(1)
                    )
                    if prev_msg:
                        conversation = db.get(Conversation, prev_msg.conversation_id)

                # A provider that reports threads decides them; subject matching would merge unrelated mail.
                if not conversation and not thread_id:
                    norm_subject = _normalize_subject(item.get("subject", ""))[:500]
                    sender = (item.get("sender_email") or "").lower()
                    # Same subject is not enough: the writer must already be part of that conversation
                    # (they wrote in it, or we wrote to them). Otherwise anyone could post into a
                    # stranger's thread by copying its subject.
                    if norm_subject and sender:
                        wrote_before = select(Message.id).where(Message.conversation_id == Conversation.id, Message.sender_email == sender)
                        was_written_to = (
                            select(MessageRecipient.id).join(Message, Message.id == MessageRecipient.message_id)
                            .where(Message.conversation_id == Conversation.id, MessageRecipient.email == sender)
                        )
                        conversation = db.scalar(
                            select(Conversation).where(
                                Conversation.workspace_id == workspace_id,
                                Conversation.email_account_id == account.id,
                                Conversation.subject == norm_subject,
                                wrote_before.exists() | was_written_to.exists(),
                            ).order_by(Conversation.last_message_at.desc()).limit(1)
                        )

                if not conversation:
                    conversation = Conversation(
                        workspace_id=workspace_id,
                        email_account_id=account.id,
                        provider_thread_id=thread_id,
                        # The conversation is named after its topic; each message keeps its own "Re:" subject.
                        subject=_normalize_subject(item.get("subject") or "")[:500],
                        snippet=item.get("snippet", ""),
                        is_read=bool(item.get("is_read", False)),
                        is_starred=bool(item.get("is_starred", False)),
                        is_archived=False,
                        is_deleted=False,
                        status="open",
                        last_message_at=item.get("sent_at", utcnow()),
                        last_sender_name=(item.get("sender_name") or "")[:255] or None,
                        last_sender_email=(item.get("sender_email") or "")[:320] or None,
                        message_count=0,
                    )
                    db.add(conversation)
                    db.flush()
                else:
                    sent_at = item.get("sent_at", utcnow())
                    if sent_at > conversation.last_message_at:
                        conversation.last_message_at = sent_at
                        conversation.snippet = item.get("snippet", "")
                        conversation.last_sender_name = (item.get("sender_name") or "")[:255] or None
                        conversation.last_sender_email = (item.get("sender_email") or "")[:320] or None
                        # New mail in a conversation the team had closed brings it back.
                        if conversation.status == "closed" and not item.get("is_read", False):
                            conversation.status = "open"
                    if not item.get("is_read", False):
                        conversation.is_read = False
                    if thread_id and not conversation.provider_thread_id:
                        conversation.provider_thread_id = thread_id

                # Create message
                msg = Message(
                    workspace_id=workspace_id,
                    conversation_id=conversation.id,
                    email_account_id=account.id,
                    provider_message_id=p_msg_id,
                    direction="inbound",
                    sender_name=(item.get("sender_name") or "")[:255],
                    sender_email=(item.get("sender_email") or "")[:320].lower(),
                    subject=(item.get("subject") or "")[:500],
                    body_text=item.get("body_text"),
                    body_html=item.get("body_html"),
                    in_reply_to=(item.get("in_reply_to") or "")[:500] or None,
                    message_references=item.get("references"),
                    # A sender's clock cannot put mail in the future, where it would sit on top for ever.
                    sent_at=min(item.get("sent_at", utcnow()), utcnow()),
                    is_read=bool(item.get("is_read", False)),
                    is_starred=bool(item.get("is_starred", False)),
                )
                db.add(msg)
                db.flush()
                conversation.message_count = (conversation.message_count or 0) + 1
                if new_ids is not None:
                    new_ids.append(msg.id)
                if item.get("attachments"):
                    conversation.has_attachments = True

                # Add recipients
                for r_name, r_email in item.get("to_recipients", []):
                    db.add(MessageRecipient(message_id=msg.id, kind="to", email=(r_email or "")[:320], name=(r_name or "")[:255] or None))
                for r_name, r_email in item.get("cc_recipients", []):
                    db.add(MessageRecipient(message_id=msg.id, kind="cc", email=(r_email or "")[:320], name=(r_name or "")[:255] or None))

                # Add attachments
                for att in item.get("attachments", []):
                    db.add(Attachment(
                        message_id=msg.id,
                        filename=(att["filename"] or "attachment")[:255],
                        content_type=(att["content_type"] or "application/octet-stream")[:128],
                        file_size=att["file_size"],
                    ))

                db.flush()
            stored += 1
        except Exception as msg_err:
            logger.warning("An email for account %s could not be stored: %s", account.id, type(msg_err).__name__)
            continue
    return stored


SYNC_FAILED = "The mailbox could not be synced. It will be tried again; if this keeps happening, reconnect the account."


def sync_account(db: Session, account_id: int, workspace_id: int, limit: int = 40) -> tuple[int, str | None]:
    """Sync recent messages from the email account into MySQL."""
    account = email_repo.get_account(db, account_id, workspace_id)
    if not account:
        return 0, "Account not found"

    account.status = "syncing"
    db.commit()

    synced_count = 0

    try:
        provider = email_accounts.get_provider_for_account(account)
        raw_messages = provider.fetch_messages(folder_name="INBOX", limit=limit)

        # Mail seen for the first time by a mailbox that has synced before is new mail: rules act on it.
        # A mailbox's very first sync, like the import of its history, is old mail and is left alone.
        arrived: list[int] | None = [] if account.last_sync_at else None
        synced_count = _store_messages(db, account, workspace_id, raw_messages, arrived)

        account.status = "connected"
        account.last_sync_at = utcnow()
        account.last_error = None
        # Providers that follow a change feed say where the next sync starts.
        next_cursor = getattr(provider, "next_cursor", None)
        if next_cursor:
            account.sync_cursor = next_cursor
        db.commit()
        if arrived:
            try:
                engine.run_for_messages(db, workspace_id, account.id, arrived)
            except Exception as rule_error:  # rules must never break mail arriving
                db.rollback()
                logger.warning("Rules could not run for account %s: %s", account.id, rule_error)
            try:
                from app.services import ai_triage

                ai_triage.enqueue_new_mail(db, workspace_id, account.id, arrived)
            except Exception as ai_error:  # nor must the AI queue
                db.rollback()
                logger.warning("New mail could not be queued for AI for account %s: %s", account.id, ai_error)
        return synced_count, None

    except ReconnectRequired:
        db.rollback()
        account = db.get(EmailAccount, account_id)
        message = "Google no longer accepts this connection. Reconnect the account to keep it in sync."
        if account:
            account.status = "needs_reconnect"
            account.last_error = message
            db.commit()
        return 0, message

    except GmailRateLimited:
        # Not a fault: Google's per-minute limit was reached. The next sync picks up from the same place.
        db.rollback()
        account = db.get(EmailAccount, account_id)
        if account:
            account.status = "connected"
            db.commit()
        _wait_before_import[account_id] = time.monotonic() + RATE_LIMIT_PAUSE
        return 0, None

    except Exception as exc:
        db.rollback()
        account = db.get(EmailAccount, account_id)
        if account:
            account.status = "error"
            # The exception's own text can hold server replies or SQL with its values; people see a plain sentence.
            account.last_error = SYNC_FAILED
            db.commit()
        logger.warning("Sync failed for account %s: %s", account_id, type(exc).__name__)
        return 0, SYNC_FAILED


def sync_account_task(account_id: int, workspace_id: int, limit: int = 40) -> tuple[int, str | None]:
    """Helper to run sync_account with its own DB session for background tasks."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        return sync_account(db, account_id, workspace_id, limit=limit)
    finally:
        db.close()


def sync_all_active_accounts(limit_per_account: int = 30) -> list[dict[str, Any]]:
    """Periodic worker: Finds all connected accounts, recovers stale syncing, and syncs messages."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    results = []
    try:
        # Recover accounts stuck in syncing state
        stale_syncing = db.scalars(
            select(EmailAccount).where(EmailAccount.status == "syncing")
        ).all()
        for s in stale_syncing:
            s.status = "connected"
        if stale_syncing:
            db.commit()

        accounts = db.scalars(
            select(EmailAccount).where(EmailAccount.status.in_(["connected", "error"]))
        ).all()

        for acc in accounts:
            try:
                count, err = sync_account(db, acc.id, acc.workspace_id, limit=limit_per_account)
                results.append({"account_id": acc.id, "synced": count, "error": err})
                if count > 0:
                    logger.info("Background sync: synced %d messages for account %s", count, acc.email_address)
            except Exception as e:
                logger.error("Error syncing account %s (%s): %s", acc.id, acc.email_address, e)
                results.append({"account_id": acc.id, "synced": 0, "error": str(e)})
    finally:
        db.close()
    return results



IMPORT_PAGE_SIZE = 50
# Seconds between two pages of one mailbox, and how long to stand back after Google says to slow down.
IMPORT_PAGE_PAUSE = 20
RATE_LIMIT_PAUSE = 75
# Per mailbox: the moment its next page may be fetched. In memory; a restart simply starts without waiting.
_wait_before_import: dict[int, float] = {}


def import_history_page(db: Session, account: EmailAccount) -> int:
    """Bring in the next page of mail that was already in the mailbox, oldest pages last.

    The position is saved in the same transaction as the page, so a restart
    continues where it stopped and never skips or repeats a page.
    """
    provider = email_accounts.get_provider_for_account(account)
    if not hasattr(provider, "fetch_page"):
        account.import_state = "done"  # this kind of mailbox has no paged import yet
        db.commit()
        return 0

    try:
        if account.import_total is None:
            account.import_total = provider.label_total("INBOX")
        messages, next_token = provider.fetch_page("INBOX", account.import_page_token, IMPORT_PAGE_SIZE)
        stored = _store_messages(db, account, account.workspace_id, messages)
        account.import_page_token = next_token
        account.import_state = "running" if next_token else "done"
        db.commit()
        _wait_before_import[account.id] = time.monotonic() + IMPORT_PAGE_PAUSE
        return stored
    except GmailRateLimited:
        db.rollback()
        _wait_before_import[account.id] = time.monotonic() + RATE_LIMIT_PAUSE
        return 0
    except ReconnectRequired:
        db.rollback()
        account = db.get(EmailAccount, account.id)
        if account:
            account.status = "needs_reconnect"
            account.last_error = "Google no longer accepts this connection. Reconnect the account to keep it in sync."
            db.commit()
        return 0


def import_pending_history() -> bool:
    """Background worker: one page for every mailbox whose older mail is not all in yet. True if there is more to do."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    more = False
    try:
        accounts = db.scalars(
            select(EmailAccount).where(
                EmailAccount.auth_type == "oauth",
                EmailAccount.import_state != "done",
                EmailAccount.status != "needs_reconnect",
            )
        ).all()
        for account in accounts:
            if _wait_before_import.get(account.id, 0) > time.monotonic():
                more = True  # pacing itself, or standing back after a rate limit
                continue
            try:
                import_history_page(db, account)
                db.refresh(account)
                more = more or account.import_state != "done"
            except Exception as exc:  # one mailbox failing must not stop the others
                db.rollback()
                logger.warning("Import of older mail failed for account %s: %s", account.id, exc)
    finally:
        db.close()
    return more
