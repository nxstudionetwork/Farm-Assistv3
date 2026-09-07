from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, Integer, ForeignKey, Text, JSON, Boolean,
    UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class CommunityPost(Base):
    """A discussion/question/experience post in the Community module."""

    __tablename__ = "community_posts"
    __table_args__ = (
        Index("ix_community_posts_created", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    community_id = Column(String(36), ForeignKey("community_groups.id"), nullable=True)
    title = Column(String(300), nullable=True)
    content = Column(Text, nullable=False)
    category = Column(String(60), default="General", index=True)
    crop = Column(String(120), nullable=True)
    location = Column(String(200), nullable=True)
    image_url = Column(String(600), nullable=True)
    media_type = Column(String(10), default="text")
    post_type = Column(String(20), default="text")  # text | question | poll
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    shares_count = Column(Integer, default=0)
    saves_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="community_posts")
    community = relationship("CommunityGroup", back_populates="posts")
    comments = relationship("CommunityComment", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("CommunityLike", back_populates="post", cascade="all, delete-orphan")
    answers = relationship("CommunityAnswer", back_populates="post", cascade="all, delete-orphan")
    saves = relationship("CommunitySave", back_populates="post", cascade="all, delete-orphan")

    @property
    def best_answer_count(self):
        return sum(1 for a in self.answers if a.is_best_answer)


class CommunityComment(Base):
    """A comment or reply on a CommunityPost."""

    __tablename__ = "community_comments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("community_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    parent_comment_id = Column(String(36), ForeignKey("community_comments.id"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("CommunityPost", back_populates="comments")
    user = relationship("User")
    replies = relationship("CommunityComment", back_populates="parent", cascade="all, delete-orphan")
    parent = relationship("CommunityComment", remote_side=[id], back_populates="replies")


class CommunityLike(Base):
    """Persistent like on a post. Unique per (post, user)."""

    __tablename__ = "community_likes"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_community_like"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("community_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("CommunityPost", back_populates="likes")
    user = relationship("User")


class CommunitySave(Base):
    """A post saved/bookmarked by a farmer. Unique per (post, user)."""

    __tablename__ = "community_saves"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_community_save"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    post_id = Column(String(36), ForeignKey("community_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("CommunityPost", back_populates="saves")
    user = relationship("User")


class CommunityAnswer(Base):
    """An answer to a question post."""

    __tablename__ = "community_answers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    answer_id = Column(String(20), unique=True, index=True)
    post_id = Column(String(36), ForeignKey("community_posts.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_best_answer = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    post = relationship("CommunityPost", back_populates="answers")
    user = relationship("User")


class CommunityGroup(Base):
    """A topic-based community/group that farmers can join."""

    __tablename__ = "community_groups"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    community_id = Column(String(20), unique=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(60), default="General", index=True)
    icon = Column(String(50), nullable=True)
    color = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    posts = relationship("CommunityPost", back_populates="community")
    members = relationship("CommunityGroupMember", back_populates="group", cascade="all, delete-orphan")


class CommunityGroupMember(Base):
    """Membership between a farmer and a community group. Unique per (group, user)."""

    __tablename__ = "community_group_members"
    __table_args__ = (
        UniqueConstraint("community_id", "user_id", name="uq_community_member"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    community_id = Column(String(36), ForeignKey("community_groups.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("CommunityGroup", back_populates="members")
    user = relationship("User")


class CommunityReport(Base):
    """A user-submitted report on a post or comment."""

    __tablename__ = "community_reports"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    report_id = Column(String(20), unique=True, index=True)
    reporter_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    post_id = Column(String(36), ForeignKey("community_posts.id"), nullable=True)
    comment_id = Column(String(36), ForeignKey("community_comments.id"), nullable=True)
    reason = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    reporter = relationship("User")
    post = relationship("CommunityPost")


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
    consultation_type = Column(String(100), nullable=True)
    consultation_method = Column(String(50), nullable=True)
    farm_id = Column(String(36), nullable=True)
    farm_name = Column(String(200), nullable=True)
    crop_id = Column(String(36), nullable=True)
    crop_name = Column(String(200), nullable=True)
    scheduled_date = Column(String(10), nullable=True)
    scheduled_time = Column(String(10), nullable=True)
    status = Column(String(20), default="scheduled")
    meeting_reference = Column(String(500), nullable=True)
    meeting_location = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    cancel_reason = Column(Text, nullable=True)
    rating = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    farmer = relationship("User", foreign_keys=[farmer_id], back_populates="consultations")
    expert = relationship("Expert")
