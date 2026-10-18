"""Shared test fixtures.

Each test runs against a fresh in-memory SQLite database with the schema
created via SQLAlchemy metadata (no Alembic needed for tests). The FastAPI
dependency ``get_db`` is overridden to yield sessions from the test engine.
"""

from __future__ import annotations

from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db, set_test_engine
from app.models import Base
from app.main import app


@pytest.fixture()
def db_engine():
    """A fresh in-memory SQLite engine per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    set_test_engine(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db(db_engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False, class_=Session)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_engine) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with get_db pointed at the test engine."""
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False, class_=Session)

    def _override_get_db() -> Generator[Session, None, None]:
        session = SessionLocal()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --- Seed helpers -----------------------------------------------------------

from app.core.security import hash_password
from app.models import Team, TeamMember, User, WorkItem
from datetime import datetime, timedelta, timezone


def make_team(db: Session, name: str = "Team Alpha", slug: str = "alpha") -> Team:
    t = Team(name=name, slug=slug)
    db.add(t)
    db.flush()
    return t


def make_user(db: Session, email: str, name: str, password: str = "password123") -> User:
    u = User(email=email, full_name=name, password_hash=hash_password(password))
    db.add(u)
    db.flush()
    return u


def make_member(db: Session, team: Team, user: User, role: str = "contributor") -> TeamMember:
    m = TeamMember(team_id=team.id, user_id=user.id, role=role)
    db.add(m)
    db.flush()
    return m


def make_work_item(
    db: Session,
    team: Team,
    title: str = "Test item",
    priority: str = "medium",
    status: str = "open",
    assignee: User | None = None,
) -> WorkItem:
    wi = WorkItem(
        team_id=team.id,
        title=title,
        description="desc",
        status=status,
        priority=priority,
        assignee_id=assignee.id if assignee else None,
        version=1,
        due_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(wi)
    db.commit()
    return wi


def login(client: TestClient, email: str, password: str = "password123") -> str:
    r = client.post("/api/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def seeded(db: Session):
    """A fully seeded scenario: two teams, a manager + contributor each."""
    alpha = make_team(db, "Team Alpha", "alpha")
    beta = make_team(db, "Team Beta", "beta")
    alpha_mgr = make_user(db, "manager@alpha.ops", "Alpha Manager")
    alice = make_user(db, "alice@alpha.ops", "Alice")
    beta_mgr = make_user(db, "manager@beta.ops", "Beta Manager")
    bob = make_user(db, "bob@beta.ops", "Bob")
    make_member(db, alpha, alpha_mgr, "manager")
    make_member(db, alpha, alice, "contributor")
    make_member(db, beta, beta_mgr, "manager")
    make_member(db, beta, bob, "contributor")
    db.commit()
    return {
        "alpha": alpha, "beta": beta,
        "alpha_mgr": alpha_mgr, "alice": alice,
        "beta_mgr": beta_mgr, "bob": bob,
    }
