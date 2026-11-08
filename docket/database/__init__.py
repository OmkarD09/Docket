"""Docket SQLite Database Package.

Provides minimal, zero-dependency relational persistence, foreign key enforcement,
WAL mode concurrency, and transactional integrity for Docket dispute operations.
"""

from docket.database.connection import DatabaseConnection
from docket.database.repository import DocketRepository
from docket.database.schema import SCHEMA_DDL, initialize_schema

__all__ = [
    "DatabaseConnection",
    "DocketRepository",
    "SCHEMA_DDL",
    "initialize_schema",
]

