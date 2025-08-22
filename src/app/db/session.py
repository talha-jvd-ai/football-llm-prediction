"""Database session management."""

from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.logging import get_logger

logger = get_logger("db")

# Create database engine
engine = create_engine(
    settings.SUPABASE_DB_URL,
    pool_pre_ping=True,
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=False,  # Set to True for SQL debugging
    future=True,
)

# Create session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """Set pragmas for SQLite connections (if using SQLite for testing)."""
    # This is primarily for testing with SQLite
    if "sqlite" in str(dbapi_connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session() -> Generator[Session, None, None]:
    """Get a database session.

    Yields:
        SQLAlchemy session instance
    """
    session = SessionLocal()
    try:
        logger.debug("Created database session")
        yield session
    except Exception as e:
        logger.error(f"Database session error: {e}")
        session.rollback()
        raise
    finally:
        session.close()
        logger.debug("Closed database session")


def create_session() -> Session:
    """Create a new database session.

    Returns:
        SQLAlchemy session instance
    """
    return SessionLocal()
