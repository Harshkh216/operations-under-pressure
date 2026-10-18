"""Optimistic concurrency tests: version mismatch yields 409."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_header, login, make_work_item


def test_update_with_stale_version_returns_409(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Original")
    mgr = login(client, "manager@alpha.ops")
    # First update succeeds (version 1 -> 2)
    r = client.put(
        f"/api/work-items/{wi.id}",
        headers=auth_header(mgr),
        json={"title": "Updated", "version": 1},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 2
    # Second update with stale version 1 -> 409
    r = client.put(
        f"/api/work-items/{wi.id}",
        headers=auth_header(mgr),
        json={"title": "Stale update", "version": 1},
    )
    assert r.status_code == 409


def test_update_with_current_version_succeeds(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Original")
    mgr = login(client, "manager@alpha.ops")
    r = client.put(
        f"/api/work-items/{wi.id}",
        headers=auth_header(mgr),
        json={"title": "V2", "version": 1},
    )
    assert r.status_code == 200
    r = client.put(
        f"/api/work-items/{wi.id}",
        headers=auth_header(mgr),
        json={"title": "V3", "version": 2},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 3
    assert r.json()["title"] == "V3"


def test_transition_with_stale_version_returns_409(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="For claim", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    # Claim: version 1 -> 2
    r = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers=auth_header(alice),
        json={"action": "claim", "version": 1},
    )
    assert r.status_code == 200
    # Try start_review with stale version 1 -> 409
    r = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers=auth_header(alice),
        json={"action": "start_review", "version": 1},
    )
    assert r.status_code == 409
