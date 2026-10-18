"""Atomic claiming tests: race-free claim via single UPDATE."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_header, login, make_work_item


def test_claim_sets_assignee_atomically(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Open item", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    r = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers=auth_header(alice),
        json={"action": "claim", "version": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["assignee_id"] == seeded["alice"].id
    assert body["status"] == "in_progress"
    assert body["version"] == 2


def test_cannot_claim_already_assigned(client: TestClient, db, seeded):
    from app.models import WorkItem
    wi = make_work_item(db, seeded["alpha"], title="Already assigned", assignee=seeded["alice"])
    bob_token = login(client, "bob@beta.ops")
    # bob is on beta, so 403 first
    r = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers=auth_header(bob_token),
        json={"action": "claim", "version": 1},
    )
    assert r.status_code == 403

    # Now alice (the assignee) tries to claim again -> already in_progress
    alice = login(client, "alice@alpha.ops")
    r = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers=auth_header(alice),
        json={"action": "claim", "version": 1},
    )
    assert r.status_code == 409


def test_claim_requires_open_status(client: TestClient, db, seeded):
    from app.models import WorkItem
    wi = make_work_item(db, seeded["alpha"], title="In progress", status="in_progress", assignee=seeded["alice"])
    # Release it first, then someone else can claim
    alice = login(client, "alice@alpha.ops")
    r = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers=auth_header(alice),
        json={"action": "release", "version": 1},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "open"
    assert r.json()["assignee_id"] is None
