"""Pydantic schemas (request/response models) for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# --- Enums / literals -------------------------------------------------------

Priority = Literal["low", "medium", "high", "urgent"]
WorkStatus = Literal["open", "in_progress", "blocked", "in_review", "approved", "rejected", "done", "cancelled"]
Role = Literal["manager", "contributor"]

VALID_TRANSITION = Literal[
    "claim", "release", "start_review", "approve", "reject", "block", "unblock", "complete", "cancel"
]


# --- Auth -------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: "UserWithMemberships"


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    is_active: bool


class MembershipPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    team_id: int
    team_slug: str
    team_name: str
    role: Role


class UserWithMemberships(UserPublic):
    memberships: list[MembershipPublic] = []


# --- Teams ------------------------------------------------------------------

class TeamPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str


# --- Work items -------------------------------------------------------------

class WorkItemBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    priority: Priority = "medium"
    due_at: datetime | None = None


class WorkItemCreate(WorkItemBase):
    team_id: int
    assignee_id: int | None = None


class WorkItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    priority: Priority | None = None
    due_at: datetime | None = None
    assignee_id: int | None = None
    # Required for optimistic concurrency: the version the client last read.
    version: int = Field(..., description="Version the client last read; must match the current row")


class WorkItemPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    team_id: int
    title: str
    description: str
    status: WorkStatus
    priority: Priority
    assignee_id: int | None
    version: int
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    assignee_name: str | None = None


class WorkItemDetail(WorkItemPublic):
    team_name: str | None = None


class WorkItemListResponse(BaseModel):
    items: list[WorkItemPublic]
    total: int
    page: int
    page_size: int


# --- Comments ---------------------------------------------------------------

class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    work_item_id: int
    author_id: int
    author_name: str | None = None
    body: str
    created_at: datetime


# --- Activity ---------------------------------------------------------------

class ActivityEventPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    work_item_id: int
    actor_id: int
    actor_name: str | None = None
    action: str
    detail: str
    version_after: int
    created_at: datetime


# --- Transition -------------------------------------------------------------

class TransitionRequest(BaseModel):
    action: VALID_TRANSITION
    version: int = Field(..., description="Current version the client last read")


# --- Outbox / generic -------------------------------------------------------

class OutboxEventPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_type: str
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    processed_at: datetime | None


class MessageResponse(BaseModel):
    message: str


# Forward refs.
TokenResponse.model_rebuild()
