"""
API integration tests for the playoff system.

Covers:
  POST   /leagues/{id}/playoff/config   — create config (manager only)
  GET    /leagues/{id}/playoff/config   — retrieve config (members only)
  PATCH  /leagues/{id}/playoff/config   — update config; locks structural fields after seeding
  POST   /leagues/{id}/playoff/seed     — manually seed bracket
  GET    /leagues/{id}/playoff/bracket  — full bracket view
  GET    /leagues/{id}/playoff/pods/{pod_id}/draft  — draft status
  PUT    /leagues/{id}/playoff/pods/{pod_id}/preferences — submit preferences
  POST   /leagues/{id}/playoff/rounds/{id}/resolve — resolve draft to picks
  POST   /leagues/{id}/playoff/rounds/{id}/score   — score round from tournament results
  POST   /leagues/{id}/playoff/rounds/{id}/advance — advance bracket / promote winners
  POST   /leagues/{id}/playoff/override            — manual pod winner override

All tests use the real PostgreSQL test DB (conftest.py fixtures).
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
    PlayoffConfig,
    PlayoffPick,
    PlayoffPod,
    PlayoffPodMember,
    PlayoffRound,
    Season,
    Tournament,
    TournamentEntry,
    User,
)
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _register(client, email: str, display_name: str = "Player") -> str:
    """Register a user and return their access token."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": display_name},
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_user(db: Session, email: str, display_name: str = "Player") -> User:
    user = User(email=email, password_hash=hash_password("password123"), display_name=display_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(client, email: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200, resp.json()
    return _headers(resp.json()["access_token"])


def _make_league(db: Session, manager: User) -> tuple[League, Season]:
    league = League(name="Playoff League", created_by=manager.id)
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=manager.id,
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


def _add_member(db: Session, league: League, user: User) -> None:
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=user.id,
            role=LeagueMemberRole.MEMBER.value,
            status=LeagueMemberStatus.APPROVED.value,
        )
    )
    db.commit()


def _make_golfer(db: Session, name: str = "Test Golfer") -> Golfer:
    g = Golfer(pga_tour_id=f"T{uuid.uuid4().hex[:6]}", name=name)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _make_tournament(
    db: Session,
    league: League,
    status: str = "scheduled",
    days_from_now: int = 14,
    multiplier: float = 1.0,
) -> Tournament:
    start = date.today() + timedelta(days=days_from_now)
    if days_from_now < 0:
        start = date.today() - timedelta(days=abs(days_from_now))
    t = Tournament(
        pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
        name=f"Tournament {uuid.uuid4().hex[:4]}",
        start_date=start,
        end_date=start + timedelta(days=3),
        status=status,
        multiplier=multiplier,
    )
    db.add(t)
    db.flush()
    db.add(LeagueTournament(league_id=league.id, tournament_id=t.id))
    db.commit()
    db.refresh(t)
    return t


def _make_entry(
    db: Session, tournament: Tournament, golfer: Golfer, earnings_usd: float | None = None
) -> TournamentEntry:
    entry = TournamentEntry(
        tournament_id=tournament.id, golfer_id=golfer.id, earnings_usd=earnings_usd
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# Playoff Config endpoints
# ---------------------------------------------------------------------------


class TestPlayoffConfigCreate:
    def test_manager_creates_config_successfully(self, client, db):
        """Happy path: manager creates a playoff config for their league."""
        manager = _make_user(db, "mgr_ccs@test.com")
        league, season = _make_league(db, manager)
        # Need at least 2 members for playoff_size=2, and 1 scheduled future tournament
        member = _make_user(db, "m_ccs@test.com")
        _add_member(db, league, member)
        _make_tournament(db, league, status="scheduled", days_from_now=14)

        headers = _login(client, "mgr_ccs@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"playoff_size": 2, "draft_style": "snake", "picks_per_round": [1]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["playoff_size"] == 2
        assert data["draft_style"] == "snake"
        assert data["status"] == "pending"

    def test_duplicate_config_returns_409(self, client, db):
        """Creating a second config for the same league/season returns 409."""
        manager = _make_user(db, "mgr_dup@test.com")
        league, season = _make_league(db, manager)
        member = _make_user(db, "m_dup@test.com")
        _add_member(db, league, member)
        _make_tournament(db, league, status="scheduled", days_from_now=14)

        headers = _login(client, "mgr_dup@test.com")
        client.post(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"playoff_size": 2, "picks_per_round": [1]},
        )
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"playoff_size": 2, "picks_per_round": [1]},
        )
        assert resp.status_code == 409

    def test_invalid_playoff_size_returns_422(self, client, db):
        """Non-power-of-2 playoff_size fails Pydantic validation."""
        manager = _make_user(db, "mgr_ips@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_ips@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"playoff_size": 5, "picks_per_round": [1]},  # 5 is not valid
        )
        assert resp.status_code == 422

    def test_playoff_size_exceeds_member_count_returns_422(self, client, db):
        """Trying to create a bracket larger than the member count returns 422."""
        manager = _make_user(db, "mgr_psmc@test.com")
        league, _ = _make_league(db, manager)
        # Only 1 member (the manager); cannot create a 4-player bracket
        headers = _login(client, "mgr_psmc@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"playoff_size": 4, "picks_per_round": [1]},
        )
        assert resp.status_code == 422
        assert "member" in resp.json()["detail"].lower()

    def test_not_enough_schedule_for_bracket_returns_422(self, client, db):
        """If the schedule lacks enough future tournaments, creation returns 422."""
        manager = _make_user(db, "mgr_nes@test.com")
        league, _ = _make_league(db, manager)
        for i in range(3):
            _make_user(db, f"m_nes_{i}@test.com")
        members = [_make_user(db, f"mm_nes_{i}@test.com") for i in range(3)]
        for m in members:
            _add_member(db, league, m)
        # No scheduled future tournaments at all
        headers = _login(client, "mgr_nes@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"playoff_size": 4, "picks_per_round": [1, 1]},  # needs 2 scheduled tournaments
        )
        assert resp.status_code == 422
        assert (
            "schedule" in resp.json()["detail"].lower()
            or "tournament" in resp.json()["detail"].lower()
        )

    def test_non_manager_returns_403(self, client, db):
        """A regular member cannot create a playoff config."""
        manager = _make_user(db, "mgr_nm@test.com")
        league, _ = _make_league(db, manager)
        member = _make_user(db, "m_nm@test.com")
        _add_member(db, league, member)
        headers = _login(client, "m_nm@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"playoff_size": 2, "picks_per_round": [1]},
        )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client, db):
        manager = _make_user(db, "mgr_ua@test.com")
        league, _ = _make_league(db, manager)
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/config",
            json={"playoff_size": 2, "picks_per_round": [1]},
        )
        assert resp.status_code == 401


class TestPlayoffConfigGet:
    def test_member_can_retrieve_config(self, client, db):
        """Any league member can GET the playoff config."""
        manager = _make_user(db, "mgr_get@test.com")
        league, season = _make_league(db, manager)
        member = _make_user(db, "m_get@test.com")
        _add_member(db, league, member)
        # Create config directly in DB
        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=2,
                draft_style="linear",
                picks_per_round=[1],
            )
        )
        db.commit()

        member_headers = _login(client, "m_get@test.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/config", headers=member_headers)
        assert resp.status_code == 200
        assert resp.json()["playoff_size"] == 2
        assert resp.json()["draft_style"] == "linear"

    def test_nonmember_returns_403(self, client, db):
        manager = _make_user(db, "mgr_ng@test.com")
        league, season = _make_league(db, manager)
        _make_user(db, "out_ng@test.com")
        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=2,
                draft_style="snake",
                picks_per_round=[1],
            )
        )
        db.commit()
        outsider_headers = _login(client, "out_ng@test.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/config", headers=outsider_headers)
        assert resp.status_code == 403


class TestPlayoffConfigUpdate:
    def _create_config(self, client, db, manager_email, size=2, picks=None):
        manager = _make_user(db, manager_email)
        league, season = _make_league(db, manager)
        member = _make_user(db, f"member_{uuid.uuid4().hex[:4]}@test.com")
        _add_member(db, league, member)
        _make_tournament(db, league, status="scheduled", days_from_now=14)
        headers = _login(client, manager_email)
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"playoff_size": size, "picks_per_round": picks or [1]},
        )
        assert resp.status_code == 201, resp.json()
        return league, season, headers

    def test_patch_pending_config_updates_all_fields(self, client, db):
        """Before seeding, all config fields can be updated freely."""
        league, season, headers = self._create_config(client, db, "mgr_pend@test.com")
        # Add another future tournament to allow draft_style changes
        _make_tournament(db, league, status="scheduled", days_from_now=21)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"draft_style": "linear", "picks_per_round": [2]},
        )
        assert resp.status_code == 200
        assert resp.json()["draft_style"] == "linear"
        assert resp.json()["picks_per_round"] == [2]

    def test_patch_playoff_size_after_seeding_returns_422(self, client, db):
        """Once the bracket is seeded, changing playoff_size is blocked."""
        manager = _make_user(db, "mgr_psa@test.com")
        league, season = _make_league(db, manager)
        member = _make_user(db, "m_psa@test.com")
        _add_member(db, league, member)
        _make_tournament(db, league, status="scheduled", days_from_now=7)

        # Create and seed the config
        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=2,
            draft_style="snake",
            picks_per_round=[1],
            status="active",  # already seeded
        )
        db.add(config)
        db.commit()

        headers = _login(client, "mgr_psa@test.com")
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/config",
            headers=headers,
            json={"playoff_size": 4},  # try to change after seeding
        )
        assert resp.status_code == 422
        assert "playoff_size" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Bracket seeding
# ---------------------------------------------------------------------------


class TestBracketSeeding:
    def _setup_4player_league(self, db, suffix=""):
        """Create a league with 4 approved members and 2 scheduled future tournaments."""
        manager = _make_user(db, f"mgr_seed{suffix}@test.com")
        league, season = _make_league(db, manager)
        members = [_make_user(db, f"m{i}_seed{suffix}@test.com") for i in range(3)]
        for m in members:
            _add_member(db, league, m)
        t1 = _make_tournament(db, league, status="scheduled", days_from_now=7)
        t2 = _make_tournament(db, league, status="scheduled", days_from_now=14)
        return manager, league, season, members, [t1, t2]

    def test_seed_creates_correct_bracket_structure(self, client, db):
        """4-player bracket: 2 rounds, 2 pods in round 1, each with 2 members."""
        manager, league, season, members, tournaments = self._setup_4player_league(db, suffix="1")
        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=4,
                draft_style="snake",
                picks_per_round=[1, 1],
            )
        )
        db.commit()

        headers = _login(client, "mgr_seed1@test.com")
        resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=headers)
        assert resp.status_code == 200

        data = resp.json()
        assert data["playoff_config"]["status"] == "active"
        rounds = data["rounds"]
        assert len(rounds) == 2, "4-player bracket needs 2 rounds (log2(4)=2)"

        r1 = next(r for r in rounds if r["round_number"] == 1)
        assert len(r1["pods"]) == 2, "Round 1 should have 2 pods for 4 players"
        for pod in r1["pods"]:
            assert len(pod["members"]) == 2, "Each pod should have exactly 2 members"

    def test_seed_already_seeded_returns_422(self, client, db):
        """Seeding a bracket that is already seeded returns 422."""
        manager, league, season, _, _ = self._setup_4player_league(db, suffix="2")
        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=4,
            draft_style="snake",
            picks_per_round=[1, 1],
            status="active",  # already seeded
        )
        db.add(config)
        db.commit()
        # Add a dummy round so the seeding guard fires
        db.add(PlayoffRound(playoff_config_id=config.id, round_number=1, status="drafting"))
        db.commit()

        headers = _login(client, "mgr_seed2@test.com")
        resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=headers)
        assert resp.status_code == 422
        assert "already seeded" in resp.json()["detail"].lower()

    def test_seed_not_enough_members_returns_422(self, client, db):
        """Seeding fails with 422 if standings have fewer members than playoff_size."""
        manager = _make_user(db, "mgr_nem@test.com")
        league, season = _make_league(db, manager)
        # Only 1 member (manager) — not enough for a 4-player bracket
        _make_tournament(db, league, status="scheduled", days_from_now=7)
        _make_tournament(db, league, status="scheduled", days_from_now=14)
        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=4,
            draft_style="snake",
            picks_per_round=[1, 1],
        )
        db.add(config)
        db.commit()

        headers = _login(client, "mgr_nem@test.com")
        resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=headers)
        assert resp.status_code == 422
        assert "enough" in resp.json()["detail"].lower()

    def test_top_seed_placed_in_pod_1(self, client, db):
        """The #1 seed (highest scorer) should be placed in bracket_position=1."""
        manager, league, season, members, tournaments = self._setup_4player_league(db, suffix="3")
        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=4,
            draft_style="snake",
            picks_per_round=[1, 1],
        )
        db.add(config)
        db.commit()

        headers = _login(client, "mgr_seed3@test.com")
        resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=headers)
        assert resp.status_code == 200

        r1 = next(r for r in resp.json()["rounds"] if r["round_number"] == 1)
        pod1 = next(p for p in r1["pods"] if p["bracket_position"] == 1)
        seeds_in_pod1 = [m["seed"] for m in pod1["members"]]
        # Seed 1 should always be in pod 1 (standard bracket seeding)
        assert 1 in seeds_in_pod1


# ---------------------------------------------------------------------------
# Full lifecycle integration test
# ---------------------------------------------------------------------------


class TestPlayoffLifecycle:
    """
    Smoke-test the complete playoff round lifecycle:
    config → seed → preferences → resolve → score → advance
    """

    def test_full_two_player_round_lifecycle(self, client, db):
        """
        End-to-end flow for a 2-player playoff:
        1. Create config (playoff_size=2, 1 pick per round, 1 round)
        2. Seed bracket
        3. Both players submit preferences
        4. Manager resolves draft (tournament in_progress)
        5. Manager scores round (tournament completed)
        6. Manager advances bracket (marks winner)
        """
        # Setup: 2 users, 1 league, 1 scheduled future tournament
        manager = _make_user(db, "mgr_lc@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "player_lc@test.com")
        _add_member(db, league, player)

        tournament = _make_tournament(db, league, status="scheduled", days_from_now=7)
        golfer_1 = _make_golfer(db, "Top Golfer")
        golfer_2 = _make_golfer(db, "Second Golfer")

        # Create config and seed
        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=2,
                draft_style="snake",
                picks_per_round=[1],
            )
        )
        db.commit()

        mgr_headers = _login(client, "mgr_lc@test.com")
        player_headers = _login(client, "player_lc@test.com")

        # Step 1: Seed the bracket
        seed_resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=mgr_headers)
        assert seed_resp.status_code == 200, seed_resp.json()
        r1_data = seed_resp.json()["rounds"][0]
        assert len(r1_data["pods"]) == 1
        pod_id = r1_data["pods"][0]["id"]
        round_id = r1_data["id"]

        # Step 2: Add golfers to field; both players submit preferences
        _make_entry(db, tournament, golfer_1)
        _make_entry(db, tournament, golfer_2)

        # 2 players × 1 pick = 2 preferences required
        mgr_pref = client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=mgr_headers,
            json={"golfer_ids": [str(golfer_1.id), str(golfer_2.id)]},
        )
        assert mgr_pref.status_code == 200, mgr_pref.json()

        player_pref = client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=player_headers,
            json={"golfer_ids": [str(golfer_1.id), str(golfer_2.id)]},
        )
        assert player_pref.status_code == 200, player_pref.json()

        # Step 3: Set tournament to in_progress so manager can resolve
        tournament.status = "in_progress"
        db.commit()

        resolve_resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/{round_id}/resolve",
            headers=mgr_headers,
        )
        assert resolve_resp.status_code == 200, resolve_resp.json()
        assert resolve_resp.json()["status"] == "locked"

        # Verify 2 picks were created (1 per player)
        picks = db.query(PlayoffPick).filter_by(pod_id=pod_id).all()
        assert len(picks) == 2

        # Step 4: Complete the tournament and publish earnings
        tournament.status = "completed"
        db.commit()

        # Set specific earnings on the golfers' tournament entries
        entry_1 = (
            db.query(TournamentEntry)
            .filter_by(tournament_id=tournament.id, golfer_id=golfer_1.id)
            .first()
        )
        entry_2 = (
            db.query(TournamentEntry)
            .filter_by(tournament_id=tournament.id, golfer_id=golfer_2.id)
            .first()
        )
        entry_1.earnings_usd = 200_000
        entry_2.earnings_usd = 100_000
        db.commit()

        score_resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/{round_id}/score",
            headers=mgr_headers,
        )
        assert score_resp.status_code == 200, score_resp.json()

        # Step 5: Advance bracket — determines winner
        advance_resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/{round_id}/advance",
            headers=mgr_headers,
        )
        assert advance_resp.status_code == 200, advance_resp.json()

        # Verify the pod is completed with a winner
        pod = db.query(PlayoffPod).filter_by(id=pod_id).first()
        assert pod.status == "completed"
        assert pod.winner_user_id is not None


# ---------------------------------------------------------------------------
# Draft status and preferences
# ---------------------------------------------------------------------------


class TestDraftStatus:
    def test_draft_status_shows_has_submitted_flag(self, client, db):
        """GET /pods/{id}/draft shows has_submitted=True once preferences are submitted."""
        manager = _make_user(db, "mgr_ds@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_ds@test.com")
        _add_member(db, league, player)
        tournament = _make_tournament(db, league, status="scheduled", days_from_now=7)
        golfer_1 = _make_golfer(db, "GolferOne DS")
        golfer_2 = _make_golfer(db, "GolferTwo DS")
        _make_entry(db, tournament, golfer_1)
        _make_entry(db, tournament, golfer_2)

        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=2,
                draft_style="snake",
                picks_per_round=[1],
            )
        )
        db.commit()

        mgr_headers = _login(client, "mgr_ds@test.com")
        seed_resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=mgr_headers)
        pod_id = seed_resp.json()["rounds"][0]["pods"][0]["id"]

        # Before submission: has_submitted=False
        status_before = client.get(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/draft",
            headers=mgr_headers,
        )
        assert status_before.status_code == 200
        mgr_entry = next(
            m for m in status_before.json()["members"] if m["display_name"] == "Player"
        )
        assert mgr_entry["has_submitted"] is False

        # Manager submits preferences (2 golfers = 2 players × 1 pick)
        client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=mgr_headers,
            json={"golfer_ids": [str(golfer_1.id), str(golfer_2.id)]},
        )

        # After submission: has_submitted=True
        status_after = client.get(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/draft",
            headers=mgr_headers,
        )
        mgr_entry_after = next(
            m for m in status_after.json()["members"] if m["display_name"] == "Player"
        )
        assert mgr_entry_after["has_submitted"] is True
        assert mgr_entry_after["preference_count"] == 2


class TestPreferenceSubmission:
    def test_wrong_count_returns_422(self, client, db):
        """Submitting the wrong number of preferences returns 422."""
        manager = _make_user(db, "mgr_wc@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_wc@test.com")
        _add_member(db, league, player)
        _make_tournament(db, league, status="scheduled", days_from_now=7)

        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=2,
                draft_style="snake",
                picks_per_round=[1],
            )
        )
        db.commit()

        headers = _login(client, "mgr_wc@test.com")
        seed_resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=headers)
        pod_id = seed_resp.json()["rounds"][0]["pods"][0]["id"]

        # 2 players × 1 pick = 2 required; submitting only 1
        resp = client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=headers,
            json={"golfer_ids": [str(uuid.uuid4())]},
        )
        assert resp.status_code == 422
        assert "rank exactly" in resp.json()["detail"].lower()

    def test_duplicate_golfer_ids_returns_422(self, client, db):
        """Submitting duplicate golfer IDs in the preference list returns 422."""
        manager = _make_user(db, "mgr_dgi@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_dgi@test.com")
        _add_member(db, league, player)
        _make_tournament(db, league, status="scheduled", days_from_now=7)

        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=2,
                draft_style="snake",
                picks_per_round=[1],
            )
        )
        db.commit()

        headers = _login(client, "mgr_dgi@test.com")
        seed_resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=headers)
        pod_id = seed_resp.json()["rounds"][0]["pods"][0]["id"]

        same_id = str(uuid.uuid4())
        resp = client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=headers,
            json={"golfer_ids": [same_id, same_id]},  # same golfer listed twice
        )
        assert resp.status_code == 422
        assert "duplicate" in resp.json()["detail"].lower()

    def test_non_pod_member_returns_403(self, client, db):
        """A user who is not in the pod cannot submit preferences."""
        manager = _make_user(db, "mgr_npm@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_npm@test.com")
        outsider = _make_user(db, "out_npm@test.com")
        _add_member(db, league, player)
        _add_member(db, league, outsider)
        _make_tournament(db, league, status="scheduled", days_from_now=7)

        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=2,
                draft_style="snake",
                picks_per_round=[1],
            )
        )
        db.commit()

        mgr_headers = _login(client, "mgr_npm@test.com")
        seed_resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=mgr_headers)
        pod_id = seed_resp.json()["rounds"][0]["pods"][0]["id"]

        # Outsider is a league member but not in this pod
        # (outsider wasn't in the top 2 standings)
        outsider_headers = _login(client, "out_npm@test.com")
        resp = client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=outsider_headers,
            json={"golfer_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Manual result override
# ---------------------------------------------------------------------------


class TestManualOverride:
    def test_manager_can_override_pod_winner(self, client, db):
        """Manager can manually set pod winner regardless of total_points."""
        manager = _make_user(db, "mgr_mo@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_mo@test.com")
        _add_member(db, league, player)
        tournament = _make_tournament(db, league, status="completed", days_from_now=-7)

        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            is_enabled=True,
            playoff_size=2,
            draft_style="snake",
            picks_per_round=[1],
            status="active",
        )
        db.add(config)
        db.commit()

        # Create scored pod manually
        round_obj = PlayoffRound(
            playoff_config_id=config.id,
            round_number=1,
            tournament_id=tournament.id,
            status="locked",
        )
        db.add(round_obj)
        db.commit()
        pod = PlayoffPod(playoff_round_id=round_obj.id, bracket_position=1, status="locked")
        db.add(pod)
        db.commit()
        mgr_member = PlayoffPodMember(
            pod_id=pod.id,
            user_id=manager.id,
            seed=1,
            draft_position=1,
            total_points=50_000,
        )
        player_member = PlayoffPodMember(
            pod_id=pod.id,
            user_id=player.id,
            seed=2,
            draft_position=2,
            total_points=200_000,  # player has higher score
        )
        db.add_all([mgr_member, player_member])
        db.commit()

        # Manager overrides to themselves despite lower score
        mgr_headers = _login(client, "mgr_mo@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/override",
            headers=mgr_headers,
            json={"pod_id": pod.id, "winner_user_id": str(manager.id)},
        )
        assert resp.status_code == 200

        db.refresh(pod)
        assert pod.winner_user_id == manager.id

    def test_non_manager_cannot_override(self, client, db):
        """A regular member cannot use the override endpoint."""
        manager = _make_user(db, "mgr_nmo@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_nmo@test.com")
        _add_member(db, league, player)

        player_headers = _login(client, "p_nmo@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/override",
            headers=player_headers,
            json={"pod_id": 999, "winner_user_id": str(player.id)},
        )
        assert resp.status_code == 403
