"""Lightweight additive migrations for SQLite.

SQLAlchemy's ``create_all`` only creates missing tables; it never adds new
columns to tables that already exist. This module performs safe ``ALTER TABLE
ADD COLUMN`` operations for the columns introduced after an install, so existing
databases are upgraded in place without requiring Alembic.
"""

import json
import logging
import sqlite3

logger = logging.getLogger("app.migrations")

#: table -> list of (column_name, sqlite_column_declaration)
ADDITIVE_COLUMNS = {
    "farms": [
        ("boundary_coordinates", "JSON"),
    ],
    # NOTE: only one "farmer_profiles" key may exist in this dict. A second
    # literal key silently replaces the first, so columns listed in the earlier
    # entry would never be applied to existing databases. Merge instead.
    "farmer_profiles": [
        ("aadhaar_number", "VARCHAR(12)"),
        ("pan_number", "VARCHAR(10)"),
        ("irrigation_type", "VARCHAR(100)"),
        ("bio", "TEXT"),
        ("farm_location", "VARCHAR(200)"),
        ("farming_type", "VARCHAR(100)"),
        ("farming_types", "VARCHAR(200)"),
        ("farming_activities", "VARCHAR(500)"),
        ("hydroponics_status", "VARCHAR(50)"),
        ("hydroponics_units_count", "INTEGER"),
        ("hydroponics_system", "VARCHAR(100)"),
        ("hydroponics_crops", "VARCHAR(500)"),
        ("hydroponics_area", "FLOAT"),
        ("hydroponics_area_unit", "VARCHAR(20)"),
        # Identity verification ledger. The cleartext aadhaar/pan columns above
        # are retained for existing rows, but the client is only ever shown
        # these last-4 values plus a status that honestly reflects that nothing
        # has been checked against any authority.
        ("aadhaar_last4", "VARCHAR(4)"),
        ("aadhaar_verification_status", "VARCHAR(20)"),
        ("pan_last4", "VARCHAR(4)"),
        ("pan_verification_status", "VARCHAR(20)"),
        ("farmer_card_number", "VARCHAR(64)"),
        ("farmer_card_issuing_authority", "VARCHAR(120)"),
        ("farmer_card_last4", "VARCHAR(4)"),
        ("farmer_card_verification_status", "VARCHAR(20)"),
        ("farmer_card_verification_reference", "VARCHAR(120)"),
        ("identity_verification_status", "VARCHAR(20)"),
        ("identity_verification_reference", "VARCHAR(120)"),
        ("identity_provider", "VARCHAR(60)"),
        ("identity_provider_ref", "VARCHAR(120)"),
    ],
    "ai_conversations": [
        ("farmer_id", "VARCHAR(36)"),
        ("title", "VARCHAR(200)"),
        ("updated_at", "DATETIME"),
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
        # Storage capacity facts (see the storage section in ADDITIVE_COLUMNS).
        ("storage_type", "VARCHAR(30)"),
        ("capacity_quintal", "FLOAT"),
        ("available_capacity_quintal", "FLOAT"),
        ("temperature_controlled", "BOOLEAN DEFAULT 0"),
        ("min_duration_days", "INTEGER"),
        ("supported_produce", "VARCHAR(500)"),
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
        # Phone/email proof of ownership is tracked per channel. The legacy
        # is_verified flag stays as an overall "this account was checked" marker
        # so existing login checks keep working unchanged.
        ("phone_verified", "BOOLEAN DEFAULT 0"),
        ("phone_verified_at", "DATETIME"),
        ("email_verified", "BOOLEAN DEFAULT 0"),
        ("email_verified_at", "DATETIME"),
        # Consent ledger for government identity verification.
        ("identity_consent_given", "BOOLEAN DEFAULT 0"),
        ("identity_consent_version", "VARCHAR(20)"),
        ("identity_consent_at", "DATETIME"),
        # Server-authoritative onboarding state so a farmer can resume on any
        # device instead of re-entering everything into browser localStorage.
        ("onboarding_status", "VARCHAR(30)"),
        ("onboarding_step", "VARCHAR(30)"),
        ("onboarding_updated_at", "DATETIME"),
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
        ("auth_token_hash", "VARCHAR(128)"),
        ("auth_token_prefix", "VARCHAR(16)"),
        ("metrics_supported", "JSON"),
    ],
    "sensor_readings": [
        ("user_id", "VARCHAR(36)"),
        ("farm_id", "VARCHAR(36)"),
        ("plot_id", "VARCHAR(36)"),
        ("received_at", "DATETIME"),
        ("payload", "JSON"),
    ],
    "products": [
        ("supports_cod", "BOOLEAN DEFAULT 1"),
    ],
    "marketplace_listings": [
        ("is_deleted", "BOOLEAN DEFAULT 0"),
        ("listing_type", "VARCHAR(10) DEFAULT 'sell'"),
        ("rental_period", "VARCHAR(10)"),
        ("min_rental_duration", "VARCHAR(60)"),
        ("available_from", "VARCHAR(20)"),
        ("available_until", "VARCHAR(20)"),
        ("security_deposit", "FLOAT"),
        ("rental_terms", "TEXT"),
        ("service_area", "VARCHAR(200)"),
        ("delivery_option", "VARCHAR(20)"),
    ],
    "marketplace_enquiries": [
        ("requested_quantity", "FLOAT"),
        ("offered_price", "FLOAT"),
    ],
    "marketplace_orders": [
        ("received_at", "DATETIME"),
        ("cancelled_at", "DATETIME"),
    ],
    "delivery_tracking": [
        ("notes", "TEXT"),
    ],
    "market_prices": [
        ("region", "VARCHAR(120)"),
        ("arrival_quantity", "FLOAT"),
    ],
    "worker_bookings": [
        ("started_at", "DATETIME"),
        ("completed_at", "DATETIME"),
        ("cancelled_at", "DATETIME"),
        ("cancelled_by", "VARCHAR(30)"),
        ("cancel_reason", "TEXT"),
        ("missed_at", "DATETIME"),
        ("subtotal", "FLOAT"),
        ("gst_amount", "FLOAT"),
    ],
    "crop_tasks": [
        ("source", "VARCHAR(30)"),
        ("growth_stage", "VARCHAR(50)"),
    ],
    # Scalable crop taxonomy. Every column is nullable so existing farmer rows
    # and their crop_cycles keep working untouched.
    "crops": [
        ("domain", "VARCHAR(80)"),
        ("category_id", "VARCHAR(36)"),
        ("subcategory", "VARCHAR(80)"),
        ("scientific_name", "VARCHAR(150)"),
        ("local_names", "JSON"),
        ("life_cycle_type", "VARCHAR(30)"),
        ("suitable_seasons", "VARCHAR(120)"),
        ("suitable_climate", "VARCHAR(160)"),
        ("suitable_soil_types", "VARCHAR(160)"),
        ("water_requirement", "VARCHAR(80)"),
        ("harvest_type", "VARCHAR(80)"),
        ("production_unit", "VARCHAR(30)"),
        ("storage_notes", "VARCHAR(255)"),
        ("market_type", "VARCHAR(80)"),
        ("lifecycle_stages", "JSON"),
        ("suitable_cultivation_methods", "JSON"),
        ("hydroponic_targets", "JSON"),
        ("is_catalog", "BOOLEAN DEFAULT 0"),
        ("is_archived", "BOOLEAN DEFAULT 0"),
    ],
    "crop_cycles": [
        ("variety_id", "VARCHAR(36)"),
        ("cultivation_method_id", "VARCHAR(36)"),
        ("protected_structure", "VARCHAR(40)"),
        ("planting_material", "VARCHAR(120)"),
    ],
    "expenses": [
        ("hydroponic_unit_id", "VARCHAR(36)"),
    ],
}


def run_additive_migrations(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        _migrate_sqlite(database_url)
    elif database_url.startswith("postgresql"):
        _migrate_postgres(database_url)


#: Customer authentication adds three tables and touches none of the existing
#: ones, so this is a pure additive migration: existing Farmer rows, Farmer IDs
#: and every other table are left exactly as they are.
#:
#: ``customers`` is created alongside ``farmer_profiles``, not in place of it.
#: ``user_id`` is unique, so one authenticated user resolves to at most one
#: customer profile, and ``customer_id`` carries a UNIQUE index so the public
#: ``FA-CS-######`` identifier can never be duplicated or forged onto a second
#: account.
#:
#: ``id_sequences`` holds the database-owned counter the Customer ID is drawn
#: from. It is created and primed here so the very first registration on an
#: existing database starts from the right number rather than from 1.
CUSTOMER_IDENTITY_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS customers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    customer_id VARCHAR(20) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    phone_number VARCHAR(15),
    email VARCHAR(200),
    date_of_birth VARCHAR(10),
    gender VARCHAR(10),
    verification_status VARCHAR(30) DEFAULT 'pending',
    phone_verified BOOLEAN DEFAULT 0,
    email_verified BOOLEAN DEFAULT 0,
    points_balance INTEGER DEFAULT 0,
    preferred_language VARCHAR(10) DEFAULT 'en',
    bio TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_user_id ON customers (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_customer_id ON customers (customer_id);
CREATE INDEX IF NOT EXISTS ix_customers_phone_number ON customers (phone_number);
CREATE INDEX IF NOT EXISTS ix_customers_email ON customers (email);

CREATE TABLE IF NOT EXISTS customer_points_entries (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    entry_id VARCHAR(20),
    customer_pk VARCHAR(36) NOT NULL,
    customer_id VARCHAR(20) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    points INTEGER NOT NULL,
    reason VARCHAR(60) NOT NULL,
    balance_after INTEGER DEFAULT 0,
    reference_type VARCHAR(40),
    reference_id VARCHAR(64),
    created_at DATETIME,
    FOREIGN KEY (customer_pk) REFERENCES customers (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_points_entries_entry_id ON customer_points_entries (entry_id);
CREATE INDEX IF NOT EXISTS ix_customer_points_entries_customer_pk ON customer_points_entries (customer_pk);
CREATE INDEX IF NOT EXISTS ix_customer_points_entries_customer_id ON customer_points_entries (customer_id);
CREATE INDEX IF NOT EXISTS ix_customer_points_entries_user_id ON customer_points_entries (user_id);

CREATE TABLE IF NOT EXISTS id_sequences (
    scope VARCHAR(40) NOT NULL PRIMARY KEY,
    last_value INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS customer_settings (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    notif_orders BOOLEAN DEFAULT 1,
    notif_products BOOLEAN DEFAULT 1,
    notif_grow BOOLEAN DEFAULT 1,
    notif_community BOOLEAN DEFAULT 1,
    notif_points BOOLEAN DEFAULT 1,
    shopping_default_address_id VARCHAR(36),
    shopping_preferences JSON,
    grow_reminders BOOLEAN DEFAULT 1,
    plant_care_reminders BOOLEAN DEFAULT 1,
    community_notifications BOOLEAN DEFAULT 1,
    community_privacy JSON,
    language VARCHAR(10) DEFAULT 'en',
    theme VARCHAR(20) DEFAULT 'system',
    text_size VARCHAR(20) DEFAULT 'medium',
    reduce_motion BOOLEAN DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_settings_user_id ON customer_settings (user_id);

CREATE TABLE IF NOT EXISTS customer_plants (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    plant_id VARCHAR(20),
    customer_pk VARCHAR(36) NOT NULL,
    customer_id VARCHAR(20) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    crop_id VARCHAR(36),
    nickname VARCHAR(120),
    planted_on VARCHAR(10),
    expected_harvest_on VARCHAR(10),
    quantity INTEGER,
    status VARCHAR(30) DEFAULT 'growing',
    notes TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (customer_pk) REFERENCES customers (id),
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (crop_id) REFERENCES crops (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_plants_plant_id ON customer_plants (plant_id);
CREATE INDEX IF NOT EXISTS ix_customer_plants_customer_pk ON customer_plants (customer_pk);
CREATE INDEX IF NOT EXISTS ix_customer_plants_customer_id ON customer_plants (customer_id);
CREATE INDEX IF NOT EXISTS ix_customer_plants_user_id ON customer_plants (user_id);
CREATE INDEX IF NOT EXISTS ix_customer_plants_crop_id ON customer_plants (crop_id);
"""

CUSTOMER_IDENTITY_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS customers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users (id),
    customer_id VARCHAR(20) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    phone_number VARCHAR(15),
    email VARCHAR(200),
    date_of_birth VARCHAR(10),
    gender VARCHAR(10),
    verification_status VARCHAR(30) DEFAULT 'pending',
    phone_verified BOOLEAN DEFAULT FALSE,
    email_verified BOOLEAN DEFAULT FALSE,
    points_balance INTEGER DEFAULT 0,
    preferred_language VARCHAR(10) DEFAULT 'en',
    bio TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_user_id ON customers (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_customer_id ON customers (customer_id);
CREATE INDEX IF NOT EXISTS ix_customers_phone_number ON customers (phone_number);
CREATE INDEX IF NOT EXISTS ix_customers_email ON customers (email);

CREATE TABLE IF NOT EXISTS customer_points_entries (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    entry_id VARCHAR(20),
    customer_pk VARCHAR(36) NOT NULL REFERENCES customers (id),
    customer_id VARCHAR(20) NOT NULL REFERENCES customers (customer_id),
    user_id VARCHAR(36) NOT NULL REFERENCES users (id),
    points INTEGER NOT NULL,
    reason VARCHAR(60) NOT NULL,
    balance_after INTEGER DEFAULT 0,
    reference_type VARCHAR(40),
    reference_id VARCHAR(64),
    created_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_points_entries_entry_id ON customer_points_entries (entry_id);
CREATE INDEX IF NOT EXISTS ix_customer_points_entries_customer_pk ON customer_points_entries (customer_pk);
CREATE INDEX IF NOT EXISTS ix_customer_points_entries_customer_id ON customer_points_entries (customer_id);
CREATE INDEX IF NOT EXISTS ix_customer_points_entries_user_id ON customer_points_entries (user_id);

CREATE TABLE IF NOT EXISTS id_sequences (
    scope VARCHAR(40) NOT NULL PRIMARY KEY,
    last_value INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_settings (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users (id),
    notif_orders BOOLEAN DEFAULT TRUE,
    notif_products BOOLEAN DEFAULT TRUE,
    notif_grow BOOLEAN DEFAULT TRUE,
    notif_community BOOLEAN DEFAULT TRUE,
    notif_points BOOLEAN DEFAULT TRUE,
    shopping_default_address_id VARCHAR(36),
    shopping_preferences JSON,
    grow_reminders BOOLEAN DEFAULT TRUE,
    plant_care_reminders BOOLEAN DEFAULT TRUE,
    community_notifications BOOLEAN DEFAULT TRUE,
    community_privacy JSON,
    language VARCHAR(10) DEFAULT 'en',
    theme VARCHAR(20) DEFAULT 'system',
    text_size VARCHAR(20) DEFAULT 'medium',
    reduce_motion BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_settings_user_id ON customer_settings (user_id);

CREATE TABLE IF NOT EXISTS customer_plants (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    plant_id VARCHAR(20),
    customer_pk VARCHAR(36) NOT NULL REFERENCES customers (id),
    customer_id VARCHAR(20) NOT NULL REFERENCES customers (customer_id),
    user_id VARCHAR(36) NOT NULL REFERENCES users (id),
    crop_id VARCHAR(36) REFERENCES crops (id),
    nickname VARCHAR(120),
    planted_on VARCHAR(10),
    expected_harvest_on VARCHAR(10),
    quantity INTEGER,
    status VARCHAR(30) DEFAULT 'growing',
    notes TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_customer_plants_plant_id ON customer_plants (plant_id);
CREATE INDEX IF NOT EXISTS ix_customer_plants_customer_pk ON customer_plants (customer_pk);
CREATE INDEX IF NOT EXISTS ix_customer_plants_customer_id ON customer_plants (customer_id);
CREATE INDEX IF NOT EXISTS ix_customer_plants_user_id ON customer_plants (user_id);
CREATE INDEX IF NOT EXISTS ix_customer_plants_crop_id ON customer_plants (crop_id);
"""


def _prime_customer_id_sequence_sqlite(conn) -> None:
    """Start the Customer ID counter above every ID already in the table.

    Only ever raises the counter. On a database that has never issued a Customer
    ID this inserts the seed row and does nothing else; on one that somehow
    already holds customers, it makes sure the next allocation cannot collide
    with them. Safe to run on every boot.
    """
    try:
        highest = 0
        for row in conn.execute(
            "SELECT customer_id FROM customers WHERE customer_id LIKE 'FA-CS-%'"
        ).fetchall():
            digits = "".join(ch for ch in str(row[0] or "") if ch.isdigit())
            if digits:
                highest = max(highest, int(digits))
        conn.execute(
            "INSERT INTO id_sequences (scope, last_value, updated_at) "
            "VALUES ('customer_id', ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(scope) DO UPDATE SET "
            "last_value = CASE WHEN id_sequences.last_value < ? "
            "THEN ? ELSE id_sequences.last_value END",
            (highest, highest, highest),
        )
        logger.info("Customer ID sequence primed at %s", highest)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Customer ID sequence priming failed: %s", exc)


def _ensure_customer_role_sqlite(conn) -> None:
    """Give every pre-customer row an explicit ``farmer`` role.

    Rows created before the customer role existed have ``role IS NULL`` and the
    rest of the application already treats them as farmers, so this records
    that explicitly instead of leaving it to a default. It never touches a row
    that already has a role.
    """
    try:
        # TRIM is SQLite's spelling of Postgres' BTRIM. Using btrim here made
        # the whole statement fail, which the catch below swallowed -- the
        # backfill then silently never ran.
        cursor = conn.execute(
            "UPDATE users SET role = 'farmer' WHERE role IS NULL OR TRIM(role) = ''"
        )
        if cursor.rowcount:
            logger.info("Backfilled role='farmer' for %s existing users", cursor.rowcount)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Role backfill failed: %s", exc)


#: Indexes that accelerate case-insensitive filters. The API filters with a
#: pre-lowered value (``lower(column) == value``); a plain index cannot serve
#: that predicate, but an index on the lowercase expression can.
MARKET_PRICE_LC_INDEXES = {
    "market_prices": [
        "ix_market_prices_lc_commodity",
        "ix_market_prices_lc_market",
        "ix_market_prices_lc_state",
        "ix_market_prices_lc_district",
        "ix_market_prices_lc_region",
        "ix_market_prices_lc_category",
    ],
    "market_price_latest": [
        "ix_mkt_latest_lc_commodity",
        "ix_mkt_latest_lc_market",
        "ix_mkt_latest_lc_state",
        "ix_mkt_latest_lc_district",
        "ix_mkt_latest_lc_region",
        "ix_mkt_latest_lc_category",
    ],
}

MARKET_PRICE_LATEST_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS market_price_latest (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    price_id VARCHAR(20),
    variety_key VARCHAR(120),
    commodity VARCHAR(120) NOT NULL,
    variety VARCHAR(120),
    grade VARCHAR(80),
    category VARCHAR(60),
    market VARCHAR(200) NOT NULL,
    district VARCHAR(120),
    state VARCHAR(120),
    region VARCHAR(120),
    min_price FLOAT,
    max_price FLOAT,
    modal_price FLOAT,
    unit VARCHAR(40),
    price_date VARCHAR(10) NOT NULL,
    arrival_date VARCHAR(10),
    arrival_quantity FLOAT,
    source VARCHAR(160) NOT NULL,
    source_url VARCHAR(500),
    source_timestamp VARCHAR(60),
    fetched_at DATETIME,
    created_at DATETIME
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mkt_latest_key ON market_price_latest (market, commodity, variety_key);
CREATE INDEX IF NOT EXISTS ix_mkt_latest_lookup ON market_price_latest (market, commodity, variety_key, price_date);
CREATE INDEX IF NOT EXISTS ix_mkt_latest_geo ON market_price_latest (state, district, region, market);
CREATE INDEX IF NOT EXISTS ix_mkt_latest_commodity ON market_price_latest (commodity);
CREATE INDEX IF NOT EXISTS ix_mkt_latest_market ON market_price_latest (market);
CREATE INDEX IF NOT EXISTS ix_mkt_latest_category ON market_price_latest (category);
CREATE INDEX IF NOT EXISTS ix_mkt_latest_price_date ON market_price_latest (price_date);
CREATE INDEX IF NOT EXISTS ix_mkt_latest_price_id ON market_price_latest (price_id);
CREATE INDEX IF NOT EXISTS ix_mkt_latest_fetched_at ON market_price_latest (fetched_at);
"""


#: Structured crop taxonomy, variety and cultivation-method tables. These are
#: created with ``IF NOT EXISTS`` so the script is safe to run on every boot.
CROP_TAXONOMY_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS crop_categories (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    code VARCHAR(120) NOT NULL UNIQUE,
    domain VARCHAR(80),
    category VARCHAR(80),
    subcategory VARCHAR(80),
    display_name VARCHAR(120),
    description TEXT,
    icon VARCHAR(60),
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME
);
CREATE TABLE IF NOT EXISTS cultivation_methods (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    code VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    is_soil_based BOOLEAN DEFAULT 1,
    is_protected BOOLEAN DEFAULT 0,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME
);
CREATE TABLE IF NOT EXISTS crop_varieties (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    crop_id VARCHAR(36) NOT NULL REFERENCES crops (id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    local_name VARCHAR(150),
    is_hybrid BOOLEAN DEFAULT 0,
    duration_days FLOAT,
    is_custom BOOLEAN DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME
);
CREATE INDEX IF NOT EXISTS ix_crop_varieties_crop_id ON crop_varieties (crop_id);
CREATE INDEX IF NOT EXISTS ix_crops_domain ON crops (domain);
CREATE INDEX IF NOT EXISTS ix_crops_category_id ON crops (category_id);
CREATE INDEX IF NOT EXISTS ix_crops_is_catalog ON crops (is_catalog);
CREATE TABLE IF NOT EXISTS marketplace_crop_listings (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    crop_listing_id VARCHAR(20) UNIQUE,
    listing_id VARCHAR(36) NOT NULL UNIQUE REFERENCES marketplace_listings (id) ON DELETE CASCADE,
    farm_id VARCHAR(36) REFERENCES farms (id),
    plot_id VARCHAR(36) REFERENCES farm_plots (id),
    crop_id VARCHAR(36) REFERENCES crops (id),
    variety_id VARCHAR(36) REFERENCES crop_varieties (id),
    crop_cycle_id VARCHAR(36) REFERENCES crop_cycles (id),
    crop_name VARCHAR(100),
    variety_name VARCHAR(150),
    crop_category VARCHAR(50),
    crop_domain VARCHAR(80),
    growing_season VARCHAR(120),
    harvest_status VARCHAR(30) DEFAULT 'expected',
    expected_harvest_date VARCHAR(20),
    actual_harvest_date VARCHAR(20),
    harvest_quantity FLOAT,
    harvest_unit VARCHAR(20),
    is_advance_sale BOOLEAN DEFAULT 0,
    quality_grade VARCHAR(60),
    size_grade VARCHAR(60),
    freshness VARCHAR(60),
    farming_method VARCHAR(30),
    certification VARCHAR(120),
    moisture_percentage FLOAT,
    packaging_type VARCHAR(80),
    packaging_size VARCHAR(80),
    produce_condition VARCHAR(120),
    storage_condition VARCHAR(120),
    quality_notes TEXT,
    price_unit VARCHAR(20),
    min_order_quantity FLOAT,
    max_order_quantity FLOAT,
    bulk_order_available BOOLEAN DEFAULT 0,
    pickup_available BOOLEAN DEFAULT 1,
    delivery_available BOOLEAN DEFAULT 0,
    pickup_instructions VARCHAR(500),
    delivery_radius VARCHAR(200),
    preferred_buyer_location VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME
);
CREATE INDEX IF NOT EXISTS ix_marketplace_crop_listings_listing_id ON marketplace_crop_listings (listing_id);
CREATE INDEX IF NOT EXISTS ix_marketplace_crop_listings_crop_id ON marketplace_crop_listings (crop_id);
CREATE INDEX IF NOT EXISTS ix_marketplace_crop_listings_crop_name ON marketplace_crop_listings (crop_name);
CREATE INDEX IF NOT EXISTS ix_marketplace_crop_listings_harvest_status ON marketplace_crop_listings (harvest_status);
"""


def _backfill_crop_varieties_sqlite(conn) -> None:
    """Move legacy ``crops.variety`` text into the new ``crop_varieties`` table.

    Older builds stored a single variety directly on the crop row, which meant
    a crop and one of its varieties were the same record. The text column is
    left in place (existing readers still use it) and mirrored into a real
    variety row so the farmer's existing data is not lost and the same crop
    can now carry further varieties without creating duplicate crops.
    """
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"crops", "crop_varieties"} <= tables:
            return
        conn.execute(
            """
            INSERT INTO crop_varieties
                (id, crop_id, name, duration_days, is_custom, is_active, created_at)
            SELECT
                lower(hex(randomblob(16))),
                c.id,
                trim(c.variety),
                c.growth_duration_days,
                0,
                1,
                CURRENT_TIMESTAMP
            FROM crops c
            WHERE c.variety IS NOT NULL
              AND trim(c.variety) <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM crop_varieties v
                  WHERE v.crop_id = c.id AND lower(trim(v.name)) = lower(trim(c.variety))
              )
            """
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Crop variety backfill failed: %s", exc)


def _backfill_hydroponic_targets_sqlite(conn) -> None:
    """Seed ``crops.hydroponic_targets`` for the crops that support soilless work.

    Runs before the catalog seeder on an upgraded database, so hydroponics has
    nutrient targets even if the seeder has not yet repopulated the crop rows.
    Crops already carrying targets are never overwritten, so a farmer-adjusted
    value survives a restart.
    """
    try:
        from app.database.seed_crops import HYDROPONIC_TARGETS

        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "crops" not in tables:
            return
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(crops)").fetchall()
        }
        if "hydroponic_targets" not in columns or "name" not in columns:
            return
        for name, targets in HYDROPONIC_TARGETS.items():
            conn.execute(
                """
                UPDATE crops
                   SET hydroponic_targets = ?
                 WHERE hydroponic_targets IS NULL
                   AND lower(trim(name)) = lower(trim(?))
                """,
                (json.dumps(targets), name),
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Hydroponic target backfill failed: %s", exc)


def _backfill_cycle_farms_sqlite(conn) -> None:
    """Make every crop cycle agree with the farm that owns its plot.

    ``crop_cycles.farm_id`` is required by the model, but rows written by older
    builds either left it empty or pointed it at a different farm than the one
    that owns the plot the crop is planted in. A crop is planted *in* a plot and
    a plot belongs to exactly one farm, so the plot is the authoritative link
    and the cycle is aligned to it here.

    Without this, farm-scoped readers (crop health, calendar, My Farm) filter
    cycles by farm, then by the requested plot, find nothing and answer 404 for
    a crop that plainly exists. Only cycles that actually have a plot are
    touched, and cycles with no plot keep whatever farm they already record.
    """
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not {"crop_cycles", "farm_plots"} <= tables:
            return
        cur = conn.execute(
            """
            UPDATE crop_cycles
               SET farm_id = (
                   SELECT p.farm_id FROM farm_plots p WHERE p.id = crop_cycles.plot_id
               )
             WHERE plot_id IS NOT NULL
               AND plot_id IN (SELECT id FROM farm_plots WHERE farm_id IS NOT NULL)
               AND farm_id IS NOT (
                   SELECT p.farm_id FROM farm_plots p WHERE p.id = crop_cycles.plot_id
               )
            """
        )
        if cur.rowcount and cur.rowcount > 0:
            logger.info("Aligned farm_id on %s crop cycle(s) with their plot", cur.rowcount)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Crop cycle farm backfill failed: %s", exc)


def _rename_production_unit_sqlite(conn) -> None:
    """Move the harvest quantity unit onto an unambiguous column name.

    The harvest record originally stored the yield unit in a column called
    ``unit``, which is also the name of the relationship pointing back at the
    hydroponic unit. The relationship won, so the column never reached the
    database. The value now lives in ``quantity_unit``; any database created by
    that earlier build still has the stray ``unit`` column, so rename it.
    """
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "hydroponic_production_records" not in tables:
            return
        existing = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(hydroponic_production_records)"
            ).fetchall()
        }
        if "quantity_unit" in existing:
            return
        conn.execute(
            "ALTER TABLE hydroponic_production_records "
            "ADD COLUMN quantity_unit VARCHAR(20) DEFAULT 'kg'"
        )
        if "unit" in existing:
            conn.execute(
                "UPDATE hydroponic_production_records SET quantity_unit = unit "
                "WHERE quantity_unit IS NULL AND unit IS NOT NULL"
            )
        logger.info("Added column hydroponic_production_records.quantity_unit")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Hydroponic production unit rename failed: %s", exc)


def _migrate_sqlite(database_url: str) -> None:
    db_path = database_url.replace("sqlite:///", "", 1)
    try:
        conn = sqlite3.connect(db_path)
        try:
            present = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for table, columns in ADDITIVE_COLUMNS.items():
                # A database that predates this table has nothing to alter, and
                # ALTER would raise and abort every later table's migration.
                if table not in present:
                    continue
                existing = {
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                for column, declaration in columns:
                    if column not in existing:
                        conn.execute(
                            f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
                        )
                        logger.info("Added column %s.%s", table, column)
            conn.executescript(MARKET_PRICE_LATEST_SQLITE_DDL)
            conn.executescript(CROP_TAXONOMY_SQLITE_DDL)
            conn.executescript(CUSTOMER_IDENTITY_SQLITE_DDL)
            for table, index_names in MARKET_PRICE_LC_INDEXES.items():
                if table not in present:
                    continue
                lc_cols = {
                    "commodity": "commodity",
                    "market": "market",
                    "state": "state",
                    "district": "district",
                    "region": "region",
                    "category": "category",
                }
                for index_name in index_names:
                    marker = index_name.rsplit("_", 1)[-1]
                    conn.execute(
                        f"CREATE INDEX IF NOT EXISTS {index_name} "
                        f"ON {table} (lower({lc_cols[marker]}))"
                    )
            _backfill_cycle_farms_sqlite(conn)
            _backfill_crop_varieties_sqlite(conn)
            _backfill_hydroponic_targets_sqlite(conn)
            _rename_production_unit_sqlite(conn)
            _ensure_customer_role_sqlite(conn)
            _prime_customer_id_sequence_sqlite(conn)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("SQLite additive migrations failed: %s", exc)


def _backfill_hydroponic_targets_postgres(cur) -> None:
    """Postgres counterpart of :func:`_backfill_hydroponic_targets_sqlite`."""
    try:
        from app.database.seed_crops import HYDROPONIC_TARGETS

        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'crops'"
        )
        columns = {row[0] for row in cur.fetchall()}
        if not {"crops"}.issubset(columns) or "hydroponic_targets" not in columns:
            return
        for name, targets in HYDROPONIC_TARGETS.items():
            cur.execute(
                "UPDATE crops SET hydroponic_targets = %s "
                "WHERE hydroponic_targets IS NULL AND lower(trim(name)) = lower(trim(%s))",
                (json.dumps(targets), name),
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Hydroponic target backfill failed (postgres): %s", exc)


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
                # Skip tables this database never had; ALTER would raise and
                # abort every later table's migration.
                if not existing:
                    continue
                for column, declaration in columns:
                    if column not in existing:
                        pg_type = declaration.upper().replace("VARCHAR", "VARCHAR")
                        cur.execute(
                            f"ALTER TABLE {table} ADD COLUMN {column} {pg_type}"
                        )
                        logger.info("Added column %s.%s (postgres)", table, column)
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'hydroponic_production_records'"
            )
            pg_cols = {row[0] for row in cur.fetchall()}
            if pg_cols and "quantity_unit" not in pg_cols:
                cur.execute(
                    "ALTER TABLE hydroponic_production_records "
                    "ADD COLUMN quantity_unit VARCHAR(20) DEFAULT 'kg'"
                )
                if "unit" in pg_cols:
                    cur.execute(
                        "UPDATE hydroponic_production_records "
                        "SET quantity_unit = unit "
                        "WHERE quantity_unit IS NULL AND unit IS NOT NULL"
                    )
                logger.info("Added column hydroponic_production_records.quantity_unit")
            _backfill_hydroponic_targets_postgres(cur)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crop_categories (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    code VARCHAR(120) NOT NULL UNIQUE,
                    domain VARCHAR(80),
                    category VARCHAR(80),
                    subcategory VARCHAR(80),
                    display_name VARCHAR(120),
                    description TEXT,
                    icon VARCHAR(60),
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cultivation_methods (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    code VARCHAR(60) NOT NULL UNIQUE,
                    name VARCHAR(120) NOT NULL,
                    is_soil_based BOOLEAN DEFAULT TRUE,
                    is_protected BOOLEAN DEFAULT FALSE,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crop_varieties (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    crop_id VARCHAR(36) NOT NULL REFERENCES crops (id) ON DELETE CASCADE,
                    name VARCHAR(150) NOT NULL,
                    local_name VARCHAR(150),
                    is_hybrid BOOLEAN DEFAULT FALSE,
                    duration_days FLOAT,
                    is_custom BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP
                )
            """)
            for idx_sql in (
                "CREATE INDEX IF NOT EXISTS ix_crop_varieties_crop_id ON crop_varieties (crop_id)",
                "CREATE INDEX IF NOT EXISTS ix_crops_domain ON crops (domain)",
                "CREATE INDEX IF NOT EXISTS ix_crops_category_id ON crops (category_id)",
                "CREATE INDEX IF NOT EXISTS ix_crops_is_catalog ON crops (is_catalog)",
            ):
                cur.execute(idx_sql)
            pg_crop_cols = {
                row[0] for row in cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'crops'").fetchall()
            }
            if pg_crop_cols:
                cur.execute("""
                    INSERT INTO crop_varieties
                        (id, crop_id, name, duration_days, is_custom, is_active, created_at)
                    SELECT
                        md5(random()::text || clock_timestamp()::text),
                        c.id,
                        btrim(c.variety),
                        c.growth_duration_days,
                        FALSE,
                        TRUE,
                        CURRENT_TIMESTAMP
                    FROM crops c
                    WHERE c.variety IS NOT NULL
                      AND btrim(c.variety) <> ''
                      AND NOT EXISTS (
                          SELECT 1 FROM crop_varieties v
                          WHERE v.crop_id = c.id AND lower(btrim(v.name)) = lower(btrim(c.variety))
                      )
                """)
            # ---- Marketplace "Sell Crop" listing detail (additive) ----
            cur.execute("""
                CREATE TABLE IF NOT EXISTS marketplace_crop_listings (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    crop_listing_id VARCHAR(20) UNIQUE,
                    listing_id VARCHAR(36) NOT NULL UNIQUE
                        REFERENCES marketplace_listings (id) ON DELETE CASCADE,
                    farm_id VARCHAR(36) REFERENCES farms (id),
                    plot_id VARCHAR(36) REFERENCES farm_plots (id),
                    crop_id VARCHAR(36) REFERENCES crops (id),
                    variety_id VARCHAR(36) REFERENCES crop_varieties (id),
                    crop_cycle_id VARCHAR(36) REFERENCES crop_cycles (id),
                    crop_name VARCHAR(100),
                    variety_name VARCHAR(150),
                    crop_category VARCHAR(50),
                    crop_domain VARCHAR(80),
                    growing_season VARCHAR(120),
                    harvest_status VARCHAR(30) DEFAULT 'expected',
                    expected_harvest_date VARCHAR(20),
                    actual_harvest_date VARCHAR(20),
                    harvest_quantity FLOAT,
                    harvest_unit VARCHAR(20),
                    is_advance_sale BOOLEAN DEFAULT FALSE,
                    quality_grade VARCHAR(60),
                    size_grade VARCHAR(60),
                    freshness VARCHAR(60),
                    farming_method VARCHAR(30),
                    certification VARCHAR(120),
                    moisture_percentage FLOAT,
                    packaging_type VARCHAR(80),
                    packaging_size VARCHAR(80),
                    produce_condition VARCHAR(120),
                    storage_condition VARCHAR(120),
                    quality_notes TEXT,
                    price_unit VARCHAR(20),
                    min_order_quantity FLOAT,
                    max_order_quantity FLOAT,
                    bulk_order_available BOOLEAN DEFAULT FALSE,
                    pickup_available BOOLEAN DEFAULT TRUE,
                    delivery_available BOOLEAN DEFAULT FALSE,
                    pickup_instructions VARCHAR(500),
                    delivery_radius VARCHAR(200),
                    preferred_buyer_location VARCHAR(200),
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            for idx_sql in (
                "CREATE INDEX IF NOT EXISTS ix_marketplace_crop_listings_listing_id "
                "ON marketplace_crop_listings (listing_id)",
                "CREATE INDEX IF NOT EXISTS ix_marketplace_crop_listings_crop_id "
                "ON marketplace_crop_listings (crop_id)",
                "CREATE INDEX IF NOT EXISTS ix_marketplace_crop_listings_crop_name "
                "ON marketplace_crop_listings (crop_name)",
                "CREATE INDEX IF NOT EXISTS ix_marketplace_crop_listings_harvest_status "
                "ON marketplace_crop_listings (harvest_status)",
            ):
                cur.execute(idx_sql)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS market_price_latest (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    price_id VARCHAR(20),
                    variety_key VARCHAR(120),
                    commodity VARCHAR(120) NOT NULL,
                    variety VARCHAR(120),
                    grade VARCHAR(80),
                    category VARCHAR(60),
                    market VARCHAR(200) NOT NULL,
                    district VARCHAR(120),
                    state VARCHAR(120),
                    region VARCHAR(120),
                    min_price FLOAT,
                    max_price FLOAT,
                    modal_price FLOAT,
                    unit VARCHAR(40),
                    price_date VARCHAR(10) NOT NULL,
                    arrival_date VARCHAR(10),
                    arrival_quantity FLOAT,
                    source VARCHAR(160) NOT NULL,
                    source_url VARCHAR(500),
                    source_timestamp VARCHAR(60),
                    fetched_at TIMESTAMP,
                    created_at TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_mkt_latest_key
                ON market_price_latest (market, commodity, variety_key)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS ix_mkt_latest_lookup
                ON market_price_latest (market, commodity, variety_key, price_date)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS ix_mkt_latest_geo
                ON market_price_latest (state, district, region, market)
            """)
            for table, index_names in MARKET_PRICE_LC_INDEXES.items():
                cols = {
                    "commodity": "commodity", "market": "market", "state": "state",
                    "district": "district", "region": "region", "category": "category",
                }
                for index_name in index_names:
                    marker = index_name.rsplit("_", 1)[-1]
                    cur.execute(
                        f"CREATE INDEX IF NOT EXISTS {index_name} "
                        f"ON {table} (lower({cols[marker]}))"
                    )
            # ---- Customer authentication (additive; farmers untouched) ----
            cur.execute(CUSTOMER_IDENTITY_POSTGRES_DDL)
            cur.execute(
                "UPDATE users SET role = 'farmer' WHERE role IS NULL OR btrim(role) = ''"
            )
            cur.execute("""
                INSERT INTO id_sequences (scope, last_value, updated_at)
                VALUES (
                    'customer_id',
                    COALESCE((
                        SELECT MAX(substring(customer_id from '[0-9]+')::int)
                        FROM customers
                        WHERE customer_id LIKE 'FA-CS-%'
                    ), 0),
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (scope) DO UPDATE SET
                    last_value = CASE
                        WHEN id_sequences.last_value < EXCLUDED.last_value
                        THEN EXCLUDED.last_value
                        ELSE id_sequences.last_value
                    END
            """)
            conn.commit()
        finally:
            conn.close()
    except ImportError:
        logger.warning("psycopg2 not installed; skipping PostgreSQL migrations")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("PostgreSQL additive migrations failed: %s", exc)
