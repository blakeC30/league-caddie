"""User schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    """
    Safe public representation of a user.

    password_hash and google_id are intentionally excluded — never expose them.
    """

    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool
    pick_reminders_enabled: bool
    created_at: datetime

    # from_attributes=True tells Pydantic to read data from ORM object
    # attributes (e.g. user.email) instead of dict keys. Required when
    # returning SQLAlchemy model instances from FastAPI routes.
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    """Fields the user is allowed to change about themselves."""

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    pick_reminders_enabled: bool | None = None


# ---------------------------------------------------------------------------
# League summary (batch endpoint for Leagues page)
# ---------------------------------------------------------------------------


class LeagueSummaryTournament(BaseModel):
    id: uuid.UUID
    name: str
    start_date: str
    end_date: str
    status: str
    purse_usd: int | None
    effective_multiplier: float
    all_r1_teed_off: bool


class LeagueSummaryPick(BaseModel):
    golfer_name: str
    is_locked: bool


class LeagueSummaryPlayoffPick(BaseModel):
    golfer_name: str


class LeagueSummaryOut(BaseModel):
    league_id: uuid.UUID
    league_name: str
    # Standings
    rank: int | None = None
    is_tied: bool = False
    total_points: int | None = None
    member_count: int = 0
    # Role
    is_manager: bool = False
    # Current tournament
    current_tournament: LeagueSummaryTournament | None = None
    # Pick for current tournament
    my_pick: LeagueSummaryPick | None = None
    # Playoff
    is_playoff_week: bool = False
    is_in_playoffs: bool = False
    my_playoff_picks: list[LeagueSummaryPlayoffPick] = []
    # Pick window
    pick_window_open: bool = False
    # "Picks open after X" message
    preceding_tournament_name: str | None = None
