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
    "feedback": [
        ("category", "VARCHAR(50)"),
    ],
    "notifications": [
        ("is_archived", "BOOLEAN DEFAULT 0"),
        ("is_deleted", "BOOLEAN DEFAULT 0"),
        ("updated_at", "DATETIME"),
    ],
    "consultations": [
        ("consultation_type", "VARCHAR(100)"),
        ("consultation_method", "VARCHAR(50)"),
        ("farm_id", "VARCHAR(36)"),
        ("farm_name", "VARCHAR(200)"),
        ("crop_id", "VARCHAR(36)"),
        ("crop_name", "VARCHAR(200)"),
        ("meeting_reference", "VARCHAR(500)"),
        ("meeting_location", "VARCHAR(500)"),
        ("cancel_reason", "TEXT"),
        ("completed_at", "DATETIME"),
        ("cancelled_at", "DATETIME"),
        ("updated_at", "DATETIME"),
    ],
    "farm_emergency_reports": [
        ("reference_id", "VARCHAR(20)"),
        ("contact_phone", "VARCHAR(15)"),
        ("updated_at", "DATETIME"),
    ],
    "agricultural_services": [
        ("full_description", "TEXT"),
        ("deliverables", "TEXT"),
        ("eligibility", "VARCHAR(300)"),
        ("service_duration", "VARCHAR(100)"),
        ("required_documents", "VARCHAR(300)"),
    ],
    "government_schemes": [
        ("department", "VARCHAR(300)"),
        ("level", "VARCHAR(30)"),
        ("overview", "TEXT"),
        ("objectives", "TEXT"),
        ("application_process", "TEXT"),
        ("contact_information", "TEXT"),
        ("source", "VARCHAR(200)"),
        ("source_url", "VARCHAR(500)"),
        ("start_date", "VARCHAR(20)"),
        ("faqs", "JSON"),
        ("eligible_farmer_types", "JSON"),
        ("related_crops", "JSON"),
        ("land_category", "VARCHAR(100)"),
        ("income_category", "VARCHAR(100)"),
        ("benefit_type", "VARCHAR(50)"),
        ("last_verified_at", "DATETIME"),
        ("updated_at", "DATETIME"),
    ],
    "service_requests": [
        ("service_id", "VARCHAR(36)"),
        ("location", "VARCHAR(200)"),
        ("rating", "INTEGER"),
        ("rating_feedback", "TEXT"),
    ],
    "community_posts": [
        ("title", "VARCHAR(300)"),
        ("category", "VARCHAR(60)"),
        ("crop", "VARCHAR(120)"),
        ("location", "VARCHAR(200)"),
        ("community_id", "VARCHAR(36)"),
        ("media_type", "VARCHAR(10)"),
        ("saves_count", "INTEGER DEFAULT 0"),
    ],
    "community_comments": [
        ("parent_comment_id", "VARCHAR(36)"),
    ],
    "lesson_progress": [
        ("course_id", "VARCHAR(36)"),
        ("score", "FLOAT DEFAULT 0"),
        ("attempts", "INTEGER DEFAULT 0"),
        ("started_at", "DATETIME"),
        ("last_accessed_at", "DATETIME"),
    ],
    "users": [
        ("is_online", "BOOLEAN DEFAULT 0"),
        ("last_seen_at", "DATETIME"),
        ("typing_conversation_id", "VARCHAR(36)"),
    ],
    "messages": [
        ("status", "VARCHAR(10) DEFAULT 'sent'"),
        ("delivered_at", "DATETIME"),
        ("read_at", "DATETIME"),
    ],
    "conversation_participants": [
        ("muted", "BOOLEAN DEFAULT 0"),
        ("deleted_at", "DATETIME"),
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
