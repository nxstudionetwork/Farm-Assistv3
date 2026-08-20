from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, ForeignKey, Text, JSON, Boolean
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class WeatherCache(Base):
    __tablename__ = "weather_cache"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    data = Column(JSON, nullable=False)
    weather_type = Column(String(20), default="current")
    fetched_at = Column(DateTime, default=datetime.utcnow)


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    conversation_id = Column(String(20), index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    model = Column(String(50), nullable=True)
    tokens_used = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    recommendation_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(20), default="medium")
    is_read = Column(Boolean, default=False)
    is_applied = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
