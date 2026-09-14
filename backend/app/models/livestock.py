"""
Livestock Management Models for Farm Assist.
All records are strictly scoped to an authenticated farmer via user_id.
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, Float, Integer, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.database.base import Base


def _uuid():
    return str(uuid.uuid4())


class Livestock(Base):
    __tablename__ = "livestock"

    id = Column(String(36), primary_key=True, default=_uuid)
    animal_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Identity
    name = Column(String(200), nullable=False)
    tag_id = Column(String(100), nullable=True)
    animal_type = Column(String(50), nullable=False)   # cow, buffalo, goat, sheep, poultry, pig, other
    breed = Column(String(100), nullable=True)
    gender = Column(String(10), nullable=True)         # male, female
    date_of_birth = Column(String(10), nullable=True)  # YYYY-MM-DD string
    weight_kg = Column(Float, nullable=True)
    color = Column(String(100), nullable=True)

    # Acquisition
    source = Column(String(200), nullable=True)        # purchased, born, gifted
    purchase_date = Column(String(10), nullable=True)
    purchase_price = Column(Float, nullable=True)

    # Location
    location = Column(String(200), nullable=True)      # shed / field / barn

    # Health summary
    health_status = Column(String(30), default="healthy")  # healthy, monitoring, needs_attention, critical

    # Photo
    photo_url = Column(String(500), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    health_records = relationship("LivestockHealthRecord", back_populates="animal", cascade="all, delete-orphan")
    vaccinations = relationship("LivestockVaccination", back_populates="animal", cascade="all, delete-orphan")
    treatments = relationship("LivestockTreatment", back_populates="animal", cascade="all, delete-orphan")
    feeding_records = relationship("LivestockFeedingRecord", back_populates="animal", cascade="all, delete-orphan")
    breeding_records = relationship("LivestockBreedingRecord", back_populates="animal", cascade="all, delete-orphan")
    weight_records = relationship("LivestockWeightRecord", back_populates="animal", cascade="all, delete-orphan")
    production_records = relationship("LivestockProductionRecord", back_populates="animal", cascade="all, delete-orphan")
    expense_records = relationship("LivestockExpenseRecord", back_populates="animal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_livestock_user_type", "user_id", "animal_type"),
        Index("ix_livestock_user_status", "user_id", "health_status"),
    )


class LivestockHealthRecord(Base):
    __tablename__ = "livestock_health_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    record_id = Column(String(20), unique=True, index=True)
    animal_id = Column(String(36), ForeignKey("livestock.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    record_date = Column(String(10), nullable=True)
    health_status = Column(String(30), nullable=True)
    symptoms = Column(Text, nullable=True)
    observation = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=True)
    treatment = Column(Text, nullable=True)
    medicine = Column(String(500), nullable=True)
    veterinarian = Column(String(200), nullable=True)
    follow_up_date = Column(String(10), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    animal = relationship("Livestock", back_populates="health_records")


class LivestockVaccination(Base):
    __tablename__ = "livestock_vaccinations"

    id = Column(String(36), primary_key=True, default=_uuid)
    vacc_id = Column(String(20), unique=True, index=True)
    animal_id = Column(String(36), ForeignKey("livestock.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    vaccine_name = Column(String(200), nullable=False)
    date_given = Column(String(10), nullable=True)
    next_due_date = Column(String(10), nullable=True)
    dose = Column(String(100), nullable=True)
    veterinarian = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(20), default="completed")   # completed, due_soon, overdue

    created_at = Column(DateTime, default=datetime.utcnow)

    animal = relationship("Livestock", back_populates="vaccinations")


class LivestockTreatment(Base):
    __tablename__ = "livestock_treatments"

    id = Column(String(36), primary_key=True, default=_uuid)
    treatment_id = Column(String(20), unique=True, index=True)
    animal_id = Column(String(36), ForeignKey("livestock.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    treatment_date = Column(String(10), nullable=True)
    issue = Column(String(500), nullable=True)
    treatment = Column(Text, nullable=True)
    medicine = Column(String(500), nullable=True)
    veterinarian = Column(String(200), nullable=True)
    status = Column(String(20), default="ongoing")     # ongoing, completed, follow_up
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    animal = relationship("Livestock", back_populates="treatments")


class LivestockFeedingRecord(Base):
    __tablename__ = "livestock_feeding_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    feed_id = Column(String(20), unique=True, index=True)
    animal_id = Column(String(36), ForeignKey("livestock.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    feed_type = Column(String(200), nullable=True)
    quantity = Column(String(100), nullable=True)
    frequency = Column(String(100), nullable=True)
    feeding_time = Column(String(100), nullable=True)
    water_requirement = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    record_date = Column(String(10), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    animal = relationship("Livestock", back_populates="feeding_records")


class LivestockBreedingRecord(Base):
    __tablename__ = "livestock_breeding_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    breeding_id = Column(String(20), unique=True, index=True)
    animal_id = Column(String(36), ForeignKey("livestock.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    breeding_date = Column(String(10), nullable=True)
    method = Column(String(100), nullable=True)       # natural, artificial_insemination
    partner_info = Column(String(500), nullable=True)
    pregnancy_status = Column(String(50), nullable=True)  # not_pregnant, pregnant, delivered
    expected_delivery_date = Column(String(10), nullable=True)
    actual_delivery_date = Column(String(10), nullable=True)
    offspring_count = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    animal = relationship("Livestock", back_populates="breeding_records")


class LivestockWeightRecord(Base):
    __tablename__ = "livestock_weight_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    weight_id = Column(String(20), unique=True, index=True)
    animal_id = Column(String(36), ForeignKey("livestock.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    measurement_date = Column(String(10), nullable=True)
    weight_kg = Column(Float, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    animal = relationship("Livestock", back_populates="weight_records")


class LivestockProductionRecord(Base):
    """Milk / egg / wool / other production records, scoped to farmer + animal."""

    __tablename__ = "livestock_production_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    production_id = Column(String(20), unique=True, index=True)
    animal_id = Column(String(36), ForeignKey("livestock.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    record_date = Column(String(10), nullable=True)          # YYYY-MM-DD
    product_type = Column(String(50), nullable=True)         # milk, eggs, wool, other
    quantity = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)                 # L, kg, pcs, ...
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    animal = relationship("Livestock", back_populates="production_records")


class LivestockExpenseRecord(Base):
    """Livestock-related expenses (feed, vet, medicine, ...), scoped to farmer + animal."""

    __tablename__ = "livestock_expense_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    expense_id = Column(String(20), unique=True, index=True)
    animal_id = Column(String(36), ForeignKey("livestock.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    expense_date = Column(String(10), nullable=True)         # YYYY-MM-DD
    category = Column(String(100), nullable=True)            # feed, veterinary, medicine, ...
    amount = Column(Float, nullable=True)
    vendor = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    animal = relationship("Livestock", back_populates="expense_records")
