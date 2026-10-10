"""AI triage of new mail, and the approval queue for the replies it drafts.

Draft-only: the AI never sends. A reply goes out only when a person who may send from that
mailbox approves the exact text, and then only once.
"""

import hashlib
import logging
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai import gemini, triage
from app.ai.base import AIError
from app.core.config import get_settings
from app.core.database import utcnow
from app.core.errors import AppError
from app.models.ai import AiAccountSetting, AiAnalysis, AiReply, AiSetting
from app.models.email import Conversation, EmailAccount, Message
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.repositories import email as email_repo
from app.services import audit, email_send, mailbox_access
from app.services.accounts import MANAGERS
from app.services.auth import Client, Identity

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_AFTER = (timedelta(minutes=1), timedelta(minutes=5))
STUCK_AFTER = timedelta(minutes=10)
# Replies are drafted only for recent mail: nobody wants a queue of answers to last month's email.
DRAFT_WITHIN = timedelta(days=14)
# Automatic replies: only to mail that has just arrived, short, and never in a loop with another machine.
AUTO_WITHIN = timedelta(hours=24)
AUTO_MAX_LENGTH = 1200
AUTO_PER_PERSON = 3
AUTOMATED = ("noreply", "no-reply", "no_reply", "donotreply", "do-not-reply", "mailer-daemon", "notification", "newsletter", "postmaster", "bounce")


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- settings ---------------------------------------------------------------------------------------

def _setting(db: Session, workspace_id: int) -> AiSetting | None:
    return db.get(AiSetting, workspace_id)


def is_on(db: Session, workspace_id: int, account_id: int) -> bool:
    """AI runs for a mailbox only if it is set up, switched on, not stopped, and not switched off for that mailbox."""
    setting = _setting(db, workspace_id)
    if not get_settings().ai_configured or not setting or not setting.enabled or setting.paused:
        return False
    account = db.get(AiAccountSetting, account_id)
    return account.enabled if account else True


def get_settings_view(db: Session, identity: Identity) -> dict:
    workspace_id = identity.workspace.id
    setting = _setting(db, workspace_id)
    rows = db.scalars(select(AiAccountSetting).where(AiAccountSetting.workspace_id == workspace_id)).all()
    per_account = {row.email_account_id: row.enabled for row in rows}
    per_auto = {row.email_account_id: row.auto_send for row in rows}
    allowed = mailbox_access.allowed_account_ids(db, identity)
    config = get_settings()
    return {
        "configured": config.ai_configured, "model": config.ai_model,
        "enabled": bool(setting and setting.enabled), "paused": bool(setting and setting.paused),
        "business_info": ((setting.business_info if setting else None) or "") if identity.role in MANAGERS else "",
        "has_business_info": bool(setting and (setting.business_info or "").strip()),
        "mailboxes": [{"account_id": a.id, "email_address": a.email_address, "enabled": per_account.get(a.id, True), "auto_send": per_auto.get(a.id, True)}
                      for a, _n in email_repo.list_accounts(db, workspace_id) if allowed is None or a.id in allowed],
        "auto_send_low": bool(setting and setting.auto_send_low), "auto_send_medium": bool(setting and setting.auto_send_medium),
        "daily_limit": setting.daily_limit if setting else 20, "auto_sent_today": _auto_sent_since(db, workspace_id, utcnow() - timedelta(hours=24)),
    }


def update_settings(db: Session, identity: Identity, enabled: bool | None, paused: bool | None, business_info: str | None, mailboxes: dict[int, bool], client: Client,
                    auto_send_low: bool | None = None, auto_send_medium: bool | None = None, daily_limit: int | None = None, mailbox_auto_send: dict[int, bool] | None = None) -> dict:
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only owners and admins can change AI settings.")
    workspace_id = identity.workspace.id
    setting = _setting(db, workspace_id)
    if not setting:
        setting = AiSetting(workspace_id=workspace_id, enabled=False, paused=False, auto_send_low=False, auto_send_medium=False, daily_limit=20)
        db.add(setting)

    def note(summary: str) -> None:
        audit.record(db, action="ai.settings", summary=summary, actor=identity.user, workspace_id=workspace_id, ip=client.ip)

    if enabled is not None and enabled != setting.enabled:
        if enabled and not get_settings().ai_configured:
            raise AppError(409, "AI_NOT_SET_UP", "AI is not set up on the server yet. Add GEMINI_API_KEY to the .env file and restart.")
        setting.enabled = enabled
        note(f"Switched AI assistance {'on' if enabled else 'off'}")
    if paused is not None and paused != setting.paused:
        setting.paused = paused
        note("Stopped all AI activity (emergency stop)" if paused else "Let AI activity resume")
    if business_info is not None and business_info.strip() != (setting.business_info or ""):
        setting.business_info = business_info.strip() or None
        note("Changed the business information the AI may use")
    if not setting.enabled:
        # Switching AI off takes automatic sending with it, so turning AI back on never resumes sending by surprise.
        if setting.auto_send_low or setting.auto_send_medium:
            setting.auto_send_low = setting.auto_send_medium = False
            note("Automatic sending switched off along with AI assistance")
        if auto_send_low or auto_send_medium:
            raise AppError(409, "AI_OFF", "Switch AI assistance on before automatic sending.")
    if auto_send_low is not None and auto_send_low != setting.auto_send_low:
        setting.auto_send_low = auto_send_low
        note(f"Switched automatic sending of Low-priority replies {'on' if auto_send_low else 'off'}")
    if auto_send_medium is not None and auto_send_medium != setting.auto_send_medium:
        if auto_send_medium and not (setting.business_info or "").strip():
            raise AppError(409, "NO_BUSINESS_INFO", "Add business information first: Medium replies are sent automatically only when they can be checked against it.")
        setting.auto_send_medium = auto_send_medium
        note(f"Switched automatic sending of Medium-priority replies {'on' if auto_send_medium else 'off'}")
    if setting.auto_send_medium and not (setting.business_info or "").strip():
        setting.auto_send_medium = False
        note("Automatic sending of Medium-priority replies switched off because the business information was removed")
    if daily_limit is not None and daily_limit != setting.daily_limit:
        setting.daily_limit = daily_limit
        note(f"Set the daily limit for automatic replies to {daily_limit}")
    own = {a.id: a.email_address for a, _n in email_repo.list_accounts(db, workspace_id)}

    def account_row(account_id: int) -> AiAccountSetting:
        if account_id not in own:
            raise AppError(404, "ACCOUNT_NOT_FOUND", "That mailbox is not in this workspace.")
        row = db.get(AiAccountSetting, account_id)
        if not row:
            row = AiAccountSetting(email_account_id=account_id, workspace_id=workspace_id, enabled=True, auto_send=True)
            db.add(row)
        return row

    for account_id, on in mailboxes.items():
        account_row(account_id).enabled = on
        note(f"Switched AI {'on' if on else 'off'} for {own[account_id]}")
    for account_id, on in (mailbox_auto_send or {}).items():
        account_row(account_id).auto_send = on
        note(f"Switched automatic sending {'on' if on else 'off'} for {own[account_id]}")
    db.commit()
    return get_settings_view(db, identity)


# ---- the queue of emails to analyse ---------------------------------------------------------------------

def _queue(db: Session, message: Message) -> AiAnalysis | None:
    """Add one email to the queue. Returns None if it is already there: an email is analysed once."""
    row = AiAnalysis(workspace_id=message.workspace_id, email_account_id=message.email_account_id, conversation_id=message.conversation_id, message_id=message.id, status="pending", attempts=0)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return None
    return row


def enqueue_new_mail(db: Session, workspace_id: int, account_id: int, message_ids: list[int]) -> int:
    """Called when a sync stores newly arrived mail."""
    if not message_ids or not is_on(db, workspace_id, account_id):
        return 0
    messages = db.scalars(select(Message).where(Message.id.in_(message_ids), Message.workspace_id == workspace_id, Message.direction == "inbound")).all()
    added = sum(1 for message in messages if _queue(db, message))
    db.commit()
    return added


def _ai_budget(identity: Identity) -> None:
    """Each request here is a paid call to the AI service, so one person cannot fire them without limit."""
    from app.core.rate_limit import limiter

    key = f"ai:{identity.user.id}"
    limiter.check(key, limit=30, window_seconds=60)
    limiter.record(key, window_seconds=60)


def analyse_now(db: Session, identity: Identity, conversation_id: int) -> dict:
    """A person asks for the latest email of a conversation to be analysed."""
    conversation, account = _conversation(db, identity, conversation_id)
    if identity.role == "viewer":
        raise AppError(403, "FORBIDDEN", "Viewers cannot ask for an analysis.")
    setting = _setting(db, identity.workspace.id)
    if not get_settings().ai_configured:
        raise AppError(409, "AI_NOT_SET_UP", "AI is not set up on the server yet.")
    if not setting or not setting.enabled:
        raise AppError(409, "AI_OFF", "AI assistance is switched off for this workspace.")
    if setting.paused:
        raise AppError(409, "AI_STOPPED", "AI activity has been stopped. An owner or admin can let it resume in Settings.")
    per_account = db.get(AiAccountSetting, account.id)
    if per_account and not per_account.enabled:
        raise AppError(409, "AI_OFF", f"AI is switched off for {account.email_address}, so its mail is not sent to the AI.")
    _ai_budget(identity)
    message = db.scalar(select(Message).where(Message.conversation_id == conversation.id, Message.direction == "inbound").order_by(Message.sent_at.desc(), Message.id.desc()).limit(1))
    if not message:
        raise AppError(409, "NOTHING_TO_ANALYSE", "This conversation has no received email to analyse.")
    existing = db.scalar(select(AiAnalysis).where(AiAnalysis.message_id == message.id))
    if existing and existing.status in ("gave_up", "skipped"):
        existing.status, existing.attempts, existing.error, existing.next_attempt_at = "pending", 0, None, None
    elif not existing:
        # Someone else may have queued it in the same instant; then theirs is the one to use.
        existing = _queue(db, message) or db.scalar(select(AiAnalysis).where(AiAnalysis.message_id == message.id))
    db.commit()
    _work_on(db, existing.id, by_hand=True)
    return _analysis_view(db, db.get(AiAnalysis, existing.id), account.email_address)


def _thread(db: Session, analysis: AiAnalysis, message: Message) -> list[dict]:
    earlier = db.scalars(
        select(Message).where(Message.conversation_id == analysis.conversation_id, Message.sent_at <= message.sent_at, Message.id != message.id)
        .order_by(Message.sent_at.desc(), Message.id.desc()).limit(triage.THREAD - 1)
    ).all()
    return [
        {"who": f"{m.sender_name or ''} <{m.sender_email}>".strip(), "when": m.sent_at.strftime("%Y-%m-%d %H:%M UTC"), "subject": m.subject or "", "body": m.body_text or ""}
        for m in [*reversed(earlier), message]
    ]


def _is_automated(message: Message, account: EmailAccount) -> bool:
    from app.services.email import is_app_mail

    return is_app_mail(message.sender_email, message.subject) or message.sender_email.lower() == account.email_address.lower() or any(word in message.sender_email.lower().split("@")[0] for word in AUTOMATED)


def _signature(db: Session, account: EmailAccount) -> str:
    """The name replies are signed with: the mailbox's display name if someone chose one, else the workspace owner's name.

    A display name that is just the first part of the address was filled in automatically and is not a name.
    """
    chosen = (account.display_name or "").strip()
    if chosen and chosen.lower() != account.email_address.split("@")[0].lower():
        return chosen
    owner = db.scalar(select(User).join(WorkspaceMember, WorkspaceMember.user_id == User.id).where(WorkspaceMember.workspace_id == account.workspace_id, WorkspaceMember.role == "owner").limit(1))
    return (owner.name if owner else "") or account.email_address


def analyse_recent(db: Session, identity: Identity, per_mailbox: int, client: Client) -> dict:
    """Queue the latest emails already in each mailbox for analysis. Asked for by an owner or admin."""
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only owners and admins can analyse mail that is already here.")
    workspace_id = identity.workspace.id
    setting = _setting(db, workspace_id)
    if not get_settings().ai_configured:
        raise AppError(409, "AI_NOT_SET_UP", "AI is not set up on the server yet.")
    if not setting or not setting.enabled:
        raise AppError(409, "AI_OFF", "Switch AI assistance on first.")
    if setting.paused:
        raise AppError(409, "AI_STOPPED", "AI activity has been stopped. Let it resume first.")
    looked = queued = automated = 0
    for account, _n in email_repo.list_accounts(db, workspace_id):
        if not is_on(db, workspace_id, account.id):
            continue
        messages = db.scalars(
            select(Message).where(Message.workspace_id == workspace_id, Message.email_account_id == account.id, Message.direction == "inbound")
            .order_by(Message.sent_at.desc(), Message.id.desc()).limit(per_mailbox)
        ).all()
        looked += len(messages)
        for message in messages:
            if _is_automated(message, account):
                automated += 1  # never sent to the AI, so not worth a place in the queue
            elif _queue(db, message):
                queued += 1
    audit.record(db, action="ai.analyse_recent", summary=f"Asked the AI to analyse the latest {per_mailbox} emails in each mailbox", actor=identity.user, workspace_id=workspace_id, ip=client.ip)
    db.commit()
    return {"looked_at": looked, "queued": queued, "automated": automated, "already_done": looked - queued - automated}


def _fail(analysis: AiAnalysis, error: str, retry: bool) -> None:
    analysis.error = error[:500]
    if not retry or analysis.attempts >= MAX_ATTEMPTS:
        analysis.status, analysis.next_attempt_at, analysis.finished_at = "gave_up", None, utcnow()
    else:
        analysis.status, analysis.next_attempt_at = "failed", utcnow() + RETRY_AFTER[min(analysis.attempts - 1, len(RETRY_AFTER) - 1)]


def _work_on(db: Session, analysis_id: int, by_hand: bool = False) -> bool:
    """Analyse one queued email. Only one worker can claim a row, so two never analyse or draft for the same email."""
    claimed = db.execute(
        update(AiAnalysis).where(AiAnalysis.id == analysis_id, AiAnalysis.status.in_(("pending", "failed")))
        .values(status="working", started_at=utcnow(), attempts=AiAnalysis.attempts + 1)
    ).rowcount
    db.commit()
    if claimed != 1:
        return False
    analysis = db.get(AiAnalysis, analysis_id)
    db.refresh(analysis)
    message = db.get(Message, analysis.message_id)
    account = db.get(EmailAccount, analysis.email_account_id)
    setting = _setting(db, analysis.workspace_id)
    to_send: int | None = None
    try:
        if not by_hand and not is_on(db, analysis.workspace_id, analysis.email_account_id):
            analysis.status, analysis.reason, analysis.finished_at = "skipped", "AI was switched off or stopped before this email was reached.", utcnow()
        elif not by_hand and _is_automated(message, account):
            # Automated senders are not read by the AI at all: nobody is there to answer.
            analysis.status, analysis.reply_required, analysis.reason, analysis.finished_at = "skipped", False, "Automated sender, so no reply is needed. Not sent to the AI.", utcnow()
        else:
            provider = gemini.provider_from_settings()
            if provider is None:
                raise AIError("AI is not set up on the server.", retry=False)
            result = triage.analyse(provider, mailbox=account.email_address, business_info=setting.business_info if setting else None,
                                    thread=_thread(db, analysis, message), signature=_signature(db, account))
            analysis.summary, analysis.intent, analysis.requested_actions = result.summary, result.intent, result.requested_actions
            analysis.reply_required, analysis.priority, analysis.confidence, analysis.grounded = result.reply_required, result.priority, result.confidence, result.grounded
            analysis.risk_flags, analysis.reason, analysis.hold_reasons = result.risk_flags, result.reason, triage.hold_reasons(result)
            analysis.model, analysis.error, analysis.next_attempt_at = provider.name, None, None
            analysis.status, analysis.finished_at = "done", utcnow()
            recent = message.sent_at >= utcnow() - DRAFT_WITHIN
            if result.reply_required and result.suggested_reply.strip() and (recent or by_hand) and not db.scalar(select(AiReply.id).where(AiReply.analysis_id == analysis.id)):
                conversation = db.get(Conversation, analysis.conversation_id)
                subject = conversation.subject or message.subject or ""
                body = result.suggested_reply.strip()
                drafted = AiReply(
                    workspace_id=analysis.workspace_id, email_account_id=analysis.email_account_id, conversation_id=analysis.conversation_id, analysis_id=analysis.id,
                    message_id=message.id, to_email=message.sender_email, subject=subject if subject.lower().startswith("re:") else f"Re: {subject}"[:500],
                    body=body, body_hash=fingerprint(body), status="pending",
                )
                db.add(drafted)
                db.flush()
                to_send = drafted.id
    except AIError as exc:
        _fail(analysis, str(exc), exc.retry)
    except Exception as exc:  # noqa: BLE001 - whatever went wrong is recorded, and mail carries on
        logger.warning("AI analysis %s failed: %s", analysis_id, exc)
        db.rollback()
        analysis = db.get(AiAnalysis, analysis_id)
        _fail(analysis, "Something went wrong while analysing this email.", True)
    db.commit()
    if to_send is not None:
        _send_automatically_if_allowed(db, to_send, by_hand)
    done = db.get(AiAnalysis, analysis_id)
    if done and done.status == "done" and not by_hand:
        try:
            from app.automation import engine

            engine.run_after_analysis(db, done.workspace_id, done.email_account_id, done.message_id, done.priority)
        except Exception as exc:  # noqa: BLE001 - rules must never undo an analysis
            db.rollback()
            logger.warning("Rules could not run after analysis %s: %s", analysis_id, exc)
    return True


def process_pending(db: Session, limit: int = 5) -> int:
    """Work through the queue. Called by the background loop; safe to run from several places at once."""
    now = utcnow()
    # A worker that died mid-way leaves its row 'working'; give those back to the queue.
    db.execute(update(AiAnalysis).where(AiAnalysis.status == "working", AiAnalysis.started_at < now - STUCK_AFTER).values(status="failed", next_attempt_at=now, error="The analysis was interrupted."))
    # A send that was interrupted is not retried by itself (it may have gone out); a person decides.
    db.execute(update(AiReply).where(AiReply.status == "sending", AiReply.decided_at < now - STUCK_AFTER).values(
        status="failed", auto_sent=False, error="Sending was interrupted. Check the mailbox's Sent folder before approving this again."))
    db.commit()
    due = db.scalars(
        select(AiAnalysis.id).where((AiAnalysis.status == "pending") | ((AiAnalysis.status == "failed") & (AiAnalysis.next_attempt_at <= now))).order_by(AiAnalysis.id).limit(limit)
    ).all()
    return sum(1 for analysis_id in due if _work_on(db, analysis_id))


def process_pending_task() -> int:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return process_pending(db)
    finally:
        db.close()


# ---- reading results ----------------------------------------------------------------------------------

def _allowed(db: Session, identity: Identity) -> list[int] | None:
    return mailbox_access.allowed_account_ids(db, identity)


def _conversation(db: Session, identity: Identity, conversation_id: int) -> tuple[Conversation, EmailAccount]:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.workspace_id == identity.workspace.id))
    allowed = _allowed(db, identity)
    if not conversation or (allowed is not None and conversation.email_account_id not in allowed):
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation not found.")
    return conversation, db.get(EmailAccount, conversation.email_account_id)


def _analysis_view(db: Session, analysis: AiAnalysis, account_email: str | None = None) -> dict:
    message = db.get(Message, analysis.message_id)
    reply = db.execute(select(AiReply.id, AiReply.status).where(AiReply.analysis_id == analysis.id)).first()
    return {
        "id": analysis.id, "conversation_id": analysis.conversation_id, "message_id": analysis.message_id,
        "account_email": account_email or db.get(EmailAccount, analysis.email_account_id).email_address,
        "subject": message.subject or "(no subject)", "sender": message.sender_name or message.sender_email,
        "status": analysis.status, "attempts": analysis.attempts, "summary": analysis.summary, "intent": analysis.intent,
        "requested_actions": analysis.requested_actions or [], "reply_required": analysis.reply_required, "priority": analysis.priority,
        "confidence": analysis.confidence, "grounded": analysis.grounded, "risk_flags": analysis.risk_flags or [], "hold_reasons": analysis.hold_reasons or [],
        "reason": analysis.reason, "error": analysis.error, "reply_id": reply[0] if reply else None, "reply_status": reply[1] if reply else None,
        "created_at": analysis.created_at, "finished_at": analysis.finished_at,
    }


def for_conversation(db: Session, identity: Identity, conversation_id: int) -> dict | None:
    conversation, account = _conversation(db, identity, conversation_id)
    analysis = db.scalar(select(AiAnalysis).where(AiAnalysis.conversation_id == conversation.id).order_by(AiAnalysis.id.desc()).limit(1))
    return _analysis_view(db, analysis, account.email_address) if analysis else None


def activity(db: Session, identity: Identity, limit: int) -> list[dict]:
    stmt = select(AiAnalysis).where(AiAnalysis.workspace_id == identity.workspace.id).order_by(AiAnalysis.id.desc()).limit(limit)
    allowed = _allowed(db, identity)
    if allowed is not None:
        stmt = stmt.where(AiAnalysis.email_account_id.in_(allowed))
    return [_analysis_view(db, analysis) for analysis in db.scalars(stmt)]


def status(db: Session, identity: Identity) -> dict:
    workspace_id = identity.workspace.id
    allowed = _allowed(db, identity)
    since = utcnow() - timedelta(hours=24)

    def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model).where(model.workspace_id == workspace_id, *where)
        if allowed is not None:
            stmt = stmt.where(model.email_account_id.in_(allowed))
        return int(db.scalar(stmt) or 0)

    view = get_settings_view(db, identity)
    return {
        "configured": view["configured"], "enabled": view["enabled"], "paused": view["paused"],
        "waiting_for_approval": count(AiReply, AiReply.status.in_(("pending", "failed"))),
        "waiting_for_analysis": count(AiAnalysis, AiAnalysis.status.in_(("pending", "working", "failed"))),
        "working_now": count(AiAnalysis, AiAnalysis.status.in_(("pending", "working"))),
        "auto_sent_today": _auto_sent_since(db, workspace_id, since) if allowed is None else count(AiReply, AiReply.auto_sent.is_(True), AiReply.status == "sent", AiReply.sent_at >= since),
        "analysed_today": count(AiAnalysis, AiAnalysis.status == "done", AiAnalysis.finished_at >= since),
        "failed_today": count(AiAnalysis, AiAnalysis.status == "gave_up", AiAnalysis.finished_at >= since),
        "sent_today": count(AiReply, AiReply.status == "sent", AiReply.sent_at >= since),
    }


# ---- writing help ---------------------------------------------------------------------------------------

def write_with_ai(db: Session, identity: Identity, instruction: str, current: str, conversation_id: int | None) -> dict:
    """A person asks the AI to write or rewrite an email. The text goes back to them and nowhere else."""
    from app.ai import writer

    if identity.role == "viewer":
        raise AppError(403, "FORBIDDEN", "Viewers cannot write email.")
    setting = _setting(db, identity.workspace.id)
    if not get_settings().ai_configured:
        raise AppError(409, "AI_NOT_SET_UP", "AI is not set up on the server yet.")
    if not setting or not setting.enabled:
        raise AppError(409, "AI_OFF", "AI assistance is switched off. An owner or admin can switch it on in Settings > AI controls.")
    if setting.paused:
        raise AppError(409, "AI_STOPPED", "AI activity has been stopped. An owner or admin can let it resume in Settings.")
    _ai_budget(identity)
    thread: list[dict] = []
    if conversation_id is not None:
        conversation, account = _conversation(db, identity, conversation_id)
        per_account = db.get(AiAccountSetting, account.id)
        if per_account and not per_account.enabled:
            raise AppError(409, "AI_OFF", f"AI is switched off for {account.email_address}, so its mail is not sent to the AI.")
        recent = db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.sent_at.desc(), Message.id.desc()).limit(triage.THREAD)).all()
        thread = [{"who": f"{m.sender_name or ''} <{m.sender_email}>".strip(), "when": m.sent_at.strftime("%Y-%m-%d %H:%M UTC"), "subject": m.subject or "", "body": m.body_text or ""} for m in reversed(recent)]
    provider = gemini.provider_from_settings()
    try:
        result = writer.write_email(provider, instruction=instruction, current=current, thread=thread, business_info=setting.business_info, signature=identity.user.name, replying=conversation_id is not None)
    except AIError as exc:
        raise AppError(502, "AI_UNAVAILABLE", f"{exc} Nothing was changed; try again in a moment.") from exc
    return {"subject": result.subject, "body": result.body}


# ---- automatic sending -----------------------------------------------------------------------------------

def _auto_sent_since(db: Session, workspace_id: int, since, *where) -> int:
    """Automatic replies sent or being sent. Ones in flight count, so the limit cannot be slipped past."""
    return int(db.scalar(select(func.count()).select_from(AiReply).where(
        AiReply.workspace_id == workspace_id, AiReply.auto_sent.is_(True), AiReply.status.in_(("sending", "sent")), AiReply.decided_at >= since, *where)) or 0)


def auto_send_blockers(db: Session, reply: AiReply, by_hand: bool) -> list[str]:
    """Every reason this draft may not go out by itself. An empty list is the only thing that lets it.

    The priority chooses which switch applies; it never clears a reply on its own.
    """
    setting = _setting(db, reply.workspace_id)
    analysis = db.get(AiAnalysis, reply.analysis_id)
    message = db.get(Message, reply.message_id)
    account = db.get(EmailAccount, reply.email_account_id)
    per_account = db.get(AiAccountSetting, reply.email_account_id)
    if analysis.priority == "high":
        return ["High priority always needs approval"]
    if not setting or not get_settings().ai_configured or not setting.enabled or setting.paused:
        return ["AI is off or stopped"]
    if not (setting.auto_send_low if analysis.priority == "low" else setting.auto_send_medium):
        return [f"Automatic sending is off for {analysis.priority.capitalize()} priority"]
    if per_account and not per_account.auto_send:
        return ["Automatic sending is off for this mailbox"]
    if by_hand:
        return ["Analysed on request, so it waits for approval"]

    why = list(analysis.hold_reasons or [])
    if analysis.risk_flags:
        why += [f"Risk: {triage.RISK_WORDS.get(flag, flag)}" for flag in analysis.risk_flags if f"Risk: {triage.RISK_WORDS.get(flag, flag)}" not in why and flag != "unverified_claim"]
    if not analysis.grounded and not any("could not be checked" in reason for reason in why):
        why.append("The reply could not be checked against the thread or your business information")
    if analysis.priority == "medium" and not (setting.business_info or "").strip():
        why.append("There is no business information to check a Medium reply against")
    if reply.edited:
        why.append("The draft was edited")
    if message.sent_at < utcnow() - AUTO_WITHIN:
        why.append("The email is more than a day old")
    if len(reply.body) > AUTO_MAX_LENGTH:
        why.append("The reply is long")
    if account.status != "connected":
        why.append("The mailbox needs reconnecting")
    if _is_automated(message, account):
        why.append("The sender looks automated")
    if db.scalar(select(Message.id).where(Message.conversation_id == reply.conversation_id, Message.direction == "outbound", Message.sent_at > message.sent_at).limit(1)):
        why.append("Someone has already replied in this conversation")
    day = utcnow() - timedelta(hours=24)
    # Two machines answering each other must not run away: one automatic reply per conversation a day, a few per person.
    if _auto_sent_since(db, reply.workspace_id, day, AiReply.conversation_id == reply.conversation_id, AiReply.id != reply.id):
        why.append("An automatic reply was already sent in this conversation today")
    if _auto_sent_since(db, reply.workspace_id, day, AiReply.to_email == reply.to_email, AiReply.id != reply.id) >= AUTO_PER_PERSON:
        why.append(f"This person has already had {AUTO_PER_PERSON} automatic replies today")
    if _auto_sent_since(db, reply.workspace_id, day, AiReply.id != reply.id) >= setting.daily_limit:
        why.append(f"The daily limit of {setting.daily_limit} automatic replies has been reached")
    return why


def _send_automatically_if_allowed(db: Session, reply_id: int, by_hand: bool) -> None:
    reply = db.get(AiReply, reply_id)
    blockers = auto_send_blockers(db, reply, by_hand)
    if blockers:
        reply.auto_note = blockers
        db.commit()
        return
    # Claim it exactly as an approval would: whoever moves it from waiting to sending is the only one who sends.
    claimed = db.execute(
        update(AiReply).where(AiReply.id == reply.id, AiReply.status == "pending", AiReply.body_hash == reply.body_hash)
        .values(status="sending", auto_sent=True, approved_hash=reply.body_hash, decided_at=utcnow(), error=None)
    ).rowcount
    db.commit()
    if claimed != 1:
        return
    db.refresh(reply)
    source = db.get(Message, reply.message_id)
    try:
        sent = email_send.send_message(
            db, None, system_workspace=db.get(Workspace, reply.workspace_id), account_id=reply.email_account_id, to=[reply.to_email], subject=reply.subject,
            body_text=reply.body, conversation_id=reply.conversation_id, in_reply_to=source.provider_message_id, client=Client(ip=None, user_agent=None),
        )
    except email_send.SentButNotRecorded as exc:
        db.rollback()
        reply = db.get(AiReply, reply_id)
        reply.status, reply.provider_message_id, reply.sent_at, reply.error = "sent", exc.provider_message_id, utcnow(), exc.message[:500]
        db.commit()
        return
    except Exception as exc:  # noqa: BLE001 - a failed automatic send is handed to a person, never retried blindly
        db.rollback()
        reply = db.get(AiReply, reply_id)
        reply.status, reply.auto_sent, reply.error = "failed", False, (exc.message if isinstance(exc, AppError) else "The automatic send failed.")[:500]
        reply.auto_note = ["It was cleared to send automatically, but sending failed. It was not tried again, in case the first attempt got through."]
        audit.record(db, action="ai.auto_send_failed", summary=f"An automatic AI reply to {reply.to_email} could not be sent", actor=None, workspace_id=reply.workspace_id, ip=None)
        db.commit()
        return
    reply = db.get(AiReply, reply_id)
    reply.status, reply.provider_message_id, reply.sent_message_id, reply.sent_at = "sent", sent.provider_message_id, sent.id, utcnow()
    db.commit()


# ---- the approval queue -------------------------------------------------------------------------------

def _reply_view(db: Session, identity: Identity, reply: AiReply) -> dict:
    account = db.get(EmailAccount, reply.email_account_id)
    decider = db.get(User, reply.decided_by_user_id) if reply.decided_by_user_id else None
    return {
        "id": reply.id, "conversation_id": reply.conversation_id, "account_email": account.email_address, "to_email": reply.to_email, "subject": reply.subject,
        "body": reply.body, "body_hash": reply.body_hash, "edited": reply.edited, "status": reply.status, "error": reply.error,
        "auto_sent": reply.auto_sent, "auto_note": reply.auto_note or [],
        "decided_by_name": decider.name if decider else None, "provider_message_id": reply.provider_message_id,
        "created_at": reply.created_at, "decided_at": reply.decided_at, "sent_at": reply.sent_at,
        "can_send": identity.role != "viewer" and mailbox_access.permission(db, identity, account) == "send",
        "analysis": _analysis_view(db, db.get(AiAnalysis, reply.analysis_id), account.email_address),
    }


def list_replies(db: Session, identity: Identity, which: str, limit: int) -> list[dict]:
    statuses = {"waiting": ("pending", "failed", "sending"), "sent": ("sent",), "rejected": ("rejected",)}[which]
    stmt = select(AiReply).where(AiReply.workspace_id == identity.workspace.id, AiReply.status.in_(statuses)).order_by(AiReply.id.desc()).limit(limit)
    allowed = _allowed(db, identity)
    if allowed is not None:
        stmt = stmt.where(AiReply.email_account_id.in_(allowed))
    return [_reply_view(db, identity, reply) for reply in db.scalars(stmt)]


def _reply(db: Session, identity: Identity, reply_id: int) -> AiReply:
    reply = db.scalar(select(AiReply).where(AiReply.id == reply_id, AiReply.workspace_id == identity.workspace.id))
    allowed = _allowed(db, identity)
    if not reply or (allowed is not None and reply.email_account_id not in allowed):
        raise AppError(404, "DRAFT_NOT_FOUND", "Draft not found.")
    return reply


def _may_decide(db: Session, identity: Identity, reply: AiReply) -> None:
    if identity.role == "viewer":
        raise AppError(403, "FORBIDDEN", "Viewers can read drafts but not change or send them.")
    mailbox_access.require_send(db, identity, db.get(EmailAccount, reply.email_account_id))
    if reply.status not in ("pending", "failed"):
        raise AppError(409, "DRAFT_CLOSED", {"sent": "This reply has already been sent.", "rejected": "This draft was rejected.", "sending": "This reply is already being sent."}.get(reply.status, "This draft can no longer be changed."))


def edit_reply(db: Session, identity: Identity, reply_id: int, body: str) -> dict:
    reply = _reply(db, identity, reply_id)
    _may_decide(db, identity, reply)
    body = body.strip()
    if fingerprint(body) != reply.body_hash:
        # New text means a new fingerprint: an approval given for the old text no longer matches anything.
        reply.body, reply.body_hash, reply.edited, reply.approved_hash, reply.error = body, fingerprint(body), True, None, None
        reply.status = "pending"
    db.commit()
    return _reply_view(db, identity, reply)


def reject_reply(db: Session, identity: Identity, reply_id: int, client: Client) -> dict:
    reply = _reply(db, identity, reply_id)
    _may_decide(db, identity, reply)
    reply.status, reply.decided_by_user_id, reply.decided_at, reply.approved_hash = "rejected", identity.user.id, utcnow(), None
    audit.record(db, action="ai.reply_rejected", summary=f"Rejected the AI draft to {reply.to_email}", actor=identity.user, workspace_id=identity.workspace.id, ip=client.ip)
    db.commit()
    return _reply_view(db, identity, reply)


def approve_and_send(db: Session, identity: Identity, reply_id: int, body_hash: str, client: Client) -> dict:
    reply = _reply(db, identity, reply_id)
    _may_decide(db, identity, reply)
    if body_hash != reply.body_hash:
        raise AppError(409, "DRAFT_CHANGED", "This draft changed after you opened it. Read the current text and approve again.")

    # The reply must still belong where it was drafted: same mailbox, same thread, same person.
    source = db.get(Message, reply.message_id)
    conversation = db.get(Conversation, reply.conversation_id)
    if not source or not conversation or source.conversation_id != conversation.id or conversation.email_account_id != reply.email_account_id or source.sender_email.lower() != reply.to_email.lower():
        raise AppError(409, "DRAFT_MISMATCH", "This draft no longer matches its conversation, so it was not sent. Reject it and write a reply by hand.")
    if db.scalar(select(Message.id).where(Message.conversation_id == conversation.id, Message.direction == "outbound", Message.sent_at > source.sent_at).limit(1)):
        raise AppError(409, "ALREADY_ANSWERED", "Someone has already replied in this conversation since the draft was written. Reject the draft if it is no longer needed.")

    # Only one request can take the draft from waiting to sending, so it cannot go out twice.
    claimed = db.execute(
        update(AiReply).where(AiReply.id == reply.id, AiReply.status.in_(("pending", "failed")), AiReply.body_hash == body_hash)
        .values(status="sending", approved_hash=body_hash, decided_by_user_id=identity.user.id, decided_at=utcnow(), error=None)
    ).rowcount
    db.commit()
    if claimed != 1:
        raise AppError(409, "DRAFT_CLOSED", "This reply is already being sent or was changed.")
    db.refresh(reply)
    try:
        sent = email_send.send_message(
            db, identity, account_id=reply.email_account_id, to=[reply.to_email], subject=reply.subject, body_text=reply.body,
            conversation_id=conversation.id, in_reply_to=source.provider_message_id, client=client,
        )
    except email_send.SentButNotRecorded as exc:
        db.rollback()
        reply = db.get(AiReply, reply_id)
        reply.status, reply.provider_message_id, reply.sent_at, reply.error = "sent", exc.provider_message_id, utcnow(), exc.message[:500]
        db.commit()
        raise
    except Exception as exc:  # noqa: BLE001 - whatever happened, the draft must not be left "sending" for ever
        db.rollback()
        reply = db.get(AiReply, reply_id)
        reply.status, reply.error = "failed", (exc.message if isinstance(exc, AppError) else "Something went wrong while sending. Nothing was sent.")[:500]
        audit.record(db, action="ai.reply_failed", summary=f"An approved AI draft to {reply.to_email} could not be sent", actor=identity.user, workspace_id=identity.workspace.id, ip=client.ip)
        db.commit()
        raise
    # Only now, with the provider's own id for the message, is it called sent.
    reply = db.get(AiReply, reply_id)
    reply.status, reply.provider_message_id, reply.sent_message_id, reply.sent_at = "sent", sent.provider_message_id, sent.id, utcnow()
    audit.record(db, action="ai.reply_sent", summary=f"Approved and sent an AI draft to {reply.to_email}", actor=identity.user, workspace_id=identity.workspace.id, ip=client.ip)
    db.commit()
    return _reply_view(db, identity, reply)
