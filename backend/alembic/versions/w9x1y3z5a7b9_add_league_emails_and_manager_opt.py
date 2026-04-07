"""add league_emails table and manager_emails_enabled to users

Revision ID: w9x1y3z5a7b9
Revises: v8w0x2y4z6a8
Create Date: 2026-04-07
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "w9x1y3z5a7b9"
down_revision = "v8w0x2y4z6a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add opt-out toggle for manager emails (default True = opted in).
    op.add_column(
        "users",
        sa.Column(
            "manager_emails_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )

    # Audit table for manager-sent league emails.
    op.create_table(
        "league_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "league_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leagues.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "sender_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_league_emails_league_id",
        "league_emails",
        ["league_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_league_emails_league_id", table_name="league_emails")
    op.drop_table("league_emails")
    op.drop_column("users", "manager_emails_enabled")
