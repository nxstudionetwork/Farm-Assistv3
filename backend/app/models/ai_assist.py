import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.database.connection import Base

# Enum for sender type
SenderType = Enum('user', 'assistant', name='sender_type')

class AssistedAIConversation(Base):
    __tablename__ = 'ai_conversations'
    __table_args__ = {'extend_existing': True}

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farmer_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    title = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    messages = relationship('AIMessage', back_populates='conversation', cascade='all, delete-orphan')
    attachments = relationship('AIAttachment', back_populates='conversation', cascade='all, delete-orphan')

class AIMessage(Base):
    __tablename__ = 'ai_messages'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(PG_UUID(as_uuid=True), ForeignKey('ai_conversations.id'), nullable=False, index=True)
    farmer_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    sender_type = Column(SenderType, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship('AssistedAIConversation', back_populates='messages')
    attachments = relationship('AIAttachment', back_populates='message', cascade='all, delete-orphan')

class AIAttachment(Base):
    __tablename__ = 'ai_attachments'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(PG_UUID(as_uuid=True), ForeignKey('ai_messages.id'), nullable=False, index=True)
    conversation_id = Column(PG_UUID(as_uuid=True), ForeignKey('ai_conversations.id'), nullable=False, index=True)
    farmer_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=False)
    file_path = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship('AIMessage', back_populates='attachments')
    conversation = relationship('AssistedAIConversation', back_populates='attachments')

class AIMemory(Base):
    __tablename__ = 'ai_memory'

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farmer_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    memory_key = Column(String(200), nullable=False)
    memory_value = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class AISettings(Base):
    __tablename__ = 'ai_settings'

    farmer_id = Column(PG_UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True)
    language = Column(String(20), nullable=True)
    memory_enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
