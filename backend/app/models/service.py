from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Float, ForeignKey, Text, Integer
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class AgriculturalService(Base):
    __tablename__ = "agricultural_services"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    service_id = Column(String(20), unique=True, index=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)
    full_description = Column(Text, nullable=True)
    deliverables = Column(Text, nullable=True)
    eligibility = Column(String(300), nullable=True)
    service_duration = Column(String(100), nullable=True)
    required_documents = Column(String(300), nullable=True)
    icon = Column(String(50), default="fa-concierge-bell")
    image_url = Column(String(500), nullable=True)
    color = Column(String(20), default="#1B5E3F")
    availability = Column(String(20), default="available")  # available, busy, limited
    response_time = Column(String(50), default="24 hours")
    price_info = Column(String(100), nullable=True)
    provider_name = Column(String(200), nullable=True)
    location_coverage = Column(String(200), default="All Districts")
    rating = Column(Float, default=4.8)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    requests = relationship("ServiceRequest", back_populates="service")


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    service_request_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    service_id = Column(String(36), ForeignKey("agricultural_services.id"), nullable=True)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    service_name = Column(String(200), nullable=False)
    service_category = Column(String(50), nullable=True)
    contact_name = Column(String(200), nullable=True)
    contact_phone = Column(String(15), nullable=True)
    description = Column(Text, nullable=True)
    location = Column(String(200), nullable=True)
    preferred_date = Column(DateTime, nullable=True)
    preferred_time = Column(String(50), nullable=True)
    budget_min = Column(Float, nullable=True)
    budget_max = Column(Float, nullable=True)
    urgency = Column(String(20), default="normal")
    is_custom = Column(Boolean, default=False)
    status = Column(String(20), default="pending")
    assigned_expert = Column(String(200), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    estimated_response_time = Column(String(50), nullable=True)
    rating = Column(Integer, nullable=True)
    rating_feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="service_requests")
    farm = relationship("Farm", back_populates="service_requests")
    service = relationship("AgriculturalService", back_populates="requests")

