"""Add LLM-optimized computed columns to fixture table.

Revision ID: 0002_llm_optimization
Revises: 0001_initial
Create Date: 2025-01-20 15:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_llm_optimization"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add LLM-optimized columns to fixture table for direct data access."""
    
    # Add computed columns to fixture table for easier LLM queries
    op.add_column(
        "fixture",
        sa.Column("home_goals", sa.Integer),
        schema="football"
    )
    
    op.add_column(
        "fixture", 
        sa.Column("away_goals", sa.Integer),
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("result", sa.CHAR(1)),  # 'H'/'A'/'D'
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("home_position", sa.Integer),  # League position at match time
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("away_position", sa.Integer),  # League position at match time
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("home_possession", sa.Numeric),  # Ball possession %
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("away_possession", sa.Numeric),  # Ball possession %
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("home_corners", sa.Integer),  # Corner kicks
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("away_corners", sa.Integer),  # Corner kicks
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("home_yellow_cards", sa.Integer),  # Yellow cards
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("away_yellow_cards", sa.Integer),  # Yellow cards
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("home_red_cards", sa.Integer),  # Red cards
        schema="football"
    )
    
    op.add_column(
        "fixture",
        sa.Column("away_red_cards", sa.Integer),  # Red cards
        schema="football"
    )

    # Create indexes for common LLM queries
    op.create_index(
        "ix_fixture_result", 
        "fixture", 
        ["result"], 
        schema="football"
    )
    
    op.create_index(
        "ix_fixture_goals", 
        "fixture", 
        ["home_goals", "away_goals"], 
        schema="football"
    )
    
    op.create_index(
        "ix_fixture_teams_result", 
        "fixture", 
        ["home_team_id", "away_team_id", "result"], 
        schema="football"
    )
    
    # Create partial index for finished matches (most common LLM query)
    op.execute("""
        CREATE INDEX ix_fixture_finished 
        ON football.fixture (kickoff_ts DESC) 
        WHERE status = '5'
    """)


def downgrade() -> None:
    """Remove LLM-optimized columns and indexes."""
    
    # Drop indexes
    op.drop_index("ix_fixture_finished", "fixture", schema="football")
    op.drop_index("ix_fixture_teams_result", "fixture", schema="football")
    op.drop_index("ix_fixture_goals", "fixture", schema="football")
    op.drop_index("ix_fixture_result", "fixture", schema="football")
    
    # Drop columns
    columns_to_drop = [
        "home_goals",
        "away_goals", 
        "result",
        "home_position",
        "away_position",
        "home_possession",
        "away_possession",
        "home_corners",
        "away_corners",
        "home_yellow_cards",
        "away_yellow_cards",
        "home_red_cards",
        "away_red_cards"
    ]
    
    for column in columns_to_drop:
        op.drop_column("fixture", column, schema="football")