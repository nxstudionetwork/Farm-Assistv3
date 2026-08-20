from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Text, Integer, ForeignKey, Boolean, JSON,
    UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class FarmBuzzPost(Base):
    """Post or Short published through the FarmBuzz module."""

    __tablename__ = "farmbuzz_posts"
    __table_args__ = (
        Index("ix_farmbuzz_posts_created", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    content_type = Column(String(10), default="post", index=True)  # post | short
    title = Column(String(300), nullable=True)
    caption = Column(Text, nullable=True)
    media_url = Column(String(600), nullable=True)
    media_type = Column(String(10), default="text")  # image | video | text
    thumbnail_url = Column(String(600), nullable=True)
    location = Column(String(200), nullable=True)
    crop = Column(String(120), nullable=True)
    category = Column(String(60), default="Farming", index=True)
    hashtags = Column(JSON, nullable=True)
    tagged_users = Column(JSON, nullable=True)
    visibility = Column(String(20), default="public")
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    shares_count = Column(Integer, default=0)
    saves_count = Column(Integer, default=0)
    views_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    comments = relationship("FarmBuzzComment", back_populates="post", cascade="all, delete-orphan")


class FarmBuzzComment(Base):
    __tablename__ = "farmbuzz_comments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("farmbuzz_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("FarmBuzzPost", back_populates="comments")
    user = relationship("User")


class FarmBuzzLike(Base):
    __tablename__ = "farmbuzz_likes"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_farmbuzz_like"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("farmbuzz_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FarmBuzzSave(Base):
    __tablename__ = "farmbuzz_saves"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_farmbuzz_save"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("farmbuzz_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FarmBuzzShare(Base):
    __tablename__ = "farmbuzz_shares"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("farmbuzz_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FarmBuzzFollow(Base):
    __tablename__ = "farmbuzz_follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uq_farmbuzz_follow"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    follower_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    following_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FarmBuzzHashtag(Base):
    __tablename__ = "farmbuzz_hashtags"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    tag = Column(String(120), unique=True, index=True, nullable=False)
    post_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class FarmBuzzTrend(Base):
    __tablename__ = "farmbuzz_trends"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    trend_id = Column(String(20), unique=True, index=True)
    topic = Column(String(300), nullable=False)
    category = Column(String(60), default="agriculture", index=True)
    description = Column(Text, nullable=True)
    engagement_score = Column(Integer, default=0)
    icon = Column(String(60), nullable=True)
    extra_data = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
