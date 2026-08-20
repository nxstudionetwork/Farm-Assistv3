from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Text, Integer
)
from sqlalchemy.orm import relationship
from app.database.base import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String(36), primary_key=True)
    feedback_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farmer_id = Column(String(20), nullable=False)
    name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=True)
    feedback_type = Column(String(50), nullable=False)
    rating = Column(Integer, nullable=False)
    message = Column(Text, nullable=False)
    related_page = Column(String(100), nullable=True)
    status = Column(String(20), default="new")
    admin_reply = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="feedback_entries")
