"""
Tests for the scoreboard-based round data optimization.

Covers:
  - _fetch_scoreboard_rounds() — parsing inline competitor data from the scoreboard
  - Round transition detection (scoreboard mode fallback to linescores)
"""

from unittest.mock import patch

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
        assert "123" in result
        rounds = result["123"]
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

        rounds = result["456"]
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

        rounds = result["789"]
        assert len(rounds) == 1  # Only round 1

    def test_tee_time_is_none(self):
        """Scoreboard rounds have tee_time=None (not available from scoreboard)."""
        comp = _make_competitor("100", rounds=[_make_round(1, 70.0, "-2", 18)])
        data = _make_scoreboard_response("404", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("404")

        assert result["100"][0]["tee_time"] is None

    def test_position_is_none(self):
        """Scoreboard rounds have position=None (not available)."""
        comp = _make_competitor("101", rounds=[_make_round(1, 70.0, "-2", 18)])
        data = _make_scoreboard_response("405", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("405")

        assert result["101"][0]["position"] is None

    def test_is_playoff_is_false(self):
        """Scoreboard rounds always set is_playoff=False."""
        comp = _make_competitor("102", rounds=[_make_round(1, 70.0, "-2", 18)])
        data = _make_scoreboard_response("406", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("406")

        assert result["102"][0]["is_playoff"] is False

    def test_tournament_not_found_returns_none(self):
        """If the tournament isn't in the scoreboard, returns None."""
        data = _make_scoreboard_response("999", [])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("000")  # Different ID

        assert result is None

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

        assert len(result) == 3
        assert result["10"][0]["score_to_par"] == -4
        assert result["20"][0]["score_to_par"] == 0
        assert result["30"][0]["score_to_par"] == 3
        assert result["30"][0]["thru"] == 12

    def test_positive_score_to_par(self):
        """Positive score-to-par like '+3' is parsed correctly."""
        comp = _make_competitor("50", rounds=[_make_round(1, 75.0, "+3", 18)])
        data = _make_scoreboard_response("408", [comp])
        with patch("app.services.scraper._get_json", return_value=data):
            result = _fetch_scoreboard_rounds("408")

        assert result["50"][0]["score_to_par"] == 3

    def test_fetch_failure_returns_none(self):
        """If the HTTP call fails, returns None gracefully."""
        with patch("app.services.scraper._get_json", side_effect=Exception("Network error")):
            result = _fetch_scoreboard_rounds("500")

        assert result is None
