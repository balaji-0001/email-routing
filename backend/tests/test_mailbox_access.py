"""Who may use each mailbox: open to everyone, or limited to chosen people with read or send."""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import PASSWORD
from tests.test_gmail_oauth import _connect, google  # noqa: F401 - `google` is a fixture


def _join(owner, email: str, name: str, role: str) -> tuple[TestClient, int]:
    """A second person who accepts an invitation with the given role. Returns their browser and user id."""
    token = owner.post("/api/v1/workspace/invitations", json={"email": email, "role": role}).json()["data"]["token"]
    browser = TestClient(app)
    assert browser.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "name": name}).status_code == 201
    assert browser.post(f"/api/v1/auth/invitations/{token}/accept").status_code == 200
    return browser, browser.get("/api/v1/auth/me").json()["data"]["user"]["id"]


def _mailbox(client, google):
    google.deliver("m1", "t1", sender="Maya Chen <maya@example.com>", subject="Invoice 1042", body="Please pay.", message_id="<a1@example.com>", files=[("invoice.pdf", b"pdf bytes")])
    account = _connect(client)
    client.post(f"/api/v1/email-accounts/{account['id']}/sync")
    return account


def test_a_mailbox_is_open_to_the_workspace_until_it_is_restricted(client, member, google):
    account = _mailbox(client, google)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")

    listed = grace.get("/api/v1/email-accounts").json()["data"]
    assert [a["email_address"] for a in listed] == ["team@gmail.com"] and listed[0]["access_mode"] == "everyone" and listed[0]["my_permission"] == "send"
    assert len(grace.get("/api/v1/conversations?view=inbox").json()["data"]) == 1

    access = client.get(f"/api/v1/email-accounts/{account['id']}/access").json()["data"]
    assert access["access_mode"] == "everyone"
    people = {p["email"]: p for p in access["members"]}
    assert people["ada@example.com"]["always"] is True and people["ada@example.com"]["permission"] == "send"
    assert people["grace@example.com"]["always"] is False and people["grace@example.com"]["permission"] is None

    # Only owners and admins decide who has access.
    assert grace.get(f"/api/v1/email-accounts/{account['id']}/access").status_code == 403
    assert grace.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "members": []}).status_code == 403


def test_restricting_hides_the_mailbox_and_its_mail_from_everyone_not_chosen(client, member, google):
    account = _mailbox(client, google)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    conversation = client.get("/api/v1/conversations?view=inbox").json()["data"][0]
    detail = client.get(f"/api/v1/conversations/{conversation['id']}").json()["data"]
    attachment_id = detail["messages"][0]["attachments"][0]["id"]
    label = client.post("/api/v1/labels", json={"name": "Billing"}).json()["data"]

    saved = client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "members": []})
    assert saved.status_code == 200 and saved.json()["data"]["access_mode"] == "restricted"

    assert grace.get("/api/v1/email-accounts").json()["data"] == []
    assert grace.get("/api/v1/conversations?view=inbox").json()["data"] == []
    assert grace.get("/api/v1/conversations?view=all&search=Invoice").json()["data"] == []
    assert grace.get("/api/v1/conversations/counts").json()["data"] == {"inbox_unread": 0, "inbox_unread_by_account": {}}
    assert grace.get(f"/api/v1/conversations/{conversation['id']}").status_code == 404
    assert grace.patch(f"/api/v1/conversations/{conversation['id']}", json={"is_starred": True}).status_code == 404
    assert grace.post("/api/v1/conversations/batch", json={"conversation_ids": [conversation["id"]], "action": "delete"}).json()["data"]["updated"] == 0
    assert grace.put(f"/api/v1/conversations/{conversation['id']}/labels", json={"label_ids": [label["id"]]}).status_code == 404
    assert grace.get(f"/api/v1/attachments/{attachment_id}").status_code == 404
    assert grace.post(f"/api/v1/email-accounts/{account['id']}/sync").status_code == 404
    assert grace.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["x@example.com"], "subject": "x"}).status_code == 404
    assert grace.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["x@example.com"], "subject": "x", "forward_attachments_of": detail["messages"][0]["id"]}).status_code == 404

    # The owner is unaffected, and nothing was deleted by the refused batch.
    assert len(client.get("/api/v1/conversations?view=inbox").json()["data"]) == 1
    events = [e["action"] for e in client.get("/api/v1/workspace/audit-events").json()["data"]]
    assert "email_account.access_changed" in events


def test_read_only_and_send_permissions(client, member, google):
    account = _mailbox(client, google)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    omar, omar_id = _join(client, "omar@example.com", "Omar Haddad", "agent")

    saved = client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "members": [
        {"user_id": grace_id, "permission": "read"}, {"user_id": omar_id, "permission": "send"},
    ]}).json()["data"]
    assert {p["email"]: p["permission"] for p in saved["members"]} == {"ada@example.com": "send", "grace@example.com": "read", "omar@example.com": "send"}

    assert grace.get("/api/v1/email-accounts").json()["data"][0]["my_permission"] == "read"
    conversation = grace.get("/api/v1/conversations?view=inbox").json()["data"][0]
    assert grace.get(f"/api/v1/conversations/{conversation['id']}").status_code == 200
    refused = grace.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["maya@example.com"], "subject": "Re: Invoice 1042"})
    assert refused.status_code == 403 and "not send" in refused.json()["error"]["message"]

    assert omar.get("/api/v1/email-accounts").json()["data"][0]["my_permission"] == "send"
    assert omar.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["maya@example.com"], "subject": "Re: Invoice 1042", "body_text": "On it."}).status_code == 201

    # Opening it again gives everyone back what their role allows.
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "everyone", "members": []})
    assert grace.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["maya@example.com"], "subject": "Hello", "body_text": "Hi"}).status_code == 201


def test_access_cannot_be_given_to_people_outside_the_workspace_or_with_made_up_levels(client, member, google):
    account = _mailbox(client, google)
    stranger = TestClient(app)
    stranger.post("/api/v1/auth/register", json={"email": "eve@example.com", "password": PASSWORD, "name": "Eve Stranger"})
    eve_id = stranger.get("/api/v1/auth/me").json()["data"]["user"]["id"]
    url = f"/api/v1/email-accounts/{account['id']}/access"
    assert client.put(url, json={"access_mode": "restricted", "members": [{"user_id": eve_id, "permission": "send"}]}).status_code == 404
    assert client.put(url, json={"access_mode": "restricted", "members": [{"user_id": member["user"]["id"], "permission": "admin"}]}).status_code == 422
    assert client.put(url, json={"access_mode": "secret", "members": []}).status_code == 422
    assert client.get(url).json()["data"]["access_mode"] == "everyone"
    assert client.get("/api/v1/email-accounts/999999/access").status_code == 404


def test_viewers_read_but_never_change_or_send(client, member, google):
    account = _mailbox(client, google)
    vera, vera_id = _join(client, "vera@example.com", "Vera Viewer", "viewer")
    conversation = vera.get("/api/v1/conversations?view=inbox").json()["data"][0]
    assert vera.get("/api/v1/email-accounts").json()["data"][0]["my_permission"] == "read"
    assert vera.patch(f"/api/v1/conversations/{conversation['id']}", json={"status": "closed"}).status_code == 403
    assert vera.post("/api/v1/conversations/batch", json={"conversation_ids": [conversation["id"]], "action": "delete"}).status_code == 403
    assert vera.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["a@example.com"], "subject": "x"}).status_code == 403
    # Even when a restricted mailbox lists them with "send".
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "members": [{"user_id": vera_id, "permission": "send"}]})
    assert vera.get("/api/v1/email-accounts").json()["data"][0]["my_permission"] == "read"
    assert vera.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["a@example.com"], "subject": "x"}).status_code == 403


def test_access_can_be_given_to_whole_roles(client, member, google):
    account = _mailbox(client, google)
    grace, grace_id = _join(client, "grace@example.com", "Grace Hopper", "agent")
    omar, omar_id = _join(client, "omar@example.com", "Omar Haddad", "manager")
    vera, vera_id = _join(client, "vera@example.com", "Vera Viewer", "viewer")
    url = f"/api/v1/email-accounts/{account['id']}/access"

    listed = client.get(url).json()["data"]["roles"]
    assert [(r["role"], r["name"], r["description"]) for r in listed] == [
        ("owner", "Owner", "Created the workspace"), ("admin", "Admin", "Runs the workspace"), ("manager", "Manager", "Leads a team"),
        ("agent", "Agent", "Works conversations"), ("viewer", "Viewer", "Read-only access"),
    ]
    assert {r["role"]: (r["always"], r["permission"], r["people"]) for r in listed} == {
        "owner": (True, "send", 1), "admin": (True, "send", 0), "manager": (False, None, 1), "agent": (False, None, 1), "viewer": (False, None, 1),
    }

    saved = client.put(url, json={"access_mode": "restricted", "roles": [
        {"role": "manager", "permission": "send"}, {"role": "agent", "permission": "read"}, {"role": "owner", "permission": "read"},
    ]}).json()["data"]
    assert {r["role"]: r["permission"] for r in saved["roles"]} == {"owner": "send", "admin": "send", "manager": "send", "agent": "read", "viewer": None}

    send = {"account_id": account["id"], "to": ["maya@example.com"], "subject": "Hello", "body_text": "Hi"}
    assert omar.get("/api/v1/email-accounts").json()["data"][0]["my_permission"] == "send"
    assert omar.post("/api/v1/messages/send", json=send).status_code == 201
    assert grace.get("/api/v1/email-accounts").json()["data"][0]["my_permission"] == "read"
    assert len(grace.get("/api/v1/conversations?view=inbox").json()["data"]) == 1
    assert grace.post("/api/v1/messages/send", json=send).status_code == 403
    assert vera.get("/api/v1/email-accounts").json()["data"] == []
    assert vera.get("/api/v1/conversations?view=all").json()["data"] == []

    # A person can be given more than their role has; the higher of the two applies.
    client.put(url, json={"access_mode": "restricted", "roles": [{"role": "agent", "permission": "read"}, {"role": "viewer", "permission": "send"}],
                          "members": [{"user_id": grace_id, "permission": "send"}]})
    assert grace.post("/api/v1/messages/send", json=send).status_code == 201
    assert omar.get("/api/v1/email-accounts").json()["data"] == []  # managers were left out this time
    # Viewers read at most, whatever was sent.
    assert vera.get("/api/v1/email-accounts").json()["data"][0]["my_permission"] == "read"
    assert vera.post("/api/v1/messages/send", json=send).status_code == 403

    assert client.put(url, json={"access_mode": "restricted", "roles": [{"role": "boss", "permission": "send"}]}).status_code == 422
    summaries = [e["summary"] for e in client.get("/api/v1/workspace/audit-events").json()["data"]]
    assert any("managers, agents" in s for s in summaries)
