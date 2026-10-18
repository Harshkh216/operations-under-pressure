"""Work-item endpoints: list/create/get/update/transition/comment/activity.

Highlights:
* Server-side pagination + filtering + full-text search on title/description.
* Optimistic concurrency: PUT requires ``version``; mismatch yields 409.
* Idempotency: POST and PUT accept an ``Idempotency-Key`` header; a repeat
  with the same key returns the original result instead of duplicating.
* Atomic claiming: the ``claim`` transition is the only way to set an
  assignee on an unassigned item, and it sets the assignee to the actor
  within the same UPDATE — no read-modify-write race.
* Transactional activity history: every mutation writes an activity row in
  the same transaction.
* 401/403/409 are returned with human-readable detail.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_membership
from app.db.session import get_db
from app.models import ActivityEvent, Comment, IdempotencyRecord, TeamMember, User, WorkItem
from app.schemas import (
    ActivityEventPublic,
    CommentCreate,
    CommentPublic,
    TransitionRequest,
    WorkItemCreate,
    WorkItemDetail,
    WorkItemListResponse,
    WorkItemPublic,
    WorkItemUpdate,
)
from app.services.workflow import NotAuthorized, TransitionNotAllowed, apply_transition

router = APIRouter(prefix="/api", tags=["work-items"])

# --- Helpers ----------------------------------------------------------------


def _enrich(wi: WorkItem, db: Session) -> WorkItemPublic:
    assignee_name = None
    if wi.assignee_id is not None:
        u = db.get(User, wi.assignee_id)
        if u is not None:
            assignee_name = u.full_name
    return WorkItemPublic.model_validate(wi).model_copy(update={"assignee_name": assignee_name})


def _enrich_detail(wi: WorkItem, db: Session) -> WorkItemDetail:
    pub = _enrich(wi, db)
    team_name = wi.team.name if wi.team else None
    return WorkItemDetail(**pub.model_dump(), team_name=team_name)


def _resolve_team_membership(
    team_id: int, current_user: User, db: Session
) -> TeamMember:
    """Resolve membership for a team_id coming from the request body/path."""
    m = db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == current_user.id,
        )
    ).scalars().first()
    if m is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of this team")
    return m


# --- Idempotency ------------------------------------------------------------

def _idem_key(action: str, user_id: int, body: str) -> str:
    return f"{action}:{user_id}:{hashlib.sha256(body.encode()).hexdigest()[:16]}"


def _check_idempotency(db: Session, key: str) -> dict | None:
    """Look up a prior result for this idempotency key.

    Returns the stored response body, or None if this is a fresh request.
    """
    row = db.execute(
        select(IdempotencyRecord).where(IdempotencyRecord.key == key)
    ).scalars().first()
    if row is None:
        return None
    return json.loads(row.response_body)


def _store_idempotency(db: Session, key: str, status_code: int, body: dict) -> None:
    rec = IdempotencyRecord(key=key, status_code=status_code, response_body=json.dumps(body))
    db.add(rec)


# --- List -------------------------------------------------------------------

@router.get("/work-items", response_model=WorkItemListResponse)
def list_work_items(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    status_filter: list[str] | None = Query(None, alias="status"),
    priority: list[str] | None = Query(None),
    assignee_id: int | None = Query(None),
    view: str | None = Query(None, description="assigned_to_me | unassigned_urgent | awaiting_my_approval"),
    search: str | None = Query(None),
    team_id: int | None = Query(None),
) -> WorkItemListResponse:
    # Restrict to teams the user belongs to.
    team_ids = [m.team_id for m in current_user.memberships]
    if not team_ids:
        return WorkItemListResponse(items=[], total=0, page=page, page_size=page_size)
    if team_id is not None:
        if team_id not in team_ids:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of that team")
        team_ids = [team_id]

    stmt = select(WorkItem).where(WorkItem.team_id.in_(team_ids))

    if status_filter:
        stmt = stmt.where(WorkItem.status.in_(status_filter))
    if priority:
        stmt = stmt.where(WorkItem.priority.in_(priority))
    if assignee_id is not None:
        stmt = stmt.where(WorkItem.assignee_id == assignee_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(WorkItem.title.ilike(like), WorkItem.description.ilike(like)))

    if view == "assigned_to_me":
        stmt = stmt.where(
            WorkItem.assignee_id == current_user.id,
            WorkItem.status.in_(["in_progress", "blocked", "in_review"]),
        )
    elif view == "unassigned_urgent":
        stmt = stmt.where(
            WorkItem.assignee_id.is_(None),
            WorkItem.priority.in_(["urgent", "high"]),
            WorkItem.status.in_(["open"]),
        )
    elif view == "awaiting_my_approval":
        # Items in review on teams where the user is a manager.
        manager_team_ids = [
            m.team_id for m in current_user.memberships if m.role == "manager"
        ]
        if not manager_team_ids:
            return WorkItemListResponse(items=[], total=0, page=page, page_size=page_size)
        stmt = stmt.where(
            WorkItem.team_id.in_(manager_team_ids),
            WorkItem.status == "in_review",
        )

    # Total count.
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0

    # Ordering: urgent first, then by due date, then newest.
    priority_order = case(
        (WorkItem.priority == "urgent", 0),
        (WorkItem.priority == "high", 1),
        (WorkItem.priority == "medium", 2),
        (WorkItem.priority == "low", 3),
        else_=4,
    )
    stmt = stmt.order_by(priority_order, WorkItem.due_at.asc().nulls_last(), WorkItem.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).scalars().all()
    items = [_enrich(wi, db) for wi in rows]
    return WorkItemListResponse(items=items, total=total, page=page, page_size=page_size)


# --- Summary (dashboard cards) ---------------------------------------------

@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    team_ids = [m.team_id for m in current_user.memberships]
    manager_team_ids = [m.team_id for m in current_user.memberships if m.role == "manager"]
    if not team_ids:
        return {"assigned_to_me": 0, "unassigned_urgent": 0, "awaiting_my_approval": 0, "total_visible": 0}

    assigned = db.execute(
        select(func.count())
        .select_from(WorkItem)
        .where(
            WorkItem.team_id.in_(team_ids),
            WorkItem.assignee_id == current_user.id,
            WorkItem.status.in_(["in_progress", "blocked", "in_review"]),
        )
    ).scalar() or 0

    urgent = db.execute(
        select(func.count())
        .select_from(WorkItem)
        .where(
            WorkItem.team_id.in_(team_ids),
            WorkItem.assignee_id.is_(None),
            WorkItem.priority.in_(["urgent", "high"]),
            WorkItem.status == "open",
        )
    ).scalar() or 0

    approval = 0
    if manager_team_ids:
        approval = db.execute(
            select(func.count())
            .select_from(WorkItem)
            .where(
                WorkItem.team_id.in_(manager_team_ids),
                WorkItem.status == "in_review",
            )
        ).scalar() or 0

    total = db.execute(
        select(func.count())
        .select_from(WorkItem)
        .where(WorkItem.team_id.in_(team_ids))
    ).scalar() or 0

    return {
        "assigned_to_me": assigned,
        "unassigned_urgent": urgent,
        "awaiting_my_approval": approval,
        "total_visible": total,
    }


# --- Create -----------------------------------------------------------------

@router.post("/work-items", response_model=WorkItemDetail, status_code=201)
def create_work_item(
    payload: WorkItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> WorkItemDetail:
    membership = _resolve_team_membership(payload.team_id, current_user, db)
    # Only managers can create work items (could be relaxed; challenge implies
    # managers triage the queue).
    if membership.role != "manager":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only managers can create work items")

    # Idempotency check.
    raw_body = json.dumps(payload.model_dump(), sort_keys=True, default=str)
    idem = _idem_key("create", current_user.id, raw_body) if idempotency_key is None else idempotency_key
    prior = _check_idempotency(db, idem)
    if prior is not None:
        # Replay the original response (and its status). We return 201 with the
        # stored body; clients see the same work item id as the first call.
        wi = db.get(WorkItem, prior.get("id"))
        if wi is not None:
            return _enrich_detail(wi, db)

    if payload.assignee_id is not None:
        # Assignee must be a member of the same team.
        ok = db.execute(
            select(TeamMember).where(
                TeamMember.team_id == payload.team_id,
                TeamMember.user_id == payload.assignee_id,
            )
        ).scalars().first()
        if ok is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assignee is not a team member")

    wi = WorkItem(
        team_id=payload.team_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_at=payload.due_at,
        assignee_id=payload.assignee_id,
        status="open" if payload.assignee_id is None else "in_progress",
        version=1,
    )
    db.add(wi)
    db.flush()  # populate wi.id for the activity + idempotency rows

    activity = ActivityEvent(
        work_item_id=wi.id,
        actor_id=current_user.id,
        action="created",
        detail=f"created by {current_user.email}",
        version_after=wi.version,
    )
    db.add(activity)
    _store_idempotency(db, idem, 201, {"id": wi.id})
    db.commit()
    db.refresh(wi)
    return _enrich_detail(wi, db)


# --- Get --------------------------------------------------------------------

@router.get("/work-items/{work_item_id}", response_model=WorkItemDetail)
def get_work_item(
    work_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkItemDetail:
    wi = db.get(WorkItem, work_item_id)
    if wi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work item not found")
    _resolve_team_membership(wi.team_id, current_user, db)
    return _enrich_detail(wi, db)


# --- Update (optimistic concurrency) ---------------------------------------

@router.put("/work-items/{work_item_id}", response_model=WorkItemDetail)
def update_work_item(
    work_item_id: int,
    payload: WorkItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> WorkItemDetail:
    wi = db.get(WorkItem, work_item_id)
    if wi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work item not found")
    membership = _resolve_team_membership(wi.team_id, current_user, db)

    # Idempotency.
    raw_body = json.dumps(payload.model_dump(), sort_keys=True, default=str)
    idem = _idem_key(f"update:{work_item_id}", current_user.id, raw_body) if idempotency_key is None else idempotency_key
    prior = _check_idempotency(db, idem)
    if prior is not None and prior.get("id") == work_item_id:
        wi2 = db.get(WorkItem, work_item_id)
        return _enrich_detail(wi2, db)

    # Optimistic concurrency: the version sent must match the current row.
    if payload.version != wi.version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": "This work item was modified by someone else. Refresh and try again.",
                "current_version": wi.version,
                "your_version": payload.version,
            },
        )

    # Authorization: managers can edit anything on their team; contributors
    # may edit only items assigned to them, and only a subset of fields.
    if membership.role != "manager":
        if wi.assignee_id != current_user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit work assigned to you")
        # Contributors may not reassign.
        if payload.assignee_id is not None and payload.assignee_id != current_user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Contributors cannot reassign work")

    if payload.assignee_id is not None and payload.assignee_id != wi.assignee_id:
        # Reassign: only managers, and target must be a team member.
        if membership.role != "manager":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only managers can reassign")
        ok = db.execute(
            select(TeamMember).where(
                TeamMember.team_id == wi.team_id,
                TeamMember.user_id == payload.assignee_id,
            )
        ).scalars().first()
        if ok is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assignee is not a team member")
        wi.assignee_id = payload.assignee_id

    if payload.title is not None:
        wi.title = payload.title
    if payload.description is not None:
        wi.description = payload.description
    if payload.priority is not None:
        wi.priority = payload.priority
    if payload.due_at is not None:
        wi.due_at = payload.due_at

    wi.version += 1
    db.add(
        ActivityEvent(
            work_item_id=wi.id,
            actor_id=current_user.id,
            action="updated",
            detail=f"updated by {current_user.email}",
            version_after=wi.version,
        )
    )
    _store_idempotency(db, idem, 200, {"id": wi.id})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Conflict updating work item")
    db.refresh(wi)
    return _enrich_detail(wi, db)


# --- Transition (claim / approve / etc.) -----------------------------------

@router.post("/work-items/{work_item_id}/transition", response_model=WorkItemDetail)
def transition_work_item(
    work_item_id: int,
    payload: TransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> WorkItemDetail:
    wi = db.get(WorkItem, work_item_id)
    if wi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work item not found")
    membership = _resolve_team_membership(wi.team_id, current_user, db)

    # Idempotency on the transition action + version.
    raw_body = json.dumps({"action": payload.action, "version": payload.version})
    idem = (
        _idem_key(f"transition:{work_item_id}", current_user.id, raw_body)
        if idempotency_key is None
        else idempotency_key
    )
    prior = _check_idempotency(db, idem)
    if prior is not None and prior.get("id") == work_item_id:
        return _enrich_detail(db.get(WorkItem, work_item_id), db)

    # Optimistic concurrency on transitions too.
    if payload.version != wi.version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": "This work item was modified by someone else. Refresh and try again.",
                "current_version": wi.version,
                "your_version": payload.version,
            },
        )

    try:
        apply_transition(db=db, work_item=wi, action=payload.action, actor=current_user, membership=membership)
    except TransitionNotAllowed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except NotAuthorized as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))

    _store_idempotency(db, idem, 200, {"id": wi.id})
    db.commit()
    db.refresh(wi)
    return _enrich_detail(wi, db)


# --- Comments ---------------------------------------------------------------

@router.post("/work-items/{work_item_id}/comments", response_model=CommentPublic, status_code=201)
def add_comment(
    work_item_id: int,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> CommentPublic:
    wi = db.get(WorkItem, work_item_id)
    if wi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work item not found")
    _resolve_team_membership(wi.team_id, current_user, db)

    raw_body = json.dumps(payload.model_dump(), sort_keys=True)
    idem = _idem_key(f"comment:{work_item_id}", current_user.id, raw_body) if idempotency_key is None else idempotency_key
    prior = _check_idempotency(db, idem)
    if prior is not None and prior.get("id") is not None:
        c = db.get(Comment, prior["id"])
        if c is not None:
            return CommentPublic.model_validate(c).model_copy(
                update={"author_name": c.author.full_name if c.author else None}
            )

    c = Comment(work_item_id=work_item_id, author_id=current_user.id, body=payload.body)
    db.add(c)
    db.flush()
    _store_idempotency(db, idem, 201, {"id": c.id})
    db.commit()
    db.refresh(c)
    return CommentPublic.model_validate(c).model_copy(
        update={"author_name": c.author.full_name if c.author else None}
    )


# --- Activity timeline ------------------------------------------------------

@router.get("/work-items/{work_item_id}/activity", response_model=list[ActivityEventPublic])
def list_activity(
    work_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityEventPublic]:
    wi = db.get(WorkItem, work_item_id)
    if wi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work item not found")
    _resolve_team_membership(wi.team_id, current_user, db)
    rows = db.execute(
        select(ActivityEvent)
        .where(ActivityEvent.work_item_id == work_item_id)
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
    ).scalars().all()
    out = []
    for a in rows:
        actor = db.get(User, a.actor_id)
        out.append(
            ActivityEventPublic.model_validate(a).model_copy(
                update={"actor_name": actor.full_name if actor else None}
            )
        )
    return out


# --- Comments list ----------------------------------------------------------

@router.get("/work-items/{work_item_id}/comments", response_model=list[CommentPublic])
def list_comments(
    work_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CommentPublic]:
    wi = db.get(WorkItem, work_item_id)
    if wi is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work item not found")
    _resolve_team_membership(wi.team_id, current_user, db)
    rows = db.execute(
        select(Comment)
        .where(Comment.work_item_id == work_item_id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    ).scalars().all()
    out = []
    for c in rows:
        out.append(
            CommentPublic.model_validate(c).model_copy(
                update={"author_name": c.author.full_name if c.author else None}
            )
        )
    return out


__all__ = ["router"]
