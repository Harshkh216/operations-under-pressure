"""Workflow transition tests: full state machine path."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_header, login, make_work_item


def test_full_lifecycle(client: TestClient, db, seeded):
    """open -> claim -> in_progress -> start_review -> in_review -> approve -> approved -> complete -> done"""
    wi = make_work_item(db, seeded["alpha"], title="Lifecycle", priority="high")
    alice = login(client, "alice@alpha.ops")
    mgr = login(client, "manager@alpha.ops")

    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "claim", "version": 1})
    assert r.json()["status"] == "in_progress"
    v = r.json()["version"]

    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "start_review", "version": v})
    assert r.json()["status"] == "in_review"
    v = r.json()["version"]

    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(mgr), json={"action": "approve", "version": v})
    assert r.json()["status"] == "approved"
    v = r.json()["version"]

    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(mgr), json={"action": "complete", "version": v})
    assert r.json()["status"] == "done"


def test_reject_returns_to_in_progress(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Rejectable", status="in_review", assignee=seeded["alice"])
    mgr = login(client, "manager@alpha.ops")
    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(mgr), json={"action": "reject", "version": 1})
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


def test_block_unblock(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Blockable", status="in_progress", assignee=seeded["alice"])
    alice = login(client, "alice@alpha.ops")
    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "block", "version": 1})
    assert r.json()["status"] == "blocked"
    v = r.json()["version"]
    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "unblock", "version": v})
    assert r.json()["status"] == "in_progress"


def test_invalid_transition_returns_409(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Open item")
    alice = login(client, "alice@alpha.ops")
    # Cannot start_review from open (must claim first)
    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "start_review", "version": 1})
    assert r.status_code == 409


def test_cancel_by_manager(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Cancellable")
    mgr = login(client, "manager@alpha.ops")
    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(mgr), json={"action": "cancel", "version": 1})
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_contributor_cannot_cancel(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Cancellable")
    alice = login(client, "alice@alpha.ops")
    r = client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "cancel", "version": 1})
    assert r.status_code == 403
