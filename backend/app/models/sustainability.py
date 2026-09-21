"""Sustainability-extension models.

These tables extend the real, already-existing soil and irrigation data
(``SoilRecord`` / ``IrrigationRecord`` in ``app.models.crop``) with the two
sustainability domains that are NOT yet tracked anywhere: on-farm energy usage
and sustainable farming practices. Water usage is deliberately NOT duplicated
here -- it is read from the existing ``irrigation_records`` table so a farmer's
water numbers always match what they log on the Soil & Irrigation page.

All tables are owner-scoped (``farm_id``/``plot_id``) and every read goes
through the authenticated farmer, mirroring the rest of the app.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database.connection import Base


def _now() -> datetime:
    return datetime.utcnow()


class EnergyUsageRecord(Base):
    """A single energy-use event (e.g. pump hours, solar consumption, fuel use).

    Uniqueness: one record per (farm, plot, energy_type, usage_date) so that
    re-saving the same day does not double-count totals.
    """

    __tablename__ = "energy_usage_records"
    __table_args__ = (
        UniqueConstraint(
            "farm_id", "plot_id", "energy_type", "usage_date",
            name="uq_energy_farm_plot_type_date",
        ),
    )

    id = Column(String, primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    farmer_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_id = Column(String, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    plot_id = Column(String, ForeignKey("farm_plots.id", ondelete="CASCADE"), nullable=True, index=True)
    energy_type = Column(String(50), nullable=False)          # electricity | fuel | solar | diesel | other
    source = Column(String(80), nullable=True)                # grid | solar_panel | generator | ...
    quantity = Column(Float, nullable=False, default=0.0)     # value
    unit = Column(String(20), nullable=False, default="kWh")  # kWh | litres | kg
    cost = Column(Float, nullable=True, default=0.0)          # local currency
    usage_date = Column(DateTime, nullable=False, default=_now, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)


class SustainablePracticeRecord(Base):
    """A sustainability practice actively applied on a plot (cover cropping,
    composting, drip irrigation, crop rotation, mulching, IPM, ...).
    """

    __tablename__ = "sustainable_practice_records"
    __table_args__ = (
        UniqueConstraint("farm_id", "plot_id", "practice_name", name="uq_practice_farm_plot_name"),
    )

    id = Column(String, primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    farmer_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_id = Column(String, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    plot_id = Column(String, ForeignKey("farm_plots.id", ondelete="CASCADE"), nullable=True, index=True)
    practice_name = Column(String(120), nullable=False)       # e.g. "Cover Cropping"
    category = Column(String(60), nullable=False, default="soil")  # soil | water | energy | waste | biodiversity
    status = Column(String(30), nullable=False, default="active")  # active | planned | completed
    area_hectares = Column(Float, nullable=True)              # area the practice covers
    started_on = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)


class SustainabilityProfileRecord(Base):
    """A snapshot of aggregate sustainability metrics for a farm.

    Computed server-side from the farmer's real soil + irrigation + energy +
    practice records (never from hardcoded values). Used for the dashboard's
    summary cards; refreshed when the farmer saves a new record.
    """

    __tablename__ = "sustainability_profiles"
    __table_args__ = (
        UniqueConstraint("farm_id", "snapshot_date", name="uq_sust_profile_farm_date"),
    )

    id = Column(String, primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    farmer_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_id = Column(String, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date = Column(DateTime, nullable=False, default=_now, index=True)

    # Real computed aggregates (zero if no underlying records exist yet).
    soil_avg_ph = Column(Float, nullable=True)
    soil_avg_moisture = Column(Float, nullable=True)
    soil_avg_organic_matter = Column(Float, nullable=True)
    water_total_litres = Column(Float, nullable=False, default=0.0)
    water_days = Column(Integer, nullable=False, default=0)
    energy_total = Column(Float, nullable=False, default=0.0)
    energy_unit = Column(String(20), nullable=False, default="kWh")
    practice_count = Column(Integer, nullable=False, default=0)
    water_consumption_score = Column(Integer, nullable=True)   # 0-100, real-data derived
    energy_score = Column(Integer, nullable=True)              # 0-100, real-data derived
    soil_score = Column(Integer, nullable=True)                # 0-100, real-data derived
    overall_score = Column(Integer, nullable=True)             # 0-100 composite
    created_at = Column(DateTime, default=_now)
