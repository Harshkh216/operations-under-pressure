"""Authentication endpoints: POST /api/login."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import TeamMember, User
from app.schemas import LoginRequest, MembershipPublic, TokenResponse, UserWithMemberships

router = APIRouter(prefix="/api", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalars().first()
    if user is None or not verify_password(payload.password, user.password_hash):
        logger.warning("Login rejected for email=%s", payload.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    token = create_access_token(subject=str(user.id))
    pub = _user_with_memberships(user, db)
    logger.info("Login succeeded user_id=%s membership_count=%s", user.id, len(pub.memberships))
    return TokenResponse(access_token=token, user=pub)


@router.get("/me", response_model=UserWithMemberships)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserWithMemberships:
    return _user_with_memberships(current_user, db)


def _user_with_memberships(user: User, db: Session) -> UserWithMemberships:
    memberships = db.execute(
        select(TeamMember).where(TeamMember.user_id == user.id)
    ).scalars().all()
    return UserWithMemberships(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        memberships=[
            MembershipPublic(
                team_id=m.team_id, team_slug=m.team.slug, team_name=m.team.name, role=m.role,
            )
            for m in memberships
        ],
    )


__all__ = ["router"]
