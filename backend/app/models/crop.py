from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class Crop(Base):
    __tablename__ = "crops"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    crop_id = Column(String(20), unique=True, index=True)
    name = Column(String(100), nullable=False)
    variety = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)
    season = Column(String(50), nullable=True)
    growth_duration_days = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    crop_cycles = relationship("CropCycle", back_populates="crop")


class CropCycle(Base):
    __tablename__ = "crop_cycles"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    cycle_id = Column(String(20), unique=True, index=True)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=False)
    sowing_date = Column(String(10), nullable=True)
    expected_harvest_date = Column(String(10), nullable=True)
    actual_harvest_date = Column(String(10), nullable=True)
    current_stage = Column(String(50), nullable=True)
    seed_quantity = Column(Float, nullable=True)
    seed_unit = Column(String(20), nullable=True)
    fertilizer_usage = Column(Text, nullable=True)
    pesticide_usage = Column(Text, nullable=True)
    irrigation_schedule = Column(Text, nullable=True)
    yield_quantity = Column(Float, nullable=True)
    yield_unit = Column(String(20), nullable=True)
    revenue = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farm = relationship("Farm", back_populates="crop_cycles")
    plot = relationship("FarmPlot", back_populates="crop_cycles")
    crop = relationship("Crop", back_populates="crop_cycles")
    tasks = relationship("CropTask", back_populates="crop_cycle", cascade="all, delete-orphan")


class CropTask(Base):
    __tablename__ = "crop_tasks"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    task_id = Column(String(20), unique=True, index=True)
    crop_cycle_id = Column(String(36), ForeignKey("crop_cycles.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)
    due_date = Column(String(10), nullable=True)
    due_time = Column(String(10), nullable=True)
    status = Column(String(20), default="pending")
    priority = Column(String(20), default="medium")
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    crop_cycle = relationship("CropCycle", back_populates="tasks")


class FarmJournal(Base):
    __tablename__ = "farm_journal"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    activity = Column(String(200), nullable=False)
    notes = Column(Text, nullable=True)
    entry_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class SoilRecord(Base):
    __tablename__ = "soil_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=False)
    ph_level = Column(Float, nullable=True)
    nitrogen = Column(Float, nullable=True)
    phosphorus = Column(Float, nullable=True)
    potassium = Column(Float, nullable=True)
    organic_matter = Column(Float, nullable=True)
    moisture = Column(Float, nullable=True)
    soil_type = Column(String(50), nullable=True)
    test_date = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)


class IrrigationRecord(Base):
    __tablename__ = "irrigation_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=False)
    method = Column(String(50), nullable=True)
    duration_minutes = Column(Float, nullable=True)
    water_quantity = Column(Float, nullable=True)
    water_unit = Column(String(20), nullable=True)
    irrigation_date = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)
