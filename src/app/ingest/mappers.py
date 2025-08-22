"""Data mappers for converting SportMonks API responses to LLM-optimized database format."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from app.logging import get_logger

logger = get_logger("mappers")


def _convert_to_numeric(value: Any) -> Optional[float]:
    """
    Convert various value types to numeric for database storage.
    
    Args:
        value: Value from SportMonks API (could be number, boolean, string, null)
        
    Returns:
        Numeric value or None if not convertible
    """
    if value is None:
        return None
    
    # Handle boolean values
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    
    # Handle numeric values
    if isinstance(value, (int, float)):
        return float(value)
    
    # Handle string values - try to parse as number
    if isinstance(value, str):
        # Remove common non-numeric characters and try to parse
        cleaned = value.strip().replace('%', '').replace(',', '')
        
        # Try direct conversion
        try:
            return float(cleaned)
        except ValueError:
            pass
        
        # Handle special cases
        cleaned_lower = cleaned.lower()
        if cleaned_lower in ('yes', 'true', 'y', '1'):
            return 1.0
        elif cleaned_lower in ('no', 'false', 'n', '0'):
            return 0.0
        else:
            # Cannot convert to numeric
            logger.debug(f"Cannot convert string value to numeric: '{value}'")
            return None
    
    # Cannot convert
    logger.debug(f"Cannot convert value to numeric: {value} (type: {type(value)})")
    return None


def map_league(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Map SportMonks league data to database format.
    
    Args:
        obj: Raw league data from SportMonks API
        
    Returns:
        Mapped league data for database insertion
    """
    country_data = obj.get("country")
    country_name = None
    
    if isinstance(country_data, dict):
        country_name = country_data.get("name")
    elif isinstance(country_data, str):
        country_name = country_data
    
    return {
        "sm_id": obj["id"],
        "name": obj.get("name") or obj.get("display_name") or "Unknown League",
        "country": country_name,
    }


def map_season(obj: Dict[str, Any], league_id: int) -> Dict[str, Any]:
    """Map SportMonks season data to database format.
    
    Args:
        obj: Raw season data from SportMonks API
        league_id: Internal league ID (not SportMonks ID)
        
    Returns:
        Mapped season data for database insertion
    """
    name = obj.get("name") or obj.get("display_name") or "Season"
    year_start, year_end = None, None
    
    # Try to extract years from season name (e.g., "2024/2025")
    if "/" in name:
        parts = name.replace(" ", "").split("/")
        try:
            if len(parts) >= 2:
                year_start = int(parts[0][-4:])  # Last 4 digits of first part
                year_end = int(parts[1][:4])     # First 4 digits of second part
        except (ValueError, IndexError):
            pass
    
    return {
        "sm_id": obj["id"],
        "league_id": league_id,
        "name": name,
        "year_start": year_start,
        "year_end": year_end,
    }


def map_venue(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Map SportMonks venue data to database format.
    
    Args:
        obj: Raw venue data from SportMonks API
        
    Returns:
        Mapped venue data for database insertion
    """
    return {
        "sm_id": obj["id"],
        "name": obj.get("name"),
        "city": obj.get("city"),
        "capacity": obj.get("capacity"),
    }


def map_team(obj: Dict[str, Any], league_id: int, venue_id: Optional[int]) -> Dict[str, Any]:
    """Map SportMonks team data to database format.
    
    Args:
        obj: Raw team data from SportMonks API
        league_id: Internal league ID (not SportMonks ID)
        venue_id: Internal venue ID (not SportMonks ID)
        
    Returns:
        Mapped team data for database insertion
    """
    country_data = obj.get("country")
    country_name = None
    
    if isinstance(country_data, dict):
        country_name = country_data.get("name")
    elif isinstance(country_data, str):
        country_name = country_data
    
    return {
        "sm_id": obj["id"],
        "league_id": league_id,
        "name": obj.get("name") or obj.get("display_name") or "Unknown Team",
        "short_code": obj.get("short_code"),
        "venue_id": venue_id,
        "country": country_name,
    }


def map_coach_from_full_data(obj: Dict[str, Any], team_id: Optional[int]) -> Dict[str, Any]:
    """Map SportMonks coach data to database format (from full coach details).
    
    Args:
        obj: Raw coach data from SportMonks API (full coach details)
        team_id: Internal team ID (not SportMonks ID)
        
    Returns:
        Mapped coach data for database insertion
    """
    # Handle different name fields
    full_name = (
        obj.get("name") or 
        obj.get("display_name") or 
        obj.get("common_name") or 
        f"{obj.get('firstname', '')} {obj.get('lastname', '')}".strip() or
        f"Coach {obj.get('id', 'Unknown')}"
    )
    
    # Extract nationality
    nationality = None
    nationality_data = obj.get("nationality")
    if isinstance(nationality_data, dict):
        nationality = nationality_data.get("name")
    elif isinstance(nationality_data, str):
        nationality = nationality_data
    
    return {
        "sm_id": obj["id"],
        "team_id": team_id,
        "full_name": full_name,
        "nationality": nationality,
    }


def map_player_from_full_data(obj: Dict[str, Any], team_id: Optional[int]) -> Dict[str, Any]:
    """Map SportMonks player data to database format (from full player details).
    
    Args:
        obj: Raw player data from SportMonks API (full player details)
        team_id: Internal team ID (not SportMonks ID)
        
    Returns:
        Mapped player data for database insertion
    """
    # Handle different name fields
    full_name = (
        obj.get("name") or 
        obj.get("display_name") or 
        obj.get("common_name") or 
        f"{obj.get('firstname', '')} {obj.get('lastname', '')}".strip() or
        f"Player {obj.get('id', 'Unknown')}"
    )
    
    # Map position ID to position code
    position_id = obj.get("position_id") or obj.get("detailed_position_id")
    position_map = {
        24: "GK",   # Goalkeeper
        25: "DF",   # Defender  
        26: "MF",   # Midfielder
        27: "FW",   # Forward
    }
    position = position_map.get(position_id, "UNK")
    
    # Extract nationality
    nationality = None
    nationality_data = obj.get("nationality")
    if isinstance(nationality_data, dict):
        nationality = nationality_data.get("name")
    elif isinstance(nationality_data, str):
        nationality = nationality_data
    
    return {
        "sm_id": obj["id"],
        "team_id": team_id,
        "full_name": full_name,
        "position": position,
        "nationality": nationality,
        "date_of_birth": obj.get("date_of_birth"),
    }


def extract_squad_player_ids(team_data: Dict[str, Any]) -> List[int]:
    """Extract player IDs from team squad information.
    
    Args:
        team_data: Team data with squad information
        
    Returns:
        List of player IDs (SportMonks IDs)
    """
    # Check both 'squad' and 'players' keys for squad data
    squad = team_data.get("squad", [])
    if not squad:
        squad = team_data.get("players", [])
    
    player_ids = []
    
    for squad_member in squad:
        # Ensure squad_member is a dictionary and extract player_id
        if isinstance(squad_member, dict):
            player_id = squad_member.get("player_id")
            if player_id:
                player_ids.append(player_id)
    
    return player_ids


def extract_coaching_staff_ids(team_data: Dict[str, Any]) -> List[int]:
    """Extract coach IDs from team coaching staff information.
    
    Args:
        team_data: Team data with coaching staff information
        
    Returns:
        List of coach IDs (SportMonks IDs) for active coaches
    """
    coaching_staff = team_data.get("coaches", [])
    if not coaching_staff:
        coaching_staff = team_data.get("coaching_staff", [])
    
    coach_ids = []
    
    for staff_member in coaching_staff:
        # Ensure staff_member is a dictionary and only include active coaches
        if (isinstance(staff_member, dict) and 
            staff_member.get("active", True)):  # Default to True if not specified
            
            coach_id = staff_member.get("coach_id")
            if coach_id:
                coach_ids.append(coach_id)
    
    return coach_ids


def map_fixture_shell(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Map SportMonks fixture data to basic database format (without includes).
    
    Args:
        obj: Raw fixture data from SportMonks API
        
    Returns:
        Mapped fixture data for database insertion
    """
    # Handle different timestamp formats
    kickoff_ts = obj.get("starting_at") or obj.get("starting_at_timestamp")
    
    # Handle round data
    round_data = obj.get("round")
    round_name = None
    if isinstance(round_data, dict):
        round_name = round_data.get("name")
    elif isinstance(round_data, str):
        round_name = round_data
    
    # Handle referee data
    referee_data = obj.get("referee")
    referee_name = None
    if isinstance(referee_data, dict):
        referee_name = referee_data.get("name") or referee_data.get("common_name")
    elif isinstance(referee_data, str):
        referee_name = referee_data
    
    return {
        "sm_id": obj["id"],
        "league_id": obj.get("league_id"),
        "season_id": obj.get("season_id"),
        "venue_id": obj.get("venue_id"),
        "kickoff_ts": kickoff_ts,
        "status": str(obj.get("state_id", obj.get("status", "UNKNOWN"))),
        "round": round_name,
        "home_team_id": None,  # Set later from participants
        "away_team_id": None,  # Set later from participants
        "referee_name": referee_name,
    }


def map_fixture_complete(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map SportMonks fixture data with complete match information for LLM analysis.
    
    Extracts direct results from participants.meta.winner and scores.CURRENT
    without requiring complex aggregations.
    
    Args:
        obj: Raw fixture data from SportMonks API with includes
        
    Returns:
        Mapped fixture data with computed LLM-ready fields
    """
    # Start with basic fixture data
    fixture_data = map_fixture_shell(obj)
    
    # Extract participants data
    participants = obj.get("participants", [])
    home_team = next((p for p in participants if p.get("meta", {}).get("location") == "home"), None)
    away_team = next((p for p in participants if p.get("meta", {}).get("location") == "away"), None)
    
    # Store SportMonks team IDs (will be resolved to internal IDs later)
    home_team_sm_id = home_team["id"] if home_team else None
    away_team_sm_id = away_team["id"] if away_team else None
    
    # Extract final scores from scores with "CURRENT" description
    scores = obj.get("scores", [])
    home_score = 0
    away_score = 0
    
    for score in scores:
        if score.get("description") == "CURRENT":
            if score.get("score", {}).get("participant") == "home":
                home_score = score.get("score", {}).get("goals", 0)
            elif score.get("score", {}).get("participant") == "away":
                away_score = score.get("score", {}).get("goals", 0)
    
    # Determine result from participants.meta.winner (more reliable than score comparison)
    result = "D"  # Default to draw
    if home_team and home_team.get("meta", {}).get("winner") is True:
        result = "H"
    elif away_team and away_team.get("meta", {}).get("winner") is True:
        result = "A"
    
    # Extract league positions from participants.meta.position
    home_position = None
    away_position = None
    if home_team:
        home_position = home_team.get("meta", {}).get("position")
    if away_team:
        away_position = away_team.get("meta", {}).get("position")
    
    # Extract team statistics
    statistics = obj.get("statistics", [])
    home_stats = {}
    away_stats = {}
    
    for stat in statistics:
        stat_code = stat.get("type", {}).get("code")
        stat_value = stat.get("data", {}).get("value")
        location = stat.get("location")
        
        if stat_code and stat_value is not None:
            if location == "home":
                home_stats[stat_code] = stat_value
            elif location == "away":
                away_stats[stat_code] = stat_value
    
    # Add computed LLM-ready fields
    fixture_data.update({
        # Team IDs - store SportMonks IDs (will be resolved later in backfill)
        "home_team_sm_id": home_team_sm_id,  # Store for later resolution
        "away_team_sm_id": away_team_sm_id,  # Store for later resolution
        
        # Keep the original fields as None for now (will be set after ID resolution)
        "home_team_id": None,
        "away_team_id": None,
        
        # Direct match results 
        "home_goals": home_score,
        "away_goals": away_score,
        "result": result,
        
        # League context
        "home_position": home_position,
        "away_position": away_position,
        
        # Performance metrics from statistics
        "home_possession": home_stats.get("ball-possession"),
        "away_possession": away_stats.get("ball-possession"),
        "home_corners": home_stats.get("corners"),
        "away_corners": away_stats.get("corners"),
        "home_yellow_cards": home_stats.get("yellowcards"),
        "away_yellow_cards": away_stats.get("yellowcards"),
        "home_red_cards": home_stats.get("redcards"),
        "away_red_cards": away_stats.get("redcards"),
    })
    
    return fixture_data


def extract_home_away_from_participants(participants: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[int]]:
    """Extract home and away team IDs from participants data.
    
    Args:
        participants: List of participant data from fixture includes
        
    Returns:
        Tuple of (home_team_id, away_team_id)
    """
    home_team_id = None
    away_team_id = None
    
    for participant in participants or []:
        # Check meta data for location
        meta = participant.get("meta", {})
        location = (meta.get("location") or meta.get("home_away") or "").lower()
        
        # Get team ID
        team_id = participant.get("id") or participant.get("team_id")
        
        if location == "home":
            home_team_id = team_id
        elif location == "away":
            away_team_id = team_id
    
    return home_team_id, away_team_id


def map_event(event: Dict[str, Any], fixture_id: int) -> Dict[str, Any]:
    """Map SportMonks event data to database format.
    
    Args:
        event: Raw event data from SportMonks API
        fixture_id: Internal fixture ID (not SportMonks ID)
        
    Returns:
        Mapped event data for database insertion
    """
    # Extract type code from nested type data if available
    type_data = event.get("type")
    if isinstance(type_data, dict):
        type_code = type_data.get("code") or type_data.get("name") or str(type_data.get("id", "UNKNOWN"))
    else:
        type_code = str(event.get("type_id", "UNKNOWN"))
    
    return {
        "fixture_id": fixture_id,
        "team_id": event.get("participant_id") or event.get("team_id"),
        "player_id": event.get("player_id"),
        "related_player_id": event.get("related_player_id"),
        "minute": event.get("minute"),
        "type_code": type_code,
        "payload": {
            "result": event.get("result"),
            "info": event.get("info"),
            "addition": event.get("addition"),
            "extra_minute": event.get("extra_minute"),
            "rescinded": event.get("rescinded"),
            "raw_type_id": event.get("type_id"),
        },
    }


def map_fixture_team_stat(stat: Dict[str, Any], fixture_id: int, team_id: int) -> Dict[str, Any]:
    """Map SportMonks team statistic to database format with proper value conversion.
    
    Args:
        stat: Raw statistic data from SportMonks API (API v3 structure)
        fixture_id: Internal fixture ID (not SportMonks ID)
        team_id: Internal team ID (not SportMonks ID)
        
    Returns:
        Mapped team statistic data for database insertion
    """
    # Extract stat code from nested type data if available
    type_data = stat.get("type")
    if isinstance(type_data, dict):
        stat_code = type_data.get("code") or type_data.get("name") or str(type_data.get("id", "UNKNOWN"))
    else:
        stat_code = str(stat.get("type_id", "UNKNOWN"))
    
    # Extract and convert value from data object (API v3 structure)
    raw_value = None
    data = stat.get("data")
    if isinstance(data, dict):
        raw_value = data.get("value")
    else:
        raw_value = stat.get("value")  # Fallback
    
    # Convert to numeric value
    numeric_value = _convert_to_numeric(raw_value)
    
    # Log conversion issues for debugging
    if raw_value is not None and numeric_value is None:
        logger.debug(f"Team stat conversion failed: {stat_code} = '{raw_value}' (type: {type(raw_value)})")
    
    return {
        "fixture_id": fixture_id,
        "team_id": team_id,
        "stat_code": stat_code,
        "value": numeric_value,
    }


def map_player_match_stat(stat: Dict[str, Any], fixture_id: int, player_id: int) -> Dict[str, Any]:
    """Map SportMonks player statistic to database format with proper value conversion.
    
    Args:
        stat: Raw statistic data from SportMonks API (from lineups.details.type)
        fixture_id: Internal fixture ID (not SportMonks ID)
        player_id: Internal player ID (not SportMonks ID)
        
    Returns:
        Mapped player statistic data for database insertion
    """
    # Extract stat code from nested type data if available
    type_data = stat.get("type")
    if isinstance(type_data, dict):
        stat_code = type_data.get("code") or type_data.get("name") or str(type_data.get("id", "UNKNOWN"))
    else:
        stat_code = str(stat.get("type_id", "UNKNOWN"))
    
    # Extract and convert value from data object (API v3 structure)
    raw_value = None
    data = stat.get("data")
    if isinstance(data, dict):
        raw_value = data.get("value")
    else:
        raw_value = stat.get("value")  # Fallback
    
    # Convert to numeric value
    numeric_value = _convert_to_numeric(raw_value)
    
    # Log conversion issues for debugging
    if raw_value is not None and numeric_value is None:
        logger.debug(f"Player stat conversion failed: {stat_code} = '{raw_value}' (type: {type(raw_value)})")
    
    return {
        "fixture_id": fixture_id,
        "player_id": player_id,
        "stat_code": stat_code,
        "value": numeric_value,
    }