from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Float, Integer, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship
from app.database.base import Base


def gen_uuid():
    import uuid
    return str(uuid.uuid4())


class Farm(Base):
    __tablename__ = "farms"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    farm_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_name = Column(String(200), nullable=False)
    address = Column(String(500), nullable=True)
    village = Column(String(100), nullable=True)
    mandal = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    total_area = Column(Float, nullable=True)
    area_unit = Column(String(20), default="Acres")
    soil_type = Column(String(50), nullable=True)
    water_source = Column(String(100), nullable=True)
    irrigation_method = Column(String(100), nullable=True)
    farm_type = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="farms")
    plots = relationship("FarmPlot", back_populates="farm", cascade="all, delete-orphan")
    documents = relationship("FarmDocument", back_populates="farm", cascade="all, delete-orphan")
    crop_cycles = relationship("CropCycle", back_populates="farm")
    transactions = relationship("Transaction", back_populates="farm")
    worker_bookings = relationship("WorkerBooking", back_populates="farm")
    insurance_policies = relationship("InsurancePolicy", back_populates="farm")
    insurance_claims = relationship("InsuranceClaim", back_populates="farm")
    service_requests = relationship("ServiceRequest", back_populates="farm")


class FarmPlot(Base):
    __tablename__ = "farm_plots"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    plot_id = Column(String(20), unique=True, index=True)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    plot_name = Column(String(200), nullable=False)
    area = Column(Float, nullable=True)
    boundary_coordinates = Column(JSON, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    soil_type = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farm = relationship("Farm", back_populates="plots")
    crop_cycles = relationship("CropCycle", back_populates="plot")


class FarmDocument(Base):
    __tablename__ = "farm_documents"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(String(20), unique=True, index=True)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    document_type = Column(String(50), nullable=False)
    document_name = Column(String(200), nullable=True)
    file_url = Column(String(500), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    verification_status = Column(String(20), default="pending")

    farm = relationship("Farm", back_populates="documents")
