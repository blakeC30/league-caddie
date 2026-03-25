"""add first_name and last_name to users

Revision ID: v8w0x2y4z6a8
Revises: u7v9w1x3y5z7
Create Date: 2026-03-25
"""

import sqlalchemy as sa

from alembic import op

revision = "v8w0x2y4z6a8"
down_revision = "u7v9w1x3y5z7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("first_name", sa.String(50), nullable=False, server_default="")
    )
    op.add_column("users", sa.Column("last_name", sa.String(50), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
