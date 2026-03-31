"""
Tests for GET /users/me/league-summaries — the batch endpoint that powers
the Leagues page cards.

Covers: standings rank/tie detection, current tournament resolution,
pick status, pick window logic, and playoff context.
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
    PlayoffConfig,
    PlayoffPod,
    PlayoffPodMember,
    PlayoffRound,
    Season,
    Tournament,
    TournamentEntry,
    TournamentStatus,
    User,
)
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db: Session, email: str, display_name: str = "Player") -> User:
    user = User(email=email, password_hash=hash_password("password123"), display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_league(db: Session, creator: User, name: str = "Test League") -> tuple[League, Season]:
    league = League(name=name, created_by=creator.id)
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


def _login_headers(client, email: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _register_and_login(client, email: str, display_name: str = "Player") -> dict:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "password123",
            "display_name": display_name,
            "first_name": "Test",
            "last_name": "User",
        },
    )
    return _login_headers(client, email)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLeagueSummaries:
    """GET /users/me/league-summaries"""

    def test_empty_when_no_leagues(self, client, auth_headers):
        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_league_with_basic_fields(self, client, auth_headers, db):
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = _make_league(db, user)

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["league_id"] == str(league.id)
        assert data[0]["league_name"] == "Test League"
        assert data[0]["is_manager"] is True
        assert data[0]["member_count"] >= 1

    def test_rank_and_points_with_completed_tournament(self, client, auth_headers, db):
        """After a completed tournament with a scored pick, rank and points should be populated."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = _make_league(db, user)

        start = date(date.today().year, 1, 6)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Past Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.COMPLETED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))

        golfer = Golfer(pga_tour_id=f"G{uuid.uuid4().hex[:6]}", name="Tiger Woods")
        db.add(golfer)
        db.flush()
        db.add(TournamentEntry(tournament_id=t.id, golfer_id=golfer.id, earnings_usd=500_000))
        db.add(
            Pick(
                league_id=league.id,
                season_id=season.id,
                user_id=user.id,
                tournament_id=t.id,
                golfer_id=golfer.id,
                points_earned=500_000,
            )
        )
        db.commit()

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        data = resp.json()
        assert len(data) == 1
        assert data[0]["rank"] == 1
        assert data[0]["total_points"] == 500_000
        assert data[0]["is_tied"] is False

    def test_current_tournament_in_progress(self, client, auth_headers, db):
        """An in_progress tournament should appear as current_tournament."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = _make_league(db, user)

        start = date.today()
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Live Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.IN_PROGRESS.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
        db.commit()

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        data = resp.json()
        ct = data[0]["current_tournament"]
        assert ct is not None
        assert ct["name"] == "Live Open"
        assert ct["status"] == "in_progress"

    def test_current_tournament_scheduled(self, client, auth_headers, db):
        """A scheduled tournament should appear as current_tournament if no in_progress exists."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = _make_league(db, user)

        start = date.today() + timedelta(days=7)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Future Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
        db.commit()

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        data = resp.json()
        ct = data[0]["current_tournament"]
        assert ct is not None
        assert ct["name"] == "Future Open"
        assert ct["status"] == "scheduled"

    def test_no_current_tournament_when_all_completed(self, client, auth_headers, db):
        """If all tournaments are completed, current_tournament is null."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = _make_league(db, user)

        start = date(date.today().year, 1, 6)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Done Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.COMPLETED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
        db.commit()

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        data = resp.json()
        assert data[0]["current_tournament"] is None

    def test_my_pick_populated(self, client, auth_headers, db):
        """If user has a pick for the current tournament, my_pick is populated."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = _make_league(db, user)

        start = date.today() + timedelta(days=7)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Pick Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))

        golfer = Golfer(pga_tour_id=f"G{uuid.uuid4().hex[:6]}", name="Rory McIlroy")
        db.add(golfer)
        db.flush()
        db.add(
            Pick(
                league_id=league.id,
                season_id=season.id,
                user_id=user.id,
                tournament_id=t.id,
                golfer_id=golfer.id,
            )
        )
        db.commit()

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        data = resp.json()
        assert data[0]["my_pick"] is not None
        assert data[0]["my_pick"]["golfer_name"] == "Rory McIlroy"

    def test_member_sees_manager_false(self, client, db):
        """A regular member should see is_manager=False."""
        creator = _make_user(db, "sum_creator@test.com", "Creator")
        league, season = _make_league(db, creator)

        headers = _register_and_login(client, "sum_member@test.com", "Member")
        member = db.query(User).filter_by(email="sum_member@test.com").first()
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        resp = client.get("/api/v1/users/me/league-summaries", headers=headers)
        data = resp.json()
        assert len(data) == 1
        assert data[0]["is_manager"] is False

    def test_tied_rank_detected(self, client, db):
        """Two members with the same points should both show is_tied=True."""
        creator = _make_user(db, "tie_creator@test.com", "Creator")
        league, season = _make_league(db, creator)

        member = _make_user(db, "tie_member@test.com", "Member")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )

        start = date(date.today().year, 1, 6)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Tie Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.COMPLETED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))

        golfer_a = Golfer(pga_tour_id=f"G{uuid.uuid4().hex[:6]}", name="GolferA")
        golfer_b = Golfer(pga_tour_id=f"G{uuid.uuid4().hex[:6]}", name="GolferB")
        db.add_all([golfer_a, golfer_b])
        db.flush()
        db.add(TournamentEntry(tournament_id=t.id, golfer_id=golfer_a.id, earnings_usd=100_000))
        db.add(TournamentEntry(tournament_id=t.id, golfer_id=golfer_b.id, earnings_usd=100_000))

        # Both members earn the same points
        db.add(
            Pick(
                league_id=league.id,
                season_id=season.id,
                user_id=creator.id,
                tournament_id=t.id,
                golfer_id=golfer_a.id,
                points_earned=100_000,
            )
        )
        db.add(
            Pick(
                league_id=league.id,
                season_id=season.id,
                user_id=member.id,
                tournament_id=t.id,
                golfer_id=golfer_b.id,
                points_earned=100_000,
            )
        )
        db.commit()

        headers = _login_headers(client, "tie_creator@test.com")
        resp = client.get("/api/v1/users/me/league-summaries", headers=headers)
        data = resp.json()
        assert data[0]["is_tied"] is True
        assert data[0]["rank"] == 1

    def test_multiple_leagues_returned(self, client, auth_headers, db):
        """A user in multiple leagues sees all of them."""
        user = db.query(User).filter_by(email="test@example.com").first()
        _make_league(db, user, name="League One")
        _make_league(db, user, name="League Two")

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        data = resp.json()
        names = {d["league_name"] for d in data}
        assert "League One" in names
        assert "League Two" in names

    def test_effective_multiplier_on_current_tournament(self, client, auth_headers, db):
        """The current tournament should include effective_multiplier from league_tournaments."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = _make_league(db, user)

        start = date.today() + timedelta(days=7)
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Major Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id, multiplier=2.0))
        db.commit()

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        ct = resp.json()[0]["current_tournament"]
        assert ct["effective_multiplier"] == 2.0

    def test_playoff_context_populated(self, client, auth_headers, db):
        """League with active playoff round should populate is_playoff_week and related fields."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = _make_league(db, user)

        # Create an in-progress tournament that's a playoff round
        start = date.today()
        t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Playoff Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.IN_PROGRESS.value,
        )
        db.add(t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))

        # Create playoff config and round
        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=4,
            draft_style="snake",
            picks_per_round=[1],
            status="active",
        )
        db.add(config)
        db.flush()

        round_obj = PlayoffRound(
            playoff_config_id=config.id,
            round_number=1,
            tournament_id=t.id,
            status="drafting",
        )
        db.add(round_obj)
        db.flush()

        # Create pod with user as member
        pod = PlayoffPod(playoff_round_id=round_obj.id, bracket_position=1, status="drafting")
        db.add(pod)
        db.flush()
        db.add(PlayoffPodMember(pod_id=pod.id, user_id=user.id, seed=1, draft_position=1))
        db.commit()

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        data = resp.json()
        assert data[0]["is_playoff_week"] is True
        assert data[0]["is_in_playoffs"] is True

    def test_preceding_tournament_shown_when_pick_window_closed(self, client, auth_headers, db):
        """When pick window is closed due to a preceding global tournament,
        preceding_tournament_name should be populated."""
        user = db.query(User).filter_by(email="test@example.com").first()
        league, season = _make_league(db, user)

        # Create a globally in-progress tournament (not in this league)
        global_ip = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="Global Live",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=3),
            status=TournamentStatus.IN_PROGRESS.value,
        )
        db.add(global_ip)
        db.flush()

        # Create a scheduled tournament in this league (next week)
        start = date.today() + timedelta(days=7)
        league_t = Tournament(
            pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
            name="League Future",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(league_t)
        db.flush()
        db.add(LeagueTournament(league_id=league.id, tournament_id=league_t.id))
        db.commit()

        resp = client.get("/api/v1/users/me/league-summaries", headers=auth_headers)
        data = resp.json()
        assert data[0]["pick_window_open"] is False
        # The preceding tournament name should be populated
        assert data[0]["preceding_tournament_name"] is not None
