from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Float, Integer, Text
)
from app.database.base import Base


def gen_uuid():
    import uuid
    return str(uuid.uuid4())


class UserDocument(Base):
    __tablename__ = "user_documents"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), index=True, nullable=False)
    farmer_id = Column(String(20), index=True, nullable=False)
    document_name = Column(String(200), nullable=False)
    document_category = Column(String(50), nullable=False, default="Other")
    file_type = Column(String(20), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    file_url = Column(String(500), nullable=True)
    file_path = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="active")
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
