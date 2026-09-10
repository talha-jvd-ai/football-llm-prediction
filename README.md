# Football Data Ingestion Pipeline (LLM-Optimized)

**Goal**: Continuously ingest & normalize SportMonks Football data for Premier League, La Liga, and Ligue 1 into **Supabase Postgres** with **LLM-ready computed fields** for match prediction and analysis.

**Stack**: Python 3.11+ (< 3.13), Poetry, Celery + Redis, httpx (HTTP/2), SQLAlchemy 2.0 + Alembic, Supabase Postgres, Typer CLIs, Pendulum for timezone-aware dates.

## What It Does

- Discovers leagues by name (`LEAGUE_NAMES`) and resolves their **current seasons** via the SportMonks API
- Syncs teams, venues, coaches, and players metadata for each league/season
- Fetches **finished fixtures** with direct result extraction (scores, win/loss, possession, corners, cards, league positions)
- Fetches **upcoming fixtures** for the prediction pipeline
- Stores **fixture events** (goals, cards, subs), **team fixture stats**, and **player match stats** for detailed analysis
- Archives every raw SportMonks payload in `football.source_raw` for audit/replay, and tracks incremental sync state in `football.etl_cursor`
- **LLM-optimized**: pre-computed fields on `football.fixture` eliminate complex joins/aggregations at query time

## Key Features (LLM-Ready)

✅ **Direct Result Extraction**: Final scores and win/loss derived from SportMonks `participants.meta.winner` and `scores.CURRENT`
✅ **Computed Fields**: `home_goals`, `away_goals`, `result` (`H`/`A`/`D`), `home_possession`/`away_possession`, `home_corners`/`away_corners`, `home_yellow_cards`/`away_yellow_cards`, `home_red_cards`/`away_red_cards`
✅ **League Context**: `home_position`/`away_position` capture standings at match time for strength-of-schedule analysis
✅ **Fast Queries**: no real-time aggregation needed when building LLM prompts — read straight off `football.fixture`
✅ **Finished vs Upcoming**: separate ingestion paths — finished fixtures pull full detail (events/stats/lineups), upcoming fixtures stay lightweight for scheduling/prediction
✅ **Idempotent Upserts**: all writes go through `bulk_upsert` keyed on SportMonks IDs / natural composite keys, so re-running ingestion is always safe

## Project Structure

```
football-llm-prediction/
├── pyproject.toml             # Poetry dependencies, ruff & mypy config
├── README.md
├── .gitignore
├── alembic.ini                 # Alembic configuration
├── alembic/                    # Database migrations
│   ├── env.py
│   └── versions/
│       ├── 0001_initial.py           # Base schema (league, season, team, fixture, ...)
│       └── 0002_llm_optimization.py  # Adds LLM-computed columns to fixture
├── docker/
│   └── docker-compose.redis.yml      # Local Redis broker/backend for Celery
└── src/
    └── app/
        ├── __init__.py
        ├── logging.py             # Logging configuration (structured, LOG_LEVEL-driven)
        ├── config.py              # Pydantic Settings loaded from environment / .env
        ├── worker.py              # Celery app, beat schedule, failure handlers
        ├── utils/
        │   ├── __init__.py
        │   └── http.py            # httpx client wrapper with retry/backoff (tenacity)
        ├── db/
        │   ├── __init__.py
        │   ├── session.py         # SQLAlchemy engine & session factory
        │   └── models.py          # ORM models (League, Season, Team, Fixture, ...)
        ├── clients/
        │   ├── __init__.py
        │   └── sportmonks.py      # SportMonks API client (pagination, includes, checksums)
        ├── ingest/
        │   ├── __init__.py
        │   ├── tasks.py           # Celery tasks (metadata sync, finished/upcoming fixtures, cleanup)
        │   ├── mappers.py         # SportMonks JSON → ORM-ready dict mappers
        │   └── upsert.py          # bulk_upsert / get_or_create_mapping / ETL cursor helpers
        └── scripts/
            ├── bootstrap.py        # Typer CLI: initial league/season/metadata sync + connection tests
            └── backfill.py         # Typer CLI: historical/upcoming fixture backfill + data verification
```

## Quick Start

### Prerequisites

- Python 3.11 or 3.12
- Redis (use `docker/docker-compose.redis.yml`)
- Supabase Postgres connection string (Service Role)
- SportMonks API token

### 1. Install Dependencies

```bash
# Install Poetry if you haven't already
curl -sSL https://install.python-poetry.org | python3 -

# Install project dependencies (including dev tools: pytest, ruff, mypy)
poetry install
```

### 2. Configure Environment

Create a `.env` file in the project root (see [Environment Variables](#environment-variables) below for all options). At minimum you need `SPORTMONKS_API_TOKEN` and `SUPABASE_DB_URL` — both are required and the app will fail to start without them.

### 3. Start Redis

```bash
docker compose -f docker/docker-compose.redis.yml up -d
```

### 4. Initialize the Database

```bash
# Applies 0001_initial.py then 0002_llm_optimization.py
poetry run alembic upgrade head
```

### 5. Test Connections (optional but recommended)

```bash
poetry run python -m app.scripts.bootstrap test-connection
```

Checks the database, SportMonks API, and Redis connections independently and prints ✓/❌ for each.

### 6. Bootstrap Metadata

```bash
# Discover leagues/seasons and sync teams/venues/coaches/players
poetry run python -m app.scripts.bootstrap main

# Optionally target specific leagues, or run async via Celery
poetry run python -m app.scripts.bootstrap main --leagues "Premier League,La Liga,Ligue 1"
poetry run python -m app.scripts.bootstrap main --async
```

### 7. Backfill LLM-Optimized Data

```bash
# Backfill finished fixtures with computed LLM fields (historical analysis)
poetry run python -m app.scripts.backfill finished-fixtures --days 30

# Backfill upcoming fixtures (for prediction)
poetry run python -m app.scripts.backfill upcoming-fixtures --days 21

# Verify LLM data quality
poetry run python -m app.scripts.backfill verify-llm-data
```

### 8. Start Workers & Scheduler

```bash
# Terminal 1: Celery worker
poetry run celery -A app.worker.app worker --loglevel=INFO

# Terminal 2: Celery Beat scheduler (drives the recurring sync tasks)
poetry run celery -A app.worker.app beat --loglevel=INFO
```

## Environment Variables

The app reads settings via `pydantic-settings` (`src/app/config.py`), from process environment or a `.env` file in the project root.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `SPORTMONKS_API_TOKEN` | ✅ | — | SportMonks API token |
| `SUPABASE_DB_URL` | ✅ | — | Supabase/Postgres connection URL, e.g. `postgresql+psycopg://postgres.USER:PASS@HOST:PORT/postgres` |
| `REDIS_URL` | | `redis://localhost:6379/0` | Redis broker/result backend URL for Celery |
| `LEAGUE_NAMES` | | `Premier League,La Liga,Ligue 1` | Comma-separated league names to monitor (matched by name against SportMonks) |
| `FIXTURE_HORIZON_DAYS` | | `21` | Days ahead to fetch upcoming fixtures (1–100) |
| `TIMEZONE` | | `UTC` | Timezone used for scheduling and date math |
| `LOG_LEVEL` | | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `HTTP_TIMEOUT` | | `30.0` | SportMonks HTTP request timeout (seconds) |
| `MAX_RETRIES` | | `5` | Max HTTP retry attempts (tenacity-backed) |
| `RETRY_DELAY` | | `1.0` | Base retry backoff delay (seconds) |

Example `.env`:

```bash
SPORTMONKS_API_TOKEN=your_sportmonks_api_token_here
SUPABASE_DB_URL=postgresql+psycopg://postgres.USER:PASS@HOST:PORT/postgres
REDIS_URL=redis://localhost:6379/0
LEAGUE_NAMES=Premier League,La Liga,Ligue 1
FIXTURE_HORIZON_DAYS=21
TIMEZONE=UTC
LOG_LEVEL=INFO
```

## LLM-Optimized Data Pipeline

### Scheduled Tasks (Celery Beat)

Defined in `src/app/worker.py`, these run automatically once beat + a worker are up:

| Beat entry | Task | Schedule | Notes |
| --- | --- | --- | --- |
| `daily_llm_data_sync` | `ingest.daily_llm_data_sync` | 02:00 UTC daily | Full sync: metadata + finished + upcoming fixtures |
| `sync_upcoming_fixtures_6h` | `ingest.sync_upcoming_fixtures` | every 6 hours | Refreshes the prediction horizon (`FIXTURE_HORIZON_DAYS`) |
| `sync_finished_fixtures_daily` | `ingest.sync_finished_fixtures` | 03:30 UTC daily | Re-syncs the last 30 days of finished fixtures |

### Task Reference (`src/app/ingest/tasks.py`)

All tasks are registered on the `ingest.*` namespace and routed to the `default` queue:

- `ingest.sync_metadata` — resolves each configured league's current season and syncs teams/venues/coaches/players
- `ingest.sync_finished_fixtures(horizon_days=None)` — pulls finished fixtures with full detail (events, stats, lineups) and computes LLM fields
- `ingest.sync_upcoming_fixtures(horizon_days=None)` — pulls scheduled fixtures for the prediction horizon
- `ingest.hydrate_fixture(fixture_id)` — fetches and upserts full detail for a single fixture on demand
- `ingest.cleanup_old_fixtures(days_to_keep=365)` — prunes fixtures older than the retention window
- `ingest.daily_llm_data_sync` — orchestrates metadata + finished + upcoming sync in one run

### Data Flow

1. **Bootstrap**: discover leagues/seasons, sync metadata (`sync_metadata` / `bootstrap.py`)
2. **Finished Fixtures**: extract direct results from SportMonks (`participants.meta.winner`, `scores.CURRENT`), plus events/team-stats/player-stats
3. **Upcoming Fixtures**: fetch scheduled matches (state `1`) for prediction, lightweight (no detail includes)
4. **Computed Fields**: LLM-ready columns are pre-calculated during mapping (`ingest/mappers.py`) — no aggregation needed downstream
5. **Storage**: normalized rows land in `football.*` tables via idempotent upserts (`ingest/upsert.py`), keyed on SportMonks IDs

## LLM-Ready Database Schema

All tables live in the `football` Postgres schema (see `src/app/db/models.py`).

### Core Table: `football.fixture`

Base columns: `sm_id`, `league_id`, `season_id`, `venue_id`, `home_team_id`, `away_team_id`, `referee_name`, `kickoff_ts`, `status`, `round`.

LLM-computed columns:

- `home_goals`, `away_goals` — final scores
- `result` — `'H'` / `'A'` / `'D'` (home win / away win / draw)
- `home_position`, `away_position` — league standings at match time
- `home_possession`, `away_possession` — ball possession %
- `home_corners`, `away_corners` — corner kicks
- `home_yellow_cards`, `away_yellow_cards` — yellow cards
- `home_red_cards`, `away_red_cards` — red cards

Convenience properties on the `Fixture` model: `total_goals`, `goal_difference`, `is_finished` (`status == "5"`), `home_win`, `away_win`, `draw`.

### Supporting Tables

- `football.league`, `football.season`, `football.team` — core metadata (SportMonks IDs + names)
- `football.venue`, `football.coach`, `football.player` — contextual entities
- `football.fixture_event` — match events: `type_code`, `minute`, `team_id`, `player_id`, `related_player_id`, raw `payload` JSON
- `football.fixture_team_stat` — keyed on `(fixture_id, team_id, stat_code)`, e.g. shots, possession
- `football.player_match_stat` — keyed on `(fixture_id, player_id, stat_code)`, e.g. minutes, passes, rating
- `football.source_raw` — raw SportMonks payloads with checksum, for audit/replay
- `football.etl_cursor` — per-resource cursor state for incremental syncs

## LLM Query Examples

### Team Recent Form
```sql
SELECT
    kickoff_ts,
    CASE WHEN home_team_id = ? THEN 'home' ELSE 'away' END as venue,
    CASE WHEN home_team_id = ? THEN away_team_id ELSE home_team_id END as opponent_id,
    CASE WHEN home_team_id = ? THEN home_goals ELSE away_goals END as goals_scored,
    CASE WHEN home_team_id = ? THEN away_goals ELSE home_goals END as goals_conceded,
    result
FROM football.fixture
WHERE (home_team_id = ? OR away_team_id = ?)
    AND status = '5'  -- Finished matches
ORDER BY kickoff_ts DESC
LIMIT 5;
```

### Head-to-Head Analysis
```sql
SELECT
    kickoff_ts,
    home_goals,
    away_goals,
    result,
    home_possession,
    away_possession
FROM football.fixture
WHERE ((home_team_id = ? AND away_team_id = ?)
    OR (home_team_id = ? AND away_team_id = ?))
    AND status = '5'
ORDER BY kickoff_ts DESC;
```

### Sample LLM Input
```json
{
  "upcoming_match": {
    "home_team": "Manchester United",
    "away_team": "Liverpool",
    "kickoff": "2025-08-25 16:30:00"
  },
  "recent_form": {
    "manchester_united": {
      "last_5_results": ["W", "D", "L", "W", "W"],
      "goals_scored": [2, 1, 0, 3, 1],
      "goals_conceded": [1, 1, 2, 1, 0],
      "avg_possession": 58.4
    }
  }
}
```

## SportMonks API Client (`src/app/clients/sportmonks.py`)

`SportMonksClient` is a context-manager wrapper around `httpx` (HTTP/2, retry/backoff via `tenacity`, configurable timeout/retries). Notable methods:

- `leagues_search_by_name(name)`, `leagues_all(per_page)`, `league_by_id_with_current_season(league_id)`
- `seasons_by_league(league_id)`, `get_current_season_for_league(league_id)`
- `teams_by_season(season_id)`, `team_by_id_with_venue(team_id)`, `team_squad_by_id(team_id)`, `team_coaches_by_id(team_id)`, `team_by_id_with_statistics(...)`
- `player_by_id(player_id)`, `players_by_ids(ids)`, `player_by_id_with_statistics(...)`
- `coach_by_id(coach_id)`, `coaches_by_ids(ids)`
- `fixtures_between(start, end, include_details, finished_only)`, `fixtures_multi(...)`, `latest_updated_fixtures()`
- `get_upcoming_fixtures(days_ahead, league_ids)`, `get_team_recent_form(...)`

**LLM-Optimized Includes**: `participants;events.type;statistics.type;scores;lineups.details.type`

- **Strategic**: direct extraction from `participants.meta.winner` and `scores.CURRENT` avoids re-deriving results from raw event streams
- **Efficient**: finished fixtures request full detail includes; upcoming fixtures skip them entirely
- Every response is checksummed and archived to `football.source_raw` for traceability

## Manual Operations

### Backfill Commands (`app.scripts.backfill`)

Run bootstrap first — backfill resolves foreign keys against metadata already in the database.

```bash
# Finished fixtures (historical analysis)
poetry run python -m app.scripts.backfill finished-fixtures --days 60
poetry run python -m app.scripts.backfill finished-fixtures --days 7 --no-details
poetry run python -m app.scripts.backfill finished-fixtures --days 30 --leagues "Premier League"

# Upcoming fixtures (prediction)
poetry run python -m app.scripts.backfill upcoming-fixtures --days 21

# Data quality verification (prints a full LLM-readiness report)
poetry run python -m app.scripts.backfill verify-llm-data

# Clean rebuild (deletes existing fixture data, cascades to events/stats)
poetry run python -m app.scripts.backfill clean-and-rebuild --days 30 --confirm
```

### Bootstrap Commands (`app.scripts.bootstrap`)

```bash
poetry run python -m app.scripts.bootstrap main
poetry run python -m app.scripts.bootstrap main --leagues "Premier League,La Liga,Ligue 1"
poetry run python -m app.scripts.bootstrap main --async   # submit via Celery instead of running inline
poetry run python -m app.scripts.bootstrap test-connection
```

### Trigger Celery Tasks Directly

```bash
# Sync all LLM data
poetry run celery -A app.worker.app call ingest.daily_llm_data_sync

# Sync only finished fixtures
poetry run celery -A app.worker.app call ingest.sync_finished_fixtures

# Sync only upcoming fixtures
poetry run celery -A app.worker.app call ingest.sync_upcoming_fixtures

# Hydrate a single fixture by internal ID
poetry run celery -A app.worker.app call ingest.hydrate_fixture --args='[12345]'

# Prune fixtures older than the retention window
poetry run celery -A app.worker.app call ingest.cleanup_old_fixtures
```

### Monitor Tasks

```bash
poetry run celery -A app.worker.app inspect active
poetry run celery -A app.worker.app inspect scheduled
poetry run celery -A app.worker.app events
```

## Database Migrations

Migrations live under `alembic/versions/` and are applied with Alembic (config in `alembic.ini`, environment setup in `alembic/env.py`):

- `0001_initial.py` — base `football` schema: `league`, `season`, `venue`, `team`, `coach`, `player`, `fixture`, `fixture_event`, `fixture_team_stat`, `player_match_stat`, `source_raw`, `etl_cursor`
- `0002_llm_optimization.py` — adds the LLM-computed columns to `football.fixture` (`home_goals`, `away_goals`, `result`, positions, possession, corners, cards)

```bash
poetry run alembic upgrade head        # apply all migrations
poetry run alembic downgrade -1        # roll back one revision
poetry run alembic revision -m "..."   # create a new revision
```

## Development

```bash
poetry run pytest              # run tests (pytest + pytest-httpx for mocked HTTP)
poetry run ruff check .        # lint (see [tool.ruff] in pyproject.toml for enabled rule sets)
poetry run mypy src            # type-check (strict: disallows untyped/incomplete defs)
```

## Troubleshooting

### Common Issues

1. **Redis Connection Error**
   - Ensure Redis is running: `docker compose -f docker/docker-compose.redis.yml up -d`

2. **Database Connection Error**
   - Verify `SUPABASE_DB_URL` in `.env`
   - Ensure the database exists and migrations are applied (`poetry run alembic upgrade head`)

3. **SportMonks API Errors**
   - Check `SPORTMONKS_API_TOKEN` is valid
   - Watch for rate limiting (HTTP 429) — the client retries with backoff up to `MAX_RETRIES`

4. **Foreign Key Violations**
   - Run bootstrap (`app.scripts.bootstrap main`) before any backfill — fixtures resolve league/season/venue/team IDs against existing metadata

### Logs

```bash
# Worker logs
poetry run celery -A app.worker.app worker --loglevel=DEBUG

# Beat scheduler logs
poetry run celery -A app.worker.app beat --loglevel=DEBUG
```

## Data Quality Verification

```bash
poetry run python -m app.scripts.backfill verify-llm-data
```

Reports, per finished fixture: % with computed results, % with final scores, % with possession data, plus a sample LLM-ready match (score, result, possession, league positions, related events/team-stats/player-stats counts) and an overall readiness assessment (`>80%` computed scores = Excellent, upcoming fixtures present = ready for prediction).

## Phase 2: LLM Integration

With LLM-optimized data in place, this pipeline is ready to support:

- **Match Prediction**: using team form, head-to-head history, player stats
- **Tactical Analysis**: playing-style patterns from events/statistics
- **API Development**: FastAPI endpoints serving LLM predictions
- **Real-time Updates**: the existing Celery beat schedule keeps data fresh
