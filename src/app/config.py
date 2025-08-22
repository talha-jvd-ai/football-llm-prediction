"""Application configuration and settings."""

from __future__ import annotations

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        case_sensitive=True,
    )

    # SportMonks API Configuration
    SPORTMONKS_API_TOKEN: str = Field(..., description="SportMonks API token")

    # Database Configuration
    SUPABASE_DB_URL: str = Field(..., description="Supabase PostgreSQL connection URL")

    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )

    # League Configuration
    LEAGUE_NAMES: List[str] = Field(
        default=["Premier League", "La Liga", "Ligue 1"],
        description="List of league names to monitor",
    )

    # Scheduling Configuration
    FIXTURE_HORIZON_DAYS: int = Field(
        default=21, ge=1, le=100, description="Days ahead to fetch fixtures"
    )
    TIMEZONE: str = Field(default="UTC", description="Timezone for scheduling")

    # Logging Configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # HTTP Configuration
    HTTP_TIMEOUT: float = Field(
        default=30.0, ge=1.0, description="HTTP request timeout in seconds"
    )
    MAX_RETRIES: int = Field(
        default=5, ge=1, description="Maximum number of HTTP retries"
    )
    RETRY_DELAY: float = Field(
        default=1.0, ge=0.1, description="Base retry delay in seconds"
    )

    @field_validator("LEAGUE_NAMES", mode="before")
    @classmethod
    def parse_league_names(cls, v: str | List[str]) -> List[str]:
        """Parse league names from string or list."""
        if isinstance(v, str):
            return [name.strip() for name in v.split(",") if name.strip()]
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        level = v.upper()
        if level not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return level


# Global settings instance
settings = Settings()
