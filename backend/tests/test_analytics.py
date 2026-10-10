"""The Analytics figures are counted from real records, and only for mailboxes the reader may open."""

from datetime import datetime, timezone

from tests.test_automation import _arrive, _conv, _ready, _rule
from tests.test_gmail_oauth import google  # noqa: F401 - fixture
from tests.test_mailbox_access import _join


def test_the_report_counts_what_really_happened(client, member, google):
    account = _ready(client, google)
    _rule(client, "Flag invoices", {"subject": "invoice"}, [{"type": "flag"}])
    _arrive(client, google, account, "n1", "Invoice 9")
    _arrive(client, google, account, "n2", "Hello there", sender="Omar <omar@example.com>")
    conversation = _conv(client, "Invoice 9")
    assert client.post("/api/v1/messages/send", json={"account_id": account["id"], "to": ["maya@example.com"], "subject": "Re: Invoice 9", "body_text": "Paid.", "conversation_id": conversation["id"], "in_reply_to": "<n1@example.com>"}).status_code == 201
    client.patch(f"/api/v1/conversations/{conversation['id']}", json={"status": "pending", "assignee_user_id": member["user"]["id"]})

    report = client.get("/api/v1/analytics?days=90").json()["data"]
    assert len(report["daily"]) == 90 and report["daily"][-1]["day"] == str(datetime.now(timezone.utc).date())
    assert report["totals"]["received"] == 3 and report["totals"]["sent"] == 1 and report["totals"]["rule_runs"] == 1 and report["totals"]["rule_failures"] == 0
    assert sum(d["received"] for d in report["daily"]) == 3 and report["daily"][-1]["sent"] == 1 and report["daily"][-1]["rule_runs"] == 1
    assert report["replies"]["count"] == 1 and report["replies"]["median_hours"] > 0
    assert report["now"]["pending"] == 1 and report["now"]["open"] == 2 and report["now"]["unassigned"] == 2
    assert report["workload"] == [{"name": "Ada Lovelace", "open": 1}]
    assert {s["email"]: s["received"] for s in report["top_senders"]} == {"maya@example.com": 1, "omar@example.com": 1, "old@example.com": 1}
    assert report["mailboxes"] == [{"email_address": "team@gmail.com", "received": 3, "sent": 1}]
    assert [(r["name"], r["runs"], r["failed"]) for r in report["rules"]] == [("Flag invoices", 1, 0)]
    assert report["rules"][0]["last_run_at"].endswith("Z")  # marked as UTC, so browsers do not read it as local time
    assert report["ai"]["analysed"] == 0 and report["ai"]["sent_automatically"] == 0
    assert client.get("/api/v1/analytics?days=0").status_code == 422 and client.get("/api/v1/analytics?days=91").status_code == 422


def test_the_report_leaves_out_mailboxes_the_reader_cannot_open(client, member, google):
    account = _ready(client, google)
    _rule(client, "Flag all", {}, [{"type": "flag"}])
    _arrive(client, google, account, "n1", "Secret deal")
    grace, _ = _join(client, "grace@example.com", "Grace Hopper", "agent")
    assert grace.get("/api/v1/analytics").json()["data"]["totals"]["received"] == 2
    client.put(f"/api/v1/email-accounts/{account['id']}/access", json={"access_mode": "restricted", "members": []})
    hidden = grace.get("/api/v1/analytics").json()["data"]
    assert hidden["totals"] == {"received": 0, "sent": 0, "rule_runs": 0, "rule_failures": 0}
    assert hidden["top_senders"] == [] and hidden["mailboxes"] == [] and hidden["now"]["open"] == 0 and all(r["runs"] == 0 for r in hidden["rules"])

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import PASSWORD

    other = TestClient(app)
    other.post("/api/v1/auth/register", json={"email": "eve@example.com", "password": PASSWORD, "name": "Eve Elsewhere"})
    other.post("/api/v1/workspaces", json={"name": "Elsewhere"})
    elsewhere = other.get("/api/v1/analytics").json()["data"]
    assert elsewhere["totals"]["received"] == 0 and elsewhere["rules"] == [] and elsewhere["top_senders"] == []
