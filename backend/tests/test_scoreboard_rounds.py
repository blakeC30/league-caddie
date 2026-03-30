"""
Tests for the scoreboard-based round data optimization.

Covers:
  - _fetch_scoreboard_rounds() — parsing inline competitor data from the scoreboard
  - Round transition detection (scoreboard mode fallback to linescores)
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.models import (
    Golfer,
    Tournament,
    TournamentEntry,
    TournamentEntryRound,
    TournamentStatus,
)
from app.services.scraper import _fetch_scoreboard_rounds


def _make_scoreboard_response(pga_tour_id: str, competitors: list[dict]) -> dict:
    """Build a minimal scoreboard API response for testing."""
    return {
        "events": [
            {
                "id": pga_tour_id,
                "name": "Test Tournament",
                "date": "2026-03-26T10:00Z",
                "status": {"type": {"name": "STATUS_IN_PROGRESS"}},
                "competitions": [
                    {
                        "id": pga_tour_id,
                        "startDate": "2026-03-26T10:00Z",
                        "endDate": "2026-03-29T10:00Z",
                        "competitors": competitors,
                    }
                ],
            }
        ]
    }


def _make_competitor(
    aid: str,
    rounds: list[dict] | None = None,
) -> dict:
    """Build a minimal scoreboard competitor."""
    return {
        "id": int(aid),
        "order": 1,
        "type": "athlete",
        "athlete": {
            "fullName": f"Golfer {aid}",
            "displayName": f"Golfer {aid}",
            "flag": {"alt": "US"},
        },
        "score": "-5",
        "linescores": rounds or [],
    }


def _make_round(period: int, strokes: float | None, stp: str, holes: int) -> dict:
    """Build a minimal scoreboard round with hole data."""
    return {
        "period": period,
        "value": strokes,
        "displayValue": stp,
        "linescores": [{"value": 4.0, "period": i + 1} for i in range(holes)],
    }


# ---------------------------------------------------------------------------
# _fetch_scoreboard_rounds — parsing
# ---------------------------------------------------------------------------


class TestFetchScoreboardRounds:
    """Test scoreboard round data parsing."""

    def test_parses_completed_rounds(self):
        """A competitor with 4 completed rounds returns 4 round dicts."""
        comp = _make_competitor(
            "123",
            rounds=[
                _make_round(1, 68.0, "-4", 18),
                _make_round(2, 70.0, "-2", 18),
                _make_round(3, 65.0, "-7", 18),
                _make_round(4, 72.0, "E", 18),
            ],
        )
        data = _make_scoreboard_response("401", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("401")

        assert result is not None
        rounds_data, max_round = result
        assert "123" in rounds_data
        rounds = rounds_data["123"]
        assert len(rounds) == 4
        assert rounds[0]["round_number"] == 1
        assert rounds[0]["score"] == 68
        assert rounds[0]["score_to_par"] == -4
        assert rounds[0]["thru"] == 18
        assert rounds[3]["score_to_par"] == 0  # "E" → 0

    def test_parses_partial_round(self):
        """A competitor mid-round shows correct thru from hole count."""
        comp = _make_competitor(
            "456",
            rounds=[
                _make_round(1, 68.0, "-4", 18),  # completed
                _make_round(2, 35.0, "-1", 9),  # 9 holes through
            ],
        )
        data = _make_scoreboard_response("402", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("402")

        rounds = result[0]["456"]
        assert len(rounds) == 2
        assert rounds[1]["thru"] == 9
        assert rounds[1]["score"] == 35

    def test_skips_empty_future_rounds(self):
        """Rounds with no score and no holes (future rounds) are skipped."""
        comp = _make_competitor(
            "789",
            rounds=[
                _make_round(1, 68.0, "-4", 18),
                {"period": 2, "value": None, "displayValue": None, "linescores": []},
            ],
        )
        data = _make_scoreboard_response("403", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("403")

        rounds = result[0]["789"]
        assert len(rounds) == 1  # Only round 1

    def test_tee_time_is_none(self):
        """Scoreboard rounds have tee_time=None (not available from scoreboard)."""
        comp = _make_competitor("100", rounds=[_make_round(1, 70.0, "-2", 18)])
        data = _make_scoreboard_response("404", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("404")

        assert result[0]["100"][0]["tee_time"] is None

    def test_position_is_none(self):
        """Scoreboard rounds have position=None (not available)."""
        comp = _make_competitor("101", rounds=[_make_round(1, 70.0, "-2", 18)])
        data = _make_scoreboard_response("405", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("405")

        assert result[0]["101"][0]["position"] is None

    def test_is_playoff_is_false(self):
        """Scoreboard rounds always set is_playoff=False."""
        comp = _make_competitor("102", rounds=[_make_round(1, 70.0, "-2", 18)])
        data = _make_scoreboard_response("406", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("406")

        assert result[0]["102"][0]["is_playoff"] is False

    def test_tournament_not_found_returns_none(self):
        """If the tournament isn't in the scoreboard, returns None."""
        data = _make_scoreboard_response("999", [])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("000")  # Different ID

        assert result is None  # Tournament not found → None (not a tuple)

    def test_multiple_competitors(self):
        """Multiple competitors are all parsed."""
        comps = [
            _make_competitor("10", rounds=[_make_round(1, 68.0, "-4", 18)]),
            _make_competitor("20", rounds=[_make_round(1, 72.0, "E", 18)]),
            _make_competitor("30", rounds=[_make_round(1, 75.0, "+3", 12)]),
        ]
        data = _make_scoreboard_response("407", comps)
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("407")

        rounds_data = result[0]
        assert len(rounds_data) == 3
        assert rounds_data["10"][0]["score_to_par"] == -4
        assert rounds_data["20"][0]["score_to_par"] == 0
        assert rounds_data["30"][0]["score_to_par"] == 3
        assert rounds_data["30"][0]["thru"] == 12

    def test_positive_score_to_par(self):
        """Positive score-to-par like '+3' is parsed correctly."""
        comp = _make_competitor("50", rounds=[_make_round(1, 75.0, "+3", 18)])
        data = _make_scoreboard_response("408", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("408")

        assert result[0]["50"][0]["score_to_par"] == 3

    def test_fetch_failure_returns_none(self):
        """If the HTTP call fails, returns None gracefully."""
        with patch("app.services.scraper._get_json", side_effect=Exception("Network error")):
            result = _fetch_scoreboard_rounds("500")

        assert result is None

    def test_max_round_seen_includes_empty_future_rounds(self):
        """max_round_seen captures the highest round ESPN knows about,
        even if that round has no score data yet (critical for round transition)."""
        comp = _make_competitor(
            "200",
            rounds=[
                _make_round(1, 68.0, "-4", 18),
                # R2 exists but is empty — no score, no holes
                {"period": 2, "value": None, "displayValue": None, "linescores": []},
            ],
        )
        data = _make_scoreboard_response("409", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("409")

        assert result is not None
        rounds_data, max_round = result
        # The R2 entry should be stripped from rounds_data (no data to upsert)
        assert len(rounds_data["200"]) == 1  # Only R1
        # But max_round_seen should be 2 (ESPN knows about R2)
        assert max_round == 2

    def test_max_round_seen_with_all_rounds_played(self):
        """max_round_seen equals the highest played round when no future rounds exist."""
        comp = _make_competitor(
            "201",
            rounds=[
                _make_round(1, 68.0, "-4", 18),
                _make_round(2, 70.0, "-2", 18),
            ],
        )
        data = _make_scoreboard_response("410", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("410")

        _, max_round = result
        assert max_round == 2

    def test_max_round_seen_with_partial_r2_and_empty_r3(self):
        """Mid-tournament: R1 done, R2 in progress, R3 exists but empty."""
        comp = _make_competitor(
            "202",
            rounds=[
                _make_round(1, 68.0, "-4", 18),
                _make_round(2, 35.0, "-1", 9),
                {"period": 3, "value": None, "displayValue": None, "linescores": []},
            ],
        )
        data = _make_scoreboard_response("411", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("411")

        rounds_data, max_round = result
        assert len(rounds_data["202"]) == 2  # R1 + R2 (R3 stripped)
        assert max_round == 3  # But ESPN knows about R3


# ---------------------------------------------------------------------------
# Round transition detection — integration tests using the DB
# ---------------------------------------------------------------------------


def _make_db_tournament(db, *, status="in_progress") -> Tournament:
    """Create a tournament in the test DB."""
    t = Tournament(
        pga_tour_id=str(uuid.uuid4())[:8],
        name="Test Tournament",
        start_date=datetime.now(UTC).date() - timedelta(days=1),
        end_date=datetime.now(UTC).date() + timedelta(days=2),
        status=status,
    )
    db.add(t)
    db.flush()
    return t


def _make_db_golfer(db, pga_id: str = "12345") -> Golfer:
    g = Golfer(pga_tour_id=pga_id, name=f"Golfer {pga_id}")
    db.add(g)
    db.flush()
    return g


def _make_db_entry(db, tournament, golfer, *, tee_time=None) -> TournamentEntry:
    e = TournamentEntry(
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        tee_time=tee_time,
    )
    db.add(e)
    db.flush()
    return e


def _make_db_round(db, entry, round_number, *, tee_time=None) -> TournamentEntryRound:
    r = TournamentEntryRound(
        tournament_entry_id=entry.id,
        round_number=round_number,
        tee_time=tee_time,
    )
    db.add(r)
    db.flush()
    return r


class TestScoreboardModeDecision:
    """Test the use_scoreboard decision logic in sync_tournament.

    These tests verify the conditions under which sync_tournament chooses
    scoreboard mode vs linescores mode, including round transition detection.
    """

    def _get_use_scoreboard(self, db, tournament, sb_max_round: int = 0, force=False):
        """Replicate the use_scoreboard decision logic from sync_tournament.

        sb_max_round simulates the max_round_seen from _fetch_scoreboard_rounds,
        which includes empty/future rounds ESPN knows about.
        """
        from sqlalchemy import func as sqlfunc

        from app.services.picks import all_r1_teed_off

        if tournament.status != TournamentStatus.IN_PROGRESS.value or force:
            return False

        if not all_r1_teed_off(db, tournament.id):
            return False

        max_round_with_tee = (
            db.query(sqlfunc.max(TournamentEntryRound.round_number))
            .join(
                TournamentEntry,
                TournamentEntryRound.tournament_entry_id == TournamentEntry.id,
            )
            .filter(
                TournamentEntry.tournament_id == tournament.id,
                TournamentEntryRound.tee_time.isnot(None),
            )
            .scalar()
        ) or 0

        if sb_max_round > max_round_with_tee:
            return False

        return True

    def test_scheduled_tournament_uses_linescores(self, db):
        """Scheduled tournaments always use linescores (need tee times)."""
        t = _make_db_tournament(db, status="scheduled")
        assert self._get_use_scoreboard(db, t, 0) is False

    def test_completed_tournament_uses_linescores(self, db):
        """Completed tournaments always use linescores (full historical data)."""
        t = _make_db_tournament(db, status="completed")
        assert self._get_use_scoreboard(db, t, 0) is False

    def test_force_sync_uses_linescores(self, db):
        """Force sync always uses linescores even if all R1 teed off."""
        t = _make_db_tournament(db)
        g = _make_db_golfer(db, "force1")
        e = _make_db_entry(db, t, g, tee_time=datetime.now(UTC) - timedelta(hours=3))
        _make_db_round(db, e, 1, tee_time=datetime.now(UTC) - timedelta(hours=3))
        db.commit()

        assert self._get_use_scoreboard(db, t, 1, force=True) is False

    def test_r1_not_teed_off_uses_linescores(self, db):
        """Before all R1 tee times pass, linescores are used for pick-locking accuracy."""
        t = _make_db_tournament(db)
        g = _make_db_golfer(db, "notteed1")
        # Tee time in the future — not yet teed off
        e = _make_db_entry(db, t, g, tee_time=datetime.now(UTC) + timedelta(hours=2))
        _make_db_round(db, e, 1, tee_time=datetime.now(UTC) + timedelta(hours=2))
        db.commit()

        assert self._get_use_scoreboard(db, t, 1) is False

    def test_all_r1_teed_off_same_round_uses_scoreboard(self, db):
        """After all R1 teed off and ESPN is on the same round, use scoreboard."""
        t = _make_db_tournament(db)
        g = _make_db_golfer(db, "teed1")
        e = _make_db_entry(db, t, g, tee_time=datetime.now(UTC) - timedelta(hours=3))
        _make_db_round(db, e, 1, tee_time=datetime.now(UTC) - timedelta(hours=3))
        db.commit()

        result = self._get_use_scoreboard(db, t, 1)
        assert result is True

    def test_round_transition_r1_to_r2_uses_linescores(self, db):
        """When ESPN reports Round 2 but we only have R1 tee times, use linescores."""
        t = _make_db_tournament(db)
        g = _make_db_golfer(db, "trans1")
        e = _make_db_entry(db, t, g, tee_time=datetime.now(UTC) - timedelta(hours=20))
        _make_db_round(db, e, 1, tee_time=datetime.now(UTC) - timedelta(hours=20))
        db.commit()

        # ESPN knows about Round 2, but we only have R1 tee times
        result = self._get_use_scoreboard(db, t, 2)
        assert result is False

    def test_round_transition_resolved_uses_scoreboard(self, db):
        """After R2 tee times are fetched, scoreboard mode resumes."""
        t = _make_db_tournament(db)
        g = _make_db_golfer(db, "resolved1")
        e = _make_db_entry(db, t, g, tee_time=datetime.now(UTC) - timedelta(hours=20))
        _make_db_round(db, e, 1, tee_time=datetime.now(UTC) - timedelta(hours=20))
        _make_db_round(db, e, 2, tee_time=datetime.now(UTC) - timedelta(hours=3))
        db.commit()

        # ESPN shows Round 2 and we have R2 tee times
        result = self._get_use_scoreboard(db, t, 2)
        assert result is True

    def test_round_transition_r2_to_r3(self, db):
        """Round 3 start with only R1+R2 tee times triggers linescores."""
        t = _make_db_tournament(db)
        g = _make_db_golfer(db, "r3trans1")
        e = _make_db_entry(db, t, g, tee_time=datetime.now(UTC) - timedelta(hours=30))
        _make_db_round(db, e, 1, tee_time=datetime.now(UTC) - timedelta(hours=30))
        _make_db_round(db, e, 2, tee_time=datetime.now(UTC) - timedelta(hours=10))
        db.commit()

        result = self._get_use_scoreboard(db, t, 3)
        assert result is False

    def test_r2_tee_times_null_stays_in_linescores(self, db):
        """R2 round exists but tee_time is NULL — ESPN hasn't published yet."""
        t = _make_db_tournament(db)
        g = _make_db_golfer(db, "nulltee1")
        e = _make_db_entry(db, t, g, tee_time=datetime.now(UTC) - timedelta(hours=20))
        _make_db_round(db, e, 1, tee_time=datetime.now(UTC) - timedelta(hours=20))
        _make_db_round(db, e, 2, tee_time=None)  # No tee time yet
        db.commit()

        # ESPN knows about Round 2, but max round with tee_time is still 1
        result = self._get_use_scoreboard(db, t, 2)
        assert result is False

    def test_sb_max_round_zero_defaults_to_scoreboard(self, db):
        """If scoreboard fetch failed (max_round=0), default to scoreboard mode."""
        t = _make_db_tournament(db)
        g = _make_db_golfer(db, "noperiod1")
        e = _make_db_entry(db, t, g, tee_time=datetime.now(UTC) - timedelta(hours=3))
        _make_db_round(db, e, 1, tee_time=datetime.now(UTC) - timedelta(hours=3))
        db.commit()

        # sb_max_round=0 means scoreboard fetch failed — don't detect transition
        result = self._get_use_scoreboard(db, t, 0)
        assert result is True

    def test_multiple_golfers_all_teed_off(self, db):
        """Scoreboard mode works with multiple golfers, all teed off."""
        t = _make_db_tournament(db)
        for i in range(5):
            g = _make_db_golfer(db, f"multi{i}")
            tee = datetime.now(UTC) - timedelta(hours=3, minutes=i * 10)
            e = _make_db_entry(db, t, g, tee_time=tee)
            _make_db_round(db, e, 1, tee_time=tee)
        db.commit()

        result = self._get_use_scoreboard(db, t, 1)
        assert result is True

    def test_one_golfer_not_teed_off_blocks_scoreboard(self, db):
        """If even one golfer hasn't teed off in R1, stay in linescores."""
        t = _make_db_tournament(db)
        g1 = _make_db_golfer(db, "block1")
        g2 = _make_db_golfer(db, "block2")
        past = datetime.now(UTC) - timedelta(hours=3)
        future = datetime.now(UTC) + timedelta(hours=1)
        e1 = _make_db_entry(db, t, g1, tee_time=past)
        _make_db_round(db, e1, 1, tee_time=past)
        e2 = _make_db_entry(db, t, g2, tee_time=future)
        _make_db_round(db, e2, 1, tee_time=future)
        db.commit()

        result = self._get_use_scoreboard(db, t, 1)
        assert result is False
