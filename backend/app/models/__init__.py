"""
Import all models here so that:
  1. They are registered with Base.metadata before Alembic runs.
  2. Anywhere in the app that does `from app.models import User` works cleanly.
"""

from app.models.base import Base
from app.models.golfer import Golfer
from app.models.league import League, LeagueMember, LeagueMemberRole, LeagueMemberStatus
from app.models.league_tournament import LeagueTournament
from app.models.password_reset_token import PasswordResetToken
from app.models.pick import Pick
from app.models.pick_reminder import PickReminder
from app.models.playoff import (
    PlayoffConfig,
    PlayoffDraftPreference,
    PlayoffPick,
    PlayoffPod,
    PlayoffPodMember,
    PlayoffRound,
)
from app.models.season import Season
from app.models.tournament import (
    Tournament,
    TournamentEntry,
    TournamentEntryRound,
    TournamentStatus,
)
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "League",
    "LeagueMember",
    "LeagueMemberRole",
    "LeagueMemberStatus",
    "Season",
    "Golfer",
    "Tournament",
    "TournamentEntry",
    "TournamentEntryRound",
    "TournamentStatus",
    "Pick",
    "LeagueTournament",
    "PickReminder",
    "PlayoffConfig",
    "PlayoffRound",
    "PlayoffPod",
    "PlayoffPodMember",
    "PlayoffPick",
    "PlayoffDraftPreference",
    "PasswordResetToken",
]
