"""
Pick reminder service — weekly email reminders for unpicked league members.

Split into two phases:
  1. **Detection** (scraper, APScheduler): ``create_pick_reminders(db)`` finds all
     scheduled tournaments starting within the next 7 days, creates PickReminder
     rows, and publishes a single ``PICK_REMINDER_SEND`` SQS trigger event.
  2. **Sending** (worker, SQS): ``send_pick_reminders(db)`` aggregates all unsent
     reminders by user, sends one consolidated email per user listing all their
     unpicked leagues/tournaments, and marks reminders as sent.

This separation keeps the scraper free of email dependencies (no RESEND_API_KEY)
and deduplicates emails for users in multiple leagues.
"""

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _is_pick_window_open(db: Session, tournament) -> bool:
    """
    Return True if members can currently submit picks for this tournament.

    Mirrors the frontend pickWindowOpen logic:
      - Tournament is in_progress → always open (until R1 tees off)
      - No globally in_progress tournament AND this is the globally-next
        scheduled tournament → open
    """
    from app.models import Tournament, TournamentStatus

    if tournament.status == TournamentStatus.IN_PROGRESS.value:
        return True

    has_global_in_progress = (
        db.query(Tournament).filter(Tournament.status == TournamentStatus.IN_PROGRESS.value).first()
    ) is not None

    if has_global_in_progress:
        return False

    globally_next = (
        db.query(Tournament)
        .filter(Tournament.status == TournamentStatus.SCHEDULED.value)
        .order_by(Tournament.start_date.asc())
        .first()
    )
    return globally_next is not None and tournament.start_date == globally_next.start_date


# ---------------------------------------------------------------------------
# Phase 1: Detection (scraper)
# ---------------------------------------------------------------------------


def create_pick_reminders(db: Session) -> dict:
    """
    Entry point called by the Wednesday APScheduler job (scraper container).

    Finds all scheduled PGA tournaments starting within the next 7 days,
    creates PickReminder rows for each affected active-season league,
    then publishes a single PICK_REMINDER_SEND SQS trigger event for the
    worker to process all unsent reminders.

    Returns a summary dict: {"reminders_created": int, "skipped": int,
    "published": bool}.
    """
    from app.models import (
        LeagueTournament,
        PickReminder,
        Season,
        Tournament,
        TournamentStatus,
    )
    from app.services.sqs import publish

    now_utc = datetime.now(tz=UTC)
    today = now_utc.date()
    window_end = today + timedelta(days=7)

    upcoming = (
        db.query(Tournament)
        .filter(
            Tournament.status == TournamentStatus.SCHEDULED.value,
            Tournament.start_date >= today,
            Tournament.start_date <= window_end,
        )
        .all()
    )

    if not upcoming:
        log.info("Pick reminders: no tournaments starting in the next 7 days")
        return {"reminders_created": 0, "skipped": 0, "published": False}

    total_created = 0
    total_skipped = 0

    for tournament in upcoming:
        league_ids = [
            row.league_id
            for row in db.query(LeagueTournament.league_id)
            .filter(LeagueTournament.tournament_id == tournament.id)
            .all()
        ]
        if not league_ids:
            continue

        for league_id in league_ids:
            season: Season | None = (
                db.query(Season).filter_by(league_id=league_id, is_active=True).first()
            )
            if season is None:
                continue

            existing: PickReminder | None = (
                db.query(PickReminder)
                .filter_by(
                    league_id=league_id,
                    season_id=season.id,
                    tournament_id=tournament.id,
                )
                .first()
            )

            if existing:
                if existing.sent_at or existing.failed_at:
                    total_skipped += 1
                # else: unsent reminder already exists, will be picked up
                continue

            db.add(
                PickReminder(
                    id=uuid.uuid4(),
                    league_id=league_id,
                    season_id=season.id,
                    tournament_id=tournament.id,
                    scheduled_at=now_utc,
                )
            )
            total_created += 1

    db.commit()

    # Publish a single trigger — the worker aggregates all unsent reminders.
    has_unsent = total_created > 0 or (
        db.query(PickReminder)
        .filter(
            PickReminder.sent_at.is_(None),
            PickReminder.failed_at.is_(None),
        )
        .first()
        is not None
    )

    if has_unsent:
        publish("PICK_REMINDER_SEND")
        log.info(
            "Pick reminders: created=%d skipped=%d, published trigger",
            total_created,
            total_skipped,
        )
    else:
        log.info(
            "Pick reminders: created=%d skipped=%d, no unsent — skipping publish",
            total_created,
            total_skipped,
        )

    return {
        "reminders_created": total_created,
        "skipped": total_skipped,
        "published": has_unsent,
    }


# ---------------------------------------------------------------------------
# Phase 2: Sending (worker)
# ---------------------------------------------------------------------------


def send_pick_reminders(db: Session) -> dict:
    """
    Called by the SQS worker for the PICK_REMINDER_SEND trigger.

    Aggregates all unsent PickReminder rows by user, sends one consolidated
    email per user listing all their unpicked leagues/tournaments, then marks
    all related reminders as sent.

    Returns {"sent": int, "skipped": int, "failed": int}.
    """
    from app.models import (
        LeagueMember,
        LeagueMemberStatus,
        Pick,
        PickReminder,
        Season,
        Tournament,
        User,
    )
    from app.services.email import send_pick_reminder_email

    now_utc = datetime.now(tz=UTC)

    # All unsent, non-failed reminders.
    unsent = (
        db.query(PickReminder)
        .filter(
            PickReminder.sent_at.is_(None),
            PickReminder.failed_at.is_(None),
        )
        .all()
    )

    if not unsent:
        log.info("PICK_REMINDER_SEND: no unsent reminders")
        return {"sent": 0, "skipped": 0, "failed": 0}

    # Pre-load tournaments and seasons for all reminders.
    tournament_ids = {r.tournament_id for r in unsent}
    tournaments = {
        t.id: t for t in db.query(Tournament).filter(Tournament.id.in_(tournament_ids)).all()
    }

    season_ids = {r.season_id for r in unsent}
    seasons = {s.id: s for s in db.query(Season).filter(Season.id.in_(season_ids)).all()}

    # Pre-compute pick window status per tournament (shared across leagues).
    window_open_cache: dict[uuid.UUID, bool] = {}
    for tid, t in tournaments.items():
        window_open_cache[tid] = _is_pick_window_open(db, t)

    # Group reminders by league to find all affected users.
    # For each reminder, find unpicked members and build a per-user list.
    # user_id → list of {league_name, league_id, tournament_name, start_date,
    #                     pick_window_open, reminder}
    user_unpicked: dict[uuid.UUID, list[dict]] = defaultdict(list)
    reminder_to_mark: list[PickReminder] = []

    for reminder in unsent:
        tournament = tournaments.get(reminder.tournament_id)
        season = seasons.get(reminder.season_id)
        if not tournament or not season or not season.is_active:
            continue

        league = reminder.league
        if not league:
            continue

        members = (
            db.query(LeagueMember)
            .filter_by(
                league_id=reminder.league_id,
                status=LeagueMemberStatus.APPROVED.value,
            )
            .all()
        )

        for member in members:
            user: User | None = db.get(User, member.user_id)
            if not user or not user.pick_reminders_enabled:
                continue

            already_picked = (
                db.query(Pick)
                .filter_by(
                    league_id=reminder.league_id,
                    season_id=reminder.season_id,
                    user_id=member.user_id,
                    tournament_id=reminder.tournament_id,
                )
                .first()
            )
            if already_picked:
                continue

            user_unpicked[member.user_id].append(
                {
                    "league_name": league.name,
                    "league_id": str(reminder.league_id),
                    "tournament_name": tournament.name,
                    "start_date": tournament.start_date.strftime("%B %-d"),
                    "pick_window_open": window_open_cache.get(reminder.tournament_id, False),
                    "reminder": reminder,
                }
            )

        reminder_to_mark.append(reminder)

    # Send one email per user with all their unpicked leagues.
    total_sent = 0
    total_skipped = 0
    total_failed = 0
    sent_reminder_ids: set[uuid.UUID] = set()

    for user_id, entries in user_unpicked.items():
        user = db.get(User, user_id)
        if not user:
            total_skipped += 1
            continue

        try:
            send_pick_reminder_email(
                to_email=user.email,
                display_name=user.display_name,
                unpicked=entries,
            )
            total_sent += 1
            for e in entries:
                sent_reminder_ids.add(e["reminder"].id)
        except Exception as exc:
            total_failed += 1
            log.error(
                "PICK_REMINDER_SEND: email failed for user=%s: %s",
                user_id,
                exc,
            )

    # Mark all reminders that had at least one email sent as done.
    for reminder in reminder_to_mark:
        reminder.attempt_count += 1
        if reminder.id in sent_reminder_ids:
            reminder.sent_at = now_utc
        elif reminder.attempt_count >= reminder.max_attempts:
            reminder.failed_at = now_utc
            reminder.error_message = "All email sends for this reminder failed"

    db.commit()

    log.info(
        "PICK_REMINDER_SEND: sent=%d skipped=%d failed=%d reminders_marked=%d",
        total_sent,
        total_skipped,
        total_failed,
        len(sent_reminder_ids),
    )

    return {"sent": total_sent, "skipped": total_skipped, "failed": total_failed}
