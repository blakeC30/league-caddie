"""
Standings router — /leagues/{league_id}/standings

Endpoints:
  GET /leagues/{league_id}/standings   Current season standings for the league
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_season, require_active_purchase, require_league_member
from app.models import League, LeagueMember, LeaguePurchase, Season
from app.schemas.standings import StandingsResponse, StandingsRow
from app.services.scoring import calculate_standings

router = APIRouter(prefix="/leagues/{league_id}/standings", tags=["standings"])


@router.get("", response_model=StandingsResponse)
def get_standings(
    league_and_member: tuple[League, LeagueMember] = Depends(require_league_member),
    purchase: LeaguePurchase | None = Depends(require_active_purchase),
    season: Season = Depends(get_active_season),
    db: Session = Depends(get_db),
):
    """
    Return the current season standings for all league members.

    Points are calculated from completed tournament picks. Members who missed
    a tournament receive the league's no_pick_penalty for that week.
    Rows are sorted best-to-worst (highest total_points first).
    """
    league, _ = league_and_member
    raw_rows = calculate_standings(db, league, season)

    # Competition ranking (golf-style) — single-pass O(N) algorithm.
    # raw_rows is already sorted by total_points descending from calculate_standings.
    #   Tied players share the rank of their group's first position, and the
    #   next rank skips over the tied spots.
    #   Example: scores [100, 80, 80, 60] → ranks [1, 2, 2, 4]
    #            is_tied                  → [F, T, T, F]
    #
    # First pass: assign ranks. When points match the previous row, reuse its
    # rank; otherwise rank = position (1-indexed). This is O(N).
    ranks = []
    for i, row in enumerate(raw_rows):
        if i == 0:
            ranks.append(1)
        elif row["total_points"] == raw_rows[i - 1]["total_points"]:
            ranks.append(ranks[i - 1])
        else:
            ranks.append(i + 1)

    # Second pass: mark ties. A row is tied if any adjacent row shares its rank.
    tied = set()
    for i in range(len(ranks)):
        if (i > 0 and ranks[i] == ranks[i - 1]) or (
            i < len(ranks) - 1 and ranks[i] == ranks[i + 1]
        ):
            tied.add(i)

    rows = [
        StandingsRow(
            rank=ranks[i],
            is_tied=i in tied,
            user_id=row["user_id"],
            display_name=row["display_name"],
            total_points=row["total_points"],
            pick_count=row["pick_count"],
            missed_count=row["missed_count"],
        )
        for i, row in enumerate(raw_rows)
    ]

    return StandingsResponse(
        league_id=league.id,
        season_year=season.year,
        rows=rows,
    )
