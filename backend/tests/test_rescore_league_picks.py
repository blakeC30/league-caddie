"""
Tests for rescore_league_picks() — pure SQL rescoring with no ESPN calls.

Covers real user scenarios:
  - Multiplier change rescores correctly
  - Only the target league's picks are affected (no cross-league side effects)
  - Golfer with no TournamentEntry gets zero points
  - Golfer with NULL earnings gets zero points
  - Multiple completed tournaments rescored independently
  - Standings cache is refreshed after rescore
"""

import uuid
from datetime import date, timedelta

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueTournament,
    Pick,
    Season,
    Tournament,
    TournamentEntry,
    TournamentStatus,
    User,
)
from app.services.auth import hash_password
from app.services.scoring import rescore_league_picks


def _make_user(db, email, display_name="Test"):
    user = User(
        email=email,
        password_hash=hash_password("password1"),
        display_name=display_name,
    )
    db.add(user)
    db.flush()
    return user


def _make_league_with_season(db, user, league_name="Test League"):
    league = League(name=league_name, created_by=user.id)
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=user.id,
            role=LeagueMemberRole.MANAGER.value,
        )
    )
    season = Season(league_id=league.id, year=date.today().year, is_active=True)
    db.add(season)
    db.flush()
    return league, season


def _make_completed_tournament(db, name, pga_tour_id=None):
    t_start = date.today() - timedelta(days=7)
    tournament = Tournament(
        pga_tour_id=pga_tour_id or f"T-{uuid.uuid4().hex[:8]}",
        name=name,
        start_date=t_start,
        end_date=t_start + timedelta(days=3),
        status=TournamentStatus.COMPLETED.value,
    )
    db.add(tournament)
    db.flush()
    return tournament


def _make_golfer(db, name, pga_tour_id=None):
    golfer = Golfer(
        pga_tour_id=pga_tour_id or f"G-{uuid.uuid4().hex[:8]}",
        name=name,
    )
    db.add(golfer)
    db.flush()
    return golfer


class TestRescoreLeaguePicks:
    """Core rescore functionality."""

    def test_rescores_with_multiplier(self, db):
        """Changing a multiplier from 1x to 2x should double points."""
        user = _make_user(db, "rescore1@test.com")
        league, season = _make_league_with_season(db, user)
        tournament = _make_completed_tournament(db, "Rescore Major")
        golfer = _make_golfer(db, "Winner")

        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=golfer.id,
                earnings_usd=1_000_000,
            )
        )
        # Start with 1x multiplier
        db.add(
            LeagueTournament(
                league_id=league.id,
                tournament_id=tournament.id,
                multiplier=1.0,
            )
        )
        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        db.add(pick)
        db.commit()

        # Score at 1x
        count = rescore_league_picks(db, tournament.id, league.id)
        db.commit()
        assert count == 1
        db.refresh(pick)
        assert pick.points_earned == 1_000_000.0

        # Now change multiplier to 2x and rescore
        lt = (
            db.query(LeagueTournament)
            .filter_by(league_id=league.id, tournament_id=tournament.id)
            .first()
        )
        lt.multiplier = 2.0
        db.flush()

        count = rescore_league_picks(db, tournament.id, league.id)
        db.commit()
        assert count == 1
        db.refresh(pick)
        assert pick.points_earned == 2_000_000.0

    def test_no_cross_league_side_effects(self, db):
        """Rescoring league A must not change league B's picks."""
        user_a = _make_user(db, "leagueA@test.com", "User A")
        user_b = _make_user(db, "leagueB@test.com", "User B")
        league_a, season_a = _make_league_with_season(db, user_a, "League A")
        league_b, season_b = _make_league_with_season(db, user_b, "League B")

        tournament = _make_completed_tournament(db, "Shared Tournament")
        golfer = _make_golfer(db, "Shared Golfer")

        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=golfer.id,
                earnings_usd=500_000,
            )
        )
        # League A: 2x multiplier
        db.add(
            LeagueTournament(
                league_id=league_a.id,
                tournament_id=tournament.id,
                multiplier=2.0,
            )
        )
        # League B: 1x multiplier
        db.add(
            LeagueTournament(
                league_id=league_b.id,
                tournament_id=tournament.id,
                multiplier=1.0,
            )
        )

        pick_a = Pick(
            league_id=league_a.id,
            season_id=season_a.id,
            user_id=user_a.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        pick_b = Pick(
            league_id=league_b.id,
            season_id=season_b.id,
            user_id=user_b.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        db.add_all([pick_a, pick_b])
        db.commit()

        # Score both leagues initially
        rescore_league_picks(db, tournament.id, league_a.id)
        rescore_league_picks(db, tournament.id, league_b.id)
        db.commit()

        db.refresh(pick_a)
        db.refresh(pick_b)
        assert pick_a.points_earned == 1_000_000.0  # 500k × 2
        assert pick_b.points_earned == 500_000.0  # 500k × 1

        # Now rescore only league A with a new multiplier
        lt_a = (
            db.query(LeagueTournament)
            .filter_by(league_id=league_a.id, tournament_id=tournament.id)
            .first()
        )
        lt_a.multiplier = 3.0
        db.flush()

        rescore_league_picks(db, tournament.id, league_a.id)
        db.commit()

        db.refresh(pick_a)
        db.refresh(pick_b)
        assert pick_a.points_earned == 1_500_000.0  # 500k × 3
        assert pick_b.points_earned == 500_000.0  # unchanged

    def test_golfer_with_no_entry_gets_zero(self, db):
        """If a golfer withdrew before field sync (no TournamentEntry), score = 0."""
        user = _make_user(db, "noentry@test.com")
        league, season = _make_league_with_season(db, user)
        tournament = _make_completed_tournament(db, "No Entry Open")
        golfer = _make_golfer(db, "Ghost Golfer")

        # No TournamentEntry for this golfer
        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        db.add(pick)
        db.commit()

        count = rescore_league_picks(db, tournament.id, league.id)
        db.commit()
        assert count == 1
        db.refresh(pick)
        assert pick.points_earned == 0

    def test_null_earnings_scores_zero(self, db):
        """Entry with NULL earnings_usd should score as 0 (not trigger ESPN)."""
        user = _make_user(db, "nullearnings@test.com")
        league, season = _make_league_with_season(db, user)
        tournament = _make_completed_tournament(db, "Null Earnings Open")
        golfer = _make_golfer(db, "Cut Golfer")

        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=golfer.id,
                earnings_usd=None,
            )
        )
        db.add(
            LeagueTournament(
                league_id=league.id,
                tournament_id=tournament.id,
                multiplier=2.0,
            )
        )
        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        db.add(pick)
        db.commit()

        count = rescore_league_picks(db, tournament.id, league.id)
        db.commit()
        assert count == 1
        db.refresh(pick)
        assert pick.points_earned == 0.0  # COALESCE(NULL, 0) × 2.0 = 0

    def test_no_league_tournament_defaults_multiplier_to_one(self, db):
        """If no LeagueTournament row exists, multiplier defaults to 1.0."""
        user = _make_user(db, "nomult@test.com")
        league, season = _make_league_with_season(db, user)
        tournament = _make_completed_tournament(db, "No Mult Open")
        golfer = _make_golfer(db, "Default Golfer")

        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=golfer.id,
                earnings_usd=750_000,
            )
        )
        # No LeagueTournament row — multiplier defaults to 1.0
        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        db.add(pick)
        db.commit()

        count = rescore_league_picks(db, tournament.id, league.id)
        db.commit()
        assert count == 1
        db.refresh(pick)
        assert pick.points_earned == 750_000.0

    def test_rescore_returns_zero_for_no_picks(self, db):
        """If no picks exist for the tournament, count is 0."""
        user = _make_user(db, "nopicks@test.com")
        league, _season = _make_league_with_season(db, user)
        tournament = _make_completed_tournament(db, "Empty Open")

        count = rescore_league_picks(db, tournament.id, league.id)
        assert count == 0

    def test_standings_cache_refreshed(self, db):
        """Rescore should refresh standings cache when picks are updated."""
        user = _make_user(db, "cache@test.com")
        league, season = _make_league_with_season(db, user)
        tournament = _make_completed_tournament(db, "Cache Open")
        golfer = _make_golfer(db, "Cache Golfer")

        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=golfer.id,
                earnings_usd=200_000,
            )
        )
        db.add(
            LeagueTournament(
                league_id=league.id,
                tournament_id=tournament.id,
                multiplier=1.0,
            )
        )
        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        db.add(pick)
        db.commit()

        # Rescore with standings refresh enabled (default)
        rescore_league_picks(db, tournament.id, league.id)
        db.commit()

        db.refresh(season)
        assert season.standings_cache is not None
        assert len(season.standings_cache) == 1
        assert float(season.standings_cache[0]["total_points"]) == 200_000.0

    def test_skip_standings_refresh(self, db):
        """When skip_standings_refresh=True, cache should not be updated."""
        user = _make_user(db, "skiprefresh@test.com")
        league, season = _make_league_with_season(db, user)
        tournament = _make_completed_tournament(db, "Skip Refresh Open")
        golfer = _make_golfer(db, "Skip Golfer")

        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=golfer.id,
                earnings_usd=100_000,
            )
        )
        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        db.add(pick)
        db.commit()

        # Clear any existing cache
        season.standings_cache = None
        season.standings_cached_at = None
        db.commit()

        rescore_league_picks(db, tournament.id, league.id, skip_standings_refresh=True)
        db.commit()

        db.refresh(season)
        assert season.standings_cache is None

    def test_multiple_members_rescored(self, db):
        """All members' picks in the league are rescored, not just one."""
        user1 = _make_user(db, "multi1@test.com", "User 1")
        user2 = _make_user(db, "multi2@test.com", "User 2")
        league, season = _make_league_with_season(db, user1)
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user2.id,
                role=LeagueMemberRole.MEMBER.value,
            )
        )

        tournament = _make_completed_tournament(db, "Multi Open")
        golfer1 = _make_golfer(db, "Golfer 1")
        golfer2 = _make_golfer(db, "Golfer 2")

        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=golfer1.id,
                earnings_usd=1_000_000,
            )
        )
        db.add(
            TournamentEntry(
                tournament_id=tournament.id,
                golfer_id=golfer2.id,
                earnings_usd=500_000,
            )
        )
        db.add(
            LeagueTournament(
                league_id=league.id,
                tournament_id=tournament.id,
                multiplier=1.5,
            )
        )

        pick1 = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user1.id,
            tournament_id=tournament.id,
            golfer_id=golfer1.id,
        )
        pick2 = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user2.id,
            tournament_id=tournament.id,
            golfer_id=golfer2.id,
        )
        db.add_all([pick1, pick2])
        db.commit()

        count = rescore_league_picks(db, tournament.id, league.id)
        db.commit()
        assert count == 2

        db.refresh(pick1)
        db.refresh(pick2)
        assert pick1.points_earned == 1_500_000.0  # 1M × 1.5
        assert pick2.points_earned == 750_000.0  # 500k × 1.5
