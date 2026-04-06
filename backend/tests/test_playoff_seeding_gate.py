"""
Tests for the playoff seeding scoring gate.

ESPN publishes earnings gradually (12-48h after tournament completion).
The score_picks() earnings gate defers scoring until all made-the-cut
entries have earnings. The bracket must not be seeded until scoring is
complete — otherwise standings exclude the last tournament's points and
seeding is incorrect.

Covers:
  - Manual seed (POST /playoff/seed) rejects when picks are unscored
  - Manual seed succeeds when all picks are scored
  - Auto-seed (GET /bracket) defers when picks are unscored
  - Auto-seed triggers once scoring completes
"""

import uuid
from datetime import date, timedelta

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeagueTournament,
    Pick,
    PlayoffConfig,
    Season,
    Tournament,
    TournamentEntry,
    TournamentEntryRound,
    User,
)
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db, email):
    u = User(
        email=email,
        password_hash=hash_password("password123"),
        display_name="Player",
    )
    db.add(u)
    db.flush()
    return u


def _login(client, email):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _setup_league_for_seeding(db, *, suffix="", unscored=True):
    """Build a league where the regular season just completed.

    Creates:
    - 4 approved members (manager + 3 players)
    - 1 completed regular-season tournament with picks
    - 1 scheduled playoff tournament
    - A pending playoff config (size=4, 2 rounds, needs 2 scheduled tournaments)

    When unscored=True: the completed tournament's picks have points_earned=NULL
    (simulating ESPN not having published all earnings yet).

    When unscored=False: picks have points_earned set (scoring is complete).

    Returns (manager_email, league, season, config).
    """
    sfx = suffix or uuid.uuid4().hex[:4]
    manager = _make_user(db, f"mgr_{sfx}@test.com")
    league = League(name=f"Seeding League {sfx}", created_by=manager.id)
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

    players = []
    for i in range(3):
        p = _make_user(db, f"p{i}_{sfx}@test.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=p.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        players.append(p)

    season = Season(league_id=league.id, year=date.today().year, is_active=True)
    db.add(season)
    db.flush()

    # Completed regular-season tournament (ended 1 day ago).
    today = date.today()
    completed = Tournament(
        pga_tour_id=f"comp_{sfx}",
        name="Completed Regular",
        start_date=today - timedelta(days=4),
        end_date=today - timedelta(days=1),
        status="completed",
    )
    db.add(completed)
    db.flush()
    db.add(
        LeagueTournament(
            league_id=league.id,
            tournament_id=completed.id,
        )
    )

    # Each member picks a different golfer.
    all_users = [manager] + players
    for i, user in enumerate(all_users):
        golfer = Golfer(
            pga_tour_id=f"golfer_{sfx}_{i}",
            name=f"Golfer {i}",
        )
        db.add(golfer)
        db.flush()

        entry = TournamentEntry(
            tournament_id=completed.id,
            golfer_id=golfer.id,
            finish_position=i + 1,
            earnings_usd=(4 - i) * 500000,
        )
        db.add(entry)
        db.flush()
        # Add rounds so the earnings gate doesn't treat them as pre-WDs.
        for rn in range(1, 5):
            db.add(
                TournamentEntryRound(
                    tournament_entry_id=entry.id,
                    round_number=rn,
                )
            )

        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=completed.id,
            golfer_id=golfer.id,
            points_earned=None if unscored else float((4 - i) * 500000),
        )
        db.add(pick)

    # 2 scheduled playoff tournaments (bracket size 4 → 2 rounds → 2 tournaments).
    for j in range(2):
        t = Tournament(
            pga_tour_id=f"playoff_{sfx}_{j}",
            name=f"Playoff T{j + 1}",
            start_date=today + timedelta(days=7 + j * 7),
            end_date=today + timedelta(days=10 + j * 7),
            status="scheduled",
        )
        db.add(t)
        db.flush()
        db.add(
            LeagueTournament(
                league_id=league.id,
                tournament_id=t.id,
            )
        )

    # Pending playoff config.
    config = PlayoffConfig(
        league_id=league.id,
        season_id=season.id,
        is_enabled=True,
        playoff_size=4,
        draft_style="snake",
        picks_per_round=[1, 1],
        status="pending",
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    return f"mgr_{sfx}@test.com", league, season, config


# ---------------------------------------------------------------------------
# Manual seed: POST /playoff/seed
# ---------------------------------------------------------------------------


class TestManualSeedScoringGate:
    """POST /playoff/seed rejects seeding when completed tournaments have
    unscored picks (points_earned IS NULL)."""

    def test_rejects_when_picks_unscored(self, client, db):
        """Tournament completed but earnings not yet published → 422."""
        email, league, _, _ = _setup_league_for_seeding(db, suffix="ms1", unscored=True)
        headers = _login(client, email)

        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/seed",
            headers=headers,
        )
        assert resp.status_code == 422
        assert "unscored picks" in resp.json()["detail"].lower()

    def test_succeeds_when_all_picks_scored(self, client, db):
        """All picks scored → seeding proceeds normally."""
        email, league, _, _ = _setup_league_for_seeding(db, suffix="ms2", unscored=False)
        headers = _login(client, email)

        resp = client.post(
            f"/api/v1/leagues/{league.id}/playoff/seed",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["playoff_config"]["status"] == "active"


# ---------------------------------------------------------------------------
# Auto-seed: GET /bracket
# ---------------------------------------------------------------------------


class TestAutoSeedScoringGate:
    """GET /bracket defers auto-seeding when completed tournaments have
    unscored picks, and triggers it once scoring completes."""

    def test_defers_autoseed_when_picks_unscored(self, client, db):
        """Regular season done, but picks unscored → bracket stays empty."""
        email, league, _, config = _setup_league_for_seeding(db, suffix="as1", unscored=True)
        headers = _login(client, email)

        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/bracket",
            headers=headers,
        )
        assert resp.status_code == 200
        # Config is still pending — not seeded.
        assert resp.json()["playoff_config"]["status"] == "pending"
        assert resp.json()["rounds"] == []

    def test_autoseeds_when_all_picks_scored(self, client, db):
        """All picks scored → auto-seed triggers on bracket view."""
        email, league, _, config = _setup_league_for_seeding(db, suffix="as2", unscored=False)
        headers = _login(client, email)

        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/bracket",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["playoff_config"]["status"] == "active"
        assert len(resp.json()["rounds"]) == 2  # 4-player bracket → 2 rounds

    def test_autoseeds_after_scoring_completes(self, client, db):
        """Bracket defers, then scoring completes, then next visit seeds."""
        email, league, season, config = _setup_league_for_seeding(db, suffix="as3", unscored=True)
        headers = _login(client, email)

        # First visit: unscored → deferred.
        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/bracket",
            headers=headers,
        )
        assert resp.json()["playoff_config"]["status"] == "pending"

        # Simulate scoring completing (ESPN published all earnings).
        picks = db.query(Pick).filter_by(league_id=league.id, season_id=season.id).all()
        for i, pick in enumerate(picks):
            pick.points_earned = float((4 - i) * 500000)
        db.commit()

        # Second visit: all scored → auto-seed triggers.
        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/bracket",
            headers=headers,
        )
        assert resp.json()["playoff_config"]["status"] == "active"
        assert len(resp.json()["rounds"]) == 2
