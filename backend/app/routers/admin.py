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
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_platform_admin
from app.limiter import limiter
from app.models import (
    League,
    LeagueMember,
    LeagueMemberStatus,
    LeaguePurchase,
    Pick,
    PlayoffConfig,
    StripeWebhookFailure,
    Tournament,
    TournamentStatus,
    User,
)
from app.models.deleted_league import DeletedLeague
from app.services.scraper import full_sync, sync_tournament

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
