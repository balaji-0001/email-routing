"""Notifications also go out by email: once each, only to people who want them, and never in a loop."""

import smtplib
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.automation import scheduler
from app.core.config import get_settings
from app.core.database import utcnow
from app.models.collab import Notification
from app.services import notify_email
from tests.test_automation import _arrive, _conv, _ready, _rule, _runs
from tests.test_gmail_oauth import google  # noqa: F401 - fixture
from tests.test_mailbox_access import _join


class FakeSMTP:
    sent: list = []
    fail = False

    def __init__(self, host, port, timeout=None):
        assert host == "smtp.test" and port == 587

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self):
        pass

    def login(self, username, password):
        assert (username, password) == ("robot@acme.test", "app-password")

    def send_message(self, message):
        if FakeSMTP.fail:
            raise smtplib.SMTPServerDisconnected("gone")
        FakeSMTP.sent.append(message)


@pytest.fixture
def smtp(monkeypatch):
    for key, value in {"SMTP_HOST": "smtp.test", "SMTP_PORT": "587", "SMTP_USERNAME": "robot@acme.test", "SMTP_PASSWORD": "app-password", "SMTP_FROM": "Acme <robot@acme.test>"}.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    FakeSMTP.sent, FakeSMTP.fail = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def _assign_to(client, google, account, person_id, gmail_id="n1", subject="Quote for Maya"):
    _arrive(client, google, account, gmail_id, subject)
    conversation = _conv(client, subject)
    assert client.patch(f"/api/v1/conversations/{conversation['id']}", json={"assignee_user_id": person_id}).status_code == 200
    return conversation


def test_a_notification_is_emailed_once_with_a_link(client, member, google, db, smtp):
    account = _ready(client, google, on=False)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    assert grace.get("/api/v1/notifications/email").json()["data"] == {"available": True, "enabled": True, "address": "grace@example.com"}
    conversation = _assign_to(client, google, account, grace_id)

    scheduler.tick()
    scheduler.tick()
    assert len(smtp.sent) == 1
    message = smtp.sent[0]
    assert message["To"] == "grace@example.com" and message["From"] == "Acme <robot@acme.test>" and message["Subject"].startswith("[Email Routing] ")
    body = message.get_content()
    assert f"http://localhost:5173/inbox?c={conversation['id']}" in body and "Quote for Maya" in body and "Settings > Profile" in body
    db.rollback()
    assert [n.email_state for n in db.scalars(select(Notification))] == ["sent"]


def test_people_who_switch_it_off_or_have_already_seen_it_get_no_email(client, member, google, db, smtp):
    account = _ready(client, google, on=False)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    alan, alan_id = _join(client, "alan@example.com", "Alan Turing", "agent")
    assert grace.put("/api/v1/notifications/email", json={"enabled": False}).json()["data"]["enabled"] is False
    assert grace.put("/api/v1/notifications/email", json={"enabled": "no"}).status_code == 422
    _assign_to(client, google, account, grace_id, "n1", "For Grace")
    _assign_to(client, google, account, alan_id, "n2", "For Alan")
    assert alan.post("/api/v1/notifications/read", json={"ids": []}).status_code == 204  # he reads it in the app first

    _assign_to(client, google, account, alan_id, "n3", "Stale for Alan")
    db.rollback()
    stale = db.scalars(select(Notification).order_by(Notification.id.desc())).first()
    stale.created_at = utcnow() - timedelta(days=2)
    db.commit()

    assert notify_email.send_pending(db) == 0 and smtp.sent == []
    db.rollback()
    assert {n.email_state for n in db.scalars(select(Notification))} == {"skipped"}
    assert alan.get("/api/v1/notifications/email").json()["data"]["enabled"] is True  # one person's choice is theirs alone


def test_a_failed_email_is_tried_three_times_and_nothing_waits_when_email_is_not_set_up(client, member, google, db, smtp):
    account = _ready(client, google, on=False)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    _assign_to(client, google, account, grace_id)
    smtp.fail = True
    for expected in ("pending", "pending", "failed", "failed"):
        notify_email.send_pending(db)
        db.rollback()
        assert db.scalar(select(Notification.email_state)) == expected
    assert db.scalar(select(Notification.email_attempts)) == 3 and smtp.sent == []
    assert len(grace.get("/api/v1/notifications").json()["data"]["items"]) == 1  # still there in the app

    smtp.fail = False
    _assign_to(client, google, account, grace_id, "n2", "Second one")
    db.rollback()  # see what was just stored
    notify_email.send_pending(db)
    assert len(smtp.sent) == 1 and "Second one" in smtp.sent[0].get_content()


def test_without_smtp_nothing_is_sent_and_nothing_is_kept_for_later(client, member, google, db, monkeypatch):
    account = _ready(client, google, on=False)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    assert grace.get("/api/v1/notifications/email").json()["data"]["available"] is False
    _assign_to(client, google, account, grace_id)
    assert notify_email.send_pending(db) == 0
    db.rollback()
    assert db.scalar(select(Notification.email_state)) == "skipped"


def test_the_apps_own_emails_never_set_off_rules(client, member, google, db, smtp):
    """A notification email can land in a connected mailbox. It must not cause another notification."""
    account = _ready(client, google)
    _rule(client, "Everything", {}, [{"type": "flag"}, {"type": "notify", "user_id": member["user"]["id"]}])
    _arrive(client, google, account, "n1", "[Email Routing] The rule “Everything” matched a new email", sender="Acme <robot@acme.test>")
    _arrive(client, google, account, "n2", "Urgent: from the same address, but a real email", sender="Acme <robot@acme.test>")
    _arrive(client, google, account, "n3", "[Email Routing] spoofed by someone else", sender="Mallory <mallory@example.com>")
    assert sorted(r["subject"] for r in _runs(client)) == ["Urgent: from the same address, but a real email", "[Email Routing] spoofed by someone else"]
