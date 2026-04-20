"""League and league membership schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.user import UserOut


class LeagueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    # Default matches the house rule; league manager can override on creation.
    # Accepts positive values for convenience (frontend sends display value);
    # the validator auto-negates them so the DB always stores non-positive.
    no_pick_penalty: int = -50_000
    auto_accept_requests: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("no_pick_penalty")
    @classmethod
    def normalize_penalty(cls, v: int) -> int:
        if v > 0:
            v = -v
        if v < -500_000:
            raise ValueError("no_pick_penalty cannot exceed -500,000")
        return v


class LeagueUpdate(BaseModel):
    """Partial update for league settings. Only provided fields are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    no_pick_penalty: int | None = None
    accepting_requests: bool | None = None
    auto_accept_requests: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        if isinstance(v, str):
            stripped = v.strip()
            return stripped if stripped else v
        return v

    @field_validator("no_pick_penalty")
    @classmethod
    def normalize_penalty(cls, v: int | None) -> int | None:
        if v is not None and v > 0:
            v = -v
        if v is not None and v < -500_000:
            raise ValueError("no_pick_penalty cannot exceed -500,000")
        return v


class LeagueOut(BaseModel):
    id: uuid.UUID
    name: str
    no_pick_penalty: int
    invite_code: str
    is_public: bool
    accepting_requests: bool
    auto_accept_requests: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeagueMemberOut(BaseModel):
    """A league member with their user details nested."""

    user_id: uuid.UUID
    league_id: uuid.UUID
    role: str
    status: str
    joined_at: datetime
    user: UserOut

    model_config = ConfigDict(from_attributes=True)


class RoleUpdate(BaseModel):
    """Used by league managers to change a member's role."""

    role: str

    @field_validator("role")
    @classmethod
    def must_be_valid_role(cls, v: str) -> str:
        if v not in ("manager", "member"):
            raise ValueError("role must be 'manager' or 'member'")
        return v


class LeagueJoinPreview(BaseModel):
    """League info shown to a user before they confirm a join request."""

    league_id: uuid.UUID
    name: str
    member_count: int
    # None = no relationship, "pending" = waiting for approval, "approved" = already a member
    user_status: str | None
    # False when the manager has paused new join requests
    accepting_requests: bool
    # True when the league auto-accepts join requests (no pending state)
    auto_accept_requests: bool


class LeagueRequestOut(BaseModel):
    """A pending join request from the requesting user's perspective."""

    league_id: uuid.UUID
    league_name: str
    requested_at: datetime


class RosterMemberOut(BaseModel):
    """Roster info for an approved league member.

    email is only populated for league managers; regular members see null.
    """

    user_id: str
    display_name: str
    first_name: str
    last_name: str
    email: str | None = None
    role: str
    joined_at: str


# ---------------------------------------------------------------------------
# Manager league email
# ---------------------------------------------------------------------------


class SendLeagueEmailRequest(BaseModel):
    """Manager sends an email to selected (or all) league members."""

    recipient_user_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=500,
        description="Specific user IDs to email. Empty list = all opted-in members.",
    )
    subject: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def strip_whitespace(self):
        self.subject = self.subject.strip()
        self.body = self.body.strip()
        return self


class LeagueEmailOut(BaseModel):
    id: uuid.UUID
    subject: str
    recipient_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
