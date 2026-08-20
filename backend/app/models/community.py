from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, Integer, ForeignKey, Text, JSON, Boolean
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class CommunityPost(Base):
    __tablename__ = "community_posts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    post_type = Column(String(20), default="text")
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    shares_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="community_posts")
    comments = relationship("CommunityComment", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("CommunityLike", back_populates="post", cascade="all, delete-orphan")


class CommunityComment(Base):
    __tablename__ = "community_comments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("community_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("CommunityPost", back_populates="comments")
    user = relationship("User")


class CommunityLike(Base):
    __tablename__ = "community_likes"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("community_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("CommunityPost", back_populates="likes")
    user = relationship("User")


class Expert(Base):
    __tablename__ = "experts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    expert_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    full_name = Column(String(200), nullable=False)
    speciality = Column(String(200), nullable=False)
    qualification = Column(String(200), nullable=True)
    experience_years = Column(Float, nullable=True)
    profile_image = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)
    consultation_fee = Column(Float, nullable=True)
    rating = Column(Float, default=0.0)
    total_consultations = Column(Integer, default=0)
    is_available = Column(Boolean, default=True)
    location = Column(String(200), nullable=True)
    languages = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Consultation(Base):
    __tablename__ = "consultations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    consultation_id = Column(String(20), unique=True, index=True)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    expert_id = Column(String(36), ForeignKey("experts.id"), nullable=False)
    topic = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    scheduled_date = Column(String(10), nullable=True)
    scheduled_time = Column(String(10), nullable=True)
    status = Column(String(20), default="scheduled")
    notes = Column(Text, nullable=True)
    rating = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    farmer = relationship("User", foreign_keys=[farmer_id], back_populates="consultations")
    expert = relationship("Expert")
