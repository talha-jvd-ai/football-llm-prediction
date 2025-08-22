"""SQLAlchemy database models with LLM-optimized computed columns."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    CHAR,
    Date,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Schema name for all football tables
SCHEMA = "football"


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class League(Base):
    """League model representing football leagues."""

    __tablename__ = "league"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sm_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    # Relationships
    seasons: Mapped[List["Season"]] = relationship("Season", back_populates="league")
    teams: Mapped[List["Team"]] = relationship("Team", back_populates="league")
    fixtures: Mapped[List["Fixture"]] = relationship("Fixture", back_populates="league")

    def __repr__(self) -> str:
        return f"<League(id={self.id}, name='{self.name}', sm_id={self.sm_id})>"


class Season(Base):
    """Season model representing football seasons."""

    __tablename__ = "season"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sm_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    league_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.league.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    year_start: Mapped[Optional[int]] = mapped_column(Integer)
    year_end: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    # Relationships
    league: Mapped[Optional["League"]] = relationship(
        "League", back_populates="seasons"
    )
    fixtures: Mapped[List["Fixture"]] = relationship("Fixture", back_populates="season")

    def __repr__(self) -> str:
        return f"<Season(id={self.id}, name='{self.name}', sm_id={self.sm_id})>"


class Venue(Base):
    """Venue model representing football stadiums/venues."""

    __tablename__ = "venue"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sm_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(Text)
    capacity: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    # Relationships
    teams: Mapped[List["Team"]] = relationship("Team", back_populates="venue")
    fixtures: Mapped[List["Fixture"]] = relationship("Fixture", back_populates="venue")

    def __repr__(self) -> str:
        return f"<Venue(id={self.id}, name='{self.name}', sm_id={self.sm_id})>"


class Team(Base):
    """Team model representing football teams."""

    __tablename__ = "team"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sm_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    league_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.league.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    short_code: Mapped[Optional[str]] = mapped_column(Text)
    venue_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.venue.id"))
    country: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    # Relationships
    league: Mapped[Optional["League"]] = relationship("League", back_populates="teams")
    venue: Mapped[Optional["Venue"]] = relationship("Venue", back_populates="teams")
    coaches: Mapped[List["Coach"]] = relationship("Coach", back_populates="team")
    players: Mapped[List["Player"]] = relationship("Player", back_populates="team")
    home_fixtures: Mapped[List["Fixture"]] = relationship(
        "Fixture", foreign_keys="Fixture.home_team_id", back_populates="home_team"
    )
    away_fixtures: Mapped[List["Fixture"]] = relationship(
        "Fixture", foreign_keys="Fixture.away_team_id", back_populates="away_team"
    )
    fixture_events: Mapped[List["FixtureEvent"]] = relationship(
        "FixtureEvent", back_populates="team"
    )
    fixture_team_stats: Mapped[List["FixtureTeamStat"]] = relationship(
        "FixtureTeamStat", back_populates="team"
    )

    def __repr__(self) -> str:
        return f"<Team(id={self.id}, name='{self.name}', sm_id={self.sm_id})>"


class Coach(Base):
    """Coach model representing team coaches."""

    __tablename__ = "coach"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sm_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.team.id"))
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    nationality: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    # Relationships
    team: Mapped[Optional["Team"]] = relationship("Team", back_populates="coaches")

    def __repr__(self) -> str:
        return f"<Coach(id={self.id}, name='{self.full_name}', sm_id={self.sm_id})>"


class Player(Base):
    """Player model representing football players."""

    __tablename__ = "player"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sm_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.team.id"))
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[Optional[str]] = mapped_column(Text)
    nationality: Mapped[Optional[str]] = mapped_column(Text)
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    # Relationships
    team: Mapped[Optional["Team"]] = relationship("Team", back_populates="players")
    fixture_events: Mapped[List["FixtureEvent"]] = relationship(
        "FixtureEvent", foreign_keys="FixtureEvent.player_id", back_populates="player"
    )
    related_fixture_events: Mapped[List["FixtureEvent"]] = relationship(
        "FixtureEvent",
        foreign_keys="FixtureEvent.related_player_id",
        back_populates="related_player",
    )
    player_match_stats: Mapped[List["PlayerMatchStat"]] = relationship(
        "PlayerMatchStat", back_populates="player"
    )

    def __repr__(self) -> str:
        return f"<Player(id={self.id}, name='{self.full_name}', sm_id={self.sm_id})>"


class Fixture(Base):
    """Fixture model representing football matches with LLM-optimized computed columns."""

    __tablename__ = "fixture"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sm_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    league_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.league.id"))
    season_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.season.id"))
    venue_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.venue.id"))
    home_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.team.id"))
    away_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.team.id"))
    referee_name: Mapped[Optional[str]] = mapped_column(Text)
    kickoff_ts: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    round: Mapped[Optional[str]] = mapped_column(Text)

    # LLM-optimized computed columns (from SportMonks direct extraction)
    home_goals: Mapped[Optional[int]] = mapped_column(Integer)
    away_goals: Mapped[Optional[int]] = mapped_column(Integer)
    result: Mapped[Optional[str]] = mapped_column(CHAR(1))  # 'H'/'A'/'D'
    home_position: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # League position at match time
    away_position: Mapped[Optional[int]] = mapped_column(
        Integer
    )  # League position at match time
    home_possession: Mapped[Optional[float]] = mapped_column(
        Numeric
    )  # Ball possession %
    away_possession: Mapped[Optional[float]] = mapped_column(
        Numeric
    )  # Ball possession %
    home_corners: Mapped[Optional[int]] = mapped_column(Integer)  # Corner kicks
    away_corners: Mapped[Optional[int]] = mapped_column(Integer)  # Corner kicks
    home_yellow_cards: Mapped[Optional[int]] = mapped_column(Integer)  # Yellow cards
    away_yellow_cards: Mapped[Optional[int]] = mapped_column(Integer)  # Yellow cards
    home_red_cards: Mapped[Optional[int]] = mapped_column(Integer)  # Red cards
    away_red_cards: Mapped[Optional[int]] = mapped_column(Integer)  # Red cards

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    # Relationships
    league: Mapped[Optional["League"]] = relationship(
        "League", back_populates="fixtures"
    )
    season: Mapped[Optional["Season"]] = relationship(
        "Season", back_populates="fixtures"
    )
    venue: Mapped[Optional["Venue"]] = relationship("Venue", back_populates="fixtures")
    home_team: Mapped[Optional["Team"]] = relationship(
        "Team", foreign_keys=[home_team_id], back_populates="home_fixtures"
    )
    away_team: Mapped[Optional["Team"]] = relationship(
        "Team", foreign_keys=[away_team_id], back_populates="away_fixtures"
    )
    events: Mapped[List["FixtureEvent"]] = relationship(
        "FixtureEvent", back_populates="fixture", cascade="all, delete-orphan"
    )
    team_stats: Mapped[List["FixtureTeamStat"]] = relationship(
        "FixtureTeamStat", back_populates="fixture", cascade="all, delete-orphan"
    )
    player_stats: Mapped[List["PlayerMatchStat"]] = relationship(
        "PlayerMatchStat", back_populates="fixture", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Fixture(id={self.id}, sm_id={self.sm_id}, result='{self.result}', score='{self.home_goals}-{self.away_goals}')>"

    @property
    def total_goals(self) -> Optional[int]:
        """Total goals in the match."""
        if self.home_goals is not None and self.away_goals is not None:
            return self.home_goals + self.away_goals
        return None

    @property
    def goal_difference(self) -> Optional[int]:
        """Goal difference (home goals - away goals)."""
        if self.home_goals is not None and self.away_goals is not None:
            return self.home_goals - self.away_goals
        return None

    @property
    def is_finished(self) -> bool:
        """Check if match is finished."""
        return self.status == "5"

    @property
    def home_win(self) -> bool:
        """Check if home team won."""
        return self.result == "H"

    @property
    def away_win(self) -> bool:
        """Check if away team won."""
        return self.result == "A"

    @property
    def draw(self) -> bool:
        """Check if match was a draw."""
        return self.result == "D"


class FixtureEvent(Base):
    """Fixture event model representing match events (goals, cards, etc.)."""

    __tablename__ = "fixture_event"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.fixture.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.team.id"))
    player_id: Mapped[Optional[int]] = mapped_column(ForeignKey(f"{SCHEMA}.player.id"))
    related_player_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(f"{SCHEMA}.player.id")
    )
    minute: Mapped[Optional[int]] = mapped_column(Integer)
    type_code: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships
    fixture: Mapped["Fixture"] = relationship("Fixture", back_populates="events")
    team: Mapped[Optional["Team"]] = relationship(
        "Team", back_populates="fixture_events"
    )
    player: Mapped[Optional["Player"]] = relationship(
        "Player", foreign_keys=[player_id], back_populates="fixture_events"
    )
    related_player: Mapped[Optional["Player"]] = relationship(
        "Player",
        foreign_keys=[related_player_id],
        back_populates="related_fixture_events",
    )

    def __repr__(self) -> str:
        return f"<FixtureEvent(id={self.id}, type='{self.type_code}', minute={self.minute})>"


class FixtureTeamStat(Base):
    """Fixture team statistics model representing team stats for a match."""

    __tablename__ = "fixture_team_stat"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id", "team_id", "stat_code", name="uq_fixture_team_stat"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.fixture.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.team.id"), nullable=False
    )
    stat_code: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships
    fixture: Mapped["Fixture"] = relationship("Fixture", back_populates="team_stats")
    team: Mapped["Team"] = relationship("Team", back_populates="fixture_team_stats")

    def __repr__(self) -> str:
        return f"<FixtureTeamStat(id={self.id}, stat='{self.stat_code}', value={self.value})>"


class PlayerMatchStat(Base):
    """Player match statistics model representing player stats for a match."""

    __tablename__ = "player_match_stat"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id", "player_id", "stat_code", name="uq_player_match_stat"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.fixture.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.player.id"), nullable=False
    )
    stat_code: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships
    fixture: Mapped["Fixture"] = relationship("Fixture", back_populates="player_stats")
    player: Mapped["Player"] = relationship(
        "Player", back_populates="player_match_stats"
    )

    def __repr__(self) -> str:
        return f"<PlayerMatchStat(id={self.id}, stat='{self.stat_code}', value={self.value})>"


class SourceRaw(Base):
    """Source raw model for storing raw API responses for audit trail."""

    __tablename__ = "source_raw"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    sm_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)

    def __repr__(self) -> str:
        return f"<SourceRaw(id={self.id}, source='{self.source}', sm_id={self.sm_id})>"


class EtlCursor(Base):
    """ETL cursor model for tracking incremental processing state."""

    __tablename__ = "etl_cursor"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resource: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    cursor_value: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    def __repr__(self) -> str:
        return f"<EtlCursor(id={self.id}, resource='{self.resource}', cursor='{self.cursor_value}')>"
