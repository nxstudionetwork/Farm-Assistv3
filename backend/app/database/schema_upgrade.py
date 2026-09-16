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
    "courses": [
        ("video_url", "VARCHAR(500)"),
        ("core_content", "TEXT"),
        ("tools_materials", "TEXT"),
        ("safety_tips", "TEXT"),
    ],
    "users": [
        ("is_online", "BOOLEAN DEFAULT 0"),
        ("last_seen_at", "DATETIME"),
        ("typing_conversation_id", "VARCHAR(36)"),
        ("is_demo", "BOOLEAN DEFAULT 0"),
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
    "community_posts": [
        ("is_demo", "BOOLEAN DEFAULT 0"),
    ],
    "community_comments": [
        ("parent_comment_id", "VARCHAR(36)"),
        ("is_demo", "BOOLEAN DEFAULT 0"),
    ],
    "community_likes": [
        ("is_demo", "BOOLEAN DEFAULT 0"),
    ],
    "community_saves": [
        ("is_demo", "BOOLEAN DEFAULT 0"),
    ],
    "community_answers": [
        ("is_demo", "BOOLEAN DEFAULT 0"),
    ],
    "community_groups": [
        ("is_demo", "BOOLEAN DEFAULT 0"),
    ],
    "insurance_policies": [
        ("product_id", "VARCHAR(36)"),
        ("application_id", "VARCHAR(36)"),
        ("insured_item", "VARCHAR(300)"),
        ("sum_insured", "FLOAT"),
        ("premium_paid", "FLOAT"),
        ("premium_due", "FLOAT"),
        ("premium_due_date", "VARCHAR(10)"),
        ("renewal_date", "VARCHAR(10)"),
        ("renewal_count", "INTEGER DEFAULT 0"),
        ("policy_holder_name", "VARCHAR(200)"),
        ("updated_at", "DATETIME"),
    ],
    "insurance_claims": [
        ("claim_number", "VARCHAR(20)"),
        ("incident_date", "VARCHAR(10)"),
        ("incident_location", "VARCHAR(300)"),
        ("estimated_loss", "FLOAT"),
        ("description", "TEXT"),
        ("assessment_amount", "FLOAT"),
        ("settled_at", "VARCHAR(10)"),
    ],
    # calendar_events is created by create_all; no additive columns needed yet.
    "equipment": [
        ("deposit_amount", "FLOAT"),
        ("min_duration_days", "INTEGER DEFAULT 1"),
        ("rental_terms", "TEXT"),
        ("condition", "VARCHAR(30)"),
        ("listing_status", "VARCHAR(20) DEFAULT 'active'"),
    ],
    "equipment_metadata": [
        ("location", "VARCHAR(200)"),
        ("condition", "VARCHAR(30)"),
        ("delivery_available", "BOOLEAN"),
        ("pickup_available", "BOOLEAN"),
    ],
    "sensors": [
        ("plot_id", "VARCHAR(36)"),
        ("status", "VARCHAR(20) DEFAULT 'connected'"),
        ("device_identifier", "VARCHAR(100)"),
        ("connected_at", "DATETIME"),
        ("last_seen", "DATETIME"),
    ],
    "sensor_readings": [
        ("user_id", "VARCHAR(36)"),
        ("farm_id", "VARCHAR(36)"),
        ("plot_id", "VARCHAR(36)"),
    ],
    "products": [
        ("supports_cod", "BOOLEAN DEFAULT 1"),
    ],
    "marketplace_listings": [
        ("is_deleted", "BOOLEAN DEFAULT 0"),
    ],
    "marketplace_orders": [
        ("received_at", "DATETIME"),
        ("cancelled_at", "DATETIME"),
    ],
    "delivery_tracking": [
        ("notes", "TEXT"),
    ],
}


def run_additive_migrations(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        _migrate_sqlite(database_url)
    elif database_url.startswith("postgresql"):
        _migrate_postgres(database_url)


def _migrate_sqlite(database_url: str) -> None:
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
        logger.error("SQLite additive migrations failed: %s", exc)


def _migrate_postgres(database_url: str) -> None:
    try:
        import psycopg2
        from urllib.parse import urlparse

        parsed = urlparse(database_url)
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            dbname=parsed.path.lstrip("/"),
            user=parsed.username,
            password=parsed.password,
            sslmode="require" if "render.com" in (parsed.hostname or "") else "prefer",
        )
        try:
            cur = conn.cursor()
            for table, columns in ADDITIVE_COLUMNS.items():
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s",
                    (table,),
                )
                existing = {row[0] for row in cur.fetchall()}
                for column, declaration in columns:
                    if column not in existing:
                        pg_type = declaration.upper().replace("VARCHAR", "VARCHAR")
                        cur.execute(
                            f"ALTER TABLE {table} ADD COLUMN {column} {pg_type}"
                        )
                        logger.info("Added column %s.%s (postgres)", table, column)
            conn.commit()
        finally:
            conn.close()
    except ImportError:
        logger.warning("psycopg2 not installed; skipping PostgreSQL migrations")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("PostgreSQL additive migrations failed: %s", exc)
