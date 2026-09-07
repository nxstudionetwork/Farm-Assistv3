from sqlalchemy import Column, Integer, String, Text, Date, Time, Enum, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from backend.app.db.base import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey('farmers.id'), nullable=False)
    farm_id = Column(Integer, ForeignKey('farms.id'), nullable=True)
    plot_id = Column(Integer, ForeignKey('plots.id'), nullable=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=False)  # task type/category
    due_date = Column(Date, nullable=False)
    due_time = Column(Time, nullable=True)
    priority = Column(Enum('low', 'medium', 'high', name='task_priority'), nullable=False, default='medium')
    status = Column(Enum('pending', 'in_progress', 'completed', name='task_status'), nullable=False, default='pending')
    reminder_offset = Column(String, nullable=True)  # e.g., "15m", "1h"
    is_deleted = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    farmer = relationship('Farmer', back_populates='tasks')
    farm = relationship('Farm', back_populates='tasks')
    plot = relationship('Plot', back_populates='tasks')
