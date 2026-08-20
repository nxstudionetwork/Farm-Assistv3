from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Float, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class ServiceRequest(Base):
    __tablename__ = "service_requests"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    service_request_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    service_name = Column(String(200), nullable=False)
    service_category = Column(String(50), nullable=True)
    contact_name = Column(String(200), nullable=True)
    contact_phone = Column(String(15), nullable=True)
    description = Column(Text, nullable=True)
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="service_requests")
    farm = relationship("Farm", back_populates="service_requests")
