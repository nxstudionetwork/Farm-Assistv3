import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, Float, Integer, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.database.base import Base


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    farmer_id = Column(String(20), unique=True, index=True)
    full_name = Column(String(200), nullable=False)
    phone_number = Column(String(15), unique=True, index=True)
    email = Column(String(200), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    profile_image = Column(String(500), nullable=True)
    preferred_language = Column(String(10), default="en")
    role = Column(String(20), default="farmer")
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farmer_profile = relationship("FarmerProfile", back_populates="user", uselist=False)
    addresses = relationship("UserAddress", back_populates="user")
    farms = relationship("Farm", back_populates="user")
    login_history = relationship("LoginHistory", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    orders = relationship("MarketplaceOrder", back_populates="user")
    community_posts = relationship("CommunityPost", back_populates="user")
    consultations = relationship("Consultation", foreign_keys="Consultation.farmer_id", back_populates="farmer")
    scheme_applications = relationship("SchemeApplication", back_populates="farmer")
    insurance_policies = relationship("InsurancePolicy", back_populates="user")
    insurance_claims = relationship("InsuranceClaim", back_populates="user")
    worker_bookings_made = relationship("WorkerBooking", foreign_keys="WorkerBooking.farmer_id", back_populates="farmer")
    service_requests = relationship("ServiceRequest", back_populates="user")


class FarmerProfile(Base):
    __tablename__ = "farmer_profiles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    farmer_id = Column(String(20), unique=True, index=True)
    date_of_birth = Column(String(10), nullable=True)
    gender = Column(String(10), nullable=True)
    occupation = Column(String(100), nullable=True)
    farming_experience = Column(String(50), nullable=True)
    preferred_crops = Column(String(500), nullable=True)
    aadhaar_number = Column(String(12), unique=True, index=True, nullable=True)
    pan_number = Column(String(10), unique=True, index=True, nullable=True)
    irrigation_type = Column(String(100), nullable=True)
    bio = Column(Text, nullable=True)
    farm_location = Column(String(200), nullable=True)
    farming_type = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="farmer_profile")


class UserAddress(Base):
    __tablename__ = "user_addresses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    address_line = Column(String(500), nullable=True)
    village = Column(String(100), nullable=True)
    mandal = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(50), default="India")
    pincode = Column(String(10), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_primary = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="addresses")


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    phone = Column(String(15), nullable=False)
    email = Column(String(200), nullable=True)
    otp_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class LoginHistory(Base):
    __tablename__ = "login_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    login_time = Column(DateTime, default=datetime.utcnow)
    logout_time = Column(DateTime, nullable=True)
    device = Column(String(200), nullable=True)
    browser = Column(String(100), nullable=True)
    ip_address = Column(String(45), nullable=True)
    login_status = Column(String(20), default="success")

    user = relationship("User", back_populates="login_history")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    token_jti = Column(String(100), unique=True, index=True)
    device = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
