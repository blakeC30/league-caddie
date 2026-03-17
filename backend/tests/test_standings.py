"""
Tests for season standings: scoring, no-pick penalties, tie-breaking, and
competition ranking (golf-style).

Covers both the standings HTTP endpoint and the calculate_standings service
directly so the core scoring logic gets line-level coverage.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeagueTournament,
    Pick,
    Season,
    Tournament,
    TournamentStatus,
    User,
)
from app.services.auth import hash_password
from app.services.scoring import calculate_standings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_user(db: Session, email: str, display_name: str = "Player") -> User:
    user = User(email=email, password_hash=hash_password("password123"), display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_league(
    db: Session, creator: User, name: str = "Test League", penalty: int = -50_000
) -> tuple[League, Season]:
    league = League(name=name, created_by=creator.id, no_pick_penalty=penalty)
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=creator.id,
            role=LeagueMemberRole.MANAGER.value,
            status=LeagueMemberStatus.APPROVED.value,
        )
    )
    season = Season(league_id=league.id, year=date.today().year, is_active=True)
    db.add(season)
    db.commit()
    db.refresh(league)
    db.refresh(season)
    return league, season


def add_member(db: Session, league: League, user: User) -> LeagueMember:
    member = LeagueMember(
        league_id=league.id,
        user_id=user.id,
        role=LeagueMemberRole.MEMBER.value,
        status=LeagueMemberStatus.APPROVED.value,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def make_completed_tournament(
    db: Session, league: League, multiplier: float = 1.0, days_ago: int = 7
) -> Tournament:
    start = date.today() - timedelta(days=days_ago)
    t = Tournament(
        pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
        name=f"Completed Open {uuid.uuid4().hex[:4]}",
        start_date=start,
        end_date=start + timedelta(days=3),
        status=TournamentStatus.COMPLETED.value,
        multiplier=multiplier,
    )
    db.add(t)
    db.flush()
    db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
    db.commit()
    db.refresh(t)
    return t


def make_pick(
    db: Session,
    league: League,
    season: Season,
    user: User,
    tournament: Tournament,
    points_earned: float,
) -> Pick:
    """Insert a pick with points already set (as score_picks would do after completion)."""
    golfer = Golfer(pga_tour_id=f"T{uuid.uuid4().hex[:6]}", name=f"G{uuid.uuid4().hex[:4]}")
    db.add(golfer)
    db.flush()
    pick = Pick(
        league_id=league.id,
        season_id=season.id,
        user_id=user.id,
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        points_earned=points_earned,
    )
    db.add(pick)
    db.commit()
    db.refresh(pick)
    return pick


def _login_headers(client, email: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestStandingsEndpoint:
    def test_empty_standings_before_any_completed_tournament(self, client, auth_headers, db):
        """Everyone starts at 0 until a tournament completes."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rows"]) == 1
        assert data["rows"][0]["total_points"] == 0
        assert data["rows"][0]["rank"] == 1
        assert data["rows"][0]["pick_count"] == 0

    def test_points_reflected_after_completed_tournament(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user)
        tournament = make_completed_tournament(db, league)
        make_pick(db, league, season, user, tournament, points_earned=300_000.0)

        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=auth_headers)
        assert resp.status_code == 200
        row = resp.json()["rows"][0]
        assert row["total_points"] == 300_000.0
        assert row["pick_count"] == 1
        assert row["missed_count"] == 0

    def test_no_pick_penalty_applied_for_missed_tournament(self, client, auth_headers, db):
        """A member who makes no pick receives the league penalty for that week."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = make_league(db, user, penalty=-50_000)
        make_completed_tournament(db, league)  # No pick submitted.

        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=auth_headers)
        assert resp.status_code == 200
        row = resp.json()["rows"][0]
        assert row["total_points"] == -50_000.0
        assert row["missed_count"] == 1
        assert row["pick_count"] == 0

    def test_standings_sorted_best_to_worst(self, client, db):
        p1 = make_user(db, "sort_p1@example.com", "Alpha")
        p2 = make_user(db, "sort_p2@example.com", "Beta")
        league, season = make_league(db, p1)
        add_member(db, league, p2)
        tournament = make_completed_tournament(db, league)

        make_pick(db, league, season, p1, tournament, 500_000.0)
        make_pick(db, league, season, p2, tournament, 100_000.0)

        headers = _login_headers(client, "sort_p1@example.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)
        rows = resp.json()["rows"]

        assert rows[0]["display_name"] == "Alpha"
        assert rows[0]["rank"] == 1
        assert rows[1]["display_name"] == "Beta"
        assert rows[1]["rank"] == 2

    def test_tied_players_share_rank_golf_style(self, client, db):
        """
        Golf-style ranking: tied players share the same rank and the next rank
        is skipped over the tied group.
        E.g. scores [300k, 100k, 100k] → ranks [1, 2, 2] (not [1, 2, 3]).
        """
        p1 = make_user(db, "tie_p1@example.com", "First")
        p2 = make_user(db, "tie_p2@example.com", "Tied A")
        p3 = make_user(db, "tie_p3@example.com", "Tied B")
        league, season = make_league(db, p1)
        add_member(db, league, p2)
        add_member(db, league, p3)
        tournament = make_completed_tournament(db, league)

        make_pick(db, league, season, p1, tournament, 300_000.0)
        make_pick(db, league, season, p2, tournament, 100_000.0)
        make_pick(db, league, season, p3, tournament, 100_000.0)

        headers = _login_headers(client, "tie_p1@example.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)
        rows = resp.json()["rows"]

        first = next(r for r in rows if r["total_points"] == 300_000.0)
        tied = [r for r in rows if r["total_points"] == 100_000.0]

        assert first["rank"] == 1
        assert first["is_tied"] is False
        assert all(r["rank"] == 2 for r in tied)
        assert all(r["is_tied"] is True for r in tied)

    def test_standings_returns_season_year(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, _ = make_league(db, user)

        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=auth_headers)
        assert resp.json()["season_year"] == date.today().year

    def test_non_member_cannot_view_standings(self, client, auth_headers, db):
        creator = make_user(db, "stnd_creator@example.com")
        league, _ = make_league(db, creator)

        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=auth_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Direct service tests — calculate_standings()
# ---------------------------------------------------------------------------


class TestCalculateStandings:
    def test_no_completed_tournaments_everyone_at_zero(self, db):
        user = make_user(db, "cs_empty@example.com")
        league, season = make_league(db, user)

        rows = calculate_standings(db, league, season)
        assert len(rows) == 1
        assert rows[0]["total_points"] == 0
        assert rows[0]["pick_count"] == 0
        assert rows[0]["missed_count"] == 0

    def test_picks_with_earnings_sum_correctly(self, db):
        user = make_user(db, "cs_sum@example.com")
        league, season = make_league(db, user)
        t1 = make_completed_tournament(db, league, days_ago=14)
        t2 = make_completed_tournament(db, league, days_ago=7)
        make_pick(db, league, season, user, t1, 400_000.0)
        make_pick(db, league, season, user, t2, 150_000.0)

        rows = calculate_standings(db, league, season)
        assert rows[0]["total_points"] == 550_000.0
        assert rows[0]["pick_count"] == 2
        assert rows[0]["missed_count"] == 0

    def test_missed_tournament_applies_penalty(self, db):
        user = make_user(db, "cs_miss@example.com")
        league, season = make_league(db, user, penalty=-75_000)
        make_completed_tournament(db, league)  # No pick.

        rows = calculate_standings(db, league, season)
        assert rows[0]["total_points"] == -75_000.0
        assert rows[0]["missed_count"] == 1

    def test_partial_picks_missed_others_penalized(self, db):
        user = make_user(db, "cs_partial@example.com")
        league, season = make_league(db, user, penalty=-50_000)
        t1 = make_completed_tournament(db, league, days_ago=14)
        make_completed_tournament(db, league, days_ago=7)

        make_pick(db, league, season, user, t1, 200_000.0)
        # t2: no pick → penalty applies.

        rows = calculate_standings(db, league, season)
        # 200k earned + (-50k penalty) = 150k.
        assert rows[0]["total_points"] == 150_000.0
        assert rows[0]["pick_count"] == 1
        assert rows[0]["missed_count"] == 1

    def test_tiebreak_by_pick_count(self, db):
        """When total points are equal, the player with more picks submitted wins."""
        p1 = make_user(db, "tb_count_p1@example.com", "More Picks")
        p2 = make_user(db, "tb_count_p2@example.com", "Fewer Picks")
        league, season = make_league(db, p1, penalty=0)
        add_member(db, league, p2)

        t1 = make_completed_tournament(db, league, days_ago=14)
        t2 = make_completed_tournament(db, league, days_ago=7)

        # p1: 50k + 50k = 100k, pick_count=2
        make_pick(db, league, season, p1, t1, 50_000.0)
        make_pick(db, league, season, p1, t2, 50_000.0)
        # p2: 100k + missed (penalty=0) = 100k, pick_count=1
        make_pick(db, league, season, p2, t1, 100_000.0)

        rows = calculate_standings(db, league, season)
        assert rows[0]["display_name"] == "More Picks"
        assert rows[1]["display_name"] == "Fewer Picks"

    def test_tiebreak_by_best_week_when_pick_count_equal(self, db):
        """Second tiebreak: highest single-week score wins."""
        p1 = make_user(db, "tb_best_p1@example.com", "Big Week")
        p2 = make_user(db, "tb_best_p2@example.com", "Consistent")
        league, season = make_league(db, p1, penalty=0)
        add_member(db, league, p2)

        t1 = make_completed_tournament(db, league, days_ago=21)
        t2 = make_completed_tournament(db, league, days_ago=7)

        # Both have 2 picks totaling 200k.
        # p1: 180k + 20k  → best_week = 180k
        # p2: 100k + 100k → best_week = 100k
        make_pick(db, league, season, p1, t1, 180_000.0)
        make_pick(db, league, season, p1, t2, 20_000.0)
        make_pick(db, league, season, p2, t1, 100_000.0)
        make_pick(db, league, season, p2, t2, 100_000.0)

        rows = calculate_standings(db, league, season)
        assert rows[0]["display_name"] == "Big Week"
        assert rows[1]["display_name"] == "Consistent"

    def test_only_approved_members_appear_in_standings(self, db):
        creator = make_user(db, "cs_approved@example.com")
        pending = make_user(db, "cs_pending@example.com")
        league, season = make_league(db, creator)

        # Add pending member (should not appear in standings).
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=pending.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        rows = calculate_standings(db, league, season)
        user_ids = [str(r["user_id"]) for r in rows]
        assert str(creator.id) in user_ids
        assert str(pending.id) not in user_ids
