# Football Data Ingestion Pipeline (LLM-Optimized)

**Goal**: Continuously ingest & normalize SportMonks Football data for Premier League, La Liga, Ligue 1 into **Supabase Postgres** with **LLM-ready computed fields** for match prediction and analysis.

**Stack**: Python 3.11+, Poetry, Celery + Redis, httpx, SQLAlchemy + Alembic, Supabase

## What It Does

- Discovers leagues by name and resolves **current seasons**
- Syncs teams/venues/coaches/players metadata
- Fetches **finished fixtures** with direct result extraction (scores, win/loss, possession, league positions)
- Fetches **upcoming fixtures** for prediction
- Stores **events**, **team fixture stats**, **player match stats** for detailed analysis
- **LLM-optimized**: Pre-computed fields eliminate complex aggregations for fast queries

## Key Features (LLM-Ready)

✅ **Direct Result Extraction**: Final scores and win/loss from SportMonks `participants.meta.winner`  
✅ **Computed Fields**: `home_goals`, `away_goals`, `result`, `home_possession`, etc.  
✅ **League Context**: Team positions at match time for strength analysis  
✅ **Fast Queries**: No real-time aggregations needed for LLM input generation  
✅ **Finished vs Upcoming**: Separate handling for historical analysis vs prediction  

## Project Structure

```
football-ingest/
├── pyproject.toml             # Poetry dependencies & config
├── README.md                 
├── .env.example               # Environment variables template
├── alembic.ini                # Alembic configuration
├── alembic/                   # Database migrations
│   ├── env.py
│   └── versions/
│       ├── 0001_initial.py
│       └── 0002_llm_optimization.py
├── docker/
│   └── docker-compose.redis.yml
└── src/
   └── app/
      ├── __init__.py
      ├── logging.py             # Logging configuration
      ├── config.py              # Settings & environment
      ├── worker.py              # Celery app & beat schedule
      ├── utils/
      │   ├── __init__.py
      │   └── http.py            # HTTP client with retries
      ├── db/
      │   ├── __init__.py
      │   ├── session.py         # Database session & engine
      │   └── models.py          # SQLAlchemy models (with LLM fields)
      ├── clients/
      │   ├── __init__.py
      │   └── sportmonks.py      # SportMonks API client (LLM-optimized)
      ├── ingest/
      │   ├── __init__.py
      │   ├── tasks.py           # Celery tasks (finished vs upcoming)
      │   ├── mappers.py         # JSON → model mappers (direct extraction)
      │   └── upsert.py          # Database upsert helpers
      └── scripts/
         ├── bootstrap.py        # Bootstrap script
         └── backfill.py         # Backfill script (LLM-optimized)
```

## Quick Start

### Prerequisites

- Python 3.11+
- Redis (use `docker/docker-compose.redis.yml`)
- Supabase Postgres connection string (Service Role)
- SportMonks API token

### 1. Install Dependencies

```bash
# Install Poetry if you haven't already
curl -sSL https://install.python-poetry.org | python3 -

# Install project dependencies
poetry install

# Copy environment template
cp .env.example .env
# Edit .env with your keys (see Environment Variables section below)
```

### 2. Start Redis

```bash
docker compose -f docker/docker-compose.redis.yml up -d
```

### 3. Initialize Database

```bash
# Run database migrations (includes LLM optimization)
poetry run alembic upgrade head
```

### 4. Bootstrap Metadata

```bash
# Discover leagues/seasons and sync initial metadata
poetry run python -m app.scripts.bootstrap main
```

### 5. Backfill LLM-Optimized Data

```bash
# Backfill finished fixtures with computed LLM fields (historical analysis)
poetry run python -m app.scripts.backfill finished-fixtures --days 30

# Backfill upcoming fixtures (for prediction)
poetry run python -m app.scripts.backfill upcoming-fixtures --days 21

# Verify LLM data quality
poetry run python -m app.scripts.backfill verify-llm-data
```

### 6. Start Workers & Scheduler

```bash
# Terminal 1: Start Celery worker
poetry run celery -A app.worker.app worker --loglevel=INFO

# Terminal 2: Start Celery Beat scheduler
poetry run celery -A app.worker.app beat --loglevel=INFO
```

## Environment Variables

Create a `.env` file with the following variables:

```bash
# SportMonks API
SPORTMONKS_API_TOKEN=your_sportmonks_api_token_here

# Supabase Postgres (Service Role URI)
SUPABASE_DB_URL=postgresql+psycopg://postgres.USER:PASS@HOST:PORT/postgres

# Redis
REDIS_URL=redis://localhost:6379/0

# Leagues to manage (names exactly as in SportMonks)
LEAGUE_NAMES=Premier League,La Liga,Ligue 1

# Scheduling Configuration
FIXTURE_HORIZON_DAYS=21
TIMEZONE=UTC
LOG_LEVEL=INFO
```

## LLM-Optimized Data Pipeline

### Scheduled Tasks

Once workers are running, these tasks execute automatically:

- **`daily_llm_data_sync`** (02:00 UTC daily)
  - Comprehensive sync: metadata + finished fixtures + upcoming fixtures
  
- **`sync_upcoming_fixtures`** (every 6 hours)
  - Updates upcoming fixtures for prediction pipeline
  
- **`sync_finished_fixtures`** (daily, last 30 days)
  - Updates historical data with computed LLM fields

### Data Flow

1. **Bootstrap**: Discovers leagues/seasons, syncs metadata
2. **Finished Fixtures**: Extracts direct results from SportMonks (scores, win/loss, possession)
3. **Upcoming Fixtures**: Fetches scheduled matches for prediction
4. **Computed Fields**: Pre-calculates LLM-ready data (no aggregation needed)
5. **Storage**: Normalized data with computed columns for fast LLM queries

## LLM-Ready Database Schema

### Core Tables (Enhanced)

- `football.fixture` - **Enhanced with computed columns**:
  - `home_goals`, `away_goals` - Final scores
  - `result` - 'H'/'A'/'D' for home/away/draw
  - `home_position`, `away_position` - League standings
  - `home_possession`, `away_possession` - Ball possession %
  - `home_corners`, `away_corners` - Corner kicks
  - `home_yellow_cards`, `away_yellow_cards` - Cards

### Supporting Tables

- `football.league`, `football.season`, `football.team` - Metadata
- `football.venue`, `football.coach`, `football.player` - Context data
- `football.fixture_event` - Match events (goals, cards, subs)
- `football.fixture_team_stat` - Detailed team statistics
- `football.player_match_stat` - Individual player statistics

## LLM Query Examples

### Team Recent Form (Simple!)
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

## SportMonks API Optimization

**LLM-Optimized Includes**: `participants;events.type;statistics.type;scores;lineups.details.type`

- **Strategic**: Direct extraction from `participants.meta.winner` and `scores.CURRENT`
- **Efficient**: Separate handling for finished vs upcoming fixtures

## Manual Operations

### Backfill Commands (Make sure to run bootstrap first)

```bash
# Finished fixtures (historical analysis)
poetry run python -m app.scripts.backfill finished-fixtures --days 60

# Upcoming fixtures (prediction)
poetry run python -m app.scripts.backfill upcoming-fixtures --days 21

# Data quality verification
poetry run python -m app.scripts.backfill verify-llm-data

# Clean rebuild (if needed)
poetry run python -m app.scripts.backfill clean-and-rebuild --days 30 --confirm
```

### Trigger Tasks

```bash
# Sync all LLM data
poetry run celery -A app.worker.app call ingest.daily_llm_data_sync

# Sync only finished fixtures
poetry run celery -A app.worker.app call ingest.sync_finished_fixtures

# Sync only upcoming fixtures
poetry run celery -A app.worker.app call ingest.sync_upcoming_fixtures
```

### Monitor Tasks

```bash
# View active tasks
poetry run celery -A app.worker.app inspect active

# View scheduled tasks
poetry run celery -A app.worker.app inspect scheduled
```


## Troubleshooting

### Common Issues

1. **Redis Connection Error**
   - Ensure Redis is running: `docker compose -f docker/docker-compose.redis.yml up -d`

2. **Database Connection Error**
   - Verify `SUPABASE_DB_URL` in `.env`
   - Ensure database exists and migrations are applied

3. **SportMonks API Errors**
   - Check `SPORTMONKS_API_TOKEN` is valid
   - Monitor rate limits (429 errors)

4. **Foreign Key Violations**
   - Run bootstrap before backfill

### Logs

Monitor Celery logs for detailed information:

```bash
# Worker logs
poetry run celery -A app.worker.app worker --loglevel=DEBUG

# Beat scheduler logs  
poetry run celery -A app.worker.app beat --loglevel=DEBUG
```

## Data Quality Verification

### Check LLM-Ready Data
```bash
# Run verification
poetry run python -m app.scripts.backfill verify-llm-data

# Expected output:
# ✅ Excellent: >80% of finished matches have computed scores
# ✅ Upcoming fixtures available for prediction
# ✅ READY for LLM analysis and prediction!
```

### Sample LLM Input (Available Now)
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

## Phase 2: LLM Integration

With LLM-optimized data in place, you're ready for:

- **Match Prediction**: Using team form, head-to-head, player stats
- **Tactical Analysis**: Playing style patterns from events/statistics
- **API Development**: FastAPI endpoints serving LLM predictions
- **Real-time Updates**: Continuous pipeline feeding fresh data

