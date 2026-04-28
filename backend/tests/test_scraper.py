"""
Tests for the scraper service.

These are unit tests — no HTTP is made. httpx calls are intercepted by
pytest-httpx (or unittest.mock) so tests run without a network connection.

What's tested here:
  - parse_schedule_response()  — JSON → tournament dicts (including team event detection)
  - upsert_tournaments()       — create new / update existing tournament rows
  - upsert_field()             — create new / update existing golfer + entry rows
  - score_picks()              — points_earned set correctly after results land
  - _fetch_team_roster()       — correct URL construction (event ID required)
  - _fetch_team_field()        — linescores fetched at team level; tee times propagate

The high-level sync_* functions (which make real HTTP calls) are integration
tests and run only when the ESPN API is reachable. They are not included here.
"""

from datetime import UTC, date, datetime, timedelta

import httpx

from app.services.scraper import (
    _fetch_competitor_rounds,
    _fetch_team_field,
    _fetch_team_roster,
    _map_espn_status,
    _parse_date,
    parse_schedule_response,
    score_picks,
    upsert_tournaments,
)

UTC = UTC

# ---------------------------------------------------------------------------
# Fixtures — sample ESPN API payloads
# ---------------------------------------------------------------------------

SCOREBOARD_PAYLOAD = {
    "events": [
        {
            "id": "401580001",
            "name": "The Masters",
            "date": "2025-04-10T10:00Z",
            "status": {"type": {"name": "STATUS_FINAL"}},
            "competitions": [
                {
                    "startDate": "2025-04-10T10:00Z",
                    "endDate": "2025-04-13T20:00Z",
                }
            ],
        },
        {
            "id": "401580002",
            "name": "AT&T Pebble Beach Pro-Am",
            "date": "2025-02-06T14:00Z",
            "status": {"type": {"name": "STATUS_SCHEDULED"}},
            "competitions": [
                {
                    "startDate": "2025-02-06T14:00Z",
                    "endDate": "2025-02-09T22:00Z",
                }
            ],
        },
    ]
}

# ESPN scoreboard payload for a team-format tournament (Zurich Classic style).
# competitors[0].type == "team" triggers is_team_event=True detection.
# The competition id ("11450") differs from the event id ("401703507").
TEAM_EVENT_PAYLOAD = {
    "events": [
        {
            "id": "401703507",
            "name": "Zurich Classic of New Orleans",
            "date": "2025-04-24T14:00Z",
            "status": {"type": {"name": "STATUS_SCHEDULED"}},
            "competitions": [
                {
                    "id": "11450",
                    "startDate": "2025-04-24T14:00Z",
                    "endDate": "2025-04-27T22:00Z",
                    "competitors": [
                        {"id": "131066", "type": "team", "order": 1},
                        {"id": "131067", "type": "team", "order": 2},
                    ],
                }
            ],
        }
    ]
}

# Some ESPN responses nest events under leagues instead of top-level.
SCOREBOARD_PAYLOAD_NESTED = {
    "leagues": [
        {
            "events": SCOREBOARD_PAYLOAD["events"],
        }
    ]
}


# ---------------------------------------------------------------------------
# parse_schedule_response
# ---------------------------------------------------------------------------


class TestParseScheduleResponse:
    def test_extracts_both_events(self):
        result, _ = parse_schedule_response(SCOREBOARD_PAYLOAD)
        assert len(result) == 2

    def test_extracts_correct_fields(self):
        result, _ = parse_schedule_response(SCOREBOARD_PAYLOAD)
        masters = next(t for t in result if t["pga_tour_id"] == "401580001")

        assert masters["name"] == "The Masters"
        assert masters["start_date"] == date(2025, 4, 10)
        assert masters["end_date"] == date(2025, 4, 13)
        assert masters["status"] == "completed"
        assert (
            masters["is_team_event"] is False
        )  # scraper never sets multiplier — admin does that on league_tournaments

    def test_handles_nested_leagues_structure(self):
        """ESPN sometimes wraps events under leagues[i].events."""
        result, _ = parse_schedule_response(SCOREBOARD_PAYLOAD_NESTED)
        assert len(result) == 2

    def test_status_mapping(self):
        result, _ = parse_schedule_response(SCOREBOARD_PAYLOAD)
        pebble = next(t for t in result if t["pga_tour_id"] == "401580002")
        assert pebble["status"] == "scheduled"

    def test_skips_events_without_id(self):
        data = {"events": [{"name": "No ID Event", "date": "2025-01-01T00:00Z"}]}
        result, _ = parse_schedule_response(data)
        assert result == []

    def test_skips_events_without_date(self):
        data = {"events": [{"id": "123", "name": "No Date", "competitions": [{}]}]}
        result, _ = parse_schedule_response(data)
        assert result == []

    def test_falls_back_to_event_date_if_no_competition(self):
        data = {
            "events": [
                {
                    "id": "555",
                    "name": "Fallback Test",
                    "date": "2025-07-01T10:00Z",
                    "status": {"type": {"name": "STATUS_SCHEDULED"}},
                    "competitions": [],
                }
            ]
        }
        result, _ = parse_schedule_response(data)
        assert len(result) == 1
        assert result[0]["start_date"] == date(2025, 7, 1)
        # end_date falls back to start_date + 3 days
        assert result[0]["end_date"] == date(2025, 7, 4)

    def test_empty_response(self):
        assert parse_schedule_response({}) == ([], {})
        assert parse_schedule_response({"events": []}) == ([], {})

    def test_individual_event_not_team(self):
        """Standard individual tournaments must have is_team_event=False."""
        result, _ = parse_schedule_response(SCOREBOARD_PAYLOAD)
        masters = next(t for t in result if t["pga_tour_id"] == "401580001")
        assert masters["is_team_event"] is False

    def test_individual_event_competition_id_matches_event_id(self):
        """For standard tournaments, competition_id should equal pga_tour_id."""
        result, _ = parse_schedule_response(SCOREBOARD_PAYLOAD)
        masters = next(t for t in result if t["pga_tour_id"] == "401580001")
        assert masters["competition_id"] == "401580001"

    def test_team_event_detected(self):
        """Zurich-style events with type='team' competitors must set is_team_event=True."""
        result, _ = parse_schedule_response(TEAM_EVENT_PAYLOAD)
        assert len(result) == 1
        zurich = result[0]
        assert zurich["is_team_event"] is True

    def test_team_event_competition_id_differs_from_event_id(self):
        """Team events expose a different competition id (e.g. '11450' vs '401703507')."""
        result, _ = parse_schedule_response(TEAM_EVENT_PAYLOAD)
        zurich = result[0]
        assert zurich["pga_tour_id"] == "401703507"
        assert zurich["competition_id"] == "11450"


# ---------------------------------------------------------------------------
# _map_espn_status and _parse_date (pure helpers)
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_status_mapping_scheduled(self):
        assert _map_espn_status("STATUS_SCHEDULED") == "scheduled"

    def test_status_mapping_in_progress(self):
        assert _map_espn_status("STATUS_IN_PROGRESS") == "in_progress"

    def test_status_mapping_final(self):
        assert _map_espn_status("STATUS_FINAL") == "completed"

    def test_status_mapping_unknown_defaults_to_scheduled(self):
        assert _map_espn_status("SOME_UNKNOWN_VALUE") == "scheduled"

    def test_parse_date_espn_format(self):
        assert _parse_date("2025-04-10T10:00Z") == date(2025, 4, 10)

    def test_parse_date_none(self):
        assert _parse_date(None) is None

    def test_parse_date_empty_string(self):
        assert _parse_date("") is None

    def test_parse_date_invalid(self):
        assert _parse_date("not-a-date") is None


# ---------------------------------------------------------------------------
# upsert_tournaments (DB tests — require the test database)
# ---------------------------------------------------------------------------


class TestUpsertTournaments:
    def test_creates_new_tournaments(self, db):
        parsed = [
            {
                "pga_tour_id": "ESPN_001",
                "name": "Test Open",
                "start_date": date(2025, 6, 1),
                "end_date": date(2025, 6, 4),
                "status": "scheduled",
            }
        ]
        created, updated, transitions = upsert_tournaments(db, parsed)
        assert created == 1
        assert updated == 0
        assert transitions == []

        from app.models import Tournament

        t = db.query(Tournament).filter_by(pga_tour_id="ESPN_001").first()
        assert t is not None
        assert t.name == "Test Open"

    def test_updates_existing_tournament(self, db):
        from app.models import Tournament

        db.add(
            Tournament(
                pga_tour_id="ESPN_002",
                name="Old Name",
                start_date=date(2025, 7, 1),
                end_date=date(2025, 7, 4),
                status="scheduled",
            )
        )
        db.commit()

        parsed = [
            {
                "pga_tour_id": "ESPN_002",
                "name": "New Name",
                "start_date": date(2025, 7, 1),
                "end_date": date(2025, 7, 4),
                "status": "completed",
            }
        ]
        created, updated, transitions = upsert_tournaments(db, parsed)
        assert created == 0
        assert updated == 1
        assert len(transitions) == 1
        assert transitions[0][1] == "scheduled"
        assert transitions[0][2] == "completed"

        t = db.query(Tournament).filter_by(pga_tour_id="ESPN_002").first()
        assert t.name == "New Name"
        assert t.status == "completed"

    def test_does_not_overwrite_competition_id(self, db):
        """Manually-set competition_id must survive a sync."""
        from app.models import Tournament

        db.add(
            Tournament(
                pga_tour_id="ESPN_003",
                name="The Masters",
                start_date=date(2025, 4, 10),
                end_date=date(2025, 4, 13),
                status="scheduled",
                competition_id="MANUAL_001",
            )
        )
        db.commit()

        parsed = [
            {
                "pga_tour_id": "ESPN_003",
                "name": "The Masters",
                "start_date": date(2025, 4, 10),
                "end_date": date(2025, 4, 13),
                "status": "completed",
                "competition_id": "NEW_001",
            }
        ]
        upsert_tournaments(db, parsed)

        t = db.query(Tournament).filter_by(pga_tour_id="ESPN_003").first()
        assert t.competition_id == "MANUAL_001"  # unchanged


# ---------------------------------------------------------------------------
# score_picks (DB tests)
# ---------------------------------------------------------------------------


class TestScorePicks:
    def test_scores_completed_picks(self, db):
        from datetime import date

        from app.models import (
            Golfer,
            League,
            LeagueMember,
            LeagueMemberRole,
            LeagueTournament,
            Pick,
            Season,
            Tournament,
            TournamentEntry,
            TournamentStatus,
            User,
        )
        from app.services.auth import hash_password

        # Set up minimal data.
        user = User(
            email="scorer@example.com",
            password_hash=hash_password("x"),
            display_name="S",
        )
        db.add(user)
        db.flush()

        league = League(name="SL", created_by=user.id)
        db.add(league)
        db.flush()

        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.MANAGER.value,
            )
        )
        season = Season(league_id=league.id, year=2025, is_active=True)
        db.add(season)
        db.flush()

        golfer = Golfer(pga_tour_id="G001", name="Test Golfer")
        db.add(golfer)
        db.flush()

        t_start = date.today() - timedelta(days=7)
        tournament = Tournament(
            pga_tour_id="T001",
            name="Score Test Open",
            start_date=t_start,
            end_date=t_start + timedelta(days=3),
            status=TournamentStatus.COMPLETED.value,
        )
        db.add(tournament)
        db.flush()

        # League-level multiplier (2× for majors).
        db.add(LeagueTournament(league_id=league.id, tournament_id=tournament.id, multiplier=2.0))

        entry = TournamentEntry(
            tournament_id=tournament.id,
            golfer_id=golfer.id,
            finish_position=1,
            earnings_usd=3_600_000,
        )
        db.add(entry)
        db.flush()

        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        db.add(pick)
        db.commit()

        count = score_picks(db, tournament)
        assert count == 1

        db.refresh(pick)
        assert pick.points_earned == 7_200_000.0  # 3_600_000 × 2.0

    def test_missed_cut_scores_zero(self, db):
        from datetime import date

        from app.models import (
            Golfer,
            League,
            LeagueMember,
            LeagueMemberRole,
            Pick,
            Season,
            Tournament,
            TournamentEntry,
            TournamentStatus,
            User,
        )
        from app.services.auth import hash_password

        user = User(email="cut@example.com", password_hash=hash_password("x"), display_name="C")
        db.add(user)
        db.flush()

        league = League(name="CL", created_by=user.id)
        db.add(league)
        db.flush()

        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.MANAGER.value,
            )
        )
        season = Season(league_id=league.id, year=2025, is_active=True)
        db.add(season)
        db.flush()

        golfer = Golfer(pga_tour_id="G002", name="Cut Golfer")
        db.add(golfer)
        db.flush()

        t_start = date.today() - timedelta(days=7)
        tournament = Tournament(
            pga_tour_id="T002",
            name="Cut Test",
            start_date=t_start,
            end_date=t_start + timedelta(days=3),
            status=TournamentStatus.COMPLETED.value,
        )
        db.add(tournament)
        db.flush()

        # Golfer missed cut — no earnings.
        entry = TournamentEntry(
            tournament_id=tournament.id,
            golfer_id=golfer.id,
            status="cut",
            earnings_usd=None,
        )
        db.add(entry)
        db.flush()

        pick = Pick(
            league_id=league.id,
            season_id=season.id,
            user_id=user.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )
        db.add(pick)
        db.commit()

        count = score_picks(db, tournament)
        assert count == 1

        db.refresh(pick)
        assert pick.points_earned == 0.0

    def test_skips_non_completed_tournament(self, db):
        from datetime import date

        from app.models import Tournament, TournamentStatus

        t_start = date.today() + timedelta(days=7)
        tournament = Tournament(
            pga_tour_id="T003",
            name="Future Open",
            start_date=t_start,
            end_date=t_start + timedelta(days=3),
            status=TournamentStatus.SCHEDULED.value,
        )
        db.add(tournament)
        db.commit()

        count = score_picks(db, tournament)
        assert count == 0


# ---------------------------------------------------------------------------
# _fetch_competitor_rounds: phantom round filtering
# ---------------------------------------------------------------------------


class TestFetchCompetitorRoundsPhantomFiltering:
    """ESPN includes phantom future rounds for CUT/WD players (e.g. R3 for
    a player who missed the R2 cut). These have value=0, displayValue="-",
    and an empty linescores array. They must be filtered out to avoid
    creating DB rows that block allFinishedCurrentRound on the frontend."""

    def _make_linescores_response(self, rounds_data):
        """Build a minimal ESPN /linescores JSON response."""
        items = []
        for rd in rounds_data:
            item = {"period": rd["period"]}
            if "value" in rd:
                item["value"] = rd["value"]
            if "displayValue" in rd:
                item["displayValue"] = rd["displayValue"]
            if "teeTime" in rd:
                item["teeTime"] = rd["teeTime"]
            if "linescores" in rd:
                item["linescores"] = rd["linescores"]
            else:
                item["linescores"] = []
            items.append(item)
        return {"items": items}

    def test_phantom_round_for_cut_player_is_skipped(self):
        """CUT player: R1+R2 completed, phantom R3 (value=0, display='-').
        Only R1 and R2 should be returned."""
        from unittest.mock import MagicMock, patch

        import httpx

        response_data = self._make_linescores_response(
            [
                {
                    "period": 1,
                    "value": 75.0,
                    "displayValue": "+3",
                    "teeTime": "2026-04-09T14:00Z",
                    "linescores": [{"displayValue": "4"}] * 18,
                },
                {
                    "period": 2,
                    "value": 77.0,
                    "displayValue": "+5",
                    "teeTime": "2026-04-10T14:30Z",
                    "linescores": [{"displayValue": "4"}] * 18,
                },
                {
                    "period": 3,
                    "value": 0.0,
                    "displayValue": "-",
                    "linescores": [],
                },
            ]
        )

        response = httpx.Response(200, json=response_data)
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = lambda s: s
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.return_value = response

            aid, rounds = _fetch_competitor_rounds("401811941", "401811941", "5532")

        assert len(rounds) == 2
        assert rounds[0]["round_number"] == 1
        assert rounds[1]["round_number"] == 2
        # R3 phantom should NOT be in the results

    def test_real_future_round_with_tee_time_is_kept(self):
        """A golfer who made the cut has R3 with a tee time but no score
        yet. This is NOT a phantom — it's a real upcoming round."""
        from unittest.mock import MagicMock, patch

        import httpx

        response_data = self._make_linescores_response(
            [
                {
                    "period": 1,
                    "value": 68.0,
                    "displayValue": "-4",
                    "teeTime": "2026-04-09T14:00Z",
                    "linescores": [{"displayValue": "4"}] * 18,
                },
                {
                    "period": 2,
                    "value": 70.0,
                    "displayValue": "-2",
                    "teeTime": "2026-04-10T14:30Z",
                    "linescores": [{"displayValue": "4"}] * 18,
                },
                {
                    "period": 3,
                    "value": 0.0,
                    "displayValue": "-",
                    "teeTime": "2026-04-11T15:00Z",
                    "linescores": [],
                },
            ]
        )

        response = httpx.Response(200, json=response_data)
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = lambda s: s
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.return_value = response

            aid, rounds = _fetch_competitor_rounds("401811941", "401811941", "1234")

        assert len(rounds) == 3
        # R3 has a tee time → it's a real round, not a phantom
        assert rounds[2]["round_number"] == 3
        assert rounds[2]["tee_time"] is not None

    def test_mid_round_with_played_holes_is_kept(self):
        """A golfer currently playing R2 with 6 holes done. This must NOT
        be filtered out — it has real hole data."""
        from unittest.mock import MagicMock, patch

        import httpx

        response_data = self._make_linescores_response(
            [
                {
                    "period": 1,
                    "value": 72.0,
                    "displayValue": "E",
                    "teeTime": "2026-04-09T14:00Z",
                    "linescores": [{"displayValue": "4"}] * 18,
                },
                {
                    "period": 2,
                    "value": 20.0,
                    "displayValue": "-3",
                    "teeTime": "2026-04-10T14:30Z",
                    "linescores": [{"displayValue": "3"}] * 6,
                },
            ]
        )

        response = httpx.Response(200, json=response_data)
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__ = lambda s: s
            mock_client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.return_value.get.return_value = response

            aid, rounds = _fetch_competitor_rounds("401811941", "401811941", "11119")

        assert len(rounds) == 2
        assert rounds[1]["round_number"] == 2
        assert rounds[1]["thru"] == 6


# ---------------------------------------------------------------------------
# _fetch_team_roster: URL construction and response parsing
# ---------------------------------------------------------------------------


class TestFetchTeamRoster:
    """
    The roster endpoint requires /events/{pga_tour_id}/ in the path.
    Previously the URL was missing the event segment, causing every call to
    return 404 and the sync to store zero entries for the Zurich Classic.
    """

    def test_url_includes_event_id(self):
        from unittest.mock import patch

        with patch("app.services.scraper._get_json") as mock_get:
            mock_get.return_value = {"entries": []}
            _fetch_team_roster("EVT001", "COMP001", "TEAM001")

        called_url = mock_get.call_args[0][0]
        assert "/events/EVT001/" in called_url
        assert "/competitions/COMP001/" in called_url
        assert "/competitors/TEAM001/roster" in called_url

    def test_returns_athlete_ids_as_strings(self):
        from unittest.mock import patch

        with patch("app.services.scraper._get_json") as mock_get:
            mock_get.return_value = {"entries": [{"playerId": 6011}, {"playerId": 7001}]}
            result = _fetch_team_roster("EVT001", "COMP001", "TEAM001")

        assert result == ["6011", "7001"]

    def test_skips_entries_without_player_id(self):
        from unittest.mock import patch

        with patch("app.services.scraper._get_json") as mock_get:
            mock_get.return_value = {"entries": [{"playerId": 6011}, {}, {"playerId": None}]}
            result = _fetch_team_roster("EVT001", "COMP001", "TEAM001")

        assert result == ["6011"]

    def test_returns_empty_list_on_http_error(self):
        from unittest.mock import MagicMock, patch

        with patch("app.services.scraper._get_json") as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
            result = _fetch_team_roster("EVT001", "COMP001", "TEAM001")

        assert result == []


# ---------------------------------------------------------------------------
# _fetch_team_field: team-level linescores, tee-time propagation, copy safety
# ---------------------------------------------------------------------------


def _processed_round(round_number: int = 1, tee_time_str: str = "2026-04-23T12:00Z") -> dict:
    """Return a fully-processed round dict as _fetch_competitor_rounds would produce."""
    return {
        "round_number": round_number,
        "tee_time": datetime.fromisoformat(tee_time_str.replace("Z", "+00:00")),
        "score": None,
        "score_to_par": None,
        "position": None,
        "is_playoff": False,
        "thru": None,
        "started_on_back": None,
        "_has_back_nine_linescore": True,
    }


# Two-team fixture used by all TestFetchTeamField tests.
_TWO_TEAMS_RESPONSE = {
    "items": [
        {"id": "TEAM001", "type": "team", "order": 1},
        {"id": "TEAM002", "type": "team", "order": 2},
    ]
}


class TestFetchTeamField:
    """
    _fetch_team_field must fetch linescores and status at the team-competitor
    level, not at the individual-athlete level.  Individual-athlete linescores
    return count=0 for team events like the Zurich Classic.
    """

    def _patch_all(self, roster_return=None, rounds_by_team=None):
        """Return a context-manager stack that mocks every HTTP helper."""
        from contextlib import ExitStack
        from unittest.mock import patch

        roster_return = roster_return or ["A1", "A2"]

        def fake_roster(pga_tour_id, competition_id, team_id):
            return roster_return

        def fake_athlete_info(aid):
            return {"pga_tour_id": aid, "name": f"Golfer {aid}", "country": None}

        def fake_rounds(pga, comp, tid):
            rds = (rounds_by_team or {}).get(tid, [_processed_round()])
            return tid, rds

        def fake_status(pga, comp, tid):
            return tid, None, None, None

        stack = ExitStack()
        stack.enter_context(
            patch("app.services.scraper._get_json", return_value=_TWO_TEAMS_RESPONSE)
        )
        stack.enter_context(
            patch("app.services.scraper._fetch_team_roster", side_effect=fake_roster)
        )
        stack.enter_context(
            patch("app.services.scraper._fetch_athlete_info", side_effect=fake_athlete_info)
        )
        mock_rounds = stack.enter_context(
            patch("app.services.scraper._fetch_competitor_rounds", side_effect=fake_rounds)
        )
        stack.enter_context(
            patch("app.services.scraper._fetch_competitor_status", side_effect=fake_status)
        )
        return stack, mock_rounds

    def test_linescores_fetched_by_team_id_not_athlete_id(self):
        """_fetch_competitor_rounds must be called with TEAM001/TEAM002, never
        with the individual athlete IDs A1/A2."""
        stack, mock_rounds = self._patch_all(roster_return=["A1", "A2"])
        with stack:
            _fetch_team_field("EVT001", "COMP001", fetch_round_data=True)

        called_ids = {call.args[2] for call in mock_rounds.call_args_list}
        assert "TEAM001" in called_ids
        assert "TEAM002" in called_ids
        assert "A1" not in called_ids
        assert "A2" not in called_ids

    def test_tee_time_propagates_to_both_athletes_in_team(self):
        """Both golfers on a team must receive the team's Round 1 tee time."""
        tee_time = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
        rounds_by_team = {
            "TEAM001": [_processed_round(1, "2026-04-23T12:00Z")],
            "TEAM002": [_processed_round(1, "2026-04-23T13:00Z")],
        }
        stack, _ = self._patch_all(roster_return=["A1", "A2"], rounds_by_team=rounds_by_team)
        with stack:
            _, results = _fetch_team_field("EVT001", "COMP001", fetch_round_data=True)

        # Four results total: A1+A2 on TEAM001, A1+A2 on TEAM002 (roster
        # returns ["A1","A2"] for every team in this fixture).
        team001_results = [r for r in results if r["team_competitor_id"] == "TEAM001"]
        assert len(team001_results) == 2
        for r in team001_results:
            assert r["tee_time"] == tee_time, f"Expected {tee_time}, got {r['tee_time']}"

    def test_round_dicts_are_independent_per_athlete(self):
        """Each athlete gets its own copy of the round dicts so mutations in
        the per-athlete processing loop (started_on_back, _has_back_nine pop)
        don't bleed through to the partner athlete."""
        stack, _ = self._patch_all(roster_return=["A1", "A2"])
        with stack:
            _, results = _fetch_team_field("EVT001", "COMP001", fetch_round_data=True)

        team001_results = [r for r in results if r["team_competitor_id"] == "TEAM001"]
        assert len(team001_results) == 2
        r0_rounds = team001_results[0]["rounds"]
        r1_rounds = team001_results[1]["rounds"]
        # Lists must be different objects.
        assert r0_rounds is not r1_rounds
        # The round dicts inside must also be different objects.
        assert r0_rounds[0] is not r1_rounds[0]

    def test_returns_empty_when_no_competitors(self):
        """If ESPN returns no team competitors, both lists come back empty."""
        from unittest.mock import patch

        with patch("app.services.scraper._get_json", return_value={"items": []}):
            golfers, results = _fetch_team_field("EVT001", "COMP001", fetch_round_data=True)

        assert golfers == []
        assert results == []


# ---------------------------------------------------------------------------
# Round-count CUT inference fallback
# ---------------------------------------------------------------------------


class TestFetchTeamFieldCutInference:
    """
    _fetch_team_field infers status='CUT' for teams with played rounds but
    fewer than the max. This covers completed events where ESPN's site
    leaderboard no longer returns shortDetail='CUT' (it reverts to 'F' once
    the event is final), and the Core /status endpoint only returns a $ref
    for team events.
    """

    _THREE_TEAMS = {
        "items": [
            {"id": "TEAM001", "type": "team", "order": 1},
            {"id": "TEAM002", "type": "team", "order": 2},
            {"id": "TEAM003", "type": "team", "order": 3},
        ]
    }

    def _build_rounds(self, count: int) -> list[dict]:
        return [_processed_round(r) for r in range(1, count + 1)]

    def _patch_all(
        self,
        rounds_by_team: dict,
        leaderboard_statuses: dict | None = None,
        status_fn=None,
    ):
        """Patch all ESPN HTTP helpers. Returns an ExitStack context manager.

        Args:
            rounds_by_team: team_id → list of round dicts
            leaderboard_statuses: what _fetch_start_holes returns as the
                statuses dict. Defaults to {} (nothing from leaderboard).
            status_fn: optional override for _fetch_competitor_status; receives
                (pga, comp, tid) and returns (tid, short_detail, round, hole).
                Defaults to always returning (tid, None, None, None).
        """
        from contextlib import ExitStack
        from unittest.mock import patch

        def fake_roster(pga, comp, tid):
            return ["A1", "A2"]

        def fake_athlete_info(aid):
            return {"pga_tour_id": aid, "name": f"Golfer {aid}", "country": None}

        def fake_rounds(pga, comp, tid):
            return tid, rounds_by_team.get(tid, [])

        def default_status(pga, comp, tid):
            return tid, None, None, None

        stack = ExitStack()
        stack.enter_context(patch("app.services.scraper._get_json", return_value=self._THREE_TEAMS))
        stack.enter_context(
            patch("app.services.scraper._fetch_team_roster", side_effect=fake_roster)
        )
        stack.enter_context(
            patch("app.services.scraper._fetch_athlete_info", side_effect=fake_athlete_info)
        )
        stack.enter_context(
            patch("app.services.scraper._fetch_competitor_rounds", side_effect=fake_rounds)
        )
        stack.enter_context(
            patch(
                "app.services.scraper._fetch_competitor_status",
                side_effect=status_fn or default_status,
            )
        )
        stack.enter_context(
            patch(
                "app.services.scraper._fetch_start_holes",
                return_value=({}, leaderboard_statuses or {}),
            )
        )
        return stack

    def _statuses(self, results: list[dict]) -> dict[str, str | None]:
        """Collapse results to {team_id: status}, keeping one entry per team."""
        seen: dict[str, str | None] = {}
        for r in results:
            seen[r["team_competitor_id"]] = r["status"]
        return seen

    def test_cut_inferred_for_teams_with_fewer_rounds(self):
        """Teams that played rounds 1-2 while the max is 4 (completed event)
        get status='CUT' when the leaderboard returns no explicit statuses."""
        rounds_by_team = {
            "TEAM001": self._build_rounds(4),  # made cut
            "TEAM002": self._build_rounds(2),  # cut after R2
            "TEAM003": self._build_rounds(2),  # cut after R2
        }
        with self._patch_all(rounds_by_team):
            _, results = _fetch_team_field("EVT001", "COMP001", fetch_round_data=True)

        statuses = self._statuses(results)
        assert statuses["TEAM001"] is None
        assert statuses["TEAM002"] == "CUT"
        assert statuses["TEAM003"] == "CUT"

    def test_both_athletes_on_cut_team_receive_cut_status(self):
        """Both golfers on a CUT team must carry status='CUT', not just one."""
        rounds_by_team = {
            "TEAM001": self._build_rounds(4),
            "TEAM002": self._build_rounds(4),
            "TEAM003": self._build_rounds(2),  # cut
        }
        with self._patch_all(rounds_by_team):
            _, results = _fetch_team_field("EVT001", "COMP001", fetch_round_data=True)

        team003_results = [r for r in results if r["team_competitor_id"] == "TEAM003"]
        assert len(team003_results) == 2
        assert all(r["status"] == "CUT" for r in team003_results)

    def test_zero_round_teams_not_marked_cut(self):
        """A team with 0 rounds is a pre-tournament WD, not a cut. Must stay None."""
        rounds_by_team = {
            "TEAM001": self._build_rounds(4),
            "TEAM002": self._build_rounds(4),
            "TEAM003": [],  # withdrew before playing
        }
        with self._patch_all(rounds_by_team):
            _, results = _fetch_team_field("EVT001", "COMP001", fetch_round_data=True)

        statuses = self._statuses(results)
        assert statuses["TEAM003"] is None

    def test_explicit_status_from_status_endpoint_not_overwritten(self):
        """If _fetch_competitor_status already returned an explicit status (e.g.
        WD) for a team with fewer rounds, the round-count inference must not
        overwrite it."""

        def status_with_wd(pga, comp, tid):
            if tid == "TEAM003":
                return tid, "WD", None, None
            return tid, None, None, None

        rounds_by_team = {
            "TEAM001": self._build_rounds(4),
            "TEAM002": self._build_rounds(4),
            "TEAM003": self._build_rounds(1),  # withdrew during R1
        }
        with self._patch_all(rounds_by_team, status_fn=status_with_wd):
            _, results = _fetch_team_field("EVT001", "COMP001", fetch_round_data=True)

        statuses = self._statuses(results)
        assert statuses["TEAM003"] == "WD"

    def test_leaderboard_status_not_overwritten_by_round_count(self):
        """If the leaderboard already supplied a status for a team, the
        round-count inference must not overwrite it."""
        rounds_by_team = {
            "TEAM001": self._build_rounds(4),
            "TEAM002": self._build_rounds(4),
            "TEAM003": self._build_rounds(2),
        }
        # Leaderboard returns MDF (made cut, didn't finish) for TEAM003 —
        # a more specific status than CUT; round-count fallback must keep it.
        with self._patch_all(rounds_by_team, leaderboard_statuses={"TEAM003": "MDF"}):
            _, results = _fetch_team_field("EVT001", "COMP001", fetch_round_data=True)

        statuses = self._statuses(results)
        assert statuses["TEAM003"] == "MDF"
