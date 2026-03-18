"""
Stripe payment models.

Four tables support per-league seasonal payment gating:
  - StripeCustomer       — maps a platform User to their Stripe Customer ID (1:1)
  - LeaguePurchase       — one active purchase row per (league, season_year)
  - LeaguePurchaseEvent  — append-only audit log; one row per Stripe checkout completed
  - StripeWebhookFailure — records webhook events that failed to process so admins
                           can inspect and retry them without losing the payload
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.deleted_league import DeletedLeague
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
    stripe_customer_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
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
    league_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leagues.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_league_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deleted_leagues.id", ondelete="RESTRICT"),
        nullable=True,
    )
    season_year: Mapped[int] = mapped_column(Integer(), nullable=False)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    member_limit: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    league: Mapped["League | None"] = relationship(back_populates="purchases")
    deleted_league: Mapped["DeletedLeague | None"] = relationship()


class LeaguePurchaseEvent(Base):
    """Append-only audit log. One row is inserted per completed Stripe checkout."""

    __tablename__ = "league_purchase_events"
    __table_args__ = (Index("ix_league_purchase_events_league_season", "league_id", "season_year"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leagues.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_league_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deleted_leagues.id", ondelete="RESTRICT"),
        nullable=True,
    )
    season_year: Mapped[int] = mapped_column(Integer(), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    member_limit: Mapped[int] = mapped_column(Integer(), nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer(), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    league: Mapped["League | None"] = relationship(back_populates="purchase_events")
    deleted_league: Mapped["DeletedLeague | None"] = relationship()


class StripeWebhookFailure(Base):
    """
    Records checkout.session.completed events that failed to process.

    The full Stripe session dict is stored in raw_payload so an admin can
    inspect what went wrong and trigger a retry without needing to contact
    Stripe support or reconstruct the event manually.

    resolved_at is set when the failure is successfully retried via the
    admin endpoint — unresolved rows (resolved_at IS NULL) represent events
    that still need attention.
    """

    __tablename__ = "stripe_webhook_failures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
