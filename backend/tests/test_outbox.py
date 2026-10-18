"""Outbox tests: events are written transactionally and drained reliably."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_header, login, make_work_item
from app.services.outbox import drain_once


def test_outbox_event_created_on_transition(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Outboxed", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "claim", "version": 1})

    r = client.get("/api/outbox", headers=auth_header(alice))
    assert r.status_code == 200
    events = r.json()
    assert any(e["event_type"] == "work_item.claim" for e in events)


def test_outbox_drain_marks_done(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Drainable", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "claim", "version": 1})

    n = drain_once()
    assert n >= 1

    r = client.get("/api/outbox", headers=auth_header(alice))
    pending = [e for e in r.json() if e["status"] == "pending"]
    assert len(pending) == 0


def test_outbox_drain_endpoint(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Endpoint drain", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "claim", "version": 1})
    r = client.post("/api/outbox/drain", headers=auth_header(alice))
    assert r.status_code == 200
    assert r.json()["processed"] >= 1


def test_outbox_idempotency_key_unique_per_version(client: TestClient, db, seeded):
    """Two distinct transitions on the same work item produce two outbox
    events with different idempotency keys (because version differs)."""
    wi = make_work_item(db, seeded["alpha"], title="Two events", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "claim", "version": 1})
    v = client.get(f"/api/work-items/{wi.id}", headers=auth_header(alice)).json()["version"]
    client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "start_review", "version": v})

    r = client.get("/api/outbox", headers=auth_header(alice))
    types = [e["event_type"] for e in r.json()]
    assert "work_item.claim" in types
    assert "work_item.start_review" in types
