"""SQLAlchemy ORM models for Operations Under Pressure.

The schema models an operations team managing a queue of work items under
tight deadlines. Core guarantees the schema must support:

* Team isolation — a user only ever sees work items for teams they belong to.
* Role-based access — managers can approve/deny and reassign; contributors
  can claim and progress work.
* Optimistic concurrency — every mutable row carries a ``version`` integer
  bumped on every update; clients must send the version they read, and a
  mismatch yields HTTP 409.
* Transactional activity history — every state-changing operation writes an
  ``activity_events`` row in the SAME database transaction as the change,
  so history is never lost or orphaned.
* Transactional outbox — ``outbox_events`` rows are written in the same
  transaction as the business change, then drained by a background worker
  for at-least-once delivery to downstream systems.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all models."""


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())

    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )
    work_items: Mapped[list["WorkItem"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Team {self.slug}>"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Stored as a bcrypt hash, never the plain password.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Global role is informational; real authorization is per-team via TeamMember.role.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())

    memberships: Mapped[list["TeamMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    comments: Mapped[list["Comment"]] = relationship(back_populates="author")
    activity_events: Mapped[list["ActivityEvent"]] = relationship(back_populates="actor")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email}>"


class TeamMember(Base):
    """Membership join table with a per-team role.

    Roles:
      * ``manager``  — can approve/deny work, reassign, create work items.
      * ``contributor`` — can claim unassigned work, progress their own work, comment.
    """

    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # manager | contributor

    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TeamMember {self.role} team={self.team_id} user={self.user_id}>"


class WorkItem(Base):
    """A unit of operational work flowing through a simple state machine.

    States (``status``):
        open       — newly created, not yet claimed
        in_progress — claimed by a contributor
        blocked    — contributor cannot proceed (needs info / dependency)
        in_review  — submitted for manager approval
        approved   — manager approved the work
        rejected   — manager rejected; returns to in_progress for rework
        done       — completed (terminal)
        cancelled  — abandoned (terminal)

    Transitions are enforced in ``app.services.workflow``.
    """

    __tablename__ = "work_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default="open")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium", server_default="medium")
    # low | medium | high | urgent
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Optimistic concurrency control. Bumped on every UPDATE.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), onupdate=_utcnow
    )

    team: Mapped[Team] = relationship(back_populates="work_items")
    assignee: Mapped[User | None] = relationship()
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="work_item", cascade="all, delete-orphan", order_by="Comment.created_at"
    )
    activity_events: Mapped[list["ActivityEvent"]] = relationship(
        back_populates="work_item", cascade="all, delete-orphan", order_by="ActivityEvent.created_at.desc()"
    )

    __table_args__ = (
        Index("ix_work_items_team_status", "team_id", "status"),
        Index("ix_work_items_assignee_status", "assignee_id", "status"),
        Index("ix_work_items_priority_status", "priority", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<WorkItem {self.id} {self.status}>"


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())

    work_item: Mapped[WorkItem] = relationship(back_populates="comments")
    author: Mapped[User] = relationship(back_populates="comments")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Comment {self.id} on wi={self.work_item_id}>"


class ActivityEvent(Base):
    """Immutable audit trail of every state-changing action on a work item.

    Written in the SAME transaction as the work-item mutation, so the history
    is always consistent with the current row state.
    """

    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    # Human-readable detail, e.g. "claimed by alice@example.com" or "status: open -> in_progress".
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Snapshot of the work-item version AFTER the action, for timeline ordering.
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())

    work_item: Mapped[WorkItem] = relationship(back_populates="activity_events")
    actor: Mapped[User] = relationship(back_populates="activity_events")

    __table_args__ = (Index("ix_activity_workitem_created", "work_item_id", "created_at"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ActivityEvent {self.action} wi={self.work_item_id}>"


class OutboxEvent(Base):
    """Transactional outbox for reliable downstream delivery.

    A row is inserted in the same transaction as the business change. A
    background worker polls ``status='pending'`` rows and attempts delivery.
    On success the row is marked ``done``; on repeated failure it is marked
    ``failed`` after ``max_attempts`` tries. Each attempt records the attempt
    count and last error. A unique ``idempotency_key`` lets downstream
    consumers deduplicate redeliveries.
    """

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Logical event type, e.g. "work_item.claimed", "work_item.approved".
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # JSON-encoded payload.
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    # Stable key so consumers can dedupe redeliveries (at-least-once).
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    # pending | done | failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_outbox_status_created", "status", "created_at"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OutboxEvent {self.id} {self.event_type} {self.status}>"


class IdempotencyRecord(Base):
    """Stores the response of a prior request keyed by an idempotency key.

    A repeat request with the same key replays the stored response instead of
    re-executing the operation. Rows are write-once per key.
    """

    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IdempotencyRecord {self.key}>"


__all__ = [
    "Base",
    "Team",
    "User",
    "TeamMember",
    "WorkItem",
    "Comment",
    "ActivityEvent",
    "OutboxEvent",
    "IdempotencyRecord",
]
