"""add_stripe_webhook_failures

Revision ID: 5b6c7d8e9f0a
Revises: 4f5a8d68595c
Create Date: 2026-03-17 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b6c7d8e9f0a"
down_revision: str | Sequence[str] | None = "4f5a8d68595c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create stripe_webhook_failures table.

    Stores checkout.session.completed events that failed to process so
    admins can inspect and retry them without losing the payload.
    """
    op.create_table(
        "stripe_webhook_failures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("raw_payload", JSON, nullable=False),
        sa.Column("error_message", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_stripe_webhook_failures_session_id",
        "stripe_webhook_failures",
        ["stripe_checkout_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_stripe_webhook_failures_session_id", table_name="stripe_webhook_failures")
    op.drop_table("stripe_webhook_failures")
