"""Lightweight additive migrations for SQLite.

SQLAlchemy's ``create_all`` only creates missing tables; it never adds new
columns to tables that already exist. This module performs safe ``ALTER TABLE
ADD COLUMN`` operations for the columns introduced after an install, so existing
databases are upgraded in place without requiring Alembic.
"""

import logging
import sqlite3

logger = logging.getLogger("app.migrations")

#: table -> list of (column_name, sqlite_column_declaration)
ADDITIVE_COLUMNS = {
    "farmer_profiles": [
        ("aadhaar_number", "VARCHAR(12)"),
        ("pan_number", "VARCHAR(10)"),
        ("irrigation_type", "VARCHAR(100)"),
        ("bio", "TEXT"),
        ("farm_location", "VARCHAR(200)"),
        ("farming_type", "VARCHAR(100)"),
    ],
}


def run_additive_migrations(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    db_path = database_url.replace("sqlite:///", "", 1)
    try:
        conn = sqlite3.connect(db_path)
        try:
            for table, columns in ADDITIVE_COLUMNS.items():
                existing = {
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                for column, declaration in columns:
                    if column not in existing:
                        conn.execute(
                            f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
                        )
                        logger.info("Added column %s.%s", table, column)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Additive migrations failed: %s", exc)
