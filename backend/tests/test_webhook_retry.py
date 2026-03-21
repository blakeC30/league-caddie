"""
Tests for the automatic Stripe webhook failure retry scheduler job.

Covers:
  - Unresolved failures older than 1 hour are retried
  - Recent failures (< 1 hour) are skipped
  - Already-resolved failures are skipped
  - Failures at max retry count are skipped
  - Successful retry sets resolved_at and increments retry_count
  - Failed retry increments retry_count but leaves resolved_at NULL
  - Multiple failures retried independently
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models.league_purchase import StripeWebhookFailure


def _create_failure(db, *, session_id="cs_test_abc123", hours_ago=2, retry_count=0, resolved=False):
    """Insert a StripeWebhookFailure row for testing."""
    failure = StripeWebhookFailure(
        stripe_checkout_session_id=session_id,
        raw_payload={"id": session_id, "metadata": {"tier": "starter", "season_year": "2026"}},
        error_message="Test error",
        retry_count=retry_count,
    )
    if resolved:
        failure.resolved_at = datetime.now(UTC)
    db.add(failure)
    db.commit()
    db.refresh(failure)

    # Backdate created_at to simulate age
    db.execute(
        StripeWebhookFailure.__table__.update()
        .where(StripeWebhookFailure.id == failure.id)
        .values(created_at=datetime.now(UTC) - timedelta(hours=hours_ago))
    )
    db.commit()
    db.refresh(failure)
    return failure


def _run_retry_with_test_db(db, handle_side_effect=None):
    """Run _run_webhook_failure_retry with the test DB session injected."""
    mock_session_local = MagicMock(return_value=db)
    # Prevent the job from closing the shared test session
    original_close = db.close
    db.close = lambda: None

    handle_target = "app.routers.stripe_router._handle_checkout_complete"

    try:
        with patch("app.database.SessionLocal", mock_session_local):
            if handle_side_effect is not None:
                with patch(handle_target, side_effect=handle_side_effect):
                    from app.services.scheduler import _run_webhook_failure_retry

                    _run_webhook_failure_retry()
            else:
                with patch(handle_target) as mock_handle:
                    from app.services.scheduler import _run_webhook_failure_retry

                    _run_webhook_failure_retry()
                    return mock_handle
    finally:
        db.close = original_close


class TestWebhookFailureRetry:
    def test_retries_old_unresolved_failure(self, client, db):
        """Failures older than 1 hour with retry_count < 3 are retried."""
        failure = _create_failure(db, hours_ago=2)

        mock_handle = _run_retry_with_test_db(db)

        mock_handle.assert_called_once()
        db.refresh(failure)
        assert failure.resolved_at is not None
        assert failure.retry_count == 1

    def test_skips_recent_failure(self, client, db):
        """Failures less than 1 hour old are not retried."""
        _create_failure(db, hours_ago=0)

        mock_handle = _run_retry_with_test_db(db)

        mock_handle.assert_not_called()

    def test_skips_resolved_failure(self, client, db):
        """Already-resolved failures are not retried."""
        _create_failure(db, hours_ago=2, resolved=True)

        mock_handle = _run_retry_with_test_db(db)

        mock_handle.assert_not_called()

    def test_skips_max_retry_count(self, client, db):
        """Failures at max retry count (3) are not retried."""
        _create_failure(db, hours_ago=2, retry_count=3)

        mock_handle = _run_retry_with_test_db(db)

        mock_handle.assert_not_called()

    def test_failed_retry_increments_count(self, client, db):
        """A failed retry increments retry_count but does not set resolved_at."""
        failure = _create_failure(db, hours_ago=2)

        _run_retry_with_test_db(db, handle_side_effect=ValueError("Simulated failure"))

        db.refresh(failure)
        assert failure.resolved_at is None
        assert failure.retry_count == 1

    def test_multiple_failures_retried_independently(self, client, db):
        """Multiple failures are retried independently — one failure doesn't block others."""
        f1 = _create_failure(db, session_id="cs_test_first", hours_ago=3)
        f2 = _create_failure(db, session_id="cs_test_second", hours_ago=3)

        call_count = {"n": 0}

        def mock_handle(payload, session):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError("First one fails")

        _run_retry_with_test_db(db, handle_side_effect=mock_handle)

        db.refresh(f1)
        db.refresh(f2)
        # First failed, second succeeded
        assert f1.resolved_at is None
        assert f1.retry_count == 1
        assert f2.resolved_at is not None
        assert f2.retry_count == 1
