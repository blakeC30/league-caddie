"""add is_admin_league and has_active_purchase to leagues

Revision ID: t6u8v0w2x4y6
Revises: s5t7u9v1w3x5
Create Date: 2026-03-25
"""

import sqlalchemy as sa

from alembic import op

revision = "t6u8v0w2x4y6"
down_revision = "s5t7u9v1w3x5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leagues",
        sa.Column(
            "is_admin_league",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "leagues",
        sa.Column(
            "has_active_purchase",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # Backfill is_admin_league: leagues created by platform admins with a $0 purchase.
    op.execute(
        """
        UPDATE leagues
        SET is_admin_league = TRUE
        WHERE created_by IN (SELECT id FROM users WHERE is_platform_admin = TRUE)
          AND id IN (
            SELECT league_id FROM league_purchases
            WHERE amount_cents = 0 AND paid_at IS NOT NULL
          )
        """
    )

    # Backfill has_active_purchase: leagues with a paid purchase for the current year,
    # OR admin leagues (always active).
    op.execute(
        """
        UPDATE leagues
        SET has_active_purchase = TRUE
        WHERE is_admin_league = TRUE
           OR id IN (
             SELECT league_id FROM league_purchases
             WHERE paid_at IS NOT NULL
               AND season_year = EXTRACT(YEAR FROM NOW())::INT
           )
        """
    )


def downgrade() -> None:
    op.drop_column("leagues", "has_active_purchase")
    op.drop_column("leagues", "is_admin_league")
