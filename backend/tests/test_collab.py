"""Saved drafts, assignment, internal notes, notifications, contacts and templates."""

import base64
import email

from sqlalchemy import select

from app.models.collab import Draft
from tests.test_gmail_oauth import _connect, google  # noqa: F401 - `google` is a fixture
from tests.test_mailbox_access import _join


def _mailbox(client, google):
    google.deliver("m1", "t1", sender="Maya Chen <maya@example.com>", subject="Invoice 1042", body="Please pay.", message_id="<a1@example.com>")
    google.deliver("m2", "t2", sender="Omar Haddad <omar@example.com>", subject="Meeting on Friday", body="Afternoon?", message_id="<b1@example.com>")
    google.deliver("m3", "t1", sender="Maya Chen <maya@example.com>", subject="Re: Invoice 1042", body="Any update?", message_id="<a2@example.com>", in_reply_to="<a1@example.com>")
    account = _connect(client)
    client.post(f"/api/v1/email-accounts/{account['id']}/sync")
    return account


def _conv(client, subject):
    return next(c for c in client.get("/api/v1/conversations?view=inbox").json()["data"] if c["subject"] == subject)


# --- drafts -------------------------------------------------------------------------

def test_a_draft_is_saved_changed_listed_and_removed_when_sent(client, member, google, db):
    account = _mailbox(client, google)
    conversation = _conv(client, "Invoice 1042")
    body = {"email_account_id": account["id"], "mode": "reply", "conversation_id": conversation["id"], "in_reply_to": "<a2@example.com>",
            "to": "maya@example.com", "subject": "Re: Invoice 1042", "body_text": "Paid"}
    created = client.post("/api/v1/drafts", json=body)
    assert created.status_code == 201, created.text
    draft = created.json()["data"]
    assert draft["account_email"] == "team@gmail.com" and draft["mode"] == "reply"

    changed = client.put(f"/api/v1/drafts/{draft['id']}", json={**body, "body_text": "Paid today, thanks.", "cc": "finance@example.com"}).json()["data"]
    assert changed["body_text"] == "Paid today, thanks." and changed["cc"] == "finance@example.com"
    listed = client.get("/api/v1/drafts").json()["data"]
    assert [d["id"] for d in listed] == [draft["id"]] and listed[0]["conversation_id"] == conversation["id"]

    sent = client.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["maya@example.com"], "subject": "Re: Invoice 1042", "body_text": "Paid today, thanks.",
                                                     "conversation_id": conversation["id"], "in_reply_to": "<a2@example.com>", "draft_id": draft["id"]})
    assert sent.status_code == 201
    assert client.get("/api/v1/drafts").json()["data"] == []
    raw = email.message_from_bytes(base64.urlsafe_b64decode(google.sent[0]["raw"]))
    assert raw["In-Reply-To"] == "<a2@example.com>"

    kept = client.post("/api/v1/drafts", json={"email_account_id": account["id"], "to": "", "subject": "", "body_text": "half a thought"}).json()["data"]
    assert client.delete(f"/api/v1/drafts/{kept['id']}").status_code == 204
    assert client.delete(f"/api/v1/drafts/{kept['id']}").status_code == 404
    assert db.scalars(select(Draft)).all() == []


def test_drafts_are_private_and_need_access_to_the_mailbox(client, member, google):
    account = _mailbox(client, google)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    vera, _ = _join(client, "vera@example.com", "Vera Viewer", "viewer")
    mine = client.post("/api/v1/drafts", json={"email_account_id": account["id"], "to": "x@example.com", "subject": "Mine"}).json()["data"]

    assert grace.get("/api/v1/drafts").json()["data"] == []
    assert grace.put(f"/api/v1/drafts/{mine['id']}", json={"email_account_id": account["id"], "subject": "Stolen"}).status_code == 404
    assert grace.delete(f"/api/v1/drafts/{mine['id']}").status_code == 404
    assert vera.post("/api/v1/drafts", json={"email_account_id": account["id"]}).status_code == 403

    hers = grace.post("/api/v1/drafts", json={"email_account_id": account["id"], "subject": "Hers"}).json()["data"]
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted"})
    assert grace.get("/api/v1/drafts").json()["data"] == []  # the mailbox is gone for her, and so is what she drafted in it
    assert grace.post("/api/v1/drafts", json={"email_account_id": account["id"]}).status_code == 404
    assert grace.put(f"/api/v1/drafts/{hers['id']}", json={"email_account_id": account["id"]}).status_code == 404
    assert [d["subject"] for d in client.get("/api/v1/drafts").json()["data"]] == ["Mine"]


# --- assignment and notifications ----------------------------------------------------

def test_assigning_notifies_the_person_and_filters_work(client, member, google):
    _mailbox(client, google)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    invoice, meeting = _conv(client, "Invoice 1042"), _conv(client, "Meeting on Friday")

    assigned = client.patch(f"/api/v1/conversations/{invoice['id']}", json={"assignee_user_id": grace_id}).json()["data"]
    assert assigned["assignee_user_id"] == grace_id and assigned["assignee_name"] == "Grace Hopper"
    assert [c["subject"] for c in client.get("/api/v1/conversations?view=inbox&assignee=none").json()["data"]] == ["Meeting on Friday"]
    assert [c["subject"] for c in grace.get("/api/v1/conversations?view=inbox&assignee=me").json()["data"]] == ["Invoice 1042"]
    assert [c["subject"] for c in client.get(f"/api/v1/conversations?view=inbox&assignee={grace_id}").json()["data"]] == ["Invoice 1042"]
    assert client.get("/api/v1/conversations?view=inbox&assignee=me").json()["data"] == []
    assert client.get(f"/api/v1/conversations/{invoice['id']}").json()["data"]["conversation"]["assignee_name"] == "Grace Hopper"

    inbox = grace.get("/api/v1/notifications").json()["data"]
    assert inbox["unread"] == 1 and inbox["items"][0]["kind"] == "assigned" and inbox["items"][0]["conversation_id"] == invoice["id"]
    assert inbox["items"][0]["title"] == "Ada Lovelace assigned you a conversation" and inbox["items"][0]["body"] == "Invoice 1042"
    assert client.get("/api/v1/notifications").json()["data"] == {"unread": 0, "items": []}  # nobody is told about their own action

    # Changing something else leaves the assignment alone; null removes it.
    assert client.patch(f"/api/v1/conversations/{invoice['id']}", json={"is_starred": True}).json()["data"]["assignee_user_id"] == grace_id
    assert client.patch(f"/api/v1/conversations/{invoice['id']}", json={"assignee_user_id": None}).json()["data"]["assignee_user_id"] is None

    assert grace.post("/api/v1/notifications/read", json={"ids": [inbox["items"][0]["id"]]}).status_code == 204
    after = grace.get("/api/v1/notifications").json()["data"]
    assert after["unread"] == 0 and after["items"][0]["is_read"] is True
    assert "conversation.assigned" in [e["action"] for e in client.get("/api/v1/workspace/audit-events").json()["data"]]
    assert meeting["assignee_user_id"] is None


def test_who_may_assign_to_whom(client, member, google):
    account = _mailbox(client, google)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    omar, omar_id = _join(client, "omar@example.com", "Omar Haddad", "manager")
    vera, vera_id = _join(client, "vera@example.com", "Vera Viewer", "viewer")
    invoice = _conv(client, "Invoice 1042")
    url = f"/api/v1/conversations/{invoice['id']}"

    assert grace.patch(url, json={"assignee_user_id": omar_id}).status_code == 403      # an agent cannot hand work to others
    assert grace.patch(url, json={"assignee_user_id": grace_id}).status_code == 200     # but can take it
    assert grace.patch(url, json={"assignee_user_id": None}).status_code == 200         # and give it up
    assert omar.patch(url, json={"assignee_user_id": grace_id}).status_code == 200      # a manager assigns anyone
    assert grace.patch(url, json={"assignee_user_id": None}).status_code == 200
    assert omar.patch(url, json={"assignee_user_id": omar_id}).status_code == 200
    assert grace.patch(url, json={"assignee_user_id": None}).status_code == 403         # not hers to give up
    assert vera.patch(url, json={"assignee_user_id": vera_id}).status_code == 403
    assert client.patch(url, json={"assignee_user_id": 999999}).status_code == 404

    # Someone who cannot use the mailbox cannot be given its conversations.
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "roles": [{"role": "manager", "permission": "send"}]})
    refused = client.patch(url, json={"assignee_user_id": grace_id})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "NO_MAILBOX_ACCESS"


# --- notes -----------------------------------------------------------------------------

def test_notes_stay_internal_and_mentions_notify(client, member, google):
    account = _mailbox(client, google)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    omar, omar_id = _join(client, "omar@example.com", "Omar Haddad", "manager")
    invoice = _conv(client, "Invoice 1042")
    client.patch(f"/api/v1/conversations/{invoice['id']}", json={"assignee_user_id": omar_id})
    omar.post("/api/v1/notifications/read", json={})

    added = grace.post(f"/api/v1/conversations/{invoice['id']}/notes", json={"body": "  Customer called. @Ada can you approve the refund?  "})
    assert added.status_code == 201
    note = added.json()["data"]
    assert note["body"] == "Customer called. @Ada can you approve the refund?" and note["author_name"] == "Grace Hopper" and note["is_yours"] is True

    detail = client.get(f"/api/v1/conversations/{invoice['id']}").json()["data"]
    assert [n["body"] for n in detail["notes"]] == [note["body"]] and detail["notes"][0]["is_yours"] is False
    assert all("refund" not in (m["body_text"] or "") for m in detail["messages"])

    ada = client.get("/api/v1/notifications").json()["data"]
    assert ada["unread"] == 1 and ada["items"][0]["kind"] == "mentioned" and "refund" in ada["items"][0]["body"]
    assignee = omar.get("/api/v1/notifications").json()["data"]
    assert assignee["unread"] == 1 and assignee["items"][0]["kind"] == "note"
    assert grace.get("/api/v1/notifications").json()["data"]["unread"] == 0

    # A reply sent afterwards carries no trace of the note.
    client.post("/api/v1/messages/send", json={"account_id": account["id"], "conversation_id": invoice["id"], "in_reply_to": "<a2@example.com>",
                                              "to": ["maya@example.com"], "subject": "Re: Invoice 1042", "body_text": "Refund approved."})
    assert "Customer called" not in base64.urlsafe_b64decode(google.sent[0]["raw"]).decode()

    recent = client.get("/api/v1/notes").json()["data"]
    assert recent[0]["conversation_subject"] == "Invoice 1042" and recent[0]["id"] == note["id"]

    assert omar.delete(f"/api/v1/notes/{note['id']}").status_code == 403   # not the author, not an owner or admin
    assert grace.delete(f"/api/v1/notes/{note['id']}").status_code == 204
    assert client.get(f"/api/v1/conversations/{invoice['id']}").json()["data"]["notes"] == []
    assert grace.post(f"/api/v1/conversations/{invoice['id']}/notes", json={"body": "   "}).status_code == 422


def test_notes_follow_mailbox_access_and_viewers_cannot_write_them(client, member, google):
    account = _mailbox(client, google)
    grace, _ = _join(client, "grace@example.com", "Grace Hopper", "agent")
    vera, _ = _join(client, "vera@example.com", "Vera Viewer", "viewer")
    invoice = _conv(client, "Invoice 1042")
    note = client.post(f"/api/v1/conversations/{invoice['id']}/notes", json={"body": "Owner only context"}).json()["data"]
    assert vera.post(f"/api/v1/conversations/{invoice['id']}/notes", json={"body": "hi"}).status_code == 403
    assert len(vera.get("/api/v1/notes").json()["data"]) == 1  # a viewer may read them

    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted"})
    assert grace.get("/api/v1/notes").json()["data"] == []
    assert grace.post(f"/api/v1/conversations/{invoice['id']}/notes", json={"body": "hi"}).status_code == 404
    assert grace.delete(f"/api/v1/notes/{note['id']}").status_code == 404


# --- contacts ----------------------------------------------------------------------------

def test_contacts_come_from_the_real_mail(client, member, google):
    account = _mailbox(client, google)
    client.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["lena@example.com", "maya@example.com"], "subject": "Hello", "body_text": "Hi"})
    people = {p["email"]: p for p in client.get("/api/v1/contacts").json()["data"]}
    assert set(people) == {"maya@example.com", "omar@example.com", "lena@example.com"}  # the mailbox itself is not a contact
    assert people["maya@example.com"]["name"] == "Maya Chen" and people["maya@example.com"]["received"] == 2 and people["maya@example.com"]["sent"] == 1
    assert people["lena@example.com"]["received"] == 0 and people["lena@example.com"]["sent"] == 1 and people["lena@example.com"]["name"] is None
    assert [p["email"] for p in client.get("/api/v1/contacts?search=omar").json()["data"]] == ["omar@example.com"]
    assert [p["email"] for p in client.get("/api/v1/contacts?search=chen").json()["data"]] == ["maya@example.com"]
    assert len(client.get("/api/v1/contacts?limit=2").json()["data"]) == 2 and len(client.get("/api/v1/contacts?limit=2&offset=2").json()["data"]) == 1

    grace, _ = _join(client, "grace@example.com", "Grace Hopper", "agent")
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted"})
    assert grace.get("/api/v1/contacts").json()["data"] == []


# --- templates -----------------------------------------------------------------------------

def test_templates_are_shared_and_only_some_roles_change_them(client, member, google):
    grace, _ = _join(client, "grace@example.com", "Grace Hopper", "agent")
    omar, _ = _join(client, "omar@example.com", "Omar Haddad", "manager")
    created = omar.post("/api/v1/templates", json={"name": " Refund  approved ", "subject": "Your refund", "body": "Hi {{recipient_name}},\n\nYour refund is on its way.\n\n{{my_name}}"})
    assert created.status_code == 201
    template = created.json()["data"]
    assert template["name"] == "Refund approved" and template["created_by_name"] == "Omar Haddad"
    assert omar.post("/api/v1/templates", json={"name": "Refund approved", "body": "x"}).status_code == 409
    assert omar.post("/api/v1/templates", json={"name": "Empty", "body": ""}).status_code == 422

    assert [t["name"] for t in grace.get("/api/v1/templates").json()["data"]] == ["Refund approved"]  # everyone can use them
    assert grace.post("/api/v1/templates", json={"name": "Mine", "body": "x"}).status_code == 403
    assert grace.put(f"/api/v1/templates/{template['id']}", json={"name": "Hacked", "body": "x"}).status_code == 403
    assert grace.delete(f"/api/v1/templates/{template['id']}").status_code == 403

    changed = client.put(f"/api/v1/templates/{template['id']}", json={"name": "Refund sent", "subject": "", "body": "Done."}).json()["data"]
    assert changed["name"] == "Refund sent" and changed["body"] == "Done." and changed["created_by_name"] == "Omar Haddad"
    assert client.delete(f"/api/v1/templates/{template['id']}").status_code == 204
    assert client.get("/api/v1/templates").json()["data"] == []


def test_none_of_it_crosses_workspaces(client, member, google):
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import PASSWORD

    account = _mailbox(client, google)
    invoice = _conv(client, "Invoice 1042")
    draft = client.post("/api/v1/drafts", json={"email_account_id": account["id"], "subject": "Mine"}).json()["data"]
    note = client.post(f"/api/v1/conversations/{invoice['id']}/notes", json={"body": "Private"}).json()["data"]
    template = client.post("/api/v1/templates", json={"name": "Ours", "body": "x"}).json()["data"]

    other = TestClient(app)
    other.post("/api/v1/auth/register", json={"email": "eve@example.com", "password": PASSWORD, "name": "Eve Other"})
    other.post("/api/v1/workspaces", json={"name": "Elsewhere"})
    eve_id = other.get("/api/v1/auth/me").json()["data"]["user"]["id"]
    for path in ("/drafts", "/notes", "/contacts", "/templates"):
        assert other.get(f"/api/v1{path}").json()["data"] == [], path
    assert other.get("/api/v1/notifications").json()["data"] == {"unread": 0, "items": []}
    assert other.put(f"/api/v1/drafts/{draft['id']}", json={"email_account_id": account["id"]}).status_code == 404
    assert other.delete(f"/api/v1/notes/{note['id']}").status_code == 404
    assert other.put(f"/api/v1/templates/{template['id']}", json={"name": "x", "body": "x"}).status_code == 404
    assert other.post(f"/api/v1/conversations/{invoice['id']}/notes", json={"body": "x"}).status_code == 404
    assert client.patch(f"/api/v1/conversations/{invoice['id']}", json={"assignee_user_id": eve_id}).status_code == 404
