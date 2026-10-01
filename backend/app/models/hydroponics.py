from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, Integer, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class HydroponicUnit(Base):
    __tablename__ = "hydroponic_units"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    unit_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)

    name = Column(String(200), nullable=False)
    system_type = Column(String(50), nullable=True)
    status = Column(String(30), default="planning")
    setup_location = Column(String(200), nullable=True)
    setup_date = Column(String(10), nullable=True)

    growing_area = Column(Float, nullable=True)
    area_unit = Column(String(20), default="sq ft")
    channels = Column(Integer, nullable=True)
    planting_sites = Column(Integer, nullable=True)
    reservoir_capacity = Column(Float, nullable=True)
    reservoir_unit = Column(String(20), default="Litres")

    water_source = Column(String(100), nullable=True)
    pump_available = Column(Boolean, default=False)
    air_pump_available = Column(Boolean, default=False)
    lighting_setup = Column(String(100), nullable=True)
    protection_structure = Column(String(100), nullable=True)
    automation_available = Column(Boolean, default=False)

    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    crops = relationship(
        "HydroponicCrop", back_populates="unit", cascade="all, delete-orphan"
    )
    water_logs = relationship(
        "HydroponicWaterLog", back_populates="unit", cascade="all, delete-orphan"
    )
    health_records = relationship(
        "HydroponicHealthRecord", back_populates="unit", cascade="all, delete-orphan"
    )
    production_records = relationship(
        "HydroponicProductionRecord", back_populates="unit", cascade="all, delete-orphan"
    )
    farm = relationship("Farm")
    plot = relationship("FarmPlot")


class HydroponicCrop(Base):
    __tablename__ = "hydroponic_crops"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    cycle_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    unit_id = Column(String(36), ForeignKey("hydroponic_units.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    crop_cycle_id = Column(String(36), ForeignKey("crop_cycles.id"), nullable=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=True)

    crop_name = Column(String(100), nullable=False)
    variety = Column(String(100), nullable=True)
    planting_date = Column(String(10), nullable=True)
    expected_harvest_date = Column(String(10), nullable=True)
    actual_harvest_date = Column(String(10), nullable=True)
    plants_count = Column(Integer, nullable=True)
    growing_area = Column(Float, nullable=True)
    area_unit = Column(String(20), default="sq ft")
    expected_yield = Column(Float, nullable=True)
    yield_unit = Column(String(20), default="kg")
    actual_yield = Column(Float, nullable=True)
    current_stage = Column(String(50), nullable=True)
    status = Column(String(20), default="active")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    unit = relationship("HydroponicUnit", back_populates="crops")
    crop = relationship("Crop")
    crop_cycle = relationship("CropCycle")
    production_records = relationship(
        "HydroponicProductionRecord", back_populates="crop"
    )


class HydroponicWaterLog(Base):
    __tablename__ = "hydroponic_water_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    log_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    unit_id = Column(String(36), ForeignKey("hydroponic_units.id"), nullable=False)

    recorded_date = Column(String(10), nullable=True)
    water_quantity = Column(Float, nullable=True)
    water_unit = Column(String(20), default="Litres")
    ph = Column(Float, nullable=True)
    ec = Column(Float, nullable=True)
    tds = Column(Float, nullable=True)
    water_temperature = Column(Float, nullable=True)
    nutrient_solution = Column(String(200), nullable=True)
    nutrient_quantity = Column(Float, nullable=True)
    nutrient_unit = Column(String(20), default="g")
    water_replaced = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    unit = relationship("HydroponicUnit", back_populates="water_logs")


class HydroponicHealthRecord(Base):
    __tablename__ = "hydroponic_health_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    record_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    unit_id = Column(String(36), ForeignKey("hydroponic_units.id"), nullable=False)
    hydroponic_crop_id = Column(
        String(36), ForeignKey("hydroponic_crops.id"), nullable=True
    )
    crop_cycle_id = Column(String(36), ForeignKey("crop_cycles.id"), nullable=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=True)

    observed_date = Column(String(10), nullable=True)
    plant_appearance = Column(String(50), nullable=True)
    leaf_condition = Column(String(50), nullable=True)
    root_condition = Column(String(50), nullable=True)
    growth_rate = Column(String(50), nullable=True)
    deficiency_symptoms = Column(Text, nullable=True)
    pest_observation = Column(Text, nullable=True)
    water_condition = Column(String(50), nullable=True)
    ph_issue = Column(String(50), nullable=True)
    ec_issue = Column(String(50), nullable=True)
    severity = Column(String(20), default="low")
    status = Column(String(30), default="observed")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    unit = relationship("HydroponicUnit", back_populates="health_records")
    crop = relationship("HydroponicCrop")


class HydroponicProductionRecord(Base):
    __tablename__ = "hydroponic_production_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    production_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    unit_id = Column(String(36), ForeignKey("hydroponic_units.id"), nullable=False)
    hydroponic_crop_id = Column(
        String(36), ForeignKey("hydroponic_crops.id"), nullable=True
    )
    crop_cycle_id = Column(String(36), ForeignKey("crop_cycles.id"), nullable=True)

    recorded_date = Column(String(10), nullable=True)
    quantity = Column(Float, nullable=True)
    quantity_unit = Column(String(20), default="kg")
    quality_grade = Column(String(30), nullable=True)
    revenue = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    unit = relationship("HydroponicUnit", back_populates="production_records")
    crop = relationship("HydroponicCrop", back_populates="production_records")
