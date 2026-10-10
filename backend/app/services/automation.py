"""Managing rules, testing them, reading their history, and the ON/OFF switches."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.automation import engine
from app.automation.conditions import matches
from app.core.database import utcnow
from app.core.errors import AppError
from app.models.automation import AutomationSetting, Rule, RuleRun
from app.models.email import Conversation, Label, Message
from app.models.user import User
from app.repositories import email as email_repo
from app.repositories import workspaces
from app.schemas.automation import RuleIn
from app.services import audit, mailbox_access
from app.services.accounts import MANAGERS
from app.services.auth import Client, Identity

EDITORS = (*MANAGERS, "manager")
TEST_WINDOW = 300


def _can_edit(identity: Identity) -> None:
    if identity.role not in EDITORS:
        raise AppError(403, "FORBIDDEN", "Owners, admins and managers can change rules. Everyone else can see them.")


def _names(db: Session, workspace_id: int) -> tuple[dict[int, str], dict[int, str], dict[int, str]]:
    people = {user.id: user.name for _m, user, _s in workspaces.members(db, workspace_id)}
    labels = {label.id: label.name for label in db.scalars(select(Label).where(Label.workspace_id == workspace_id))}
    mailboxes = {account.id: account.email_address for account, _n in email_repo.list_accounts(db, workspace_id)}
    return people, labels, mailboxes


def _how_long(hours: int) -> str:
    if hours % 24 == 0:
        return "1 day" if hours == 24 else f"{hours // 24} days"
    return "1 hour" if hours == 1 else f"{hours} hours"


def describe(rule_conditions: dict, rule_actions: list, people: dict[int, str], labels: dict[int, str], mailboxes: dict[int, str], trigger: str = "new_mail", wait_hours: int | None = None) -> str:
    """The rule as one sentence: "If subject contains “invoice” → add the label Billing, assign to Grace"."""
    parts = []
    c = rule_conditions or {}
    if c.get("account_id"):
        parts.append(f"mail to {mailboxes.get(c['account_id'], 'a removed mailbox')}")
    for key, word in (("sender", "sender"), ("recipient", "recipient"), ("subject", "subject"), ("body", "message")):
        if c.get(key):
            parts.append(f"{word} contains “{c[key]}”")
    if c.get("ai_priority"):
        parts.append(f"the AI marks it {c['ai_priority'].capitalize()}")
    if c.get("has_attachments") is not None:
        parts.append("has attachments" if c["has_attachments"] else "has no attachments")
    does = []
    for a in rule_actions or []:
        kind = a.get("type")
        if kind == "add_label":
            does.append(f"add the label {labels.get(a['label_id'], '(removed)')}")
        elif kind == "set_priority":
            does.append(f"set priority to {a['value']}")
        elif kind == "set_status":
            does.append(f"set status to {a['value']}")
        elif kind == "assign":
            does.append(f"assign to {people.get(a['user_id'], '(removed person)')}")
        elif kind == "assign_in_turn":
            does.append("assign in turn to " + ", ".join(people.get(u, "(removed person)") for u in a["user_ids"]))
        elif kind == "flag":
            does.append("flag it")
        elif kind == "archive":
            does.append("archive it")
        elif kind == "notify":
            does.append(f"notify {people.get(a['user_id'], '(removed person)')}")
    if trigger == "waiting" and wait_hours:
        return f"No reply after {_how_long(wait_hours)}" + (" and " + " and ".join(parts) if parts else "") + " → " + ", ".join(does)
    return ("If " + " and ".join(parts) if parts else "Every new email") + " → " + ", ".join(does)


def _validate(db: Session, identity: Identity, data: RuleIn) -> None:
    """Everything a rule points at must belong to this workspace."""
    people, labels, mailboxes = _names(db, identity.workspace.id)
    if data.conditions.account_id is not None and data.conditions.account_id not in mailboxes:
        raise AppError(404, "ACCOUNT_NOT_FOUND", "That mailbox is not in this workspace.")
    # Rules act with the app's own authority, on every mailbox they cover. So someone shut out of a
    # mailbox must not be able to aim a rule at it, or learn what arrives there from the rule's counts.
    allowed = _limited_to(db, identity)
    if allowed is not None:
        if data.conditions.account_id is None:
            raise AppError(403, "FORBIDDEN", "You cannot open every mailbox in this workspace, so choose which mailbox this rule is for.")
        if data.conditions.account_id not in allowed:
            raise AppError(404, "ACCOUNT_NOT_FOUND", "That mailbox is not in this workspace.")
    for action in data.actions:
        if action.type == "add_label" and action.label_id not in labels:
            raise AppError(404, "LABEL_NOT_FOUND", "That label is not in this workspace.")
        if action.type in ("assign", "notify") and action.user_id not in people:
            raise AppError(404, "MEMBER_NOT_FOUND", "That person is not in this workspace.")
        if action.type == "assign_in_turn" and any(user_id not in people for user_id in action.user_ids):
            raise AppError(404, "MEMBER_NOT_FOUND", "One of those people is not in this workspace.")


def list_rules(db: Session, identity: Identity) -> list[dict]:
    workspace_id = identity.workspace.id
    rules = [rule for rule in db.scalars(select(Rule).where(Rule.workspace_id == workspace_id).order_by(Rule.position, Rule.id)) if _may_see(db, identity, rule)]
    people, labels, mailboxes = _names(db, workspace_id)
    failed = dict(db.execute(
        select(RuleRun.rule_id, func.count()).where(RuleRun.workspace_id == workspace_id, RuleRun.status.in_(("failed", "gave_up"))).group_by(RuleRun.rule_id)
    ).all())
    creators = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_({r.created_by_user_id for r in rules if r.created_by_user_id})))} if rules else {}
    return [{
        "id": r.id, "name": r.name, "enabled": r.enabled, "position": r.position, "conditions": r.conditions, "actions": r.actions,
        "run_count": r.run_count, "failed_count": int(failed.get(r.id, 0)), "last_run_at": r.last_run_at,
        "created_by_name": creators.get(r.created_by_user_id), "summary": describe(r.conditions, r.actions, people, labels, mailboxes, r.trigger, r.wait_hours),
        "trigger": r.trigger, "wait_hours": r.wait_hours,
    } for r in rules]


def _get(db: Session, identity: Identity, rule_id: int) -> Rule:
    rule = db.scalar(select(Rule).where(Rule.id == rule_id, Rule.workspace_id == identity.workspace.id))
    if not rule or not _may_see(db, identity, rule):
        raise AppError(404, "RULE_NOT_FOUND", "Rule not found.")
    return rule


def _may_see(db: Session, identity: Identity, rule: Rule) -> bool:
    """People who cannot open every mailbox see only the rules made for a mailbox they can open."""
    allowed = _limited_to(db, identity)
    return allowed is None or (rule.conditions or {}).get("account_id") in allowed


def _limited_to(db: Session, identity: Identity) -> set[int] | None:
    """The mailboxes this person may open, if there is at least one they may not. None when they can open them all."""
    allowed = mailbox_access.allowed_account_ids(db, identity)
    if allowed is None:
        return None
    everything = {account.id for account, _n in email_repo.list_accounts(db, identity.workspace.id)}
    return set(allowed) if everything - set(allowed) else None


def _one(db: Session, identity: Identity, rule_id: int) -> dict:
    return next(r for r in list_rules(db, identity) if r["id"] == rule_id)


def create_rule(db: Session, identity: Identity, data: RuleIn, client: Client) -> dict:
    _can_edit(identity)
    _validate(db, identity, data)
    last = db.scalar(select(func.max(Rule.position)).where(Rule.workspace_id == identity.workspace.id))
    rule = Rule(workspace_id=identity.workspace.id, created_by_user_id=identity.user.id, name=" ".join(data.name.split()), enabled=data.enabled,
                position=(last if last is not None else -1) + 1, conditions=data.conditions.model_dump(), actions=[a.model_dump() for a in data.actions],
                trigger=data.trigger, wait_hours=data.wait_hours if data.trigger == "waiting" else None)
    db.add(rule)
    audit.record(db, action="rule.created", summary=f"Created the rule {rule.name}", actor=identity.user, workspace_id=identity.workspace.id, ip=client.ip)
    db.commit()
    return _one(db, identity, rule.id)


def update_rule(db: Session, identity: Identity, rule_id: int, data: RuleIn, client: Client) -> dict:
    _can_edit(identity)
    rule = _get(db, identity, rule_id)
    _validate(db, identity, data)
    rule.name, rule.enabled = " ".join(data.name.split()), data.enabled
    rule.conditions, rule.actions, rule.updated_at = data.conditions.model_dump(), [a.model_dump() for a in data.actions], utcnow()
    rule.trigger, rule.wait_hours = data.trigger, data.wait_hours if data.trigger == "waiting" else None
    audit.record(db, action="rule.changed", summary=f"Changed the rule {rule.name}", actor=identity.user, workspace_id=identity.workspace.id, ip=client.ip)
    db.commit()
    return _one(db, identity, rule.id)


def set_enabled(db: Session, identity: Identity, rule_id: int, enabled: bool, client: Client) -> dict:
    _can_edit(identity)
    rule = _get(db, identity, rule_id)
    rule.enabled = enabled
    audit.record(db, action="rule.switched", summary=f"Switched the rule {rule.name} {'on' if enabled else 'off'}", actor=identity.user, workspace_id=identity.workspace.id, ip=client.ip)
    db.commit()
    return _one(db, identity, rule.id)


def delete_rule(db: Session, identity: Identity, rule_id: int, client: Client) -> None:
    _can_edit(identity)
    rule = _get(db, identity, rule_id)
    audit.record(db, action="rule.deleted", summary=f"Deleted the rule {rule.name}", actor=identity.user, workspace_id=identity.workspace.id, ip=client.ip)
    db.delete(rule)
    db.commit()


def reorder(db: Session, identity: Identity, rule_ids: list[int]) -> None:
    _can_edit(identity)
    rules = {r.id: r for r in db.scalars(select(Rule).where(Rule.workspace_id == identity.workspace.id))}
    if set(rule_ids) != set(rules):
        raise AppError(422, "VALIDATION_ERROR", "The order must list every rule once.")
    for position, rule_id in enumerate(rule_ids):
        rules[rule_id].position = position
    db.commit()


def test_rule(db: Session, identity: Identity, data: RuleIn) -> tuple[int, list[dict]]:
    """Which recent emails the rule would act on. Changes nothing."""
    _validate(db, identity, data)
    allowed = mailbox_access.allowed_account_ids(db, identity)
    stmt = (
        select(Message).options(selectinload(Message.recipients), selectinload(Message.attachments))
        .where(Message.workspace_id == identity.workspace.id, Message.direction == "inbound")
        .order_by(Message.sent_at.desc(), Message.id.desc()).limit(TEST_WINDOW)
    )
    if allowed is not None:
        stmt = stmt.where(Message.email_account_id.in_(allowed))
    recent = db.scalars(stmt).all()
    conditions = data.conditions.model_dump()
    from app.models.ai import AiAnalysis

    seen = dict(db.execute(select(AiAnalysis.message_id, AiAnalysis.priority).where(AiAnalysis.message_id.in_([m.id for m in recent]), AiAnalysis.status == "done")).all()) if recent else {}
    hits = [m for m in recent if matches(conditions, engine.mail_from(m, seen.get(m.id)))][:25]
    return len(recent), [{"conversation_id": m.conversation_id, "subject": m.subject or "(no subject)", "sender": m.sender_name or m.sender_email, "sent_at": m.sent_at} for m in hits]


def runs(db: Session, identity: Identity, rule_id: int | None, limit: int) -> list[dict]:
    allowed = mailbox_access.allowed_account_ids(db, identity)
    stmt = (
        select(RuleRun, Rule.name, Conversation.subject, Conversation.email_account_id)
        .join(Rule, Rule.id == RuleRun.rule_id).join(Conversation, Conversation.id == RuleRun.conversation_id)
        .where(RuleRun.workspace_id == identity.workspace.id).order_by(RuleRun.created_at.desc(), RuleRun.id.desc()).limit(limit)
    )
    if rule_id is not None:
        stmt = stmt.where(RuleRun.rule_id == rule_id)
    if allowed is not None:
        stmt = stmt.where(Conversation.email_account_id.in_(allowed))
    return [{
        "id": run.id, "rule_id": run.rule_id, "rule_name": name, "conversation_id": run.conversation_id, "subject": subject,
        "status": run.status, "attempts": run.attempts, "done": run.done or [], "error": run.error, "created_at": run.created_at,
    } for run, name, subject, _account in db.execute(stmt)]


def get_settings(db: Session, identity: Identity) -> dict:
    workspace_id = identity.workspace.id
    saved = {(s.level, s.level_id): s.enabled for s in db.scalars(select(AutomationSetting).where(AutomationSetting.workspace_id == workspace_id))}
    return {
        "enabled": bool(saved.get(("organization", workspace_id), False)),
        "mailboxes": [{"account_id": a.id, "email_address": a.email_address, "enabled": bool(saved.get(("email_account", a.id), True))}
                      for a, _n in email_repo.list_accounts(db, workspace_id) if (allowed := mailbox_access.allowed_account_ids(db, identity)) is None or a.id in allowed],
    }


def _set(db: Session, workspace_id: int, level: str, level_id: int, enabled: bool) -> None:
    row = db.scalar(select(AutomationSetting).where(AutomationSetting.workspace_id == workspace_id, AutomationSetting.level == level, AutomationSetting.level_id == level_id))
    if row:
        row.enabled = enabled
    else:
        db.add(AutomationSetting(workspace_id=workspace_id, level=level, level_id=level_id, enabled=enabled))


def update_settings(db: Session, identity: Identity, enabled: bool | None, mailboxes: dict[int, bool], client: Client) -> dict:
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only owners and admins can switch automation on or off.")
    workspace_id = identity.workspace.id
    own = {a.id: a.email_address for a, _n in email_repo.list_accounts(db, workspace_id)}
    if enabled is not None:
        _set(db, workspace_id, "organization", workspace_id, enabled)
        audit.record(db, action="automation.switched", summary=f"Switched automation {'on' if enabled else 'off'} for the workspace", actor=identity.user, workspace_id=workspace_id, ip=client.ip)
    for account_id, on in mailboxes.items():
        if account_id not in own:
            raise AppError(404, "ACCOUNT_NOT_FOUND", "That mailbox is not in this workspace.")
        _set(db, workspace_id, "email_account", account_id, on)
        audit.record(db, action="automation.switched", summary=f"Switched automation {'on' if on else 'off'} for {own[account_id]}", actor=identity.user, workspace_id=workspace_id, ip=client.ip)
    db.commit()
    return get_settings(db, identity)


def run_on_recent(db: Session, identity: Identity, per_mailbox: int, client: Client) -> dict:
    """Apply the rules that are on to the latest emails already in each mailbox. Asked for by a person, once."""
    if identity.role not in MANAGERS:
        raise AppError(403, "FORBIDDEN", "Only owners and admins can run rules on mail that is already here.")
    workspace_id = identity.workspace.id
    checked = acted = 0
    for account, _n in email_repo.list_accounts(db, workspace_id):
        ids = list(db.scalars(
            select(Message.id).where(Message.workspace_id == workspace_id, Message.email_account_id == account.id, Message.direction == "inbound")
            .order_by(Message.sent_at.desc(), Message.id.desc()).limit(per_mailbox)
        ))
        checked += len(ids)
        acted += engine.run_for_messages(db, workspace_id, account.id, ids, by_hand=True)
    audit.record(db, action="automation.run_on_recent", summary=f"Ran the rules on the latest {per_mailbox} emails in each mailbox", actor=identity.user, workspace_id=workspace_id, ip=client.ip)
    db.commit()
    return {"checked": checked, "runs": acted}


def summary(db: Session, identity: Identity) -> dict:
    workspace_id = identity.workspace.id
    rules = list_rules(db, identity)
    since = utcnow() - timedelta(hours=24)
    counts = dict(db.execute(select(RuleRun.status, func.count()).where(RuleRun.workspace_id == workspace_id, RuleRun.created_at >= since).group_by(RuleRun.status)).all())
    return {
        "enabled": get_settings(db, identity)["enabled"],
        "rules_total": len(rules),
        "rules_on": sum(1 for r in rules if r["enabled"]),
        "runs_today": int(sum(counts.values())),
        "failed_today": int(counts.get("failed", 0) + counts.get("gave_up", 0)),
        "rules": rules,
        "recent": runs(db, identity, None, 6),
    }
