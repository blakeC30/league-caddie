"""
Schemas and constants for Stripe payment integration.

PRICING_TIERS is the single source of truth for tier names, member limits,
and prices. Import it in both the router and the webhook handler.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Pricing constants
# ---------------------------------------------------------------------------

PRICING_TIERS: dict[str, dict] = {
    "starter": {"member_limit": 20, "amount_cents": 5000},
    "standard": {"member_limit": 50, "amount_cents": 9000},
    "pro": {"member_limit": 150, "amount_cents": 15000},
    "elite": {"member_limit": 500, "amount_cents": 25000},
}

# Ordered from cheapest to most expensive — used for upgrade validation.
TIER_ORDER: list[str] = ["starter", "standard", "pro", "elite"]


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class PricingTierOut(BaseModel):
    tier: str
    member_limit: int
    amount_cents: int


class CheckoutSessionCreate(BaseModel):
    league_id: uuid.UUID
    tier: str
    upgrade: bool = False


class CheckoutSessionOut(BaseModel):
    url: str


class NewLeagueCheckoutCreate(BaseModel):
    name: str
    no_pick_penalty: int = 0
    tier: str


class LeaguePurchaseOut(BaseModel):
    league_id: uuid.UUID
    season_year: int
    tier: str | None
    member_limit: int | None
    amount_cents: int | None
    paid_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
