"""Idempotency tests: repeating a request with the same key returns the
original result without duplicating side effects."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import auth_header, login, make_work_item


def test_idempotent_create(client: TestClient, db, seeded):
    mgr = login(client, "manager@alpha.ops")
    key = f"create-{uuid.uuid4()}"
    body = {"team_id": seeded["alpha"].id, "title": "Idem item", "description": "d", "priority": "low"}
    r1 = client.post("/api/work-items", headers={**auth_header(mgr), "Idempotency-Key": key}, json=body)
    r2 = client.post("/api/work-items", headers={**auth_header(mgr), "Idempotency-Key": key}, json=body)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


def test_idempotent_transition(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Claimable", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    key = f"claim-{uuid.uuid4()}"
    r1 = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers={**auth_header(alice), "Idempotency-Key": key},
        json={"action": "claim", "version": 1},
    )
    r2 = client.post(
        f"/api/work-items/{wi.id}/transition",
        headers={**auth_header(alice), "Idempotency-Key": key},
        json={"action": "claim", "version": 1},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["version"] == r2.json()["version"]


def test_idempotent_comment(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Commentable")
    alice = login(client, "alice@alpha.ops")
    key = f"comment-{uuid.uuid4()}"
    r1 = client.post(
        f"/api/work-items/{wi.id}/comments",
        headers={**auth_header(alice), "Idempotency-Key": key},
        json={"body": "first comment"},
    )
    r2 = client.post(
        f"/api/work-items/{wi.id}/comments",
        headers={**auth_header(alice), "Idempotency-Key": key},
        json={"body": "first comment"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    # Only one comment should exist.
    r = client.get(f"/api/work-items/{wi.id}/comments", headers=auth_header(alice))
    assert len(r.json()) == 1
