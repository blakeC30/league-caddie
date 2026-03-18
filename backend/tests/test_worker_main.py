"""
Tests for app/worker_main.py — SQS event consumer/router.

Uses a mix of strategies:
  - handle():  patches SessionLocal so no real DB session is created.
  - _handle_tournament_in_progress() / _handle_tournament_completed():
    pass the real `db` fixture and mock the service functions they call.

Import-time patching note
-------------------------
Both handler functions import service functions inside their body:
  from app.services.playoff import any_r1_teed_off, resolve_draft
  from app.services.scraper import score_picks

Because the import happens at call time, the correct patch targets are the
*module attributes* — e.g. `app.services.playoff.any_r1_teed_off` — NOT
`app.worker_main.any_r1_teed_off` (which never exists as a module attribute).
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import (
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    Season,
    Tournament,
)
from app.models.playoff import PlayoffConfig, PlayoffRound
from app.models.user import User
from app.services.auth import hash_password
from app.worker_main import (
    _handle_tournament_completed,
    _handle_tournament_in_progress,
    handle,
)

# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _make_user(db, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw"),
        display_name="Worker Test User",
    )
    db.add(user)
    db.flush()
    return user


def _make_completed_tournament(db, name: str = "Completed Open") -> Tournament:
    today = date.today()
    t = Tournament(
        pga_tour_id=f"tour_{uuid.uuid4().hex[:8]}",
        name=name,
        start_date=today - timedelta(days=7),
        end_date=today - timedelta(days=4),
        status="completed",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_scheduled_tournament(db, name: str = "Upcoming Open") -> Tournament:
    today = date.today()
    t = Tournament(
        pga_tour_id=f"tour_{uuid.uuid4().hex[:8]}",
        name=name,
        start_date=today + timedelta(days=3),
        end_date=today + timedelta(days=6),
        status="scheduled",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_in_progress_tournament(db, name: str = "Live Open") -> Tournament:
    today = date.today()
    t = Tournament(
        pga_tour_id=f"tour_{uuid.uuid4().hex[:8]}",
        name=name,
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=2),
        status="in_progress",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_league_with_season(db, manager: User) -> tuple[League, Season]:
    league = League(name="Worker Test League", created_by=manager.id)
    db.add(league)
    db.flush()
    season = Season(league_id=league.id, year=2026, is_active=True)
    db.add(season)
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=manager.id,
            role=LeagueMemberRole.MANAGER.value,
            status=LeagueMemberStatus.APPROVED.value,
        )
    )
    db.commit()
    db.refresh(league)
    db.refresh(season)
    return league, season


def _make_playoff_config(db, league: League, season: Season) -> PlayoffConfig:
    config = PlayoffConfig(
        id=uuid.uuid4(),
        league_id=league.id,
        season_id=season.id,
        is_enabled=True,
        playoff_size=2,
        draft_style="snake",
        picks_per_round=[1],
        status="seeded",
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _make_locked_playoff_round(db, tournament: Tournament) -> PlayoffRound:
    """Create a full League/Season/PlayoffConfig/PlayoffRound chain for a locked round."""
    manager = _make_user(db, f"mgr_{uuid.uuid4().hex[:6]}@worker.com")
    league, season = _make_league_with_season(db, manager)
    config = _make_playoff_config(db, league, season)
    round_obj = PlayoffRound(
        playoff_config_id=config.id,
        round_number=1,
        status="locked",
        tournament_id=tournament.id,
    )
    db.add(round_obj)
    db.commit()
    db.refresh(round_obj)
    return round_obj


def _make_drafting_playoff_round(db, tournament: Tournament) -> PlayoffRound:
    """Create a PlayoffRound in 'drafting' status, draft_resolved_at=None."""
    manager = _make_user(db, f"mgr_{uuid.uuid4().hex[:6]}@worker.com")
    league, season = _make_league_with_season(db, manager)
    config = _make_playoff_config(db, league, season)
    round_obj = PlayoffRound(
        playoff_config_id=config.id,
        round_number=1,
        status="drafting",
        tournament_id=tournament.id,
        draft_resolved_at=None,
    )
    db.add(round_obj)
    db.commit()
    db.refresh(round_obj)
    return round_obj


# ---------------------------------------------------------------------------
# TestHandleRouting  (no real DB — SessionLocal is mocked)
# ---------------------------------------------------------------------------


class TestHandleRouting:
    """handle() routes SQS messages to the correct sub-handler or discards them."""

    def test_unknown_event_type_is_discarded(self):
        """An unrecognised event type is logged and silently discarded — no exception."""
        with patch("app.database.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            # Must not raise.
            handle({"type": "UNKNOWN_TYPE"})

    def test_missing_tournament_id_in_progress_is_discarded(self):
        """A TOURNAMENT_IN_PROGRESS message without tournament_id is skipped silently."""
        with patch("app.database.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            handle({"type": "TOURNAMENT_IN_PROGRESS"})  # no tournament_id

    def test_missing_tournament_id_completed_is_discarded(self):
        """A TOURNAMENT_COMPLETED message without tournament_id is skipped silently."""
        with patch("app.database.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            handle({"type": "TOURNAMENT_COMPLETED"})  # no tournament_id

    def test_db_always_closed_on_success(self):
        """The DB session is closed even when the event is discarded without error."""
        with patch("app.database.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            handle({"type": "UNKNOWN"})
            mock_db.close.assert_called_once()

    def test_db_closed_on_handler_exception(self):
        """The DB session is closed via finally block even when a handler raises."""
        with patch("app.database.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            with patch("app.worker_main._handle_tournament_completed") as mock_h:
                mock_h.side_effect = RuntimeError("boom")
                with pytest.raises(RuntimeError, match="boom"):
                    handle({"type": "TOURNAMENT_COMPLETED", "tournament_id": "some-id"})
            mock_db.close.assert_called_once()

    def test_tournament_completed_routes_to_handler(self):
        """A valid TOURNAMENT_COMPLETED message calls _handle_tournament_completed."""
        with patch("app.database.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            with patch("app.worker_main._handle_tournament_completed") as mock_h:
                handle({"type": "TOURNAMENT_COMPLETED", "tournament_id": "tid-abc"})
                mock_h.assert_called_once_with(mock_db, "tid-abc")

    def test_tournament_in_progress_routes_to_handler(self):
        """A valid TOURNAMENT_IN_PROGRESS message calls _handle_tournament_in_progress."""
        with patch("app.database.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            with patch("app.worker_main._handle_tournament_in_progress") as mock_h:
                handle({"type": "TOURNAMENT_IN_PROGRESS", "tournament_id": "tid-xyz"})
                mock_h.assert_called_once_with(mock_db, "tid-xyz")


# ---------------------------------------------------------------------------
# TestHandleTournamentInProgress  (real DB + mocked service functions)
# ---------------------------------------------------------------------------


class TestHandleTournamentInProgress:
    """_handle_tournament_in_progress() resolves playoff draft rounds once R1 starts."""

    def test_no_rounds_does_nothing(self, db):
        """A tournament_id with no matching PlayoffRound rows completes without error."""
        random_id = str(uuid.uuid4())
        # Should not raise even though no rows exist.
        _handle_tournament_in_progress(db, random_id)

    def test_skips_when_r1_not_teed_off(self, db):
        """If any_r1_teed_off returns False, resolve_draft is never called."""
        tournament = _make_in_progress_tournament(db)
        _make_drafting_playoff_round(db, tournament)

        with patch("app.services.playoff.any_r1_teed_off", return_value=False):
            with patch("app.services.playoff.resolve_draft") as mock_resolve:
                _handle_tournament_in_progress(db, str(tournament.id))
        mock_resolve.assert_not_called()

    def test_resolves_when_r1_teed_off(self, db):
        """If any_r1_teed_off returns True, resolve_draft is called for the round."""
        tournament = _make_in_progress_tournament(db)
        playoff_round = _make_drafting_playoff_round(db, tournament)

        with patch("app.services.playoff.any_r1_teed_off", return_value=True):
            with patch("app.services.playoff.resolve_draft") as mock_resolve:
                _handle_tournament_in_progress(db, str(tournament.id))
        mock_resolve.assert_called_once()
        # The first argument should be the db session, second the PlayoffRound object.
        args = mock_resolve.call_args[0]
        assert args[0] is db
        assert args[1].id == playoff_round.id

    def test_reraises_on_resolve_error(self, db):
        """If resolve_draft raises, the exception propagates so SQS can retry."""
        tournament = _make_in_progress_tournament(db)
        _make_drafting_playoff_round(db, tournament)

        with patch("app.services.playoff.any_r1_teed_off", return_value=True):
            with patch("app.services.playoff.resolve_draft", side_effect=RuntimeError("oops")):
                with pytest.raises(RuntimeError, match="oops"):
                    _handle_tournament_in_progress(db, str(tournament.id))

    def test_skips_rounds_already_resolved(self, db):
        """Rounds with draft_resolved_at set are filtered out before any_r1_teed_off check."""
        tournament = _make_in_progress_tournament(db)
        # Create a round that is already resolved (draft_resolved_at is not None).
        manager = _make_user(db, f"mgr_{uuid.uuid4().hex[:6]}@worker.com")
        league, season = _make_league_with_season(db, manager)
        config = _make_playoff_config(db, league, season)
        already_resolved = PlayoffRound(
            playoff_config_id=config.id,
            round_number=1,
            status="drafting",
            tournament_id=tournament.id,
            draft_resolved_at=datetime.now(UTC),  # already done
        )
        db.add(already_resolved)
        db.commit()

        with patch("app.services.playoff.any_r1_teed_off", return_value=True):
            with patch("app.services.playoff.resolve_draft") as mock_resolve:
                _handle_tournament_in_progress(db, str(tournament.id))
        # The already-resolved round should be filtered before resolve_draft is called.
        mock_resolve.assert_not_called()

    def test_non_drafting_rounds_are_ignored(self, db):
        """Rounds in 'locked' or 'pending' status are not queried for draft resolution."""
        tournament = _make_in_progress_tournament(db)
        # Create a locked round (status != "drafting").
        _make_locked_playoff_round(db, tournament)

        with patch("app.services.playoff.any_r1_teed_off") as mock_teed:
            with patch("app.services.playoff.resolve_draft") as mock_resolve:
                _handle_tournament_in_progress(db, str(tournament.id))
        # No drafting round found → any_r1_teed_off and resolve_draft never called.
        mock_teed.assert_not_called()
        mock_resolve.assert_not_called()


# ---------------------------------------------------------------------------
# TestHandleTournamentCompleted  (real DB + mocked service functions)
# ---------------------------------------------------------------------------


class TestHandleTournamentCompleted:
    """_handle_tournament_completed() runs the full finalization pipeline."""

    def test_skips_when_tournament_not_found(self, db):
        """A tournament_id that doesn't exist in the DB is handled without error."""
        nonexistent_id = str(uuid.uuid4())
        # Must not raise.
        with patch("app.services.scraper.score_picks") as mock_score:
            _handle_tournament_completed(db, nonexistent_id)
        mock_score.assert_not_called()

    def test_calls_score_picks(self, db):
        """score_picks is called with the real tournament object."""
        tournament = _make_completed_tournament(db)

        with patch("app.services.scraper.score_picks", return_value=5) as mock_score:
            _handle_tournament_completed(db, str(tournament.id))

        mock_score.assert_called_once()
        args = mock_score.call_args[0]
        assert args[0] is db
        assert args[1].id == tournament.id

    def test_returns_after_score_picks_when_no_playoff_round(self, db):
        """When no locked PlayoffRound exists, score_round is never called."""
        tournament = _make_completed_tournament(db)

        with patch("app.services.scraper.score_picks", return_value=0):
            with patch("app.services.playoff.score_round") as mock_score_round:
                _handle_tournament_completed(db, str(tournament.id))

        mock_score_round.assert_not_called()

    def test_scores_playoff_round_when_exists(self, db):
        """score_round is called when a locked PlayoffRound is linked to the tournament."""
        tournament = _make_completed_tournament(db)
        locked_round = _make_locked_playoff_round(db, tournament)

        with patch("app.services.scraper.score_picks", return_value=0):
            with patch("app.services.playoff.score_round") as mock_sr:
                with patch("app.services.playoff.advance_bracket"):
                    _handle_tournament_completed(db, str(tournament.id))

        mock_sr.assert_called_once()
        sr_args = mock_sr.call_args[0]
        assert sr_args[0] is db
        assert sr_args[1].id == locked_round.id

    def test_advances_bracket_after_score_round(self, db):
        """advance_bracket is called after score_round when a locked round exists."""
        tournament = _make_completed_tournament(db)
        _make_locked_playoff_round(db, tournament)

        with patch("app.services.scraper.score_picks", return_value=0):
            with patch("app.services.playoff.score_round"):
                with patch("app.services.playoff.advance_bracket") as mock_ab:
                    _handle_tournament_completed(db, str(tournament.id))

        mock_ab.assert_called_once()

    def test_reraises_on_score_picks_exception(self, db):
        """If score_picks raises, the exception propagates so SQS retries the message."""
        tournament = _make_completed_tournament(db)

        with patch("app.services.scraper.score_picks", side_effect=RuntimeError("db error")):
            with pytest.raises(RuntimeError, match="db error"):
                _handle_tournament_completed(db, str(tournament.id))

    def test_reraises_on_score_round_exception(self, db):
        """If score_round raises, the exception propagates so SQS retries."""
        tournament = _make_completed_tournament(db)
        _make_locked_playoff_round(db, tournament)

        with patch("app.services.scraper.score_picks", return_value=0):
            with patch(
                "app.services.playoff.score_round", side_effect=RuntimeError("score_round fail")
            ):
                with pytest.raises(RuntimeError, match="score_round fail"):
                    _handle_tournament_completed(db, str(tournament.id))

    def test_reraises_on_advance_bracket_exception(self, db):
        """If advance_bracket raises, the exception propagates so SQS retries."""
        tournament = _make_completed_tournament(db)
        _make_locked_playoff_round(db, tournament)

        with patch("app.services.scraper.score_picks", return_value=0):
            with patch("app.services.playoff.score_round"):
                with patch(
                    "app.services.playoff.advance_bracket",
                    side_effect=RuntimeError("bracket fail"),
                ):
                    with pytest.raises(RuntimeError, match="bracket fail"):
                        _handle_tournament_completed(db, str(tournament.id))

    def test_advance_bracket_not_called_when_score_round_raises(self, db):
        """advance_bracket is not reached if score_round fails first."""
        tournament = _make_completed_tournament(db)
        _make_locked_playoff_round(db, tournament)

        with patch("app.services.scraper.score_picks", return_value=0):
            with patch("app.services.playoff.score_round", side_effect=RuntimeError("fail")):
                with patch("app.services.playoff.advance_bracket") as mock_ab:
                    with pytest.raises(RuntimeError):
                        _handle_tournament_completed(db, str(tournament.id))

        mock_ab.assert_not_called()

    def test_score_picks_not_called_when_tournament_missing(self, db):
        """score_picks is skipped entirely for a non-existent tournament_id."""
        with patch("app.services.scraper.score_picks") as mock_score:
            _handle_tournament_completed(db, str(uuid.uuid4()))
        mock_score.assert_not_called()

    def test_non_locked_playoff_round_is_ignored(self, db):
        """A PlayoffRound in 'pending' or 'drafting' status is not treated as locked."""
        tournament = _make_completed_tournament(db)
        # Create a drafting round (not locked) — should NOT trigger score_round.
        manager = _make_user(db, f"mgr_{uuid.uuid4().hex[:6]}@worker.com")
        league, season = _make_league_with_season(db, manager)
        config = _make_playoff_config(db, league, season)
        drafting_round = PlayoffRound(
            playoff_config_id=config.id,
            round_number=1,
            status="drafting",  # not "locked"
            tournament_id=tournament.id,
        )
        db.add(drafting_round)
        db.commit()

        with patch("app.services.scraper.score_picks", return_value=0):
            with patch("app.services.playoff.score_round") as mock_sr:
                with patch("app.services.playoff.advance_bracket") as mock_ab:
                    _handle_tournament_completed(db, str(tournament.id))

        mock_sr.assert_not_called()
        mock_ab.assert_not_called()
