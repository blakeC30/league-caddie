"""add retry_count to stripe_webhook_failures

Revision ID: q3r5s7t9u1v3
Revises: p2q4r6s8t0u2
Create Date: 2026-03-20
"""

import sqlalchemy as sa

from alembic import op

revision = "q3r5s7t9u1v3"
down_revision = "p2q4r6s8t0u2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stripe_webhook_failures",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("stripe_webhook_failures", "retry_count")
