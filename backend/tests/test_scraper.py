"""
Tests for the scraper service.

These are unit tests — no HTTP is made. httpx calls are intercepted by
pytest-httpx (or unittest.mock) so tests run without a network connection.

What's tested here:
  - parse_schedule_response()  — JSON → tournament dicts (including team event detection)
  - upsert_tournaments()       — create new / update existing tournament rows
  - upsert_field()             — create new / update existing golfer + entry rows
  - score_picks()              — points_earned set correctly after results land

The high-level sync_* functions (which make real HTTP calls) are integration
tests and run only when the ESPN API is reachable. They are not included here.
"""

from datetime import date, timedelta

from app.services.scraper import (
    _fetch_competitor_rounds,
    _map_espn_status,
    _parse_date,
    parse_schedule_response,
    score_picks,
    upsert_tournaments,
)

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
