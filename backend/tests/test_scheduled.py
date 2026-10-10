"""Things that happen on the clock: follow-up reminders and rules for mail that has waited. Also rules that use the AI's priority."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.automation import engine, scheduler
from app.core.database import utcnow
from app.models.automation import Reminder, Rule
from app.models.email import Conversation
from app.services import ai_triage, reminders
from tests.test_ai_triage import ROUTINE, ai  # noqa: F401 - fixture
from tests.test_automation import RULES, _arrive, _conv, _ready, _rule, _runs
from tests.test_gmail_oauth import google  # noqa: F401 - fixture
from tests.test_mailbox_access import _join


def _in(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def _make_due(db, **where):
    db.rollback()
    for reminder in db.scalars(select(Reminder).filter_by(status="waiting", **where)):
        reminder.due_at = utcnow() - timedelta(seconds=1)
    db.commit()


def _bell(client):
    return client.get("/api/v1/notifications").json()["data"]["items"]


# ---- reminders -------------------------------------------------------------------------------------------

def test_a_reminder_tells_its_owner_once_when_it_comes_due(client, member, google, db):
    account = _ready(client, google, on=False)
    _arrive(client, google, account, "n1", "Quote for Maya")
    conversation = _conv(client, "Quote for Maya")
    assert client.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(minutes=-5)}).status_code == 422
    assert client.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(days=400)}).status_code == 422
    made = client.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(days=2), "note": "Chase the quote"})
    assert made.status_code == 201 and made.json()["data"]["status"] == "waiting" and made.json()["data"]["subject"] == "Quote for Maya"
    assert [r["note"] for r in client.get(f"/api/v1/reminders?conversation_id={conversation['id']}").json()["data"]] == ["Chase the quote"]

    assert reminders.fire_due(db) == 0 and _bell(client) == []  # not due yet
    _make_due(db)
    scheduler.tick()
    scheduler.tick()
    bell = _bell(client)
    assert len(bell) == 1 and bell[0]["title"] == "Follow up: Quote for Maya" and bell[0]["body"] == "Chase the quote" and bell[0]["conversation_id"] == conversation["id"]
    assert client.get("/api/v1/reminders").json()["data"][0]["status"] == "done"
    assert client.get(f"/api/v1/reminders?conversation_id={conversation['id']}").json()["data"] == []


def test_a_reminder_can_stand_down_if_they_write_back_and_a_new_one_replaces_the_old(client, member, google, db):
    account = _ready(client, google, on=False)
    _arrive(client, google, account, "n1", "Contract")
    conversation = _conv(client, "Contract")
    first = client.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(days=1)}).json()["data"]
    second = client.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(days=3), "only_if_no_reply": True}).json()["data"]
    listed = {r["id"]: r["status"] for r in client.get("/api/v1/reminders").json()["data"]}
    assert listed == {first["id"]: "cancelled", second["id"]: "waiting"}

    google.deliver("n2", "t-n1", sender="Maya Chen <maya@example.com>", subject="Re: Contract", body="Signed, thanks.", message_id="<n2@example.com>", in_reply_to="<n1@example.com>")
    client.post(f"/api/v1/email-accounts/{account['id']}/sync")
    db.rollback()
    late = db.get(Reminder, second["id"])
    late.created_at = datetime(2020, 1, 1)  # set before the reply came in
    db.commit()
    _make_due(db)
    assert reminders.fire_due(db) == 0 and _bell(client) == []
    assert {r["id"]: r["status"] for r in client.get("/api/v1/reminders").json()["data"]}[second["id"]] == "answered"

    third = client.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(hours=1), "only_if_no_reply": True}).json()["data"]
    _make_due(db)  # nothing has arrived since this one was set
    assert reminders.fire_due(db) == 1 and _bell(client)[0]["body"] == "No reply has come in."
    assert client.delete(f"/api/v1/reminders/{third['id']}").status_code == 204  # already done: nothing to cancel, no error


def test_reminders_are_private_and_need_access_to_the_conversation(client, member, google, db):
    account = _ready(client, google, on=False)
    _arrive(client, google, account, "n1", "Private matter")
    conversation = _conv(client, "Private matter")
    mine = client.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(days=1)}).json()["data"]
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    assert grace.get("/api/v1/reminders").json()["data"] == []
    assert grace.delete(f"/api/v1/reminders/{mine['id']}").status_code == 404
    hers = grace.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(days=1)})
    assert hers.status_code == 201

    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "members": []})
    assert grace.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(days=1)}).status_code == 404
    assert grace.get("/api/v1/reminders").json()["data"] == []
    _make_due(db)
    reminders.fire_due(db)
    assert len(_bell(client)) == 1 and len(_bell(grace)) == 1  # each person is told about their own

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import PASSWORD

    other = TestClient(app)
    other.post("/api/v1/auth/register", json={"email": "eve@example.com", "password": PASSWORD, "name": "Eve Elsewhere"})
    other.post("/api/v1/workspaces", json={"name": "Elsewhere"})
    assert other.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": _in(days=1)}).status_code == 404
    assert other.delete(f"/api/v1/reminders/{mine['id']}").status_code == 404


# ---- rules for mail that has waited --------------------------------------------------------------------------

def _waiting_rule(client, db, hours=24, **extra):
    rule = _rule(client, "Chase after a day", {}, [{"type": "set_priority", "value": "urgent"}, {"type": "notify", "user_id": extra.pop("tell")}], trigger="waiting", wait_hours=hours, **extra)
    db.rollback()
    db.get(Rule, rule["id"]).created_at = datetime(2020, 1, 1)  # so the stand-in mailbox's mail counts as arriving after it
    db.commit()
    return rule


def test_a_waiting_rule_acts_once_on_mail_left_unanswered(client, member, google, db):
    account = _ready(client, google)
    body = {"name": "No time", "conditions": {}, "actions": [{"type": "flag"}], "trigger": "waiting"}
    assert client.post(RULES, json=body).status_code == 422  # must say how long
    rule = _waiting_rule(client, db, tell=member["user"]["id"])
    assert rule["trigger"] == "waiting" and rule["summary"] == "No reply after 1 day → set priority to urgent, notify Ada Lovelace"

    _arrive(client, google, account, "n1", "Still waiting")  # the stand-in dates its mail days ago
    assert _runs(client) == []  # arriving is not what triggers this rule
    assert engine.run_waiting(db) >= 1
    assert _conv(client, "Still waiting")["priority"] == "urgent"
    count = len(_runs(client))
    scheduler.tick()
    assert len(_runs(client)) == count  # once per email
    assert any(n["title"] == "The rule “Chase after a day” matched a new email" for n in _bell(client))


def test_a_waiting_rule_leaves_answered_closed_and_not_yet_due_mail_alone(client, member, google, db):
    account = _ready(client, google)
    _arrive(client, google, account, "n1", "Answered")
    _arrive(client, google, account, "n2", "Closed")
    _arrive(client, google, account, "n3", "Archived")
    answered, closed, archived = _conv(client, "Answered"), _conv(client, "Closed"), _conv(client, "Archived")
    assert client.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["maya@example.com"], "subject": "Re: Answered", "body_text": "Done.", "conversation_id": answered["id"], "in_reply_to": "<n1@example.com>"}).status_code == 201
    client.patch(f"/api/v1/conversations/{closed['id']}", json={"status": "closed"})
    client.patch(f"/api/v1/conversations/{archived['id']}", json={"is_archived": True})

    _waiting_rule(client, db, hours=24 * 60, tell=member["user"]["id"])  # sixty days: nothing has waited that long
    assert engine.run_waiting(db) == 0
    db.rollback()
    db.scalar(select(Rule)).wait_hours = 1
    db.commit()
    engine.run_waiting(db)
    handled = {r["subject"] for r in _runs(client)}
    assert not handled & {"Answered", "Closed", "Archived"} and "Invoice from last year" in handled
    db.rollback()
    assert db.scalar(select(Conversation.priority).where(Conversation.id == answered["id"])) == "normal"

    # Automation switched off: nothing more runs.
    client.put("/api/v1/automation/settings", json={"enabled": False})
    _arrive(client, google, account, "n4", "After switching off")
    assert engine.run_waiting(db) == 0


def test_a_waiting_rule_ignores_mail_from_before_it_was_made(client, member, google, db):
    account = _ready(client, google)
    _arrive(client, google, account, "n1", "Older than the rule")
    _rule(client, "Fresh rule", {}, [{"type": "flag"}], trigger="waiting", wait_hours=1)  # made just now
    assert engine.run_waiting(db) == 0 and _conv(client, "Older than the rule")["is_starred"] is False


# ---- rules that use the AI's priority ---------------------------------------------------------------------------

def test_a_rule_can_wait_for_the_ais_priority(client, member, google, db, ai):
    account = _ready(client, google)
    client.put("/api/v1/ai/settings", json={"enabled": True})
    rule = _rule(client, "AI says High", {"ai_priority": "high"}, [{"type": "flag"}, {"type": "set_priority", "value": "urgent"}])
    assert rule["summary"] == "If the AI marks it High → flag it, set priority to urgent"
    plain = _rule(client, "Everything", {}, [{"type": "set_status", "value": "pending"}])

    ai.answer = {**ROUTINE, "priority": "high", "risk_flags": ["complaint"]}
    _arrive(client, google, account, "n1", "Furious customer", body="This is unacceptable.")
    waiting = _conv(client, "Furious customer")
    assert waiting["status"] == "pending" and waiting["is_starred"] is False  # the plain rule ran at once; the AI rule is waiting
    ai_triage.process_pending(db)
    flagged = _conv(client, "Furious customer")
    assert flagged["is_starred"] is True and flagged["priority"] == "urgent"

    ai.answer = dict(ROUTINE)  # low
    _arrive(client, google, account, "n2", "Simple question", body="What time do you open on Saturday?")
    ai_triage.process_pending(db)
    assert _conv(client, "Simple question")["is_starred"] is False
    assert len(_runs(client, rule_id=rule["id"])) == 1 and len(_runs(client, rule_id=plain["id"])) == 2

    # Trying the rule on recent mail knows what the AI said.
    tried = client.post(f"{RULES}/test", json={"name": "t", "conditions": {"ai_priority": "high"}, "actions": [{"type": "flag"}]}).json()["data"]
    assert [m["subject"] for m in tried["matches"]] == ["Furious customer"]
    assert client.post(RULES, json={"name": "bad", "conditions": {"ai_priority": "urgent"}, "actions": [{"type": "flag"}]}).status_code == 422
