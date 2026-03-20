"""
Schemas and constants for Stripe payment integration.

PRICING_TIERS is the single source of truth for tier names, member limits,
and prices. Import it in both the router and the webhook handler.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Pricing constants
# ---------------------------------------------------------------------------

PRICING_TIERS: dict[str, dict] = {
    "starter": {"member_limit": 20, "amount_cents": 4999},
    "standard": {"member_limit": 50, "amount_cents": 8999},
    "pro": {"member_limit": 150, "amount_cents": 14999},
    "elite": {"member_limit": 500, "amount_cents": 24999},
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
    name: str = Field(min_length=1, max_length=100)
    no_pick_penalty: int = Field(default=0, ge=0)
    tier: str
    auto_accept_requests: bool = False

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class LeaguePurchaseOut(BaseModel):
    league_id: uuid.UUID
    season_year: int
    tier: str | None
    member_limit: int | None
    amount_cents: int | None
    paid_at: datetime | None
    paid_by_email: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LeaguePurchaseEventOut(BaseModel):
    id: uuid.UUID
    tier: str
    amount_cents: int
    event_type: str  # "purchase" | "upgrade"
    paid_at: datetime

    model_config = ConfigDict(from_attributes=True)
