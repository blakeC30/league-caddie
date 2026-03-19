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
        manager = _make_user(db, "mgr_ds@test.com", display_name="Manager DS")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_ds@test.com", display_name="Player DS")
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
            m for m in status_before.json()["members"] if m["display_name"] == "Manager DS"
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
            m for m in status_after.json()["members"] if m["display_name"] == "Manager DS"
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
        # outsider is added AFTER seeding so they are definitely not in the pod
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

        # Add outsider to the league after seeding — they're a league member but not in this pod
        _add_member(db, league, outsider)

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


# ---------------------------------------------------------------------------
# Shared seeded-league setup helper (used by many cross-league test classes)
# ---------------------------------------------------------------------------


def _setup_seeded_league(db, client, suffix=""):
    """
    Create a 2-player league, add playoff config, seed the bracket.

    Returns:
        (league, season, manager, player, tournament, golfer1, golfer2,
         mgr_headers, round_id, pod_id)
    """
    manager = _make_user(db, f"mgr_sl{suffix}@test.com", display_name=f"Manager{suffix}")
    league, season = _make_league(db, manager)
    player = _make_user(db, f"player_sl{suffix}@test.com", display_name=f"Player{suffix}")
    _add_member(db, league, player)

    tournament = _make_tournament(db, league, status="scheduled", days_from_now=7)
    golfer1 = _make_golfer(db, f"Golfer One {suffix}")
    golfer2 = _make_golfer(db, f"Golfer Two {suffix}")
    _make_entry(db, tournament, golfer1)
    _make_entry(db, tournament, golfer2)

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

    mgr_headers = _login(client, f"mgr_sl{suffix}@test.com")
    seed_resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=mgr_headers)
    assert seed_resp.status_code == 200, seed_resp.json()

    round_id = seed_resp.json()["rounds"][0]["id"]
    pod_id = seed_resp.json()["rounds"][0]["pods"][0]["id"]

    return (
        league,
        season,
        manager,
        player,
        tournament,
        golfer1,
        golfer2,
        mgr_headers,
        round_id,
        pod_id,
    )


# ---------------------------------------------------------------------------
# TestBracketGet — GET /bracket paths
# ---------------------------------------------------------------------------


class TestBracketGet:
    def test_no_config_returns_404(self, client, db):
        """GET /bracket returns 404 when no playoff config exists for the season."""
        manager = _make_user(db, "mgr_bg404@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_bg404@test.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/bracket", headers=headers)
        assert resp.status_code == 404

    def test_bracket_returns_rounds_after_seeding(self, client, db):
        """GET /bracket returns a populated BracketOut after seeding."""
        league, season, manager, player, tournament, g1, g2, mgr_headers, round_id, pod_id = (
            _setup_seeded_league(db, client, suffix="_bg")
        )

        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/bracket", headers=mgr_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["playoff_config"]["status"] == "active"
        assert len(data["rounds"]) == 1
        assert len(data["rounds"][0]["pods"]) == 1

    def test_bracket_pending_config_no_autoseed_conditions(self, client, db):
        """
        GET /bracket with pending config where autoseed conditions are not met
        returns an empty rounds list (not 422).
        """
        manager = _make_user(db, "mgr_bgpend@test.com")
        league, season = _make_league(db, manager)
        member = _make_user(db, "p_bgpend@test.com")
        _add_member(db, league, member)
        # Two scheduled tournaments — regular season is not done yet (too many scheduled)
        _make_tournament(db, league, status="scheduled", days_from_now=7)
        _make_tournament(db, league, status="scheduled", days_from_now=14)
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

        headers = _login(client, "mgr_bgpend@test.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/bracket", headers=headers)
        # Should succeed with empty rounds (not yet seeded, conditions not met)
        assert resp.status_code == 200
        assert resp.json()["rounds"] == []


# ---------------------------------------------------------------------------
# TestCrossLeagueChecks — 403 when round/pod belongs to a different league
# ---------------------------------------------------------------------------


class TestCrossLeagueChecks:
    """
    Create two independent seeded leagues (A and B).
    Manager of league A calls endpoints using league A's ID but league B's round/pod IDs.
    All should return 403.
    """

    def _setup_two_leagues(self, db, client):
        """Return (league_a, mgr_a_headers, league_b, round_b_id, pod_b_id)."""
        (
            league_a,
            _,
            manager_a,
            _,
            _,
            _,
            _,
            mgr_a_headers,
            _,
            _,
        ) = _setup_seeded_league(db, client, suffix="_cla")
        (
            league_b,
            _,
            _,
            _,
            _,
            _,
            _,
            _,
            round_b_id,
            pod_b_id,
        ) = _setup_seeded_league(db, client, suffix="_clb")
        return league_a, mgr_a_headers, league_b, round_b_id, pod_b_id

    def test_assign_round_cross_league_403(self, client, db):
        """PATCH /rounds/{id} with a round from another league returns 403."""
        import uuid

        league_a, mgr_a_headers, league_b, round_b_id, _ = self._setup_two_leagues(db, client)
        resp = client.patch(
            f"/api/v1/leagues/{league_a.id}/playoff/rounds/{round_b_id}",
            headers=mgr_a_headers,
            json={"tournament_id": str(uuid.uuid4()), "draft_opens_at": None},
        )
        assert resp.status_code == 403

    def test_open_round_cross_league_403(self, client, db):
        """POST /rounds/{id}/open with a round from another league returns 403."""
        league_a, mgr_a_headers, _, round_b_id, _ = self._setup_two_leagues(db, client)
        resp = client.post(
            f"/api/v1/leagues/{league_a.id}/playoff/rounds/{round_b_id}/open",
            headers=mgr_a_headers,
        )
        assert resp.status_code == 403

    def test_resolve_round_cross_league_403(self, client, db):
        """POST /rounds/{id}/resolve with a round from another league returns 403."""
        league_a, mgr_a_headers, _, round_b_id, _ = self._setup_two_leagues(db, client)
        resp = client.post(
            f"/api/v1/leagues/{league_a.id}/playoff/rounds/{round_b_id}/resolve",
            headers=mgr_a_headers,
        )
        assert resp.status_code == 403

    def test_score_round_cross_league_403(self, client, db):
        """POST /rounds/{id}/score with a round from another league returns 403."""
        league_a, mgr_a_headers, _, round_b_id, _ = self._setup_two_leagues(db, client)
        resp = client.post(
            f"/api/v1/leagues/{league_a.id}/playoff/rounds/{round_b_id}/score",
            headers=mgr_a_headers,
        )
        assert resp.status_code == 403

    def test_advance_round_cross_league_403(self, client, db):
        """POST /rounds/{id}/advance with a round from another league returns 403."""
        league_a, mgr_a_headers, _, round_b_id, _ = self._setup_two_leagues(db, client)
        resp = client.post(
            f"/api/v1/leagues/{league_a.id}/playoff/rounds/{round_b_id}/advance",
            headers=mgr_a_headers,
        )
        assert resp.status_code == 403

    def test_pod_detail_cross_league_403(self, client, db):
        """GET /pods/{id} with a pod from another league returns 403."""
        league_a, mgr_a_headers, _, _, pod_b_id = self._setup_two_leagues(db, client)
        resp = client.get(
            f"/api/v1/leagues/{league_a.id}/playoff/pods/{pod_b_id}",
            headers=mgr_a_headers,
        )
        assert resp.status_code == 403

    def test_draft_status_cross_league_403(self, client, db):
        """GET /pods/{id}/draft with a pod from another league returns 403."""
        league_a, mgr_a_headers, _, _, pod_b_id = self._setup_two_leagues(db, client)
        resp = client.get(
            f"/api/v1/leagues/{league_a.id}/playoff/pods/{pod_b_id}/draft",
            headers=mgr_a_headers,
        )
        assert resp.status_code == 403

    def test_get_preferences_cross_league_403(self, client, db):
        """GET /pods/{id}/preferences with a pod from another league returns 403."""
        league_a, mgr_a_headers, _, _, pod_b_id = self._setup_two_leagues(db, client)
        resp = client.get(
            f"/api/v1/leagues/{league_a.id}/playoff/pods/{pod_b_id}/preferences",
            headers=mgr_a_headers,
        )
        assert resp.status_code == 403

    def test_submit_preferences_cross_league_403(self, client, db):
        """PUT /pods/{id}/preferences with a pod from another league returns 403."""
        league_a, mgr_a_headers, _, _, pod_b_id = self._setup_two_leagues(db, client)
        resp = client.put(
            f"/api/v1/leagues/{league_a.id}/playoff/pods/{pod_b_id}/preferences",
            headers=mgr_a_headers,
            json={"golfer_ids": [str(uuid.uuid4())]},
        )
        assert resp.status_code == 403

    def test_override_cross_league_403(self, client, db):
        """POST /override with a pod from another league returns 403."""
        league_a, mgr_a_headers, _, _, pod_b_id = self._setup_two_leagues(db, client)
        resp = client.post(
            f"/api/v1/leagues/{league_a.id}/playoff/override",
            headers=mgr_a_headers,
            json={"pod_id": pod_b_id, "winner_user_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

    def test_admin_pick_cross_league_403(self, client, db):
        """POST /pods/{id}/admin-pick with a pod from another league returns 403."""
        league_a, mgr_a_headers, _, _, pod_b_id = self._setup_two_leagues(db, client)
        resp = client.post(
            f"/api/v1/leagues/{league_a.id}/playoff/pods/{pod_b_id}/admin-pick",
            headers=mgr_a_headers,
            json={
                "user_id": str(uuid.uuid4()),
                "golfer_id": str(uuid.uuid4()),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestPodDetail — GET /pods/{pod_id} edge cases
# ---------------------------------------------------------------------------


class TestPodDetail:
    def test_nonexistent_pod_returns_404(self, client, db):
        """Requesting a pod that does not exist returns 404."""
        manager = _make_user(db, "mgr_pd404@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_pd404@test.com")
        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/pods/99999",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_pod_detail_happy_path(self, client, db):
        """GET /pods/{id} returns pod details for a valid pod in the correct league."""
        (
            league,
            _,
            _,
            _,
            _,
            _,
            _,
            mgr_headers,
            _,
            pod_id,
        ) = _setup_seeded_league(db, client, suffix="_pdhp")

        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}",
            headers=mgr_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == pod_id
        assert len(data["members"]) == 2


# ---------------------------------------------------------------------------
# TestRoundAssignment — PATCH /playoff/rounds/{id}
# ---------------------------------------------------------------------------


class TestRoundAssignment:
    def test_assign_tournament_to_round(self, client, db):
        """Manager can assign a different tournament and draft_opens_at to a round."""
        (
            league,
            _,
            _,
            _,
            tournament,
            _,
            _,
            mgr_headers,
            round_id,
            _,
        ) = _setup_seeded_league(db, client, suffix="_ra")
        # Create a second tournament in the league
        second_t = _make_tournament(db, league, status="scheduled", days_from_now=14)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/rounds/{round_id}",
            headers=mgr_headers,
            json={
                "tournament_id": str(second_t.id),
                "draft_opens_at": None,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["tournament_id"] == str(second_t.id)

    def test_assign_nonexistent_round_returns_404(self, client, db):
        """PATCH /rounds/99999 returns 404 when the round does not exist."""
        import uuid

        manager = _make_user(db, "mgr_ra404@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_ra404@test.com")
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/rounds/99999",
            headers=headers,
            json={"tournament_id": str(uuid.uuid4()), "draft_opens_at": None},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestRoundOpen — POST /playoff/rounds/{id}/open
# ---------------------------------------------------------------------------


class TestRoundOpen:
    def test_open_pending_round_becomes_drafting(self, client, db):
        """Opening a pending round sets its status to 'drafting'."""
        (
            league,
            _,
            _,
            _,
            _,
            _,
            _,
            mgr_headers,
            round_id,
            _,
        ) = _setup_seeded_league(db, client, suffix="_ro")

        # The seeded round starts as "drafting" by default; reset it to pending manually
        round_obj = db.query(PlayoffRound).filter_by(id=round_id).first()
        round_obj.status = "pending"
        db.commit()

        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/{round_id}/open",
            headers=mgr_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "drafting"

    def test_open_already_drafting_round_is_noop(self, client, db):
        """Opening a round already in drafting is a no-op (idempotent)."""
        (
            league,
            _,
            _,
            _,
            _,
            _,
            _,
            mgr_headers,
            round_id,
            _,
        ) = _setup_seeded_league(db, client, suffix="_rono")

        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/{round_id}/open",
            headers=mgr_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "drafting"


# ---------------------------------------------------------------------------
# TestRoundResolve / TestRoundScore / TestRoundAdvance — cross-league 403
# (happy-path for these is covered in TestPlayoffLifecycle)
# ---------------------------------------------------------------------------


class TestRoundResolve:
    def test_resolve_nonexistent_round_returns_404(self, client, db):
        """POST /rounds/99999/resolve returns 404."""
        manager = _make_user(db, "mgr_rr404@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_rr404@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/99999/resolve",
            headers=headers,
        )
        assert resp.status_code == 404


class TestRoundScore:
    def test_score_nonexistent_round_returns_404(self, client, db):
        """POST /rounds/99999/score returns 404."""
        manager = _make_user(db, "mgr_rs404@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_rs404@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/99999/score",
            headers=headers,
        )
        assert resp.status_code == 404


class TestRoundAdvance:
    def test_advance_nonexistent_round_returns_404(self, client, db):
        """POST /rounds/99999/advance returns 404."""
        manager = _make_user(db, "mgr_rva404@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_rva404@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/99999/advance",
            headers=headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestGetDraftStatus — GET /pods/{id}/draft edge cases
# ---------------------------------------------------------------------------


class TestGetDraftStatus:
    def test_nonexistent_pod_returns_404(self, client, db):
        """GET /pods/99999/draft returns 404 when pod does not exist."""
        manager = _make_user(db, "mgr_gds404@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_gds404@test.com")
        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/pods/99999/draft",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_draft_status_shows_deadline_none_before_tee_times(self, client, db):
        """
        Draft status deadline is None when no tee times are stored
        (the backend returns None rather than falling back to start_date midnight).
        """
        (
            league,
            _,
            _,
            _,
            _,
            _,
            _,
            mgr_headers,
            _,
            pod_id,
        ) = _setup_seeded_league(db, client, suffix="_gdsdl")

        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/draft",
            headers=mgr_headers,
        )
        assert resp.status_code == 200
        # No TournamentEntryRound rows exist, so no tee times → deadline is None
        assert resp.json()["deadline"] is None


# ---------------------------------------------------------------------------
# TestGetMyPreferences — GET /pods/{id}/preferences edge cases
# ---------------------------------------------------------------------------


class TestGetMyPreferences:
    def test_not_pod_member_returns_403(self, client, db):
        """GET /pods/{id}/preferences returns 403 if caller is not in the pod."""
        (
            league,
            season,
            manager,
            player,
            tournament,
            golfer1,
            golfer2,
            mgr_headers,
            round_id,
            pod_id,
        ) = _setup_seeded_league(db, client, suffix="_gmpnm")

        # Create a third user who is a league member but NOT in any pod
        outsider = _make_user(db, "outsider_gmpnm@test.com")
        _add_member(db, league, outsider)
        outsider_headers = _login(client, "outsider_gmpnm@test.com")

        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=outsider_headers,
        )
        assert resp.status_code == 403

    def test_returns_preferences_after_submission(self, client, db):
        """GET /pods/{id}/preferences returns the submitted list in rank order."""
        (
            league,
            _,
            _,
            _,
            _,
            golfer1,
            golfer2,
            mgr_headers,
            _,
            pod_id,
        ) = _setup_seeded_league(db, client, suffix="_gmprv")

        # Submit preferences for the manager
        client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=mgr_headers,
            json={"golfer_ids": [str(golfer1.id), str(golfer2.id)]},
        )

        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=mgr_headers,
        )
        assert resp.status_code == 200
        prefs = resp.json()
        assert len(prefs) == 2
        assert prefs[0]["rank"] == 1
        assert prefs[0]["golfer_id"] == str(golfer1.id)
        assert prefs[1]["rank"] == 2
        assert prefs[1]["golfer_id"] == str(golfer2.id)


# ---------------------------------------------------------------------------
# TestSubmitPreferences — PUT /pods/{id}/preferences edge cases
# ---------------------------------------------------------------------------


class TestSubmitPreferences:
    def test_no_tournament_on_round_returns_422(self, client, db):
        """
        Submitting preferences when the round has no tournament assigned returns 422.
        We achieve this by seeding and then clearing the round's tournament_id.
        """
        (
            league,
            _,
            _,
            _,
            _,
            golfer1,
            golfer2,
            mgr_headers,
            round_id,
            pod_id,
        ) = _setup_seeded_league(db, client, suffix="_spnt")

        # Clear the tournament assignment from the round
        round_obj = db.query(PlayoffRound).filter_by(id=round_id).first()
        round_obj.tournament_id = None
        db.commit()

        resp = client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=mgr_headers,
            json={"golfer_ids": [str(golfer1.id), str(golfer2.id)]},
        )
        assert resp.status_code == 422
        assert "no tournament" in resp.json()["detail"].lower()

    def test_non_pod_member_cannot_submit_preferences(self, client, db):
        """PUT /pods/{id}/preferences returns 403 if caller is not in the pod."""
        (
            league,
            _,
            _,
            _,
            _,
            golfer1,
            golfer2,
            _,
            _,
            pod_id,
        ) = _setup_seeded_league(db, client, suffix="_spnm")

        outsider = _make_user(db, "outsider_spnm@test.com")
        _add_member(db, league, outsider)
        outsider_headers = _login(client, "outsider_spnm@test.com")

        resp = client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=outsider_headers,
            json={"golfer_ids": [str(golfer1.id), str(golfer2.id)]},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TestOverrideEdgeCases — POST /playoff/override edge cases
# ---------------------------------------------------------------------------


class TestOverrideEdgeCases:
    def test_nonexistent_pod_returns_404(self, client, db):
        """POST /override with a non-existent pod_id returns 404."""
        manager = _make_user(db, "mgr_ov404@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_ov404@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/override",
            headers=headers,
            json={"pod_id": 99999, "winner_user_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestMyPlayoffPod — GET /leagues/{id}/playoff/my-pod
# ---------------------------------------------------------------------------


class TestMyPlayoffPod:
    def test_no_config_returns_is_playoff_week_false(self, client, db):
        """No playoff config → my-pod returns is_playoff_week=False."""
        manager = _make_user(db, "mgr_mpp_nc@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_mpp_nc@test.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/my-pod", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["is_playoff_week"] is False

    def test_playoff_size_zero_returns_is_playoff_week_false(self, client, db):
        """Config with playoff_size=0 → my-pod returns is_playoff_week=False."""
        manager = _make_user(db, "mgr_mpp_pz@test.com")
        league, season = _make_league(db, manager)
        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=0,
                draft_style="snake",
                picks_per_round=[1],
            )
        )
        db.commit()
        headers = _login(client, "mgr_mpp_pz@test.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/my-pod", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["is_playoff_week"] is False

    def test_no_upcoming_tournament_returns_is_playoff_week_false(self, client, db):
        """Config exists but no scheduled/in_progress tournament → is_playoff_week=False."""
        manager = _make_user(db, "mgr_mpp_nut@test.com")
        league, season = _make_league(db, manager)
        member = _make_user(db, "p_mpp_nut@test.com")
        _add_member(db, league, member)
        # Only completed tournament — no upcoming
        _make_tournament(db, league, status="completed", days_from_now=-7)
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
        headers = _login(client, "mgr_mpp_nut@test.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/my-pod", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["is_playoff_week"] is False

    def test_nearest_tournament_not_playoff_round_returns_false(self, client, db):
        """Nearest tournament is not assigned to any playoff round → is_playoff_week=False."""
        manager = _make_user(db, "mgr_mpp_npp@test.com")
        league, season = _make_league(db, manager)
        member = _make_user(db, "p_mpp_npp@test.com")
        _add_member(db, league, member)
        # Scheduled tournament — but no playoff config or round assigned to it
        _make_tournament(db, league, status="scheduled", days_from_now=7)
        db.add(
            PlayoffConfig(
                league_id=league.id,
                season_id=season.id,
                is_enabled=True,
                playoff_size=2,
                draft_style="snake",
                picks_per_round=[1],
                status="active",
            )
        )
        db.commit()
        # Config exists and is active, but no PlayoffRound points to this tournament
        headers = _login(client, "mgr_mpp_npp@test.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/my-pod", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["is_playoff_week"] is False

    def test_playoff_week_user_not_in_pod(self, client, db):
        """
        Nearest tournament IS a playoff round, but the user has no pod membership.
        Returns is_playoff_week=True, is_in_playoffs=False.
        """
        (
            league,
            season,
            manager,
            player,
            tournament,
            _,
            _,
            mgr_headers,
            round_id,
            _,
        ) = _setup_seeded_league(db, client, suffix="_mpp_notp")

        # Create a third user who is in the league but was not seeded into any pod
        spectator = _make_user(db, "spectator_mpp@test.com")
        _add_member(db, league, spectator)
        spectator_headers = _login(client, "spectator_mpp@test.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/my-pod", headers=spectator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_playoff_week"] is True
        assert data["is_in_playoffs"] is False
        assert data["active_pod_id"] is None

    def test_playoff_week_user_in_pod(self, client, db):
        """
        Nearest tournament is a playoff round and the user is in a pod.
        Returns is_playoff_week=True, is_in_playoffs=True with pod details.
        """
        (
            league,
            _,
            _,
            _,
            _,
            _,
            _,
            mgr_headers,
            _,
            pod_id,
        ) = _setup_seeded_league(db, client, suffix="_mpp_inp")

        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/my-pod", headers=mgr_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_playoff_week"] is True
        assert data["is_in_playoffs"] is True
        assert data["active_pod_id"] == pod_id
        assert data["active_round_number"] == 1
        assert data["picks_per_round"] == 1
        assert data["required_preference_count"] == 2  # 2 members * 1 pick


# ---------------------------------------------------------------------------
# TestMyPlayoffPicks — GET /leagues/{id}/playoff/my-picks
# ---------------------------------------------------------------------------


class TestMyPlayoffPicks:
    def test_no_config_returns_empty_list(self, client, db):
        """No playoff config → my-picks returns an empty list."""
        manager = _make_user(db, "mgr_myp_nc@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_myp_nc@test.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/my-picks", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_picks_after_draft_resolved(self, client, db):
        """After draft is resolved, my-picks returns picks grouped by round."""
        manager = _make_user(db, "mgr_myp_rp@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, "p_myp_rp@test.com")
        _add_member(db, league, player)

        tournament = _make_tournament(db, league, status="scheduled", days_from_now=7)
        golfer1 = _make_golfer(db, "GolferMyPicksA")
        golfer2 = _make_golfer(db, "GolferMyPicksB")
        _make_entry(db, tournament, golfer1)
        _make_entry(db, tournament, golfer2)

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

        mgr_headers = _login(client, "mgr_myp_rp@test.com")
        player_headers = _login(client, "p_myp_rp@test.com")

        seed_resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=mgr_headers)
        assert seed_resp.status_code == 200
        pod_id = seed_resp.json()["rounds"][0]["pods"][0]["id"]
        round_id = seed_resp.json()["rounds"][0]["id"]

        # Both players submit preferences
        client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=mgr_headers,
            json={"golfer_ids": [str(golfer1.id), str(golfer2.id)]},
        )
        client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=player_headers,
            json={"golfer_ids": [str(golfer2.id), str(golfer1.id)]},
        )

        # Set tournament in_progress so resolve is permitted
        tournament.status = "in_progress"
        db.commit()

        resolve_resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/{round_id}/resolve",
            headers=mgr_headers,
        )
        assert resolve_resp.status_code == 200

        # Manager checks their own picks
        resp = client.get(f"/api/v1/leagues/{league.id}/playoff/my-picks", headers=mgr_headers)
        assert resp.status_code == 200
        picks = resp.json()
        assert len(picks) == 1  # 1 round
        assert picks[0]["round_number"] == 1
        assert len(picks[0]["picks"]) == 1  # 1 pick per player


# ---------------------------------------------------------------------------
# TestRevisePlayoffPick — PATCH /leagues/{id}/playoff/picks/{pick_id}
# ---------------------------------------------------------------------------


class TestRevisePlayoffPick:
    def _run_to_picks(self, db, client, suffix=""):
        """Helper: seed, submit prefs, resolve draft.
        Returns (league, tournament, pod_id, picks)."""
        manager = _make_user(db, f"mgr_rpp{suffix}@test.com")
        league, season = _make_league(db, manager)
        player = _make_user(db, f"p_rpp{suffix}@test.com")
        _add_member(db, league, player)

        tournament = _make_tournament(db, league, status="scheduled", days_from_now=7)
        golfer1 = _make_golfer(db, f"Golfer Alpha {suffix}")
        golfer2 = _make_golfer(db, f"Golfer Beta {suffix}")
        golfer3 = _make_golfer(db, f"Golfer Gamma {suffix}")
        _make_entry(db, tournament, golfer1)
        _make_entry(db, tournament, golfer2)
        _make_entry(db, tournament, golfer3)

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

        mgr_headers = _login(client, f"mgr_rpp{suffix}@test.com")
        player_headers = _login(client, f"p_rpp{suffix}@test.com")

        seed_resp = client.post(f"/api/v1/leagues/{league.id}/playoff/seed", headers=mgr_headers)
        pod_id = seed_resp.json()["rounds"][0]["pods"][0]["id"]
        round_id = seed_resp.json()["rounds"][0]["id"]

        client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=mgr_headers,
            json={"golfer_ids": [str(golfer1.id), str(golfer2.id)]},
        )
        client.put(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/preferences",
            headers=player_headers,
            json={"golfer_ids": [str(golfer2.id), str(golfer1.id)]},
        )

        tournament.status = "in_progress"
        db.commit()

        resolve_resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/rounds/{round_id}/resolve",
            headers=mgr_headers,
        )
        assert resolve_resp.status_code == 200

        picks = db.query(PlayoffPick).filter_by(pod_id=pod_id).all()
        return league, tournament, pod_id, picks, golfer1, golfer2, golfer3, mgr_headers, round_id

    def test_pick_not_found_returns_404(self, client, db):
        """PATCH /playoff/picks/{unknown_id} returns 404."""
        manager = _make_user(db, "mgr_rpp404@test.com")
        league, _ = _make_league(db, manager)
        headers = _login(client, "mgr_rpp404@test.com")
        fake_pick_id = str(uuid.uuid4())
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/picks/{fake_pick_id}",
            headers=headers,
            json={"golfer_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_pick_belongs_to_different_league_returns_403(self, client, db):
        """PATCH /picks/{id} from another league using league A's ID returns 403."""
        # League A — just for the endpoint call context
        manager_a = _make_user(db, "mgr_rpp_cla@test.com")
        league_a, _ = _make_league(db, manager_a)
        mgr_a_headers = _login(client, "mgr_rpp_cla@test.com")

        # League B — has a seeded bracket with actual picks
        (
            _,
            _,
            _,
            picks_b,
            _,
            _,
            _,
            _,
            _,
        ) = self._run_to_picks(db, client, suffix="_rppcl")

        pick_b_id = str(picks_b[0].id)
        resp = client.patch(
            f"/api/v1/leagues/{league_a.id}/playoff/picks/{pick_b_id}",
            headers=mgr_a_headers,
            json={"golfer_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

    def test_round_completed_blocks_revision_422(self, client, db):
        """Revising a pick after the round is 'completed' returns 422."""
        (
            league,
            tournament,
            pod_id,
            picks,
            _,
            _,
            golfer3,
            mgr_headers,
            round_id,
        ) = self._run_to_picks(db, client, suffix="_rpprc")

        # Mark the round as completed to simulate advance_bracket having run
        round_obj = db.query(PlayoffRound).filter_by(id=round_id).first()
        round_obj.status = "completed"
        db.commit()

        pick_id = str(picks[0].id)
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/picks/{pick_id}",
            headers=mgr_headers,
            json={"golfer_id": str(golfer3.id)},
        )
        assert resp.status_code == 422
        assert "advanced" in resp.json()["detail"].lower()

    def test_tournament_not_in_progress_blocks_revision_422(self, client, db):
        """Revising a pick when tournament is not in_progress returns 422."""
        (
            league,
            tournament,
            _,
            picks,
            _,
            _,
            golfer3,
            mgr_headers,
            _,
        ) = self._run_to_picks(db, client, suffix="_rppni")

        # Revert tournament to scheduled to simulate early revision attempt
        tournament.status = "completed"
        db.commit()

        pick_id = str(picks[0].id)
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/picks/{pick_id}",
            headers=mgr_headers,
            json={"golfer_id": str(golfer3.id)},
        )
        assert resp.status_code == 422
        assert "in progress" in resp.json()["detail"].lower()

    def test_golfer_not_found_returns_404(self, client, db):
        """Revising a pick with an unknown golfer_id returns 404."""
        (
            league,
            _,
            _,
            picks,
            _,
            _,
            _,
            mgr_headers,
            _,
        ) = self._run_to_picks(db, client, suffix="_rppgf")

        pick_id = str(picks[0].id)
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/picks/{pick_id}",
            headers=mgr_headers,
            json={"golfer_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_same_golfer_already_in_pod_returns_422(self, client, db):
        """Revising to a golfer already picked by another pod member returns 422."""
        (
            league,
            _,
            pod_id,
            picks,
            golfer1,
            golfer2,
            _,
            mgr_headers,
            _,
        ) = self._run_to_picks(db, client, suffix="_rppsg")

        # Find the pick that uses golfer1; try to revise it to golfer2 (already in pod)
        pick_with_g1 = next((p for p in picks if p.golfer_id == golfer1.id), None)
        if pick_with_g1 is None:
            # In snake draft the other member might have gotten golfer1; try the other pick
            pick_with_g1 = picks[0]
            other_golfer = (
                db.query(PlayoffPick)
                .filter(
                    PlayoffPick.pod_id == pod_id,
                    PlayoffPick.id != pick_with_g1.id,
                )
                .first()
            )
            conflicting_golfer_id = other_golfer.golfer_id
        else:
            conflicting_golfer_id = golfer2.id

        pick_id = str(pick_with_g1.id)
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/picks/{pick_id}",
            headers=mgr_headers,
            json={"golfer_id": str(conflicting_golfer_id)},
        )
        assert resp.status_code == 422
        assert "already picked" in resp.json()["detail"].lower()

    def test_successful_revision_changes_golfer_and_resets_points(self, client, db):
        """Successful revision swaps the golfer and nulls out points_earned."""
        (
            league,
            _,
            _,
            picks,
            _,
            _,
            golfer3,
            mgr_headers,
            _,
        ) = self._run_to_picks(db, client, suffix="_rppsuc")

        pick = picks[0]
        # Set a non-null points_earned to verify it gets cleared
        pick.points_earned = 50000.0
        db.commit()

        pick_id = str(pick.id)
        resp = client.patch(
            f"/api/v1/leagues/{league.id}/playoff/picks/{pick_id}",
            headers=mgr_headers,
            json={"golfer_id": str(golfer3.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["golfer_id"] == str(golfer3.id)
        assert data["points_earned"] is None  # reset on revision


# ---------------------------------------------------------------------------
# TestAdminCreatePodPick — POST /leagues/{id}/playoff/pods/{pod_id}/admin-pick
# ---------------------------------------------------------------------------


class TestAdminCreatePodPick:
    def _seeded_with_open_draft(self, db, client, suffix=""):
        """
        Return a seeded league whose round is in 'drafting' status (no picks yet).
        The seed endpoint leaves rounds as 'drafting' by default, so this is the
        starting state right after seeding.
        """
        (
            league,
            season,
            manager,
            player,
            tournament,
            golfer1,
            golfer2,
            mgr_headers,
            round_id,
            pod_id,
        ) = _setup_seeded_league(db, client, suffix=suffix)
        return league, manager, player, tournament, golfer1, golfer2, mgr_headers, round_id, pod_id

    def test_pod_not_in_league_returns_403(self, client, db):
        """POST admin-pick with a pod from another league returns 403."""
        manager_a = _make_user(db, "mgr_acp_cla@test.com")
        league_a, _ = _make_league(db, manager_a)
        mgr_a_headers = _login(client, "mgr_acp_cla@test.com")

        (_, _, _, _, _, _, _, _, _, pod_b_id) = _setup_seeded_league(db, client, suffix="_acpcl")

        resp = client.post(
            f"/api/v1/leagues/{league_a.id}/playoff/pods/{pod_b_id}/admin-pick",
            headers=mgr_a_headers,
            json={
                "user_id": str(uuid.uuid4()),
                "golfer_id": str(uuid.uuid4()),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 403

    def test_round_not_locked_returns_422(self, client, db):
        """Creating an admin pick when the round is drafting (not yet resolved) returns 422."""
        (
            league,
            manager,
            player,
            _,
            golfer1,
            _,
            mgr_headers,
            round_id,
            pod_id,
        ) = self._seeded_with_open_draft(db, client, suffix="_acpnd")

        # Round is in drafting status — picks don't exist yet, admin-pick should be blocked.
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(manager.id),
                "golfer_id": str(golfer1.id),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 422
        assert "locked" in resp.json()["detail"].lower()

    def test_round_completed_returns_422(self, client, db):
        """Creating an admin pick when the round is completed returns 422."""
        (
            league,
            manager,
            player,
            _,
            golfer1,
            _,
            mgr_headers,
            round_id,
            pod_id,
        ) = self._seeded_with_open_draft(db, client, suffix="_acpco")

        round_obj = db.query(PlayoffRound).filter_by(id=round_id).first()
        round_obj.status = "completed"
        db.commit()

        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(manager.id),
                "golfer_id": str(golfer1.id),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 422
        assert "locked" in resp.json()["detail"].lower()

    def test_admin_pick_allowed_when_locked(self, client, db):
        """Creating an admin pick when the round is locked (post-resolve) succeeds."""
        (
            league,
            manager,
            player,
            _,
            golfer1,
            _,
            mgr_headers,
            round_id,
            pod_id,
        ) = self._seeded_with_open_draft(db, client, suffix="_acplk")

        # Lock the round to simulate post-resolve state
        round_obj = db.query(PlayoffRound).filter_by(id=round_id).first()
        round_obj.status = "locked"
        db.commit()

        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(manager.id),
                "golfer_id": str(golfer1.id),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 201

    def test_user_not_in_pod_returns_404(self, client, db):
        """Creating an admin pick for a user not in the pod returns 404."""
        (
            league,
            _,
            _,
            _,
            golfer1,
            _,
            mgr_headers,
            _,
            pod_id,
        ) = self._seeded_with_open_draft(db, client, suffix="_acpnp")

        outsider = _make_user(db, "outsider_acp@test.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(outsider.id),
                "golfer_id": str(golfer1.id),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 404

    def test_draft_slot_out_of_range_returns_422(self, client, db):
        """draft_slot outside [1, picks_per_round] returns 422."""
        (
            league,
            manager,
            _,
            _,
            golfer1,
            _,
            mgr_headers,
            _,
            pod_id,
        ) = self._seeded_with_open_draft(db, client, suffix="_acpor")

        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(manager.id),
                "golfer_id": str(golfer1.id),
                "draft_slot": 99,  # config has picks_per_round=[1], so max is 1
            },
        )
        assert resp.status_code == 422
        assert "draft_slot" in resp.json()["detail"].lower()

    def test_slot_already_filled_returns_422(self, client, db):
        """Creating a pick for a slot already occupied returns 422."""
        (
            league,
            manager,
            _,
            tournament,
            golfer1,
            golfer2,
            mgr_headers,
            _,
            pod_id,
        ) = self._seeded_with_open_draft(db, client, suffix="_acpsf")

        # Create the first pick
        client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(manager.id),
                "golfer_id": str(golfer1.id),
                "draft_slot": 1,
            },
        )

        # Try to fill the same slot again
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(manager.id),
                "golfer_id": str(golfer2.id),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 422
        assert "already has a pick" in resp.json()["detail"].lower()

    def test_golfer_not_found_returns_404(self, client, db):
        """Creating an admin pick with an unknown golfer_id returns 404."""
        (
            league,
            manager,
            _,
            _,
            _,
            _,
            mgr_headers,
            _,
            pod_id,
        ) = self._seeded_with_open_draft(db, client, suffix="_acpgf")

        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(manager.id),
                "golfer_id": str(uuid.uuid4()),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 404

    def test_golfer_already_in_pod_returns_422(self, client, db):
        """Creating an admin pick with a golfer already picked in the pod returns 422."""
        (
            league,
            manager,
            player,
            tournament,
            golfer1,
            golfer2,
            mgr_headers,
            _,
            pod_id,
        ) = self._seeded_with_open_draft(db, client, suffix="_acpga")

        # Create first pick (manager gets golfer1, draft_slot=1)
        first_resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(manager.id),
                "golfer_id": str(golfer1.id),
                "draft_slot": 1,
            },
        )
        assert first_resp.status_code == 201

        # Try to give player the same golfer1 (already picked in pod)
        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(player.id),
                "golfer_id": str(golfer1.id),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 422
        assert "already picked" in resp.json()["detail"].lower()

    def test_success_creates_pick_with_correct_fields(self, client, db):
        """Happy path: admin pick creates a PlayoffPick with the right golfer and slot."""
        (
            league,
            manager,
            _,
            tournament,
            golfer1,
            _,
            mgr_headers,
            _,
            pod_id,
        ) = self._seeded_with_open_draft(db, client, suffix="_acpsuc")

        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/pods/{pod_id}/admin-pick",
            headers=mgr_headers,
            json={
                "user_id": str(manager.id),
                "golfer_id": str(golfer1.id),
                "draft_slot": 1,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["golfer_id"] == str(golfer1.id)
        assert data["draft_slot"] == 1
        assert data["points_earned"] is None

        # Verify the pick exists in the DB
        pick_in_db = db.query(PlayoffPick).filter_by(pod_id=pod_id, draft_slot=1).first()
        assert pick_in_db is not None
        assert pick_in_db.golfer_id == golfer1.id
