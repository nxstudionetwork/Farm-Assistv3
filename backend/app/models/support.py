from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from app.database.base import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(String(36), primary_key=True)
    ticket_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farmer_id = Column(String(20), nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    subject = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), default="open")
    admin_reply = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="support_tickets")
