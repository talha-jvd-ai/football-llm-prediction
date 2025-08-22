"""Initial migration - Create football schema and tables.

Revision ID: 0001_initial
Revises: 
Create Date: 2025-01-20 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the football schema and all tables."""
    # Create schema
    op.execute("CREATE SCHEMA IF NOT EXISTS football")

    # League table
    op.create_table(
        "league",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("sm_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("country", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )

    # Season table
    op.create_table(
        "season",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("sm_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("league_id", sa.BigInteger, sa.ForeignKey("football.league.id")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("year_start", sa.Integer),
        sa.Column("year_end", sa.Integer),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )

    # Venue table
    op.create_table(
        "venue",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("sm_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("name", sa.Text),
        sa.Column("city", sa.Text),
        sa.Column("capacity", sa.Integer),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )

    # Team table
    op.create_table(
        "team",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("sm_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("league_id", sa.BigInteger, sa.ForeignKey("football.league.id")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("short_code", sa.Text),
        sa.Column("venue_id", sa.BigInteger, sa.ForeignKey("football.venue.id")),
        sa.Column("country", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )

    # Coach table
    op.create_table(
        "coach",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("sm_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("football.team.id")),
        sa.Column("full_name", sa.Text, nullable=False),
        sa.Column("nationality", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )

    # Player table
    op.create_table(
        "player",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("sm_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("football.team.id")),
        sa.Column("full_name", sa.Text, nullable=False),
        sa.Column("position", sa.Text),
        sa.Column("nationality", sa.Text),
        sa.Column("date_of_birth", sa.Date),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )

    # Fixture table
    op.create_table(
        "fixture",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("sm_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("league_id", sa.BigInteger, sa.ForeignKey("football.league.id")),
        sa.Column("season_id", sa.BigInteger, sa.ForeignKey("football.season.id")),
        sa.Column("venue_id", sa.BigInteger, sa.ForeignKey("football.venue.id")),
        sa.Column("home_team_id", sa.BigInteger, sa.ForeignKey("football.team.id")),
        sa.Column("away_team_id", sa.BigInteger, sa.ForeignKey("football.team.id")),
        sa.Column("referee_name", sa.Text),
        sa.Column("kickoff_ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("round", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )
    
    # Create indexes for fixture table
    op.create_index("ix_fixture_kickoff", "fixture", ["kickoff_ts"], schema="football")
    op.create_index("ix_fixture_league_season", "fixture", ["league_id", "season_id"], schema="football")

    # Fixture Event table
    op.create_table(
        "fixture_event",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fixture_id", sa.BigInteger, sa.ForeignKey("football.fixture.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("football.team.id")),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("football.player.id")),
        sa.Column("related_player_id", sa.BigInteger, sa.ForeignKey("football.player.id")),
        sa.Column("minute", sa.Integer),
        sa.Column("type_code", sa.Text, nullable=False),
        sa.Column("payload", sa.JSON),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )
    
    # Create index for fixture events
    op.create_index("ix_fixture_event_fixture_minute", "fixture_event", ["fixture_id", "minute"], schema="football")

    # Fixture Team Statistics table
    op.create_table(
        "fixture_team_stat",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fixture_id", sa.BigInteger, sa.ForeignKey("football.fixture.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.BigInteger, sa.ForeignKey("football.team.id"), nullable=False),
        sa.Column("stat_code", sa.Text, nullable=False),
        sa.Column("value", sa.Numeric),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )
    
    # Create unique constraint for fixture team stats
    op.create_unique_constraint("uq_fixture_team_stat", "fixture_team_stat", ["fixture_id", "team_id", "stat_code"], schema="football")

    # Player Match Statistics table
    op.create_table(
        "player_match_stat",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fixture_id", sa.BigInteger, sa.ForeignKey("football.fixture.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.BigInteger, sa.ForeignKey("football.player.id"), nullable=False),
        sa.Column("stat_code", sa.Text, nullable=False),
        sa.Column("value", sa.Numeric),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )
    
    # Create unique constraint for player match stats
    op.create_unique_constraint("uq_player_match_stat", "player_match_stat", ["fixture_id", "player_id", "stat_code"], schema="football")

    # Source Raw table (for audit trail and raw payloads)
    op.create_table(
        "source_raw",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("sm_id", sa.BigInteger),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("checksum", sa.Text, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        schema="football",
    )

    # ETL Cursor table (for tracking incremental processing)
    op.create_table(
        "etl_cursor",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("resource", sa.Text, nullable=False, unique=True),
        sa.Column("cursor_value", sa.Text),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        schema="football",
    )


def downgrade() -> None:
    """Drop all tables and schema."""
    # Drop tables in reverse order to respect foreign key constraints
    tables_to_drop = [
        "etl_cursor",
        "source_raw", 
        "player_match_stat",
        "fixture_team_stat",
        "fixture_event",
        "fixture",
        "player",
        "coach", 
        "team",
        "venue",
        "season",
        "league"
    ]
    
    for table in tables_to_drop:
        op.drop_table(table, schema="football")
    
    # Drop schema
    op.execute("DROP SCHEMA IF EXISTS football CASCADE")