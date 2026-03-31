"""
Tests for the earnings-gated TOURNAMENT_COMPLETED pipeline.

Covers:
  - _winner_has_earnings() gate logic
  - _publish_schedule_transitions() deferring when earnings unavailable
  - Admin single sync triggering score_round + advance_bracket directly
  - Worker catching HTTPException from score_round gracefully
  - consume() catching connection errors and retrying
"""

import os
import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import botocore.exceptions
import pytest

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    Season,
    Tournament,
    TournamentEntry,
)
from app.models.playoff import PlayoffConfig, PlayoffRound
from app.models.user import User
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _make_user(db, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("pw"),
        display_name="Test User",
    )
    db.add(user)
    db.flush()
    return user


def _make_golfer(db, name: str, pga_tour_id: str | None = None) -> Golfer:
    golfer = Golfer(
        pga_tour_id=pga_tour_id or f"g_{uuid.uuid4().hex[:8]}",
        name=name,
    )
    db.add(golfer)
    db.flush()
    return golfer


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


def _make_entry(
    db,
    tournament: Tournament,
    golfer: Golfer,
    *,
    finish_position=None,
    earnings_usd=None,
    status=None,
) -> TournamentEntry:
    entry = TournamentEntry(
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        finish_position=finish_position,
        earnings_usd=earnings_usd,
        status=status,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _make_league_with_season(db, manager: User) -> tuple:
    league = League(name=f"Test League {uuid.uuid4().hex[:6]}", created_by=manager.id)
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


def _make_locked_playoff_round(db, tournament: Tournament) -> PlayoffRound:
    manager = _make_user(db, f"mgr_{uuid.uuid4().hex[:6]}@ep.com")
    league, season = _make_league_with_season(db, manager)
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
    db.flush()
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


# ---------------------------------------------------------------------------
# TestWinnerHasEarnings
# ---------------------------------------------------------------------------


class TestWinnerHasEarnings:
    """_winner_has_earnings() gates TOURNAMENT_COMPLETED on winner earnings."""

    def test_returns_true_when_winner_has_earnings(self, db):
        from app.services.scraper import _winner_has_earnings

        tournament = _make_completed_tournament(db, "Earnings Open")
        golfer = _make_golfer(db, "Winner Golfer")
        _make_entry(db, tournament, golfer, finish_position=1, earnings_usd=1000000)

        assert _winner_has_earnings(db, str(tournament.id)) is True

    def test_returns_false_when_winner_has_zero_earnings(self, db):
        from app.services.scraper import _winner_has_earnings

        tournament = _make_completed_tournament(db, "Zero Earnings Open")
        golfer = _make_golfer(db, "Zero Winner")
        _make_entry(db, tournament, golfer, finish_position=1, earnings_usd=0)

        assert _winner_has_earnings(db, str(tournament.id)) is False

    def test_returns_false_when_winner_has_null_earnings(self, db):
        from app.services.scraper import _winner_has_earnings

        tournament = _make_completed_tournament(db, "Null Earnings Open")
        golfer = _make_golfer(db, "Null Winner")
        _make_entry(db, tournament, golfer, finish_position=1, earnings_usd=None)

        assert _winner_has_earnings(db, str(tournament.id)) is False

    def test_returns_false_when_no_winner_entry(self, db):
        from app.services.scraper import _winner_has_earnings

        tournament = _make_completed_tournament(db, "No Winner Open")
        golfer = _make_golfer(db, "Second Place")
        _make_entry(db, tournament, golfer, finish_position=2, earnings_usd=500000)

        assert _winner_has_earnings(db, str(tournament.id)) is False


# ---------------------------------------------------------------------------
# TestPublishScheduleTransitions
# ---------------------------------------------------------------------------


class TestPublishScheduleTransitions:
    """_publish_schedule_transitions() defers when earnings unavailable."""

    def test_defers_when_winner_has_no_earnings(self, db):
        from app.services.scraper import _publish_schedule_transitions

        tournament = _make_completed_tournament(db, "Deferred Open")
        golfer = _make_golfer(db, "No Money Winner")
        _make_entry(db, tournament, golfer, finish_position=1, earnings_usd=None)

        env = {"SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.services.sqs.publish") as mock_pub:
                _publish_schedule_transitions(
                    [(str(tournament.id), "in_progress", "completed")], db=db
                )

        mock_pub.assert_not_called()

    def test_publishes_when_winner_has_earnings(self, db):
        from app.services.scraper import _publish_schedule_transitions

        tournament = _make_completed_tournament(db, "Published Open")
        golfer = _make_golfer(db, "Rich Winner")
        _make_entry(db, tournament, golfer, finish_position=1, earnings_usd=2000000)

        env = {"SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.services.sqs.publish") as mock_pub:
                _publish_schedule_transitions(
                    [(str(tournament.id), "in_progress", "completed")], db=db
                )

        mock_pub.assert_called_once_with("TOURNAMENT_COMPLETED", tournament_id=str(tournament.id))

    def test_skips_non_completed_transitions(self, db):
        from app.services.scraper import _publish_schedule_transitions

        env = {"SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.services.sqs.publish") as mock_pub:
                _publish_schedule_transitions([("tid", "scheduled", "in_progress")], db=db)

        mock_pub.assert_not_called()


# ---------------------------------------------------------------------------
# TestWorkerHTTPExceptionHandling
# ---------------------------------------------------------------------------


class TestWorkerHTTPExceptionHandling:
    """Worker catches HTTPException from score_round and defers gracefully."""

    def test_422_from_score_round_does_not_raise(self, db):
        """A 422 from score_round (earnings unavailable) is logged and swallowed."""
        from fastapi import HTTPException

        from app.worker_main import _handle_tournament_completed

        tournament = _make_completed_tournament(db, "HTTP422 Open")
        _make_locked_playoff_round(db, tournament)

        with patch("app.services.scraper.score_picks", return_value=0):
            with patch(
                "app.services.playoff.score_round",
                side_effect=HTTPException(status_code=422, detail="Earnings not available"),
            ):
                # Should NOT raise — the 422 is caught and logged.
                _handle_tournament_completed(db, str(tournament.id))

    def test_unexpected_error_from_score_round_raises(self, db):
        """A non-HTTPException from score_round propagates for SQS retry."""
        from app.worker_main import _handle_tournament_completed

        tournament = _make_completed_tournament(db, "RuntimeErr Open")
        _make_locked_playoff_round(db, tournament)

        with patch("app.services.scraper.score_picks", return_value=0):
            with patch(
                "app.services.playoff.score_round",
                side_effect=RuntimeError("unexpected DB error"),
            ):
                with pytest.raises(RuntimeError, match="unexpected DB error"):
                    _handle_tournament_completed(db, str(tournament.id))


# ---------------------------------------------------------------------------
# TestConsumeRetry
# ---------------------------------------------------------------------------


class TestConsumeRetry:
    """consume() catches connection errors and retries instead of crashing."""

    def test_retries_on_botocore_error(self):
        """A BotoCoreError on receive_message is caught, sleeps, and retries."""
        from app.services.sqs import consume

        handler = MagicMock()
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                # First call: BotoCoreError (caught, retry).
                # Second call: normal response with no messages.
                # Third call: Exception("stop") to exit the loop.
                mock_sqs.receive_message.side_effect = [
                    botocore.exceptions.EndpointConnectionError(endpoint_url="https://sqs.test"),
                    {"Messages": []},
                    Exception("stop"),
                ]
                with patch("time.sleep") as mock_sleep:
                    with pytest.raises(Exception, match="stop"):
                        consume(handler)
                    mock_sleep.assert_called_once_with(5)
        handler.assert_not_called()

    def test_retries_on_os_error(self):
        """An OSError (network failure) on receive_message is caught and retried."""
        from app.services.sqs import consume

        handler = MagicMock()
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                mock_sqs.receive_message.side_effect = [
                    OSError("Connection reset"),
                    {"Messages": []},
                    Exception("stop"),
                ]
                with patch("time.sleep"):
                    with pytest.raises(Exception, match="stop"):
                        consume(handler)

    def test_does_not_catch_non_connection_errors(self):
        """A generic Exception on receive_message is NOT caught — propagates immediately."""
        from app.services.sqs import consume

        handler = MagicMock()
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                mock_sqs.receive_message.side_effect = Exception("stop")
                with pytest.raises(Exception, match="stop"):
                    consume(handler)


# ---------------------------------------------------------------------------
# TestPublishCompletedForUnscoredPlayoffs
# ---------------------------------------------------------------------------


class TestPublishCompletedForUnscoredPlayoffs:
    """_publish_completed_for_unscored_playoffs() finds and publishes deferred events."""

    def test_publishes_for_locked_round_with_earnings(self, db):
        from app.services.scraper import _publish_completed_for_unscored_playoffs

        tournament = _make_completed_tournament(db, "Unscored Playoff Open")
        golfer = _make_golfer(db, "PO Winner")
        _make_entry(db, tournament, golfer, finish_position=1, earnings_usd=1500000)
        _make_locked_playoff_round(db, tournament)

        env = {"SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.services.sqs.publish") as mock_pub:
                _publish_completed_for_unscored_playoffs(db)

        mock_pub.assert_called_once_with("TOURNAMENT_COMPLETED", tournament_id=str(tournament.id))

    def test_skips_when_no_earnings(self, db):
        from app.services.scraper import _publish_completed_for_unscored_playoffs

        tournament = _make_completed_tournament(db, "No Earnings PO Open")
        golfer = _make_golfer(db, "PO No Money")
        _make_entry(db, tournament, golfer, finish_position=1, earnings_usd=None)
        _make_locked_playoff_round(db, tournament)

        env = {"SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.services.sqs.publish") as mock_pub:
                _publish_completed_for_unscored_playoffs(db)

        mock_pub.assert_not_called()

    def test_scoped_to_specific_tournament(self, db):
        from app.services.scraper import _publish_completed_for_unscored_playoffs

        t1 = _make_completed_tournament(db, "Scoped T1")
        t2 = _make_completed_tournament(db, "Scoped T2")
        g1 = _make_golfer(db, "T1 Winner")
        g2 = _make_golfer(db, "T2 Winner")
        _make_entry(db, t1, g1, finish_position=1, earnings_usd=1000000)
        _make_entry(db, t2, g2, finish_position=1, earnings_usd=2000000)
        _make_locked_playoff_round(db, t1)
        _make_locked_playoff_round(db, t2)

        env = {"SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("app.services.sqs.publish") as mock_pub:
                _publish_completed_for_unscored_playoffs(db, tournament_id=str(t1.id))

        # Only t1 should be published, not t2.
        mock_pub.assert_called_once_with("TOURNAMENT_COMPLETED", tournament_id=str(t1.id))

    def test_no_op_when_sqs_url_not_set(self, db):
        from app.services.scraper import _publish_completed_for_unscored_playoffs

        tournament = _make_completed_tournament(db, "No SQS Open")
        golfer = _make_golfer(db, "SQS Winner")
        _make_entry(db, tournament, golfer, finish_position=1, earnings_usd=1000000)
        _make_locked_playoff_round(db, tournament)

        clean_env = {k: v for k, v in os.environ.items() if k != "SQS_QUEUE_URL"}
        with patch.dict(os.environ, clean_env, clear=True):
            with patch("app.services.sqs.publish") as mock_pub:
                _publish_completed_for_unscored_playoffs(db)

        mock_pub.assert_not_called()
