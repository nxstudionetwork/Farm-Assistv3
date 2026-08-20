import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, Integer, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from app.database.base import Base


def gen_uuid():
    return str(uuid.uuid4())


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    conversation_id = Column(String(20), unique=True, index=True)
    type = Column(String(10), nullable=False, default="direct")
    name = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    participants = relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_read_at = Column(DateTime, nullable=True)

    conversation = relationship("Conversation", back_populates="participants")
    user = relationship("User")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    message_id = Column(String(20), unique=True, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False)
    sender_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(String(10), nullable=False, default="text")
    attachment_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User")
    reactions = relationship("MessageReaction", back_populates="message", cascade="all, delete-orphan")


class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    message_id = Column(String(36), ForeignKey("messages.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    emoji = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("Message", back_populates="reactions")
    user = relationship("User")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    contact_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    nickname = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    contact_user = relationship("User", foreign_keys=[contact_user_id])


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    attachment_id = Column(String(20), unique=True, index=True)
    message_id = Column(String(36), ForeignKey("messages.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer, nullable=True)
    file_url = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("Message")
