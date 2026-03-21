"""add standings_cache to seasons

Revision ID: r4s6t8u0v2w4
Revises: q3r5s7t9u1v3
Create Date: 2026-03-21
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

from alembic import op

revision = "r4s6t8u0v2w4"
down_revision = "q3r5s7t9u1v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("seasons", sa.Column("standings_cache", JSON, nullable=True))
    op.add_column(
        "seasons",
        sa.Column("standings_cached_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("seasons", "standings_cached_at")
    op.drop_column("seasons", "standings_cache")
