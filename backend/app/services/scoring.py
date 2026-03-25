"""
Scoring service.

Calculates season standings from picks stored in the database.

Scoring rules:
  - points_earned = golfer_earnings_usd * tournament.multiplier
  - If a user has no pick row for a completed tournament → league.no_pick_penalty is applied
  - Standings are sorted by total_points descending (highest wins)

Tie-breaking (applied in order when total_points are equal):
  1. Most picks submitted (higher pick_count wins — rewards consistent participation)
  2. Highest single-tournament score (best_week — rewards peak performance)
  3. Earliest league join date (joined_at ascending — stable, ungameable last resort)

This module contains pure calculation logic with no HTTP concerns. It can be
called from both the standings router and the scraper (when finalizing results).
"""

import datetime
import logging
from datetime import UTC

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session, joinedload

from app.models import (
    League,
    LeagueMember,
    LeagueMemberStatus,
    LeagueTournament,
    Pick,
    PlayoffConfig,
    PlayoffRound,
    Season,
    Tournament,
    TournamentStatus,
)

log = logging.getLogger(__name__)

_STANDINGS_CACHE_TTL = datetime.timedelta(minutes=5)


def invalidate_standings_cache(db: Session, season: Season) -> None:
    """Clear the cached standings so the next request recomputes them."""
    season.standings_cache = None
    season.standings_cached_at = None
    db.flush()


def invalidate_standings_cache_for_league(db: Session, league_id) -> None:
    """Find the active season for a league and clear its standings cache."""
    season = db.query(Season).filter_by(league_id=league_id, is_active=True).first()
    if season:
        invalidate_standings_cache(db, season)


def refresh_standings_cache(db: Session, season: Season) -> None:
    """Recompute and store standings immediately (write-through cache).

    Called after score_picks and other write operations so the cache is always
    warm. User requests hit the fresh cache instead of triggering recomputation.
    """
    league = db.query(League).filter_by(id=season.league_id).first()
    if not league:
        return
    # Force past the TTL check by clearing first, then recomputing.
    season.standings_cache = None
    season.standings_cached_at = None
    db.flush()
    calculate_standings(db, league, season)


def refresh_standings_cache_for_league(db: Session, league_id) -> None:
    """Find the active season for a league and refresh its standings cache."""
    season = db.query(Season).filter_by(league_id=league_id, is_active=True).first()
    if season:
        refresh_standings_cache(db, season)


def calculate_standings(db: Session, league: League, season: Season) -> list[dict]:
    """
    Return standings rows for a league season, sorted best to worst.

    Each row is a dict with:
      user_id, display_name, total_points, pick_count, missed_count

    Results are cached on the Season row for up to 5 minutes to avoid
    recomputing O(N×M) on every page load. The cache is explicitly
    invalidated when picks, members, or scores change.
    """
    # Return cached result if still fresh
    if (
        season.standings_cache is not None
        and season.standings_cached_at is not None
        and datetime.datetime.now(UTC) - season.standings_cached_at < _STANDINGS_CACHE_TTL
    ):
        log.debug(
            "Standings cache hit: league=%s season=%d",
            str(league.id),
            season.year,
        )
        return season.standings_cache

    log.info("Calculating standings: league=%s season=%d", str(league.id), season.year)
    # Only count tournaments the league admin explicitly added to the schedule
    # AND that have completed. This lets leagues start mid-season and handles
    # weeks with multiple simultaneous events.
    scheduled_ids_subq = (
        db.query(LeagueTournament.tournament_id)
        .filter(LeagueTournament.league_id == league.id)
        .scalar_subquery()
    )
    season_tournaments = (
        db.query(Tournament)
        .filter(
            Tournament.id.in_(scheduled_ids_subq),
            Tournament.status == TournamentStatus.COMPLETED.value,
            Tournament.start_date >= datetime.date(season.year, 1, 1),
            Tournament.start_date <= datetime.date(season.year, 12, 31),
        )
        .all()
    )

    # Exclude playoff tournaments — playoff members play via PlayoffPick, not
    # Pick, so they have no regular-season Pick records for those weeks. Without
    # this exclusion they'd receive spurious no-pick penalties in the standings.
    config = db.query(PlayoffConfig).filter_by(league_id=league.id, season_id=season.id).first()
    playoff_tournament_ids: set = set()
    if config:
        rows = (
            db.query(PlayoffRound.tournament_id)
            .filter(
                PlayoffRound.playoff_config_id == config.id,
                PlayoffRound.tournament_id.isnot(None),
            )
            .all()
        )
        playoff_tournament_ids = {row.tournament_id for row in rows}

    completed_ids = {t.id for t in season_tournaments if t.id not in playoff_tournament_ids}

    # Only approved members appear in standings — pending requests are excluded.
    members = (
        db.query(LeagueMember)
        .filter_by(league_id=league.id, status=LeagueMemberStatus.APPROVED.value)
        .options(joinedload(LeagueMember.user))
        .all()
    )

    if not completed_ids:
        # Season hasn't started yet — everyone tied at 0.
        return [
            {
                "user_id": m.user_id,
                "display_name": m.user.display_name,
                "total_points": 0.0,
                "pick_count": 0,
                "missed_count": 0,
            }
            for m in members
        ]

    # Aggregate picks per user in SQL — avoids loading 15,000+ Pick ORM objects.
    # Returns (user_id, sum_points, pick_count, best_week) per user.
    completed_count = len(completed_ids)
    pick_stats = (
        db.query(
            Pick.user_id,
            sqlfunc.coalesce(sqlfunc.sum(Pick.points_earned), 0.0).label("sum_points"),
            sqlfunc.count(Pick.id).label("pick_count"),
            sqlfunc.coalesce(sqlfunc.max(Pick.points_earned), 0.0).label("best_week"),
        )
        .filter(
            Pick.league_id == league.id,
            Pick.season_id == season.id,
            Pick.tournament_id.in_(completed_ids),
            Pick.points_earned.is_not(None),
        )
        .group_by(Pick.user_id)
        .all()
    )
    stats_by_user = {row.user_id: row for row in pick_stats}

    standings = []
    for member in members:
        row = stats_by_user.get(member.user_id)
        if row:
            pick_count = row.pick_count
            sum_points = float(row.sum_points)
            best_week = float(row.best_week)
        else:
            pick_count = 0
            sum_points = 0.0
            best_week = 0.0

        missed_count = completed_count - pick_count
        total_points = sum_points + missed_count * league.no_pick_penalty

        standings.append(
            {
                "user_id": member.user_id,
                "display_name": member.user.display_name,
                "total_points": total_points,
                "pick_count": pick_count,
                "missed_count": missed_count,
                "best_week": best_week,
                "joined_at": member.joined_at,
            }
        )

    # Sort by total_points desc, then tie-break:
    #   1. pick_count desc  — most picks submitted (consistent participation)
    #   2. best_week desc   — highest single-tournament score (peak performance)
    #   3. joined_at asc    — earliest join date (stable, ungameable last resort)
    standings.sort(
        key=lambda x: (
            -x["total_points"],
            -x["pick_count"],
            -x["best_week"],
            x["joined_at"],
        )
    )
    log.debug(
        "Standings calculated: league=%s members=%d completed_tournaments=%d",
        str(league.id),
        len(standings),
        len(completed_ids),
    )

    # Cache the result. Convert non-JSON-serializable fields (UUID, datetime)
    # to strings for storage; callers consume dicts so string user_id is fine
    # (Pydantic coerces it back to UUID in the schema).
    cache_rows = [
        {
            **row,
            "user_id": str(row["user_id"]),
            "joined_at": row["joined_at"].isoformat() if row.get("joined_at") else None,
        }
        for row in standings
    ]
    season.standings_cache = cache_rows
    season.standings_cached_at = datetime.datetime.now(UTC)
    db.commit()

    return standings
