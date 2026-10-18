"""Idempotent seed script — creates demo teams, users, and work items.

Run with: ``python -m app.seed`` (after migrations have been applied).

Demo credentials (email / password):
  * manager@alpha.ops  / password123  (manager of Team Alpha)
  * alice@alpha.ops    / password123  (contributor on Team Alpha)
  * manager@beta.ops   / password123  (manager of Team Beta)
  * bob@beta.ops       / password123  (contributor on Team Beta)

These are documented in README.md. Passwords are weak on purpose for local
demo only; production must use strong passwords and a real secret.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import ActivityEvent, Team, TeamMember, User, WorkItem


def _user(db, email: str, name: str) -> User:
    existing = db.execute(select(User).where(User.email == email)).scalars().first()
    if existing:
        return existing
    u = User(email=email, full_name=name, password_hash=hash_password("password123"))
    db.add(u)
    db.flush()
    return u


def _team(db, name: str, slug: str) -> Team:
    existing = db.execute(select(Team).where(Team.slug == slug)).scalars().first()
    if existing:
        return existing
    t = Team(name=name, slug=slug)
    db.add(t)
    db.flush()
    return t


def _member(db, team: Team, user: User, role: str) -> TeamMember:
    existing = db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team.id, TeamMember.user_id == user.id
        )
    ).scalars().first()
    if existing:
        return existing
    m = TeamMember(team_id=team.id, user_id=user.id, role=role)
    db.add(m)
    db.flush()
    return m


def run() -> None:
    db = SessionLocal()
    try:
        alpha = _team(db, "Team Alpha", "alpha")
        beta = _team(db, "Team Beta", "beta")

        alpha_mgr = _user(db, "manager@alpha.ops", "Alpha Manager")
        alice = _user(db, "alice@alpha.ops", "Alice Contributor")
        beta_mgr = _user(db, "manager@beta.ops", "Beta Manager")
        bob = _user(db, "bob@beta.ops", "Bob Contributor")

        _member(db, alpha, alpha_mgr, "manager")
        _member(db, alpha, alice, "contributor")
        _member(db, beta, beta_mgr, "manager")
        _member(db, beta, bob, "contributor")

        now = datetime.now(timezone.utc)

        items = [
            WorkItem(
                team_id=alpha.id, title="Investigate latency spike in checkout API",
                description="Checkout p95 jumped to 4s at 14:02 UTC. Triage and file an incident.",
                status="open", priority="urgent", assignee_id=None, version=1,
                due_at=now + timedelta(hours=4),
            ),
            WorkItem(
                team_id=alpha.id, title="Rotate database credentials",
                description="Quarterly rotation for the payments RDS instance.",
                status="open", priority="high", assignee_id=None, version=1,
                due_at=now + timedelta(days=1),
            ),
            WorkItem(
                team_id=alpha.id, title="Patch auth service CVE-2024-1234",
                description="Apply vendor patch and verify regression tests pass.",
                status="in_progress", priority="high", assignee_id=alice.id, version=1,
                due_at=now + timedelta(days=2),
            ),
            WorkItem(
                team_id=alpha.id, title="Review SLO dashboard for missing series",
                description="The error-rate panel stopped updating after the last deploy.",
                status="in_review", priority="medium", assignee_id=alice.id, version=1,
                due_at=now + timedelta(days=1),
            ),
            WorkItem(
                team_id=beta.id, title="Onboard new SRE to on-call rotation",
                description="Add Priya to the secondary rotation starting Monday.",
                status="open", priority="medium", assignee_id=None, version=1,
                due_at=now + timedelta(days=3),
            ),
            WorkItem(
                team_id=beta.id, title="Clean up orphaned S3 buckets",
                description="Three buckets from the 2023 migration are still accruing costs.",
                status="in_progress", priority="low", assignee_id=bob.id, version=1,
                due_at=now + timedelta(days=5),
            ),
        ]
        for wi in items:
            existing = db.execute(select(WorkItem).where(WorkItem.title == wi.title)).scalars().first()
            if existing:
                continue
            db.add(wi)
            db.flush()
            db.add(
                ActivityEvent(
                    work_item_id=wi.id,
                    actor_id=alpha_mgr.id if wi.team_id == alpha.id else beta_mgr.id,
                    action="created",
                    detail="seeded",
                    version_after=1,
                )
            )
        db.commit()
        print("Seed complete. Demo logins (password: password123):")
        print("  manager@alpha.ops  (manager, Team Alpha)")
        print("  alice@alpha.ops    (contributor, Team Alpha)")
        print("  manager@beta.ops   (manager, Team Beta)")
        print("  bob@beta.ops       (contributor, Team Beta)")
    finally:
        db.close()


if __name__ == "__main__":
    run()
