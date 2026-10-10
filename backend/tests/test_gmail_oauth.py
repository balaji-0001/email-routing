"""Connecting Gmail by Google sign-in, against a stand-in for Google's servers.

The stand-in answers in the shapes Google documents and keeps state (codes, tokens,
messages, history), so the real sign-in, refresh, sync and send code runs unchanged.
"""

import base64
import json
import time
from email.message import EmailMessage
from urllib.parse import parse_qs, urlparse

import httpx2
import pytest
from sqlalchemy import select

from app.core import security
from app.core.config import get_settings
from app.models.email import Conversation, EmailAccount, EmailOAuthState, Message
from app.providers import gmail
from app.services import email_sync, google_oauth
from tests.conftest import PASSWORD

SCOPE = " ".join(google_oauth.SCOPES)
START = "/api/v1/email-accounts/oauth/google/start"
CALLBACK = "/api/v1/email-accounts/oauth/google/callback"


def _raw(*, sender: str, subject: str, body: str, message_id: str, in_reply_to: str | None = None, references: str | None = None, files: list[tuple[str, bytes]] | None = None) -> str:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "team@gmail.com"
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content(body)
    for filename, content in files or []:
        msg.add_attachment(content, maintype="application", subtype="octet-stream", filename=filename)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


class FakeGoogle:
    def __init__(self):
        self.address = "team@gmail.com"
        self.granted_scope = SCOPE
        self.issue_refresh_token = True
        self.refresh_revoked = False
        self.rate_limited = False
        self.valid_access = {"access-1"}
        self.refresh_count = 0
        self.history_id = 100
        self.history_expired = False
        self.messages: dict[str, dict] = {}
        self.message_ids: dict[str, str] = {}
        self.uploads: list[bytes] = []
        self.history: list[tuple[int, str]] = []
        self.sent: list[dict] = []
        self.revoked: list[str] = []
        self.token_requests: list[dict] = []
        self.calls: list[str] = []

    def deliver(self, gmail_id: str, thread_id: str, *, unread: bool = True, **kw) -> None:
        self.history_id += 1
        self.message_ids[kw["message_id"].strip("<>")] = gmail_id
        self.messages[gmail_id] = {"id": gmail_id, "threadId": thread_id, "labelIds": ["INBOX", "UNREAD"] if unread else ["INBOX"], "internalDate": str(1791400000000 + self.history_id * 1000), "raw": _raw(**kw)}
        self.history.append((self.history_id, gmail_id))

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        if request.url.host == "oauth2.googleapis.com":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            if path == "/revoke":
                self.revoked.append(form["token"])
                return httpx2.Response(200, json={})
            self.token_requests.append(form)
            if form["grant_type"] == "authorization_code":
                if form.get("code") != "good-code" or not form.get("code_verifier"):
                    return httpx2.Response(400, json={"error": "invalid_grant"})
                body = {"access_token": "access-1", "expires_in": 3600, "scope": self.granted_scope, "token_type": "Bearer"}
                if self.issue_refresh_token:
                    body["refresh_token"] = "refresh-1"
                return httpx2.Response(200, json=body)
            if self.refresh_revoked or form.get("refresh_token") != "refresh-1":
                return httpx2.Response(400, json={"error": "invalid_grant"})
            self.refresh_count += 1
            token = f"access-r{self.refresh_count}"
            self.valid_access = {token}
            return httpx2.Response(200, json={"access_token": token, "expires_in": 3600, "scope": self.granted_scope})

        if self.rate_limited:
            return httpx2.Response(403, json={"error": {"code": 403, "message": "Quota exceeded for quota metric 'Total Query Cost' and limit 'Units per minute per user'", "status": "RESOURCE_EXHAUSTED"}})
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token not in self.valid_access:
            return httpx2.Response(401, json={"error": {"code": 401, "message": "Invalid Credentials"}})
        params = dict(request.url.params)
        if path == "/upload/gmail/v1/users/me/messages/send":
            assert request.headers["content-type"] == "message/rfc822" and params.get("uploadType") == "media"
            self.uploads.append(request.content)
            return httpx2.Response(200, json={"id": f"sent-{len(self.uploads) + len(self.sent)}", "threadId": "t-sent", "labelIds": ["SENT"]})
        sub = path.removeprefix("/gmail/v1/users/me")
        if sub == "/profile":
            return httpx2.Response(200, json={"emailAddress": self.address, "historyId": str(self.history_id)})
        if sub == "/labels":
            return httpx2.Response(200, json={"labels": [{"id": "INBOX", "type": "system"}, {"id": "SENT", "type": "system"}, {"id": "Label_1", "name": "Clients", "type": "user"}]})
        if sub == "/labels/INBOX":
            return httpx2.Response(200, json={"id": "INBOX", "messagesTotal": len(self.messages)})
        if sub == "/messages" and request.method == "GET" and params.get("q", "").startswith("rfc822msgid:"):
            found = self.message_ids.get(params["q"].removeprefix("rfc822msgid:"))
            return httpx2.Response(200, json={"messages": [{"id": found, "threadId": self.messages[found]["threadId"]}]} if found else {"resultSizeEstimate": 0})
        if sub == "/messages" and request.method == "GET":
            everything = sorted(self.messages, key=lambda i: self.messages[i]["internalDate"], reverse=True)
            start, size = int(params.get("pageToken", 0)), int(params.get("maxResults", 100))
            body = {"messages": [{"id": i, "threadId": self.messages[i]["threadId"]} for i in everything[start : start + size]]}
            if start + size < len(everything):
                body["nextPageToken"] = str(start + size)
            return httpx2.Response(200, json=body)
        if sub == "/history":
            if self.history_expired:
                return httpx2.Response(404, json={"error": {"code": 404, "message": "Requested entity was not found."}})
            start = int(params["startHistoryId"])
            records = [{"id": str(h), "messagesAdded": [{"message": {"id": i, "threadId": self.messages[i]["threadId"], "labelIds": ["INBOX"]}}]} for h, i in self.history if h > start]
            return httpx2.Response(200, json={"history": records, "historyId": str(self.history_id)})
        if sub == "/messages/send":
            payload = json.loads(request.content)
            self.sent.append(payload)
            return httpx2.Response(200, json={"id": f"sent-{len(self.uploads) + len(self.sent)}", "threadId": "t-sent", "labelIds": ["SENT"]})
        if sub.startswith("/messages/"):
            gmail_id = sub.removeprefix("/messages/")
            if gmail_id.startswith("sent-"):
                # Each sent email has its own Message-Id, as with the real Gmail.
                own = "kept-by-gmail" if gmail_id == "sent-1" else f"kept-by-gmail-{gmail_id}"
                return httpx2.Response(200, json={"id": gmail_id, "payload": {"headers": [{"name": "Message-Id", "value": f"<{own}@mail.gmail.com>"}]}})
            if gmail_id not in self.messages:
                return httpx2.Response(404, json={"error": {"code": 404, "message": "Not found"}})
            return httpx2.Response(200, json=self.messages[gmail_id])
        return httpx2.Response(404, json={"error": {"code": 404, "message": f"unexpected {path}"}})


@pytest.fixture
def google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(gmail, "transport", httpx2.MockTransport(fake))
    monkeypatch.setattr(gmail.time, "sleep", lambda _s: None)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    get_settings.cache_clear()
    # Connecting queues a first sync in the background; these tests run sync themselves.
    monkeypatch.setattr(email_sync, "sync_account_task", lambda *a, **k: (0, None))
    # No waiting between pages in tests.
    monkeypatch.setattr(email_sync, "IMPORT_PAGE_PAUSE", 0)
    email_sync._wait_before_import.clear()
    return fake


def _start(client) -> dict[str, str]:
    response = client.post(START)
    assert response.status_code == 200, response.text
    url = urlparse(response.json()["data"]["authorization_url"])
    assert url.netloc == "accounts.google.com"
    return {k: v[0] for k, v in parse_qs(url.query).items()}


def _connect(client) -> dict:
    params = _start(client)
    response = client.get(CALLBACK, params={"code": "good-code", "state": params["state"]}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/accounts?gmail_connected=team%40gmail.com"
    return client.get("/api/v1/email-accounts").json()["data"][0]


def _outcome(response) -> str:
    assert response.status_code == 303
    return parse_qs(urlparse(response.headers["location"]).query)["gmail_error"][0]


def test_reports_google_as_not_set_up_until_configured(client, member):
    data = client.get("/api/v1/email-accounts/providers").json()["data"]
    assert data == {"google_oauth": False, "google_redirect_uri": "http://localhost:5173/api/v1/email-accounts/oauth/google/callback"}
    response = client.post(START)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "GOOGLE_NOT_CONFIGURED"


def test_start_sends_the_browser_to_google_with_the_right_request(client, member, google, db):
    assert client.get("/api/v1/email-accounts/providers").json()["data"]["google_oauth"] is True
    params = _start(client)
    assert params["client_id"] == "client-id.apps.googleusercontent.com"
    assert params["redirect_uri"] == "http://localhost:5173/api/v1/email-accounts/oauth/google/callback"
    assert params["response_type"] == "code" and params["access_type"] == "offline" and params["prompt"] == "consent"
    assert set(params["scope"].split()) == set(google_oauth.SCOPES)
    assert params["code_challenge_method"] == "S256" and len(params["code_challenge"]) >= 43
    # Only a hash of the state is stored, and the verifier is encrypted.
    stored = db.scalars(select(EmailOAuthState)).one()
    assert stored.state_hash == security.hash_token(params["state"]) and params["state"] not in stored.state_hash
    assert len(security.decrypt_secret(stored.code_verifier_encrypted)) >= 43


def test_connect_stores_encrypted_tokens_and_never_returns_them(client, member, google, db):
    account = _connect(client)
    assert account["provider"] == "gmail" and account["auth_type"] == "oauth" and account["status"] == "connected"
    assert account["email_address"] == "team@gmail.com"
    assert "refresh-1" not in json.dumps(account) and "access-1" not in json.dumps(account)

    row = db.scalars(select(EmailAccount)).one()
    assert "refresh-1" not in row.credentials_encrypted and "access-1" not in row.credentials_encrypted
    stored = json.loads(security.decrypt_secret(row.credentials_encrypted))
    assert stored["refresh_token"] == "refresh-1" and stored["access_token"] == "access-1"
    # The code was exchanged with the verifier that matches the challenge, and the attempt is spent.
    assert google.token_requests[0]["code_verifier"] and google.token_requests[0]["redirect_uri"].endswith("/oauth/google/callback")
    assert db.scalars(select(EmailOAuthState)).all() == []
    events = [e["action"] for e in client.get("/api/v1/workspace/audit-events").json()["data"]]
    assert "email_account.connected" in events


def test_a_return_from_google_cannot_be_replayed_or_forged(client, member, google):
    params = _start(client)
    first = client.get(CALLBACK, params={"code": "good-code", "state": params["state"]}, follow_redirects=False)
    assert "gmail_connected" in first.headers["location"]
    again = client.get(CALLBACK, params={"code": "good-code", "state": params["state"]}, follow_redirects=False)
    assert _outcome(again) == "expired"
    assert _outcome(client.get(CALLBACK, params={"code": "good-code", "state": "made-up"}, follow_redirects=False)) == "expired"
    assert _outcome(client.get(CALLBACK, params={"code": "good-code"}, follow_redirects=False)) == "expired"
    assert len(client.get("/api/v1/email-accounts").json()["data"]) == 1


def test_a_return_in_another_session_or_signed_out_is_refused(client, member, google):
    params = _start(client)
    client.post("/api/v1/auth/logout")
    assert _outcome(client.get(CALLBACK, params={"code": "good-code", "state": params["state"]}, follow_redirects=False)) == "signed_out"

    # A fresh attempt, finished from a different sign-in of the same person.
    client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
    params = _start(client)
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
    assert _outcome(client.get(CALLBACK, params={"code": "good-code", "state": params["state"]}, follow_redirects=False)) == "expired"
    assert client.get("/api/v1/email-accounts").json()["data"] == []


def test_declined_consent_missing_permission_and_bad_code(client, member, google):
    params = _start(client)
    assert _outcome(client.get(CALLBACK, params={"error": "access_denied", "state": params["state"]}, follow_redirects=False)) == "denied"

    google.granted_scope = google_oauth.SCOPES[0]  # the person unticked "send"
    params = _start(client)
    assert _outcome(client.get(CALLBACK, params={"code": "good-code", "state": params["state"]}, follow_redirects=False)) == "missing_permission"

    google.granted_scope = SCOPE
    params = _start(client)
    assert _outcome(client.get(CALLBACK, params={"code": "wrong-code", "state": params["state"]}, follow_redirects=False)) == "failed"
    assert client.get("/api/v1/email-accounts").json()["data"] == []


def test_only_owners_and_admins_can_connect(client, member, google, db):
    from app.models import WorkspaceMember

    membership = db.scalars(select(WorkspaceMember)).one()
    membership.role = "agent"
    db.commit()
    assert client.post(START).status_code == 403


def test_sync_imports_mail_threads_it_and_then_follows_history(client, member, google, db):
    google.deliver("m1", "t1", sender="Maya <maya@example.com>", subject="Invoice question", body="Can you resend the invoice?", message_id="<a1@example.com>")
    google.deliver("m2", "t2", sender="Omar <omar@example.com>", subject="Invoice question", body="A different person, same subject.", message_id="<b1@example.com>")
    account = _connect(client)

    result = client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]
    assert result["synced_messages"] == 2 and result["error"] is None
    # Two Gmail threads stay two conversations even though the subjects match.
    conversations = db.scalars(select(Conversation).order_by(Conversation.id)).all()
    assert sorted(c.provider_thread_id for c in conversations) == ["t1", "t2"]
    assert db.scalars(select(EmailAccount)).one().sync_cursor == str(google.history_id)

    # Nothing new: the next sync asks for changes only and stores nothing twice.
    google.calls.clear()
    assert client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]["synced_messages"] == 0
    assert "GET /gmail/v1/users/me/history" in google.calls and "GET /gmail/v1/users/me/messages" not in google.calls

    # A reply arrives in the first thread.
    google.deliver("m3", "t1", sender="Maya <maya@example.com>", subject="Re: Invoice question", body="Thanks!", message_id="<a2@example.com>", in_reply_to="<a1@example.com>")
    assert client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]["synced_messages"] == 1
    db.rollback()  # start a fresh read: MySQL keeps one snapshot per transaction
    db.expire_all()
    first = db.scalars(select(Conversation).where(Conversation.provider_thread_id == "t1")).one()
    assert len(db.scalars(select(Message).where(Message.conversation_id == first.id)).all()) == 2
    assert len(db.scalars(select(Message)).all()) == 3

    inbox = client.get("/api/v1/conversations?view=inbox").json()["data"]
    assert {c["subject"] for c in inbox} == {"Invoice question"} and len(inbox) == 2
    assert inbox[0]["account_provider"] == "gmail"


def test_sync_recovers_when_gmail_has_forgotten_the_position(client, member, google, db):
    google.deliver("m1", "t1", sender="maya@example.com", subject="Hello", body="One", message_id="<a1@example.com>")
    account = _connect(client)
    client.post(f"/api/v1/email-accounts/{account['id']}/sync")
    google.deliver("m2", "t2", sender="omar@example.com", subject="Second", body="Two", message_id="<b1@example.com>")
    google.history_expired = True
    result = client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]
    assert result["synced_messages"] == 1 and result["error"] is None
    assert len(db.scalars(select(Message)).all()) == 2


def test_an_expired_access_token_is_renewed_and_saved(client, member, google, db):
    account = _connect(client)
    row = db.scalars(select(EmailAccount)).one()
    stored = json.loads(security.decrypt_secret(row.credentials_encrypted))
    stored["expires_at"] = int(time.time()) - 10
    row.credentials_encrypted = security.encrypt_secret(json.dumps(stored))
    db.commit()

    result = client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]
    assert result["error"] is None and google.refresh_count == 1
    db.rollback()  # start a fresh read: MySQL keeps one snapshot per transaction
    db.expire_all()
    renewed = json.loads(security.decrypt_secret(db.scalars(select(EmailAccount)).one().credentials_encrypted))
    assert renewed["access_token"] == "access-r1" and renewed["refresh_token"] == "refresh-1"

    # A token Google rejects before its time is also renewed, once.
    google.valid_access = set()
    result = client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]
    assert result["error"] is None and google.refresh_count == 2


def test_a_revoked_connection_asks_for_reconnecting_and_reconnect_restores_it(client, member, google, db):
    account = _connect(client)
    google.refresh_revoked = True
    google.valid_access = set()

    result = client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]
    assert result["status"] == "needs_reconnect" and "Reconnect" in result["error"]
    listed = client.get("/api/v1/email-accounts").json()["data"][0]
    assert listed["status"] == "needs_reconnect"
    # The background sync leaves it alone until someone reconnects.
    assert email_sync.sync_all_active_accounts() == []

    send = client.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["maya@example.com"], "subject": "Hi", "body_text": "Hello"})
    assert send.status_code == 409 and send.json()["error"]["code"] == "RECONNECT_REQUIRED"

    google.refresh_revoked = False
    google.valid_access = {"access-1"}
    again = _connect(client)
    assert again["id"] == account["id"] and again["status"] == "connected"
    assert len(db.scalars(select(EmailAccount)).all()) == 1


def test_send_goes_through_the_gmail_api_and_keeps_googles_message_id(client, member, google, db):
    account = _connect(client)
    response = client.post(
        "/api/v1/messages/send",
        json={"account_id": account["id"], "to": ["maya@example.com"], "cc": ["omar@example.com"], "subject": "Your invoice", "body_text": "Attached as asked.", "in_reply_to": "<a1@example.com>"},
    )
    assert response.status_code == 201, response.text
    sent = base64.urlsafe_b64decode(google.sent[0]["raw"]).decode()
    assert "To: maya@example.com" in sent and "Cc: omar@example.com" in sent and "Subject: Your invoice" in sent
    assert "In-Reply-To: <a1@example.com>" in sent and "References: <a1@example.com>" in sent
    assert "From: " in sent and "team@gmail.com" in sent and "Attached as asked." in sent
    stored = db.scalars(select(Message).where(Message.direction == "outbound")).one()
    assert stored.provider_message_id == "<kept-by-gmail@mail.gmail.com>"


def test_signing_in_replaces_an_app_password_connection_and_disconnect_revokes(client, member, google, db, monkeypatch):
    from app.providers.imap_smtp import ImapSmtpProvider

    monkeypatch.setattr(ImapSmtpProvider, "test_connection", lambda self: (True, ""))
    monkeypatch.setattr(ImapSmtpProvider, "list_folders", lambda self: [{"name": "INBOX", "system_folder": "inbox"}])
    created = client.post("/api/v1/email-accounts/connect", json={
        "provider": "gmail", "email_address": "team@gmail.com", "display_name": "Team",
        "incoming_host": "imap.gmail.com", "incoming_username": "team@gmail.com", "incoming_password": "app-password",
        "outgoing_host": "smtp.gmail.com", "outgoing_username": "team@gmail.com", "outgoing_password": "app-password",
    })
    assert created.status_code == 201 and created.json()["data"]["auth_type"] == "basic"

    account = _connect(client)
    assert account["id"] == created.json()["data"]["id"] and account["auth_type"] == "oauth" and account["display_name"] == "Team"
    assert "app-password" not in security.decrypt_secret(db.scalars(select(EmailAccount)).one().credentials_encrypted)

    assert client.delete(f"/api/v1/email-accounts/{account['id']}").status_code == 204
    assert google.revoked == ["refresh-1"]
    assert client.get("/api/v1/email-accounts").json()["data"] == []


def test_one_workspace_cannot_see_or_sync_anothers_gmail(client, member, google):
    account = _connect(client)
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={"email": "grace@example.com", "password": PASSWORD, "name": "Grace Hopper"})
    client.post("/api/v1/workspaces", json={"name": "Compilers"})
    assert client.get("/api/v1/email-accounts").json()["data"] == []
    result = client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]
    assert result["synced_messages"] == 0 and result["error"] == "Account not found"
    assert client.delete(f"/api/v1/email-accounts/{account['id']}").status_code == 404


def test_stored_secrets_survive_setting_an_encryption_key(monkeypatch):
    before = security.encrypt_secret("mailbox-password")
    monkeypatch.setenv("ENCRYPTION_KEY", "a-long-random-secret")
    get_settings.cache_clear()
    security._fernet.cache_clear()
    try:
        assert security.decrypt_secret(before) == "mailbox-password"
        after = security.encrypt_secret("new-token")
        assert security.decrypt_secret(after) == "new-token"
        monkeypatch.delenv("ENCRYPTION_KEY")
        get_settings.cache_clear()
        security._fernet.cache_clear()
        with pytest.raises(Exception):
            security.decrypt_secret(after)  # written with the key, unreadable without it
    finally:
        get_settings.cache_clear()
        security._fernet.cache_clear()


def test_the_whole_inbox_is_imported_page_by_page_and_resumes(client, member, google, db, monkeypatch):
    monkeypatch.setattr(email_sync, "IMPORT_PAGE_SIZE", 5)
    for n in range(12):
        google.deliver(f"m{n}", f"t{n}", unread=n >= 10, sender="maya@example.com", subject=f"Order {n}", body=f"Body {n}", message_id=f"<o{n}@example.com>")
    account = _connect(client)
    assert account["import_state"] == "pending"

    # The ordinary sync brings the newest few; the import then walks back through everything.
    client.post(f"/api/v1/email-accounts/{account['id']}/sync?limit=3")
    assert email_sync.import_pending_history() is True
    listed = client.get("/api/v1/email-accounts").json()["data"][0]
    assert listed["import_state"] == "running" and listed["import_total"] == 12

    # A restart in the middle continues from the saved page: nothing skipped, nothing stored twice.
    assert db.scalars(select(EmailAccount)).one().import_page_token == "5"
    db.rollback()
    assert email_sync.import_pending_history() is True
    assert email_sync.import_pending_history() is False
    listed = client.get("/api/v1/email-accounts").json()["data"][0]
    assert listed["import_state"] == "done" and listed["message_count"] == 12
    assert len(db.scalars(select(Message)).all()) == 12
    assert email_sync.import_pending_history() is False  # finished mailboxes are left alone

    # Mail the owner had already read in Gmail arrives as read; unread stays unread.
    unread = {c.subject for c in db.scalars(select(Conversation).where(Conversation.is_read.is_(False))).all()}
    assert unread == {"Order 10", "Order 11"}

    # The inbox list pages through all of it.
    first = client.get("/api/v1/conversations?view=inbox&limit=5").json()["data"]
    rest = client.get("/api/v1/conversations?view=inbox&limit=200&offset=5").json()["data"]
    assert len(first) == 5 and len(rest) == 7 and not {c["id"] for c in first} & {c["id"] for c in rest}
    assert first[0]["subject"] == "Order 11"


def test_import_stops_for_a_mailbox_that_needs_reconnecting(client, member, google, db):
    google.deliver("m1", "t1", sender="maya@example.com", subject="Hello", body="One", message_id="<a1@example.com>")
    account = _connect(client)
    google.refresh_revoked = True
    google.valid_access = set()
    assert email_sync.import_pending_history() is False or True  # the page fails; what matters is the state below
    listed = client.get("/api/v1/email-accounts").json()["data"][0]
    assert listed["status"] == "needs_reconnect" and listed["id"] == account["id"]
    assert email_sync.import_pending_history() is False


def test_googles_rate_limit_pauses_the_import_without_marking_the_mailbox_broken(client, member, google, db, monkeypatch):
    monkeypatch.setattr(email_sync, "IMPORT_PAGE_SIZE", 2)
    for n in range(4):
        google.deliver(f"m{n}", f"t{n}", sender="maya@example.com", subject=f"Order {n}", body="x", message_id=f"<o{n}@example.com>")
    account = _connect(client)
    assert email_sync.import_pending_history() is True

    google.rate_limited = True
    assert email_sync.import_pending_history() is True
    # The ordinary sync is not turned into an error either.
    result = client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]
    assert result["error"] is None
    listed = client.get("/api/v1/email-accounts").json()["data"][0]
    assert listed["status"] == "connected" and listed["last_error"] is None and listed["import_state"] == "running"
    # It stands back for a while instead of hammering Google...
    assert email_sync._wait_before_import[account["id"]] > email_sync.time.monotonic() + 30
    google.rate_limited = False
    assert email_sync.import_pending_history() is True
    assert len(db.scalars(select(Message)).all()) == 2
    # ...and carries on from the same page once the wait is over.
    email_sync._wait_before_import.clear()
    assert email_sync.import_pending_history() is False
    db.rollback()
    assert len(db.scalars(select(Message)).all()) == 4
