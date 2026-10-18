"""Admin endpoints for inspecting the outbox (handy for demos/tests)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import OutboxEvent, User
from app.schemas import OutboxEventPublic
from app.services.outbox import drain_once

router = APIRouter(prefix="/api/outbox", tags=["outbox"])


@router.get("", response_model=list[OutboxEventPublic])
def list_outbox(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[OutboxEventPublic]:
    rows = db.execute(
        select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).limit(50)
    ).scalars().all()
    return [OutboxEventPublic.model_validate(r) for r in rows]


@router.post("/drain")
def drain(current_user: User = Depends(get_current_user)) -> dict:
    n = drain_once()
    return {"processed": n}


__all__ = ["router"]
