"""Authorization tests: role-based access, team isolation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_header, login, make_work_item


def test_contributor_cannot_create(client: TestClient, db, seeded):
    token = login(client, "alice@alpha.ops")
    r = client.post(
        "/api/work-items",
        headers=auth_header(token),
        json={"team_id": seeded["alpha"].id, "title": "x", "description": "d", "priority": "low"},
    )
    assert r.status_code == 403


def test_manager_can_create(client: TestClient, db, seeded):
    token = login(client, "manager@alpha.ops")
    r = client.post(
        "/api/work-items",
        headers=auth_header(token),
        json={"team_id": seeded["alpha"].id, "title": "x", "description": "d", "priority": "low"},
    )
    assert r.status_code == 201


def test_team_isolation_list(client: TestClient, db, seeded):
    """A user only sees work items from teams they belong to."""
    make_work_item(db, seeded["alpha"], title="Alpha item")
    make_work_item(db, seeded["beta"], title="Beta item")

    alice = login(client, "alice@alpha.ops")
    r = client.get("/api/work-items", headers=auth_header(alice))
    assert r.status_code == 200
    titles = {i["title"] for i in r.json()["items"]}
    assert "Alpha item" in titles
    assert "Beta item" not in titles

    bob = login(client, "bob@beta.ops")
    r = client.get("/api/work-items", headers=auth_header(bob))
    titles = {i["title"] for i in r.json()["items"]}
    assert "Beta item" in titles
    assert "Alpha item" not in titles


def test_cross_team_access_denied(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["beta"], title="Beta secret")
    alice = login(client, "alice@alpha.ops")
    r = client.get(f"/api/work-items/{wi.id}", headers=auth_header(alice))
    assert r.status_code == 403


def test_contributor_can_claim(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Claimable", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    r = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers=auth_header(alice),
        json={"action": "claim", "version": 1},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"
    assert r.json()["assignee_id"] == seeded["alice"].id


def test_contributor_cannot_approve(client: TestClient, db, seeded):
    from app.models import WorkItem
    wi = make_work_item(db, seeded["alpha"], title="For approval", status="in_review", assignee=seeded["alice"])
    alice = login(client, "alice@alpha.ops")
    r = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers=auth_header(alice),
        json={"action": "approve", "version": 1},
    )
    assert r.status_code == 403


def test_manager_can_approve(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="For approval", status="in_review", assignee=seeded["alice"])
    mgr = login(client, "manager@alpha.ops")
    r = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers=auth_header(mgr),
        json={"action": "approve", "version": 1},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
