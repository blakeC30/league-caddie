"""add accepting_requests to leagues

Revision ID: m9n1o3p5q7r9
Revises: l8m0n2o4p6q8
Create Date: 2026-03-16

Adds leagues.accepting_requests (BOOLEAN NOT NULL DEFAULT TRUE).

When True (default), users with the invite link can submit join requests.
When False, the join endpoint returns 403 — existing pending requests are
unaffected, but no new requests can be submitted until the manager flips it
back on via PATCH /leagues/{league_id}.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m9n1o3p5q7r9"
down_revision: str | Sequence[str] | None = "l8m0n2o4p6q8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "leagues",
        sa.Column(
            "accepting_requests",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("leagues", "accepting_requests")
