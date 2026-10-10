"""Figures for the Analytics page. Everything is counted from real records, for the mailboxes the reader may open."""

from datetime import timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models.ai import AiAnalysis, AiReply
from app.models.automation import Rule, RuleRun
from app.models.email import Conversation, EmailAccount, Message
from app.repositories import workspaces
from app.services import mailbox_access
from app.services.auth import Identity


def report(db: Session, identity: Identity, days: int) -> dict:
    workspace_id = identity.workspace.id
    allowed = mailbox_access.allowed_account_ids(db, identity)
    today = utcnow().date()
    first = today - timedelta(days=days - 1)
    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)

    def scope(stmt, column):
        return stmt if allowed is None else stmt.where(column.in_(allowed))

    # ---- mail per day ----
    day = func.date(Message.sent_at)
    rows = db.execute(scope(select(day, Message.direction, func.count()).where(Message.workspace_id == workspace_id, Message.sent_at >= since), Message.email_account_id).group_by(day, Message.direction)).all()
    by_day = {(str(d), direction): n for d, direction, n in rows}
    run_day = func.date(RuleRun.created_at)
    run_stmt = select(run_day, RuleRun.status, func.count()).join(Conversation, Conversation.id == RuleRun.conversation_id).where(RuleRun.workspace_id == workspace_id, RuleRun.created_at >= since)
    runs_by_day: dict[str, dict[str, int]] = {}
    for d, status, n in db.execute(scope(run_stmt, Conversation.email_account_id).group_by(run_day, RuleRun.status)):
        runs_by_day.setdefault(str(d), {})[status] = n
    daily = []
    for offset in range(days):
        d = str(first + timedelta(days=offset))
        ran = runs_by_day.get(d, {})
        daily.append({"day": d, "received": by_day.get((d, "inbound"), 0), "sent": by_day.get((d, "outbound"), 0),
                      "rule_runs": sum(ran.values()), "rule_failures": ran.get("failed", 0) + ran.get("gave_up", 0)})

    # ---- how fast the team answers: each reply against the email it answered ----
    earlier = Message.__table__.alias("earlier")
    asked = select(func.max(earlier.c.sent_at)).where(earlier.c.conversation_id == Message.conversation_id, earlier.c.direction == "inbound", earlier.c.sent_at < Message.sent_at).scalar_subquery()
    pairs = db.execute(scope(select(Message.sent_at, asked).where(Message.workspace_id == workspace_id, Message.direction == "outbound", Message.sent_at >= since), Message.email_account_id).limit(3000)).all()
    waits = sorted((sent - got).total_seconds() / 3600 for sent, got in pairs if got is not None and sent > got)

    # ---- where things stand now ----
    def conversations(*where) -> int:
        return int(db.scalar(scope(select(func.count()).select_from(Conversation).where(Conversation.workspace_id == workspace_id, Conversation.is_deleted.is_(False), *where), Conversation.email_account_id)) or 0)

    live = (Conversation.is_archived.is_(False),)
    people = {user.id: user.name for _m, user, _s in workspaces.members(db, workspace_id)}
    load = db.execute(scope(select(Conversation.assignee_user_id, func.count()).where(Conversation.workspace_id == workspace_id, Conversation.is_deleted.is_(False), Conversation.is_archived.is_(False), Conversation.status != "closed", Conversation.assignee_user_id.is_not(None)), Conversation.email_account_id).group_by(Conversation.assignee_user_id)).all()

    senders = db.execute(scope(select(Message.sender_email, func.max(Message.sender_name), func.count()).where(Message.workspace_id == workspace_id, Message.direction == "inbound", Message.sent_at >= since), Message.email_account_id).group_by(Message.sender_email).order_by(func.count().desc()).limit(8)).all()
    boxes = db.execute(scope(select(EmailAccount.email_address, Message.direction, func.count()).join(EmailAccount, EmailAccount.id == Message.email_account_id).where(Message.workspace_id == workspace_id, Message.sent_at >= since), Message.email_account_id).group_by(EmailAccount.email_address, Message.direction)).all()
    mailboxes: dict[str, dict] = {}
    for address, direction, n in boxes:
        mailboxes.setdefault(address, {"email_address": address, "received": 0, "sent": 0})["received" if direction == "inbound" else "sent"] = n

    # ---- rules ----
    per_rule: dict[int, dict[str, int]] = {}
    rule_stmt = select(RuleRun.rule_id, RuleRun.status, func.count()).join(Conversation, Conversation.id == RuleRun.conversation_id).where(RuleRun.workspace_id == workspace_id, RuleRun.created_at >= since)
    for rule_id, status, n in db.execute(scope(rule_stmt, Conversation.email_account_id).group_by(RuleRun.rule_id, RuleRun.status)):
        per_rule.setdefault(rule_id, {})[status] = n
    rules = [{"id": r.id, "name": r.name, "enabled": r.enabled, "runs": sum(per_rule.get(r.id, {}).values()),
              "failed": per_rule.get(r.id, {}).get("failed", 0) + per_rule.get(r.id, {}).get("gave_up", 0), "last_run_at": f"{r.last_run_at.isoformat()}Z" if r.last_run_at else None}
             for r in db.scalars(select(Rule).where(Rule.workspace_id == workspace_id).order_by(Rule.position, Rule.id))]

    # ---- AI ----
    def analyses(*where) -> int:
        return int(db.scalar(scope(select(func.count()).select_from(AiAnalysis).where(AiAnalysis.workspace_id == workspace_id, AiAnalysis.created_at >= since, *where), AiAnalysis.email_account_id)) or 0)

    def replies(*where) -> int:
        return int(db.scalar(scope(select(func.count()).select_from(AiReply).where(AiReply.workspace_id == workspace_id, AiReply.created_at >= since, *where), AiReply.email_account_id)) or 0)

    priorities = dict(db.execute(scope(select(AiAnalysis.priority, func.count()).where(AiAnalysis.workspace_id == workspace_id, AiAnalysis.created_at >= since, AiAnalysis.status == "done"), AiAnalysis.email_account_id).group_by(AiAnalysis.priority)).all())

    return {
        "days": days,
        "daily": daily,
        "totals": {"received": sum(d["received"] for d in daily), "sent": sum(d["sent"] for d in daily), "rule_runs": sum(d["rule_runs"] for d in daily), "rule_failures": sum(d["rule_failures"] for d in daily)},
        "replies": {"count": len(waits), "median_hours": round(median(waits), 1) if waits else None, "within_a_day": sum(1 for w in waits if w <= 24)},
        "now": {
            "open": conversations(Conversation.status == "open", *live), "pending": conversations(Conversation.status == "pending", *live), "closed": conversations(Conversation.status == "closed", *live),
            "unassigned": conversations(Conversation.status != "closed", Conversation.assignee_user_id.is_(None), *live), "unread": conversations(Conversation.is_read.is_(False), *live),
            "urgent": conversations(Conversation.status != "closed", Conversation.priority == "urgent", *live), "high": conversations(Conversation.status != "closed", Conversation.priority == "high", *live),
        },
        "workload": sorted(({"name": people.get(user_id, "Someone who left"), "open": n} for user_id, n in load), key=lambda row: -row["open"]),
        "top_senders": [{"email": email, "name": name, "received": n} for email, name, n in senders],
        "mailboxes": sorted(mailboxes.values(), key=lambda row: -row["received"]),
        "rules": rules,
        "ai": {
            "analysed": analyses(AiAnalysis.status == "done"), "skipped": analyses(AiAnalysis.status == "skipped"), "failed": analyses(AiAnalysis.status == "gave_up"),
            "waiting": analyses(AiAnalysis.status.in_(("pending", "working", "failed"))), "reply_needed": analyses(AiAnalysis.status == "done", AiAnalysis.reply_required.is_(True)),
            "low": int(priorities.get("low", 0)), "medium": int(priorities.get("medium", 0)), "high": int(priorities.get("high", 0)),
            "drafts_waiting": replies(AiReply.status.in_(("pending", "failed"))), "sent_by_people": replies(AiReply.status == "sent", AiReply.auto_sent.is_(False)),
            "sent_automatically": replies(AiReply.status == "sent", AiReply.auto_sent.is_(True)), "rejected": replies(AiReply.status == "rejected"),
        },
    }
