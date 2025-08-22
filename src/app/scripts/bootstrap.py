"""Bootstrap script to initialize leagues, seasons, and metadata."""

from __future__ import annotations

import os
import sys
from typing import List
from sqlalchemy import text
import typer

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.config import settings
from app.logging import configure_logging, get_logger
from app.ingest.tasks import sync_metadata

# Configure logging
configure_logging()
logger = get_logger("bootstrap")

app = typer.Typer(
    help="Bootstrap the football ingestion pipeline with initial metadata.",
    no_args_is_help=True,
)


@app.command()
def main(
    leagues: List[str] = typer.Option(
        None,
        "--leagues",
        "-l",
        help="League names to bootstrap (comma-separated)",
    ),
    async_execution: bool = typer.Option(
        False,
        "--async",
        "-a",
        help="Run tasks asynchronously via Celery (requires running worker)",
    ),
) -> None:
    """
    Bootstrap the football ingestion pipeline with initial metadata.
    
    This script will:
    1. Discover and create league records
    2. Find current seasons for each league
    3. Sync teams, venues, coaches, and players
    4. Set up initial ETL cursors
    
    Examples:
        python -m app.scripts.bootstrap
        python -m app.scripts.bootstrap --leagues "Premier League,La Liga,Ligue 1"
        python -m app.scripts.bootstrap --async
    """
    # Use provided leagues or default from settings
    if leagues:
        league_list = [league.strip() for league in ",".join(leagues).split(",")]
        # Update settings for this run
        import json
        os.environ["LEAGUE_NAMES"] = json.dumps(league_list)
        # Reload settings to pick up the change
        from importlib import reload
        from app import config
        reload(config)
    else:
        league_list = settings.LEAGUE_NAMES
    
    logger.info("=" * 60)
    logger.info("FOOTBALL INGESTION BOOTSTRAP")
    logger.info("=" * 60)
    logger.info(f"Leagues to process: {', '.join(league_list)}")
    logger.info(f"Async execution: {async_execution}")
    logger.info("=" * 60)
    
    try:
        if async_execution:
            logger.info("Submitting metadata sync task to Celery...")
            result = sync_metadata.delay()
            logger.info(f"Task submitted with ID: {result.id}")
            logger.info("Monitor task progress using: celery -A app.worker.app events")
        else:
            logger.info("Running metadata sync synchronously...")
            result = sync_metadata()
            logger.info("Bootstrap completed successfully!")
            logger.info(f"Results: {result}")
            
            # Print summary
            typer.echo("\n" + "=" * 60)
            typer.echo(typer.style("BOOTSTRAP COMPLETE", fg=typer.colors.GREEN, bold=True))
            typer.echo("=" * 60)
            typer.echo(f"✓ Teams synced: {result.get('teams', 0)}")
            typer.echo(f"✓ Venues synced: {result.get('venues', 0)}")
            typer.echo(f"✓ Coaches synced: {result.get('coaches', 0)}")
            typer.echo(f"✓ Players synced: {result.get('players', 0)}")
            typer.echo("\nNext steps:")
            typer.echo("1. Run backfill script to load recent fixtures")
            typer.echo("2. Start Celery workers for ongoing sync")
            typer.echo("=" * 60)
            
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        typer.echo(
            typer.style(f"❌ Bootstrap failed: {e}", fg=typer.colors.RED),
            err=True
        )
        raise typer.Exit(1)


@app.command()
def test_connection() -> None:
    """Test connections to database and SportMonks API."""
    logger.info("Testing connections...")
    
    # Test database connection
    try:
        from app.db.session import create_session
        with create_session() as session:
            result = session.execute(text("SELECT 1")).scalar()
            if result == 1:
                typer.echo("✓ Database connection: OK", color=typer.colors.GREEN)
            else:
                typer.echo("❌ Database connection: FAILED", color=typer.colors.RED)
    except Exception as e:
        typer.echo(f"❌ Database connection: FAILED - {e}", color=typer.colors.RED)
    
    # Test SportMonks API connection
    try:
        from app.clients.sportmonks import SportMonksClient
        with SportMonksClient() as client:
            leagues = client.leagues_all(per_page=1)
            if leagues:
                typer.echo("✓ SportMonks API connection: OK", color=typer.colors.GREEN)
            else:
                typer.echo("❌ SportMonks API connection: No data returned", color=typer.colors.RED)
    except Exception as e:
        typer.echo(f"❌ SportMonks API connection: FAILED - {e}", color=typer.colors.RED)
    
    # Test Redis connection
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        typer.echo("✓ Redis connection: OK", color=typer.colors.GREEN)
    except Exception as e:
        typer.echo(f"❌ Redis connection: FAILED - {e}", color=typer.colors.RED)


if __name__ == "__main__":
    app()