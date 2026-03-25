"""remove tournament.multiplier column — multipliers are per-league only

Revision ID: u7v9w1x3y5z7
Revises: t6u8v0w2x4y6
Create Date: 2026-03-25

Before dropping, backfill any NULL league_tournaments.multiplier values
with the corresponding tournament.multiplier so no league loses its
configured multiplier when the fallback disappears.
"""

import sqlalchemy as sa

from alembic import op

revision = "u7v9w1x3y5z7"
down_revision = "t6u8v0w2x4y6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill: any league_tournament with NULL multiplier inherits from
    # tournament.multiplier today. Write that value explicitly before we
    # drop the column, so scoring (which now defaults NULL → 1.0) doesn't
    # silently change a league's configured 2× major to 1×.
    op.execute(
        """
        UPDATE league_tournaments lt
        SET multiplier = t.multiplier
        FROM tournaments t
        WHERE lt.tournament_id = t.id
          AND lt.multiplier IS NULL
          AND t.multiplier != 1.0
        """
    )

    op.drop_column("tournaments", "multiplier")


def downgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column(
            "multiplier",
            sa.Float(),
            nullable=False,
            server_default="1.0",
        ),
    )
