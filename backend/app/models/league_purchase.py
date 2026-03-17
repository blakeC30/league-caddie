"""
Stripe payment models.

Three tables support per-league seasonal payment gating:
  - StripeCustomer    — maps a platform User to their Stripe Customer ID (1:1)
  - LeaguePurchase    — one active purchase row per (league, season_year)
  - LeaguePurchaseEvent — append-only audit log; one row per Stripe checkout completed
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.league import League
    from app.models.user import User


class StripeCustomer(Base):
    __tablename__ = "stripe_customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="stripe_customer")


class LeaguePurchase(Base):
    """Active season pass for a league. At most one row per (league_id, season_year)."""

    __tablename__ = "league_purchases"
    __table_args__ = (
        UniqueConstraint("league_id", "season_year", name="uq_league_purchases_league_season"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leagues.id", ondelete="CASCADE"),
        nullable=False,
    )
    season_year: Mapped[int] = mapped_column(Integer(), nullable=False)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    member_limit: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    league: Mapped["League"] = relationship(back_populates="purchases")


class LeaguePurchaseEvent(Base):
    """Append-only audit log. One row is inserted per completed Stripe checkout."""

    __tablename__ = "league_purchase_events"
    __table_args__ = (Index("ix_league_purchase_events_league_season", "league_id", "season_year"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leagues.id", ondelete="CASCADE"),
        nullable=False,
    )
    season_year: Mapped[int] = mapped_column(Integer(), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    member_limit: Mapped[int] = mapped_column(Integer(), nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer(), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    league: Mapped["League"] = relationship(back_populates="purchase_events")
