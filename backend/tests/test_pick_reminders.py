"""
Tests for app/services/pick_reminders.py — pick reminder service.

Phase 1 (scraper): create_pick_reminders() detects upcoming tournaments, creates
PickReminder rows, and publishes a single PICK_REMINDER_SEND SQS trigger.

Phase 2 (worker): send_pick_reminders() aggregates all unsent reminders by user
and sends one consolidated email per user.
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
    create_pick_reminders,
    send_pick_reminders,
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


def _make_league_with_season(db, manager: User, name: str = "Test League") -> tuple[League, Season]:
    league = League(name=name, created_by=manager.id)
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


def _add_to_schedule(db, league: League, tournament: Tournament) -> None:
    db.add(LeagueTournament(league_id=league.id, tournament_id=tournament.id, multiplier=1.0))
    db.commit()


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


def _make_reminder(
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


def _make_pick(db, league, season, user, tournament) -> Pick:
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
    return pick


# ---------------------------------------------------------------------------
# TestIsPickWindowOpen
# ---------------------------------------------------------------------------


class TestIsPickWindowOpen:
    def test_returns_true_for_in_progress_tournament(self, db):
        t = _make_tournament(db, start_days_from_now=-1, status="in_progress")
        assert _is_pick_window_open(db, t) is True

    def test_returns_false_when_global_in_progress_exists(self, db):
        _make_tournament(db, start_days_from_now=-1, status="in_progress", name="Live")
        scheduled = _make_tournament(db, start_days_from_now=3, status="scheduled", name="Future")
        assert _is_pick_window_open(db, scheduled) is False

    def test_returns_true_for_globally_next_scheduled(self, db):
        t = _make_tournament(db, start_days_from_now=3, status="scheduled")
        assert _is_pick_window_open(db, t) is True

    def test_returns_false_when_not_globally_next(self, db):
        _make_tournament(db, start_days_from_now=1, status="scheduled", name="Earlier")
        later = _make_tournament(db, start_days_from_now=5, status="scheduled", name="Later")
        assert _is_pick_window_open(db, later) is False

    def test_completed_tournament_is_not_window_open(self, db):
        _make_tournament(db, start_days_from_now=1, status="scheduled", name="Next")
        completed = _make_tournament(db, start_days_from_now=-7, status="completed", name="Done")
        assert _is_pick_window_open(db, completed) is False


# ---------------------------------------------------------------------------
# Phase 1: create_pick_reminders (scraper)
# ---------------------------------------------------------------------------


class TestCreatePickReminders:
    def test_returns_zeros_when_no_upcoming_tournaments(self, db):
        with patch("app.services.sqs.publish"):
            result = create_pick_reminders(db)
        assert result["reminders_created"] == 0
        assert result["published"] is False

    def test_skips_tournament_with_no_league_schedule(self, db):
        _make_tournament(db, start_days_from_now=3)
        with patch("app.services.sqs.publish") as mock_pub:
            result = create_pick_reminders(db)
        assert result["reminders_created"] == 0
        mock_pub.assert_not_called()

    def test_skips_league_with_no_active_season(self, db):
        manager = _make_user(db, "mgr@noseason.com")
        league = League(name="Dead League", created_by=manager.id)
        db.add(league)
        db.flush()
        db.add(Season(league_id=league.id, year=2024, is_active=False))
        t = _make_tournament(db, start_days_from_now=3)
        db.add(LeagueTournament(league_id=league.id, tournament_id=t.id, multiplier=1.0))
        db.commit()

        with patch("app.services.sqs.publish") as mock_pub:
            result = create_pick_reminders(db)
        assert result["reminders_created"] == 0
        mock_pub.assert_not_called()

    def test_creates_reminder_and_publishes_trigger(self, db):
        manager = _make_user(db, "mgr@create.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, league, t)

        with patch("app.services.sqs.publish") as mock_pub:
            result = create_pick_reminders(db)

        assert result["reminders_created"] == 1
        assert result["published"] is True
        mock_pub.assert_called_once_with("PICK_REMINDER_SEND")
        assert db.query(PickReminder).count() == 1

    def test_idempotent_already_sent_is_skipped(self, db):
        manager = _make_user(db, "mgr@idem.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, league, t)
        _make_reminder(db, league, season, t, sent_at=datetime.now(UTC))

        with patch("app.services.sqs.publish") as mock_pub:
            result = create_pick_reminders(db)

        assert result["skipped"] == 1
        assert result["reminders_created"] == 0
        mock_pub.assert_not_called()

    def test_permanently_failed_reminder_is_skipped(self, db):
        manager = _make_user(db, "mgr@fail.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, league, t)
        _make_reminder(db, league, season, t, failed_at=datetime.now(UTC))

        with patch("app.services.sqs.publish") as mock_pub:
            result = create_pick_reminders(db)

        assert result["skipped"] == 1
        mock_pub.assert_not_called()

    def test_ignores_non_scheduled_tournaments(self, db):
        manager = _make_user(db, "mgr@status.com")
        league, season = _make_league_with_season(db, manager)
        t_ip = _make_tournament(db, status="in_progress", start_days_from_now=-1)
        t_done = _make_tournament(db, status="completed", start_days_from_now=-7)
        _add_to_schedule(db, league, t_ip)
        _add_to_schedule(db, league, t_done)

        with patch("app.services.sqs.publish") as mock_pub:
            result = create_pick_reminders(db)

        assert result["reminders_created"] == 0
        mock_pub.assert_not_called()

    def test_tournament_beyond_7_days_ignored(self, db):
        manager = _make_user(db, "mgr@far.com")
        league, season = _make_league_with_season(db, manager)
        _add_to_schedule(db, league, _make_tournament(db, start_days_from_now=10))

        with patch("app.services.sqs.publish") as mock_pub:
            result = create_pick_reminders(db)

        assert result["reminders_created"] == 0
        mock_pub.assert_not_called()

    def test_multiple_leagues_get_separate_reminders(self, db):
        mgr1 = _make_user(db, "mgr1@multi.com")
        mgr2 = _make_user(db, "mgr2@multi.com")
        l1, _ = _make_league_with_season(db, mgr1, name="League 1")
        l2, _ = _make_league_with_season(db, mgr2, name="League 2")
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, l1, t)
        _add_to_schedule(db, l2, t)

        with patch("app.services.sqs.publish") as mock_pub:
            create_pick_reminders(db)

        assert db.query(PickReminder).count() == 2
        mock_pub.assert_called_once_with("PICK_REMINDER_SEND")


# ---------------------------------------------------------------------------
# Phase 2: send_pick_reminders (worker — aggregated by user)
# ---------------------------------------------------------------------------


class TestSendPickReminders:
    def test_sends_one_email_per_user(self, db):
        """User in one league gets one email."""
        manager = _make_user(db, "mgr@send1.com")
        member = _make_user(db, "member@send1.com", display_name="Bob")
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, member)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, league, t)
        _make_reminder(db, league, season, t)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            result = send_pick_reminders(db)

        assert result["sent"] >= 1
        emails = [c.kwargs["to_email"] for c in mock_send.call_args_list]
        assert "member@send1.com" in emails

    def test_user_in_two_leagues_gets_one_email(self, db):
        """User in 2 leagues with the same tournament → one email, two items."""
        mgr = _make_user(db, "mgr@dedup.com")
        member = _make_user(db, "shared@dedup.com", display_name="Shared")
        l1, s1 = _make_league_with_season(db, mgr, name="League A")
        l2, s2 = _make_league_with_season(db, mgr, name="League B")
        _add_member(db, l1, member)
        _add_member(db, l2, member)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, l1, t)
        _add_to_schedule(db, l2, t)
        _make_reminder(db, l1, s1, t)
        _make_reminder(db, l2, s2, t)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            send_pick_reminders(db)

        # Member gets one email with 2 unpicked entries.
        member_calls = [
            c for c in mock_send.call_args_list if c.kwargs["to_email"] == "shared@dedup.com"
        ]
        assert len(member_calls) == 1
        assert len(member_calls[0].kwargs["unpicked"]) == 2

    def test_skips_opted_out_members(self, db):
        manager = _make_user(db, "mgr@optout.com")
        opted_out = _make_user(db, "out@optout.com", pick_reminders_enabled=False)
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, opted_out)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, league, t)
        _make_reminder(db, league, season, t)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            send_pick_reminders(db)

        for c in mock_send.call_args_list:
            assert c.kwargs["to_email"] != "out@optout.com"

    def test_skips_already_picked_members(self, db):
        manager = _make_user(db, "mgr@picked.com")
        picker = _make_user(db, "picker@picked.com")
        league, season = _make_league_with_season(db, manager)
        _add_member(db, league, picker)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, league, t)
        _make_pick(db, league, season, picker, t)
        _make_reminder(db, league, season, t)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            send_pick_reminders(db)

        for c in mock_send.call_args_list:
            assert c.kwargs["to_email"] != "picker@picked.com"

    def test_user_picked_in_all_leagues_gets_no_email(self, db):
        """User picked in all leagues → no email at all."""
        mgr = _make_user(db, "mgr@allpicked.com")
        member = _make_user(db, "all@allpicked.com")
        l1, s1 = _make_league_with_season(db, mgr, name="L1")
        _add_member(db, l1, member)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, l1, t)
        _make_pick(db, l1, s1, member, t)
        _make_reminder(db, l1, s1, t)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            send_pick_reminders(db)

        emails = [c.kwargs["to_email"] for c in mock_send.call_args_list]
        assert "all@allpicked.com" not in emails

    def test_marks_sent_at_on_success(self, db):
        manager = _make_user(db, "mgr@sentat.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, league, t)
        _make_reminder(db, league, season, t)

        with patch("app.services.email.send_pick_reminder_email"):
            send_pick_reminders(db)

        reminder = db.query(PickReminder).first()
        assert reminder.sent_at is not None

    def test_idempotent_already_sent_skipped(self, db):
        manager = _make_user(db, "mgr@idem2.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, league, t)
        _make_reminder(db, league, season, t, sent_at=datetime.now(UTC))

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            send_pick_reminders(db)

        mock_send.assert_not_called()

    def test_no_unsent_reminders_returns_zeros(self, db):
        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            result = send_pick_reminders(db)

        assert result == {"sent": 0, "skipped": 0, "failed": 0}
        mock_send.assert_not_called()

    def test_pick_window_open_flag_passed_to_email(self, db):
        manager = _make_user(db, "mgr@flag.com")
        league, season = _make_league_with_season(db, manager)
        t = _make_tournament(db, start_days_from_now=3)
        _add_to_schedule(db, league, t)
        _make_reminder(db, league, season, t)

        with patch("app.services.email.send_pick_reminder_email") as mock_send:
            send_pick_reminders(db)

        for c in mock_send.call_args_list:
            for entry in c.kwargs["unpicked"]:
                assert "pick_window_open" in entry
