"""remove_league_description

Revision ID: g3h5i7j9k1l2
Revises: c7e2a1f9b4d3
Create Date: 2026-03-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g3h5i7j9k1l2"
down_revision: str | Sequence[str] | None = "c7e2a1f9b4d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("leagues", "description")


def downgrade() -> None:
    op.add_column(
        "leagues",
        sa.Column("description", sa.String(length=500), nullable=True),
    )
