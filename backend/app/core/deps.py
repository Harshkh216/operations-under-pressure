"""FastAPI auth dependencies: resolve the current user from the JWT bearer
token, and provide helpers for team-membership and role checks.

Authorization is enforced per request, in application code, on top of the
per-team role stored in ``team_members.role``. This is deliberate: the API
owns the authz rules so they can be unit-tested end-to-end without depending
on database-level RLS.
"""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import JWTError, decode_access_token
from app.db.session import get_db
from app.models import TeamMember, User

# tokenUrl is the relative path clients use to obtain a token (for OpenAPI).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=True)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise cred_exc
    except JWTError:
        raise cred_exc

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise cred_exc
    return user


def get_membership(team_id: int) -> Callable[..., TeamMember]:
    """Dependency factory: require that the current user belongs to ``team_id``
    and return the membership row. Raises 403 otherwise."""

    def _dep(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> TeamMember:
        m = db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == current_user.id,
            )
        ).scalars().first()
        if m is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this team",
            )
        return m

    return _dep


def require_role(*roles: str) -> Callable[..., TeamMember]:
    """Dependency factory: require that the membership role is in ``roles``.
    Use on top of ``get_membership`` (the route must also resolve a team_id)."""

    allowed = set(roles)

    def _dep(membership: TeamMember = Depends()) -> TeamMember:
        if membership.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(allowed)}",
            )
        return membership

    return _dep


__all__ = ["oauth2_scheme", "get_current_user", "get_membership", "require_role"]
