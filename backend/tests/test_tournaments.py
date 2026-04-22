"""
Tests for the tournaments router.

Covers:
  - GET /tournaments               List (with/without status filter)
  - GET /tournaments/{id}          Single tournament detail
  - GET /tournaments/{id}/field    Field listing, WD exclusion, ranking order
  - GET /tournaments/{id}/leaderboard  Status guards, entry sorting, positions
  - GET /tournaments/{id}/sync-status  Sync timestamp endpoint
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models import Golfer, Tournament, TournamentEntry, TournamentStatus
from app.models.tournament import TournamentEntryRound

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_login(client, email: str = "user@example.com") -> dict:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "password123",
            "display_name": "User",
            "first_name": "Test",
            "last_name": "User",
        },
    )
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_tournament(
    db,
    name: str = "Test Open",
    status: str = TournamentStatus.SCHEDULED.value,
    days_from_now: int = 7,
    last_synced_at: datetime | None = None,
) -> Tournament:
    start = date.today() + timedelta(days=days_from_now)
    t = Tournament(
        pga_tour_id=f"R{uuid.uuid4().hex[:6]}",
        name=name,
        start_date=start,
        end_date=start + timedelta(days=3),
        status=status,
        last_synced_at=last_synced_at,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_golfer(db, name: str, ranking: int | None = None) -> Golfer:
    g = Golfer(
        pga_tour_id=f"G{uuid.uuid4().hex[:6]}",
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
) -> TournamentEntry:
    entry = TournamentEntry(
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        earnings_usd=earnings,
        status=status,
        finish_position=finish_position,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# GET /tournaments — list
# ---------------------------------------------------------------------------


class TestListTournaments:
    def test_returns_empty_list_when_no_tournaments(self, client, db):
        headers = _register_and_login(client)
        resp = client.get("/api/v1/tournaments", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_tournaments_without_filter(self, client, db):
        _make_tournament(db, "Open A", TournamentStatus.SCHEDULED.value, days_from_now=10)
        _make_tournament(db, "Open B", TournamentStatus.COMPLETED.value, days_from_now=-7)

        headers = _register_and_login(client)
        resp = client.get("/api/v1/tournaments", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_filter_by_status_scheduled(self, client, db):
        _make_tournament(db, "Scheduled T", TournamentStatus.SCHEDULED.value, days_from_now=5)
        _make_tournament(db, "Completed T", TournamentStatus.COMPLETED.value, days_from_now=-5)

        headers = _register_and_login(client)
        resp = client.get("/api/v1/tournaments?status=scheduled", headers=headers)
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "Scheduled T" in names
        assert "Completed T" not in names

    def test_filter_by_status_completed(self, client, db):
        _make_tournament(db, "Done T", TournamentStatus.COMPLETED.value, days_from_now=-5)
        _make_tournament(db, "Future T", TournamentStatus.SCHEDULED.value, days_from_now=10)

        headers = _register_and_login(client)
        resp = client.get("/api/v1/tournaments?status=completed", headers=headers)
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "Done T" in names
        assert "Future T" not in names

    def test_filter_by_invalid_status_returns_400(self, client, db):
        headers = _register_and_login(client)
        resp = client.get("/api/v1/tournaments?status=invalid", headers=headers)
        assert resp.status_code == 400

    def test_requires_authentication(self, client, db):
        resp = client.get("/api/v1/tournaments")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /tournaments/{id} — single tournament
# ---------------------------------------------------------------------------


class TestGetTournament:
    def test_returns_tournament_data(self, client, db):
        tournament = _make_tournament(db, "Masters")

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Masters"
        assert data["status"] == "scheduled"
        assert "id" in data

    def test_returns_404_for_unknown_id(self, client, db):
        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    def test_requires_authentication(self, client, db):
        tournament = _make_tournament(db, "Auth Test")
        resp = client.get(f"/api/v1/tournaments/{tournament.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /tournaments/{id}/field
# ---------------------------------------------------------------------------


class TestGetTournamentField:
    def test_returns_empty_when_no_field(self, client, db):
        tournament = _make_tournament(db)
        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/field", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_golfers_in_field(self, client, db):
        tournament = _make_tournament(db)
        golfer = _make_golfer(db, "Tiger Woods", ranking=1)
        _make_entry(db, tournament, golfer)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/field", headers=headers)
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 1
        assert entries[0]["name"] == "Tiger Woods"

    def test_excludes_withdrawn_golfers(self, client, db):
        tournament = _make_tournament(db)
        active = _make_golfer(db, "Active Player", ranking=5)
        wd = _make_golfer(db, "Withdrew Player", ranking=10)
        _make_entry(db, tournament, active)
        _make_entry(db, tournament, wd, status="WD")

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/field", headers=headers)
        assert resp.status_code == 200
        names = [e["name"] for e in resp.json()]
        assert "Active Player" in names
        assert "Withdrew Player" not in names

    def test_sorted_by_world_ranking(self, client, db):
        tournament = _make_tournament(db)
        g3 = _make_golfer(db, "Ranked 3rd", ranking=3)
        g1 = _make_golfer(db, "Ranked 1st", ranking=1)
        g2 = _make_golfer(db, "Ranked 2nd", ranking=2)
        _make_entry(db, tournament, g3)
        _make_entry(db, tournament, g1)
        _make_entry(db, tournament, g2)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/field", headers=headers)
        names = [e["name"] for e in resp.json()]
        assert names == ["Ranked 1st", "Ranked 2nd", "Ranked 3rd"]

    def test_unranked_golfers_appear_last(self, client, db):
        tournament = _make_tournament(db)
        ranked = _make_golfer(db, "Ranked Player", ranking=50)
        unranked = _make_golfer(db, "Unranked Player", ranking=None)
        _make_entry(db, tournament, unranked)
        _make_entry(db, tournament, ranked)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/field", headers=headers)
        names = [e["name"] for e in resp.json()]
        assert names.index("Ranked Player") < names.index("Unranked Player")

    def test_returns_404_for_unknown_tournament(self, client, db):
        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{uuid.uuid4()}/field", headers=headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /tournaments/{id}/leaderboard
# ---------------------------------------------------------------------------


class TestGetLeaderboard:
    def test_scheduled_tournament_returns_400(self, client, db):
        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value)
        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 400
        assert "not available" in resp.json()["detail"].lower()

    def test_returns_404_for_unknown_tournament(self, client, db):
        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{uuid.uuid4()}/leaderboard", headers=headers)
        assert resp.status_code == 404

    def test_completed_tournament_returns_leaderboard(self, client, db):
        tournament = _make_tournament(db, status=TournamentStatus.COMPLETED.value, days_from_now=-5)
        golfer = _make_golfer(db, "Winner", ranking=1)
        _make_entry(db, tournament, golfer, earnings=2_000_000, finish_position=1)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tournament_name"] == tournament.name
        assert data["tournament_status"] == "completed"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["golfer_name"] == "Winner"
        assert data["entries"][0]["earnings_usd"] == 2_000_000

    def test_in_progress_tournament_returns_leaderboard(self, client, db):
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        golfer = _make_golfer(db, "Live Leader", ranking=1)
        _make_entry(db, tournament, golfer)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tournament_status"] == "in_progress"
        assert len(data["entries"]) == 1

    def test_leaderboard_entry_positions_assigned_correctly(self, client, db):
        """Golfers with the same score share a rank; next rank is skipped."""
        tournament = _make_tournament(db, status=TournamentStatus.COMPLETED.value, days_from_now=-5)

        g1 = _make_golfer(db, "Leader", ranking=1)
        g2 = _make_golfer(db, "Tied 2nd A", ranking=2)
        g3 = _make_golfer(db, "Tied 2nd B", ranking=3)

        e1 = _make_entry(db, tournament, g1, earnings=2_000_000, finish_position=1)
        e2 = _make_entry(db, tournament, g2, earnings=1_000_000, finish_position=2)
        e3 = _make_entry(db, tournament, g3, earnings=1_000_000, finish_position=2)

        # Add round data so score_to_par is available for position computation.
        for entry, stp in [(e1, -10), (e2, -8), (e3, -8)]:
            db.add(
                TournamentEntryRound(
                    tournament_entry_id=entry.id,
                    round_number=4,
                    score_to_par=stp,
                )
            )
        db.commit()

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200
        entries = resp.json()["entries"]

        leader_entry = next(e for e in entries if e["golfer_name"] == "Leader")
        tied_entries = [e for e in entries if "Tied 2nd" in e["golfer_name"]]

        assert leader_entry["finish_position"] == 1
        # Both tied players should share the same finish position.
        positions = {e["finish_position"] for e in tied_entries}
        assert len(positions) == 1  # same rank for both

    def test_withdrawn_golfer_has_no_position(self, client, db):
        tournament = _make_tournament(db, status=TournamentStatus.COMPLETED.value, days_from_now=-5)
        golfer = _make_golfer(db, "Withdrew", ranking=10)
        _make_entry(db, tournament, golfer, status="WD")

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200
        entry = resp.json()["entries"][0]
        assert entry["finish_position"] is None
        assert entry["made_cut"] is False

    def test_requires_authentication(self, client, db):
        tournament = _make_tournament(db, status=TournamentStatus.COMPLETED.value, days_from_now=-1)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /tournaments/{id}/sync-status
# ---------------------------------------------------------------------------


class TestGetSyncStatus:
    def test_returns_sync_status_for_known_tournament(self, client, db):
        synced_at = datetime.now(UTC)
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, last_synced_at=synced_at
        )

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/sync-status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tournament_status"] == "in_progress"
        assert data["last_synced_at"] is not None

    def test_returns_null_synced_at_when_never_synced(self, client, db):
        tournament = _make_tournament(db)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/sync-status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["last_synced_at"] is None

    def test_returns_404_for_unknown_tournament(self, client, db):
        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{uuid.uuid4()}/sync-status", headers=headers)
        assert resp.status_code == 404

    def test_requires_authentication(self, client, db):
        tournament = _make_tournament(db)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/sync-status")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Team event leaderboard — position and is_tied correctness
# ---------------------------------------------------------------------------


def _make_team_tournament(db, name: str = "Zurich Classic") -> Tournament:
    start = date.today() - timedelta(days=5)
    t = Tournament(
        pga_tour_id=f"T{uuid.uuid4().hex[:6]}",
        name=name,
        start_date=start,
        end_date=start + timedelta(days=3),
        status=TournamentStatus.COMPLETED.value,
        is_team_event=True,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_team_entry(
    db,
    tournament: Tournament,
    golfer: Golfer,
    team_competitor_id: str,
    score_to_par: int,
    earnings: int = 0,
) -> TournamentEntry:
    entry = TournamentEntry(
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        earnings_usd=earnings,
        team_competitor_id=team_competitor_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    db.add(
        TournamentEntryRound(
            tournament_entry_id=entry.id,
            round_number=4,
            score_to_par=score_to_par,
        )
    )
    db.commit()
    return entry


class TestTeamEventLeaderboardPositions:
    def test_positions_not_double_counted_for_team_partners(self, client, db):
        """Each team should occupy exactly one position slot, not two."""
        tournament = _make_team_tournament(db)
        # Three teams at -10, -8, -6
        g1 = _make_golfer(db, "Player A1", ranking=1)
        g2 = _make_golfer(db, "Player A2", ranking=2)
        g3 = _make_golfer(db, "Player B1", ranking=3)
        g4 = _make_golfer(db, "Player B2", ranking=4)
        g5 = _make_golfer(db, "Player C1", ranking=5)
        g6 = _make_golfer(db, "Player C2", ranking=6)

        _make_team_entry(db, tournament, g1, "TEAM_A", score_to_par=-10, earnings=1_200_000)
        _make_team_entry(db, tournament, g2, "TEAM_A", score_to_par=-10, earnings=1_200_000)
        _make_team_entry(db, tournament, g3, "TEAM_B", score_to_par=-8, earnings=700_000)
        _make_team_entry(db, tournament, g4, "TEAM_B", score_to_par=-8, earnings=700_000)
        _make_team_entry(db, tournament, g5, "TEAM_C", score_to_par=-6, earnings=400_000)
        _make_team_entry(db, tournament, g6, "TEAM_C", score_to_par=-6, earnings=400_000)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200
        entries = resp.json()["entries"]

        pos_by_name = {e["golfer_name"]: e["finish_position"] for e in entries}

        # Both partners on Team A should be position 1
        assert pos_by_name["Player A1"] == 1
        assert pos_by_name["Player A2"] == 1

        # Team B: should be 2 (not 3 — without the fix, double-counting shifts it)
        assert pos_by_name["Player B1"] == 2
        assert pos_by_name["Player B2"] == 2

        # Team C: should be 3 (not 5)
        assert pos_by_name["Player C1"] == 3
        assert pos_by_name["Player C2"] == 3

    def test_is_tied_false_for_solo_leader(self, client, db):
        """The leading team with a unique score must NOT be marked as tied."""
        tournament = _make_team_tournament(db)
        g1 = _make_golfer(db, "Leader 1", ranking=1)
        g2 = _make_golfer(db, "Leader 2", ranking=2)
        g3 = _make_golfer(db, "Trailer 1", ranking=3)
        g4 = _make_golfer(db, "Trailer 2", ranking=4)

        _make_team_entry(db, tournament, g1, "TEAM_A", score_to_par=-12, earnings=1_200_000)
        _make_team_entry(db, tournament, g2, "TEAM_A", score_to_par=-12, earnings=1_200_000)
        _make_team_entry(db, tournament, g3, "TEAM_B", score_to_par=-8, earnings=700_000)
        _make_team_entry(db, tournament, g4, "TEAM_B", score_to_par=-8, earnings=700_000)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200
        entries = resp.json()["entries"]

        tied_by_name = {e["golfer_name"]: e["is_tied"] for e in entries}

        # Both leaders share a unique team score — not tied
        assert tied_by_name["Leader 1"] is False
        assert tied_by_name["Leader 2"] is False

    def test_is_tied_true_for_genuinely_tied_teams(self, client, db):
        """Two teams at the same score must both be marked tied."""
        tournament = _make_team_tournament(db)
        g1 = _make_golfer(db, "Tied A1", ranking=1)
        g2 = _make_golfer(db, "Tied A2", ranking=2)
        g3 = _make_golfer(db, "Tied B1", ranking=3)
        g4 = _make_golfer(db, "Tied B2", ranking=4)

        _make_team_entry(db, tournament, g1, "TEAM_A", score_to_par=-10, earnings=800_000)
        _make_team_entry(db, tournament, g2, "TEAM_A", score_to_par=-10, earnings=800_000)
        _make_team_entry(db, tournament, g3, "TEAM_B", score_to_par=-10, earnings=800_000)
        _make_team_entry(db, tournament, g4, "TEAM_B", score_to_par=-10, earnings=800_000)

        headers = _register_and_login(client)
        resp = client.get(f"/api/v1/tournaments/{tournament.id}/leaderboard", headers=headers)
        assert resp.status_code == 200
        entries = resp.json()["entries"]

        tied_by_name = {e["golfer_name"]: e["is_tied"] for e in entries}

        assert tied_by_name["Tied A1"] is True
        assert tied_by_name["Tied A2"] is True
        assert tied_by_name["Tied B1"] is True
        assert tied_by_name["Tied B2"] is True


# ---------------------------------------------------------------------------
# GET /tournaments/{id}/golfers/{gid}/scorecard — team_competitor_id routing
# ---------------------------------------------------------------------------


class TestScorecardEndpoint:
    def test_scorecard_passes_team_competitor_id_for_team_event(self, client, db, monkeypatch):
        """For a team event entry, fetch_golfer_scorecard must receive team_competitor_id."""
        tournament = _make_team_tournament(db, name="Scorecard Team Test")
        golfer = _make_golfer(db, "Team Golfer", ranking=5)
        entry = TournamentEntry(
            tournament_id=tournament.id,
            golfer_id=golfer.id,
            team_competitor_id="ESPN_TEAM_999",
        )
        db.add(entry)
        db.commit()

        calls: list[dict] = []

        def fake_scorecard(tournament, golfer, round_number, team_competitor_id=None):
            calls.append({"team_competitor_id": team_competitor_id})
            return {
                "golfer_id": str(golfer.id),
                "round_number": round_number,
                "holes": [],
                "total_score": None,
                "total_score_to_par": None,
            }

        monkeypatch.setattr(
            "app.services.scraper.fetch_golfer_scorecard",
            fake_scorecard,
        )

        headers = _register_and_login(client)
        resp = client.get(
            f"/api/v1/tournaments/{tournament.id}/golfers/{golfer.id}/scorecard?round=1",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(calls) == 1
        assert calls[0]["team_competitor_id"] == "ESPN_TEAM_999"

    def test_scorecard_passes_none_for_individual_event(self, client, db, monkeypatch):
        """For a non-team entry, team_competitor_id should be None."""
        start = date.today() - timedelta(days=5)
        tournament = Tournament(
            pga_tour_id=f"I{uuid.uuid4().hex[:6]}",
            name="Individual Open",
            start_date=start,
            end_date=start + timedelta(days=3),
            status=TournamentStatus.COMPLETED.value,
            is_team_event=False,
        )
        db.add(tournament)
        db.commit()
        db.refresh(tournament)

        golfer = _make_golfer(db, "Solo Golfer", ranking=10)
        entry = TournamentEntry(tournament_id=tournament.id, golfer_id=golfer.id)
        db.add(entry)
        db.commit()

        calls: list[dict] = []

        def fake_scorecard(tournament, golfer, round_number, team_competitor_id=None):
            calls.append({"team_competitor_id": team_competitor_id})
            return {
                "golfer_id": str(golfer.id),
                "round_number": round_number,
                "holes": [],
                "total_score": None,
                "total_score_to_par": None,
            }

        monkeypatch.setattr(
            "app.services.scraper.fetch_golfer_scorecard",
            fake_scorecard,
        )

        headers = _register_and_login(client)
        resp = client.get(
            f"/api/v1/tournaments/{tournament.id}/golfers/{golfer.id}/scorecard?round=1",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(calls) == 1
        assert calls[0]["team_competitor_id"] is None
