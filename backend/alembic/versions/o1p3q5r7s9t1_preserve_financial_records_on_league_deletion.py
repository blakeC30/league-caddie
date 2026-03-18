"""preserve financial records on league deletion

Creates a deleted_leagues audit table and updates league_purchases /
league_purchase_events so that:
  - league_id becomes nullable with ON DELETE SET NULL (not CASCADE)
  - a new deleted_league_id FK column references deleted_leagues.id

Revision ID: o1p3q5r7s9t1
Revises: n0o2p4q6r8s0
Create Date: 2026-03-18
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "o1p3q5r7s9t1"
down_revision = "5b6c7d8e9f0a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create the audit table — no FK constraints by design.
    op.create_table(
        "deleted_leagues",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. league_purchases — drop CASCADE FK, re-add as SET NULL + nullable; add deleted_league_id.
    op.drop_constraint("league_purchases_league_id_fkey", "league_purchases", type_="foreignkey")
    op.alter_column(
        "league_purchases", "league_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True
    )
    op.create_foreign_key(
        "league_purchases_league_id_fkey",
        "league_purchases",
        "leagues",
        ["league_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "league_purchases",
        sa.Column("deleted_league_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "league_purchases_deleted_league_id_fkey",
        "league_purchases",
        "deleted_leagues",
        ["deleted_league_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 3. league_purchase_events — same changes.
    op.drop_constraint(
        "league_purchase_events_league_id_fkey", "league_purchase_events", type_="foreignkey"
    )
    op.alter_column(
        "league_purchase_events",
        "league_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_foreign_key(
        "league_purchase_events_league_id_fkey",
        "league_purchase_events",
        "leagues",
        ["league_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "league_purchase_events",
        sa.Column("deleted_league_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "league_purchase_events_deleted_league_id_fkey",
        "league_purchase_events",
        "deleted_leagues",
        ["deleted_league_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    # Remove deleted_league_id FKs and columns from both tables.
    op.drop_constraint(
        "league_purchase_events_deleted_league_id_fkey",
        "league_purchase_events",
        type_="foreignkey",
    )
    op.drop_column("league_purchase_events", "deleted_league_id")
    op.drop_constraint(
        "league_purchase_events_league_id_fkey", "league_purchase_events", type_="foreignkey"
    )
    op.alter_column(
        "league_purchase_events",
        "league_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "league_purchase_events_league_id_fkey",
        "league_purchase_events",
        "leagues",
        ["league_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "league_purchases_deleted_league_id_fkey", "league_purchases", type_="foreignkey"
    )
    op.drop_column("league_purchases", "deleted_league_id")
    op.drop_constraint("league_purchases_league_id_fkey", "league_purchases", type_="foreignkey")
    op.alter_column(
        "league_purchases", "league_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False
    )
    op.create_foreign_key(
        "league_purchases_league_id_fkey",
        "league_purchases",
        "leagues",
        ["league_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_table("deleted_leagues")
