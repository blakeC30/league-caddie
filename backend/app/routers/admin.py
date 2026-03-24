"""
Admin router — /admin/*

Platform-admin-only endpoints locked behind `require_platform_admin`.
Regular users and league admins cannot access these routes.

Endpoints:
  GET  /admin/stats                    Aggregated platform statistics (counts only, no PII)
  POST /admin/sync                                   Full sync for the current calendar year
  POST /admin/sync/{pga_tour_id}                     Sync a single tournament by its ESPN event ID
  GET  /admin/stripe/webhook-failures                List unresolved webhook failures
  POST /admin/stripe/webhook-failures/{id}/retry     Retry a failed webhook event
  POST /admin/import-members                         Bulk import members from CSV
  POST /admin/import-picks                           Bulk import picks from CSV
"""

import csv
import io
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_platform_admin
from app.limiter import limiter
from app.models import (
    Golfer,
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeaguePurchase,
    LeagueTournament,
    Pick,
    PlayoffConfig,
    Season,
    StripeWebhookFailure,
    Tournament,
    TournamentStatus,
    User,
)
from app.models.deleted_league import DeletedLeague
from app.services.auth import hash_password
from app.services.scraper import full_sync, score_picks, sync_tournament

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Platform statistics
# ---------------------------------------------------------------------------


class TierBreakdownItem(BaseModel):
    tier: str
    count: int


class AdminStatsOut(BaseModel):
    # Users
    total_users: int
    new_users_30d: int
    # Leagues
    total_leagues: int
    paid_leagues_this_year: int
    total_approved_memberships: int
    # Tier breakdown (paid leagues in the current season year)
    leagues_by_tier: list[TierBreakdownItem]
    # Picks
    total_picks: int
    picks_last_7d: int
    # Tournaments
    tournaments_scheduled: int
    tournaments_in_progress: int
    tournaments_completed: int
    # Leagues — additional breakdown
    leagues_with_playoffs: int
    leagues_accepting_requests: int
    avg_members_per_league: float
    deleted_leagues_total: int
    # Operational
    open_webhook_failures: int


@router.get("/stats", response_model=AdminStatsOut)
@limiter.limit("30/minute")
def get_platform_stats(
    request: Request,
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """
    Return aggregated platform statistics.

    Only counts and aggregates are returned — no PII (emails, names, user IDs)
    is exposed. All values are scoped to the current calendar year where relevant.
    """
    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago = now - timedelta(days=7)
    current_year = date.today().year

    total_users = db.query(func.count(User.id)).scalar() or 0
    new_users_30d = (
        db.query(func.count(User.id)).filter(User.created_at >= thirty_days_ago).scalar() or 0
    )

    total_leagues = db.query(func.count(League.id)).scalar() or 0
    paid_leagues_this_year = (
        db.query(func.count(LeaguePurchase.id))
        .filter(
            LeaguePurchase.season_year == current_year,
            LeaguePurchase.paid_at.isnot(None),
            LeaguePurchase.amount_cents > 0,
        )
        .scalar()
        or 0
    )
    total_approved_memberships = (
        db.query(func.count(LeagueMember.user_id))
        .filter(LeagueMember.status == LeagueMemberStatus.APPROVED)
        .scalar()
        or 0
    )

    # Count paid purchases per tier for the current year, sorted by count desc.
    # Excludes platform-admin leagues (amount_cents=0) — they don't represent real revenue.
    tier_rows = (
        db.query(LeaguePurchase.tier, func.count(LeaguePurchase.id).label("n"))
        .filter(
            LeaguePurchase.season_year == current_year,
            LeaguePurchase.paid_at.isnot(None),
            LeaguePurchase.amount_cents > 0,
        )
        .group_by(LeaguePurchase.tier)
        .order_by(func.count(LeaguePurchase.id).desc())
        .all()
    )
    leagues_by_tier = [TierBreakdownItem(tier=tier or "unknown", count=n) for tier, n in tier_rows]

    total_picks = db.query(func.count(Pick.id)).scalar() or 0
    picks_last_7d = (
        db.query(func.count(Pick.id)).filter(Pick.submitted_at >= seven_days_ago).scalar() or 0
    )

    tournaments_scheduled = (
        db.query(func.count(Tournament.id))
        .filter(Tournament.status == TournamentStatus.SCHEDULED)
        .scalar()
        or 0
    )
    tournaments_in_progress = (
        db.query(func.count(Tournament.id))
        .filter(Tournament.status == TournamentStatus.IN_PROGRESS)
        .scalar()
        or 0
    )
    tournaments_completed = (
        db.query(func.count(Tournament.id))
        .filter(Tournament.status == TournamentStatus.COMPLETED)
        .scalar()
        or 0
    )

    open_webhook_failures = (
        db.query(func.count(StripeWebhookFailure.id))
        .filter(StripeWebhookFailure.resolved_at.is_(None))
        .scalar()
        or 0
    )

    leagues_with_playoffs = (
        db.query(func.count(PlayoffConfig.id)).filter(PlayoffConfig.is_enabled.is_(True)).scalar()
        or 0
    )
    leagues_accepting_requests = (
        db.query(func.count(League.id)).filter(League.accepting_requests.is_(True)).scalar() or 0
    )
    deleted_leagues_total = db.query(func.count(DeletedLeague.id)).scalar() or 0
    avg_members_per_league = (
        round(total_approved_memberships / total_leagues, 1) if total_leagues > 0 else 0.0
    )

    return AdminStatsOut(
        total_users=total_users,
        new_users_30d=new_users_30d,
        total_leagues=total_leagues,
        paid_leagues_this_year=paid_leagues_this_year,
        total_approved_memberships=total_approved_memberships,
        leagues_by_tier=leagues_by_tier,
        total_picks=total_picks,
        picks_last_7d=picks_last_7d,
        tournaments_scheduled=tournaments_scheduled,
        tournaments_in_progress=tournaments_in_progress,
        tournaments_completed=tournaments_completed,
        leagues_with_playoffs=leagues_with_playoffs,
        leagues_accepting_requests=leagues_accepting_requests,
        avg_members_per_league=avg_members_per_league,
        deleted_leagues_total=deleted_leagues_total,
        open_webhook_failures=open_webhook_failures,
    )


@router.post("/sync")
@limiter.limit("5/hour")
def trigger_full_sync(
    request: Request,
    year: int | None = None,
    force: bool = Query(
        False,
        description="When true, delete all existing round data before re-syncing each tournament",
    ),
    admin_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """
    Trigger a full PGA Tour data sync.

    Fetches the schedule for the given year (defaults to the current calendar
    year), upserts tournaments, then syncs fields and results for every
    in-progress or completed tournament.

    force=false (default): upsert only — existing round data is updated where
    new data is available but never cleared.
    force=true: delete all TournamentEntryRound rows for each tournament first,
    then re-fetch everything from ESPN.

    This runs the same logic as the daily scheduled job, so it's safe to call
    at any time. All upserts are idempotent.
    """
    target_year = year or date.today().year
    log.info("Admin full sync triggered by user=%s year=%d", str(admin_user.id), target_year)
    try:
        result = full_sync(db, target_year, force=force)
    except Exception as exc:
        log.warning("Admin full sync failed: user=%s error=%s", str(admin_user.id), str(exc))
        raise HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc

    log.info("Admin full sync completed: user=%s year=%d", str(admin_user.id), target_year)
    return result


@router.post("/sync/{pga_tour_id}")
@limiter.limit("10/hour")
def trigger_tournament_sync(
    request: Request,
    pga_tour_id: str,
    force: bool = Query(
        False, description="When true, delete all existing round data before re-syncing"
    ),
    admin_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """
    Sync a single tournament by its ESPN event ID (our pga_tour_id).

    force=false (default): upsert — only update fields where new data is available.
    force=true: delete all TournamentEntryRound rows for this tournament first,
    then re-fetch everything from ESPN. Use this when cached data is stale or wrong.
    """
    log.info(
        "Admin single tournament sync: pga_tour_id=%s triggered by user=%s",
        pga_tour_id,
        str(admin_user.id),
    )
    tournament = db.query(Tournament).filter_by(pga_tour_id=pga_tour_id).first()
    if not tournament:
        log.warning("Admin sync: tournament not found: pga_tour_id=%s", pga_tour_id)
        raise HTTPException(
            status_code=404,
            detail=(
                f"Tournament '{pga_tour_id}' not found. "
                "Run /admin/sync first to populate the schedule."
            ),
        )

    try:
        result = sync_tournament(db, pga_tour_id, force=force)
    except Exception as exc:
        log.warning(
            "Admin single tournament sync failed: pga_tour_id=%s error=%s",
            pga_tour_id,
            str(exc),
        )
        raise HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc

    # Directly run the playoff pipeline for any unscored playoff rounds
    # linked to this tournament. Runs synchronously in the admin request
    # rather than going through SQS (the backend container doesn't have
    # SQS_QUEUE_URL set). This covers the case where the original SQS
    # event was consumed but the playoff pipeline didn't complete.
    if tournament.status == "completed":
        from app.models import PlayoffRound
        from app.services.playoff import advance_bracket, score_round
        from app.services.scraper import _winner_has_earnings

        playoff_round = (
            db.query(PlayoffRound).filter_by(tournament_id=tournament.id, status="locked").first()
        )
        if playoff_round and _winner_has_earnings(db, str(tournament.id)):
            try:
                score_round(db, playoff_round)
                log.info(
                    "Admin sync: scored playoff round %d for '%s'",
                    playoff_round.round_number,
                    tournament.name,
                )
                advance_bracket(db, playoff_round)
                log.info(
                    "Admin sync: advanced bracket past round %d for '%s'",
                    playoff_round.round_number,
                    tournament.name,
                )
            except HTTPException as exc:
                log.warning(
                    "Admin sync: playoff pipeline deferred for round %d: %s",
                    playoff_round.round_number,
                    exc.detail,
                )
            except Exception as exc:
                db.rollback()
                log.error(
                    "Admin sync: playoff pipeline failed for round %d: %s",
                    playoff_round.round_number,
                    exc,
                    exc_info=True,
                )

    log.info("Admin single tournament sync completed: pga_tour_id=%s", pga_tour_id)
    return result


# ---------------------------------------------------------------------------
# Stripe webhook failure management
# ---------------------------------------------------------------------------


class WebhookFailureOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    stripe_checkout_session_id: str | None
    error_message: str
    created_at: datetime
    resolved_at: datetime | None
    retry_count: int


@router.get("/stripe/webhook-failures", response_model=list[WebhookFailureOut])
def list_webhook_failures(
    _: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Return all unresolved Stripe webhook failures, newest first."""
    return (
        db.query(StripeWebhookFailure)
        .filter(StripeWebhookFailure.resolved_at.is_(None))
        .order_by(StripeWebhookFailure.created_at.desc())
        .all()
    )


@router.post("/stripe/webhook-failures/{failure_id}/retry")
def retry_webhook_failure(
    failure_id: uuid.UUID,
    admin_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """
    Re-process a previously failed webhook event using its stored payload.

    On success the failure row is marked resolved so it no longer appears in
    the unresolved list.  On failure a 502 is returned with the error detail
    so the admin knows what still needs fixing.
    """
    from app.routers.stripe_router import _handle_checkout_complete

    log.info(
        "Admin webhook retry: failure_id=%s triggered by user=%s",
        str(failure_id),
        str(admin_user.id),
    )
    failure = db.query(StripeWebhookFailure).filter_by(id=failure_id).first()
    if not failure:
        log.warning("Admin webhook retry: failure not found: failure_id=%s", str(failure_id))
        raise HTTPException(status_code=404, detail="Webhook failure not found")
    if failure.resolved_at is not None:
        log.warning("Admin webhook retry: already resolved: failure_id=%s", str(failure_id))
        raise HTTPException(status_code=409, detail="Already resolved")

    try:
        _handle_checkout_complete(failure.raw_payload, db)
        failure.resolved_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        log.warning(
            "Admin webhook retry failed: failure_id=%s error=%s",
            str(failure_id),
            str(exc),
        )
        raise HTTPException(status_code=502, detail=f"Retry failed: {exc}") from exc

    log.info("Admin webhook retry resolved: failure_id=%s", str(failure_id))
    return {"resolved": True}


# ---------------------------------------------------------------------------
# Bulk import — members
# ---------------------------------------------------------------------------


@router.post("/import-members")
@limiter.limit("10/hour")
def import_members(
    request: Request,
    league_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    admin_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """
    Bulk import members from a CSV file into a league.

    CSV format: name,email (header row required).
    - If the email exists in the DB, uses the existing account.
    - If the email is new, creates an account with password "password123".
    - Adds the user to the league as an approved member.
    - Skips users already in the league.
    """
    log.info(
        "Admin import members: league=%s triggered by user=%s",
        str(league_id),
        str(admin_user.id),
    )

    league = db.query(League).filter_by(id=league_id).first()
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    # Parse CSV
    try:
        content = file.file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse CSV: {exc}",
        ) from exc

    if not rows:
        raise HTTPException(status_code=422, detail="CSV is empty")

    # Validate required columns
    if "name" not in rows[0] or "email" not in rows[0]:
        raise HTTPException(
            status_code=422,
            detail="CSV must have 'name' and 'email' columns",
        )

    temp_password_hash = hash_password("password123")
    accounts_created = 0
    existing_accounts = 0
    members_added = 0
    skipped_already_in_league = 0
    errors: list[str] = []

    for i, row in enumerate(rows, start=2):  # start=2 because row 1 is the header
        name = row.get("name", "").strip()
        email = row.get("email", "").strip().lower()

        if not name or not email:
            errors.append(f"Row {i}: missing name or email")
            continue

        # Find or create user
        user = db.query(User).filter(func.lower(User.email) == email).first()
        if user:
            existing_accounts += 1
        else:
            user = User(
                email=email,
                password_hash=temp_password_hash,
                display_name=name,
            )
            db.add(user)
            db.flush()
            accounts_created += 1

        # Check if already a member
        existing_membership = (
            db.query(LeagueMember).filter_by(league_id=league.id, user_id=user.id).first()
        )
        if existing_membership:
            skipped_already_in_league += 1
            continue

        # Add as approved member
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        members_added += 1

    db.commit()

    result = {
        "accounts_created": accounts_created,
        "existing_accounts": existing_accounts,
        "members_added": members_added,
        "skipped_already_in_league": skipped_already_in_league,
        "errors": errors,
    }
    log.info("Admin import members complete: league=%s result=%s", str(league_id), result)
    return result


# ---------------------------------------------------------------------------
# Bulk import — picks
# ---------------------------------------------------------------------------


@router.post("/import-picks")
@limiter.limit("30/hour")
def import_picks(
    request: Request,
    league_id: uuid.UUID = Form(...),
    tournament_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    admin_user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """
    Bulk import picks from a CSV file for a specific tournament in a league.

    CSV format: email,golfer_name (header row required).
    - Rows with golfer_name "No Pick" are skipped (penalty applied automatically).
    - Creates or replaces picks using the admin override logic.
    - Enforces the no-repeat rule.
    - Auto-scores if the tournament is completed.
    """
    log.info(
        "Admin import picks: league=%s tournament=%s triggered by user=%s",
        str(league_id),
        str(tournament_id),
        str(admin_user.id),
    )

    league = db.query(League).filter_by(id=league_id).first()
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    tournament = db.query(Tournament).filter_by(id=tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Verify tournament is in the league's schedule
    lt = (
        db.query(LeagueTournament)
        .filter_by(league_id=league.id, tournament_id=tournament.id)
        .first()
    )
    if not lt:
        raise HTTPException(
            status_code=422,
            detail="Tournament is not in this league's schedule",
        )

    # Get active season
    season = db.query(Season).filter_by(league_id=league.id, is_active=True).first()
    if not season:
        raise HTTPException(status_code=422, detail="No active season for this league")

    # Parse CSV
    try:
        content = file.file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse CSV: {exc}",
        ) from exc

    if not rows:
        raise HTTPException(status_code=422, detail="CSV is empty")

    if "email" not in rows[0] or "golfer_name" not in rows[0]:
        raise HTTPException(
            status_code=422,
            detail="CSV must have 'email' and 'golfer_name' columns",
        )

    # ── Phase 1: Validate all rows before writing anything ──────────
    validated_rows: list[dict] = []
    validation_errors: list[str] = []

    for i, row in enumerate(rows, start=2):
        email = row.get("email", "").strip().lower()
        golfer_name = row.get("golfer_name", "").strip()

        if not email:
            validation_errors.append(f"Row {i}: missing email")
            continue

        # Skip "No Pick" rows
        if golfer_name.lower() == "no pick":
            continue

        if not golfer_name:
            validation_errors.append(f"Row {i}: missing golfer_name")
            continue

        # Validate user exists and is a league member
        user = db.query(User).filter(func.lower(User.email) == email).first()
        if not user:
            validation_errors.append(f"Row {i}: user not found: {email}")
            continue

        membership = (
            db.query(LeagueMember)
            .filter_by(
                league_id=league.id,
                user_id=user.id,
                status=LeagueMemberStatus.APPROVED.value,
            )
            .first()
        )
        if not membership:
            validation_errors.append(f"Row {i}: {email} is not a member of this league")
            continue

        # Validate golfer exists
        golfer = db.query(Golfer).filter(Golfer.name == golfer_name).first()
        if not golfer:
            validation_errors.append(f"Row {i}: golfer not found: {golfer_name}")
            continue

        # Check no-repeat rule: golfer not used by this member in another tournament
        no_repeat_conflict = (
            db.query(Pick)
            .filter(
                Pick.league_id == league.id,
                Pick.season_id == season.id,
                Pick.user_id == user.id,
                Pick.golfer_id == golfer.id,
                Pick.tournament_id != tournament.id,
            )
            .first()
        )
        if no_repeat_conflict:
            conflict_t = db.query(Tournament).filter_by(id=no_repeat_conflict.tournament_id).first()
            validation_errors.append(
                f"Row {i}: {email} already used {golfer_name} "
                f"in {conflict_t.name if conflict_t else 'another tournament'}"
            )
            continue

        validated_rows.append({"user": user, "golfer": golfer})

    if validation_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Validation failed — no data was written",
                "errors": validation_errors,
            },
        )

    # ── Phase 2: Create/replace picks ───────────────────────────────
    picks_created = 0
    picks_updated = 0
    skipped_no_pick = len(rows) - len(validated_rows)

    for vrow in validated_rows:
        user = vrow["user"]
        golfer = vrow["golfer"]

        existing = (
            db.query(Pick)
            .filter_by(
                league_id=league.id,
                season_id=season.id,
                user_id=user.id,
                tournament_id=tournament.id,
            )
            .first()
        )

        if existing:
            existing.golfer_id = golfer.id
            existing.points_earned = None  # reset for re-scoring
            picks_updated += 1
        else:
            db.add(
                Pick(
                    league_id=league.id,
                    season_id=season.id,
                    user_id=user.id,
                    tournament_id=tournament.id,
                    golfer_id=golfer.id,
                )
            )
            picks_created += 1

    db.commit()

    # ── Phase 3: Auto-score if tournament is completed ──────────────
    scored = False
    if tournament.status == TournamentStatus.COMPLETED.value:
        try:
            score_picks(db, tournament)
            scored = True
            log.info(
                "Admin import picks: auto-scored for '%s'",
                tournament.name,
            )
        except Exception as exc:
            log.error(
                "Admin import picks: scoring failed for '%s': %s",
                tournament.name,
                exc,
            )

    # Invalidate standings cache
    from app.services.scoring import invalidate_standings_cache

    invalidate_standings_cache(db, season)
    db.commit()

    result = {
        "picks_created": picks_created,
        "picks_updated": picks_updated,
        "skipped_no_pick": skipped_no_pick,
        "scored": scored,
        "errors": [],
    }
    log.info(
        "Admin import picks complete: league=%s tournament=%s result=%s",
        str(league_id),
        str(tournament_id),
        result,
    )
    return result
