"""Workflow state machine for work items.

Single source of truth for which transitions are legal, who may perform them,
and what the resulting status is. The service layer calls ``apply_transition``
which mutates the work item, writes an activity event, and emits an outbox
event — all within the caller's transaction.

Design notes:

* The state machine is encoded as a dict keyed by current status -> allowed
  action -> next status. This keeps the rules declarative and easy to audit.
* Authorization is role + ownership aware: ``can_perform`` checks the actor's
  per-team role and (for some actions) whether they are the assignee.
* All side effects (activity log row, outbox row) are written in the SAME
  transaction as the work-item update, so history and downstream events can
  never diverge from the persisted state.
"""

from __future__ import annotations

import json
from typing import Mapping

from sqlalchemy.orm import Session

from app.models import ActivityEvent, OutboxEvent, TeamMember, User, WorkItem
from app.schemas import Role

# --- State machine ----------------------------------------------------------
# status -> action -> next_status
TRANSITIONS: Mapping[str, Mapping[str, str]] = {
    "open": {
        "claim": "in_progress",
        "cancel": "cancelled",
    },
    "in_progress": {
        "start_review": "in_review",
        "block": "blocked",
        "release": "open",
        "cancel": "cancelled",
    },
    "blocked": {
        "unblock": "in_progress",
        "cancel": "cancelled",
    },
    "in_review": {
        "approve": "approved",
        "reject": "in_progress",
        "cancel": "cancelled",
    },
    "approved": {
        "complete": "done",
    },
    "rejected": {
        # Rejected is a transient label; "reject" moves in_review -> in_progress
        # directly, so there is no standing-in-rejected state to leave.
    },
}

TERMINAL_STATUSES = {"done", "cancelled"}

# Action -> required role and whether the actor must be the current assignee.
ACTION_PERMISSIONS: Mapping[str, Mapping[str, object]] = {
    "claim": {"role": "contributor", "require_assignee": False},
    "release": {"role": "contributor", "require_assignee": True},
    "block": {"role": "contributor", "require_assignee": True},
    "unblock": {"role": "contributor", "require_assignee": True},
    "start_review": {"role": "contributor", "require_assignee": True},
    "approve": {"role": "manager", "require_assignee": False},
    "reject": {"role": "manager", "require_assignee": False},
    "complete": {"role": "manager", "require_assignee": False},
    "cancel": {"role": "manager", "require_assignee": False},
}


class WorkflowError(Exception):
    """Raised when a transition is invalid."""


class TransitionNotAllowed(WorkflowError):
    pass


class NotAuthorized(WorkflowError):
    pass


def next_status(current: str, action: str) -> str:
    allowed = TRANSITIONS.get(current, {})
    if action not in allowed:
        raise TransitionNotAllowed(
            f"Action '{action}' is not valid from status '{current}'"
        )
    return allowed[action]


def can_perform(action: str, role: Role | str, is_assignee: bool) -> bool:
    perm = ACTION_PERMISSIONS.get(action)
    if perm is None:
        return False
    if role != perm["role"]:
        return False
    if perm["require_assignee"] and not is_assignee:
        return False
    return True


def apply_transition(
    *,
    db: Session,
    work_item: WorkItem,
    action: str,
    actor: User,
    membership: TeamMember,
) -> str:
    """Mutate ``work_item`` in place and write activity + outbox rows.

    The caller is responsible for committing the session (so this stays
    composable with the optimistic-concurrency and idempotency checks done
    before this call). Returns the new status.
    """
    new_status = next_status(work_item.status, action)

    is_assignee = work_item.assignee_id == actor.id
    if not can_perform(action, membership.role, is_assignee):
        raise NotAuthorized(
            f"Your role ({membership.role}) cannot perform '{action}'"
            + (
                " on work assigned to someone else"
                if ACTION_PERMISSIONS[action]["require_assignee"]
                else ""
            )
        )

    prev_status = work_item.status
    if action == "claim":
        if work_item.assignee_id is not None:
            raise TransitionNotAllowed("Work item is already assigned")
        work_item.assignee_id = actor.id
    if action == "release":
        work_item.assignee_id = None

    work_item.status = new_status
    work_item.version += 1  # bumped on every mutation

    activity = ActivityEvent(
        work_item_id=work_item.id,
        actor_id=actor.id,
        action=action,
        detail=_describe(action, actor=actor, prev=prev_status, new=new_status),
        version_after=work_item.version,
    )
    db.add(activity)

    outbox = OutboxEvent(
        event_type=f"work_item.{action}",
        payload=json.dumps(
            {
                "work_item_id": work_item.id,
                "team_id": work_item.team_id,
                "action": action,
                "previous_status": prev_status,
                "new_status": new_status,
                "version": work_item.version,
                "assignee_id": work_item.assignee_id,
                "actor_id": actor.id,
            }
        ),
        # version is unique per mutation, so this key never collides across
        # distinct state changes and lets consumers dedupe redeliveries.
        idempotency_key=f"wi:{work_item.id}:v{work_item.version}:{action}",
    )
    db.add(outbox)

    return new_status


def _describe(action: str, *, actor: User, prev: str, new: str) -> str:
    if action in ("claim", "release", "block", "unblock", "start_review", "complete", "cancel"):
        return f"{action} by {actor.email}"
    if action in ("approve", "reject"):
        return f"{action} by {actor.email}: status {prev} -> {new}"
    return f"{action}: {prev} -> {new}"


__all__ = [
    "TRANSITIONS",
    "TERMINAL_STATUSES",
    "ACTION_PERMISSIONS",
    "WorkflowError",
    "TransitionNotAllowed",
    "NotAuthorized",
    "next_status",
    "can_perform",
    "apply_transition",
]
