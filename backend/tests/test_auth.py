"""Authentication tests: login, token validation, /me."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_header, login, make_member, make_team, make_user


def test_login_success(client: TestClient, db, seeded):
    token = login(client, "manager@alpha.ops")
    assert token is not None and len(token) > 10


def test_login_wrong_password(client: TestClient, db, seeded):
    r = client.post("/api/login", json={"email": "manager@alpha.ops", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client: TestClient, db, seeded):
    r = client.post("/api/login", json={"email": "nobody@nowhere.ops", "password": "x"})
    assert r.status_code == 401


def test_me_returns_memberships(client: TestClient, db, seeded):
    token = login(client, "manager@alpha.ops")
    r = client.get("/api/me", headers=auth_header(token))
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "manager@alpha.ops"
    assert len(data["memberships"]) == 1
    assert data["memberships"][0]["role"] == "manager"
    assert data["memberships"][0]["team_slug"] == "alpha"


def test_me_without_token(client: TestClient, db, seeded):
    r = client.get("/api/me")
    assert r.status_code == 401


def test_invalid_token(client: TestClient, db, seeded):
    r = client.get("/api/me", headers=auth_header("garbage"))
    assert r.status_code == 401
