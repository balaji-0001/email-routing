"""Runs rules on new mail.

A rule runs at most once per email: `rule_runs` has one row per rule and email,
and that row is written in the same transaction as the rule's changes. If a run
fails, nothing it did is kept, the failure is recorded, and it is tried again
later, three times in all.
"""

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.automation.actions import ACTIONS, Skipped
from app.automation.conditions import Mail, matches
from app.core.database import utcnow
from app.models.automation import AutomationSetting, Rule, RuleRun
from app.models.email import Conversation, Message

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_AFTER = (timedelta(minutes=1), timedelta(minutes=5))


def is_on(db: Session, workspace_id: int, account_id: int) -> bool:
    """Automation runs only if it is on for the workspace and not switched off for this mailbox.

    The workspace switch starts off: nothing is automatic until someone turns it on.
    """
    rows = dict(db.execute(
        select(AutomationSetting.level, AutomationSetting.enabled).where(
            AutomationSetting.workspace_id == workspace_id,
            ((AutomationSetting.level == "organization") & (AutomationSetting.level_id == workspace_id))
            | ((AutomationSetting.level == "email_account") & (AutomationSetting.level_id == account_id)),
        )
    ).all())
    return bool(rows.get("organization", False)) and bool(rows.get("email_account", True))


def mail_from(message: Message, ai_priority: str | None = None) -> Mail:
    return Mail(
        ai_priority=ai_priority,
        account_id=message.email_account_id,
        sender=f"{message.sender_name or ''} {message.sender_email}",
        recipients=" ".join(f"{r.name or ''} {r.email}" for r in message.recipients),
        subject=message.subject or "",
        body=message.body_text or "",
        has_attachments=bool(message.attachments),
    )


def _apply(db: Session, rule: Rule, message: Message, run: RuleRun, quiet: bool = False) -> None:
    """Do the rule's actions inside a savepoint: either all of what it did is kept with its record, or none."""
    conversation = db.get(Conversation, message.conversation_id)
    did: list[str] = []
    run.attempts += 1
    try:
        with db.begin_nested():
            for action in rule.actions:
                handler = ACTIONS.get(action.get("type"))
                if handler is None:
                    did.append(f"Skipped an unknown action ({action.get('type')})")
                    continue
                if quiet and action.get("type") == "notify":
                    did.append("Skipped: nobody is notified about older mail")
                    continue
                try:
                    did.append(handler(db, rule, conversation, action))
                except Skipped as reason:
                    did.append(f"Skipped: {reason}")
            db.flush()
        run.status, run.done, run.error, run.next_attempt_at, run.finished_at = "done", did, None, None, utcnow()
        rule.run_count += 1
        rule.last_run_at = run.finished_at
    except Exception as exc:  # noqa: BLE001 - whatever went wrong is recorded and retried
        logger.warning("Rule %s failed on message %s: %s", rule.id, message.id, exc)
        run.done, run.error = [], str(exc)[:500]
        if run.attempts >= MAX_ATTEMPTS:
            run.status, run.next_attempt_at, run.finished_at = "gave_up", None, utcnow()
        else:
            run.status, run.next_attempt_at = "failed", utcnow() + RETRY_AFTER[min(run.attempts - 1, len(RETRY_AFTER) - 1)]


def _ai_priority(db: Session, message_id: int) -> str | None:
    from app.models.ai import AiAnalysis

    return db.scalar(select(AiAnalysis.priority).where(AiAnalysis.message_id == message_id, AiAnalysis.status == "done"))


def _load(db: Session, workspace_id: int, message_ids: list[int]) -> list[Message]:
    from app.services.email import is_app_mail

    return [message for message in db.scalars(
        select(Message).options(selectinload(Message.recipients), selectinload(Message.attachments))
        .where(Message.id.in_(message_ids), Message.workspace_id == workspace_id, Message.direction == "inbound").order_by(Message.sent_at, Message.id)
    ) if not is_app_mail(message.sender_email, message.subject)]


def _run(db: Session, rule: Rule, message: Message, quiet: bool = False) -> bool:
    """Record that this rule is handling this email, then do it. False if it already has: a rule runs once per email."""
    run = RuleRun(workspace_id=rule.workspace_id, rule_id=rule.id, message_id=message.id, conversation_id=message.conversation_id, status="failed", attempts=0, done=[])
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        return False
    _apply(db, rule, message, run, quiet=quiet)
    db.commit()
    return True


def _rules(db: Session, workspace_id: int, trigger: str) -> list[Rule]:
    return list(db.scalars(select(Rule).where(Rule.workspace_id == workspace_id, Rule.enabled.is_(True), Rule.trigger == trigger).order_by(Rule.position, Rule.id)))


def run_for_messages(db: Session, workspace_id: int, account_id: int, message_ids: list[int], by_hand: bool = False) -> int:
    """Run every enabled new-mail rule, in order, on emails that have just arrived. Returns how many runs were recorded.

    `by_hand` is a person asking for the rules to be applied to mail already there: it does not
    wait for the automation switch, and it sends no notifications.

    Rules that ask what the AI made of the email wait for the analysis (see `run_after_analysis`),
    unless this is by hand and the email has already been analysed.
    """
    if not message_ids or not (by_hand or is_on(db, workspace_id, account_id)):
        return 0
    rules = _rules(db, workspace_id, "new_mail")
    if not rules:
        return 0
    recorded = 0
    for message in _load(db, workspace_id, message_ids):
        priority = _ai_priority(db, message.id) if by_hand else None
        mail = mail_from(message, priority)
        for rule in rules:
            if (rule.conditions or {}).get("ai_priority") and priority is None:
                continue
            if matches(rule.conditions, mail) and _run(db, rule, message, quiet=by_hand):
                recorded += 1
    return recorded


def run_after_analysis(db: Session, workspace_id: int, account_id: int, message_id: int, priority: str | None) -> int:
    """The AI has just analysed an email: run the new-mail rules that were waiting to know its priority."""
    if not priority or not is_on(db, workspace_id, account_id):
        return 0
    rules = [rule for rule in _rules(db, workspace_id, "new_mail") if (rule.conditions or {}).get("ai_priority")]
    recorded = 0
    for message in _load(db, workspace_id, [message_id]) if rules else []:
        mail = mail_from(message, priority)
        recorded += sum(1 for rule in rules if matches(rule.conditions, mail) and _run(db, rule, message))
    return recorded


# Where each waiting rule has got to in its pass over unanswered mail (rule id -> last message id looked at).
_waiting_cursor: dict[int, int] = {}


def run_waiting(db: Session, limit: int = 100) -> int:
    """Rules that act when an email has sat without a reply from us for a set time.

    They look only at mail that arrived after the rule was made, in conversations that are still
    open, where that email is still the latest word.
    """
    recorded = 0
    now = utcnow()
    for rule in db.scalars(select(Rule).where(Rule.enabled.is_(True), Rule.trigger == "waiting", Rule.wait_hours.is_not(None)).order_by(Rule.position, Rule.id)):
        m0 = Message.__table__.alias("m0")
        newer = Message.__table__.alias("m1")
        done = select(RuleRun.id).where(RuleRun.rule_id == rule.id, RuleRun.message_id == m0.c.id)
        ids = db.scalars(
            select(m0.c.id).join(Conversation, Conversation.id == m0.c.conversation_id)
            .where(
                m0.c.workspace_id == rule.workspace_id, m0.c.direction == "inbound",
                m0.c.sent_at >= rule.created_at, m0.c.sent_at <= now - timedelta(hours=rule.wait_hours),
                Conversation.status == "open", Conversation.is_archived.is_(False), Conversation.is_deleted.is_(False),
                ~select(newer.c.id).where(newer.c.conversation_id == m0.c.conversation_id, newer.c.sent_at > m0.c.sent_at).exists(),
                ~done.exists(),
                m0.c.id > _waiting_cursor.get(rule.id, 0),
            ).order_by(m0.c.id).limit(limit)
        ).all()
        # Move on past what was just looked at, matching or not, and start over once the end is reached.
        # Without this, a hundred emails that will never match would hide every newer one for ever.
        _waiting_cursor[rule.id] = max(ids) if len(ids) == limit else 0
        for message in _load(db, rule.workspace_id, list(ids)):
            if not is_on(db, rule.workspace_id, message.email_account_id):
                continue
            if matches(rule.conditions, mail_from(message, _ai_priority(db, message.id))) and _run(db, rule, message):
                recorded += 1
    return recorded


def retry_failed(db: Session) -> int:
    """Try again the runs that failed and are due. Called by the background loop."""
    due = db.scalars(select(RuleRun).where(RuleRun.status == "failed", RuleRun.next_attempt_at <= utcnow()).limit(50)).all()
    for run in due:
        rule = db.get(Rule, run.rule_id)
        message = db.scalar(select(Message).options(selectinload(Message.recipients), selectinload(Message.attachments)).where(Message.id == run.message_id))
        if rule is None or message is None or not rule.enabled or not is_on(db, run.workspace_id, message.email_account_id):
            run.status, run.next_attempt_at, run.finished_at, run.error = "gave_up", None, utcnow(), "The rule or automation was switched off before it could be retried."
        else:
            _apply(db, rule, message, run)
        db.commit()
    return len(due)


def retry_failed_task() -> int:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return retry_failed(db)
    finally:
        db.close()
