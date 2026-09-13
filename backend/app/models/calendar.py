from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Boolean, Text, ForeignKey, Integer
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class CalendarEvent(Base):
    """Central calendar event for the entire Farm Assist application.

    Events are either created manually by the farmer or automatically synced
    from other modules (tasks, consultations, services, orders, etc.) via
    source_type + source_id deduplication.
    """
    __tablename__ = "calendar_events"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    event_id = Column(String(20), unique=True, index=True)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Core event data
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(String(50), nullable=False, index=True)
    # task | consultation | service | worker | equipment | order | scheme |
    # insurance | crop_activity | learning | document | weather | manual

    # Timing
    start_datetime = Column(DateTime, nullable=True)
    end_datetime = Column(DateTime, nullable=True)
    all_day = Column(Boolean, default=False)

    # Status and priority
    status = Column(String(20), default="scheduled", index=True)
    # scheduled | completed | cancelled | overdue | pending
    priority = Column(String(20), default="normal")
    # low | normal | high | urgent

    # Context: farm / plot / crop
    farm_id = Column(String(36), nullable=True)
    farm_name = Column(String(200), nullable=True)
    plot_id = Column(String(36), nullable=True)
    plot_name = Column(String(200), nullable=True)
    crop_id = Column(String(36), nullable=True)
    crop_name = Column(String(200), nullable=True)

    # Source tracking for auto-synced events
    source_type = Column(String(50), nullable=True, index=True)
    source_id = Column(String(100), nullable=True, index=True)
    # (source_type, source_id) is the dedup key for auto-synced events

    # Link to the source page in the frontend
    source_page = Column(String(200), nullable=True)
    # e.g. "tasks.html?id=...", "expert.html?consult=..."

    # Reminder configuration (JSON string: e.g. "15m,1h,1d")
    reminder_config = Column(String(200), nullable=True)
    reminder_fired = Column(Boolean, default=False)

    # Repeat / recurrence
    recurrence = Column(String(50), nullable=True)
    # null | daily | weekly | monthly | custom

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farmer = relationship("User")
