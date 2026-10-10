import json
import pytest
from sqlalchemy import select

from app.core import security
from app.models.email import Conversation, EmailAccount, Folder, Message, MessageRecipient
from app.providers.imap_smtp import ImapSmtpProvider
from tests.conftest import PASSWORD


def test_encryption_roundtrip():
    secret = "SuperSecretPassword!@#123"
    encrypted = security.encrypt_secret(secret)
    assert encrypted != secret
    assert secret not in encrypted
    decrypted = security.decrypt_secret(encrypted)
    assert decrypted == secret


def test_connect_email_account_failure(client, member, monkeypatch):
    monkeypatch.setattr(
        ImapSmtpProvider,
        "test_connection",
        lambda self: (False, "IMAP authentication failed: Invalid login"),
    )

    payload = {
        "provider": "imap",
        "email_address": "support@company.com",
        "display_name": "Support Team",
        "incoming_host": "imap.example.com",
        "incoming_port": 993,
        "incoming_security": "ssl",
        "incoming_username": "support@company.com",
        "incoming_password": "wrong-password",
        "outgoing_host": "smtp.example.com",
        "outgoing_port": 465,
        "outgoing_security": "ssl",
        "outgoing_username": "support@company.com",
        "outgoing_password": "wrong-password",
    }
    res = client.post("/api/v1/email-accounts/connect", json=payload)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "CONNECTION_FAILED"


def test_connect_account_and_list(client, member, db, monkeypatch):
    monkeypatch.setattr(ImapSmtpProvider, "test_connection", lambda self: (True, None))
    monkeypatch.setattr(
        ImapSmtpProvider,
        "list_folders",
        lambda self: [
            {"name": "INBOX", "system_folder": "inbox"},
            {"name": "Sent Messages", "system_folder": "sent"},
        ],
    )

    payload = {
        "provider": "gmail",
        "email_address": "team@example.com",
        "display_name": "Team Inbox",
        "incoming_host": "imap.gmail.com",
        "incoming_port": 993,
        "incoming_security": "ssl",
        "incoming_username": "team@example.com",
        "incoming_password": "app-password-1234",
        "outgoing_host": "smtp.gmail.com",
        "outgoing_port": 465,
        "outgoing_security": "ssl",
        "outgoing_username": "team@example.com",
        "outgoing_password": "app-password-1234",
    }

    res = client.post("/api/v1/email-accounts/connect", json=payload)
    assert res.status_code == 201
    account_data = res.json()["data"]
    assert account_data["email_address"] == "team@example.com"
    assert account_data["display_name"] == "Team Inbox"
    acc_id = account_data["id"]

    # Verify password was never returned in response
    assert "password" not in str(res.json())

    # Verify DB stores encrypted credentials
    db_acc = db.get(EmailAccount, acc_id)
    assert db_acc is not None
    assert "app-password-1234" not in db_acc.credentials_encrypted
    decrypted = json.loads(security.decrypt_secret(db_acc.credentials_encrypted))
    assert decrypted["incoming_password"] == "app-password-1234"

    # List accounts endpoint
    list_res = client.get("/api/v1/email-accounts")
    assert list_res.status_code == 200
    accounts = list_res.json()["data"]
    assert len(accounts) == 1
    assert accounts[0]["email_address"] == "team@example.com"
    assert accounts[0]["message_count"] == 0

    # Disconnect account
    del_res = client.delete(f"/api/v1/email-accounts/{acc_id}")
    assert del_res.status_code == 204

    # Now listing accounts is empty
    empty_res = client.get("/api/v1/email-accounts")
    assert empty_res.status_code == 200
    assert len(empty_res.json()["data"]) == 0


def test_conversations_and_send_mail(client, member, db, monkeypatch):
    monkeypatch.setattr(ImapSmtpProvider, "test_connection", lambda self: (True, None))
    monkeypatch.setattr(
        ImapSmtpProvider,
        "list_folders",
        lambda self: [{"name": "INBOX", "system_folder": "inbox"}],
    )
    monkeypatch.setattr(
        ImapSmtpProvider,
        "send_message",
        lambda self, to, subject, body_text, body_html=None, **kwargs: "<msg-12345@domain.com>",
    )

    # 1. Connect an account
    connect_res = client.post(
        "/api/v1/email-accounts/connect",
        json={
            "provider": "imap",
            "email_address": "support@mycompany.com",
            "display_name": "Support",
            "incoming_host": "imap.mycompany.com",
            "incoming_port": 993,
            "incoming_security": "ssl",
            "incoming_username": "support@mycompany.com",
            "incoming_password": "secret",
            "outgoing_host": "smtp.mycompany.com",
            "outgoing_port": 465,
            "outgoing_security": "ssl",
            "outgoing_username": "support@mycompany.com",
            "outgoing_password": "secret",
        },
    )
    assert connect_res.status_code == 201
    account_id = connect_res.json()["data"]["id"]

    # 2. Send an outbound email
    send_payload = {
        "account_id": account_id,
        "to": ["customer@example.com"],
        "subject": "Thank you for reaching out!",
        "body_text": "Hello, we received your inquiry and are happy to help.",
    }
    send_res = client.post("/api/v1/messages/send", json=send_payload)
    assert send_res.status_code == 201

    # 3. Filter by sent view to get conversation
    sent_list = client.get("/api/v1/conversations?view=sent")
    assert sent_list.status_code == 200
    sent_convs = sent_list.json()["data"]
    assert len(sent_convs) == 1
    conv_id = sent_convs[0]["id"]

    # 4. View sent conversation detail
    detail_res = client.get(f"/api/v1/conversations/{conv_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()["data"]
    assert detail["conversation"]["subject"] == "Thank you for reaching out!"
    assert len(detail["messages"]) == 1
    msg = detail["messages"][0]
    assert msg["direction"] == "outbound"
    assert "Hello, we received your inquiry" in msg["body_text"]

    # 5. Star the conversation
    patch_star = client.patch(f"/api/v1/conversations/{conv_id}", json={"is_starred": True})
    assert patch_star.status_code == 200
    assert patch_star.json()["data"]["is_starred"] is True

    starred_list = client.get("/api/v1/conversations?view=starred")
    assert starred_list.status_code == 200
    assert len(starred_list.json()["data"]) == 1

    # 6. Archive the conversation
    patch_archive = client.patch(f"/api/v1/conversations/{conv_id}", json={"is_archived": True})
    assert patch_archive.status_code == 200
    assert patch_archive.json()["data"]["is_archived"] is True

    archived_list = client.get("/api/v1/conversations?view=archive")
    assert archived_list.status_code == 200
    assert len(archived_list.json()["data"]) == 1
