from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, JSON, Text
)
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.user import generate_uuid


class IdSequence(Base):
    """Database-owned counters used to allocate sequential public IDs.

    ``Farmer ID`` historically allocated its number by scanning the users table
    for the highest value in use. That is a read-modify-write race: two
    concurrent registrations can read the same maximum and be handed the same
    ID. A row here, bumped with a single atomic statement, makes the
    allocation a real database operation instead of a guess that happens to be
    right when nothing else is happening.

    The unique index on the generated ID remains the final authority; this only
    means the common case never has to collide.
    """

    __tablename__ = "id_sequences"

    scope = Column(String(40), primary_key=True)
    last_value = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Customer(Base):
    """The customer counterpart to ``FarmerProfile``.

    Identity lives in ``users`` (credentials, role, verification ledger); this
    table holds the customer-facing profile and, most importantly, the
    customer-facing ``customer_id`` (``FA-CS-000000``) which is what a customer
    types at login. ``user_id`` is one-to-one, so a single authenticated user
    can never own two customer profiles or resolve two customer IDs.
    """

    __tablename__ = "customers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    # Unique + indexed at the column level, matching how farmer_profiles and
    # farmer_profiles.farmer_id declare their identity columns. That gives the
    # database a hard guarantee that one user owns one customer profile and
    # that one Customer ID belongs to one account.
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, index=True, nullable=False)
    customer_id = Column(String(20), unique=True, index=True, nullable=False)
    full_name = Column(String(200), nullable=False)
    # Mirrors of the authenticated contact channels. ``users`` stays
    # authoritative (and is the only place uniqueness is enforced, via its
    # unique indexes); these are refreshed whenever the user's contact details
    # change so customer reads do not have to join through the user row.
    phone_number = Column(String(15), nullable=True, index=True)
    email = Column(String(200), nullable=True, index=True)
    date_of_birth = Column(String(10), nullable=True)
    gender = Column(String(10), nullable=True)
    # pending | phone_verified | email_verified | verified. Never 'verified'
    # without a channel actually having been proven by the OTP service.
    verification_status = Column(String(30), default="pending")
    phone_verified = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)
    # Loyalty balance. Denormalised from customer_points_ledger so the header
    # badge is a single-column read; the ledger is the audit trail.
    points_balance = Column(Integer, nullable=False, default=0)
    preferred_language = Column(String(10), default="en")
    bio = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="customer_profile")
    # CustomerPointsEntry holds two FKs into customers (``customer_pk`` -> the
    # primary key and ``customer_id`` -> the public FA-CS id), so the join has to
    # be stated explicitly. Without it the relationship is ambiguous and
    # configure_mappers() fails for every mapper in the registry, which takes the
    # whole app down, not just this relationship.
    points_entries = relationship(
        "CustomerPointsEntry",
        back_populates="customer",
        cascade="all, delete-orphan",
        foreign_keys="CustomerPointsEntry.customer_pk",
    )


class CustomerPointsEntry(Base):
    """Append-only ledger behind ``Customer.points_balance``.

    Every movement of points produces a row, so the balance shown in the UI is
    always reconstructible rather than an opaque number.
    """

    __tablename__ = "customer_points_entries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    entry_id = Column(String(20), unique=True, index=True)
    customer_pk = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    customer_id = Column(String(20), ForeignKey("customers.customer_id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # Positive credits, negative debits.
    points = Column(Integer, nullable=False)
    reason = Column(String(60), nullable=False)
    balance_after = Column(Integer, nullable=False, default=0)
    reference_type = Column(String(40), nullable=True)
    reference_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship(
        "Customer",
        back_populates="points_entries",
        foreign_keys=[customer_pk],
    )


class CustomerSettings(Base):
    """Customer preferences, kept separate from ``UserSettings``.

    ``UserSettings`` is the Farmer preference sheet: farm defaults, soil type,
    irrigation, weather/task notifications. None of that means anything to
    somebody who shops here, and reusing it would mean either widening a
    farmer-facing table with customer columns or showing a customer the farmer
    screen. This table is its own thing, one row per customer.
    """

    __tablename__ = "customer_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, index=True, nullable=False)

    # Notifications
    notif_orders = Column(Boolean, default=True)
    notif_products = Column(Boolean, default=True)
    notif_grow = Column(Boolean, default=True)
    notif_community = Column(Boolean, default=True)
    notif_points = Column(Boolean, default=True)
    # Shopping
    shopping_default_address_id = Column(String(36), nullable=True)
    shopping_preferences = Column(JSON, nullable=True)
    # Grow
    grow_reminders = Column(Boolean, default=True)
    plant_care_reminders = Column(Boolean, default=True)
    # Community
    community_notifications = Column(Boolean, default=True)
    community_privacy = Column(JSON, nullable=True)
    # App
    language = Column(String(10), default="en")
    theme = Column(String(20), default="system")
    text_size = Column(String(20), default="medium")
    reduce_motion = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")


class CustomerPlant(Base):
    """Something a customer is growing at home.

    The customer's "Grow" tab is deliberately not the Farmer farm module: there
    is no land, no plot, no soil survey and no irrigation record here, because a
    customer is not farming a field. What it does share with the farmer side is
    the crop itself -- ``crop_id`` points at the existing seeded ``crops``
    catalogue, so a customer grows a real variety from the app's own catalogue
    instead of a second, parallel crop list.
    """

    __tablename__ = "customer_plants"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    plant_id = Column(String(20), unique=True, index=True)
    customer_pk = Column(String(36), ForeignKey("customers.id"), nullable=False, index=True)
    customer_id = Column(String(20), ForeignKey("customers.customer_id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=True, index=True)
    nickname = Column(String(120), nullable=True)
    planted_on = Column(String(10), nullable=True)
    expected_harvest_on = Column(String(10), nullable=True)
    quantity = Column(Integer, nullable=True)
    # growing | harvested | removed
    status = Column(String(30), default="growing")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Two FKs point at customers (``customer_pk`` -> the primary key and
    # ``customer_id`` -> the public FA-CS id), so the join has to be explicit.
    customer = relationship("Customer", foreign_keys=[customer_pk])
    crop = relationship("Crop")
