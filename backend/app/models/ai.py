from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, ForeignKey, Text, JSON, Boolean
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class AIConversationRecord(Base):
    """Persistent conversation metadata (title, timestamps, share token)."""
    __tablename__ = "ai_conversation_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    conversation_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), default="New Chat")
    is_shared = Column(Boolean, default=False)
    share_token = Column(String(64), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AISettingsRecord(Base):
    """Persisted AI chat settings per user."""
    __tablename__ = "ai_settings_records"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    language = Column(String(20), default="en")
    response_style = Column(String(20), default="friendly")
    appearance = Column(String(20), default="system")
    chat_history_enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WeatherCache(Base):
    __tablename__ = "weather_cache"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    data = Column(JSON, nullable=False)
    weather_type = Column(String(20), default="current")
    fetched_at = Column(DateTime, default=datetime.utcnow)


class AIConversation(Base):
    __tablename__ = "legacy_ai_conversations"
    __table_args__ = {'extend_existing': True}

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
