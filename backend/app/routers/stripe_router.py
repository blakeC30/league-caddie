"""
Stripe payment router.

Endpoints:
  GET  /stripe/pricing                     Public — list all pricing tiers
  POST /stripe/create-checkout-session     Manager — start a Stripe Checkout session for existing
                                           league
  POST /stripe/create-league-checkout      Authenticated — create new league via Stripe Checkout
  POST /stripe/webhook                     Stripe webhook (raw body, no auth)
  GET  /leagues/{league_id}/purchase       Member — current season purchase status

File is named stripe_router.py (not stripe.py) to avoid shadowing the stripe
Python package that this module imports.
"""

import logging
import uuid
from datetime import UTC, datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_league_member
from app.models import (
    League,
    LeagueMember,
    LeaguePurchase,
    LeaguePurchaseEvent,
    Season,
    StripeCustomer,
    User,
)
from app.schemas.stripe_schemas import (
    PRICING_TIERS,
    TIER_ORDER,
    CheckoutSessionCreate,
    CheckoutSessionOut,
    LeaguePurchaseOut,
    NewLeagueCheckoutCreate,
    PricingTierOut,
)

log = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

router = APIRouter(tags=["stripe"])


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
def create_checkout_session(
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
    if body.upgrade:
        current_year = datetime.now(UTC).year
        current_purchase = (
            db.query(LeaguePurchase)
            .filter(
                LeaguePurchase.league_id == league.id,
                LeaguePurchase.season_year == current_year,
                LeaguePurchase.paid_at.isnot(None),
            )
            .first()
        )
        if current_purchase and current_purchase.tier:
            cur_tier = current_purchase.tier
            current_idx = TIER_ORDER.index(cur_tier) if cur_tier in TIER_ORDER else -1
            new_idx = TIER_ORDER.index(body.tier)
            if new_idx <= current_idx:
                raise HTTPException(
                    status_code=422,
                    detail="Upgrade tier must be higher than the current tier.",
                )

    # Upsert Stripe Customer
    stripe_customer = db.query(StripeCustomer).filter_by(user_id=current_user.id).first()
    if not stripe_customer:
        sc = stripe.Customer.create(
            email=current_user.email,
            name=current_user.display_name,
            metadata={"user_id": str(current_user.id)},
        )
        stripe_customer = StripeCustomer(
            id=uuid.uuid4(),
            user_id=current_user.id,
            stripe_customer_id=sc.id,
        )
        db.add(stripe_customer)
        db.commit()
        db.refresh(stripe_customer)

    tier_info = PRICING_TIERS[body.tier]
    current_year = datetime.now(UTC).year

    session = stripe.checkout.Session.create(
        customer=stripe_customer.stripe_customer_id,
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": tier_info["amount_cents"],
                    "product_data": {
                        "name": f"League Caddie {body.tier.capitalize()} — {current_year} Season",
                        "description": f"Up to {tier_info['member_limit']} members",
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
    )

    return CheckoutSessionOut(url=session.url)


# ---------------------------------------------------------------------------
# POST /stripe/create-league-checkout
# ---------------------------------------------------------------------------


@router.post("/stripe/create-league-checkout", response_model=CheckoutSessionOut)
def create_league_checkout(
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

    # Upsert Stripe Customer
    stripe_customer = db.query(StripeCustomer).filter_by(user_id=current_user.id).first()
    if not stripe_customer:
        sc = stripe.Customer.create(
            email=current_user.email,
            name=current_user.display_name,
            metadata={"user_id": str(current_user.id)},
        )
        stripe_customer = StripeCustomer(
            id=uuid.uuid4(),
            user_id=current_user.id,
            stripe_customer_id=sc.id,
        )
        db.add(stripe_customer)
        db.commit()
        db.refresh(stripe_customer)

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
            "user_id": str(current_user.id),
            "tier": body.tier,
            "season_year": str(current_year),
        },
        success_url=(
            f"{settings.FRONTEND_URL}/billing/success"
            f"?session_id={{CHECKOUT_SESSION_ID}}&league_id={pending_league_id}"
        ),
        cancel_url=f"{settings.FRONTEND_URL}/billing/canceled",
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
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        log.warning("Stripe webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as exc:
        log.error("Stripe webhook parsing error: %s", exc)
        raise HTTPException(status_code=400, detail="Webhook parse error")

    if event["type"] != "checkout.session.completed":
        return {"received": True}

    session = event["data"]["object"]
    _handle_checkout_complete(session, db)
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
        log.error("Stripe webhook missing required metadata: %s", metadata)
        return

    try:
        season_year = int(season_year_str)
    except (ValueError, TypeError):
        log.error("Stripe webhook invalid season_year: %s", season_year_str)
        return

    if tier not in PRICING_TIERS:
        log.error("Stripe webhook unknown tier: %r", tier)
        return

    tier_info = PRICING_TIERS[tier]
    amount_cents = session.get("amount_total") or tier_info["amount_cents"]
    paid_at = datetime.now(UTC)

    # ── Branch: new league creation ──────────────────────────────────────────
    if metadata.get("action") == "create_league":
        pending_league_id_str = metadata.get("pending_league_id")
        league_name = metadata.get("league_name")
        user_id_str = metadata.get("user_id")
        no_pick_penalty_str = metadata.get("no_pick_penalty", "0")

        if not all([pending_league_id_str, league_name, user_id_str]):
            log.error("Stripe webhook create_league missing metadata: %s", metadata)
            return

        try:
            league_id = uuid.UUID(pending_league_id_str)
            user_id = uuid.UUID(user_id_str)
            no_pick_penalty = int(no_pick_penalty_str)
        except (ValueError, TypeError):
            log.error("Stripe webhook create_league invalid metadata: %s", metadata)
            return

        db.add(
            League(
                id=league_id, name=league_name, created_by=user_id, no_pick_penalty=no_pick_penalty
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
                amount_cents=amount_cents,
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
                amount_cents=amount_cents,
                event_type="purchase",
                paid_at=paid_at,
            )
        )

        try:
            db.commit()
            log.info(
                "Created league %s %r for user %s (tier=%r season=%s)",
                league_id,
                league_name,
                user_id,
                tier,
                season_year,
            )
        except Exception as exc:
            db.rollback()
            log.error("Failed to create league from Stripe webhook: %s", exc)
        return

    # ── Branch: upgrade / renew existing league ───────────────────────────────
    league_id_str = metadata.get("league_id")
    if not league_id_str:
        log.error("Stripe webhook missing league_id in metadata: %s", metadata)
        return

    try:
        league_id = uuid.UUID(league_id_str)
    except (ValueError, TypeError):
        log.error("Stripe webhook invalid league_id: %s", league_id_str)
        return

    # Upsert league purchase
    purchase = (
        db.query(LeaguePurchase).filter_by(league_id=league_id, season_year=season_year).first()
    )
    if purchase:
        purchase.tier = tier
        purchase.member_limit = tier_info["member_limit"]
        purchase.stripe_customer_id = stripe_customer_id
        purchase.stripe_payment_intent_id = payment_intent_id
        purchase.stripe_checkout_session_id = checkout_session_id
        purchase.amount_cents = amount_cents
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
            amount_cents=amount_cents,
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
            amount_cents=amount_cents,
            event_type="purchase" if metadata.get("is_upgrade") != "true" else "upgrade",
            paid_at=paid_at,
        )
    )

    try:
        db.commit()
        log.info(
            "League %s purchased %r for season %s (payment_intent=%s)",
            league_id,
            tier,
            season_year,
            payment_intent_id,
        )
    except Exception as exc:
        db.rollback()
        log.error("Failed to save Stripe purchase: %s", exc)


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
    return purchase
