"""
Tests for the playoff scoring-pending state.

When the regular season ends but ESPN hasn't published all earnings yet:
  - Regular-season picks must be blocked for playoff tournaments
  - The my-pod endpoint must signal playoff_scoring_pending=True
  - The manual seed endpoint must reject (already tested in test_playoff_seeding_gate.py)

These tests verify the backend correctly blocks regular picks during the
gap between tournament completion and earnings publication, preventing
users from submitting regular-season picks on future playoff tournaments.
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


def _setup_pending_playoff(db, *, suffix="", scored=False):
    """Build a league in the scoring-pending gap state.

    - 1 completed regular-season tournament (picks scored or unscored)
    - 1 scheduled playoff tournament
    - Playoff config with status=pending (bracket not seeded)
    - 2 approved members with picks

    Returns (manager_email, league, season, completed_tournament, playoff_tournament).
    """
    sfx = suffix or uuid.uuid4().hex[:4]
    today = date.today()

    manager = _make_user(db, f"mgr_{sfx}@test.com")
    player = _make_user(db, f"p_{sfx}@test.com")

    league = League(name=f"Pending PO {sfx}", created_by=manager.id)
    db.add(league)
    db.flush()

    for user, role in [(manager, "manager"), (player, "member")]:
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=role,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )

    season = Season(league_id=league.id, year=today.year, is_active=True)
    db.add(season)
    db.flush()

    # Completed regular-season tournament
    completed = Tournament(
        pga_tour_id=f"comp_{sfx}",
        name="Completed Regular",
        start_date=today - timedelta(days=4),
        end_date=today - timedelta(days=1),
        status="completed",
    )
    db.add(completed)
    db.flush()
    db.add(LeagueTournament(league_id=league.id, tournament_id=completed.id))

    # Create picks for both members
    for i, user in enumerate([manager, player]):
        golfer = Golfer(pga_tour_id=f"g_{sfx}_{i}", name=f"Golfer {i}")
        db.add(golfer)
        db.flush()

        entry = TournamentEntry(
            tournament_id=completed.id,
            golfer_id=golfer.id,
            finish_position=i + 1,
            earnings_usd=(2 - i) * 500000 if scored else None,
        )
        db.add(entry)
        db.flush()
        for rn in range(1, 5):
            db.add(TournamentEntryRound(tournament_entry_id=entry.id, round_number=rn))

        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=completed.id,
            golfer_id=golfer.id,
            points_earned=float((2 - i) * 500000) if scored else None,
        )
        db.add(pick)

    # Scheduled playoff tournament
    playoff_t = Tournament(
        pga_tour_id=f"po_{sfx}",
        name="Playoff Round 1",
        start_date=today + timedelta(days=7),
        end_date=today + timedelta(days=10),
        status="scheduled",
    )
    db.add(playoff_t)
    db.flush()
    db.add(LeagueTournament(league_id=league.id, tournament_id=playoff_t.id))

    # Pending playoff config
    config = PlayoffConfig(
        league_id=league.id,
        season_id=season.id,
        is_enabled=True,
        playoff_size=2,
        draft_style="snake",
        picks_per_round=[1],
        status="pending",
    )
    db.add(config)
    db.commit()

    return f"mgr_{sfx}@test.com", league, season, completed, playoff_t


# ---------------------------------------------------------------------------
# Pick validation: block regular picks during scoring-pending gap
# ---------------------------------------------------------------------------


class TestPickBlockedDuringScoringPending:
    """Regular-season pick submission must be blocked when a playoff config
    exists (pending) and completed tournaments have unscored picks."""

    def test_regular_pick_rejected_when_scoring_pending(self, client, db):
        """User tries to submit a regular pick for the playoff tournament
        while earnings are still pending — should get 422."""
        email, league, season, _, playoff_t = _setup_pending_playoff(
            db, suffix="rpb1", scored=False
        )
        headers = _login(client, email)

        # Create a golfer to pick
        golfer = Golfer(pga_tour_id="pick_target", name="Pick Target")
        db.add(golfer)
        db.flush()
        db.add(
            TournamentEntry(
                tournament_id=playoff_t.id,
                golfer_id=golfer.id,
            )
        )
        db.commit()

        resp = client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=headers,
            json={
                "tournament_id": str(playoff_t.id),
                "golfer_id": str(golfer.id),
            },
        )
        assert resp.status_code == 422
        assert "scoring" in resp.json()["detail"].lower()
        assert "finalized" in resp.json()["detail"].lower()

    def test_regular_pick_allowed_when_scoring_complete(self, client, db):
        """When all picks are scored, the pick validation should not
        block on the scoring-pending guard. (It may still fail for other
        reasons like playoff round detection once the bracket is seeded,
        but the scoring-pending guard itself should pass.)"""
        email, league, season, _, playoff_t = _setup_pending_playoff(db, suffix="rpb2", scored=True)
        headers = _login(client, email)

        golfer = Golfer(pga_tour_id="pick_target2", name="Pick Target 2")
        db.add(golfer)
        db.flush()
        db.add(
            TournamentEntry(
                tournament_id=playoff_t.id,
                golfer_id=golfer.id,
            )
        )
        db.commit()

        resp = client.post(
            f"/api/v1/leagues/{league.id}/picks",
            headers=headers,
            json={
                "tournament_id": str(playoff_t.id),
                "golfer_id": str(golfer.id),
            },
        )
        # Should NOT fail with the scoring-pending error.
        # It might succeed (201) or fail for another reason (e.g., 422
        # from the playoff round check if bracket auto-seeds), but the
        # detail should NOT mention "scoring" or "finalized".
        if resp.status_code == 422:
            assert "scoring" not in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# my-pod endpoint: playoff_scoring_pending flag
# ---------------------------------------------------------------------------


class TestMyPodScoringPending:
    """GET /playoff/my-pod returns playoff_scoring_pending=True when the
    bracket can't be seeded due to unscored picks."""

    def test_scoring_pending_true_when_unscored(self, client, db):
        email, league, _, _, _ = _setup_pending_playoff(db, suffix="mp1", scored=False)
        headers = _login(client, email)

        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/my-pod",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["playoff_scoring_pending"] is True
        assert data["scoring_pending_tournament_name"] == "Completed Regular"
        assert data["is_playoff_week"] is False

    def test_scoring_pending_false_when_scored(self, client, db):
        email, league, _, _, _ = _setup_pending_playoff(db, suffix="mp2", scored=True)
        headers = _login(client, email)

        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/my-pod",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["playoff_scoring_pending"] is False

    def test_scoring_pending_false_when_no_playoff_config(self, client, db):
        """League without a playoff config should not have scoring_pending."""
        sfx = "mp3"
        manager = _make_user(db, f"mgr_{sfx}@test.com")
        league = League(name=f"No PO {sfx}", created_by=manager.id)
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

        headers = _login(client, f"mgr_{sfx}@test.com")
        resp = client.get(
            f"/api/v1/leagues/{league.id}/playoff/my-pod",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["playoff_scoring_pending"] is False
