import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import utcnow
from app.main import app
from app.models import AuthSession, PasswordResetToken, User
from tests.conftest import PASSWORD

COOKIE = "em_session"


def register(client, email="ada@example.com", password=PASSWORD, name="Ada Lovelace"):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": name})


def login(client, email="ada@example.com", password=PASSWORD, remember=False):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password, "remember": remember})


def error_code(response):
    return response.json()["error"]["code"]


# --- signing up -----------------------------------------------------------


def test_register_creates_the_account_and_signs_in(client, db):
    response = register(client, email="  Ada@Example.com ", name="  Ada   King Lovelace ")
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["user"]["email"] == "ada@example.com"
    assert (data["user"]["first_name"], data["user"]["last_name"]) == ("Ada", "King Lovelace")
    assert data["workspace"] is None and data["role"] is None

    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["user"]["name"] == "Ada King Lovelace"
    assert me.json()["data"]["user"]["created_at"].endswith("Z")


def test_register_keeps_the_browser_time_zone(client):
    response = client.post("/api/v1/auth/register", json={"email": "ada@example.com", "password": PASSWORD, "name": "Ada", "timezone": "Asia/Calcutta"})
    assert response.json()["data"]["user"]["timezone"] == "Asia/Calcutta"
    created = client.post("/api/v1/workspaces", json={"name": "Engines"}).json()["data"]
    assert created["timezone"] == "Asia/Calcutta"
    bad = TestClient(app).post("/api/v1/auth/register", json={"email": "bob@example.com", "password": PASSWORD, "name": "Bob", "timezone": "Mars/Olympus"})
    assert bad.status_code == 422


def test_secrets_are_stored_hashed(client, db):
    register(client)
    user = db.scalar(select(User))
    assert user.password_hash.startswith("$argon2") and PASSWORD not in user.password_hash
    session = db.scalar(select(AuthSession))
    assert session.token_hash != client.cookies[COOKIE] and len(session.token_hash) == 64


def test_register_rejects_an_email_that_is_taken(client):
    register(client)
    again = register(TestClient(app), email="ADA@example.com")
    assert again.status_code == 409 and error_code(again) == "EMAIL_TAKEN"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"email": "not-an-email", "password": PASSWORD, "name": "Ada"}, "email"),
        ({"email": "ada@example.com", "password": "short", "name": "Ada"}, "password"),
        ({"email": "ada@example.com", "password": PASSWORD, "name": "   "}, "name"),
    ],
)
def test_register_validates_input(client, payload, field):
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422 and error_code(response) == "VALIDATION_ERROR"
    assert [detail["field"] for detail in response.json()["error"]["details"]] == [field]


# --- signing in and out ---------------------------------------------------


def test_login_and_logout(client):
    register(client)
    other = TestClient(app)
    assert other.get("/api/v1/auth/me").status_code == 401

    response = login(other)
    assert response.status_code == 200
    assert other.get("/api/v1/auth/me").json()["data"]["user"]["email"] == "ada@example.com"

    token = other.cookies[COOKIE]
    assert other.post("/api/v1/auth/logout").status_code == 204
    assert COOKIE not in other.cookies
    assert other.get("/api/v1/auth/me").status_code == 401

    # A copy of the old cookie is worthless after signing out.
    replay = TestClient(app, cookies={COOKIE: token})
    assert replay.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_and_unknown_email_look_the_same(client):
    register(client)
    wrong = login(TestClient(app), password="not-the-password")
    unknown = login(TestClient(app), email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert error_code(wrong) == "INVALID_CREDENTIALS"


def test_me_requires_a_session(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401 and error_code(response) == "NOT_SIGNED_IN"


def test_remember_me_controls_how_long_the_cookie_lasts(client):
    register(client)
    short = login(TestClient(app)).headers["set-cookie"].lower()
    long = login(TestClient(app), remember=True).headers["set-cookie"].lower()
    assert "max-age" not in short
    assert f"max-age={30 * 24 * 60 * 60}" in long


def test_an_expired_session_stops_working(client, db):
    register(client)
    session = db.scalar(select(AuthSession))
    session.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_repeated_wrong_passwords_are_locked_out(client):
    register(client)
    attacker = TestClient(app)
    for _ in range(8):
        assert login(attacker, password="guess-guess").status_code == 401
    blocked = login(attacker, password="guess-guess")
    assert blocked.status_code == 429 and error_code(blocked) == "TOO_MANY_ATTEMPTS"
    assert int(blocked.headers["retry-after"]) > 0
    # Even the right password has to wait, or the lock would be pointless.
    assert login(attacker).status_code == 429


def test_requests_from_another_site_are_refused(client):
    register(client)
    foreign = client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"})
    assert foreign.status_code == 403 and error_code(foreign) == "ORIGIN_NOT_ALLOWED"
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout", headers={"Origin": "http://localhost:5173"}).status_code == 204


# --- passwords and sessions -----------------------------------------------


def test_change_password_signs_out_other_browsers(client):
    register(client)
    laptop = TestClient(app)
    login(laptop)

    wrong = client.post("/api/v1/auth/password/change", json={"current_password": "nope-nope", "new_password": "a-brand-new-password"})
    assert wrong.status_code == 400 and error_code(wrong) == "WRONG_PASSWORD"
    same = client.post("/api/v1/auth/password/change", json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.status_code == 400 and error_code(same) == "PASSWORD_UNCHANGED"

    changed = client.post("/api/v1/auth/password/change", json={"current_password": PASSWORD, "new_password": "a-brand-new-password"})
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 200
    assert laptop.get("/api/v1/auth/me").status_code == 401
    assert login(TestClient(app)).status_code == 401
    assert login(TestClient(app), password="a-brand-new-password").status_code == 200


def test_sessions_can_be_listed_and_others_ended(client):
    register(client)
    laptop = TestClient(app, headers={"User-Agent": "Laptop"})
    login(laptop)

    listed = client.get("/api/v1/auth/sessions").json()["data"]
    assert len(listed) == 2
    assert [s["current"] for s in listed].count(True) == 1
    assert "Laptop" in [s["user_agent"] for s in listed]

    assert client.post("/api/v1/auth/sessions/revoke-others").json()["data"] == {"ended": 1}
    assert laptop.get("/api/v1/auth/me").status_code == 401
    assert len(client.get("/api/v1/auth/sessions").json()["data"]) == 1


# --- forgotten passwords --------------------------------------------------


def test_password_reset_is_unavailable_until_email_is_configured(client):
    register(client)
    assert client.get("/api/v1/auth/options").json()["data"] == {"password_reset_available": False}
    response = client.post("/api/v1/auth/password/forgot", json={"email": "ada@example.com"})
    assert response.status_code == 503 and error_code(response) == "EMAIL_NOT_CONFIGURED"


@pytest.fixture
def outbox(monkeypatch):
    """Outgoing email switched on, with messages captured instead of sent."""
    sent = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@example.com")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.email.send_email", lambda to, subject, body: sent.append({"to": to, "subject": subject, "body": body}))
    return sent


def test_password_reset_by_emailed_link(client, db, outbox):
    register(client)
    visitor = TestClient(app)
    assert visitor.get("/api/v1/auth/options").json()["data"] == {"password_reset_available": True}

    # Same answer whether or not the address has an account.
    assert visitor.post("/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}).status_code == 202
    assert outbox == []
    assert visitor.post("/api/v1/auth/password/forgot", json={"email": "ADA@example.com"}).status_code == 202
    assert len(outbox) == 1 and outbox[0]["to"] == "ada@example.com"

    token = re.search(r"http://localhost:5173/reset-password\?token=(\S+)", outbox[0]["body"]).group(1)
    assert db.scalar(select(PasswordResetToken)).token_hash != token

    short = visitor.post("/api/v1/auth/password/reset", json={"token": token, "password": "tiny"})
    assert short.status_code == 422

    done = visitor.post("/api/v1/auth/password/reset", json={"token": token, "password": "a-brand-new-password"})
    assert done.status_code == 204
    # Everyone is signed out, the old password is dead, the new one works.
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(TestClient(app)).status_code == 401
    assert login(TestClient(app), password="a-brand-new-password").status_code == 200

    reused = visitor.post("/api/v1/auth/password/reset", json={"token": token, "password": "yet-another-password"})
    assert reused.status_code == 400 and error_code(reused) == "RESET_LINK_INVALID"


def test_a_reset_link_expires_and_a_newer_link_replaces_it(client, db, outbox):
    register(client)
    visitor = TestClient(app)
    visitor.post("/api/v1/auth/password/forgot", json={"email": "ada@example.com"})
    visitor.post("/api/v1/auth/password/forgot", json={"email": "ada@example.com"})
    first, second = (re.search(r"token=(\S+)", message["body"]).group(1) for message in outbox)

    replaced = visitor.post("/api/v1/auth/password/reset", json={"token": first, "password": "a-brand-new-password"})
    assert replaced.status_code == 400

    live = db.scalar(select(PasswordResetToken).where(PasswordResetToken.used_at.is_(None)))
    live.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    expired = visitor.post("/api/v1/auth/password/reset", json={"token": second, "password": "a-brand-new-password"})
    assert expired.status_code == 400 and error_code(expired) == "RESET_LINK_INVALID"


# --- plumbing -------------------------------------------------------------


def test_health_and_unknown_routes(client):
    assert client.get("/api/healthz").json() == {"status": "ok"}
    missing = client.get("/api/v1/nope")
    assert missing.status_code == 404 and error_code(missing) == "NOT_FOUND"
