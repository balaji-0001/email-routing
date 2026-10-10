"""Regression tests for the security review of 2026-10-10. Each test names the hole it keeps closed."""

import smtplib
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, inspect, select

from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.models.automation import Reminder
from app.models.email import Conversation, EmailAccount, EmailAccountMember, Message
from app.models.workspace import WorkspaceMember
from app.providers import imap_smtp
from app.services import ai_triage, email_send, email_sync
from tests.conftest import PASSWORD
from tests.test_ai_triage import _mail, _waiting, ai  # noqa: F401 - fixture
from tests.test_ai_triage import _ready as _ai_ready
from tests.test_automation import RULES, _arrive, _conv, _ready, _rule
from tests.test_gmail_oauth import google  # noqa: F401 - fixture
from tests.test_mailbox_access import _join


def _second_mailbox(db, first_id: int, address: str) -> EmailAccount:
    """Another mailbox in the same workspace, copied from the first."""
    db.rollback()
    first = db.get(EmailAccount, first_id)
    values = {c.key: getattr(first, c.key) for c in inspect(EmailAccount).mapper.column_attrs if c.key != "id"}
    other = EmailAccount(**{**values, "email_address": address, "access_mode": "restricted"})
    db.add(other)
    db.commit()
    return other


def _item(mid: str, subject: str, sender: str, **more) -> dict:
    return {"provider_message_id": mid, "subject": subject, "sender_email": sender, "sender_name": "", "body_text": "Hello.", "snippet": "Hello.", **more}


# ---- threading: mail lands only where its readers are meant to see it ------------------------------------------------

def test_a_stranger_cannot_post_into_someone_elses_thread_by_copying_its_subject(client, member, google, db):
    account = _ready(client, google, on=False)
    db.rollback()
    box = db.get(EmailAccount, account["id"])
    ws = box.workspace_id
    assert email_sync._store_messages(db, box, ws, [_item("<a1@x>", "Invoice 77", "maya@example.com")]) == 1
    # No thread id (as with IMAP), same subject, different people.
    email_sync._store_messages(db, box, ws, [_item("<evil@x>", "Invoice 77", "mallory@example.net"), _item("<pct@x>", "%", "mallory@example.net"), _item("<sub@x>", "voice", "mallory@example.net")])
    # The original writer following up without a reply header is still threaded.
    email_sync._store_messages(db, box, ws, [_item("<a2@x>", "Re: Invoice 77", "maya@example.com")])
    db.commit()
    by_conversation = {}
    for message in db.scalars(select(Message).where(Message.provider_message_id.in_(["<a1@x>", "<a2@x>", "<evil@x>", "<pct@x>", "<sub@x>"]))):
        by_conversation.setdefault(message.conversation_id, set()).add(message.sender_email)
    assert sorted(map(sorted, by_conversation.values())) == [["mallory@example.net"], ["mallory@example.net"], ["mallory@example.net"], ["maya@example.com"]]


def test_a_reply_arriving_in_a_restricted_mailbox_is_not_filed_into_an_open_one(client, member, google, db):
    account = _ready(client, google, on=False)
    _arrive(client, google, account, "n1", "Pricing")
    private = _second_mailbox(db, account["id"], "ceo@gmail.com")
    email_sync._store_messages(db, private, private.workspace_id, [_item("<secret@x>", "Re: Pricing", "maya@example.com", in_reply_to="<n1@example.com>", body_text="For the CEO only.")])
    db.commit()
    secret = db.scalar(select(Message).where(Message.provider_message_id == "<secret@x>"))
    assert secret.email_account_id == private.id and db.get(Conversation, secret.conversation_id).email_account_id == private.id
    agent, _ = _join(client, "grace@example.com", "Grace Hopper", "agent")
    # There are now two conversations called "Pricing", one per mailbox. The agent may open only the open mailbox's.
    theirs = next(c for c in client.get("/api/v1/conversations?view=inbox").json()["data"] if c["subject"] == "Pricing" and c["email_account_id"] == account["id"])
    answer = agent.get(f"/api/v1/conversations/{theirs['id']}")
    assert answer.status_code == 200, answer.text
    open_thread = answer.json()["data"]
    assert "For the CEO only." not in str(open_thread)
    assert agent.get(f"/api/v1/conversations/{secret.conversation_id}").status_code == 404


def test_overlong_headers_are_stored_cut_down_rather_than_lost_and_an_email_is_stored_once(client, member, google, db):
    account = _ready(client, google, on=False)
    db.rollback()
    box = db.get(EmailAccount, account["id"])
    long = _item("<long@x>" + "i" * 400, "S" * 900, "a" * 400 + "@example.com", sender_name="N" * 600, in_reply_to="<" + "r" * 700 + ">")
    assert email_sync._store_messages(db, box, box.workspace_id, [long]) == 1
    db.commit()
    stored = db.scalar(select(Message).where(Message.provider_message_id.like("<long@x>%")))
    assert len(stored.subject) == 500 and len(stored.sender_name) == 255 and len(stored.sender_email) == 320 and len(stored.provider_message_id) == 255
    # The same email again, as two syncs racing would deliver it: the database refuses the second copy.
    assert email_sync._store_messages(db, box, box.workspace_id, [long]) == 0
    db.add(Message(workspace_id=box.workspace_id, conversation_id=stored.conversation_id, email_account_id=box.id, provider_message_id=stored.provider_message_id, sender_email="x@example.com"))
    with pytest.raises(Exception, match="uq_messages_account_provider_id|Duplicate"):
        db.commit()
    db.rollback()


# ---- sending -----------------------------------------------------------------------------------------------------------

def test_you_cannot_send_into_a_conversation_of_a_mailbox_you_are_not_sending_from(client, member, google, db):
    account = _ready(client, google, on=False)
    private = _second_mailbox(db, account["id"], "ceo@gmail.com")
    email_sync._store_messages(db, private, private.workspace_id, [_item("<p1@x>", "Board matter", "chair@example.com")])
    db.commit()
    theirs = db.scalar(select(Conversation).where(Conversation.email_account_id == private.id))
    before = (theirs.snippet, theirs.message_count)
    sent = client.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["x@example.com"], "subject": "Hi", "body_text": "Planted", "conversation_id": theirs.id})
    assert sent.status_code == 404 and google.sent == []
    db.rollback()
    theirs = db.get(Conversation, theirs.id)
    assert (theirs.snippet, theirs.message_count) == before


@pytest.mark.parametrize("field, value", [
    ("to", ["not-an-address"]), ("to", ["a@example.com\r\nBcc: victim@example.com"]), ("to", ["a@example.com, b@example.com"]),
    ("cc", ["<script>@x"]), ("subject", "S" * 501), ("to", [f"p{n}@example.com" for n in range(101)]),
])
def test_bad_addresses_and_subjects_are_refused_before_anything_is_sent(client, member, google, field, value):
    account = _ready(client, google, on=False)
    body = {"account_id": account["id"], "to": ["maya@example.com"], "subject": "Hello", "body_text": "Hi", field: value}
    assert client.post("/api/v1/messages/send", json=body).status_code == 422
    assert google.sent == []


def test_a_sent_email_that_cannot_be_saved_is_reported_as_sent_not_as_failed(client, member, google, db, ai, monkeypatch):
    account = _ai_ready(client, google)
    _mail(client, google, db, account)
    draft = _waiting(client)[0]
    monkeypatch.setattr(email_send.audit, "record", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("database went away")))
    answer = client.post(f"/api/v1/ai/replies/{draft['id']}/approve", json={"body_hash": draft["body_hash"]})
    assert answer.status_code == 500 and answer.json()["error"]["code"] == "SENT_NOT_RECORDED" and "Do not send it again" in answer.json()["error"]["message"]
    assert len(google.sent) == 1
    monkeypatch.undo()
    assert _waiting(client) == []  # not waiting, so nobody is invited to send it a second time
    assert client.post(f"/api/v1/ai/replies/{draft['id']}/approve", json={"body_hash": draft["body_hash"]}).status_code == 409
    assert len(google.sent) == 1


def test_a_send_cut_short_is_handed_back_to_a_person(client, member, google, db, ai):
    account = _ai_ready(client, google)
    _mail(client, google, db, account)
    draft = _waiting(client)[0]
    db.rollback()
    stuck = db.get(ai_triage.AiReply, draft["id"])
    stuck.status, stuck.decided_at = "sending", ai_triage.utcnow() - timedelta(hours=1)  # as a crash mid-send would leave it
    db.commit()
    ai_triage.process_pending(db)
    back = _waiting(client)[0]
    assert back["status"] == "failed" and "Sent folder" in back["error"] and google.sent == []


# ---- connecting a mailbox cannot be used to look around inside the server's network --------------------------------------

@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "192.168.1.10", "169.254.169.254", "::1"])
def test_mail_server_addresses_inside_the_network_are_refused(host):
    with pytest.raises(imap_smtp.HostNotAllowed):
        imap_smtp.assert_public_host(host)


def test_the_connect_form_only_takes_mail_ports_encryption_and_plain_host_names_and_says_little_on_failure(client, member):
    good = {"provider": "imap", "email_address": "box@company.com", "incoming_host": "localhost", "incoming_port": 993, "incoming_security": "ssl",
            "incoming_username": "box", "incoming_password": "pw", "outgoing_host": "localhost", "outgoing_port": 587, "outgoing_security": "starttls",
            "outgoing_username": "box", "outgoing_password": "pw"}
    for change in ({"incoming_port": 3306}, {"outgoing_port": 6379}, {"incoming_security": "none"}, {"outgoing_security": "none"}, {"incoming_host": "http://10.0.0.1/"},
                   {"incoming_host": "a b"}, {"provider": "anything"}, {"display_name": "x" * 121}):
        assert client.post("/api/v1/email-accounts/connect", json={**good, **change}).status_code == 422, change
    refused = client.post("/api/v1/email-accounts/connect", json=good)
    assert refused.status_code == 400 and refused.json()["error"]["message"] == "Could not connect. Incoming mail (IMAP): That server address is not a public mail server."
    assert imap_smtp._why(smtplib.SMTPAuthenticationError(535, b"5.7.8 secret banner text")) == "the username or password was not accepted."
    assert "banner" not in imap_smtp._why(RuntimeError("220 internal-db banner"))
    for _ in range(9):
        client.post("/api/v1/email-accounts/connect", json=good)
    assert client.post("/api/v1/email-accounts/connect", json=good).status_code == 429  # ten tries in ten minutes


def test_viewers_cannot_start_a_sync_and_nobody_can_hammer_it(client, member, google):
    account = _ready(client, google, on=False)
    viewer, _ = _join(client, "vera@example.com", "Vera Viewer", "viewer")
    assert viewer.post(f"/api/v1/email-accounts/{account['id']}/sync").status_code == 403
    assert viewer.post("/api/v1/email-accounts/sync-all").status_code == 403
    codes = [client.post("/api/v1/email-accounts/sync-all").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 200, 429]


# ---- roles and invitations ---------------------------------------------------------------------------------------------

def test_an_admin_cannot_make_owners_or_touch_the_owner(client, member, google, db):
    admin, admin_id = _join(client, "alan@example.com", "Alan Turing", "admin")
    friend, friend_id = _join(client, "eve@example.com", "Eve Adams", "viewer")
    rows = {m.user_id: m for m in db.scalars(select(WorkspaceMember))}
    owner_row, friend_row, admin_row = rows[member["user"]["id"]], rows[friend_id], rows[admin_id]
    assert admin.patch(f"/api/v1/workspace/members/{friend_row.id}", json={"role": "owner"}).status_code == 403
    assert admin.patch(f"/api/v1/workspace/members/{owner_row.id}", json={"role": "viewer"}).status_code == 403
    assert admin.delete(f"/api/v1/workspace/members/{owner_row.id}").status_code == 403
    assert admin.patch(f"/api/v1/workspace/members/{friend_row.id}", json={"role": "manager"}).status_code == 200  # ordinary changes still work
    # The owner can hand ownership on, and is then no longer the last one.
    assert client.patch(f"/api/v1/workspace/members/{admin_row.id}", json={"role": "owner"}).status_code == 200
    db.rollback()
    assert db.scalar(select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.role == "owner")) == 2


def test_an_invitation_works_once_and_only_for_the_person_it_was_sent_to(client, member):
    from fastapi.testclient import TestClient

    from app.main import app

    token = client.post("/api/v1/workspace/invitations", json={"email": "grace@example.com", "role": "admin"}).json()["data"]["token"]
    assert all(row["invite_url"] == "" for row in client.get("/api/v1/workspace/invitations").json()["data"])  # the list cannot leak a usable link
    thief = TestClient(app)
    assert thief.post("/api/v1/auth/register", json={"email": "mallory@example.net", "password": PASSWORD, "name": "Mallory"}).status_code == 201
    stolen = thief.post(f"/api/v1/auth/invitations/{token}/accept")
    assert stolen.status_code == 403 and stolen.json()["error"]["code"] == "INVITATION_NOT_YOURS"
    grace = TestClient(app)
    assert grace.post("/api/v1/auth/register", json={"email": "Grace@Example.com", "password": PASSWORD, "name": "Grace Hopper"}).status_code == 201
    assert grace.post(f"/api/v1/auth/invitations/{token}/accept").status_code == 200
    assert grace.post(f"/api/v1/auth/invitations/{token}/accept").status_code == 404


def test_what_a_person_was_given_goes_when_they_are_removed(client, member, google, db):
    account = _ready(client, google, on=False)
    _arrive(client, google, account, "n1", "Their case")
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    conversation = _conv(client, "Their case")
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "members": [{"user_id": grace_id, "permission": "send"}]})
    client.patch(f"/api/v1/conversations/{conversation['id']}", json={"assignee_user_id": grace_id})
    assert grace.post("/api/v1/reminders", json={"conversation_id": conversation["id"], "due_at": (ai_triage.utcnow() + timedelta(days=1)).isoformat() + "Z"}).status_code == 201
    row = db.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == grace_id))
    assert client.delete(f"/api/v1/workspace/members/{row.id}").status_code == 204
    db.rollback()
    assert db.scalars(select(EmailAccountMember).where(EmailAccountMember.user_id == grace_id)).all() == []
    assert db.get(Conversation, conversation["id"]).assignee_user_id is None
    assert db.scalar(select(Reminder.status).where(Reminder.user_id == grace_id)) == "cancelled"


# ---- inside a workspace: rules, mentions and settings respect who may open which mailbox ------------------------------------

def test_a_manager_shut_out_of_a_mailbox_cannot_aim_a_rule_at_it_or_watch_it_through_one(client, member, google, db):
    account = _ready(client, google)
    private = _second_mailbox(db, account["id"], "ceo@gmail.com")
    manager, _ = _join(client, "mary@example.com", "Mary Manager", "manager")
    flag = [{"type": "flag"}]
    assert manager.post(RULES, json={"name": "Everything", "conditions": {}, "actions": flag}).status_code == 403  # would cover the private mailbox too
    assert manager.post(RULES, json={"name": "Peek", "conditions": {"account_id": private.id, "body": "acquisition"}, "actions": flag}).status_code == 404
    hers = manager.post(RULES, json={"name": "Mine", "conditions": {"account_id": account["id"]}, "actions": flag})
    assert hers.status_code == 201
    owners = _rule(client, "Owner's rule for the private mailbox", {"account_id": private.id}, flag)
    assert [r["name"] for r in manager.get(RULES).json()["data"]] == ["Mine"]  # she is not shown the other rule or its counts
    for attempt in (manager.patch(f"{RULES}/{owners['id']}", json={"enabled": False}), manager.delete(f"{RULES}/{owners['id']}"),
                    manager.put(f"{RULES}/{owners['id']}", json={"name": "x", "conditions": {"account_id": account["id"]}, "actions": flag})):
        assert attempt.status_code == 404
    assert [m["email_address"] for m in manager.get("/api/v1/automation/settings").json()["data"]["mailboxes"]] == ["team@gmail.com"]
    assert [m["email_address"] for m in manager.get("/api/v1/ai/settings").json()["data"]["mailboxes"]] == ["team@gmail.com"]
    assert len(client.get(RULES).json()["data"]) == 2


def test_naming_someone_in_a_note_does_not_send_it_to_a_person_who_may_not_open_the_mailbox(client, member, google, db):
    account = _ready(client, google, on=False)
    _arrive(client, google, account, "n1", "Salary review")
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    alan, alan_id = _join(client, "alan@example.com", "Alan Turing", "agent")
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "members": [{"user_id": grace_id, "permission": "read"}]})
    conversation = _conv(client, "Salary review")
    assert client.post(f"/api/v1/conversations/{conversation['id']}/notes", json={"body": "@Grace @Alan the figure is 90k"}).status_code == 201
    assert len(grace.get("/api/v1/notifications").json()["data"]["items"]) == 1
    assert alan.get("/api/v1/notifications").json()["data"]["items"] == []


def test_the_business_information_is_only_shown_to_those_who_manage_it_and_the_mailbox_switch_binds_analyse_now(client, member, google, db, ai):
    account = _ai_ready(client, google, info="Margins: 62 percent. Do not share.")
    agent, _ = _join(client, "grace@example.com", "Grace Hopper", "agent")
    seen = agent.get("/api/v1/ai/settings").json()["data"]
    assert seen["business_info"] == "" and seen["has_business_info"] is True
    assert client.get("/api/v1/ai/settings").json()["data"]["business_info"].startswith("Margins")
    _arrive(client, google, account, "n1", "A question")
    client.put("/api/v1/ai/settings", json={"mailboxes": {account["id"]: False}})
    calls = len(ai.requests)
    refused = agent.post(f"/api/v1/ai/conversations/{_conv(client, 'A question')['id']}/analyse")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "AI_OFF" and len(ai.requests) == calls


def test_ai_requests_are_limited_per_person(client, member, google, ai):
    _ai_ready(client, google)
    ai.answer = {"subject": "s", "body": "Hello there."}
    codes = [client.post("/api/v1/ai/write", json={"instruction": "say hello"}).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


# ---- the front door ---------------------------------------------------------------------------------------------------------

def test_every_answer_carries_the_protective_headers_and_cross_site_changes_are_refused(client, member):
    response = client.get("/api/v1/auth/me")
    assert response.headers["x-content-type-options"] == "nosniff" and response.headers["x-frame-options"] == "DENY" and response.headers["referrer-policy"] == "no-referrer"
    assert client.post("/api/v1/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/v1/labels", content=b"x", headers={"Content-Length": str(31 * 1024 * 1024), "Content-Type": "application/json"}).status_code == 413
    assert client.get("/api/v1/auth/me", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200  # reading is not blocked, only changing


def test_login_is_limited_per_address_from_everywhere_and_the_limiter_forgets_idle_keys(client, member, monkeypatch):
    from app.services import auth

    codes = []
    for attempt in range(45):
        monkeypatch.setattr(auth, "LOGIN_ATTEMPTS", auth.LOGIN_ATTEMPTS)  # no-op, keeps the constant in view
        codes.append(client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": f"wrong-password-{attempt}"}, headers={"X-Test": str(attempt)}).status_code)
    assert codes[0] == 401 and codes[-1] == 429

    limiter = RateLimiter()
    limiter.check("never-recorded", limit=1, window_seconds=60)
    assert limiter._attempts == {}  # merely asking does not store anything
    limiter.record("once", window_seconds=0)
    limiter.check("once", limit=1, window_seconds=0)
    assert limiter._attempts == {}  # and an expired key is dropped


def test_production_refuses_to_start_half_configured():
    base = {"_env_file": None, "app_env": "production"}
    with pytest.raises(ValidationError, match="ENCRYPTION_KEY"):
        Settings(**base, app_url="https://mail.example.com", database_url="mysql+pymysql://app:pw@db.internal/prod")
    with pytest.raises(ValidationError, match="APP_URL"):
        Settings(**base, encryption_key="k" * 32, database_url="mysql+pymysql://app:pw@db.internal/prod")
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(**base, encryption_key="k" * 32, app_url="https://mail.example.com")
    ok = Settings(**base, encryption_key="k" * 32, app_url="https://mail.example.com", database_url="mysql+pymysql://app:pw@db.internal/prod")
    assert ok.is_production
    assert Settings(_env_file=None, app_env="staging", encryption_key="k" * 32, app_url="https://s.example.com", database_url="mysql+pymysql://app:pw@db/x").is_production
    assert not Settings(_env_file=None, app_env="development").is_production


def test_nulls_and_unknown_actions_in_updates_are_handled_not_stored(client, member, google):
    account = _ready(client, google, on=False)
    _arrive(client, google, account, "n1", "A thing")
    conversation = _conv(client, "A thing")
    answer = client.patch(f"/api/v1/conversations/{conversation['id']}", json={"status": None, "priority": None, "is_starred": True})
    assert answer.status_code == 200 and answer.json()["data"]["status"] == "open" and answer.json()["data"]["is_starred"] is True
    assert client.post("/api/v1/conversations/batch", json={"conversation_ids": [conversation["id"]], "action": "explode"}).status_code == 422
    assert client.post("/api/v1/conversations/batch", json={"conversation_ids": list(range(501)), "action": "star"}).status_code == 422
    viewer, _ = _join(client, "vera@example.com", "Vera Viewer", "viewer")
    client.patch(f"/api/v1/conversations/{conversation['id']}", json={"is_read": False})
    assert viewer.get(f"/api/v1/conversations/{conversation['id']}").status_code == 200
    assert _conv(client, "A thing")["is_read"] is False  # a viewer looking does not mark it read for the team
