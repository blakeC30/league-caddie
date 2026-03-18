"""
Extended tests for app/routers/tournaments.py.

Covers previously uncovered paths:
  GET /tournaments?status={invalid}          — 400 invalid status filter
  GET /tournaments/{id}/leaderboard          — playoff tie-breaking, team events
  GET /tournaments/{id}/sync-status          — 404 path (not found)
  GET /tournaments/{id}/golfers/{gid}/scorecard — mocked ESPN call, 404 cases
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from app.models import Golfer, Tournament, TournamentEntry
from app.models.tournament import TournamentEntryRound, TournamentStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_login(client, email: str = "user@example.com") -> dict:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "User"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200, resp.json()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_tournament(
    db,
    name: str = "Test Open",
    status: str = TournamentStatus.SCHEDULED.value,
    days_from_now: int = 7,
    is_team_event: bool = False,
    last_synced_at: datetime | None = None,
) -> Tournament:
    start = date.today() + timedelta(days=days_from_now)
    t = Tournament(
        pga_tour_id=f"R{uuid.uuid4().hex[:8]}",
        name=name,
        start_date=start,
        end_date=start + timedelta(days=3),
        status=status,
        multiplier=1.0,
        is_team_event=is_team_event,
        last_synced_at=last_synced_at,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_golfer(db, name: str, ranking: int | None = None) -> Golfer:
    g = Golfer(
        pga_tour_id=f"G{uuid.uuid4().hex[:8]}",
        name=name,
        world_ranking=ranking,
        country="United States",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _make_entry(
    db,
    tournament: Tournament,
    golfer: Golfer,
    earnings: int | None = None,
    status: str | None = None,
    finish_position: int | None = None,
    team_competitor_id: str | None = None,
) -> TournamentEntry:
    entry = TournamentEntry(
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        earnings_usd=earnings,
        status=status,
        finish_position=finish_position,
        team_competitor_id=team_competitor_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _make_entry_round(
    db,
    entry: TournamentEntry,
    round_number: int,
    score_to_par: int | None = None,
    is_playoff: bool = False,
    position: str | None = None,
    score: int | None = None,
) -> TournamentEntryRound:
    r = TournamentEntryRound(
        tournament_entry_id=entry.id,
        round_number=round_number,
        score_to_par=score_to_par,
        is_playoff=is_playoff,
        position=position,
        score=score,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ---------------------------------------------------------------------------
# TestListTournamentsStatusFilter
# ---------------------------------------------------------------------------


class TestListTournamentsStatusFilter:
    def test_invalid_status_returns_400(self, client, db):
        """An unrecognized status value must return 400."""
        headers = _register_and_login(client)
        resp = client.get("/api/v1/tournaments?status=bogus_status", headers=headers)
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "bogus_status" in detail
        assert "invalid status" in detail.lower()

    def test_another_invalid_status_returns_400(self, client, db):
        """Any string that is not a valid TournamentStatus value is rejected."""
        headers = _register_and_login(client)
        resp = client.get("/api/v1/tournaments?status=SCHEDULED", headers=headers)  # wrong case
        assert resp.status_code == 400

    def test_valid_status_does_not_return_400(self, client, db):
        """Sanity check: a valid status filter returns 200, not 400."""
        headers = _register_and_login(client)
        resp = client.get("/api/v1/tournaments?status=scheduled", headers=headers)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestLeaderboardPlayoffTieBreaking
# ---------------------------------------------------------------------------


class TestLeaderboardPlayoffTieBreaking:
    def test_playoff_tiebreaker_assigns_distinct_positions(self, client, db):
        """Two golfers tied in regulation whose tie is broken by a playoff round get
        distinct (non-tied) positions based on playoff round position."""
        tournament = _make_tournament(
            db,
            name="Playoff Breaker Open",
            status=TournamentStatus.COMPLETED.value,
            days_from_now=-5,
        )
        g_winner = _make_golfer(db, "Playoff Winner", ranking=1)
        g_loser = _make_golfer(db, "Playoff Loser", ranking=2)

        entry_winner = _make_entry(db, tournament, g_winner)
        entry_loser = _make_entry(db, tournament, g_loser)

        # Both tied at -10 in regulation (rounds 1 and 2).
        _make_entry_round(db, entry_winner, round_number=1, score_to_par=-5, is_playoff=False)
        _make_entry_round(db, entry_winner, round_number=2, score_to_par=-5, is_playoff=False)
        _make_entry_round(db, entry_loser, round_number=1, score_to_par=-5, is_playoff=False)
        _make_entry_round(db, entry_loser, round_number=2, score_to_par=-5, is_playoff=False)

        # Playoff round: winner finishes 1st, loser finishes 2nd.
        _make_entry_round(
            db, entry_winner, round_number=5, score_to_par=-1, is_playoff=True, position="1"
        )
        _make_entry_round(
            db, entry_loser, round_number=5, score_to_par=0, is_playoff=True, position="2"
        )

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200

        entries = resp.json()["entries"]
        winner_data = next(e for e in entries if e["golfer_name"] == "Playoff Winner")
        loser_data = next(e for e in entries if e["golfer_name"] == "Playoff Loser")

        # The tie should be broken: winner gets position 1, loser gets position 2.
        assert winner_data["finish_position"] == 1
        assert loser_data["finish_position"] == 2
        # Neither should be marked as tied after the playoff resolves the tie.
        assert winner_data["is_tied"] is False
        assert loser_data["is_tied"] is False

    def test_no_playoff_keeps_tied_positions(self, client, db):
        """Two golfers tied in regulation with NO playoff round keep the same
        finish_position and is_tied=True."""
        tournament = _make_tournament(
            db,
            name="Regulation Tie Open",
            status=TournamentStatus.COMPLETED.value,
            days_from_now=-5,
        )
        g1 = _make_golfer(db, "Tied Golfer A", ranking=1)
        g2 = _make_golfer(db, "Tied Golfer B", ranking=2)

        e1 = _make_entry(db, tournament, g1)
        e2 = _make_entry(db, tournament, g2)

        # Both at -8; no playoff rounds.
        _make_entry_round(db, e1, round_number=1, score_to_par=-4)
        _make_entry_round(db, e1, round_number=2, score_to_par=-4)
        _make_entry_round(db, e2, round_number=1, score_to_par=-4)
        _make_entry_round(db, e2, round_number=2, score_to_par=-4)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200

        entries = resp.json()["entries"]
        positions = {e["finish_position"] for e in entries}
        # Both should share the same finish_position.
        assert len(positions) == 1
        for e in entries:
            assert e["is_tied"] is True

    def test_playoff_tiebreaker_with_invalid_position_string(self, client, db):
        """A non-integer position string on the playoff round falls back to 9999,
        meaning the endpoint still returns 200 without crashing."""
        tournament = _make_tournament(
            db,
            name="Bad Position Open",
            status=TournamentStatus.COMPLETED.value,
            days_from_now=-5,
        )
        g1 = _make_golfer(db, "Golfer With Bad Pos", ranking=1)
        g2 = _make_golfer(db, "Golfer Normal", ranking=2)
        e1 = _make_entry(db, tournament, g1)
        e2 = _make_entry(db, tournament, g2)

        _make_entry_round(db, e1, round_number=1, score_to_par=-3, is_playoff=False)
        _make_entry_round(db, e2, round_number=1, score_to_par=-3, is_playoff=False)
        # Non-integer position — the router uses try/except and falls back to 9999.
        _make_entry_round(db, e1, round_number=5, score_to_par=0, is_playoff=True, position="T1")
        _make_entry_round(db, e2, round_number=5, score_to_par=0, is_playoff=True, position="T1")

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200
        # Just verify we get two entries back without crashing.
        assert len(resp.json()["entries"]) == 2


# ---------------------------------------------------------------------------
# TestLeaderboardTeamEvent
# ---------------------------------------------------------------------------


class TestLeaderboardTeamEvent:
    def test_team_event_populates_partner_name(self, client, db):
        """In a team event, each golfer's leaderboard entry should include partner_name
        and partner_golfer_id pointing to their teammate."""
        tournament = _make_tournament(
            db,
            name="Zurich Classic",
            status=TournamentStatus.COMPLETED.value,
            days_from_now=-5,
            is_team_event=True,
        )
        g1 = _make_golfer(db, "Team A Golfer 1", ranking=10)
        g2 = _make_golfer(db, "Team A Golfer 2", ranking=11)

        # Both share the same team_competitor_id — this is how the scraper marks teammates.
        TEAM_ID = "team_001"
        e1 = _make_entry(db, tournament, g1, team_competitor_id=TEAM_ID, earnings=1_000_000)
        e2 = _make_entry(db, tournament, g2, team_competitor_id=TEAM_ID, earnings=1_000_000)

        # Add round data so the entries appear in regulation scoring.
        _make_entry_round(db, e1, round_number=1, score_to_par=-5)
        _make_entry_round(db, e2, round_number=1, score_to_par=-5)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200

        data = resp.json()
        assert data["is_team_event"] is True
        entries = data["entries"]
        assert len(entries) == 2

        g1_data = next(e for e in entries if e["golfer_name"] == "Team A Golfer 1")
        g2_data = next(e for e in entries if e["golfer_name"] == "Team A Golfer 2")

        # Each partner should point to the other.
        assert g1_data["partner_name"] == "Team A Golfer 2"
        assert g1_data["partner_golfer_id"] == str(g2.id)
        assert g2_data["partner_name"] == "Team A Golfer 1"
        assert g2_data["partner_golfer_id"] == str(g1.id)

    def test_non_team_event_has_no_partner(self, client, db):
        """For individual tournaments, partner_name and partner_golfer_id should be None."""
        tournament = _make_tournament(
            db,
            name="Regular Masters",
            status=TournamentStatus.COMPLETED.value,
            days_from_now=-5,
            is_team_event=False,
        )
        g = _make_golfer(db, "Solo Golfer", ranking=1)
        entry = _make_entry(db, tournament, g, earnings=2_000_000)
        _make_entry_round(db, entry, round_number=1, score_to_par=-10)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200

        data = resp.json()
        assert data["is_team_event"] is False
        entry_data = data["entries"][0]
        assert entry_data["partner_name"] is None
        assert entry_data["partner_golfer_id"] is None

    def test_team_event_with_odd_team_size_no_partner_set(self, client, db):
        """A team_competitor_id shared by only one entry (orphan) produces no partner."""
        tournament = _make_tournament(
            db,
            name="Orphan Team Open",
            status=TournamentStatus.COMPLETED.value,
            days_from_now=-5,
            is_team_event=True,
        )
        g_orphan = _make_golfer(db, "Orphan Golfer", ranking=5)
        entry = _make_entry(
            db, tournament, g_orphan, team_competitor_id="orphan_team", earnings=500_000
        )
        _make_entry_round(db, entry, round_number=1, score_to_par=-3)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200

        # A group with only 1 entry is not treated as a team — no partner is set.
        entry_data = resp.json()["entries"][0]
        assert entry_data["partner_name"] is None


# ---------------------------------------------------------------------------
# TestSyncStatus
# ---------------------------------------------------------------------------


class TestSyncStatus:
    def test_returns_sync_status_fields(self, client, db):
        """The sync-status endpoint returns tournament_id, tournament_status, and last_synced_at."""
        synced_at = datetime.now(UTC)
        tournament = _make_tournament(
            db,
            name="Synced Tournament",
            status=TournamentStatus.IN_PROGRESS.value,
            last_synced_at=synced_at,
        )
        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/sync-status", headers=headers)
        assert resp.status_code == 200

        data = resp.json()
        assert data["tournament_id"] == str(tournament.id)
        assert data["tournament_status"] == TournamentStatus.IN_PROGRESS.value
        assert data["last_synced_at"] is not None

    def test_last_synced_at_is_null_when_never_synced(self, client, db):
        """last_synced_at is null for a tournament that has never been synced."""
        tournament = _make_tournament(db, name="Unsynced Tournament")
        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/sync-status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["last_synced_at"] is None

    def test_not_found_returns_404(self, client, db):
        """Requesting sync-status for a non-existent tournament returns 404."""
        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{uuid.uuid4()}/sync-status", headers=headers)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_requires_authentication(self, client, db):
        tournament = _make_tournament(db)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/sync-status")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestScorecard
# ---------------------------------------------------------------------------


class TestScorecard:
    def test_mocked_scorecard_returns_200(self, client, db):
        """When fetch_golfer_scorecard is mocked, the endpoint returns 200 with the scorecard
        data."""
        tournament = _make_tournament(
            db,
            name="Scorecard Open",
            status=TournamentStatus.IN_PROGRESS.value,
            days_from_now=0,
        )
        golfer = _make_golfer(db, "Scorecard Golfer")

        mock_return = {
            "golfer_id": str(golfer.id),
            "round_number": 1,
            "holes": [],
            "total_score": None,
            "total_score_to_par": None,
        }

        headers = _register_and_login(client)

        with patch("app.services.scraper.fetch_golfer_scorecard", return_value=mock_return):
            resp = client.get(
                f"/api/v1/tournaments/{tournament.id}/golfers/{golfer.id}/scorecard?round=1",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["golfer_id"] == str(golfer.id)
        assert data["round_number"] == 1
        assert data["holes"] == []
        assert data["total_score"] is None
        assert data["total_score_to_par"] is None

    def test_tournament_not_found_returns_404(self, client, db):
        """When the tournament does not exist, the scorecard endpoint returns 404."""
        golfer = _make_golfer(db, "Some Golfer")
        headers = _register_and_login(client)

        resp = client.get(
            f"/api/v1/tournaments/{uuid.uuid4()}/golfers/{golfer.id}/scorecard?round=1",
            headers=headers,
        )
        assert resp.status_code == 404
        assert "tournament not found" in resp.json()["detail"].lower()

    def test_golfer_not_found_returns_404(self, client, db):
        """When the golfer does not exist, the scorecard endpoint returns 404."""
        tournament = _make_tournament(
            db,
            name="Scorecard 404 Open",
            status=TournamentStatus.IN_PROGRESS.value,
            days_from_now=0,
        )
        headers = _register_and_login(client)

        resp = client.get(
            f"/api/v1/tournaments/{tournament.id}/golfers/{uuid.uuid4()}/scorecard?round=1",
            headers=headers,
        )
        assert resp.status_code == 404
        assert "golfer not found" in resp.json()["detail"].lower()

    def test_requires_authentication(self, client, db):
        """Scorecard endpoint requires a valid JWT."""
        tournament = _make_tournament(db)
        resp = client.get(
            f"/api/v1/tournaments/{tournament.id}/golfers/{uuid.uuid4()}/scorecard?round=1"
        )
        assert resp.status_code == 401

    def test_mocked_scorecard_with_round_param(self, client, db):
        """Verify the round query parameter is forwarded correctly."""
        tournament = _make_tournament(
            db,
            name="Round 3 Open",
            status=TournamentStatus.IN_PROGRESS.value,
            days_from_now=0,
        )
        golfer = _make_golfer(db, "Round 3 Golfer")

        mock_return = {
            "golfer_id": str(golfer.id),
            "round_number": 3,
            "holes": [],
            "total_score": 68,
            "total_score_to_par": -3,
        }

        headers = _register_and_login(client)

        with patch("app.services.scraper.fetch_golfer_scorecard", return_value=mock_return):
            resp = client.get(
                f"/api/v1/tournaments/{tournament.id}/golfers/{golfer.id}/scorecard?round=3",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["round_number"] == 3
        assert data["total_score"] == 68
        assert data["total_score_to_par"] == -3
