"""The mail screens' data: list fields, search, filters, status, labels, attachments, reply and forward."""

import base64
import email

from sqlalchemy import select

from app.models.email import Attachment, Message
from tests.conftest import PASSWORD
from tests.test_gmail_oauth import _connect, google  # noqa: F401 - `google` is a fixture


def _mailbox(client, google):
    google.deliver("m1", "t1", unread=False, sender="Maya Chen <maya@example.com>", subject="Invoice 1042", body="Please find the invoice attached.", message_id="<a1@example.com>", files=[("invoice-1042.pdf", b"%PDF-1.7 invoice bytes"), ("notes.txt", b"second file")])
    google.deliver("m2", "t2", sender="Omar Haddad <omar@example.com>", subject="Meeting on Friday", body="Can we move the workshop to the afternoon?", message_id="<b1@example.com>")
    google.deliver("m3", "t1", sender="Maya Chen <maya@example.com>", subject="Re: Invoice 1042", body="Any update on the payment?", message_id="<a2@example.com>", in_reply_to="<a1@example.com>", references="<a1@example.com>")
    account = _connect(client)
    assert client.post(f"/api/v1/email-accounts/{account['id']}/sync").json()["data"]["synced_messages"] == 3
    return account


def _list(client, query=""):
    return client.get(f"/api/v1/conversations?view=inbox{query}").json()["data"]


def test_the_list_carries_what_an_inbox_row_shows(client, member, google):
    _mailbox(client, google)
    rows = _list(client)
    invoice = next(r for r in rows if r["subject"] == "Invoice 1042")
    meeting = next(r for r in rows if r["subject"] == "Meeting on Friday")
    assert invoice["last_sender_name"] == "Maya Chen" and invoice["last_sender_email"] == "maya@example.com"
    assert invoice["message_count"] == 2 and invoice["has_attachments"] is True and invoice["snippet"].startswith("Any update")
    assert meeting["message_count"] == 1 and meeting["has_attachments"] is False and meeting["is_read"] is False
    assert rows[0]["id"] == invoice["id"]  # newest activity first
    counts = client.get("/api/v1/conversations/counts").json()["data"]
    assert counts["inbox_unread"] == 2 and list(counts["inbox_unread_by_account"].values()) == [2]


def test_search_looks_at_sender_subject_and_body(client, member, google):
    _mailbox(client, google)
    assert [r["subject"] for r in _list(client, "&search=omar@example.com")] == ["Meeting on Friday"]
    assert [r["subject"] for r in _list(client, "&search=Maya")] == ["Invoice 1042"]
    assert [r["subject"] for r in _list(client, "&search=workshop")] == ["Meeting on Friday"]
    assert [r["subject"] for r in _list(client, "&search=find the invoice")] == ["Invoice 1042"]  # an older message's body
    assert _list(client, "&search=nothing-like-this") == []


def test_filters_and_status(client, member, google):
    _mailbox(client, google)
    meeting = next(r for r in _list(client) if r["subject"] == "Meeting on Friday")
    assert [r["subject"] for r in _list(client, "&has_attachments=true")] == ["Invoice 1042"]
    client.get(f"/api/v1/conversations/{meeting['id']}")  # opening marks it read
    assert [r["subject"] for r in _list(client, "&unread=true")] == ["Invoice 1042"]
    client.patch(f"/api/v1/conversations/{meeting['id']}", json={"is_starred": True})
    assert [r["subject"] for r in _list(client, "&starred=true")] == ["Meeting on Friday"]

    assert client.patch(f"/api/v1/conversations/{meeting['id']}", json={"status": "closed"}).json()["data"]["status"] == "closed"
    assert [r["subject"] for r in _list(client, "&status=closed")] == ["Meeting on Friday"]
    assert [r["subject"] for r in _list(client, "&status=open")] == ["Invoice 1042"]
    assert client.patch(f"/api/v1/conversations/{meeting['id']}", json={"status": "done"}).status_code == 422
    client.post("/api/v1/conversations/batch", json={"conversation_ids": [meeting["id"]], "action": "status_pending"})
    assert [r["subject"] for r in _list(client, "&status=pending")] == ["Meeting on Friday"]


def test_new_mail_reopens_a_closed_conversation(client, member, google):
    account = _mailbox(client, google)
    meeting = next(r for r in _list(client) if r["subject"] == "Meeting on Friday")
    client.patch(f"/api/v1/conversations/{meeting['id']}", json={"status": "closed"})
    google.deliver("m4", "t2", sender="Omar Haddad <omar@example.com>", subject="Re: Meeting on Friday", body="Afternoon works?", message_id="<b2@example.com>", in_reply_to="<b1@example.com>")
    client.post(f"/api/v1/email-accounts/{account['id']}/sync")
    again = next(r for r in _list(client) if r["id"] == meeting["id"])
    assert again["status"] == "open" and again["message_count"] == 2


def test_labels_create_apply_filter_rename_delete(client, member, google):
    _mailbox(client, google)
    invoice = next(r for r in _list(client) if r["subject"] == "Invoice 1042")
    billing = client.post("/api/v1/labels", json={"name": "Billing", "color": "green"})
    assert billing.status_code == 201
    urgent = client.post("/api/v1/labels", json={"name": "Urgent", "color": "red"}).json()["data"]
    assert client.post("/api/v1/labels", json={"name": "billing "}).status_code in (201, 409)  # MySQL compares names without case
    assert client.post("/api/v1/labels", json={"name": "Billing"}).status_code == 409
    assert client.post("/api/v1/labels", json={"name": "X", "color": "pink"}).status_code == 422

    billing_id = billing.json()["data"]["id"]
    applied = client.put(f"/api/v1/conversations/{invoice['id']}/labels", json={"label_ids": [billing_id, urgent["id"]]})
    assert [l["name"] for l in applied.json()["data"]] == ["Billing", "Urgent"]
    assert [r["subject"] for r in _list(client, f"&label_id={billing_id}")] == ["Invoice 1042"]
    assert [l["name"] for l in _list(client, f"&label_id={billing_id}")[0]["labels"]] == ["Billing", "Urgent"]
    assert [l["name"] for l in client.get(f"/api/v1/conversations/{invoice['id']}").json()["data"]["conversation"]["labels"]] == ["Billing", "Urgent"]
    counts = {l["name"]: l["conversation_count"] for l in client.get("/api/v1/labels").json()["data"]}
    assert counts["Billing"] == 1 and counts["Urgent"] == 1

    assert client.patch(f"/api/v1/labels/{billing_id}", json={"name": "Finance", "color": "teal"}).json()["data"] == {"id": billing_id, "name": "Finance", "color": "teal"}
    assert client.delete(f"/api/v1/labels/{urgent['id']}").status_code == 204
    assert [l["name"] for l in _list(client, f"&label_id={billing_id}")[0]["labels"]] == ["Finance"]
    assert client.put(f"/api/v1/conversations/{invoice['id']}/labels", json={"label_ids": [999999]}).status_code == 404


def test_labels_and_attachments_stay_inside_their_workspace(client, member, google, db):
    _mailbox(client, google)
    invoice = next(r for r in _list(client) if r["subject"] == "Invoice 1042")
    label = client.post("/api/v1/labels", json={"name": "Billing"}).json()["data"]
    attachment_id = db.scalars(select(Attachment)).first().id

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={"email": "grace@example.com", "password": PASSWORD, "name": "Grace Hopper"})
    client.post("/api/v1/workspaces", json={"name": "Compilers"})
    assert client.get("/api/v1/labels").json()["data"] == []
    assert client.patch(f"/api/v1/labels/{label['id']}", json={"name": "Mine"}).status_code == 404
    assert client.put(f"/api/v1/conversations/{invoice['id']}/labels", json={"label_ids": []}).status_code == 404
    assert client.get(f"/api/v1/attachments/{attachment_id}").status_code == 404
    assert client.post("/api/v1/messages/send", json={"account_id": 1, "to": ["x@example.com"], "subject": "x", "forward_attachments_of": 1}).status_code == 404


def test_an_attachment_downloads_from_the_mailbox_as_a_file(client, member, google):
    _mailbox(client, google)
    invoice = next(r for r in _list(client) if r["subject"] == "Invoice 1042")
    detail = client.get(f"/api/v1/conversations/{invoice['id']}").json()["data"]
    files = detail["messages"][0]["attachments"]
    assert [f["filename"] for f in files] == ["invoice-1042.pdf", "notes.txt"]

    first = client.get(f"/api/v1/attachments/{files[0]['id']}")
    assert first.status_code == 200 and first.content == b"%PDF-1.7 invoice bytes"
    assert first.headers["content-disposition"] == "attachment; filename*=UTF-8\'\'invoice-1042.pdf"
    assert first.headers["content-type"] == "application/octet-stream" and first.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/api/v1/attachments/{files[1]['id']}").content == b"second file"

    # The email was deleted from Gmail afterwards: say so instead of failing oddly.
    google.message_ids.clear()
    gone = client.get(f"/api/v1/attachments/{files[0]['id']}")
    assert gone.status_code == 404 and gone.json()["error"]["code"] == "ATTACHMENT_UNAVAILABLE"


def test_reply_all_points_at_the_real_message_and_stays_in_the_thread(client, member, google, db):
    account = _mailbox(client, google)
    invoice = next(r for r in _list(client) if r["subject"] == "Invoice 1042")
    last = client.get(f"/api/v1/conversations/{invoice['id']}").json()["data"]["messages"][-1]
    assert last["provider_message_id"] == "<a2@example.com>"

    sent = client.post("/api/v1/messages/send", json={
        "account_id": account["id"], "conversation_id": invoice["id"], "in_reply_to": last["provider_message_id"],
        "to": ["maya@example.com"], "cc": ["finance@example.com"], "subject": "Re: Invoice 1042", "body_text": "Paid today.",
    })
    assert sent.status_code == 201, sent.text
    assert google.sent[0]["threadId"] == "t1"
    raw = email.message_from_bytes(base64.urlsafe_b64decode(google.sent[0]["raw"]))
    assert raw["In-Reply-To"] == "<a2@example.com>" and raw["References"] == "<a1@example.com> <a2@example.com>"
    assert raw["To"] == "maya@example.com" and raw["Cc"] == "finance@example.com"

    after = next(r for r in _list(client) if r["id"] == invoice["id"])
    assert after["message_count"] == 3 and after["snippet"] == "Paid today." and after["last_sender_email"] == "team@gmail.com"
    assert len(_list(client)) == 2  # no new conversation was started


def test_new_mail_with_attachments_and_forward_with_the_originals(client, member, google, db):
    account = _mailbox(client, google)
    invoice = next(r for r in _list(client) if r["subject"] == "Invoice 1042")
    original = client.get(f"/api/v1/conversations/{invoice['id']}").json()["data"]["messages"][0]

    forwarded = client.post("/api/v1/messages/send", json={
        "account_id": account["id"], "to": ["accounts@example.com"], "subject": "Fwd: Invoice 1042", "body_text": "For your records.",
        "forward_attachments_of": original["id"],
        "attachments": [{"filename": "cover note.txt", "content_type": "text/plain", "content_base64": base64.b64encode(b"see attached").decode()}],
    })
    assert forwarded.status_code == 201, forwarded.text
    assert [a["filename"] for a in forwarded.json()["data"]["attachments"]] == ["invoice-1042.pdf", "notes.txt", "cover note.txt"]
    message = email.message_from_bytes(google.uploads[0])
    parts = {part.get_filename(): part.get_payload(decode=True) for part in message.walk() if part.get_filename()}
    assert parts == {"invoice-1042.pdf": b"%PDF-1.7 invoice bytes", "notes.txt": b"second file", "cover note.txt": b"see attached"}
    assert message["To"] == "accounts@example.com" and message["Subject"] == "Fwd: Invoice 1042"

    stored = db.scalars(select(Message).where(Message.direction == "outbound")).one()
    assert len(db.scalars(select(Attachment).where(Attachment.message_id == stored.id)).all()) == 3
    sent_view = client.get("/api/v1/conversations?view=sent").json()["data"]
    assert sent_view[0]["subject"] == "Fwd: Invoice 1042" and sent_view[0]["has_attachments"] is True

    bad = client.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["a@example.com"], "subject": "x", "attachments": [{"filename": "f.bin", "content_base64": "not base64!!"}]})
    assert bad.status_code == 422
    assert client.post("/api/v1/messages/send", json={"account_id": account["id"], "to": [" "], "subject": "x"}).status_code == 422


def test_viewers_cannot_send_or_label(client, member, google, db):
    from app.models import WorkspaceMember

    account = _mailbox(client, google)
    membership = db.scalars(select(WorkspaceMember)).one()
    membership.role = "viewer"
    db.commit()
    assert client.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["a@example.com"], "subject": "x"}).status_code == 403
    assert client.post("/api/v1/labels", json={"name": "Nope"}).status_code == 403
    assert len(_list(client)) == 2  # reading still works


def test_overview_counts_the_real_mail_and_respects_access(client, member, google):
    empty = client.get("/api/v1/conversations/overview").json()["data"]
    assert empty["connected_inboxes"] == 0 and empty["messages_stored"] == 0 and empty["needs_attention"] == []

    account = _mailbox(client, google)
    data = client.get("/api/v1/conversations/overview").json()["data"]
    assert data["connected_inboxes"] == 1 and data["messages_stored"] == 3 and data["inboxes_needing_attention"] == 0
    assert data["open_conversations"] == 2 and data["unread_conversations"] == 2 and data["waiting_on_team"] == 0
    assert [c["subject"] for c in data["needs_attention"]] == ["Invoice 1042", "Meeting on Friday"]  # newest activity first

    meeting = next(c for c in data["needs_attention"] if c["subject"] == "Meeting on Friday")
    client.patch(f"/api/v1/conversations/{meeting['id']}", json={"status": "pending"})
    client.get(f"/api/v1/conversations/{meeting['id']}")  # opening it reads it
    after = client.get("/api/v1/conversations/overview").json()["data"]
    assert after["waiting_on_team"] == 1 and after["open_conversations"] == 1 and after["unread_conversations"] == 1
    assert [c["subject"] for c in after["needs_attention"]] == ["Invoice 1042"]

    # A mailbox that needs reconnecting is called out.
    from app.core.database import SessionLocal
    from app.models.email import EmailAccount

    with SessionLocal() as other:
        other.get(EmailAccount, account["id"]).status = "needs_reconnect"
        other.commit()
    assert client.get("/api/v1/conversations/overview").json()["data"]["inboxes_needing_attention"] == 1

    # Someone without access to the mailbox sees none of it.
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import PASSWORD

    token = client.post("/api/v1/workspace/invitations", json={"email": "grace@example.com", "role": "agent"}).json()["data"]["token"]
    grace = TestClient(app)
    grace.post("/api/v1/auth/register", json={"email": "grace@example.com", "password": PASSWORD, "name": "Grace Hopper"})
    grace.post(f"/api/v1/auth/invitations/{token}/accept")
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted"})
    hidden = grace.get("/api/v1/conversations/overview").json()["data"]
    assert hidden.pop("sync") == {"state": "none", "stored": 0, "total": None, "percent": None, "mailboxes": [], "last_synced_at": None}
    assert hidden == {"connected_inboxes": 0, "inboxes_needing_attention": 0, "messages_stored": 0, "open_conversations": 0, "waiting_on_team": 0, "unread_conversations": 0, "needs_attention": []}


def test_overview_reports_sync_progress_then_completed(client, member, google, db, monkeypatch):
    from app.services import email_sync

    monkeypatch.setattr(email_sync, "IMPORT_PAGE_SIZE", 2)
    assert client.get("/api/v1/conversations/overview").json()["data"]["sync"]["state"] == "none"

    for n in range(5):
        google.deliver(f"m{n}", f"t{n}", sender="maya@example.com", subject=f"Order {n}", body="x", message_id=f"<o{n}@example.com>")
    _connect(client)
    sync = client.get("/api/v1/conversations/overview").json()["data"]["sync"]
    assert sync["state"] == "syncing" and sync["mailboxes"][0]["state"] == "importing" and sync["stored"] == 0

    assert email_sync.import_pending_history() is True
    sync = client.get("/api/v1/conversations/overview").json()["data"]["sync"]
    assert sync["state"] == "syncing" and sync["stored"] == 2 and sync["total"] == 5 and sync["percent"] == 40

    email_sync._wait_before_import.clear()
    while email_sync.import_pending_history():
        email_sync._wait_before_import.clear()
    sync = client.get("/api/v1/conversations/overview").json()["data"]["sync"]
    assert sync["state"] == "complete" and sync["stored"] == 5 and sync["percent"] is None and sync["mailboxes"][0]["state"] == "done"

    from app.models.email import EmailAccount

    db.rollback()
    db.scalars(__import__("sqlalchemy").select(EmailAccount)).one().status = "needs_reconnect"
    db.commit()
    assert client.get("/api/v1/conversations/overview").json()["data"]["sync"]["state"] == "attention"
