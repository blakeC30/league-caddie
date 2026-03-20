"""
Stripe payment router.

Endpoints:
  GET  /stripe/pricing                          Public — list all pricing tiers
  POST /stripe/create-checkout-session          Manager — start a Stripe Checkout session for
                                                existing league
  POST /stripe/create-league-checkout           Authenticated — create new league via Stripe
                                                Checkout
  POST /stripe/webhook                          Stripe webhook (raw body, no auth)
  GET  /leagues/{league_id}/purchase            Member — current season purchase status
  GET  /leagues/{league_id}/purchase/events     Manager — payment history for current season

File is named stripe_router.py (not stripe.py) to avoid shadowing the stripe
Python package that this module imports.
"""

import hashlib
import logging
import struct
import uuid
from datetime import UTC, datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_league_manager, require_league_member
from app.limiter import limiter
from app.models import (
    League,
    LeagueMember,
    LeaguePurchase,
    LeaguePurchaseEvent,
    Season,
    StripeCustomer,
    StripeWebhookFailure,
    User,
)
from app.schemas.stripe_schemas import (
    PRICING_TIERS,
    TIER_ORDER,
    CheckoutSessionCreate,
    CheckoutSessionOut,
    LeaguePurchaseEventOut,
    LeaguePurchaseOut,
    NewLeagueCheckoutCreate,
    PricingTierOut,
)

log = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(tags=["stripe"])


def _get_or_create_stripe_customer(user: "User", db: Session) -> StripeCustomer:
    """
    Return the StripeCustomer row for *user*, creating one if needed.

    If a DB row exists but the corresponding Stripe customer has been deleted
    (e.g. after a test-mode reset), a fresh Stripe customer is created and the
    existing DB row is updated in-place so the rest of the codebase always sees
    a valid stripe_customer_id.
    """
    stripe_customer = db.query(StripeCustomer).filter_by(user_id=user.id).first()

    if stripe_customer:
        # Verify the customer still exists in Stripe.
        try:
            sc = stripe.Customer.retrieve(stripe_customer.stripe_customer_id)
            if sc.get("deleted"):
                raise stripe.error.InvalidRequestError(
                    "Customer was deleted", param="id", code="resource_missing"
                )
        except stripe.error.InvalidRequestError:
            # Customer no longer exists in Stripe — create a replacement and
            # update the DB row so future lookups use the new ID.
            log.warning(
                "Stripe customer %s for user %s not found or deleted — recreating",
                stripe_customer.stripe_customer_id,
                user.id,
            )
            sc = stripe.Customer.create(
                email=user.email,
                name=user.display_name,
                metadata={"user_id": str(user.id)},
            )
            stripe_customer.stripe_customer_id = sc.id
            db.commit()
        return stripe_customer

    # No row at all — create both the Stripe customer and the DB record.
    sc = stripe.Customer.create(
        email=user.email,
        name=user.display_name,
        metadata={"user_id": str(user.id)},
    )
    stripe_customer = StripeCustomer(
        id=uuid.uuid4(),
        user_id=user.id,
        stripe_customer_id=sc.id,
    )
    db.add(stripe_customer)
    db.commit()
    db.refresh(stripe_customer)
    return stripe_customer


# ---------------------------------------------------------------------------
# GET /stripe/pricing
# ---------------------------------------------------------------------------


@router.get("/stripe/pricing", response_model=list[PricingTierOut])
def get_pricing():
    """Return all available pricing tiers. Public endpoint — no auth required."""
    return [PricingTierOut(tier=tier, **info) for tier, info in PRICING_TIERS.items()]


# ---------------------------------------------------------------------------
# POST /stripe/create-checkout-session
# ---------------------------------------------------------------------------


@router.post("/stripe/create-checkout-session", response_model=CheckoutSessionOut)
@limiter.limit("10/minute")
def create_checkout_session(
    request: Request,
    body: CheckoutSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a Stripe Checkout session for the given league and tier.

    The caller must be a league manager. Validates the tier and, if this is
    an upgrade, ensures the new tier is higher than the current one.

    Returns the Checkout URL to redirect the user to.
    """
    # Validate tier
    if body.tier not in PRICING_TIERS:
        raise HTTPException(status_code=422, detail=f"Invalid tier: {body.tier!r}")

    # Verify caller is a manager of the requested league
    league = db.query(League).filter_by(id=body.league_id).first()
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    membership = (
        db.query(LeagueMember)
        .filter_by(league_id=league.id, user_id=current_user.id, status="approved")
        .first()
    )
    if not membership or membership.role != "manager":
        raise HTTPException(status_code=403, detail="League manager access required")

    # Upgrade validation: new tier must be strictly higher than current
    current_year = datetime.now(UTC).year
    current_purchase = None
    already_paid_cents = 0
    if body.upgrade:
        current_purchase = (
            db.query(LeaguePurchase)
            .filter(
                LeaguePurchase.league_id == league.id,
                LeaguePurchase.season_year == current_year,
                LeaguePurchase.paid_at.isnot(None),
            )
            .first()
        )
        if not current_purchase or not current_purchase.tier:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No active purchase found for this league. "
                    "Use the standard checkout to buy a season pass."
                ),
            )
        cur_tier = current_purchase.tier
        current_idx = TIER_ORDER.index(cur_tier) if cur_tier in TIER_ORDER else -1
        new_idx = TIER_ORDER.index(body.tier)
        if new_idx <= current_idx:
            raise HTTPException(
                status_code=422,
                detail="Upgrade tier must be higher than the current tier.",
            )
        # Derive the credit from the tier's list price, not from what was
        # stored in amount_cents.  This keeps proration consistent even when
        # the original purchase used a coupon (coupons are one-time discounts
        # and should not compound into subsequent upgrade credits).
        already_paid_cents = PRICING_TIERS[cur_tier]["amount_cents"]

    stripe_customer = _get_or_create_stripe_customer(current_user, db)

    tier_info = PRICING_TIERS[body.tier]
    charge_cents = tier_info["amount_cents"] - already_paid_cents

    if body.upgrade:
        product_name = f"League Caddie {body.tier.capitalize()} — {current_year} Season (Upgrade)"
        product_desc = (
            f"Upgrade to {tier_info['member_limit']} members"
            f" — {already_paid_cents // 100} USD already paid"
        )
    else:
        product_name = f"League Caddie {body.tier.capitalize()} — {current_year} Season"
        product_desc = f"Up to {tier_info['member_limit']} members"

    session = stripe.checkout.Session.create(
        customer=stripe_customer.stripe_customer_id,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": charge_cents,
                    "product_data": {
                        "name": product_name,
                        "description": product_desc,
                    },
                },
                "quantity": 1,
            }
        ],
        metadata={
            "league_id": str(league.id),
            "tier": body.tier,
            "user_id": str(current_user.id),
            "season_year": str(current_year),
            "is_upgrade": str(body.upgrade).lower(),
        },
        success_url=(
            f"{settings.FRONTEND_URL}/billing/success"
            f"?session_id={{CHECKOUT_SESSION_ID}}&league_id={league.id}"
        ),
        cancel_url=f"{settings.FRONTEND_URL}/billing/canceled?league_id={league.id}",
        automatic_tax={"enabled": True},
        customer_update={"address": "auto"},
    )

    return CheckoutSessionOut(url=session.url)


# ---------------------------------------------------------------------------
# POST /stripe/create-league-checkout
# ---------------------------------------------------------------------------


@router.post("/stripe/create-league-checkout", response_model=CheckoutSessionOut)
@limiter.limit("10/minute")
def create_league_checkout(
    request: Request,
    body: NewLeagueCheckoutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a Stripe Checkout session that creates a brand-new league upon
    successful payment.

    No league row is created until the webhook fires — the league ID is
    pre-generated and passed through Stripe metadata so the success URL can
    link to the (not-yet-existing) league.
    """
    if body.tier not in PRICING_TIERS:
        raise HTTPException(status_code=422, detail=f"Invalid tier: {body.tier!r}")

    pending_league_id = uuid.uuid4()
    current_year = datetime.now(UTC).year
    tier_info = PRICING_TIERS[body.tier]

    stripe_customer = _get_or_create_stripe_customer(current_user, db)

    session = stripe.checkout.Session.create(
        customer=stripe_customer.stripe_customer_id,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": tier_info["amount_cents"],
                    "product_data": {
                        "name": (f"League Caddie {body.tier.capitalize()} — {current_year} Season"),
                        "description": f"Up to {tier_info['member_limit']} members",
                    },
                },
                "quantity": 1,
            }
        ],
        metadata={
            "action": "create_league",
            "pending_league_id": str(pending_league_id),
            "league_name": body.name,
            "no_pick_penalty": str(body.no_pick_penalty),
            "auto_accept_requests": str(body.auto_accept_requests).lower(),
            "user_id": str(current_user.id),
            "tier": body.tier,
            "season_year": str(current_year),
        },
        success_url=(
            f"{settings.FRONTEND_URL}/billing/success"
            f"?session_id={{CHECKOUT_SESSION_ID}}&league_id={pending_league_id}"
        ),
        cancel_url=f"{settings.FRONTEND_URL}/billing/canceled",
        automatic_tax={"enabled": True},
        customer_update={"address": "auto"},
    )

    return CheckoutSessionOut(url=session.url)


# ---------------------------------------------------------------------------
# POST /stripe/webhook
# ---------------------------------------------------------------------------


@router.post("/stripe/webhook", status_code=200)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive Stripe webhook events. Stripe sends a signed POST with a raw body;
    we must read the raw bytes (not the parsed body) to verify the signature.

    Only handles checkout.session.completed — all other event types return 200
    immediately so Stripe doesn't retry them.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        log.warning(
            "Stripe webhook received with no stripe-signature header — likely not from Stripe"
        )
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        log.warning("Stripe webhook signature verification failed (header present but invalid)")
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as exc:
        log.error("Stripe webhook parsing error: %s", exc)
        raise HTTPException(status_code=400, detail="Webhook parse error")

    if event["type"] != "checkout.session.completed":
        return {"received": True}

    session = event["data"]["object"]
    try:
        _handle_checkout_complete(session, db)
    except Exception as exc:
        # Roll back whatever partial work _handle_checkout_complete did.
        db.rollback()
        checkout_session_id = session.get("id")
        log.error(
            "Stripe webhook processing failed for session %s: %s",
            checkout_session_id,
            exc,
            exc_info=True,
        )
        # Record the failure so admins can inspect and retry it.
        try:
            db.add(
                StripeWebhookFailure(
                    stripe_checkout_session_id=checkout_session_id,
                    raw_payload=dict(session),
                    error_message=str(exc),
                )
            )
            db.commit()
        except Exception as record_exc:
            log.error("Failed to record webhook failure: %s", record_exc)
        # Return 500 so Stripe retries the webhook automatically.
        raise HTTPException(status_code=500, detail="Webhook processing failed")
    return {"received": True}


def _handle_checkout_complete(session: dict, db: Session) -> None:
    """
    Handle a completed Stripe Checkout session.

    Two flows are supported, distinguished by `metadata.action`:

    * ``create_league`` — creates a new League, Season, LeagueMember, and
      LeaguePurchase atomically.  Used by POST /stripe/create-league-checkout.

    * (default) — upserts the LeaguePurchase for an existing league.
      Used by POST /stripe/create-checkout-session (upgrade / renew).
    """
    metadata = session.get("metadata", {})
    stripe_customer_id = session.get("customer")
    payment_intent_id = session.get("payment_intent")
    checkout_session_id = session.get("id")

    tier = metadata.get("tier")
    season_year_str = metadata.get("season_year")

    if not all([tier, season_year_str]):
        raise ValueError(f"Stripe webhook missing required metadata: {metadata}")

    try:
        season_year = int(season_year_str)
    except (ValueError, TypeError):
        raise ValueError(f"Stripe webhook invalid season_year: {season_year_str!r}")

    if tier not in PRICING_TIERS:
        raise ValueError(f"Stripe webhook unknown tier: {tier!r}")

    # Idempotency guard — Stripe retries webhooks on timeout, so the same
    # checkout.session.completed event can arrive multiple times concurrently.
    #
    # We use a PostgreSQL transaction-level advisory lock keyed on the session
    # ID to serialize concurrent deliveries before checking whether the event
    # was already processed.  Without the lock, two deliveries could both pass
    # the "already processed?" check simultaneously and then race to create the
    # same League / LeaguePurchaseEvent rows.
    #
    # pg_advisory_xact_lock blocks until it can acquire the lock and releases it
    # automatically when this transaction commits or rolls back.
    if checkout_session_id:
        lock_key = struct.unpack(">q", hashlib.sha256(checkout_session_id.encode()).digest()[:8])[0]
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

        already_processed = (
            db.query(LeaguePurchaseEvent)
            .filter_by(stripe_checkout_session_id=checkout_session_id)
            .first()
        )
        if already_processed:
            log.info(
                "Stripe webhook already processed for session %s — skipping", checkout_session_id
            )
            return

    tier_info = PRICING_TIERS[tier]
    # amount_total is what Stripe actually charged (may be prorated for upgrades).
    # full_tier_amount_cents is always derived from PRICING_TIERS — never from
    # metadata — so it cannot be tampered with via a crafted webhook payload.
    # Use `is None` rather than truthiness so that a legitimate $0 charge
    # (e.g. 100% coupon applied) is recorded as 0, not silently replaced with
    # the full tier price.
    _amount_total = session.get("amount_total")
    if _amount_total is None:
        log.warning(
            "Stripe webhook: amount_total missing from session %s "
            "— falling back to tier list price %d cents",
            checkout_session_id,
            tier_info["amount_cents"],
        )
    amount_charged_cents = _amount_total if _amount_total is not None else tier_info["amount_cents"]
    paid_at = datetime.now(UTC)

    # ── Branch: new league creation ──────────────────────────────────────────
    if metadata.get("action") == "create_league":
        pending_league_id_str = metadata.get("pending_league_id")
        league_name = metadata.get("league_name")
        user_id_str = metadata.get("user_id")
        no_pick_penalty_str = metadata.get("no_pick_penalty", "0")
        auto_accept_str = metadata.get("auto_accept_requests", "false")

        if not all([pending_league_id_str, league_name, user_id_str]):
            raise ValueError(f"Stripe webhook create_league missing metadata: {metadata}")

        # Clamp the name to the League.name column length (100).  The schema
        # validator on NewLeagueCheckoutCreate already enforces this at session
        # creation time; this is defense-in-depth in case the raw_payload of a
        # stored failure is retried with a manually edited or unexpected value.
        league_name = league_name[:100].strip()
        if not league_name:
            raise ValueError(
                "Stripe webhook create_league: empty league_name after sanitization "
                f"(session={checkout_session_id})"
            )

        try:
            league_id = uuid.UUID(pending_league_id_str)
            user_id = uuid.UUID(user_id_str)
            no_pick_penalty = int(no_pick_penalty_str)
        except (ValueError, TypeError):
            raise ValueError(f"Stripe webhook create_league invalid metadata: {metadata}")

        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            raise ValueError(
                f"Stripe webhook create_league: user {user_id} not found "
                f"(session={checkout_session_id})"
            )

        # Guard against a reused pending_league_id (e.g. a manually crafted
        # Stripe session replaying an old UUID).  The idempotency check above
        # catches exact session replays; this catches the edge case where a
        # different session carries the same pending_league_id.
        existing_league = db.query(League).filter_by(id=league_id).first()
        if existing_league:
            log.error(
                "Stripe webhook create_league: league %s already exists (session=%s) — skipping",
                league_id,
                checkout_session_id,
            )
            return

        db.add(
            League(
                id=league_id,
                name=league_name,
                created_by=user_id,
                no_pick_penalty=no_pick_penalty,
                auto_accept_requests=auto_accept_str == "true",
            )
        )
        db.add(Season(league_id=league_id, year=season_year, is_active=True))
        db.add(
            LeagueMember(
                league_id=league_id,
                user_id=user_id,
                role="manager",
                status="approved",
            )
        )
        db.add(
            LeaguePurchase(
                id=uuid.uuid4(),
                league_id=league_id,
                season_year=season_year,
                tier=tier,
                member_limit=tier_info["member_limit"],
                stripe_customer_id=stripe_customer_id,
                stripe_payment_intent_id=payment_intent_id,
                stripe_checkout_session_id=checkout_session_id,
                amount_cents=amount_charged_cents,
                paid_at=paid_at,
            )
        )
        db.add(
            LeaguePurchaseEvent(
                id=uuid.uuid4(),
                league_id=league_id,
                season_year=season_year,
                tier=tier,
                member_limit=tier_info["member_limit"],
                stripe_customer_id=stripe_customer_id,
                stripe_payment_intent_id=payment_intent_id,
                stripe_checkout_session_id=checkout_session_id,
                amount_cents=amount_charged_cents,
                event_type="purchase",
                paid_at=paid_at,
            )
        )

        db.commit()
        log.info(
            "Created league %s %r for user %s (tier=%r season=%s)",
            league_id,
            league_name,
            user_id,
            tier,
            season_year,
        )
        return

    # ── Branch: upgrade / renew existing league ───────────────────────────────
    league_id_str = metadata.get("league_id")
    if not league_id_str:
        raise ValueError(f"Stripe webhook missing league_id in metadata: {metadata}")

    try:
        league_id = uuid.UUID(league_id_str)
    except (ValueError, TypeError):
        raise ValueError(f"Stripe webhook invalid league_id: {league_id_str!r}")

    league = db.query(League).filter_by(id=league_id).first()
    if not league:
        raise ValueError(
            f"Stripe webhook upgrade/renew: league {league_id} not found "
            f"(session={checkout_session_id})"
        )

    # Upsert league purchase.
    # Use with_for_update() so that two concurrent upgrade webhooks for the same
    # league are serialized at the DB level.  Without the lock, both could read
    # the same purchase row, apply their respective tier updates, and whichever
    # commits second silently overwrites the first.
    purchase = (
        db.query(LeaguePurchase)
        .filter_by(league_id=league_id, season_year=season_year)
        .with_for_update()
        .first()
    )
    if purchase:
        purchase.tier = tier
        purchase.member_limit = tier_info["member_limit"]
        purchase.stripe_customer_id = stripe_customer_id
        purchase.stripe_payment_intent_id = payment_intent_id
        purchase.stripe_checkout_session_id = checkout_session_id
        # Store what Stripe actually charged so LeaguePurchase.amount_cents is
        # always the real transaction amount (financial reconciliation).
        # Proration for future upgrades is derived from PRICING_TIERS[tier] at
        # checkout time, not from this stored value, so the proration math is
        # unaffected.
        purchase.amount_cents = amount_charged_cents
        purchase.paid_at = paid_at
    else:
        purchase = LeaguePurchase(
            id=uuid.uuid4(),
            league_id=league_id,
            season_year=season_year,
            tier=tier,
            member_limit=tier_info["member_limit"],
            stripe_customer_id=stripe_customer_id,
            stripe_payment_intent_id=payment_intent_id,
            stripe_checkout_session_id=checkout_session_id,
            amount_cents=amount_charged_cents,
            paid_at=paid_at,
        )
        db.add(purchase)

    db.add(
        LeaguePurchaseEvent(
            id=uuid.uuid4(),
            league_id=league_id,
            season_year=season_year,
            tier=tier,
            member_limit=tier_info["member_limit"],
            stripe_customer_id=stripe_customer_id,
            stripe_payment_intent_id=payment_intent_id,
            stripe_checkout_session_id=checkout_session_id,
            amount_cents=amount_charged_cents,
            event_type="purchase" if metadata.get("is_upgrade") != "true" else "upgrade",
            paid_at=paid_at,
        )
    )

    db.commit()
    log.info(
        "League %s purchased %r for season %s (payment_intent=%s)",
        league_id,
        tier,
        season_year,
        payment_intent_id,
    )


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/purchase
# ---------------------------------------------------------------------------


@router.get("/leagues/{league_id}/purchase", response_model=LeaguePurchaseOut | None)
def get_league_purchase(
    league_and_member: tuple[League, LeagueMember] = Depends(require_league_member),
    db: Session = Depends(get_db),
) -> LeaguePurchaseOut | None:
    """
    Return the active season purchase for the league, or null if none exists.

    NOT gated by require_active_purchase — members need to see this to know
    they should purchase a pass.
    """
    league, _ = league_and_member
    current_year = datetime.now(UTC).year
    purchase = (
        db.query(LeaguePurchase).filter_by(league_id=league.id, season_year=current_year).first()
    )
    if not purchase:
        return None

    # Resolve the email of the user who paid via StripeCustomer join.
    paid_by_email = None
    if purchase.stripe_customer_id:
        sc = (
            db.query(StripeCustomer)
            .filter_by(stripe_customer_id=purchase.stripe_customer_id)
            .first()
        )
        if sc:
            from app.models.user import User

            payer = db.query(User).filter_by(id=sc.user_id).first()
            if payer:
                paid_by_email = payer.email

    result = LeaguePurchaseOut.model_validate(purchase)
    result.paid_by_email = paid_by_email
    return result


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/purchase/events
# ---------------------------------------------------------------------------


@router.get(
    "/leagues/{league_id}/purchase/events",
    response_model=list[LeaguePurchaseEventOut],
)
def get_league_purchase_events(
    league_and_member: tuple[League, LeagueMember] = Depends(require_league_manager),
    db: Session = Depends(get_db),
) -> list[LeaguePurchaseEvent]:
    """
    Return all payment events for the current season, newest first.
    Manager-only — contains actual charge amounts.
    """
    league, _ = league_and_member
    current_year = datetime.now(UTC).year
    return (
        db.query(LeaguePurchaseEvent)
        .filter_by(league_id=league.id, season_year=current_year)
        .order_by(LeaguePurchaseEvent.paid_at.asc())
        .all()
    )
