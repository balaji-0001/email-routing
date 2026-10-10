import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Workspace, WorkspaceMember, User
from tests.conftest import PASSWORD


def error_code(response):
    return response.json()["error"]["code"]


def second_person(email="grace@example.com", name="Grace Hopper"):
    browser = TestClient(app)
    response = browser.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "name": name})
    assert response.status_code == 201
    return browser


def test_invite_member_flow(client, member):
    # 1. Owner creates invitation
    invite_res = client.post(
        "/api/v1/workspace/invitations",
        json={"email": "grace@example.com", "role": "manager"},
    )
    assert invite_res.status_code == 201
    invite_data = invite_res.json()["data"]
    assert invite_data["email"] == "grace@example.com"
    assert invite_data["role"] == "manager"
    assert "token" in invite_data
    assert "invite_url" in invite_data
    token = invite_data["token"]

    # 2. List invitations
    list_res = client.get("/api/v1/workspace/invitations")
    assert list_res.status_code == 200
    invites = list_res.json()["data"]
    assert len(invites) == 1
    assert invites[0]["email"] == "grace@example.com"

    # 3. View invitation publicly with token
    guest = TestClient(app)
    view_res = guest.get(f"/api/v1/auth/invitations/{token}")
    assert view_res.status_code == 200
    details = view_res.json()["data"]
    assert details["email"] == "grace@example.com"
    assert details["workspace_name"] == "Analytical Engines"

    # 4. Grace registers and accepts the invitation
    grace = second_person("grace@example.com", "Grace Hopper")
    accept_res = grace.post(f"/api/v1/auth/invitations/{token}/accept")
    assert accept_res.status_code == 200
    accepted = accept_res.json()["data"]
    assert accepted["workspace"]["name"] == "Analytical Engines"
    assert accepted["role"] == "manager"

    # 5. Grace is now in the workspace as manager
    me = grace.get("/api/v1/auth/me").json()["data"]
    assert me["workspace"]["name"] == "Analytical Engines"
    assert me["role"] == "manager"


def test_revoke_invitation(client, member):
    invite_res = client.post(
        "/api/v1/workspace/invitations",
        json={"email": "alan@example.com", "role": "agent"},
    )
    assert invite_res.status_code == 201
    inv_id = invite_res.json()["data"]["id"]
    token = invite_res.json()["data"]["token"]

    # Revoke it
    del_res = client.delete(f"/api/v1/workspace/invitations/{inv_id}")
    assert del_res.status_code == 204

    # Now token is invalid / not found
    guest = TestClient(app)
    view_res = guest.get(f"/api/v1/auth/invitations/{token}")
    assert view_res.status_code == 404


def test_agent_cannot_invite(client, member, db):
    grace = second_person("agent@example.com", "Agent Smith")
    workspace = db.scalar(select(Workspace))
    user = db.scalar(select(User).where(User.email == "agent@example.com"))
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="agent"))
    db.commit()

    # Sign in as agent
    grace.post("/api/v1/auth/logout")
    grace.post("/api/v1/auth/login", json={"email": "agent@example.com", "password": PASSWORD})

    res = grace.post("/api/v1/workspace/invitations", json={"email": "third@example.com", "role": "viewer"})
    assert res.status_code == 403
    assert error_code(res) == "FORBIDDEN"


def test_switch_workspace(client, member, db):
    # Create second workspace for another owner
    grace = second_person("grace@example.com", "Grace")
    grace.post("/api/v1/workspaces", json={"name": "Grace Works"})

    # Grace invites Ada (the original member) to Grace Works
    inv = grace.post("/api/v1/workspace/invitations", json={"email": "ada@example.com", "role": "admin"}).json()["data"]
    token = inv["token"]

    # Ada accepts the invitation
    accept = client.post(f"/api/v1/auth/invitations/{token}/accept")
    assert accept.status_code == 200

    # Ada lists her workspaces - should see both
    ws_res = client.get("/api/v1/auth/workspaces")
    assert ws_res.status_code == 200
    workspaces = ws_res.json()["data"]
    assert len(workspaces) == 2
    ws_names = [w["name"] for w in workspaces]
    assert "Analytical Engines" in ws_names
    assert "Grace Works" in ws_names

    # Ada switches to Grace Works
    grace_ws = next(w for w in workspaces if w["name"] == "Grace Works")
    switch_res = client.post(f"/api/v1/auth/workspaces/{grace_ws['id']}/switch")
    assert switch_res.status_code == 200

    # Current workspace is now Grace Works
    me = client.get("/api/v1/auth/me").json()["data"]
    assert me["workspace"]["name"] == "Grace Works"
    assert me["role"] == "admin"
