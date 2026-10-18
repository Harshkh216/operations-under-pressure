"""Activity history tests: every mutation writes an activity event in the
same transaction."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_header, login, make_work_item


def test_activity_recorded_on_claim(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Tracked", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "claim", "version": 1})

    r = client.get(f"/api/work-items/{wi.id}/activity", headers=auth_header(alice))
    assert r.status_code == 200
    actions = [a["action"] for a in r.json()]
    assert "claim" in actions
    assert len(r.json()) == 1


def test_activity_recorded_on_update(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Updatable")
    mgr = login(client, "manager@alpha.ops")
    client.put(f"/api/work-items/{wi.id}", headers=auth_header(mgr), json={"title": "Updated", "version": 1})
    r = client.get(f"/api/work-items/{wi.id}/activity", headers=auth_header(mgr))
    actions = [a["action"] for a in r.json()]
    assert "updated" in actions


def test_activity_timeline_ordered_descending(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Ordered", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    mgr = login(client, "manager@alpha.ops")
    client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "claim", "version": 1})
    v = client.get(f"/api/work-items/{wi.id}", headers=auth_header(alice)).json()["version"]
    client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "start_review", "version": v})

    r = client.get(f"/api/work-items/{wi.id}/activity", headers=auth_header(mgr))
    actions = [a["action"] for a in r.json()]
    # Most recent first
    assert actions[0] == "start_review"
    assert actions[1] == "claim"


def test_activity_includes_actor_name(client: TestClient, db, seeded):
    wi = make_work_item(db, seeded["alpha"], title="Named", priority="urgent")
    alice = login(client, "alice@alpha.ops")
    client.post(f"/api/work-items/{wi.id}/transition", headers=auth_header(alice), json={"action": "claim", "version": 1})
    r = client.get(f"/api/work-items/{wi.id}/activity", headers=auth_header(alice))
    claim_event = [a for a in r.json() if a["action"] == "claim"][0]
    assert claim_event["actor_name"] == "Alice"
