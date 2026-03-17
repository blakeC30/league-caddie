"""add stripe tables

Revision ID: n0o2p4q6r8s0
Revises: m9n1o3p5q7r9
Create Date: 2026-03-17

Creates three tables supporting per-league seasonal payment gating:
  - stripe_customers  — maps platform users to their Stripe Customer IDs
  - league_purchases  — one row per (league, season_year) with tier/payment info
  - league_purchase_events — append-only audit log for each checkout completion

Data migration: all existing leagues are backfilled as Elite tier for 2026 at
no cost so they are not blocked when the feature goes live.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n0o2p4q6r8s0"
down_revision: str | Sequence[str] | None = "m9n1o3p5q7r9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create Stripe tables and backfill existing leagues as Elite."""
    op.create_table(
        "stripe_customers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("stripe_customer_id", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "league_purchases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "league_id",
            UUID(as_uuid=True),
            sa.ForeignKey("leagues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(16), nullable=True),
        sa.Column("member_limit", sa.Integer(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(64), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(64), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("league_id", "season_year", name="uq_league_purchases_league_season"),
    )

    op.create_table(
        "league_purchase_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "league_id",
            UUID(as_uuid=True),
            sa.ForeignKey("leagues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("member_limit", sa.Integer(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(64), nullable=True, unique=True),
        sa.Column("stripe_checkout_session_id", sa.String(64), unique=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_league_purchase_events_league_season",
        "league_purchase_events",
        ["league_id", "season_year"],
    )

    # Data migration: grandfather all existing leagues as Elite for 2026 at no cost.
    # This ensures no existing league is blocked when the payment gate goes live.
    op.execute(
        """
        INSERT INTO league_purchases (
            id, league_id, season_year, tier, member_limit, amount_cents, paid_at, created_at
        )
        SELECT
            gen_random_uuid(), id, 2026, 'elite', 500, 0, now(), now()
        FROM leagues
        """
    )


def downgrade() -> None:
    """Drop Stripe tables."""
    op.drop_index("ix_league_purchase_events_league_season", table_name="league_purchase_events")
    op.drop_table("league_purchase_events")
    op.drop_table("league_purchases")
    op.drop_table("stripe_customers")
