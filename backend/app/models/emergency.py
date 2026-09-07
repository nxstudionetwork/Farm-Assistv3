import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.database.connection import Base

# Emergency types could be enum, but keep as string for flexibility

class EmergencyReport(Base):
    __tablename__ = "farm_emergency_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    reference_id = Column(String(20), nullable=True, index=True)
    farmer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    emergency_type = Column(String, nullable=False)
    urgency = Column(String, nullable=False)
    location = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    contact_phone = Column(String(15), nullable=False)
    reference_name = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="submitted")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    farmer = relationship("User", backref="emergency_reports")
