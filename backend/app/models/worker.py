from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, Integer, ForeignKey, Text, JSON, Boolean
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class Worker(Base):
    __tablename__ = "workers"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    worker_id = Column(String(20), unique=True, index=True)
    full_name = Column(String(200), nullable=False)
    phone_number = Column(String(15), nullable=True)
    profile_image = Column(String(500), nullable=True)
    village = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    skills = Column(JSON, nullable=True)
    experience_years = Column(Float, nullable=True)
    hourly_rate = Column(Float, nullable=True)
    daily_rate = Column(Float, nullable=True)
    rating = Column(Float, default=0.0)
    total_reviews = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    is_available = Column(Boolean, default=True)
    bio = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bookings = relationship("WorkerBooking", back_populates="worker")
    availability = relationship("WorkerAvailability", back_populates="worker")
    reviews = relationship("WorkerReview", back_populates="worker")


class WorkerAvailability(Base):
    __tablename__ = "worker_availability"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    worker_id = Column(String(36), ForeignKey("workers.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    start_time = Column(String(10), nullable=True)
    end_time = Column(String(10), nullable=True)
    is_available = Column(Boolean, default=True)

    worker = relationship("Worker", back_populates="availability")


class WorkerBooking(Base):
    __tablename__ = "worker_bookings"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    booking_id = Column(String(20), unique=True, index=True)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    worker_id = Column(String(36), ForeignKey("workers.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    work_type = Column(String(100), nullable=True)
    booking_date = Column(String(10), nullable=True)
    start_time = Column(String(10), nullable=True)
    end_time = Column(String(10), nullable=True)
    duration_days = Column(Integer, default=1)
    hours_per_day = Column(Float, nullable=True)
    subtotal = Column(Float, nullable=True)
    gst_amount = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    status = Column(String(20), default="pending")
    notes = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_by = Column(String(30), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    missed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farmer = relationship("User", foreign_keys=[farmer_id], back_populates="worker_bookings_made")
    worker = relationship("Worker", back_populates="bookings")
    farm = relationship("Farm", back_populates="worker_bookings")
    status_history = relationship(
        "WorkerBookingStatusHistory",
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="WorkerBookingStatusHistory.created_at",
    )


class WorkerPayment(Base):
    __tablename__ = "worker_payments"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    booking_id = Column(String(36), ForeignKey("worker_bookings.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(50), nullable=True)
    payment_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="completed")


class WorkerReview(Base):
    __tablename__ = "worker_reviews"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    worker_id = Column(String(36), ForeignKey("workers.id"), nullable=False)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    rating = Column(Float, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    worker = relationship("Worker", back_populates="reviews")


class WorkerBookingStatusHistory(Base):
    """Immutable audit trail of every worker-booking status change.

    Kept deliberately small and append-only so the current status and the
    reason/author behind it are always explainable (Missed vs Cancelled vs
    Completed, who did it, and when).
    """

    __tablename__ = "worker_booking_status_history"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    booking_id = Column(String(36), ForeignKey("worker_bookings.id"), nullable=False, index=True)
    previous_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    note = Column(Text, nullable=True)
    changed_by = Column(String(30), default="farmer")  # farmer | worker | system
    created_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("WorkerBooking", back_populates="status_history")


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    equipment_id = Column(String(20), unique=True, index=True)
    name = Column(String(200), nullable=False)
    type = Column(String(100), nullable=False)
    brand = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    daily_rate = Column(Float, nullable=True)
    hourly_rate = Column(Float, nullable=True)
    deposit_amount = Column(Float, nullable=True)
    min_duration_days = Column(Integer, default=1)
    rental_terms = Column(Text, nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    is_available = Column(Boolean, default=True)
    location = Column(String(200), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    image_url = Column(String(500), nullable=True)
    condition = Column(String(30), nullable=True)
    listing_status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)


class EquipmentBooking(Base):
    __tablename__ = "equipment_bookings"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    booking_id = Column(String(20), unique=True, index=True)
    equipment_id = Column(String(36), ForeignKey("equipment.id"), nullable=False)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    booking_date = Column(String(10), nullable=True)
    start_time = Column(String(10), nullable=True)
    end_time = Column(String(10), nullable=True)
    duration_days = Column(Integer, default=1)
    total_cost = Column(Float, nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
