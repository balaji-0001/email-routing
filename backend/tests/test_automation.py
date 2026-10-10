"""Rules: what they match, what they do, once per email, their history, retries and who may change them."""

from datetime import timedelta

from sqlalchemy import select

from app.automation import actions, engine
from app.core.database import utcnow
from app.models.automation import Rule, RuleRun
from app.models.email import Conversation, Message
from tests.test_gmail_oauth import _connect, google  # noqa: F401 - `google` is a fixture
from tests.test_mailbox_access import _join

RULES = "/api/v1/automation/rules"


def _ready(client, google, *, on: bool = True) -> dict:
    """A connected mailbox that has synced once (so what comes next is new mail), with automation on."""
    google.deliver("old", "t-old", sender="Old Friend <old@example.com>", subject="Invoice from last year", body="Old mail.", message_id="<old@example.com>")
    account = _connect(client)
    assert client.post(f"/api/v1/email-accounts/{account['id']}/sync").status_code == 200
    if on:
        assert client.put("/api/v1/automation/settings", json={"enabled": True}).status_code == 200
    return account


def _rule(client, name="Invoices", conditions=None, actions_=None, **extra):
    body = {"name": name, "conditions": conditions if conditions is not None else {"subject": "invoice"}, "actions": actions_ or [{"type": "flag"}], **extra}
    response = client.post(RULES, json=body)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _arrive(client, google, account, gmail_id="n1", subject="Invoice 2001", sender="Maya Chen <maya@example.com>", body="Please pay.", **kw):
    google.deliver(gmail_id, f"t-{gmail_id}", sender=sender, subject=subject, body=body, message_id=f"<{gmail_id}@example.com>", **kw)
    assert client.post(f"/api/v1/email-accounts/{account['id']}/sync").status_code == 200


def _conv(client, subject):
    return next(c for c in client.get("/api/v1/conversations?view=inbox").json()["data"] if c["subject"] == subject)


def _runs(client, **params):
    return client.get("/api/v1/automation/runs", params=params).json()["data"]


def test_a_rule_acts_on_new_mail_that_matches_and_leaves_the_rest(client, member, google, db):
    account = _ready(client, google)
    label = client.post("/api/v1/labels", json={"name": "Billing", "color": "green"}).json()["data"]
    rule = _rule(client, actions_=[{"type": "add_label", "label_id": label["id"]}, {"type": "set_priority", "value": "high"}, {"type": "set_status", "value": "pending"}, {"type": "flag"}])
    assert rule["summary"] == "If subject contains “invoice” → add the label Billing, set priority to high, set status to pending, flag it"

    _arrive(client, google, account, "n1", "Invoice 2001")
    _arrive(client, google, account, "n2", "Lunch on Friday")

    invoice, lunch = _conv(client, "Invoice 2001"), _conv(client, "Lunch on Friday")
    assert invoice["priority"] == "high" and invoice["status"] == "pending" and invoice["is_starred"] is True
    assert [item["name"] for item in invoice["labels"]] == ["Billing"]
    assert lunch["priority"] == "normal" and lunch["status"] == "open" and lunch["is_starred"] is False and lunch["labels"] == []
    assert [c["subject"] for c in client.get("/api/v1/conversations?view=inbox&priority=high").json()["data"]] == ["Invoice 2001"]

    history = _runs(client)
    assert len(history) == 1
    assert history[0]["rule_name"] == "Invoices" and history[0]["subject"] == "Invoice 2001" and history[0]["status"] == "done" and history[0]["attempts"] == 1
    assert history[0]["done"] == ["Added the label Billing", "Set priority to high", "Set status to pending", "Flagged it"]
    listed = client.get(RULES).json()["data"][0]
    assert listed["run_count"] == 1 and listed["failed_count"] == 0 and listed["last_run_at"]


def test_mail_that_was_already_there_is_never_touched(client, member, google, db):
    """The first sync and the import of old mail bring in history, not new mail."""
    client.put("/api/v1/automation/settings", json={"enabled": True})
    google.deliver("old", "t-old", sender="Old Friend <old@example.com>", subject="Invoice from last year", body="Old mail.", message_id="<old@example.com>")
    account = _connect(client)
    _rule(client)
    client.post(f"/api/v1/email-accounts/{account['id']}/sync")
    assert _conv(client, "Invoice from last year")["is_starred"] is False
    assert _runs(client) == []


def test_every_condition_must_hold(client, member, google):
    account = _ready(client, google)
    _rule(client, "Narrow", {"sender": "maya@", "recipient": "team@gmail", "subject": "invoice", "body": "overdue", "has_attachments": True, "account_id": account["id"]})
    _arrive(client, google, account, "n1", "Invoice A", body="This is overdue.")  # no attachment
    _arrive(client, google, account, "n2", "Invoice B", body="This is OVERDUE.", files=[("a.pdf", b"x")], sender="Omar <omar@example.com>")  # another sender
    _arrive(client, google, account, "n3", "INVOICE C", body="Now overdue.", files=[("a.pdf", b"x")])
    assert [c["subject"] for c in client.get("/api/v1/conversations?view=inbox&starred=true").json()["data"]] == ["INVOICE C"]

    # A rule with no conditions matches every new email.
    _rule(client, "Everything", {}, [{"type": "set_priority", "value": "low"}])
    _arrive(client, google, account, "n4", "Anything at all")
    assert _conv(client, "Anything at all")["priority"] == "low"


def test_a_rule_runs_once_per_email_however_often_it_is_seen(client, member, google, db):
    account = _ready(client, google)
    rule = _rule(client, actions_=[{"type": "notify", "user_id": member["user"]["id"]}])
    _arrive(client, google, account)
    message_id = db.scalar(select(Message.id).where(Message.subject == "Invoice 2001"))
    workspace_id = db.scalar(select(Conversation.workspace_id))

    assert engine.run_for_messages(db, workspace_id, account["id"], [message_id]) == 0
    assert engine.run_for_messages(db, workspace_id, account["id"], [message_id, message_id]) == 0
    client.post(f"/api/v1/email-accounts/{account['id']}/sync")

    assert len(_runs(client)) == 1
    assert client.get(RULES).json()["data"][0]["run_count"] == 1
    assert len(client.get("/api/v1/notifications").json()["data"]["items"]) == 1
    assert db.scalar(select(RuleRun.rule_id)) == rule["id"]


def test_rules_run_in_order_and_a_later_rule_has_the_last_word(client, member, google):
    account = _ready(client, google)
    first = _rule(client, "First", {"subject": "invoice"}, [{"type": "set_priority", "value": "high"}])
    second = _rule(client, "Second", {"sender": "maya"}, [{"type": "set_priority", "value": "urgent"}])
    _arrive(client, google, account, "n1", "Invoice 1")
    assert _conv(client, "Invoice 1")["priority"] == "urgent"

    assert client.put(f"{RULES}/order", json={"rule_ids": [second["id"]]}).status_code == 422
    assert client.put(f"{RULES}/order", json={"rule_ids": [second["id"], first["id"]]}).status_code == 204
    assert [r["name"] for r in client.get(RULES).json()["data"]] == ["Second", "First"]
    _arrive(client, google, account, "n2", "Invoice 2")
    assert _conv(client, "Invoice 2")["priority"] == "high"
    assert len(_runs(client)) == 4 and len(_runs(client, rule_id=first["id"])) == 2


def test_nothing_runs_while_automation_a_mailbox_or_the_rule_is_off(client, member, google):
    account = _ready(client, google, on=False)
    rule = _rule(client)
    assert client.get("/api/v1/automation/settings").json()["data"] == {"enabled": False, "mailboxes": [{"account_id": account["id"], "email_address": "team@gmail.com", "enabled": True}]}

    _arrive(client, google, account, "n1", "Invoice while off")
    client.put("/api/v1/automation/settings", json={"enabled": True, "mailboxes": {account["id"]: False}})
    _arrive(client, google, account, "n2", "Invoice while the mailbox is off")
    client.put("/api/v1/automation/settings", json={"mailboxes": {account["id"]: True}})
    assert client.patch(f"{RULES}/{rule['id']}", json={"enabled": False}).json()["data"]["enabled"] is False
    _arrive(client, google, account, "n3", "Invoice while the rule is off")
    assert _runs(client) == []

    client.patch(f"{RULES}/{rule['id']}", json={"enabled": True})
    _arrive(client, google, account, "n4", "Invoice at last")
    assert [r["subject"] for r in _runs(client)] == ["Invoice at last"]  # what arrived while off stays untouched
    assert client.put("/api/v1/automation/settings", json={"mailboxes": {999999: True}}).status_code == 404


def test_assigning_gives_the_work_to_people_who_can_use_the_mailbox(client, member, google):
    account = _ready(client, google)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    alan, alan_id = _join(client, "alan@example.com", "Alan Turing", "agent")
    _rule(client, "Share out", {}, [{"type": "assign_in_turn", "user_ids": [grace_id, alan_id]}])
    for n in range(1, 5):
        _arrive(client, google, account, f"n{n}", f"Question {n}")
    assert [_conv(client, f"Question {n}")["assignee_name"] for n in range(1, 5)] == ["Grace Hopper", "Alan Turing", "Grace Hopper", "Alan Turing"]
    told = grace.get("/api/v1/notifications").json()["data"]
    assert told["unread"] == 2 and told["items"][0]["title"] == "The rule “Share out” assigned you a conversation"

    # Alan loses the mailbox: his turn passes to Grace, and a rule naming only him skips and says why.
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "members": [{"user_id": grace_id, "permission": "send"}]})
    _rule(client, "Only Alan", {"subject": "question 6"}, [{"type": "assign", "user_id": alan_id}, {"type": "flag"}])
    _arrive(client, google, account, "n5", "Question 5")
    _arrive(client, google, account, "n6", "Question 6")
    assert _conv(client, "Question 5")["assignee_name"] == "Grace Hopper"
    six = _conv(client, "Question 6")
    assert six["assignee_name"] == "Grace Hopper" and six["is_starred"] is True
    skipped = next(r for r in _runs(client) if r["rule_name"] == "Only Alan")
    assert skipped["status"] == "done" and skipped["done"] == ["Skipped: Alan Turing cannot use this mailbox", "Flagged it"]
    assert alan.get("/api/v1/automation/runs").json()["data"] == []  # and he cannot read the history of a mailbox he cannot open


def test_a_failed_run_keeps_nothing_is_recorded_and_is_tried_again(client, member, google, db, monkeypatch):
    account = _ready(client, google)
    _rule(client, actions_=[{"type": "set_priority", "value": "urgent"}, {"type": "flag"}])

    def broken(*_args):
        raise RuntimeError("database went away")

    monkeypatch.setitem(actions.ACTIONS, "flag", broken)
    _arrive(client, google, account)
    conversation = _conv(client, "Invoice 2001")
    assert conversation["priority"] == "normal" and conversation["is_starred"] is False  # the half that worked was undone
    failed = _runs(client)[0]
    assert failed["status"] == "failed" and failed["attempts"] == 1 and failed["error"] == "database went away" and failed["done"] == []
    assert client.get(RULES).json()["data"][0]["failed_count"] == 1
    assert client.get("/api/v1/email-accounts").json()["data"][0]["status"] == "connected"  # mail itself is unaffected

    assert engine.retry_failed(db) == 0  # not due yet
    run = db.scalar(select(RuleRun))
    run.next_attempt_at = utcnow() - timedelta(seconds=1)
    db.commit()
    monkeypatch.setitem(actions.ACTIONS, "flag", actions.flag)
    assert engine.retry_failed(db) == 1
    conversation = _conv(client, "Invoice 2001")
    assert conversation["priority"] == "urgent" and conversation["is_starred"] is True
    done = _runs(client)[0]
    assert done["status"] == "done" and done["attempts"] == 2 and done["error"] is None
    assert client.get(RULES).json()["data"][0]["failed_count"] == 0


def test_after_three_failures_it_gives_up(client, member, google, db, monkeypatch):
    account = _ready(client, google)
    _rule(client)
    monkeypatch.setitem(actions.ACTIONS, "flag", lambda *_a: 1 / 0)
    _arrive(client, google, account)
    for _ in range(4):
        db.rollback()
        run = db.scalar(select(RuleRun))
        if run.next_attempt_at:
            run.next_attempt_at = utcnow() - timedelta(seconds=1)
            db.commit()
        engine.retry_failed(db)
    last = _runs(client)[0]
    assert last["status"] == "gave_up" and last["attempts"] == engine.MAX_ATTEMPTS
    summary = client.get("/api/v1/automation/summary").json()["data"]
    assert summary["failed_today"] == 1 and summary["runs_today"] == 1 and summary["rules_on"] == 1 and summary["enabled"] is True


def test_testing_a_rule_shows_what_it_would_match_and_changes_nothing(client, member, google, db):
    account = _ready(client, google)
    _arrive(client, google, account, "n1", "Invoice 2001")
    _arrive(client, google, account, "n2", "Lunch on Friday")
    result = client.post(f"{RULES}/test", json={"name": "Try", "conditions": {"subject": "invoice"}, "actions": [{"type": "archive"}]}).json()["data"]
    assert result["checked"] == 3 and [m["subject"] for m in result["matches"]] == ["Invoice 2001", "Invoice from last year"]
    assert db.scalars(select(Rule)).all() == [] and db.scalars(select(RuleRun)).all() == []
    assert db.scalar(select(Conversation.is_archived).where(Conversation.subject == "Invoice 2001")) is False


def test_who_may_change_rules_and_what_a_rule_may_point_at(client, member, google):
    account = _ready(client, google)
    manager, _ = _join(client, "mary@example.com", "Mary Manager", "manager")
    agent, agent_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    body = {"name": "Mine", "conditions": {}, "actions": [{"type": "flag"}]}

    assert agent.post(RULES, json=body).status_code == 403
    made = manager.post(RULES, json=body)
    assert made.status_code == 201 and made.json()["data"]["created_by_name"] == "Mary Manager"
    rule_id = made.json()["data"]["id"]
    assert [r["name"] for r in agent.get(RULES).json()["data"]] == ["Mine"]  # everyone can see them
    assert agent.put(f"{RULES}/{rule_id}", json=body).status_code == 403
    assert agent.patch(f"{RULES}/{rule_id}", json={"enabled": False}).status_code == 403
    assert agent.delete(f"{RULES}/{rule_id}").status_code == 403
    assert manager.put("/api/v1/automation/settings", json={"enabled": False}).status_code == 403  # the switch is for owners and admins

    for bad in ([{"type": "add_label", "label_id": 999}], [{"type": "assign", "user_id": 999}], [{"type": "assign_in_turn", "user_ids": [agent_id, 999]}], [{"type": "notify", "user_id": 999}]):
        assert client.post(RULES, json={**body, "actions": bad}).status_code == 404
    assert client.post(RULES, json={**body, "conditions": {"account_id": 999}}).status_code == 404
    for invalid in ([], [{"type": "send_email", "to": "x@example.com"}], [{"type": "set_priority", "value": "extreme"}]):
        assert client.post(RULES, json={**body, "actions": invalid}).status_code == 422

    changed = manager.put(f"{RULES}/{rule_id}", json={"name": "  Renamed   rule ", "conditions": {"subject": "x"}, "actions": [{"type": "archive"}]}).json()["data"]
    assert changed["name"] == "Renamed rule" and changed["summary"] == "If subject contains “x” → archive it"
    assert manager.delete(f"{RULES}/{rule_id}").status_code == 204
    assert client.get(RULES).json()["data"] == []
    assert account["id"]


def test_another_workspace_sees_none_of_it(client, member, google):
    account = _ready(client, google)
    rule = _rule(client)
    _arrive(client, google, account)

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import PASSWORD

    other = TestClient(app)
    assert other.post("/api/v1/auth/register", json={"email": "eve@example.com", "password": PASSWORD, "name": "Eve Elsewhere"}).status_code == 201
    assert other.post("/api/v1/workspaces", json={"name": "Elsewhere"}).status_code == 201
    assert other.get(RULES).json()["data"] == [] and other.get("/api/v1/automation/runs").json()["data"] == []
    assert other.get("/api/v1/automation/summary").json()["data"]["rules_total"] == 0
    body = {"name": "Theirs", "conditions": {}, "actions": [{"type": "flag"}]}
    assert other.put(f"{RULES}/{rule['id']}", json=body).status_code == 404
    assert other.delete(f"{RULES}/{rule['id']}").status_code == 404
    assert other.post(RULES, json={**body, "conditions": {"account_id": account["id"]}}).status_code == 404
    assert other.put("/api/v1/automation/settings", json={"mailboxes": {account["id"]: False}}).status_code == 404


def test_priority_can_also_be_set_by_hand(client, member, google):
    account = _ready(client, google)
    _arrive(client, google, account, "n1", "Server down")
    conversation = _conv(client, "Server down")
    assert client.patch(f"/api/v1/conversations/{conversation['id']}", json={"priority": "urgent"}).json()["data"]["priority"] == "urgent"
    assert client.patch(f"/api/v1/conversations/{conversation['id']}", json={"priority": "extreme"}).status_code == 422
    old = _conv(client, "Invoice from last year")
    assert client.post("/api/v1/conversations/batch", json={"conversation_ids": [conversation["id"], old["id"]], "action": "priority_low"}).json()["data"]["updated"] == 2
    assert {c["subject"] for c in client.get("/api/v1/conversations?view=inbox&priority=low").json()["data"]} == {"Server down", "Invoice from last year"}
    assert client.get("/api/v1/conversations?view=inbox&priority=urgent").json()["data"] == []


def test_rules_can_be_run_by_hand_on_mail_already_there(client, member, google):
    account = _ready(client, google, on=False)  # automation stays off throughout
    _arrive(client, google, account, "n1", "Invoice 2001")
    _arrive(client, google, account, "n2", "Lunch on Friday")
    _rule(client, actions_=[{"type": "set_priority", "value": "high"}, {"type": "notify", "user_id": member["user"]["id"]}])
    manager, _ = _join(client, "mary@example.com", "Mary Manager", "manager")
    assert manager.post("/api/v1/automation/run-recent", json={}).status_code == 403
    assert client.post("/api/v1/automation/run-recent", json={"per_mailbox": 0}).status_code == 422

    first = client.post("/api/v1/automation/run-recent", json={"per_mailbox": 2})
    assert first.status_code == 200 and first.json()["data"] == {"checked": 2, "runs": 1}  # only the latest two are looked at
    assert _conv(client, "Invoice 2001")["priority"] == "high" and _conv(client, "Invoice from last year")["priority"] == "normal"
    assert _runs(client)[0]["done"] == ["Set priority to high", "Skipped: nobody is notified about older mail"]
    assert client.get("/api/v1/notifications").json()["data"]["items"] == []

    again = client.post("/api/v1/automation/run-recent", json={}).json()["data"]
    assert again == {"checked": 3, "runs": 1}  # the older invoice is new to the rule; the one already handled is not repeated
    assert len(_runs(client)) == 2
    assert client.post("/api/v1/automation/run-recent", json={}).json()["data"] == {"checked": 3, "runs": 0}
