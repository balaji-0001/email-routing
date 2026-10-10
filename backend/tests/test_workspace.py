from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import User, Workspace, WorkspaceMember
from tests.conftest import PASSWORD


def error_code(response):
    return response.json()["error"]["code"]


def second_person(email="grace@example.com", name="Grace Hopper"):
    """Another signed-up person on their own browser."""
    browser = TestClient(app)
    response = browser.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "name": name})
    assert response.status_code == 201
    return browser


def test_workspace_routes_need_a_workspace(client, signed_up):
    for path in ("/api/v1/workspace/members", "/api/v1/workspace/audit-events"):
        response = client.get(path)
        assert response.status_code == 409 and error_code(response) == "WORKSPACE_REQUIRED"


def test_workspace_routes_need_a_session(client):
    assert client.get("/api/v1/workspace/members").status_code == 401
    assert client.post("/api/v1/workspaces", json={"name": "Nope"}).status_code == 401


def test_creating_a_workspace_makes_you_its_owner(client, signed_up):
    created = client.post("/api/v1/workspaces", json={"name": "  Analytical Engines  "})
    assert created.status_code == 201
    assert created.json()["data"]["name"] == "Analytical Engines"

    me = client.get("/api/v1/auth/me").json()["data"]
    assert me["workspace"]["name"] == "Analytical Engines" and me["role"] == "owner"

    again = client.post("/api/v1/workspaces", json={"name": "Another"})
    assert again.status_code == 409 and error_code(again) == "WORKSPACE_EXISTS"


def test_signing_in_again_lands_in_the_workspace(client, member):
    browser = TestClient(app)
    data = browser.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).json()["data"]
    assert data["workspace"]["name"] == "Analytical Engines" and data["role"] == "owner"


def test_members_lists_real_people_only(client, member):
    members = client.get("/api/v1/workspace/members").json()["data"]
    assert len(members) == 1
    assert members[0]["name"] == "Ada Lovelace" and members[0]["email"] == "ada@example.com"
    assert members[0]["role"] == "owner" and members[0]["is_you"] is True
    assert members[0]["last_active_at"] is not None


def test_owner_can_update_the_workspace(client, member):
    response = client.patch("/api/v1/workspace", json={"name": "Engines Ltd", "domain": "Engines.Example ", "timezone": "Europe/London", "allow_invitations": False})
    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["name"], data["domain"], data["timezone"], data["allow_invitations"]) == ("Engines Ltd", "engines.example", "Europe/London", False)

    # Only what is sent changes; an empty domain clears it.
    cleared = client.patch("/api/v1/workspace", json={"domain": ""}).json()["data"]
    assert cleared["domain"] is None and cleared["name"] == "Engines Ltd"

    bad = client.patch("/api/v1/workspace", json={"timezone": "Mars/Olympus"})
    assert bad.status_code == 422 and bad.json()["error"]["details"][0]["field"] == "timezone"


def test_profile_update(client, member):
    response = client.patch("/api/v1/users/me", json={"first_name": " Augusta ", "last_name": "King", "timezone": "Asia/Kolkata"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["first_name"], data["last_name"], data["name"], data["timezone"]) == ("Augusta", "King", "Augusta King", "Asia/Kolkata")
    assert client.patch("/api/v1/users/me", json={"first_name": "", "last_name": "King"}).status_code == 422
    assert client.patch("/api/v1/users/me", json={"first_name": "Ada", "timezone": "Nowhere/Town"}).status_code == 422


def test_only_owners_and_admins_manage_the_workspace(client, member, db):
    grace = second_person()
    workspace = db.scalar(select(Workspace))
    grace_user = db.scalar(select(User).where(User.email == "grace@example.com"))
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=grace_user.id, role="agent"))
    db.commit()
    # A fresh sign-in picks the workspace up.
    grace.post("/api/v1/auth/logout")
    grace.post("/api/v1/auth/login", json={"email": "grace@example.com", "password": PASSWORD})

    assert grace.get("/api/v1/auth/me").json()["data"]["role"] == "agent"
    assert len(grace.get("/api/v1/workspace/members").json()["data"]) == 2
    forbidden = grace.patch("/api/v1/workspace", json={"name": "Mine now"})
    assert forbidden.status_code == 403 and error_code(forbidden) == "FORBIDDEN"
    assert grace.get("/api/v1/workspace/audit-events").status_code == 403
    assert client.get("/api/v1/auth/me").json()["data"]["workspace"]["name"] == "Analytical Engines"


def test_workspaces_cannot_see_each_other(client, member):
    grace = second_person()
    grace.post("/api/v1/workspaces", json={"name": "Compilers Inc"})

    theirs = grace.get("/api/v1/workspace/members").json()["data"]
    assert [m["email"] for m in theirs] == ["grace@example.com"]
    mine = client.get("/api/v1/workspace/members").json()["data"]
    assert [m["email"] for m in mine] == ["ada@example.com"]

    their_log = " ".join(event["summary"] for event in grace.get("/api/v1/workspace/audit-events").json()["data"])
    assert "Compilers Inc" in their_log and "Analytical Engines" not in their_log


def test_audit_log_records_what_happened(client, member):
    client.patch("/api/v1/workspace", json={"name": "Engines Ltd"})
    client.patch("/api/v1/users/me", json={"first_name": "Ada", "last_name": "Lovelace", "timezone": "UTC"})
    client.post("/api/v1/auth/password/change", json={"current_password": PASSWORD, "new_password": "a-brand-new-password"})

    events = client.get("/api/v1/workspace/audit-events").json()["data"]
    assert [event["action"] for event in events] == ["password.changed", "profile.updated", "workspace.updated", "workspace.created"]
    assert events[2]["summary"] == "Renamed the workspace to Engines Ltd"
    assert all(event["actor_name"] == "Ada Lovelace" and event["actor_is_you"] for event in events)
    assert events[0]["created_at"].endswith("Z")

    assert len(client.get("/api/v1/workspace/audit-events", params={"limit": 2}).json()["data"]) == 2
    assert client.get("/api/v1/workspace/audit-events", params={"limit": 0}).status_code == 422
