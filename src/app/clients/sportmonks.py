"""SportMonks API client optimized for LLM data extraction."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Optional

import pendulum

from app.config import settings
from app.logging import get_logger
from app.utils.http import HttpClient

logger = get_logger("sportmonks")

# SportMonks API v3 base URL
BASE_URL = "https://api.sportmonks.com/v3/football"


def _checksum(payload: Dict[str, Any]) -> str:
    """Generate checksum for payload to detect changes."""
    return hashlib.sha256(repr(payload).encode()).hexdigest()


class SportMonksClient:
    """
    SportMonks API v3 client optimized for LLM data extraction.

    Focuses on finished matches with direct result extraction from:
    - participants.meta.winner for win/loss
    - scores.CURRENT for final scores
    - statistics for team performance
    - lineups.details for player stats
    """

    def __init__(self, token: Optional[str] = None) -> None:
        """Initialize SportMonks client.

        Args:
            token: API token, defaults to settings.SPORTMONKS_API_TOKEN
        """
        self.token = token or settings.SPORTMONKS_API_TOKEN
        self.http = HttpClient(
            base_url=BASE_URL,
            headers={"Accept": "application/json"},
            timeout=settings.HTTP_TIMEOUT,
        )
        logger.info("Initialized SportMonks client for LLM data extraction")

    def close(self) -> None:
        """Close the HTTP client."""
        self.http.close()

    def __enter__(self) -> SportMonksClient:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def _params(self, **kwargs: Any) -> Dict[str, Any]:
        """Build request parameters with API token."""
        params = {k: v for k, v in kwargs.items() if v is not None}
        params["api_token"] = self.token
        return params

    # ---------- Generic pagination helpers ----------

    def _list_paginated(
        self,
        path: str,
        params: Dict[str, Any],
        per_page: int = 50,
    ) -> Iterable[Dict[str, Any]]:
        """
        Paginate through standard API endpoints.

        Args:
            path: API endpoint path
            params: Request parameters
            per_page: Items per page (max 50 per SportMonks docs)

        Yields:
            Individual items from paginated response
        """
        if not (1 <= per_page <= 50):
            raise ValueError(
                "per_page must be between 1 and 50 per SportMonks API limits"
            )

        page = 1
        total_items = 0

        while True:
            request_params = {**params, "per_page": per_page, "page": page}

            logger.debug(f"Fetching {path} page {page} (per_page={per_page})")
            data = self.http.get(path, params=request_params)

            # Extract items from response
            items = data.get("data", [])
            if not items:
                break

            yield from items
            total_items += len(items)

            # Check pagination info
            pagination = data.get("pagination") or data.get("meta", {}).get(
                "pagination", {}
            )
            has_more = pagination.get("has_more", False)

            if not has_more:
                break

            page += 1

        logger.info(f"Fetched {total_items} items from {path}")

    def _list_populate(
        self,
        path: str,
        params: Dict[str, Any],
    ) -> Iterable[Dict[str, Any]]:
        """
        Use populate filter for bulk fetching (1000/page, includes disabled).

        Args:
            path: API endpoint path
            params: Request parameters

        Yields:
            Individual items from paginated response
        """
        page = 1
        total_items = 0

        while True:
            request_params = {
                **params,
                "filters": "populate",
                "per_page": 1000,
                "page": page,
            }

            logger.debug(f"Fetching {path} page {page} with populate filter")
            data = self.http.get(path, params=request_params)

            items = data.get("data", [])
            if not items:
                break

            yield from items
            total_items += len(items)

            # Check pagination
            pagination = data.get("pagination") or data.get("meta", {}).get(
                "pagination", {}
            )
            has_more = pagination.get("has_more", False)

            if not has_more:
                break

            page += 1

        logger.info(f"Fetched {total_items} items from {path} using populate")

    # ---------- Discovery and metadata endpoints ----------

    def leagues_search_by_name(
        self, name: str, per_page: int = 50
    ) -> List[Dict[str, Any]]:
        """Search leagues by name.

        Args:
            name: League name to search for
            per_page: Items per page (max 50)

        Returns:
            List of matching leagues
        """
        params = self._params(search=name)
        return list(self._list_paginated(f"/leagues/search/{name}", params, per_page))

    def leagues_all(self, per_page: int = 50) -> List[Dict[str, Any]]:
        """Get all leagues.

        Args:
            per_page: Items per page (max 50)

        Returns:
            List of all leagues
        """
        params = self._params()
        return list(self._list_paginated("/leagues", params, per_page))

    def league_by_id_with_current_season(self, league_id: int) -> Dict[str, Any]:
        """Get league with current season information.

        Args:
            league_id: SportMonks league ID

        Returns:
            League data with current season
        """
        params = self._params(include="currentSeason")
        return self.http.get(f"/leagues/{league_id}", params=params)

    def seasons_by_league(
        self, league_id: int, per_page: int = 50
    ) -> List[Dict[str, Any]]:
        """Get seasons for a specific league.

        Args:
            league_id: SportMonks league ID
            per_page: Items per page (max 50)

        Returns:
            List of seasons for the league
        """
        params = self._params(filters=f"seasonLeagues:{league_id}")
        return list(self._list_paginated("/seasons", params, per_page))

    def get_current_season_for_league(self, league_id: int) -> Optional[Dict[str, Any]]:
        """Get the current/active season for a specific league.

        Args:
            league_id: SportMonks league ID

        Returns:
            Current season data or None if not found
        """
        try:
            # Method 1: Use league endpoint with currentSeason include
            league_data = self.league_by_id_with_current_season(league_id)
            current_season = league_data.get("data", {}).get("current_season")
            if current_season:
                return current_season

            # Method 2: Fallback - get all seasons and find the current one
            seasons = self.seasons_by_league(league_id)
            for season in seasons:
                if season.get("is_current", False):
                    return season

            # Method 3: Last fallback - get the most recent season
            if seasons:
                seasons_sorted = sorted(
                    seasons, key=lambda s: s.get("id", 0), reverse=True
                )
                return seasons_sorted[0]

            return None

        except Exception as e:
            logger.error(f"Failed to get current season for league {league_id}: {e}")
            return None

    def teams_by_season(
        self, season_id: int, include_details: bool = True
    ) -> List[Dict[str, Any]]:
        """Get teams for a specific season with optional detailed data.

        Args:
            season_id: SportMonks season ID
            include_details: Whether to include venue, coaches, players

        Returns:
            List of teams in the season
        """
        params = self._params()

        # Get basic team data first
        teams = list(
            self._list_paginated(f"/teams/seasons/{season_id}", params, per_page=50)
        )

        if not include_details:
            return teams

        # Enrich each team with detailed data
        enriched_teams = []
        for team in teams:
            team_id = team["id"]

            try:
                # Get team with venue details
                team_with_venue = self.team_by_id_with_venue(team_id)
                team_data = team_with_venue.get("data", team)

                # Get squad data using season-specific endpoint for precise data
                squad_data = self.team_squad_by_id(team_id, season_id)
                team_data["squad"] = squad_data  # Store squad records

                # Get coaching staff data using team coaches include
                coaches_data = self.team_coaches_by_id(team_id)
                team_data["coaches"] = coaches_data  # Store coaching staff records

                enriched_teams.append(team_data)

            except Exception as e:
                logger.warning(f"Failed to enrich team {team_id}: {e}")
                enriched_teams.append(team)

        return enriched_teams

    def team_by_id_with_venue(self, team_id: int) -> Dict[str, Any]:
        """Get team with venue information.

        Args:
            team_id: SportMonks team ID

        Returns:
            Team data with venue details
        """
        params = self._params(include="venue")
        return self.http.get(f"/teams/{team_id}", params=params)

    def team_squad_by_id(
        self, team_id: int, season_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get team squad using the dedicated squad endpoint.

        Args:
            team_id: SportMonks team ID
            season_id: Optional season ID for historical squads

        Returns:
            List of squad records
        """
        params = self._params()

        if season_id:
            # Use season-specific squad endpoint for precise data
            path = f"/squads/seasons/{season_id}/teams/{team_id}"
        else:
            # Use current squad endpoint
            path = f"/squads/teams/{team_id}"

        data = self.http.get(path, params=params)
        return data.get("data", [])

    def team_coaches_by_id(self, team_id: int) -> List[Dict[str, Any]]:
        """Get team coaching staff using team endpoint with coaches include.

        Args:
            team_id: SportMonks team ID

        Returns:
            List of coaching staff records
        """
        params = self._params(include="coaches")
        data = self.http.get(f"/teams/{team_id}", params=params)
        team_data = data.get("data", {})
        return team_data.get("coaches", [])

    def player_by_id(self, player_id: int) -> Dict[str, Any]:
        """Get detailed player information by ID.

        Args:
            player_id: SportMonks player ID

        Returns:
            Player details
        """
        params = self._params()
        return self.http.get(f"/players/{player_id}", params=params)

    def players_by_ids(self, player_ids: List[int]) -> List[Dict[str, Any]]:
        """Get multiple players by IDs.

        Args:
            player_ids: List of SportMonks player IDs

        Returns:
            List of player details
        """
        if not player_ids:
            return []

        all_players = []

        # Fetch players individually (no multi endpoint available for players)
        for i, player_id in enumerate(player_ids):
            try:
                player_data = self.player_by_id(player_id)
                player = player_data.get("data")
                if player:
                    all_players.append(player)

                # Log progress for large batches
                if (i + 1) % 50 == 0:
                    logger.info(f"Fetched {i + 1}/{len(player_ids)} players")

            except Exception as e:
                logger.warning(f"Failed to fetch player {player_id}: {e}")

        logger.info(f"Fetched {len(all_players)} player details")
        return all_players

    def coach_by_id(self, coach_id: int) -> Dict[str, Any]:
        """Get detailed coach information by ID.

        Args:
            coach_id: SportMonks coach ID

        Returns:
            Coach details
        """
        params = self._params()
        return self.http.get(f"/coaches/{coach_id}", params=params)

    def coaches_by_ids(self, coach_ids: List[int]) -> List[Dict[str, Any]]:
        """Get multiple coaches by IDs.

        Args:
            coach_ids: List of SportMonks coach IDs

        Returns:
            List of coach details
        """
        if not coach_ids:
            return []

        all_coaches = []

        # Fetch coaches individually since there's no multi endpoint for coaches
        for coach_id in coach_ids:
            try:
                coach_data = self.coach_by_id(coach_id)
                coach = coach_data.get("data")
                if coach:
                    all_coaches.append(coach)
            except Exception as e:
                logger.warning(f"Failed to fetch coach {coach_id}: {e}")

        logger.info(f"Fetched {len(all_coaches)} coach details")
        return all_coaches

    # ---------- Fixture endpoints optimized for LLM data ----------

    def fixtures_between(
        self,
        start_date: str,
        end_date: str,
        per_page: int = 50,
        populate: bool = False,
        include_details: bool = False,
        finished_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get fixtures between two dates optimized for LLM analysis.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            per_page: Items per page (ignored if populate=True)
            populate: Use populate filter for bulk fetching
            include_details: Include detailed match data with LLM-optimized includes
            finished_only: Only return finished matches (state_id = 5)

        Returns:
            List of fixtures optimized for LLM analysis
        """
        params = self._params()

        if include_details and not populate:
            
            params["include"] = (
                "participants;events.type;statistics.type;scores;lineups.details.type"
            )

        path = f"/fixtures/between/{start_date}/{end_date}"

        if populate:
            fixtures = list(self._list_populate(path, params))
        else:
            fixtures = list(self._list_paginated(path, params, per_page))

        # Filter to finished matches only if requested
        if finished_only:
            fixtures = [f for f in fixtures if f.get("state_id") == 5]
            logger.info(f"Filtered to {len(fixtures)} finished matches")

        return fixtures

    def fixtures_multi(
        self,
        fixture_ids: List[int],
        include: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get multiple fixtures by IDs with LLM-optimized includes.

        Args:
            fixture_ids: List of SportMonks fixture IDs
            include: Custom includes or None for LLM-optimized defaults

        Returns:
            List of detailed fixture data
        """
        if not fixture_ids:
            return []

        # Default to LLM-optimized includes
        if include is None:
            include = (
                "participants;events.type;statistics.type;scores;lineups.details.type"
            )

        # Process in chunks to avoid URL length limits
        chunk_size = 200
        all_fixtures = []

        for i in range(0, len(fixture_ids), chunk_size):
            chunk = fixture_ids[i : i + chunk_size]
            params = self._params()

            if include:
                params["include"] = include

            path = f"/fixtures/multi/{','.join(map(str, chunk))}"

            logger.debug(f"Fetching {len(chunk)} fixtures with LLM includes: {include}")
            data = self.http.get(path, params=params)

            fixtures = data.get("data", [])
            all_fixtures.extend(fixtures)

        logger.info(f"Fetched {len(all_fixtures)} fixtures with LLM-optimized data")
        return all_fixtures

    def get_team_recent_form(
        self,
        team_id: int,
        matches_count: int = 10,
        finished_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get team's recent matches for form analysis.

        Args:
            team_id: SportMonks team ID
            matches_count: Number of recent matches to fetch
            finished_only: Only include finished matches

        Returns:
            List of recent fixtures for the team
        """
        # Get fixtures from last 4 months to ensure we get enough matches
        end_date = pendulum.now().to_date_string()
        start_date = pendulum.now().subtract(days=120).to_date_string()

        logger.info(
            f"Fetching recent form for team {team_id} ({matches_count} matches)"
        )

        # Get all fixtures in date range with detailed data
        fixtures = self.fixtures_between(
            start_date, end_date, include_details=True, finished_only=finished_only
        )

        # Filter to matches involving this team
        team_fixtures = [
            f
            for f in fixtures
            if any(p.get("id") == team_id for p in f.get("participants", []))
        ]

        # Sort by date and take most recent
        team_fixtures.sort(key=lambda x: x.get("starting_at", ""), reverse=True)
        recent_form = team_fixtures[:matches_count]

        logger.info(f"Found {len(recent_form)} recent matches for team {team_id}")
        return recent_form

    def get_upcoming_fixtures(
        self,
        days_ahead: int = 7,
        league_ids: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming fixtures for LLM prediction.

        Args:
            days_ahead: Number of days ahead to fetch
            league_ids: Optional list of league IDs to filter

        Returns:
            List of upcoming fixtures
        """
        start_date = pendulum.now().to_date_string()
        end_date = pendulum.now().add(days=days_ahead).to_date_string()

        logger.info(f"Fetching upcoming fixtures for next {days_ahead} days")

        # Get upcoming fixtures (not finished)
        fixtures = self.fixtures_between(start_date, end_date, include_details=True)

        # Filter to scheduled matches only (state_id = 1)
        upcoming = [f for f in fixtures if f.get("state_id") == 1]

        # Filter by leagues if specified
        if league_ids:
            upcoming = [f for f in upcoming if f.get("league_id") in league_ids]

        logger.info(f"Found {len(upcoming)} upcoming fixtures")
        return upcoming

    def latest_updated_fixtures(self) -> List[Dict[str, Any]]:
        """
        Get fixtures updated in the last ~10 seconds.

        Returns:
            List of recently updated fixtures
        """
        params = self._params()
        data = self.http.get("/fixtures/latest", params=params)
        return data.get("data", [])

    # ---------- Team and player endpoints ----------

    def team_by_id_with_statistics(
        self,
        team_id: int,
        season_id: int,
        stat_type_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Get team with statistics for a specific season.

        Args:
            team_id: SportMonks team ID
            season_id: SportMonks season ID
            stat_type_ids: Optional list of statistic type IDs to filter

        Returns:
            Team data with statistics
        """
        filters = [f"teamStatisticSeasons:{season_id}"]
        if stat_type_ids:
            filters.append(
                f"teamStatisticDetailTypes:{','.join(map(str, stat_type_ids))}"
            )

        params = self._params(
            include="statistics",
            filters=";".join(filters),
        )

        return self.http.get(f"/teams/{team_id}", params=params)

    def player_by_id_with_statistics(
        self,
        player_id: int,
        season_id: int,
        stat_type_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Get player with statistics for a specific season.

        Args:
            player_id: SportMonks player ID
            season_id: SportMonks season ID
            stat_type_ids: Optional list of statistic type IDs to filter

        Returns:
            Player data with statistics
        """
        filters = [f"playerStatisticSeasons:{season_id}"]
        if stat_type_ids:
            filters.append(
                f"playerStatisticDetailTypes:{','.join(map(str, stat_type_ids))}"
            )

        params = self._params(
            include="statistics",
            filters=";".join(filters),
        )

        return self.http.get(f"/players/{player_id}", params=params)

    # ---------- Utility methods ----------

    @staticmethod
    def to_iso_date(dt: Any) -> str:
        """Convert datetime to ISO date string.

        Args:
            dt: Datetime object or string

        Returns:
            Date in YYYY-MM-DD format
        """
        if isinstance(dt, str):
            return pendulum.parse(dt).to_date_string()
        return pendulum.instance(dt).to_date_string()

    @staticmethod
    def checksum_payload(payload: Dict[str, Any]) -> str:
        """Generate checksum for payload.

        Args:
            payload: Data to checksum

        Returns:
            SHA256 checksum
        """
        return _checksum(payload)
