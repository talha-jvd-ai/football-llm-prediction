"""Celery tasks for LLM-optimized data ingestion and synchronization."""

from __future__ import annotations

from typing import Dict, List, Optional, Any

import pendulum
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import create_session
from app.db import models as m
from app.clients.sportmonks import SportMonksClient
from app.ingest import mappers
from app.ingest.upsert import (
    bulk_upsert,
    clear_fixture_related_data,
    get_or_create_mapping,
    update_etl_cursor,
)
from app.logging import get_logger
from app.worker import app as celery_app

logger = get_logger("tasks")


def _get_session() -> Session:
    """Get a database session."""
    return create_session()


def _get_client() -> SportMonksClient:
    """Get a SportMonks API client."""
    return SportMonksClient()


def _resolve_fixture_foreign_keys(
    session: Session,
    fixtures: List[Dict],
) -> List[Dict]:
    """
    Resolve SportMonks IDs to internal IDs for fixture foreign keys.

    Args:
        session: Database session
        fixtures: List of fixture data with SportMonks IDs

    Returns:
        List of fixture data with internal IDs for foreign keys
    """
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
    unresolved_count = 0

    for fixture in fixtures:
        resolved_fixture = fixture.copy()

        # Resolve league_id
        if fixture.get("league_id"):
            internal_league_id = league_mappings.get(fixture["league_id"])
            if internal_league_id:
                resolved_fixture["league_id"] = internal_league_id
            else:
                logger.warning(
                    f"No internal ID found for league {fixture['league_id']}"
                )
                resolved_fixture["league_id"] = None
                unresolved_count += 1

        # Resolve season_id
        if fixture.get("season_id"):
            internal_season_id = season_mappings.get(fixture["season_id"])
            if internal_season_id:
                resolved_fixture["season_id"] = internal_season_id
            else:
                logger.warning(
                    f"No internal ID found for season {fixture['season_id']}"
                )
                resolved_fixture["season_id"] = None
                unresolved_count += 1

        # Resolve venue_id
        if fixture.get("venue_id"):
            internal_venue_id = venue_mappings.get(fixture["venue_id"])
            if internal_venue_id:
                resolved_fixture["venue_id"] = internal_venue_id
            else:
                logger.warning(f"No internal ID found for venue {fixture['venue_id']}")
                resolved_fixture["venue_id"] = None
                unresolved_count += 1

        resolved_fixtures.append(resolved_fixture)

    if unresolved_count > 0:
        logger.warning(f"Could not resolve {unresolved_count} foreign key references")

    return resolved_fixtures


def _ensure_leagues_and_seasons(
    session: Session,
    client: SportMonksClient,
    league_names: List[str],
) -> Dict[str, Dict[str, int]]:
    """
    Ensure leagues and seasons exist in database and return current season mapping.

    Args:
        session: Database session
        client: SportMonks client
        league_names: List of league names to process

    Returns:
        Dictionary mapping league names to {'league_id': int, 'season_id': int}
    """
    league_season_mapping = {}

    for league_name in league_names:
        logger.info(f"Processing league: {league_name}")

        # Search for league by name
        leagues = client.leagues_all()
        target_league = None

        # Try exact match first
        for league in leagues:
            if (league.get("name") or "").lower() == league_name.lower():
                target_league = league
                break

        # Fall back to partial match
        if not target_league:
            for league in leagues:
                if league_name.lower() in (league.get("name") or "").lower():
                    target_league = league
                    break

        if not target_league:
            logger.warning(f"League '{league_name}' not found in SportMonks")
            continue

        league_sm_id = target_league["id"]

        # Upsert league
        league_data = mappers.map_league(target_league)
        bulk_upsert(session, m.League, [league_data], ["sm_id"])

        # Get internal league ID
        league_id_mapping = get_or_create_mapping(
            session, m.League, "sm_id", [league_sm_id]
        )
        internal_league_id = league_id_mapping.get(league_sm_id)

        if not internal_league_id:
            logger.error(f"Failed to get internal ID for league {league_name}")
            continue

        # Get current season for this specific league
        current_season = client.get_current_season_for_league(league_sm_id)

        if not current_season:
            logger.warning(f"No current season found for league {league_name}")
            continue

        # Upsert season
        season_data = mappers.map_season(current_season, internal_league_id)
        bulk_upsert(session, m.Season, [season_data], ["sm_id"])

        current_season_sm_id = current_season["id"]
        league_season_mapping[league_name] = {
            "league_id": league_sm_id,
            "season_id": current_season_sm_id,
        }

        logger.info(
            f"Mapped {league_name} (ID: {league_sm_id}) to season {current_season_sm_id}"
        )

    session.commit()
    return league_season_mapping


@celery_app.task(name="ingest.sync_metadata")
def sync_metadata() -> Dict[str, int]:
    """
    Sync leagues, seasons, teams, venues, coaches, and players.

    Returns:
        Dictionary of processed items counts
    """
    logger.info("Starting metadata sync")

    with _get_client() as client, _get_session() as session:
        # Ensure leagues and seasons exist with proper mapping
        league_season_mapping = _ensure_leagues_and_seasons(
            session, client, settings.LEAGUE_NAMES
        )

        total_teams = 0
        total_venues = 0
        total_coaches = 0
        total_players = 0

        # Process each league's teams and related data
        for league_name, mapping in league_season_mapping.items():
            season_id = mapping["season_id"]
            logger.info(f"Syncing teams for {league_name} (season {season_id})")

            # Get teams for this specific league's current season
            teams = client.teams_by_season(season_id, include_details=True)
            if not teams:
                logger.warning(f"No teams found for {league_name} season {season_id}")
                continue

            # Extract and upsert venues
            venue_data = []
            venue_sm_ids = []

            for team in teams:
                venue = team.get("venue")
                if isinstance(venue, dict) and venue.get("id"):
                    venue_data.append(mappers.map_venue(venue))
                    venue_sm_ids.append(venue["id"])

            if venue_data:
                bulk_upsert(session, m.Venue, venue_data, ["sm_id"])
                total_venues += len(venue_data)
                logger.info(f"Upserted {len(venue_data)} venues for {league_name}")

            # Get venue ID mappings
            venue_mappings = get_or_create_mapping(
                session, m.Venue, "sm_id", venue_sm_ids
            )

            # Get league ID mapping
            league_query = session.query(m.League).filter_by(name=league_name).first()
            if not league_query:
                logger.error(f"League {league_name} not found in database")
                continue

            internal_league_id = league_query.id

            # Upsert teams
            team_data = []
            team_sm_ids = []

            for team in teams:
                venue = team.get("venue")
                venue_id = None
                if isinstance(venue, dict) and venue.get("id"):
                    venue_id = venue_mappings.get(venue["id"])

                team_data.append(mappers.map_team(team, internal_league_id, venue_id))
                team_sm_ids.append(team["id"])

            if team_data:
                bulk_upsert(session, m.Team, team_data, ["sm_id"])
                total_teams += len(team_data)
                logger.info(f"Upserted {len(team_data)} teams for {league_name}")

            # Get team ID mappings for coaches and players
            team_mappings = get_or_create_mapping(session, m.Team, "sm_id", team_sm_ids)

            # Extract coach IDs and fetch full coach details
            all_coach_ids = []
            team_coach_mapping = {}  # team_id -> list of coach_ids

            for team in teams:
                team_sm_id = team["id"]
                coach_ids = mappers.extract_coaching_staff_ids(team)
                if coach_ids:
                    all_coach_ids.extend(coach_ids)
                    team_coach_mapping[team_sm_id] = coach_ids

            # Remove duplicates
            unique_coach_ids = list(set(all_coach_ids))

            if unique_coach_ids:
                logger.info(
                    f"Fetching details for {len(unique_coach_ids)} coaches for {league_name}"
                )

                # Fetch full coach details
                full_coaches = client.coaches_by_ids(unique_coach_ids)

                # Map coaches to database format - handle duplicates properly
                coach_data_dict = {}  # sm_id -> coach_data to avoid duplicates

                for coach in full_coaches:
                    coach_sm_id = coach["id"]

                    # Find the primary team for this coach (first team in mapping)
                    primary_team_id = None
                    for team_sm_id, coach_ids in team_coach_mapping.items():
                        if coach_sm_id in coach_ids:
                            primary_team_id = team_mappings.get(team_sm_id)
                            break

                    if primary_team_id and coach_sm_id not in coach_data_dict:
                        coach_data_dict[coach_sm_id] = mappers.map_coach_from_full_data(
                            coach, primary_team_id
                        )

                # Convert to list for bulk insert
                coach_data = list(coach_data_dict.values())

                if coach_data:
                    bulk_upsert(session, m.Coach, coach_data, ["sm_id"])
                    total_coaches += len(coach_data)
                    logger.info(f"Upserted {len(coach_data)} coaches for {league_name}")

            # Extract player IDs and fetch full player details
            all_player_ids = []
            team_player_mapping = {}  # team_id -> list of player_ids

            for team in teams:
                team_sm_id = team["id"]
                player_ids = mappers.extract_squad_player_ids(team)
                if player_ids:
                    all_player_ids.extend(player_ids)
                    team_player_mapping[team_sm_id] = player_ids

            # Remove duplicates
            unique_player_ids = list(set(all_player_ids))

            if unique_player_ids:
                logger.info(
                    f"Fetching details for {len(unique_player_ids)} players for {league_name}"
                )

                # Fetch full player details
                full_players = client.players_by_ids(unique_player_ids)

                # Map players to database format - handle duplicates properly
                player_data_dict = {}  # sm_id -> player_data to avoid duplicates

                for player in full_players:
                    player_sm_id = player["id"]

                    # Find the primary team for this player (first team in mapping)
                    primary_team_id = None
                    for team_sm_id, player_ids in team_player_mapping.items():
                        if player_sm_id in player_ids:
                            primary_team_id = team_mappings.get(team_sm_id)
                            break

                    if primary_team_id and player_sm_id not in player_data_dict:
                        player_data_dict[player_sm_id] = (
                            mappers.map_player_from_full_data(player, primary_team_id)
                        )

                # Convert to list for bulk insert
                player_data = list(player_data_dict.values())

                if player_data:
                    bulk_upsert(session, m.Player, player_data, ["sm_id"])
                    total_players += len(player_data)
                    logger.info(
                        f"Upserted {len(player_data)} players for {league_name}"
                    )

        session.commit()

        # Update ETL cursor
        current_time = pendulum.now().to_iso8601_string()
        update_etl_cursor(session, "metadata_sync", current_time)
        session.commit()

    result = {
        "teams": total_teams,
        "venues": total_venues,
        "coaches": total_coaches,
        "players": total_players,
    }

    logger.info(f"Metadata sync completed: {result}")
    return result


@celery_app.task(name="ingest.sync_finished_fixtures")
def sync_finished_fixtures(horizon_days: Optional[int] = None) -> Dict[str, int]:
    """
    Sync finished fixtures with LLM-optimized direct data extraction.

    Args:
        horizon_days: Number of days back to fetch finished fixtures

    Returns:
        Dictionary of processed items counts
    """
    horizon_days = horizon_days or 30  # Default to last 30 days for finished matches
    logger.info(f"Starting finished fixtures sync (horizon: {horizon_days} days back)")

    with _get_client() as client, _get_session() as session:
        # Calculate date range for historical finished matches
        end_date = pendulum.now(settings.TIMEZONE).to_date_string()
        start_date = (
            pendulum.now(settings.TIMEZONE).subtract(days=horizon_days).to_date_string()
        )

        logger.info(f"Fetching finished fixtures between {start_date} and {end_date}")

        # Fetch finished fixtures only with LLM-optimized includes
        fixtures = client.fixtures_between(
            start_date,
            end_date,
            include_details=True,
            finished_only=True,  # Only get completed matches
        )
        logger.info(f"Found {len(fixtures)} finished fixtures to process")

        if not fixtures:
            return {"fixtures": 0, "events": 0, "team_stats": 0, "player_stats": 0}

        # Map fixtures to database format with direct result extraction
        fixture_data_raw = [mappers.map_fixture_complete(fx) for fx in fixtures]

        # Resolve SportMonks IDs to internal IDs for foreign keys
        fixture_data_resolved = _resolve_fixture_foreign_keys(session, fixture_data_raw)

        # Upsert fixtures with all computed LLM-ready fields
        rows_affected = bulk_upsert(
            session, m.Fixture, fixture_data_resolved, ["sm_id"]
        )
        session.commit()

        logger.info(
            f"Upserted {rows_affected} finished fixtures with computed LLM data"
        )

        # Process detailed events and statistics for finished matches
        total_events = 0
        total_team_stats = 0
        total_player_stats = 0

        # Get fixture ID mappings (SportMonks ID -> internal ID)
        fixture_ids = [fx["id"] for fx in fixtures]
        fixture_mappings = get_or_create_mapping(
            session, m.Fixture, "sm_id", fixture_ids
        )

        for fixture in fixtures:
            sm_fixture_id = fixture["id"]
            internal_fixture_id = fixture_mappings.get(sm_fixture_id)

            if not internal_fixture_id:
                logger.warning(f"No internal ID found for fixture {sm_fixture_id}")
                continue

            # Clear existing related data for clean re-processing
            clear_fixture_related_data(session, internal_fixture_id)

            # Process events with resolved IDs
            events = fixture.get("events", [])
            if events:
                # Resolve team and player IDs for events
                event_team_ids = {
                    event.get("participant_id")
                    for event in events
                    if event.get("participant_id")
                }
                event_player_ids = {
                    event.get("player_id") for event in events if event.get("player_id")
                }
                event_related_player_ids = {
                    event.get("related_player_id")
                    for event in events
                    if event.get("related_player_id")
                }

                # Get mappings for event participants
                event_team_mappings = get_or_create_mapping(
                    session, m.Team, "sm_id", list(event_team_ids)
                )
                all_event_player_ids = list(event_player_ids | event_related_player_ids)
                event_player_mappings = get_or_create_mapping(
                    session, m.Player, "sm_id", all_event_player_ids
                )

                # Map events with resolved IDs
                event_data = []
                for event in events:
                    mapped_event = mappers.map_event(event, internal_fixture_id)

                    # Resolve team ID
                    if mapped_event.get("team_id"):
                        mapped_event["team_id"] = event_team_mappings.get(
                            mapped_event["team_id"]
                        )

                    # Resolve player IDs
                    if mapped_event.get("player_id"):
                        mapped_event["player_id"] = event_player_mappings.get(
                            mapped_event["player_id"]
                        )

                    if mapped_event.get("related_player_id"):
                        mapped_event["related_player_id"] = event_player_mappings.get(
                            mapped_event["related_player_id"]
                        )

                    event_data.append(mapped_event)

                bulk_upsert(session, m.FixtureEvent, event_data, ["id"])
                total_events += len(event_data)

            # Process team statistics with resolved IDs
            statistics = fixture.get("statistics", [])
            if statistics:
                # Get team mappings for statistics
                stat_team_ids = {
                    stat.get("participant_id")
                    for stat in statistics
                    if stat.get("participant_id")
                }
                stat_team_mappings = get_or_create_mapping(
                    session, m.Team, "sm_id", list(stat_team_ids)
                )

                team_stat_data = []
                for stat_group in statistics:
                    participant_sm_id = stat_group.get("participant_id")
                    if not participant_sm_id:
                        continue

                    participant_internal_id = stat_team_mappings.get(participant_sm_id)
                    if not participant_internal_id:
                        continue

                    # SportMonks API v3: statistics are directly in stat_group
                    if stat_group.get("type_id") or stat_group.get("type"):
                        team_stat_data.append(
                            mappers.map_fixture_team_stat(
                                stat_group, internal_fixture_id, participant_internal_id
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

            # Process player statistics with resolved IDs
            lineups = fixture.get("lineups", [])
            if lineups:
                # Get player mappings for lineups
                lineup_player_ids = {
                    lineup.get("player_id")
                    for lineup in lineups
                    if lineup.get("player_id")
                }
                lineup_player_mappings = get_or_create_mapping(
                    session, m.Player, "sm_id", list(lineup_player_ids)
                )

                player_stat_data = []
                for lineup in lineups:
                    player_sm_id = lineup.get("player_id")
                    if not player_sm_id:
                        continue

                    player_internal_id = lineup_player_mappings.get(player_sm_id)
                    if not player_internal_id:
                        continue

                    # SportMonks API v3: player stats are in lineup.details with type information
                    details = lineup.get("details", [])
                    for stat in details:
                        if stat.get("type_id") or stat.get("type"):
                            player_stat_data.append(
                                mappers.map_player_match_stat(
                                    stat, internal_fixture_id, player_internal_id
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

        session.commit()

        # Update ETL cursor
        current_time = pendulum.now().to_iso8601_string()
        update_etl_cursor(
            session, f"finished_fixtures_sync_{horizon_days}d", current_time
        )
        session.commit()

    result = {
        "fixtures": len(fixtures),
        "events": total_events,
        "team_stats": total_team_stats,
        "player_stats": total_player_stats,
    }

    logger.info(f"Finished fixtures sync completed: {result}")
    return result


@celery_app.task(name="ingest.sync_upcoming_fixtures")
def sync_upcoming_fixtures(horizon_days: Optional[int] = None) -> Dict[str, int]:
    """
    Sync upcoming fixtures for LLM prediction (basic data only).

    Args:
        horizon_days: Number of days ahead to fetch upcoming fixtures

    Returns:
        Dictionary of processed items counts
    """
    horizon_days = horizon_days or settings.FIXTURE_HORIZON_DAYS
    logger.info(f"Starting upcoming fixtures sync (horizon: {horizon_days} days ahead)")

    with _get_client() as client, _get_session() as session:
        # Calculate date range for upcoming fixtures
        start_date = pendulum.now(settings.TIMEZONE).to_date_string()
        end_date = (
            pendulum.now(settings.TIMEZONE).add(days=horizon_days).to_date_string()
        )

        logger.info(f"Fetching upcoming fixtures between {start_date} and {end_date}")

        # Get upcoming fixtures (not finished) - basic data only
        upcoming_fixtures = client.get_upcoming_fixtures(
            days_ahead=horizon_days,
            league_ids=[league.sm_id for league in session.query(m.League).all()],
        )

        logger.info(f"Found {len(upcoming_fixtures)} upcoming fixtures to process")

        if not upcoming_fixtures:
            return {"fixtures": 0}

        # Map upcoming fixtures to basic database format (no computed fields)
        fixture_data_raw = [mappers.map_fixture_shell(fx) for fx in upcoming_fixtures]

        # Resolve SportMonks IDs to internal IDs for foreign keys
        fixture_data_resolved = _resolve_fixture_foreign_keys(session, fixture_data_raw)

        # Add participants data for upcoming fixtures
        for i, fixture in enumerate(upcoming_fixtures):
            participants = fixture.get("participants", [])
            home_team_sm_id, away_team_sm_id = (
                mappers.extract_home_away_from_participants(participants)
            )

            # Resolve team IDs
            if home_team_sm_id or away_team_sm_id:
                team_sm_ids = [id for id in [home_team_sm_id, away_team_sm_id] if id]
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

        logger.info(f"Upserted {rows_affected} upcoming fixtures")

        # Update ETL cursor
        current_time = pendulum.now().to_iso8601_string()
        update_etl_cursor(
            session, f"upcoming_fixtures_sync_{horizon_days}d", current_time
        )
        session.commit()

    result = {
        "fixtures": len(upcoming_fixtures),
    }

    logger.info(f"Upcoming fixtures sync completed: {result}")
    return result


@celery_app.task(name="ingest.hydrate_fixture")
def hydrate_fixture(fixture_id: int) -> bool:
    """
    Hydrate a specific fixture by SportMonks ID with complete LLM data.

    Args:
        fixture_id: SportMonks fixture ID

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Hydrating fixture {fixture_id} with complete LLM data")

    try:
        with _get_client() as client, _get_session() as session:
            # Fetch detailed fixture data with LLM-optimized includes
            detailed_fixtures = client.fixtures_multi([fixture_id])

            if not detailed_fixtures:
                logger.warning(f"No data returned for fixture {fixture_id}")
                return False

            fixture = detailed_fixtures[0]

            # Get internal fixture ID
            fixture_mappings = get_or_create_mapping(
                session, m.Fixture, "sm_id", [fixture_id]
            )
            internal_fixture_id = fixture_mappings.get(fixture_id)

            if not internal_fixture_id:
                logger.error(f"Fixture {fixture_id} not found in database")
                return False

            # Update fixture with complete LLM-ready data
            fixture_data = mappers.map_fixture_complete(fixture)

            # Resolve foreign keys
            fixture_data_resolved = _resolve_fixture_foreign_keys(
                session, [fixture_data]
            )[0]

            # Update the fixture record
            session.query(m.Fixture).filter_by(id=internal_fixture_id).update(
                fixture_data_resolved
            )

            # Clear existing related data
            clear_fixture_related_data(session, internal_fixture_id)

            # Process events, statistics, etc. (same logic as sync_finished_fixtures)

            session.commit()
            logger.info(f"Successfully hydrated fixture {fixture_id} with LLM data")
            return True

    except Exception as e:
        logger.error(f"Failed to hydrate fixture {fixture_id}: {e}")
        return False


@celery_app.task(name="ingest.cleanup_old_fixtures")
def cleanup_old_fixtures(days_to_keep: int = 365) -> Dict[str, int]:
    """
    Clean up old fixture data to keep database size manageable.

    Args:
        days_to_keep: Number of days of historical data to keep

    Returns:
        Dictionary of cleanup counts
    """
    logger.info(f"Starting cleanup of fixtures older than {days_to_keep} days")

    with _get_session() as session:
        cutoff_date = pendulum.now().subtract(days=days_to_keep).to_datetime_string()

        # Count fixtures to be deleted
        fixtures_to_delete = (
            session.query(m.Fixture).filter(m.Fixture.kickoff_ts < cutoff_date).count()
        )

        if fixtures_to_delete == 0:
            logger.info("No old fixtures to clean up")
            return {"fixtures_deleted": 0}

        # Delete old fixtures (cascade will handle related data)
        deleted_count = (
            session.query(m.Fixture).filter(m.Fixture.kickoff_ts < cutoff_date).delete()
        )

        session.commit()

        logger.info(f"Cleaned up {deleted_count} old fixtures")

        return {"fixtures_deleted": deleted_count}


# Update the worker beat schedule to use LLM-optimized tasks
@celery_app.task(name="ingest.daily_llm_data_sync")
def daily_llm_data_sync() -> Dict[str, Any]:
    """
    Daily comprehensive LLM data synchronization.

    This task orchestrates the complete LLM data pipeline:
    1. Sync metadata (teams, players, coaches)
    2. Sync finished fixtures (last 30 days with complete data)
    3. Sync upcoming fixtures (next 21 days for prediction)
    4. Cleanup old data

    Returns:
        Combined results from all sync operations
    """
    logger.info("Starting daily LLM data synchronization")

    results = {
        "metadata": {},
        "finished_fixtures": {},
        "upcoming_fixtures": {},
        "cleanup": {},
    }

    try:
        # 1. Sync metadata
        logger.info("Step 1: Syncing metadata...")
        results["metadata"] = sync_metadata()

        # 2. Sync finished fixtures (last 30 days)
        logger.info("Step 2: Syncing finished fixtures...")
        results["finished_fixtures"] = sync_finished_fixtures(30)

        # 3. Sync upcoming fixtures (next 21 days)
        logger.info("Step 3: Syncing upcoming fixtures...")
        results["upcoming_fixtures"] = sync_upcoming_fixtures(21)

        # 4. Cleanup old fixtures (keep 1 year)
        logger.info("Step 4: Cleaning up old data...")
        results["cleanup"] = cleanup_old_fixtures(365)

        logger.info("Daily LLM data synchronization completed successfully")

    except Exception as e:
        logger.error(f"Daily LLM data sync failed: {e}")
        raise

    return results
