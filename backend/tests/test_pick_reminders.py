"""
Tests for app/services/pick_reminders.py — Wednesday pick reminder service.

Uses real PostgreSQL via the `db` fixture. Email sending is mocked so no SES
calls are made. Each test function gets a clean database slate from the
`clean_db` autouse fixture in conftest.py.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeagueTournament,
    Pick,
    PickReminder,
    Season,
    Tournament,
    User,
)
from app.services.auth import hash_password
from app.services.pick_reminders import (
    _is_pick_window_open,
    _send_reminder_for_league,
    create_and_send_pick_reminders,
)

# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _make_user(
    db,
    email: str,
    display_name: str = "Player",
    pick_reminders_enabled: bool = True,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        display_name=display_name,
        pick_reminders_enabled=pick_reminders_enabled,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_league_with_season(db, manager: User) -> tuple[League, Season]:
    league = League(name="Test League", created_by=manager.id)
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


def _make_tournament(
    db,
    start_days_from_now: int = 3,
    status: str = "scheduled",
    name: str = "Test Open",
) -> Tournament:
    today = date.today()
    t = Tournament(
        pga_tour_id=f"tour_{uuid.uuid4().hex[:8]}",
        name=name,
        start_date=today + timedelta(days=start_days_from_now),
        end_date=today + timedelta(days=start_days_from_now + 3),
        status=status,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _add_to_league_schedule(db, league: League, tournament: Tournament) -> LeagueTournament:
    lt = LeagueTournament(league_id=league.id, tournament_id=tournament.id, multiplier=1.0)
    db.add(lt)
    db.commit()
    return lt


def _add_member(db, league: League, user: User) -> LeagueMember:
    member = LeagueMember(
        league_id=league.id,
        user_id=user.id,
        role=LeagueMemberRole.MEMBER.value,
        status=LeagueMemberStatus.APPROVED.value,
    )
    db.add(member)
    db.commit()
    return member


def _make_pick_reminder(
    db,
    league: League,
    season: Season,
    tournament: Tournament,
    sent_at: datetime | None = None,
    failed_at: datetime | None = None,
    attempt_count: int = 0,
) -> PickReminder:
    reminder = PickReminder(
        id=uuid.uuid4(),
        league_id=league.id,
        season_id=season.id,
        tournament_id=tournament.id,
        scheduled_at=datetime.now(UTC),
        sent_at=sent_at,
        failed_at=failed_at,
        attempt_count=attempt_count,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def _make_golfer(db) -> Golfer:
    g = Golfer(
        pga_tour_id=f"g_{uuid.uuid4().hex[:8]}",
        name="Test Golfer",
        world_ranking=50,
        country="US",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _make_pick(db, league: League, season: Season, user: User, tournament: Tournament) -> Pick:
    golfer = _make_golfer(db)
    pick = Pick(
        id=uuid.uuid4(),
        league_id=league.id,
        season_id=season.id,
        user_id=user.id,
        tournament_id=tournament.id,
        golfer_id=golfer.id,
    )
    db.add(pick)
    db.commit()
    db.refresh(pick)
    return pick


# ---------------------------------------------------------------------------
# TestIsPickWindowOpen
# ---------------------------------------------------------------------------


class TestIsPickWindowOpen:
    """_is_pick_window_open() mirrors the frontend pick window logic."""

    def test_returns_true_for_in_progress_tournament(self, db):
        """An in_progress tournament's pick window is always considered open."""
        t = _make_tournament(db, start_days_from_now=-1, status="in_progress")
        assert _is_pick_window_open(db, t) is True

    def test_returns_false_when_global_in_progress_exists(self, db):
        """If any tournament is in_progress, scheduled tournaments are not yet open."""
        _make_tournament(db, start_days_from_now=-1, status="in_progress", name="Live Event")
        scheduled = _make_tournament(db, start_days_from_now=3, status="scheduled", name="Future")
        assert _is_pick_window_open(db, scheduled) is False

    def test_returns_true_for_globally_next_scheduled(self, db):
        """The earliest scheduled tournament is open when nothing is in_progress."""
        t = _make_tournament(db, start_days_from_now=3, status="scheduled")
        assert _is_pick_window_open(db, t) is True

    def test_returns_false_when_not_globally_next(self, db):
        """A later scheduled tournament is not open when an earlier one exists."""
        _make_tournament(db, start_days_from_now=1, status="scheduled", name="Earlier")
        later = _make_tournament(db, start_days_from_now=5, status="scheduled", name="Later")
        assert _is_pick_window_open(db, later) is False

    def test_returns_true_when_only_scheduled_and_is_next(self, db):
        """Single scheduled tournament in the DB: it must be the globally-next one."""
        only = _make_tournament(db, start_days_from_now=2, status="scheduled")
        assert _is_pick_window_open(db, only) is True

    def test_completed_tournament_is_not_window_open(self, db):
        """A completed tournament returns False — no in_progress and it's not scheduled."""
        # No in_progress tournaments; completed tournament is not the globally-next scheduled.
        _make_tournament(db, start_days_from_now=1, status="scheduled", name="Next Scheduled")
        completed = _make_tournament(db, start_days_from_now=-7, status="completed", name="Done")
        # completed is not in_progress, and there IS a globally-next scheduled that is not it.
        assert _is_pick_window_open(db, completed) is False


# ---------------------------------------------------------------------------
# TestSendReminderForLeague
# ---------------------------------------------------------------------------


class TestSendReminderForLeague:
    """_send_reminder_for_league() sends emails to unpicked, opted-in, approved members."""

    def test_sends_to_eligible_member(self, db):
        """An approved, opted-in member with no pick gets an email."""
        manager = _make_user(db, "mgr@srl.com")
        member = _make_user(db, "member@srl.com", display_name="Bob")
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, member)
        tournament = _make_tournament(db)
        reminder = _make_pick_reminder(db, league, season, tournament)
        # Ensure relationship is loaded.
        db.refresh(reminder)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            sent, skipped = _send_reminder_for_league(
                db, reminder, tournament, pick_window_open=True
            )

        # Manager and member are both approved with no picks → both should be sent.
        assert sent >= 1
        assert mock_send.called

    def test_skips_opted_out_members(self, db):
        """Members who set pick_reminders_enabled=False are skipped."""
        manager = _make_user(db, "mgr@optout.com")
        opted_out = _make_user(
            db, "optout@srl.com", display_name="OptOut", pick_reminders_enabled=False
        )
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, opted_out)
        tournament = _make_tournament(db)
        reminder = _make_pick_reminder(db, league, season, tournament)
        db.refresh(reminder)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            sent, skipped = _send_reminder_for_league(
                db, reminder, tournament, pick_window_open=True
            )

        # opted_out user should be skipped; manager (opted-in) gets the email.
        # Verify the opted-out user's email was never passed to send_pick_reminder_email.
        for c in mock_send.call_args_list:
            assert c[1]["to_email"] != "optout@srl.com"
        assert skipped >= 1

    def test_skips_already_picked_members(self, db):
        """Members who already submitted a pick for this tournament are skipped."""
        manager = _make_user(db, "mgr@already.com")
        picker = _make_user(db, "picker@already.com")
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, picker)
        tournament = _make_tournament(db)
        _make_pick(db, league, season, picker, tournament)
        reminder = _make_pick_reminder(db, league, season, tournament)
        db.refresh(reminder)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            sent, skipped = _send_reminder_for_league(
                db, reminder, tournament, pick_window_open=True
            )

        # picker already picked → skipped; email should not go to picker.
        for c in mock_send.call_args_list:
            assert c[1]["to_email"] != "picker@already.com"
        assert skipped >= 1

    def test_returns_sent_and_skipped_counts(self, db):
        """The function returns a (sent, skipped) tuple with accurate counts."""
        manager = _make_user(db, "mgr@counts.com")
        eligible = _make_user(db, "eligible@counts.com")
        opted_out = _make_user(db, "opted_out@counts.com", pick_reminders_enabled=False)
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, eligible)
        _add_member(db, league, opted_out)
        tournament = _make_tournament(db)
        reminder = _make_pick_reminder(db, league, season, tournament)
        db.refresh(reminder)

        with patch("app.services.email.send_pick_reminder_email"):
            sent, skipped = _send_reminder_for_league(
                db, reminder, tournament, pick_window_open=True
            )

        # manager + eligible = 2 sent; opted_out = 1 skipped
        assert sent == 2
        assert skipped == 1

    def test_pick_window_open_flag_forwarded_to_email_function(self, db):
        """The pick_window_open argument is passed through to send_pick_reminder_email."""
        manager = _make_user(db, "mgr@flag.com")
        league, season = _make_league_with_season(db, manager)
        tournament = _make_tournament(db)
        reminder = _make_pick_reminder(db, league, season, tournament)
        db.refresh(reminder)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            _send_reminder_for_league(db, reminder, tournament, pick_window_open=False)

        for c in mock_send.call_args_list:
            assert c[1]["pick_window_open"] is False

    def test_league_name_passed_to_email_function(self, db):
        """send_pick_reminder_email receives the correct league name from the relationship."""
        manager = _make_user(db, "mgr@leaguename.com")
        league, season = _make_league_with_season(db, manager)
        tournament = _make_tournament(db)
        reminder = _make_pick_reminder(db, league, season, tournament)
        db.refresh(reminder)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            _send_reminder_for_league(db, reminder, tournament, pick_window_open=True)

        for c in mock_send.call_args_list:
            assert c[1]["league_name"] == "Test League"


# ---------------------------------------------------------------------------
# TestCreateAndSendPickReminders
# ---------------------------------------------------------------------------


class TestCreateAndSendPickReminders:
    """create_and_send_pick_reminders() is the main entry point called by APScheduler."""

    def test_returns_zeros_when_no_upcoming_tournaments(self, db):
        """If no tournaments start in the next 7 days, nothing is sent."""
        result = create_and_send_pick_reminders(db)
        assert result == {"sent": 0, "failed": 0, "skipped": 0, "errors": []}

    def test_skips_tournament_with_no_league_schedule(self, db):
        """A tournament not in any league's schedule produces zero sends."""
        # Tournament exists but no LeagueTournament rows reference it.
        _make_tournament(db, start_days_from_now=3)
        result = create_and_send_pick_reminders(db)
        assert result["sent"] == 0
        assert result["failed"] == 0

    def test_skips_league_with_no_active_season(self, db):
        """Leagues without an active season are silently skipped."""
        manager = _make_user(db, "mgr@noseason.com")
        league = League(name="Dead League", created_by=manager.id)
        db.add(league)
        db.flush()
        # Inactive season — should be skipped.
        season = Season(league_id=league.id, year=2024, is_active=False)
        db.add(season)
        t = _make_tournament(db, start_days_from_now=3)
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id, multiplier=1.0))
        db.commit()

        result = create_and_send_pick_reminders(db)
        assert result["sent"] == 0

    def test_sends_to_eligible_member(self, db):
        """An eligible member in a league with a scheduled tournament receives a reminder."""
        manager = _make_user(db, "mgr@eligible.com")
        member = _make_user(db, "member@eligible.com")
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, member)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_league_schedule(db, league, t)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            result = create_and_send_pick_reminders(db)

        # At least the member (and manager) should be sent to.
        assert result["sent"] >= 1
        assert result["failed"] == 0
        assert mock_send.called

    def test_creates_pick_reminder_row_in_db(self, db):
        """The function creates a PickReminder row so subsequent runs are idempotent."""
        manager = _make_user(db, "mgr@rowcreate.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_league_schedule(db, league, t)

        with patch("app.services.email.send_pick_reminder_email"):
            create_and_send_pick_reminders(db)

        reminder_count = db.query(PickReminder).count()
        assert reminder_count == 1

    def test_idempotent_already_sent_is_skipped(self, db):
        """A reminder with sent_at already set is skipped without sending another email."""
        manager = _make_user(db, "mgr@idempotent.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_league_schedule(db, league, t)
        # Pre-create reminder marked as already sent.
        _make_pick_reminder(db, league, season, t, sent_at=datetime.now(UTC))

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            result = create_and_send_pick_reminders(db)

        mock_send.assert_not_called()
        assert result["sent"] == 0

    def test_permanently_failed_reminder_is_skipped(self, db):
        """A reminder with failed_at set is permanently skipped even if members are eligible."""
        manager = _make_user(db, "mgr@failed.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_league_schedule(db, league, t)
        # Pre-create permanently failed reminder.
        _make_pick_reminder(db, league, season, t, failed_at=datetime.now(UTC))

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            create_and_send_pick_reminders(db)

        mock_send.assert_not_called()

    def test_handles_email_failure_increments_failed_count(self, db):
        """When send_pick_reminder_email raises, failed count is incremented."""
        manager = _make_user(db, "mgr@emailfail.com")
        member = _make_user(db, "member@emailfail.com")
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, member)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_league_schedule(db, league, t)

        with patch(
            "app.services.email.send_pick_reminder_email",
            side_effect=RuntimeError("SES down"),
        ):
            result = create_and_send_pick_reminders(db)

        assert result["failed"] == 1
        assert len(result["errors"]) == 1
        assert result["sent"] == 0

    def test_failed_reminder_stores_error_message_in_db(self, db):
        """After exhausting max_attempts, error_message is persisted to the reminder row.

        Pre-create the reminder with attempt_count=max_attempts-1 so it's already
        committed (persistent). After the rollback on send failure, persistent objects
        are expired but remain in the session — unlike newly-flushed objects which are
        expunged — so the subsequent db.commit() saves the failed_at + error_message.
        """
        manager = _make_user(db, "mgr@errmsg.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_league_schedule(db, league, t)

        # Pre-create the reminder at attempt_count=2
        # (max_attempts=3 → one more will trigger failed_at)
        _make_pick_reminder(db, league, season, t, attempt_count=2)

        with patch(
            "app.services.email.send_pick_reminder_email",
            side_effect=RuntimeError("SES error detail"),
        ):
            create_and_send_pick_reminders(db)

        db.expire_all()
        reminder = db.query(PickReminder).first()
        assert reminder is not None
        assert reminder.failed_at is not None
        assert reminder.error_message == "SES error detail"

    def test_skips_already_picked_member(self, db):
        """Members who already picked for the tournament are not emailed."""
        manager = _make_user(db, "mgr@alreadypicked.com")
        picker = _make_user(db, "picker@alreadypicked.com")
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, picker)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_league_schedule(db, league, t)
        _make_pick(db, league, season, picker, t)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            result = create_and_send_pick_reminders(db)

        # picker is skipped; manager (no pick) still gets email.
        for c in mock_send.call_args_list:
            assert c[1]["to_email"] != "picker@alreadypicked.com"
        assert result["skipped"] >= 1

    def test_ignores_completed_and_in_progress_tournaments(self, db):
        """Only scheduled tournaments within the 7-day window are processed."""
        manager = _make_user(db, "mgr@statusfilter.com")
        league, season = _make_league_with_season(db, manager)
        in_progress = _make_tournament(db, start_days_from_now=-1, status="in_progress")
        completed = _make_tournament(db, start_days_from_now=-7, status="completed")
        _add_to_league_schedule(db, league, in_progress)
        _add_to_league_schedule(db, league, completed)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            result = create_and_send_pick_reminders(db)

        # No scheduled tournament in 7-day window → nothing sent.
        mock_send.assert_not_called()
        assert result["sent"] == 0

    def test_tournament_beyond_7_day_window_ignored(self, db):
        """Tournaments starting more than 7 days from now are outside the send window."""
        manager = _make_user(db, "mgr@farfuture.com")
        league, season = _make_league_with_season(db, manager)
        far_future = _make_tournament(db, start_days_from_now=10, status="scheduled")
        _add_to_league_schedule(db, league, far_future)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            result = create_and_send_pick_reminders(db)

        mock_send.assert_not_called()
        assert result["sent"] == 0

    def test_sent_at_set_after_successful_send(self, db):
        """After successful delivery the PickReminder.sent_at is populated."""
        manager = _make_user(db, "mgr@sentat.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_league_schedule(db, league, t)

        with patch("app.services.email.send_pick_reminder_email"):
            create_and_send_pick_reminders(db)

        reminder = db.query(PickReminder).first()
        assert reminder is not None
        assert reminder.sent_at is not None

    def test_multiple_leagues_each_get_their_own_reminder(self, db):
        """When two leagues share a tournament, each gets its own PickReminder row."""
        mgr1 = _make_user(db, "mgr1@multi.com")
        mgr2 = _make_user(db, "mgr2@multi.com")
        league1, season1 = _make_league_with_season(db, mgr1)
        league2, season2 = _make_league_with_season(db, mgr2)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_league_schedule(db, league1, t)
        _add_to_league_schedule(db, league2, t)

        with patch("app.services.email.send_pick_reminder_email"):
            create_and_send_pick_reminders(db)

        reminder_count = db.query(PickReminder).count()
        assert reminder_count == 2
