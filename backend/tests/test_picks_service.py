"""
Tests for app/services/picks.py — pick validation service.

Covers:
  validate_new_pick  — all validation paths including edge cases
  validate_pick_change — all validation paths
  all_r1_teed_off — tee time lookup

These tests call the service functions directly (no HTTP). Each function raises
HTTPException on validation failure, so we assert on status_code and detail.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeagueTournament,
    Pick,
    PlayoffConfig,
    PlayoffRound,
    Season,
    Tournament,
    TournamentEntry,
    User,
)
from app.models.tournament import TournamentEntryRound, TournamentStatus
from app.services.auth import hash_password
from app.services.picks import all_r1_teed_off, validate_new_pick, validate_pick_change

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db, email: str, display_name: str = "Player") -> User:
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        display_name=display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_league(db, creator: User) -> tuple[League, Season]:
    league = League(name="Test League", created_by=creator.id)
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=creator.id,
            role=LeagueMemberRole.MANAGER.value,
            status=LeagueMemberStatus.APPROVED.value,
        )
    )
    season = Season(league_id=league.id, year=2026, is_active=True)
    db.add(season)
    db.commit()
    db.refresh(league)
    db.refresh(season)
    return league, season


def _make_golfer(db, name: str = "Test Golfer") -> Golfer:
    g = Golfer(
        pga_tour_id=f"G{uuid.uuid4().hex[:8]}",
        name=name,
        world_ranking=50,
        country="USA",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _make_tournament(
    db,
    status: str = TournamentStatus.SCHEDULED.value,
    days_from_now: int = 7,
    name: str = "Test Open",
) -> Tournament:
    start = date.today() + timedelta(days=days_from_now)
    t = Tournament(
        pga_tour_id=f"R{uuid.uuid4().hex[:8]}",
        name=name,
        start_date=start,
        end_date=start + timedelta(days=3),
        status=status,
        multiplier=1.0,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _add_to_schedule(
    db, league: League, tournament: Tournament, multiplier: float = 1.0
) -> LeagueTournament:
    lt = LeagueTournament(
        league_id=league.id,
        tournament_id=tournament.id,
        multiplier=multiplier,
    )
    db.add(lt)
    db.commit()
    db.refresh(lt)
    return lt


def _make_entry(
    db,
    tournament: Tournament,
    golfer: Golfer,
    tee_time: datetime | None = None,
    earnings_usd: int | None = None,
    status: str | None = None,
) -> TournamentEntry:
    entry = TournamentEntry(
        tournament_id=tournament.id,
        golfer_id=golfer.id,
        tee_time=tee_time,
        earnings_usd=earnings_usd,
        status=status,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _make_pick(
    db,
    league: League,
    season: Season,
    user: User,
    tournament: Tournament,
    golfer: Golfer,
) -> Pick:
    pick = Pick(
        league_id=league.id,
        season_id=season.id,
        user_id=user.id,
        tournament_id=tournament.id,
        golfer_id=golfer.id,
    )
    db.add(pick)
    db.commit()
    # Re-query to load relationships (tournament, golfer, entry) used by is_locked.
    pick = db.query(Pick).filter_by(id=pick.id).first()
    return pick


# ---------------------------------------------------------------------------
# TestValidateNewPickTournamentChecks
# ---------------------------------------------------------------------------


class TestValidateNewPickTournamentChecks:
    def test_tournament_not_found_raises_404(self, db):
        user = _make_user(db, "u1@example.com")
        _, season = _make_league(db, user)
        league, _ = _make_league(db, _make_user(db, "u2@example.com"))

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=uuid.uuid4(),
                golfer_id=uuid.uuid4(),
            )
        assert exc_info.value.status_code == 404
        assert "tournament not found" in exc_info.value.detail.lower()

    def test_tournament_not_in_schedule_raises_422(self, db):
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db)  # not added to league schedule
        golfer = _make_golfer(db)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 422
        assert "schedule" in exc_info.value.detail.lower()

    def test_playoff_tournament_raises_422(self, db):
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db)
        _add_to_schedule(db, league, tournament)
        golfer = _make_golfer(db)

        # Create playoff config and a round pointing at this tournament.
        config = PlayoffConfig(
            league_id=league.id,
            season_id=season.id,
            playoff_size=4,
            picks_per_round=[2],
        )
        db.add(config)
        db.flush()
        pround = PlayoffRound(
            playoff_config_id=config.id,
            round_number=1,
            tournament_id=tournament.id,
            status="pending",
        )
        db.add(pround)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 422
        assert "playoff" in exc_info.value.detail.lower()

    def test_completed_tournament_raises_400(self, db):
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db, status=TournamentStatus.COMPLETED.value, days_from_now=-5)
        _add_to_schedule(db, league, tournament)
        golfer = _make_golfer(db)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "completed" in exc_info.value.detail.lower()

    def test_scheduled_blocked_while_another_in_progress(self, db):
        """A pick for a SCHEDULED tournament is blocked if any tournament is IN_PROGRESS."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)

        # An unrelated tournament that is currently in progress.
        _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0, name="Live Event"
        )

        # The pick target — a future scheduled tournament.
        target = _make_tournament(
            db, status=TournamentStatus.SCHEDULED.value, days_from_now=7, name="Future Event"
        )
        _add_to_schedule(db, league, target)
        golfer = _make_golfer(db)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=target.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "live event" in exc_info.value.detail.lower()

    def test_scheduled_blocked_if_not_globally_next(self, db):
        """A pick for a SCHEDULED tournament is blocked if it is not the next upcoming tournament
        globally."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)

        # The globally-next scheduled tournament (not in league schedule).
        _make_tournament(
            db, status=TournamentStatus.SCHEDULED.value, days_from_now=3, name="Next Up"
        )

        # A later tournament that the user is trying to pick for.
        later = _make_tournament(
            db, status=TournamentStatus.SCHEDULED.value, days_from_now=10, name="Later Event"
        )
        _add_to_schedule(db, league, later)
        golfer = _make_golfer(db)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=later.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "picks are not yet available" in exc_info.value.detail.lower()

    def test_scheduled_blocked_if_last_completed_earnings_not_published(self, db):
        """Picks for a SCHEDULED tournament are blocked when the last completed tournament
        has field entries but no earnings recorded (results still being finalized)."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)

        # Create a completed tournament with an entry but no earnings.
        last_completed = _make_tournament(
            db, status=TournamentStatus.COMPLETED.value, days_from_now=-7, name="Last Week"
        )
        completed_golfer = _make_golfer(db, "Completed Golfer")
        _make_entry(db, last_completed, completed_golfer, earnings_usd=None)  # no earnings yet

        # The pick target is the globally-next scheduled tournament.
        target = _make_tournament(
            db, status=TournamentStatus.SCHEDULED.value, days_from_now=7, name="This Week"
        )
        _add_to_schedule(db, league, target)
        golfer = _make_golfer(db)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=target.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "still being finalized" in exc_info.value.detail.lower()

    def test_scheduled_allowed_when_last_completed_has_earnings(self, db):
        """Picks open normally once the last completed tournament has published earnings.
        This test does NOT raise — it reaches the golfer check instead."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)

        # Completed tournament with earnings published.
        last_completed = _make_tournament(
            db, status=TournamentStatus.COMPLETED.value, days_from_now=-7, name="Last Week"
        )
        completed_golfer = _make_golfer(db, "Completed Golfer")
        _make_entry(db, last_completed, completed_golfer, earnings_usd=1_500_000)

        # Pick target is the globally-next scheduled tournament.
        target = _make_tournament(
            db, status=TournamentStatus.SCHEDULED.value, days_from_now=7, name="This Week"
        )
        _add_to_schedule(db, league, target)

        # Non-existent golfer — the function should reach the golfer check (404),
        # meaning the earnings-finalization block did NOT fire.
        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=target.id,
                golfer_id=uuid.uuid4(),
            )
        # 404 means we got past the earnings check.
        assert exc_info.value.status_code == 404
        assert "golfer not found" in exc_info.value.detail.lower()

    def test_unknown_status_raises_400(self, db):
        """A tournament with an unrecognized status that is not SCHEDULED or IN_PROGRESS
        should raise 400 (the catch-all guard at the bottom of the status checks)."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value, days_from_now=7)
        _add_to_schedule(db, league, tournament)
        golfer = _make_golfer(db)

        # Bypass the ORM validator by mutating after commit.
        tournament.status = "unknown_status"
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "picks can only be submitted" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# TestValidateNewPickGolferChecks
# ---------------------------------------------------------------------------


class TestValidateNewPickGolferChecks:
    def test_golfer_not_found_raises_404(self, db):
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value, days_from_now=7)
        _add_to_schedule(db, league, tournament)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=uuid.uuid4(),  # non-existent golfer
            )
        assert exc_info.value.status_code == 404
        assert "golfer not found" in exc_info.value.detail.lower()

    def test_golfer_not_in_field_when_field_released(self, db):
        """When TournamentEntry rows exist (field released), the picked golfer must have one."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value, days_from_now=7)
        _add_to_schedule(db, league, tournament)

        # Release the field with one golfer.
        field_golfer = _make_golfer(db, "Field Golfer")
        _make_entry(db, tournament, field_golfer, tee_time=datetime.now(UTC) + timedelta(hours=24))

        # The golfer being picked is NOT in the field.
        picked_golfer = _make_golfer(db, "Not In Field")

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=picked_golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "not entered" in exc_info.value.detail.lower()

    def test_scheduled_with_past_tee_time_raises_400(self, db):
        """For SCHEDULED tournaments, if the golfer's R1 tee time has passed, picks are blocked."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value, days_from_now=0)
        _add_to_schedule(db, league, tournament)
        golfer = _make_golfer(db)
        # Tee time already passed.
        past_tee_time = datetime.now(UTC) - timedelta(hours=2)
        _make_entry(db, tournament, golfer, tee_time=past_tee_time)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "teed off" in exc_info.value.detail.lower()

    def test_scheduled_no_tee_time_but_start_date_past_raises_400(self, db):
        """For SCHEDULED tournaments with no tee times, start_date is used as the deadline."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        # Tournament started yesterday — start_date is in the past.
        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value, days_from_now=-1)
        _add_to_schedule(db, league, tournament)
        golfer = _make_golfer(db)
        # Entry exists but has no tee_time.
        _make_entry(db, tournament, golfer, tee_time=None)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "deadline has passed" in exc_info.value.detail.lower()

    def test_in_progress_no_field_raises_400(self, db):
        """For IN_PROGRESS tournaments with no field entries, new picks are blocked."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        _add_to_schedule(db, league, tournament)
        golfer = _make_golfer(db)
        # No TournamentEntry rows at all — field not released.

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "deadline has passed" in exc_info.value.detail.lower()

    def test_in_progress_tee_time_passed_raises_400(self, db):
        """For IN_PROGRESS tournaments, picking a golfer whose tee time has passed is blocked."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        _add_to_schedule(db, league, tournament)
        golfer = _make_golfer(db)
        past_tee_time = datetime.now(UTC) - timedelta(hours=1)
        _make_entry(db, tournament, golfer, tee_time=past_tee_time)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "deadline has passed" in exc_info.value.detail.lower()

    def test_in_progress_no_tee_time_on_entry_raises_400(self, db):
        """For IN_PROGRESS tournaments, a null tee_time is treated as locked (safety net)."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        _add_to_schedule(db, league, tournament)
        golfer = _make_golfer(db)
        # Entry exists but tee_time is null.
        _make_entry(db, tournament, golfer, tee_time=None)

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "deadline has passed" in exc_info.value.detail.lower()

    def test_in_progress_future_tee_time_passes_deadline_check(self, db):
        """For IN_PROGRESS, a golfer whose tee_time is in the future is a valid pick target.
        Validation should proceed past the deadline check to the no-repeat check."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        _add_to_schedule(db, league, tournament)
        golfer = _make_golfer(db)
        future_tee_time = datetime.now(UTC) + timedelta(hours=3)
        _make_entry(db, tournament, golfer, tee_time=future_tee_time)

        # Should not raise — no existing picks means it passes all checks.
        validate_new_pick(
            db,
            league_id=league.id,
            season=season,
            user_id=user.id,
            tournament_id=tournament.id,
            golfer_id=golfer.id,
        )


# ---------------------------------------------------------------------------
# TestValidateNewPickDuplicateChecks
# ---------------------------------------------------------------------------


class TestValidateNewPickDuplicateChecks:
    def test_no_repeat_same_golfer_same_season_raises_400(self, db):
        """A golfer already used in this season cannot be picked again in another tournament."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        golfer = _make_golfer(db)

        # Completed tournament — golfer was picked there.
        completed = _make_tournament(
            db, status=TournamentStatus.COMPLETED.value, days_from_now=-7, name="Old Tournament"
        )
        _add_to_schedule(db, league, completed)

        # Insert the first pick for this golfer directly into the DB.
        _make_pick(db, league, season, user, completed, golfer)

        # New tournament — the globally-next scheduled one.
        upcoming = _make_tournament(
            db, status=TournamentStatus.SCHEDULED.value, days_from_now=7, name="New Tournament"
        )
        _add_to_schedule(db, league, upcoming)

        # Mark the completed tournament as having earnings so the earnings check passes.
        other_golfer = _make_golfer(db, "Other Golfer")
        _make_entry(db, completed, other_golfer, earnings_usd=500_000)

        # The golfer is not yet in the new tournament's field — field not released.
        # We still need to add the golfer to the new field for it to reach the no-repeat check.
        # But since no entries exist, field is not released and any golfer is allowed past
        # the field check. So the no-repeat check fires.

        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=upcoming.id,
                golfer_id=golfer.id,
            )
        assert exc_info.value.status_code == 400
        assert "already picked" in exc_info.value.detail.lower()

    def test_duplicate_pick_same_tournament_raises_400(self, db):
        """A user cannot submit two picks for the same tournament."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)

        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value, days_from_now=7)
        _add_to_schedule(db, league, tournament)
        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B")

        # First pick for golfer_a in this tournament.
        _make_pick(db, league, season, user, tournament, golfer_a)

        # Now try to pick golfer_b (a different golfer) for the same tournament.
        with pytest.raises(HTTPException) as exc_info:
            validate_new_pick(
                db,
                league_id=league.id,
                season=season,
                user_id=user.id,
                tournament_id=tournament.id,
                golfer_id=golfer_b.id,
            )
        assert exc_info.value.status_code == 400
        assert "already submitted a pick" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# TestValidatePickChange
# ---------------------------------------------------------------------------


class TestValidatePickChange:
    def test_completed_tournament_raises_400(self, db):
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db, status=TournamentStatus.COMPLETED.value, days_from_now=-5)
        _add_to_schedule(db, league, tournament)
        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B")
        pick = _make_pick(db, league, season, user, tournament, golfer_a)

        with pytest.raises(HTTPException) as exc_info:
            validate_pick_change(
                db,
                pick=pick,
                new_golfer_id=golfer_b.id,
                season=season,
                league_id=league.id,
                user_id=user.id,
            )
        assert exc_info.value.status_code == 400
        assert "completed" in exc_info.value.detail.lower()

    def test_in_progress_locked_pick_raises_400(self, db):
        """When the current pick's golfer has teed off (R1 TournamentEntryRound exists), the pick
        is locked."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        _add_to_schedule(db, league, tournament)
        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B")

        # Create the entry with a past tee_time so is_locked returns True.
        past_tee_time = datetime.now(UTC) - timedelta(hours=2)
        entry_a = _make_entry(db, tournament, golfer_a, tee_time=past_tee_time)

        # Add R1 TournamentEntryRound so r1_played=True in is_locked.
        round_a = TournamentEntryRound(
            tournament_entry_id=entry_a.id,
            round_number=1,
            tee_time=past_tee_time,
            score_to_par=-2,
            is_playoff=False,
        )
        db.add(round_a)
        db.commit()

        pick = _make_pick(db, league, season, user, tournament, golfer_a)

        with pytest.raises(HTTPException) as exc_info:
            validate_pick_change(
                db,
                pick=pick,
                new_golfer_id=golfer_b.id,
                season=season,
                league_id=league.id,
                user_id=user.id,
            )
        assert exc_info.value.status_code == 400
        assert "locked" in exc_info.value.detail.lower()

    def test_in_progress_new_golfer_not_in_field_raises_400(self, db):
        """When swapping during IN_PROGRESS, the new golfer must be in the tournament field."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        _add_to_schedule(db, league, tournament)

        # Current pick's golfer: no R1 round data → is_locked=False (WD scenario).
        golfer_a = _make_golfer(db, "Golfer A WD")
        _make_entry(db, tournament, golfer_a, tee_time=datetime.now(UTC) - timedelta(hours=1))
        # No TournamentEntryRound row → r1_played=False → is_locked=False.

        golfer_b = _make_golfer(db, "Golfer B Not In Field")
        # golfer_b has NO TournamentEntry for this tournament.

        pick = _make_pick(db, league, season, user, tournament, golfer_a)

        with pytest.raises(HTTPException) as exc_info:
            validate_pick_change(
                db,
                pick=pick,
                new_golfer_id=golfer_b.id,
                season=season,
                league_id=league.id,
                user_id=user.id,
            )
        assert exc_info.value.status_code == 400
        assert "not entered" in exc_info.value.detail.lower()

    def test_in_progress_new_golfer_tee_time_passed_raises_400(self, db):
        """When swapping during IN_PROGRESS, the new golfer's tee_time must not have passed."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        _add_to_schedule(db, league, tournament)

        # Current pick's golfer: no R1 round → is_locked=False.
        golfer_a = _make_golfer(db, "Golfer A WD")
        _make_entry(db, tournament, golfer_a, tee_time=datetime.now(UTC) - timedelta(hours=3))
        # No TournamentEntryRound → r1_played=False → is_locked=False.

        # New golfer has a past tee_time.
        golfer_b = _make_golfer(db, "Golfer B Already Teed")
        _make_entry(db, tournament, golfer_b, tee_time=datetime.now(UTC) - timedelta(hours=1))

        pick = _make_pick(db, league, season, user, tournament, golfer_a)

        with pytest.raises(HTTPException) as exc_info:
            validate_pick_change(
                db,
                pick=pick,
                new_golfer_id=golfer_b.id,
                season=season,
                league_id=league.id,
                user_id=user.id,
            )
        assert exc_info.value.status_code == 400
        assert "locked" in exc_info.value.detail.lower()

    def test_in_progress_new_golfer_null_tee_time_raises_400(self, db):
        """For IN_PROGRESS, a null tee_time on the new golfer is treated as locked."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        _add_to_schedule(db, league, tournament)

        # Current pick's golfer: no R1 round → is_locked=False.
        golfer_a = _make_golfer(db, "Golfer A WD")
        _make_entry(db, tournament, golfer_a, tee_time=datetime.now(UTC) - timedelta(hours=3))

        # New golfer has no tee_time set.
        golfer_b = _make_golfer(db, "Golfer B No Tee Time")
        _make_entry(db, tournament, golfer_b, tee_time=None)

        pick = _make_pick(db, league, season, user, tournament, golfer_a)

        with pytest.raises(HTTPException) as exc_info:
            validate_pick_change(
                db,
                pick=pick,
                new_golfer_id=golfer_b.id,
                season=season,
                league_id=league.id,
                user_id=user.id,
            )
        assert exc_info.value.status_code == 400
        assert "locked" in exc_info.value.detail.lower()

    def test_scheduled_past_start_date_raises_400(self, db):
        """For SCHEDULED tournaments, changing a pick is blocked once start_date has passed."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        # Tournament started yesterday.
        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value, days_from_now=-1)
        _add_to_schedule(db, league, tournament)
        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B")
        _make_entry(db, tournament, golfer_a)
        pick = _make_pick(db, league, season, user, tournament, golfer_a)

        with pytest.raises(HTTPException) as exc_info:
            validate_pick_change(
                db,
                pick=pick,
                new_golfer_id=golfer_b.id,
                season=season,
                league_id=league.id,
                user_id=user.id,
            )
        assert exc_info.value.status_code == 400
        assert "deadline has passed" in exc_info.value.detail.lower()

    def test_scheduled_field_released_new_golfer_not_in_field_raises_400(self, db):
        """For SCHEDULED tournaments with a released field, the new golfer must be in the field."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value, days_from_now=7)
        _add_to_schedule(db, league, tournament)

        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B Not In Field")
        _make_entry(db, tournament, golfer_a)  # field has golfer_a → field is released
        pick = _make_pick(db, league, season, user, tournament, golfer_a)

        # golfer_b has no entry — not in the field.
        with pytest.raises(HTTPException) as exc_info:
            validate_pick_change(
                db,
                pick=pick,
                new_golfer_id=golfer_b.id,
                season=season,
                league_id=league.id,
                user_id=user.id,
            )
        assert exc_info.value.status_code == 400
        assert "not entered" in exc_info.value.detail.lower()

    def test_no_repeat_on_change_raises_400(self, db):
        """Cannot change to a golfer who has already been picked this season (in another
        tournament)."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)

        # Tournament A (completed) — golfer_b was picked there.
        completed = _make_tournament(
            db, status=TournamentStatus.COMPLETED.value, days_from_now=-7, name="Past Event"
        )
        _add_to_schedule(db, league, completed)
        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B")
        _make_pick(db, league, season, user, completed, golfer_b)

        # Tournament B (scheduled) — current pick is golfer_a; want to change to golfer_b.
        upcoming = _make_tournament(
            db, status=TournamentStatus.SCHEDULED.value, days_from_now=7, name="Future Event"
        )
        _add_to_schedule(db, league, upcoming)
        pick = _make_pick(db, league, season, user, upcoming, golfer_a)

        with pytest.raises(HTTPException) as exc_info:
            validate_pick_change(
                db,
                pick=pick,
                new_golfer_id=golfer_b.id,
                season=season,
                league_id=league.id,
                user_id=user.id,
            )
        assert exc_info.value.status_code == 400
        assert "already picked" in exc_info.value.detail.lower()

    def test_valid_scheduled_change_succeeds(self, db):
        """A valid pick change for a SCHEDULED tournament with future start_date does not raise."""
        user = _make_user(db, "u1@example.com")
        league, season = _make_league(db, user)
        tournament = _make_tournament(db, status=TournamentStatus.SCHEDULED.value, days_from_now=7)
        _add_to_schedule(db, league, tournament)

        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B")
        # No field entries → field not released → golfer_b's field presence is not checked.
        pick = _make_pick(db, league, season, user, tournament, golfer_a)

        # Should not raise.
        validate_pick_change(
            db,
            pick=pick,
            new_golfer_id=golfer_b.id,
            season=season,
            league_id=league.id,
            user_id=user.id,
        )


# ---------------------------------------------------------------------------
# TestAllR1TeedOff
# ---------------------------------------------------------------------------


class TestAllR1TeedOff:
    def test_returns_false_when_no_tee_times(self, db):
        """When no TournamentEntry rows have tee_time set, the field hasn't been synced → False."""
        tournament = _make_tournament(db)
        golfer = _make_golfer(db)
        _make_entry(db, tournament, golfer, tee_time=None)

        result = all_r1_teed_off(db, tournament.id)
        assert result is False

    def test_returns_false_when_no_entries_at_all(self, db):
        """No entries at all → no tee times → False."""
        tournament = _make_tournament(db)
        result = all_r1_teed_off(db, tournament.id)
        assert result is False

    def test_returns_false_when_latest_tee_time_is_in_future(self, db):
        """Last tee_time is still in the future → not all have teed off → False."""
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B")
        _make_entry(db, tournament, golfer_a, tee_time=datetime.now(UTC) - timedelta(hours=1))
        _make_entry(db, tournament, golfer_b, tee_time=datetime.now(UTC) + timedelta(hours=2))

        result = all_r1_teed_off(db, tournament.id)
        assert result is False

    def test_returns_true_when_all_tee_times_are_in_past(self, db):
        """All tee_times are in the past → everyone has teed off → True."""
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B")
        _make_entry(db, tournament, golfer_a, tee_time=datetime.now(UTC) - timedelta(hours=5))
        _make_entry(db, tournament, golfer_b, tee_time=datetime.now(UTC) - timedelta(hours=2))

        result = all_r1_teed_off(db, tournament.id)
        assert result is True

    def test_entries_with_null_tee_time_are_ignored(self, db):
        """Null tee_times are excluded from the MAX() aggregate.
        If the only non-null tee_time has passed, function returns True."""
        tournament = _make_tournament(
            db, status=TournamentStatus.IN_PROGRESS.value, days_from_now=0
        )
        golfer_a = _make_golfer(db, "Golfer A")
        golfer_b = _make_golfer(db, "Golfer B No Time")
        _make_entry(db, tournament, golfer_a, tee_time=datetime.now(UTC) - timedelta(hours=3))
        _make_entry(db, tournament, golfer_b, tee_time=None)  # null — excluded from MAX

        result = all_r1_teed_off(db, tournament.id)
        assert result is True
