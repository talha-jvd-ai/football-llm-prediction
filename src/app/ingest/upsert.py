"""Database upsert utilities for efficient data insertion and updates."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Type

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.logging import get_logger

logger = get_logger("upsert")


def bulk_upsert(
    session: Session,
    model: Type[Any],
    rows: Iterable[Mapping[str, Any]],
    conflict_columns: List[str],
) -> int:
    """
    Perform bulk upsert (INSERT ... ON CONFLICT DO UPDATE) operation.
    
    Args:
        session: SQLAlchemy session
        model: SQLAlchemy model class
        rows: Iterable of row data dictionaries
        conflict_columns: Column names to use for conflict detection
        
    Returns:
        Number of rows affected
    """
    rows_list = list(rows)
    if not rows_list:
        logger.debug(f"No rows to upsert for {model.__tablename__}")
        return 0
    
    # Get table name with schema
    table_name = f"{model.__table__.schema}.{model.__tablename__}"
    
    # Create insert statement
    stmt = insert(model).values(rows_list)
    
    # Determine which columns to update (all except conflict columns)
    first_row = rows_list[0]
    update_columns = {
        col: stmt.excluded[col] 
        for col in first_row.keys() 
        if col not in conflict_columns
    }
    
    # Add updated_at timestamp if the model has it
    if hasattr(model, 'updated_at'):
        update_columns['updated_at'] = text('now()')
    
    # Create ON CONFLICT DO UPDATE statement
    do_update_stmt = stmt.on_conflict_do_update(
        index_elements=conflict_columns,
        set_=update_columns
    )
    
    # Execute the statement
    result = session.execute(do_update_stmt)
    rowcount = result.rowcount or 0
    
    logger.debug(f"Upserted {rowcount} rows into {table_name}")
    return rowcount


def delete_where(
    session: Session,
    table_name: str,
    where_clause: str,
    params: Dict[str, Any],
) -> int:
    """
    Delete rows from a table with a WHERE clause.
    
    Args:
        session: SQLAlchemy session
        table_name: Full table name (with schema)
        where_clause: WHERE clause (without WHERE keyword)
        params: Parameters for the WHERE clause
        
    Returns:
        Number of rows deleted
    """
    sql = f"DELETE FROM {table_name} WHERE {where_clause}"
    result = session.execute(text(sql), params)
    rowcount = result.rowcount or 0
    
    logger.debug(f"Deleted {rowcount} rows from {table_name}")
    return rowcount


def get_or_create_mapping(
    session: Session,
    model: Type[Any],
    lookup_column: str,
    lookup_values: List[Any],
) -> Dict[Any, int]:
    """
    Get a mapping of lookup values to internal IDs, useful for foreign key resolution.
    
    Args:
        session: SQLAlchemy session
        model: SQLAlchemy model class
        lookup_column: Column name to look up (e.g., 'sm_id')
        lookup_values: List of values to look up
        
    Returns:
        Dictionary mapping lookup values to internal IDs
    """
    if not lookup_values:
        return {}
    
    # Query for existing mappings
    lookup_attr = getattr(model, lookup_column)
    id_attr = getattr(model, 'id')
    
    query = session.query(lookup_attr, id_attr).filter(
        lookup_attr.in_(lookup_values)
    )
    
    mapping = dict(query.all())
    
    logger.debug(
        f"Retrieved {len(mapping)} {model.__tablename__} mappings "
        f"for {len(lookup_values)} lookup values"
    )
    
    return mapping


def insert_raw_source(
    session: Session,
    source: str,
    sm_id: int | None,
    checksum: str,
    payload: Dict[str, Any],
) -> None:
    """
    Insert raw API response data for audit trail.
    
    Args:
        session: SQLAlchemy session
        source: Source identifier (e.g., 'fixtures', 'teams')
        sm_id: SportMonks ID (if applicable)
        checksum: Payload checksum
        payload: Raw API response data
    """
    from app.db.models import SourceRaw
    
    raw_record = SourceRaw(
        source=source,
        sm_id=sm_id,
        checksum=checksum,
        payload=payload,
    )
    
    session.add(raw_record)
    logger.debug(f"Inserted raw source record for {source} (sm_id={sm_id})")


def update_etl_cursor(
    session: Session,
    resource: str,
    cursor_value: str,
) -> None:
    """
    Update ETL cursor for incremental processing.
    
    Args:
        session: SQLAlchemy session
        resource: Resource identifier (e.g., 'fixtures:premier_league')
        cursor_value: Cursor value (date, ID, timestamp, etc.)
    """
    from app.db.models import EtlCursor
    
    # Check if cursor already exists
    existing_cursor = session.query(EtlCursor).filter_by(resource=resource).first()
    
    if existing_cursor:
        # Update existing cursor
        existing_cursor.cursor_value = cursor_value
        existing_cursor.updated_at = text('now()')
        logger.debug(f"Updated ETL cursor for {resource}: {cursor_value}")
    else:
        # Create new cursor
        cursor = EtlCursor(
            resource=resource,
            cursor_value=cursor_value,
        )
        session.add(cursor)
        logger.debug(f"Created ETL cursor for {resource}: {cursor_value}")
    
    session.flush()


def get_etl_cursor(
    session: Session,
    resource: str,
) -> str | None:
    """
    Get ETL cursor value for incremental processing.
    
    Args:
        session: SQLAlchemy session
        resource: Resource identifier
        
    Returns:
        Cursor value or None if not found
    """
    from app.db.models import EtlCursor
    
    cursor = session.query(EtlCursor).filter_by(resource=resource).first()
    
    if cursor:
        logger.debug(f"Retrieved ETL cursor for {resource}: {cursor.cursor_value}")
        return cursor.cursor_value
    else:
        logger.debug(f"No ETL cursor found for {resource}")
        return None


def clear_fixture_related_data(
    session: Session,
    fixture_id: int,
) -> None:
    """
    Clear all related data for a fixture before re-hydrating.
    
    This is used to ensure clean re-hydration of fixture data.
    
    Args:
        session: SQLAlchemy session
        fixture_id: Internal fixture ID
    """
    # Delete in order to respect foreign key constraints
    tables_to_clear = [
        "football.fixture_event",
        "football.fixture_team_stat", 
        "football.player_match_stat",
    ]
    
    total_deleted = 0
    for table in tables_to_clear:
        deleted = delete_where(
            session,
            table,
            "fixture_id = :fixture_id",
            {"fixture_id": fixture_id}
        )
        total_deleted += deleted
    
    logger.debug(f"Cleared {total_deleted} related records for fixture {fixture_id}")


def batch_process(
    items: List[Any],
    batch_size: int = 1000,
) -> Iterable[List[Any]]:
    """
    Process items in batches.
    
    Args:
        items: List of items to process
        batch_size: Size of each batch
        
    Yields:
        Batches of items
    """
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]