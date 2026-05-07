"""
Pick validation service.

All business rules for submitting or changing a pick live here. The router
calls these functions and handles the HTTPException they raise.

Separating validation from routing makes the logic testable without HTTP.

Rules enforced:
  1. New picks: tournament must be SCHEDULED, or IN_PROGRESS with the chosen
     golfer's tee_time still in the future (first-day late entry).
  2. Deadline: tournament.start_date must be in the future for SCHEDULED picks.
  3. Pick-change lock: if IN_PROGRESS, the new golfer's tee_time must not
     have passed. If tee_time is null when IN_PROGRESS, pick is locked.
     Exception: if the current pick's golfer has no Round 1 TournamentEntryRound
     data (they never teed off), the change is allowed as long as the new golfer
     hasn't teed off. WD status is not required — ESPN sometimes omits it for
     pre-event scratches replaced in the field before the tournament starts.
  4. Golfer must be entered in the tournament (TournamentEntry must exist).
  5. No-repeat rule: golfer not already picked this season in this league.
  6. One pick per tournament per user per season per league.
  7. Picks for a SCHEDULED tournament are blocked if any IN_PROGRESS tournament
     exists in the league's schedule (previous tournament must complete first).
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.models import (
    Golfer,
    LeagueTournament,
    Pick,
    PlayoffConfig,
    PlayoffRound,
    Season,
    Tournament,
    TournamentEntry,
    TournamentStatus,
)

log = logging.getLogger(__name__)


def validate_new_pick(
    db: Session,
    league_id: uuid.UUID,
    season: Season,
    user_id: uuid.UUID,
    tournament_id: uuid.UUID,
    golfer_id: uuid.UUID,
) -> None:
    """
    Validate all rules for a new pick submission.
    Raises HTTPException with an informative message on any failure.
    """
    # ── Group 1: Tournament context (1 query) ──────────────────────────────
    # Fetch tournament + league schedule membership + playoff round in one go.
    tournament_row = (
        db.query(Tournament, LeagueTournament, PlayoffRound)
        .outerjoin(
            LeagueTournament,
            (LeagueTournament.tournament_id == Tournament.id)
            & (LeagueTournament.league_id == league_id),
        )
        .outerjoin(
            PlayoffConfig,
            (PlayoffConfig.league_id == league_id) & (PlayoffConfig.season_id == season.id),
        )
        .outerjoin(
            PlayoffRound,
            (PlayoffRound.playoff_config_id == PlayoffConfig.id)
            & (PlayoffRound.tournament_id == Tournament.id),
        )
        .filter(Tournament.id == tournament_id)
        .first()
    )

    if not tournament_row:
        log.warning("Pick validation failed: tournament=%s not found", str(tournament_id))
        raise HTTPException(status_code=404, detail="Tournament not found")

    tournament, in_schedule, playoff_round = tournament_row

    if not in_schedule:
        log.warning(
            "Pick validation failed: tournament=%s not in league=%s schedule",
            str(tournament_id),
            str(league_id),
        )
        raise HTTPException(
            status_code=422,
            detail="This tournament is not in your league's schedule",
        )

    if playoff_round:
        log.warning(
            "Pick validation failed: tournament=%s is a playoff tournament in league=%s",
            str(tournament_id),
            str(league_id),
        )
        raise HTTPException(
            status_code=422,
            detail=(
                "This is a playoff tournament — submit your ranked preferences "
                "via the playoff bracket instead"
            ),
        )

    # Block regular-season picks on future playoff tournaments when the bracket
    # hasn't been seeded yet (pending config + unscored completed tournaments).
    # Without this, a user could submit a regular Pick for what should be a
    # playoff tournament before the PlayoffRound rows exist to trigger the
    # check above.
    if not playoff_round:
        pending_config = (
            db.query(PlayoffConfig)
            .filter_by(league_id=league_id, season_id=season.id, status="pending")
            .first()
        )
        if pending_config:
            # Check if this tournament would be a playoff round. The playoff
            # uses the last N scheduled tournaments; if this one is among the
            # remaining scheduled tournaments and equals the playoff size's
            # required round count, it's a future playoff tournament.
            unscored = (
                db.query(Pick)
                .join(Tournament, Pick.tournament_id == Tournament.id)
                .filter(
                    Pick.league_id == league_id,
                    Pick.season_id == season.id,
                    Tournament.status == TournamentStatus.COMPLETED.value,
                    Pick.points_earned.is_(None),
                )
                .first()
            )
            if unscored:
                pending_name = (
                    db.query(Tournament.name).filter_by(id=unscored.tournament_id).scalar()
                )
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Picks are temporarily unavailable — scoring for the "
                        f"{pending_name} is still being finalized. The playoff "
                        f"bracket will be seeded once all earnings are published."
                    ),
                )

    if tournament.status == TournamentStatus.COMPLETED.value:
        log.warning(
            "Pick validation failed: tournament=%s already completed, user=%s",
            str(tournament_id),
            str(user_id),
        )
        raise HTTPException(status_code=400, detail="Tournament is already completed")

    # ── Group 2: Pick window check (1 query) ─────────────────────────────
    # For scheduled tournaments, fetch global tournament state in one query
    # to determine: any in-progress? globally next? last completed?
    if tournament.status == TournamentStatus.SCHEDULED.value:
        global_tournaments = (
            db.query(Tournament.id, Tournament.name, Tournament.status, Tournament.start_date)
            .filter(Tournament.status != TournamentStatus.COMPLETED.value)
            .order_by(Tournament.start_date.asc())
            .all()
        )

        # Only block if an in-progress tournament started before this one.
        # Concurrent events that share the same start_date (e.g. Truist + Myrtle Beach
        # both starting Thursday) must not block each other.
        active = next(
            (
                t
                for t in global_tournaments
                if t.status == TournamentStatus.IN_PROGRESS.value
                and t.start_date < tournament.start_date
            ),
            None,
        )
        if active:
            log.warning(
                "Pick validation failed: tournament=%s blocked, in-progress tournament=%s exists",
                str(tournament_id),
                str(active.id),
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Picks for this tournament are not available until '{active.name}' completes"
                ),
            )

        globally_next = next(
            (t for t in global_tournaments if t.status == TournamentStatus.SCHEDULED.value),
            None,
        )
        if globally_next and tournament.start_date != globally_next.start_date:
            log.warning(
                "Pick validation failed: tournament=%s not globally next, next=%s",
                str(tournament_id),
                str(globally_next.id),
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Picks are not yet available. '{globally_next.name}' has not been "
                    "played yet — picks open once the global PGA schedule catches up."
                ),
            )

        # Check earnings on last completed tournament (separate lightweight query —
        # only runs for scheduled picks, not the hot path during live tournaments).
        last_completed = (
            db.query(Tournament)
            .filter(Tournament.status == TournamentStatus.COMPLETED.value)
            .order_by(Tournament.start_date.desc())
            .first()
        )
        if last_completed:
            earnings_check = (
                db.query(
                    sqlfunc.count(TournamentEntry.id).label("total"),
                    sqlfunc.count(TournamentEntry.earnings_usd).label("with_earnings"),
                )
                .filter(TournamentEntry.tournament_id == last_completed.id)
                .first()
            )
            if earnings_check and earnings_check.total > 0 and earnings_check.with_earnings == 0:
                log.warning(
                    "Pick validation failed: earnings not published for completed tournament=%s",
                    str(last_completed.id),
                )
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Results for '{last_completed.name}' are still being finalized. "
                        "Please try again once official earnings are published."
                    ),
                )

    if tournament.status not in (
        TournamentStatus.SCHEDULED.value,
        TournamentStatus.IN_PROGRESS.value,
    ):
        log.warning(
            "Pick validation failed: tournament=%s has invalid status=%s, user=%s",
            str(tournament_id),
            tournament.status,
            str(user_id),
        )
        raise HTTPException(
            status_code=400,
            detail="Picks can only be submitted for upcoming or live tournaments",
        )

    # ── Group 3: Golfer validation (1 query) ─────────────────────────────
    # Fetch golfer + field entry + no-repeat + duplicate check in one query.
    golfer_row = (
        db.query(
            Golfer,
            TournamentEntry,
            db.query(Pick)
            .filter_by(
                league_id=league_id,
                season_id=season.id,
                user_id=user_id,
                golfer_id=golfer_id,
            )
            .exists()
            .label("already_used"),
            db.query(Pick)
            .filter_by(
                league_id=league_id,
                season_id=season.id,
                user_id=user_id,
                tournament_id=tournament_id,
            )
            .exists()
            .label("has_pick_for_tournament"),
        )
        .outerjoin(
            TournamentEntry,
            (TournamentEntry.golfer_id == Golfer.id)
            & (TournamentEntry.tournament_id == tournament_id),
        )
        .filter(Golfer.id == golfer_id)
        .first()
    )

    if not golfer_row:
        log.warning("Pick validation failed: golfer=%s not found", str(golfer_id))
        raise HTTPException(status_code=404, detail="Golfer not found")

    golfer, entry, already_used, has_pick_for_tournament = golfer_row

    # Determine whether the field has been released (any entries exist for this tournament).
    field_released = (
        db.query(TournamentEntry).filter_by(tournament_id=tournament_id).first() is not None
    )

    if field_released and not entry:
        log.warning(
            "Pick validation failed: golfer=%s not in tournament=%s field",
            str(golfer_id),
            str(tournament_id),
        )
        raise HTTPException(
            status_code=400,
            detail="Golfer is not entered in this tournament",
        )

    # ── Tee-time deadline check ──────────────────────────────────────────
    if tournament.status == TournamentStatus.SCHEDULED.value:
        now = datetime.now(UTC)
        if entry is not None and entry.tee_time is not None:
            if entry.tee_time <= now:
                log.warning(
                    "Pick validation failed: golfer=%s already teed off, user=%s tournament=%s",
                    str(golfer_id),
                    str(user_id),
                    str(tournament_id),
                )
                raise HTTPException(
                    status_code=400,
                    detail="Pick deadline has passed — golfer has already teed off",
                )
        else:
            # Fallback when no per-golfer tee_time is available. Use strict <
            # so that a same-day tournament (Thursday start) doesn't reject
            # picks made before any tee times have actually passed.
            if tournament.start_date < datetime.now(UTC).date():
                log.warning(
                    "Pick validation failed: tournament=%s already started, user=%s",
                    str(tournament_id),
                    str(user_id),
                )
                raise HTTPException(
                    status_code=400,
                    detail="Pick deadline has passed — the tournament has already started",
                )
    else:
        now = datetime.now(UTC)
        if not field_released or entry is None or entry.tee_time is None or entry.tee_time <= now:
            log.warning(
                "Pick validation failed: deadline passed, golfer=%s user=%s tournament=%s",
                str(golfer_id),
                str(user_id),
                str(tournament_id),
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    "Pick deadline has passed — golfer has already teed off "
                    "or tee time is unavailable"
                ),
            )

    # ── Group 4: No-repeat + duplicate (from Group 3 results) ────────────
    if already_used:
        log.warning(
            "Pick validation failed: user=%s already picked golfer=%s this season in league=%s",
            str(user_id),
            str(golfer_id),
            str(league_id),
        )
        raise HTTPException(
            status_code=400,
            detail=f"You have already picked {golfer.name} this season",
        )

    if has_pick_for_tournament:
        log.warning(
            "Pick validation failed: user=%s already has pick for tournament=%s in league=%s",
            str(user_id),
            str(tournament_id),
            str(league_id),
        )
        raise HTTPException(
            status_code=400,
            detail="You have already submitted a pick for this tournament",
        )


def validate_pick_change(
    db: Session,
    pick: Pick,
    new_golfer_id: uuid.UUID,
    season: Season,
    league_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """
    Validate changing the golfer on an existing pick.
    Raises HTTPException on any failure.
    """
    tournament = pick.tournament

    if tournament.status == TournamentStatus.COMPLETED.value:
        log.warning(
            "Pick change failed: tournament=%s already completed, user=%s",
            str(tournament.id),
            str(user_id),
        )
        raise HTTPException(
            status_code=400,
            detail="Tournament is already completed — pick cannot be changed",
        )

    # Determine whether the official field has been released for this tournament.
    field_released = (
        db.query(TournamentEntry).filter_by(tournament_id=tournament.id).first() is not None
    )

    if tournament.status == TournamentStatus.IN_PROGRESS.value:
        # Check whether the current pick is locked before allowing a change.
        # pick.is_locked returns False when the current golfer withdrew before tee-off,
        # which is the exception that allows a swap even during an in-progress tournament.
        if pick.is_locked:
            log.warning(
                "Pick change failed: pick locked, golfer already teed off, user=%s tournament=%s",
                str(user_id),
                str(tournament.id),
            )
            raise HTTPException(
                status_code=400,
                detail="Pick is locked — your golfer has already teed off",
            )

        # Validate the new golfer: must be in the field and not yet teed off.
        entry = (
            db.query(TournamentEntry)
            .filter_by(tournament_id=tournament.id, golfer_id=new_golfer_id)
            .first()
        )
        if not entry:
            log.warning(
                "Pick change failed: golfer=%s not in tournament=%s field",
                str(new_golfer_id),
                str(tournament.id),
            )
            raise HTTPException(status_code=400, detail="Golfer is not entered in this tournament")

        now = datetime.now(UTC)
        if entry.tee_time is None or entry.tee_time <= now:
            log.warning(
                "Pick change failed: golfer=%s tee time passed or unavailable, user=%s",
                str(new_golfer_id),
                str(user_id),
            )
            raise HTTPException(
                status_code=400,
                detail="Pick is locked — golfer has already teed off or tee time is unavailable",
            )
    else:
        # SCHEDULED: check the new golfer's tee_time against now (mirrors
        # validate_new_pick logic). Falls back to start_date only when no
        # tee_time has been set yet.
        entry = None
        if field_released:
            entry = (
                db.query(TournamentEntry)
                .filter_by(tournament_id=tournament.id, golfer_id=new_golfer_id)
                .first()
            )
            if not entry:
                log.warning(
                    "Pick change failed: golfer=%s not in tournament=%s field",
                    str(new_golfer_id),
                    str(tournament.id),
                )
                raise HTTPException(
                    status_code=400, detail="Golfer is not entered in this tournament"
                )

        now = datetime.now(UTC)
        if entry is not None and entry.tee_time is not None:
            if entry.tee_time <= now:
                log.warning(
                    "Pick change failed: golfer=%s already teed off, user=%s",
                    str(new_golfer_id),
                    str(user_id),
                )
                raise HTTPException(
                    status_code=400,
                    detail="Pick deadline has passed — golfer has already teed off",
                )
        else:
            # Fallback: no per-golfer tee_time available. Use the tournament
            # start_date but only as a last resort. Compare against UTC date.
            if tournament.start_date < datetime.now(UTC).date():
                log.warning(
                    "Pick change failed: tournament=%s deadline passed, user=%s",
                    str(tournament.id),
                    str(user_id),
                )
                raise HTTPException(status_code=400, detail="Pick deadline has passed")

    # No-repeat: new golfer can't already be used this season (excluding this pick's golfer).
    existing = (
        db.query(Pick)
        .filter_by(
            league_id=league_id,
            season_id=season.id,
            user_id=user_id,
            golfer_id=new_golfer_id,
        )
        .filter(Pick.id != pick.id)
        .first()
    )
    if existing:
        log.warning(
            "Pick change failed: user=%s already picked golfer=%s this season in league=%s",
            str(user_id),
            str(new_golfer_id),
            str(league_id),
        )
        raise HTTPException(
            status_code=400,
            detail="You have already picked this golfer this season",
        )


def all_r1_teed_off(db: Session, tournament_id) -> bool:
    """True if the last Round 1 tee time in the tournament field has passed.

    Uses TournamentEntry.tee_time — the same source used for pick locking — so
    this function is consistent with validate_pick_change / Pick.is_locked.

    Returns False if no tee times are in the DB yet (field not synced), keeping
    picks hidden until data is available.
    """
    now_utc = datetime.now(tz=UTC)
    last_tee_time = (
        db.query(sqlfunc.max(TournamentEntry.tee_time))
        .filter(
            TournamentEntry.tournament_id == tournament_id,
            TournamentEntry.tee_time.isnot(None),
        )
        .scalar()
    )
    if last_tee_time is None:
        return False
    if last_tee_time.tzinfo is None:
        last_tee_time = last_tee_time.replace(tzinfo=UTC)
    return last_tee_time <= now_utc
