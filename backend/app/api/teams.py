"""Team endpoints: list the current user's teams."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import TeamMember, User
from app.schemas import MembershipPublic, TeamPublic

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("", response_model=list[MembershipPublic])
def list_my_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MembershipPublic]:
    rows = db.execute(
        select(TeamMember).where(TeamMember.user_id == current_user.id)
    ).scalars().all()
    return [
        MembershipPublic(
            team_id=m.team_id, team_slug=m.team.slug, team_name=m.team.name, role=m.role,
        )
        for m in rows
    ]


__all__ = ["router"]
