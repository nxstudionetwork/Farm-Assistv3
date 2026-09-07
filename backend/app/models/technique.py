from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Float, ForeignKey, Text, Integer, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class Technique(Base):
    __tablename__ = "techniques"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    technique_id = Column(String(20), unique=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(80), nullable=True)
    crop = Column(String(100), nullable=True)
    season = Column(String(30), nullable=True)
    difficulty = Column(String(20), default="beginner")
    duration = Column(String(50), nullable=True)
    cost_level = Column(String(20), nullable=True)
    water_requirement = Column(String(30), nullable=True)
    is_organic = Column(Boolean, default=False)
    materials = Column(Text, nullable=True)
    steps = Column(Text, nullable=True)
    tips = Column(Text, nullable=True)
    benefits = Column(Text, nullable=True)
    precautions = Column(Text, nullable=True)
    common_mistakes = Column(Text, nullable=True)
    suitable_soil = Column(String(200), nullable=True)
    icon = Column(String(50), nullable=True)
    color = Column(String(20), nullable=True)
    image_url = Column(String(500), nullable=True)
    is_published = Column(Boolean, default=True)
    views_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bookmarks = relationship("TechniqueBookmark", back_populates="technique")


class TechniqueBookmark(Base):
    __tablename__ = "technique_bookmarks"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    technique_id = Column(String(36), ForeignKey("techniques.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "technique_id", name="uq_user_technique_bookmark"),
    )

    technique = relationship("Technique", back_populates="bookmarks")
