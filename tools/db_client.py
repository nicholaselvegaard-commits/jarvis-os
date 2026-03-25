"""Database client for PostgreSQL/SQLite with parameterized queries."""
import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)


@contextmanager
def get_connection(database_url: str | None = None) -> Generator:
    """
    Get a database connection. Auto-detects SQLite vs PostgreSQL from URL.

    Args:
        database_url: Connection string (defaults to DATABASE_URL env var).

    Yields:
        Database connection object.
    """
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///local.db")

    if url.startswith("sqlite"):
        import sqlite3
        db_path = url.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    else:
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            raise ImportError("psycopg2 required for PostgreSQL: pip install psycopg2-binary")
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield conn
        finally:
            conn.close()


def query(sql: str, params: tuple = (), database_url: str | None = None) -> list[dict[str, Any]]:
    """
    Execute a read-only SQL query with parameterized inputs.

    Args:
        sql: SQL query string (use ? for SQLite, %s for PostgreSQL placeholders).
        params: Tuple of parameter values.
        database_url: Optional connection string override.

    Returns:
        List of row dicts.
    """
    logger.info(f"Executing query: {sql[:80]}...")
    with get_connection(database_url) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(row) for row in rows]


def execute(sql: str, params: tuple = (), database_url: str | None = None) -> int:
    """
    Execute a write SQL statement. Caller must confirm intent before calling.

    Args:
        sql: SQL statement.
        params: Tuple of parameter values.
        database_url: Optional connection string override.

    Returns:
        Number of rows affected.
    """
    logger.warning(f"Executing write statement: {sql[:80]}...")
    with get_connection(database_url) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        affected = cur.rowcount
    logger.info(f"Write affected {affected} rows")
    return affected
