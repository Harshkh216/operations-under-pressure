"""Pagination and filtering tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_header, login, make_work_item


def test_pagination_returns_correct_page(client: TestClient, db, seeded):
    for i in range(5):
        make_work_item(db, seeded["alpha"], title=f"Item {i}")
    mgr = login(client, "manager@alpha.ops")
    r = client.get("/api/work-items?page=1&page_size=2", headers=auth_header(mgr))
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2
    assert r.json()["total"] == 5
    assert r.json()["page"] == 1

    r = client.get("/api/work-items?page=3&page_size=2", headers=auth_header(mgr))
    assert len(r.json()["items"]) == 1
    assert r.json()["page"] == 3


def test_filter_by_status(client: TestClient, db, seeded):
    make_work_item(db, seeded["alpha"], title="Open1", status="open")
    make_work_item(db, seeded["alpha"], title="Progress", status="in_progress", assignee=seeded["alice"])
    mgr = login(client, "manager@alpha.ops")
    r = client.get("/api/work-items?status=open", headers=auth_header(mgr))
    titles = {i["title"] for i in r.json()["items"]}
    assert "Open1" in titles
    assert "Progress" not in titles


def test_search_by_title(client: TestClient, db, seeded):
    make_work_item(db, seeded["alpha"], title="Database outage")
    make_work_item(db, seeded["alpha"], title="Network glitch")
    mgr = login(client, "manager@alpha.ops")
    r = client.get("/api/work-items?search=database", headers=auth_header(mgr))
    titles = {i["title"] for i in r.json()["items"]}
    assert "Database outage" in titles
    assert "Network glitch" not in titles


def test_view_assigned_to_me(client: TestClient, db, seeded):
    make_work_item(db, seeded["alpha"], title="Mine", status="in_progress", assignee=seeded["alice"])
    make_work_item(db, seeded["alpha"], title="Not mine", status="open")
    alice = login(client, "alice@alpha.ops")
    r = client.get("/api/work-items?view=assigned_to_me", headers=auth_header(alice))
    titles = {i["title"] for i in r.json()["items"]}
    assert "Mine" in titles
    assert "Not mine" not in titles


def test_view_unassigned_urgent(client: TestClient, db, seeded):
    make_work_item(db, seeded["alpha"], title="Urgent open", status="open", priority="urgent")
    make_work_item(db, seeded["alpha"], title="Low open", status="open", priority="low")
    make_work_item(db, seeded["alpha"], title="Assigned", status="in_progress", priority="urgent", assignee=seeded["alice"])
    mgr = login(client, "manager@alpha.ops")
    r = client.get("/api/work-items?view=unassigned_urgent", headers=auth_header(mgr))
    titles = {i["title"] for i in r.json()["items"]}
    assert "Urgent open" in titles
    assert "Low open" not in titles
    assert "Assigned" not in titles


def test_view_awaiting_my_approval(client: TestClient, db, seeded):
    make_work_item(db, seeded["alpha"], title="In review", status="in_review", assignee=seeded["alice"])
    make_work_item(db, seeded["alpha"], title="Not in review", status="open")
    mgr = login(client, "manager@alpha.ops")
    r = client.get("/api/work-items?view=awaiting_my_approval", headers=auth_header(mgr))
    titles = {i["title"] for i in r.json()["items"]}
    assert "In review" in titles
    assert "Not in review" not in titles


def test_dashboard_summary(client: TestClient, db, seeded):
    make_work_item(db, seeded["alpha"], title="Urgent", status="open", priority="urgent")
    make_work_item(db, seeded["alpha"], title="Mine", status="in_progress", assignee=seeded["alice"])
    make_work_item(db, seeded["alpha"], title="Review", status="in_review", assignee=seeded["alice"])
    mgr = login(client, "manager@alpha.ops")
    r = client.get("/api/dashboard/summary", headers=auth_header(mgr))
    s = r.json()
    assert s["unassigned_urgent"] >= 1
    assert s["awaiting_my_approval"] >= 1
