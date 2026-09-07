from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Float, Integer, ForeignKey, Index,
    UniqueConstraint,
)
from app.database.base import Base
from app.models.farm import gen_uuid


class MarketPrice(Base):
    """Verified agricultural market price record (e.g. AGMARKNET daily mandi prices).

    Rows are only ever created from an external verified source or an official
    CSV import -- never fabricated. Natural key: (source, market, commodity,
    variety, grade, price_date).
    """
    __tablename__ = "market_prices"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    price_id = Column(String(20), unique=True, index=True)

    commodity = Column(String(120), nullable=False, index=True)
    variety = Column(String(120), nullable=True)
    grade = Column(String(80), nullable=True)
    category = Column(String(60), nullable=True, index=True)

    market = Column(String(200), nullable=False, index=True)
    district = Column(String(120), nullable=True, index=True)
    state = Column(String(120), nullable=True, index=True)

    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    modal_price = Column(Float, nullable=True)
    unit = Column(String(40), default="Rs/Quintal")

    price_date = Column(String(10), nullable=False, index=True)  # ISO YYYY-MM-DD
    arrival_date = Column(String(10), nullable=True)

    source = Column(String(160), nullable=False, default="AGMARKNET")
    source_url = Column(String(500), nullable=True)
    source_timestamp = Column(String(60), nullable=True)  # raw date string from source
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "source", "market", "commodity", "variety", "grade", "price_date",
            name="uq_market_price_natural",
        ),
        Index("ix_market_prices_lookup", "commodity", "market", "price_date"),
        Index("ix_market_prices_geo", "state", "district", "market"),
    )


class MarketWatchlist(Base):
    """Farmer-saved commodity/market pairs. Strictly private per user."""
    __tablename__ = "market_watchlist"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    watch_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    commodity = Column(String(120), nullable=False)
    market = Column(String(200), nullable=True)
    district = Column(String(120), nullable=True)
    state = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "commodity", "market", name="uq_watchlist_entry"),
    )


class MarketPriceAlert(Base):
    """Farmer price alert. Evaluated against real market data whenever a new
    sync/import lands; a triggered alert creates a real Notification."""
    __tablename__ = "market_price_alerts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    alert_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    commodity = Column(String(120), nullable=False)
    market = Column(String(200), nullable=True)
    target_price = Column(Float, nullable=False)
    condition = Column(String(10), nullable=False, default="above")  # above | below
    status = Column(String(20), default="active", index=True)  # active | triggered | paused
    last_checked_at = Column(DateTime, nullable=True)
    last_triggered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MarketDataSync(Base):
    """Audit log of market-data fetch/import attempts. Powers honest
    freshness labels ("Live", "Latest available", "Unavailable")."""
    __tablename__ = "market_data_syncs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    status = Column(String(20), nullable=False, index=True)  # success | failed | not_configured | cached
    trigger = Column(String(20), default="api")  # api | scheduler | csv_import
    source = Column(String(160), nullable=True)
    records_fetched = Column(Integer, default=0)
    records_stored = Column(Integer, default=0)
    message = Column(String(500), nullable=True)
    synced_at = Column(DateTime, default=datetime.utcnow, index=True)
