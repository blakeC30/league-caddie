"""widen_stripe_id_columns_to_255

Revision ID: 4f5a8d68595c
Revises: n0o2p4q6r8s0
Create Date: 2026-03-17 15:57:53.760074

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f5a8d68595c"
down_revision: str | Sequence[str] | None = "n0o2p4q6r8s0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen all Stripe ID columns from VARCHAR(64) to VARCHAR(255).

    Stripe checkout session IDs (cs_test_...) can exceed 64 characters,
    causing StringDataRightTruncation errors when writing to the DB.
    """
    for table in ("league_purchases", "league_purchase_events"):
        for col in ("stripe_customer_id", "stripe_payment_intent_id", "stripe_checkout_session_id"):
            op.alter_column(
                table,
                col,
                existing_type=sa.VARCHAR(length=64),
                type_=sa.String(length=255),
                existing_nullable=True,
            )
    op.alter_column(
        "stripe_customers",
        "stripe_customer_id",
        existing_type=sa.VARCHAR(length=64),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Narrow Stripe ID columns back to VARCHAR(64)."""
    op.alter_column(
        "stripe_customers",
        "stripe_customer_id",
        existing_type=sa.String(length=255),
        type_=sa.VARCHAR(length=64),
        existing_nullable=False,
    )
    for table in ("league_purchase_events", "league_purchases"):
        for col in ("stripe_checkout_session_id", "stripe_payment_intent_id", "stripe_customer_id"):
            op.alter_column(
                table,
                col,
                existing_type=sa.String(length=255),
                type_=sa.VARCHAR(length=64),
                existing_nullable=True,
            )
