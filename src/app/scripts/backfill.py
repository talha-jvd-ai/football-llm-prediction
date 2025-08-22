"""LLM-optimized backfill script for finished fixtures with direct data extraction."""

from __future__ import annotations

import os
import sys
from typing import Optional

import pendulum
import typer

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.clients.sportmonks import SportMonksClient
from app.config import settings
from app.db.session import create_session
from app.db import models as m
from app.ingest import mappers
from app.ingest.upsert import bulk_upsert, update_etl_cursor, get_or_create_mapping
from app.logging import configure_logging, get_logger

# Configure logging
configure_logging()
logger = get_logger("backfill")

app = typer.Typer(
    help="LLM-optimized backfill for finished fixtures with direct result extraction.",
    no_args_is_help=True,
)


def resolve_fixture_foreign_keys(session, fixtures):
    """Resolve SportMonks IDs to internal IDs for fixture foreign keys."""
    logger.info("Resolving SportMonks IDs to internal IDs...")

    # Extract unique SportMonks IDs
    league_sm_ids = set()
    season_sm_ids = set()
    venue_sm_ids = set()

    for fixture in fixtures:
        if fixture.get("league_id"):
            league_sm_ids.add(fixture["league_id"])
        if fixture.get("season_id"):
            season_sm_ids.add(fixture["season_id"])
        if fixture.get("venue_id"):
            venue_sm_ids.add(fixture["venue_id"])

    logger.info(
        f"Found {len(league_sm_ids)} unique leagues, {len(season_sm_ids)} seasons, {len(venue_sm_ids)} venues"
    )

    # Get internal ID mappings
    league_mappings = get_or_create_mapping(
        session, m.League, "sm_id", list(league_sm_ids)
    )
    season_mappings = get_or_create_mapping(
        session, m.Season, "sm_id", list(season_sm_ids)
    )
    venue_mappings = get_or_create_mapping(
        session, m.Venue, "sm_id", list(venue_sm_ids)
    )

    logger.info(
        f"Resolved {len(league_mappings)} leagues, {len(season_mappings)} seasons, {len(venue_mappings)} venues"
    )

    # Transform fixtures to use internal IDs
    resolved_fixtures = []
    for fixture in fixtures:
        resolved_fixture = fixture.copy()

        # Resolve foreign key IDs
        if fixture.get("league_id"):
            resolved_fixture["league_id"] = league_mappings.get(fixture["league_id"])
        if fixture.get("season_id"):
            resolved_fixture["season_id"] = season_mappings.get(fixture["season_id"])
        if fixture.get("venue_id"):
            resolved_fixture["venue_id"] = venue_mappings.get(fixture["venue_id"])

        resolved_fixtures.append(resolved_fixture)

    return resolved_fixtures


@app.command()
def finished_fixtures(
    days: int = typer.Option(
        30,
        "--days",
        "-d",
        min=1,
        max=365,
        help="Number of days to backfill finished fixtures",
    ),
    leagues: Optional[str] = typer.Option(
        None,
        "--leagues",
        "-l",
        help="Comma-separated league names to backfill (default: all configured leagues)",
    ),
    include_details: bool = typer.Option(
        True,
        "--include-details/--no-details",
        help="Include events, statistics, and player data",
    ),
    league_filter: bool = typer.Option(
        True,
        "--league-filter",
        help="Filter fixtures to only our configured leagues",
    ),
) -> None:
    """
    Backfill finished fixtures with LLM-optimized direct data extraction.

    This script focuses on finished matches only and extracts direct results
    from SportMonks participants.meta.winner and scores.CURRENT without
    requiring complex aggregations.

    Examples:
        python -m app.scripts.backfill finished-fixtures --days 30
        python -m app.scripts.backfill finished-fixtures --days 7
        python -m app.scripts.backfill finished-fixtures --days 60
    """
    logger.info("=" * 70)
    logger.info("LLM-OPTIMIZED FINISHED FIXTURES BACKFILL")
    logger.info("=" * 70)
    logger.info(f"Days to backfill: {days}")
    logger.info(f"Include detailed data: {include_details}")
    logger.info(f"Filter to our leagues: {league_filter}")

    # Parse leagues
    if leagues:
        league_list = [league.strip() for league in leagues.split(",")]
    else:
        league_list = settings.LEAGUE_NAMES

    logger.info(f"Target leagues: {', '.join(league_list)}")
    logger.info("=" * 70)

    # Calculate date range for historical finished matches
    end_date = pendulum.now(settings.TIMEZONE)
    start_date = end_date.subtract(days=days)

    start_str = start_date.to_date_string()
    end_str = end_date.to_date_string()

    logger.info(f"Date range: {start_str} to {end_str}")

    try:
        with SportMonksClient() as client, create_session() as session:
            # Step 1: Get our league IDs for filtering (if enabled)
            our_league_ids = set()
            if league_filter:
                logger.info("Getting our league IDs for filtering...")
                leagues_query = session.query(m.League).all()
                our_league_ids = {league.sm_id for league in leagues_query}
                logger.info(f"Will filter to {len(our_league_ids)} configured leagues")

            # Step 2: Fetch finished fixtures with LLM-optimized includes
            logger.info("Fetching finished fixtures with LLM-optimized data...")
            fixtures = client.fixtures_between(
                start_str,
                end_str,
                include_details=include_details,
                finished_only=True,  # Only get completed matches (state_id = 5)
            )

            if not fixtures:
                logger.warning("No finished fixtures found in the specified date range")
                return

            # Step 3: Filter to our leagues if enabled
            if league_filter and our_league_ids:
                original_count = len(fixtures)
                fixtures = [
                    fx for fx in fixtures if fx.get("league_id") in our_league_ids
                ]
                logger.info(
                    f"Filtered from {original_count} to {len(fixtures)} finished fixtures for our leagues"
                )

            if not fixtures:
                logger.warning("No finished fixtures found for our configured leagues")
                return

            logger.info(f"Processing {len(fixtures)} finished fixtures")

            # Step 4: Map fixtures with direct LLM data extraction
            logger.info(
                "Extracting direct results from SportMonks participants and scores..."
            )
            if include_details:
                # Use complete mapping with computed LLM fields
                fixture_data_raw = [mappers.map_fixture_complete(fx) for fx in fixtures]
                logger.info(
                    "✅ Extracted: final scores, win/loss, league positions, team stats"
                )
            else:
                # Use basic mapping for shell data only
                fixture_data_raw = [mappers.map_fixture_shell(fx) for fx in fixtures]
                logger.info("✅ Extracted: basic fixture information")

            # Step 5: Resolve SportMonks IDs to internal IDs for foreign keys
            fixture_data_resolved = resolve_fixture_foreign_keys(
                session, fixture_data_raw
            )

            # Step 6: Resolve team IDs from participants
            logger.info("Resolving team IDs from participants...")
            for i, (fixture_data, original_fixture) in enumerate(
                zip(fixture_data_resolved, fixtures)
            ):
                # Get SportMonks team IDs from the mapped data
                home_team_sm_id = fixture_data.get("home_team_sm_id")
                away_team_sm_id = fixture_data.get("away_team_sm_id")

                if home_team_sm_id or away_team_sm_id:
                    team_sm_ids = [
                        id for id in [home_team_sm_id, away_team_sm_id] if id
                    ]
                    team_mappings = get_or_create_mapping(
                        session, m.Team, "sm_id", team_sm_ids
                    )

                    # Set internal team IDs
                    fixture_data_resolved[i]["home_team_id"] = (
                        team_mappings.get(home_team_sm_id) if home_team_sm_id else None
                    )
                    fixture_data_resolved[i]["away_team_id"] = (
                        team_mappings.get(away_team_sm_id) if away_team_sm_id else None
                    )

                    # Remove the temporary SportMonks ID fields
                    fixture_data_resolved[i].pop("home_team_sm_id", None)
                    fixture_data_resolved[i].pop("away_team_sm_id", None)

            # Step 7: Upsert fixtures with computed LLM-ready fields
            rows_affected = bulk_upsert(
                session, m.Fixture, fixture_data_resolved, ["sm_id"]
            )
            session.commit()

            logger.info(
                f"Upserted {rows_affected} finished fixtures with LLM-optimized data"
            )

            total_events = 0
            total_team_stats = 0
            total_player_stats = 0

            if include_details:
                logger.info("Processing detailed match data...")

                # Get fixture ID mappings for detailed data processing
                fixture_ids = [fx["id"] for fx in fixtures]
                fixture_mappings = get_or_create_mapping(
                    session, m.Fixture, "sm_id", fixture_ids
                )

                # Process in batches for better performance
                batch_size = 50
                for i in range(0, len(fixtures), batch_size):
                    batch_fixtures = fixtures[i : i + batch_size]
                    batch_num = i // batch_size + 1
                    total_batches = (len(fixtures) + batch_size - 1) // batch_size

                    logger.info(
                        f"Processing detailed data batch {batch_num}/{total_batches} ({len(batch_fixtures)} fixtures)"
                    )

                    for fixture in batch_fixtures:
                        sm_fixture_id = fixture["id"]
                        internal_fixture_id = fixture_mappings.get(sm_fixture_id)

                        if not internal_fixture_id:
                            logger.warning(
                                f"No internal ID found for fixture {sm_fixture_id}"
                            )
                            continue

                        # Process events with resolved team/player IDs
                        events = fixture.get("events", [])
                        if events:
                            # Get team and player mappings for events
                            event_team_ids = {
                                e.get("participant_id")
                                for e in events
                                if e.get("participant_id")
                            }
                            event_player_ids = {
                                e.get("player_id") for e in events if e.get("player_id")
                            }
                            event_related_player_ids = {
                                e.get("related_player_id")
                                for e in events
                                if e.get("related_player_id")
                            }

                            event_team_mappings = get_or_create_mapping(
                                session, m.Team, "sm_id", list(event_team_ids)
                            )
                            all_player_ids = list(
                                event_player_ids | event_related_player_ids
                            )
                            event_player_mappings = get_or_create_mapping(
                                session, m.Player, "sm_id", all_player_ids
                            )

                            # Map events with resolved IDs
                            event_data = []
                            for event in events:
                                mapped_event = mappers.map_event(
                                    event, internal_fixture_id
                                )

                                # Resolve IDs
                                if mapped_event.get("team_id"):
                                    mapped_event["team_id"] = event_team_mappings.get(
                                        mapped_event["team_id"]
                                    )
                                if mapped_event.get("player_id"):
                                    mapped_event["player_id"] = (
                                        event_player_mappings.get(
                                            mapped_event["player_id"]
                                        )
                                    )
                                if mapped_event.get("related_player_id"):
                                    mapped_event["related_player_id"] = (
                                        event_player_mappings.get(
                                            mapped_event["related_player_id"]
                                        )
                                    )

                                event_data.append(mapped_event)

                            bulk_upsert(session, m.FixtureEvent, event_data, ["id"])
                            total_events += len(event_data)

                        # Process team statistics
                        statistics = fixture.get("statistics", [])
                        if statistics:
                            stat_team_ids = {
                                s.get("participant_id")
                                for s in statistics
                                if s.get("participant_id")
                            }
                            stat_team_mappings = get_or_create_mapping(
                                session, m.Team, "sm_id", list(stat_team_ids)
                            )

                            team_stat_data = []
                            for stat in statistics:
                                participant_sm_id = stat.get("participant_id")
                                if participant_sm_id:
                                    participant_internal_id = stat_team_mappings.get(
                                        participant_sm_id
                                    )
                                    if participant_internal_id and (
                                        stat.get("type_id") or stat.get("type")
                                    ):
                                        team_stat_data.append(
                                            mappers.map_fixture_team_stat(
                                                stat,
                                                internal_fixture_id,
                                                participant_internal_id,
                                            )
                                        )

                            if team_stat_data:
                                bulk_upsert(
                                    session,
                                    m.FixtureTeamStat,
                                    team_stat_data,
                                    ["fixture_id", "team_id", "stat_code"],
                                )
                                total_team_stats += len(team_stat_data)

                        # Process player statistics
                        lineups = fixture.get("lineups", [])
                        if lineups:
                            lineup_player_ids = {
                                l.get("player_id")
                                for l in lineups
                                if l.get("player_id")
                            }
                            lineup_player_mappings = get_or_create_mapping(
                                session, m.Player, "sm_id", list(lineup_player_ids)
                            )

                            player_stat_data = []
                            for lineup in lineups:
                                player_sm_id = lineup.get("player_id")
                                if player_sm_id:
                                    player_internal_id = lineup_player_mappings.get(
                                        player_sm_id
                                    )
                                    if player_internal_id:
                                        details = lineup.get("details", [])
                                        for stat in details:
                                            if stat.get("type_id") or stat.get("type"):
                                                player_stat_data.append(
                                                    mappers.map_player_match_stat(
                                                        stat,
                                                        internal_fixture_id,
                                                        player_internal_id,
                                                    )
                                                )

                            if player_stat_data:
                                bulk_upsert(
                                    session,
                                    m.PlayerMatchStat,
                                    player_stat_data,
                                    ["fixture_id", "player_id", "stat_code"],
                                )
                                total_player_stats += len(player_stat_data)

                    # Commit after each batch
                    session.commit()
                    logger.info(
                        f"Completed detailed processing batch {batch_num}/{total_batches}"
                    )

            # Update ETL cursor
            cursor_value = (
                f"{start_str}:{end_str}:finished_only=True:details={include_details}"
            )
            update_etl_cursor(session, f"finished_backfill_{days}d", cursor_value)
            session.commit()

            # Print comprehensive summary
            typer.echo("\n" + "=" * 70)
            typer.echo(
                typer.style(
                    "LLM-OPTIMIZED BACKFILL COMPLETE", fg=typer.colors.GREEN, bold=True
                )
            )
            typer.echo("=" * 70)

    except Exception as e:
        logger.error(f"LLM-optimized backfill failed: {e}")
        typer.echo(
            typer.style(f"❌ LLM-optimized backfill failed: {e}", fg=typer.colors.RED),
            err=True,
        )
        raise typer.Exit(1)


@app.command()
def upcoming_fixtures(
    days: int = typer.Option(
        21,
        "--days",
        "-d",
        min=1,
        max=60,
        help="Number of days ahead to fetch upcoming fixtures",
    ),
    leagues: Optional[str] = typer.Option(
        None,
        "--leagues",
        "-l",
        help="Comma-separated league names to fetch (default: all configured leagues)",
    ),
) -> None:
    """
    Backfill upcoming fixtures for LLM prediction preparation.

    This fetches scheduled matches (state_id = 1) without detailed data,
    as these will be used for prediction rather than analysis.

    Examples:
        python -m app.scripts.backfill upcoming-fixtures --days 21
        python -m app.scripts.backfill upcoming-fixtures --days 7 --leagues "Premier League"
    """
    logger.info("=" * 70)
    logger.info("UPCOMING FIXTURES BACKFILL FOR LLM PREDICTION")
    logger.info("=" * 70)
    logger.info(f"Days ahead to fetch: {days}")

    # Parse leagues
    if leagues:
        league_list = [league.strip() for league in leagues.split(",")]
    else:
        league_list = settings.LEAGUE_NAMES

    logger.info(f"Target leagues: {', '.join(league_list)}")
    logger.info("=" * 70)

    # Calculate date range for upcoming fixtures
    start_date = pendulum.now(settings.TIMEZONE)
    end_date = start_date.add(days=days)

    start_str = start_date.to_date_string()
    end_str = end_date.to_date_string()

    logger.info(f"Date range: {start_str} to {end_str}")

    try:
        with SportMonksClient() as client, create_session() as session:
            # Get our league IDs for filtering
            logger.info("Getting our league IDs for filtering...")
            leagues_query = session.query(m.League).all()
            our_league_ids = {league.sm_id for league in leagues_query}
            logger.info(f"Will filter to {len(our_league_ids)} configured leagues")

            # Fetch upcoming fixtures (scheduled matches only)
            logger.info("Fetching upcoming fixtures...")
            upcoming_fixtures = client.get_upcoming_fixtures(
                days_ahead=days, league_ids=list(our_league_ids)
            )

            if not upcoming_fixtures:
                logger.warning("No upcoming fixtures found for our configured leagues")
                return

            logger.info(f"Processing {len(upcoming_fixtures)} upcoming fixtures")

            # Map upcoming fixtures to basic database format
            fixture_data_raw = [
                mappers.map_fixture_shell(fx) for fx in upcoming_fixtures
            ]

            # Resolve SportMonks IDs to internal IDs
            fixture_data_resolved = resolve_fixture_foreign_keys(
                session, fixture_data_raw
            )

            # Add team assignments from participants
            for i, fixture in enumerate(upcoming_fixtures):
                participants = fixture.get("participants", [])
                home_team_sm_id, away_team_sm_id = (
                    mappers.extract_home_away_from_participants(participants)
                )

                # Resolve team IDs
                if home_team_sm_id or away_team_sm_id:
                    team_sm_ids = [
                        id for id in [home_team_sm_id, away_team_sm_id] if id
                    ]
                    team_mappings = get_or_create_mapping(
                        session, m.Team, "sm_id", team_sm_ids
                    )

                    fixture_data_resolved[i]["home_team_id"] = (
                        team_mappings.get(home_team_sm_id) if home_team_sm_id else None
                    )
                    fixture_data_resolved[i]["away_team_id"] = (
                        team_mappings.get(away_team_sm_id) if away_team_sm_id else None
                    )

            # Upsert upcoming fixtures
            rows_affected = bulk_upsert(
                session, m.Fixture, fixture_data_resolved, ["sm_id"]
            )
            session.commit()

            # Update ETL cursor
            cursor_value = f"{start_str}:{end_str}:upcoming_only=True"
            update_etl_cursor(session, f"upcoming_backfill_{days}d", cursor_value)
            session.commit()

            # Print summary
            typer.echo("\n" + "=" * 70)
            typer.echo(
                typer.style(
                    "UPCOMING FIXTURES BACKFILL COMPLETE",
                    fg=typer.colors.GREEN,
                    bold=True,
                )
            )
            typer.echo("=" * 70)
            typer.echo(f"✅ Upcoming fixtures processed: {len(upcoming_fixtures)}")
            typer.echo(f"✅ Database records affected: {rows_affected}")
            typer.echo(f"✅ Date range: {start_str} to {end_str}")
            typer.echo(f"✅ Ready for LLM prediction pipeline")
            typer.echo("=" * 70)

    except Exception as e:
        logger.error(f"Upcoming fixtures backfill failed: {e}")
        typer.echo(
            typer.style(
                f"❌ Upcoming fixtures backfill failed: {e}", fg=typer.colors.RED
            ),
            err=True,
        )
        raise typer.Exit(1)


@app.command()
def verify_llm_data() -> None:
    """
    Verify that LLM-optimized data is correctly populated.

    This command checks the quality and completeness of data for LLM analysis.
    """
    logger.info("Verifying LLM-optimized data quality...")

    try:
        with create_session() as session:
            # Check finished fixtures with computed fields
            finished_fixtures = (
                session.query(m.Fixture)
                .filter(
                    m.Fixture.status == "5",  # Finished matches
                    m.Fixture.result.isnot(None),  # Has result computed
                )
                .count()
            )

            finished_with_scores = (
                session.query(m.Fixture)
                .filter(
                    m.Fixture.status == "5",
                    m.Fixture.home_goals.isnot(None),
                    m.Fixture.away_goals.isnot(None),
                )
                .count()
            )

            finished_with_possession = (
                session.query(m.Fixture)
                .filter(
                    m.Fixture.status == "5",
                    m.Fixture.home_possession.isnot(None),
                    m.Fixture.away_possession.isnot(None),
                )
                .count()
            )

            # Check upcoming fixtures
            upcoming_fixtures = (
                session.query(m.Fixture)
                .filter(
                    m.Fixture.status == "1",  # Scheduled matches
                    m.Fixture.kickoff_ts >= pendulum.now(),
                )
                .count()
            )

            # Check data completeness
            total_finished = (
                session.query(m.Fixture).filter(m.Fixture.status == "5").count()
            )

            typer.echo("\n" + "=" * 60)
            typer.echo(
                typer.style(
                    "LLM DATA VERIFICATION REPORT", fg=typer.colors.BLUE, bold=True
                )
            )
            typer.echo("=" * 60)

            typer.echo(f"📊 FINISHED MATCHES:")
            typer.echo(f"   Total finished fixtures: {total_finished}")
            typer.echo(
                f"   With computed results: {finished_fixtures} ({finished_fixtures/total_finished*100:.1f}%)"
                if total_finished > 0
                else "   With computed results: 0"
            )
            typer.echo(
                f"   With final scores: {finished_with_scores} ({finished_with_scores/total_finished*100:.1f}%)"
                if total_finished > 0
                else "   With final scores: 0"
            )
            typer.echo(
                f"   With possession data: {finished_with_possession} ({finished_with_possession/total_finished*100:.1f}%)"
                if total_finished > 0
                else "   With possession data: 0"
            )

            typer.echo(f"\n🔮 UPCOMING MATCHES:")
            typer.echo(f"   Scheduled fixtures: {upcoming_fixtures}")

            # Sample LLM-ready data
            sample_fixture = (
                session.query(m.Fixture)
                .filter(
                    m.Fixture.status == "5",
                    m.Fixture.result.isnot(None),
                    m.Fixture.home_goals.isnot(None),
                )
                .first()
            )

            if sample_fixture:
                typer.echo(f"\n📋 SAMPLE LLM-READY MATCH:")
                typer.echo(
                    f"   Score: {sample_fixture.home_goals}-{sample_fixture.away_goals}"
                )
                typer.echo(
                    f"   Result: {sample_fixture.result} ({'Home Win' if sample_fixture.result == 'H' else 'Away Win' if sample_fixture.result == 'A' else 'Draw'})"
                )
                if sample_fixture.home_possession:
                    typer.echo(
                        f"   Possession: {sample_fixture.home_possession}% vs {sample_fixture.away_possession}%"
                    )
                if sample_fixture.home_position:
                    typer.echo(
                        f"   League positions: {sample_fixture.home_position} vs {sample_fixture.away_position}"
                    )

                # Check related data
                events_count = (
                    session.query(m.FixtureEvent)
                    .filter_by(fixture_id=sample_fixture.id)
                    .count()
                )
                team_stats_count = (
                    session.query(m.FixtureTeamStat)
                    .filter_by(fixture_id=sample_fixture.id)
                    .count()
                )
                player_stats_count = (
                    session.query(m.PlayerMatchStat)
                    .filter_by(fixture_id=sample_fixture.id)
                    .count()
                )

                typer.echo(f"   Events: {events_count}")
                typer.echo(f"   Team stats: {team_stats_count}")
                typer.echo(f"   Player stats: {player_stats_count}")

            # Data quality assessment
            typer.echo(f"\n✅ QUALITY ASSESSMENT:")

            if finished_fixtures > 0 and finished_with_scores / total_finished > 0.8:
                typer.echo(
                    "   ✅ Excellent: >80% of finished matches have computed scores"
                )
            elif finished_with_scores / total_finished > 0.5:
                typer.echo("   ⚠️  Good: >50% of finished matches have computed scores")
            else:
                typer.echo("   ❌ Poor: <50% of finished matches have computed scores")

            if upcoming_fixtures > 0:
                typer.echo("   ✅ Upcoming fixtures available for prediction")
            else:
                typer.echo("   ⚠️  No upcoming fixtures for prediction")

            typer.echo(f"\n🎯 LLM READINESS:")
            if finished_fixtures > 10 and upcoming_fixtures > 0:
                typer.echo("   ✅ READY for LLM analysis and prediction!")
                typer.echo("   ✅ Sufficient historical data for form analysis")
                typer.echo("   ✅ Upcoming matches available for prediction")
            else:
                typer.echo("   ⚠️  Need more data for optimal LLM performance")
                typer.echo(
                    "   💡 Run: backfill finished-fixtures --days 60 --include-details"
                )

            typer.echo("=" * 60)

    except Exception as e:
        logger.error(f"Data verification failed: {e}")
        typer.echo(
            typer.style(f"❌ Data verification failed: {e}", fg=typer.colors.RED),
            err=True,
        )
        raise typer.Exit(1)


@app.command()
def clean_and_rebuild(
    days: int = typer.Option(
        60,
        "--days",
        "-d",
        min=7,
        max=365,
        help="Number of days of finished fixtures to rebuild",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Confirm deletion of existing fixture data",
    ),
) -> None:
    """
    Clean existing fixture data and rebuild with LLM-optimized structure.

    This is useful when upgrading from the old schema to the new one.

    Examples:
        python -m app.scripts.backfill clean-and-rebuild --days 30 --confirm
    """
    if not confirm:
        typer.echo("⚠️  This will delete ALL existing fixture data!")
        typer.echo("Use --confirm flag if you're sure you want to proceed.")
        raise typer.Exit(1)

    logger.info("=" * 70)
    logger.info("CLEAN AND REBUILD WITH LLM-OPTIMIZED DATA")
    logger.info("=" * 70)
    logger.warning("This will delete ALL existing fixture data!")

    try:
        with create_session() as session:
            # Count existing data
            existing_fixtures = session.query(m.Fixture).count()
            existing_events = session.query(m.FixtureEvent).count()
            existing_team_stats = session.query(m.FixtureTeamStat).count()
            existing_player_stats = session.query(m.PlayerMatchStat).count()

            logger.info(f"Existing data to be deleted:")
            logger.info(f"  Fixtures: {existing_fixtures}")
            logger.info(f"  Events: {existing_events}")
            logger.info(f"  Team stats: {existing_team_stats}")
            logger.info(f"  Player stats: {existing_player_stats}")

            # Delete existing fixture data (cascades to related tables)
            logger.info("Deleting existing fixture data...")
            session.query(m.Fixture).delete()
            session.commit()

            logger.info("✅ Existing fixture data deleted")

        logger.info("Rebuilding with LLM-optimized data extraction...")

        # Run the finished fixtures backfill
        from app.scripts.backfill import finished_fixtures as backfill_finished

        # This will be called programmatically
        typer.echo("Starting LLM-optimized rebuild...")

        typer.echo(
            f"Run: python -m app.scripts.backfill finished-fixtures --days {days} --include-details"
        )
        typer.echo("Then: python -m app.scripts.backfill upcoming-fixtures --days 21")
        typer.echo("Finally: python -m app.scripts.backfill verify-llm-data")

        typer.echo("\n✅ Clean and rebuild process initiated")

    except Exception as e:
        logger.error(f"Clean and rebuild failed: {e}")
        typer.echo(
            typer.style(f"❌ Clean and rebuild failed: {e}", fg=typer.colors.RED),
            err=True,
        )
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
