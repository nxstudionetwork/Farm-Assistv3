from sqlalchemy import Column, String, DateTime, Text, Boolean, Enum
from datetime import datetime
from app.database.base import Base
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class SupportRequest(Base):
    __tablename__ = "support_requests"
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), nullable=False)
    subject = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="open")  # could be open, in_progress, closed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
