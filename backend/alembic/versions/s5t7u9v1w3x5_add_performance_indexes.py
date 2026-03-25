"""add performance indexes for picks and tournament_entries

Revision ID: s5t7u9v1w3x5
Revises: r4s6t8u0v2w4
Create Date: 2026-03-25
"""

from alembic import op

revision = "s5t7u9v1w3x5"
down_revision = "r4s6t8u0v2w4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # score_picks filters by tournament_id across all leagues.
    op.create_index("ix_picks_tournament_id", "picks", ["tournament_id"])
    # calculate_standings filters by (league_id, season_id) then groups by tournament_id.
    op.create_index(
        "ix_picks_league_season_tournament",
        "picks",
        ["league_id", "season_id", "tournament_id"],
    )
    # Leaderboard, field, all_r1_teed_off, score_picks all filter on tournament_id alone.
    op.create_index("ix_tournament_entries_tournament_id", "tournament_entries", ["tournament_id"])


def downgrade() -> None:
    op.drop_index("ix_tournament_entries_tournament_id", table_name="tournament_entries")
    op.drop_index("ix_picks_league_season_tournament", table_name="picks")
    op.drop_index("ix_picks_tournament_id", table_name="picks")
