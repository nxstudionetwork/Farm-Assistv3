from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Text, Boolean, ForeignKey
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    news_id = Column(String(20), unique=True, index=True)
    external_id = Column(String(200), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    image_url = Column(String(1000), nullable=True)
    source_name = Column(String(200), nullable=False)
    source_url = Column(String(500), nullable=True)
    article_url = Column(String(1000), nullable=True)
    author = Column(String(200), nullable=True)
    category = Column(String(50), nullable=False, default="general")
    region = Column(String(100), nullable=True)
    is_breaking = Column(Boolean, default=False)
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    cached_at = Column(DateTime, default=datetime.utcnow)


class SavedNews(Base):
    __tablename__ = "saved_news"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    saved_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    news_id = Column(String(36), ForeignKey("news_articles.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="saved_news")
    article = relationship("NewsArticle")
