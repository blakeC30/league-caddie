"""add auto_accept_requests to leagues

Revision ID: p2q4r6s8t0u2
Revises: o1p3q5r7s9t1
Create Date: 2026-03-19
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "p2q4r6s8t0u2"
down_revision = "o1p3q5r7s9t1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leagues",
        sa.Column(
            "auto_accept_requests",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("leagues", "auto_accept_requests")
