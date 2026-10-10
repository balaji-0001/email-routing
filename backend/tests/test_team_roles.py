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


def test_update_member_role(client, member, db):
    # Add a second member
    grace = second_person("grace@example.com", "Grace Hopper")
    workspace = db.scalar(select(Workspace))
    grace_user = db.scalar(select(User).where(User.email == "grace@example.com"))
    grace_member = WorkspaceMember(workspace_id=workspace.id, user_id=grace_user.id, role="agent")
    db.add(grace_member)
    db.commit()

    # Owner promotes Grace from agent to manager
    res = client.patch(f"/api/v1/workspace/members/{grace_member.id}", json={"role": "manager"})
    assert res.status_code == 200
    assert res.json()["data"]["role"] == "manager"

    # Member list reflects new role
    members = client.get("/api/v1/workspace/members").json()["data"]
    gm = next(m for m in members if m["email"] == "grace@example.com")
    assert gm["role"] == "manager"


def test_cannot_change_own_role(client, member, db):
    workspace = db.scalar(select(Workspace))
    owner_user = db.scalar(select(User).where(User.email == "ada@example.com"))
    owner_member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == owner_user.id))

    # Trying to change own role returns 400 CANNOT_CHANGE_OWN_ROLE
    res = client.patch(f"/api/v1/workspace/members/{owner_member.id}", json={"role": "admin"})
    assert res.status_code == 400
    assert error_code(res) == "CANNOT_CHANGE_OWN_ROLE"


def test_remove_member(client, member, db):
    grace = second_person("grace@example.com", "Grace Hopper")
    workspace = db.scalar(select(Workspace))
    grace_user = db.scalar(select(User).where(User.email == "grace@example.com"))
    grace_member = WorkspaceMember(workspace_id=workspace.id, user_id=grace_user.id, role="agent")
    db.add(grace_member)
    db.commit()

    # Owner removes Grace
    del_res = client.delete(f"/api/v1/workspace/members/{grace_member.id}")
    assert del_res.status_code == 204

    # Grace is no longer in the members list
    members = client.get("/api/v1/workspace/members").json()["data"]
    assert len(members) == 1
    assert all(m["email"] != "grace@example.com" for m in members)


def test_cannot_remove_self(client, member, db):
    workspace = db.scalar(select(Workspace))
    owner_user = db.scalar(select(User).where(User.email == "ada@example.com"))
    owner_member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == owner_user.id))

    res = client.delete(f"/api/v1/workspace/members/{owner_member.id}")
    assert res.status_code == 400
    assert error_code(res) == "CANNOT_REMOVE_SELF"


def test_cannot_remove_last_owner(client, member, db):
    # Grace joins as admin
    grace = second_person("grace@example.com", "Grace Hopper")
    workspace = db.scalar(select(Workspace))
    grace_user = db.scalar(select(User).where(User.email == "grace@example.com"))
    grace_member = WorkspaceMember(workspace_id=workspace.id, user_id=grace_user.id, role="admin")
    db.add(grace_member)
    db.commit()

    grace.post("/api/v1/auth/logout")
    grace.post("/api/v1/auth/login", json={"email": "grace@example.com", "password": PASSWORD})

    owner_user = db.scalar(select(User).where(User.email == "ada@example.com"))
    owner_member = db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == owner_user.id))

    # Grace (admin) tries to remove the only owner Ada
    res = grace.delete(f"/api/v1/workspace/members/{owner_member.id}")
    assert res.status_code == 403  # an admin may not remove an owner at all
    assert error_code(res) == "FORBIDDEN"
