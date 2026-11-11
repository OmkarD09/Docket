"""SQLite Database Connection and Transaction Management for Docket.

Ensures thread-safe connection pooling, explicit transaction boundaries,
Write-Ahead Logging (WAL) concurrency, foreign key enforcement, and
safe shutdown.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
from typing import Any, Generator, List, Optional, Tuple, Union

from docket.database.schema import initialize_schema


class DatabaseConnection:
    """Thread-safe SQLite database manager with WAL mode and foreign key enforcement."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.raw_path = str(db_path) if db_path else "artifacts/docket.db"
        self.is_memory = self.raw_path == ":memory:"

        if not self.is_memory:
            Path(self.raw_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        # isolation_level=None enables explicit manual control over BEGIN IMMEDIATE / COMMIT
        self._conn = sqlite3.connect(
            self.raw_path,
            check_same_thread=False,
            isolation_level=None,
            timeout=30.0,
        )
        self._conn.row_factory = sqlite3.Row

        self._configure_pragmas()
        initialize_schema(self._conn)

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the underlying sqlite3.Connection object."""
        return self._conn

    def _configure_pragmas(self) -> None:
        """Apply essential SQLite operational pragmas."""
        cur = self._conn.cursor()
        try:
            # Enforce foreign key constraints
            cur.execute("PRAGMA foreign_keys = ON;")
            # Wait up to 10 seconds for locks to clear before failing with SQLITE_BUSY
            cur.execute("PRAGMA busy_timeout = 10000;")
            if not self.is_memory:
                # Enable WAL (Write-Ahead Logging) for high concurrency
                cur.execute("PRAGMA journal_mode = WAL;")
                cur.execute("PRAGMA synchronous = NORMAL;")
        finally:
            cur.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager providing an atomic BEGIN IMMEDIATE transaction block.
        
        Guarantees that all writes within the block either commit together
        or roll back completely on unhandled exceptions.
        """
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                yield cur
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise
            finally:
                cur.close()

    @contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager providing a thread-safe read cursor."""
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    def execute(self, sql: str, params: Union[Tuple[Any, ...], List[Any]] = ()) -> sqlite3.Cursor:
        """Execute a single query with thread-safety."""
        with self._lock:
            cur = self._conn.cursor()
            try:
                return cur.execute(sql, params)
            finally:
                cur.close()

    def fetchone(self, sql: str, params: Union[Tuple[Any, ...], List[Any]] = ()) -> Optional[sqlite3.Row]:
        """Fetch a single row."""
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, params)
                return cur.fetchone()
            finally:
                cur.close()

    def fetchall(self, sql: str, params: Union[Tuple[Any, ...], List[Any]] = ()) -> List[sqlite3.Row]:
        """Fetch all rows."""
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute(sql, params)
                return cur.fetchall()
            finally:
                cur.close()

    def backup(self, target_path: Union[str, Path]) -> Path:
        """Create a consistent online point-in-time backup safe under active WAL concurrency.
        
        Uses SQLite's native online backup API to ensure active WAL transactions are flushed
        and copied without locking out readers or risking half-written file corruption.
        """
        dst = Path(target_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            dst_conn = sqlite3.connect(str(dst))
            try:
                self._conn.backup(dst_conn, pages=100)
            finally:
                dst_conn.close()
        return dst

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            self._conn.close()

