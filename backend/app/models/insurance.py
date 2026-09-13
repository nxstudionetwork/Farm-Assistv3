"""Agricultural insurance product catalogue + farmer insurance domain models.

New, additive tables used by /api/v1/insurance/* (insurance router). These sit
alongside the existing ``insurance_policies`` / ``insurance_claims`` tables
(which are extended in place and serve as the farmer policy + claim stores) and
are kept separate from legacy features so nothing else breaks.

All farmer-scoped records carry a ``farmer_id``/``user_id`` foreign key and every
query is scoped to the authenticated user server-side — Farmer A can never see
Farmer B's policies, claims, payments, applications, documents or saved items.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, Float, Integer, ForeignKey,
    JSON, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.database.base import Base


def generate_uuid():
    return str(uuid.uuid4())


class InsuranceProduct(Base):
    """A real, insurer/government-published agricultural insurance product (catalogue).

    Only values that are actually available from the official source are stored.
    Fields whose value is unknown for a particular product are left NULL and the
    UI renders them as "Not specified" — nothing is invented here.
    """

    __tablename__ = "insurance_products"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    insurance_id = Column(String(20), unique=True, index=True)
    provider = Column(String(200), nullable=False)       # insurer / organisation name
    provider_id = Column(String(100), nullable=True)     # AIC / AICL / ICICI-LOMBARD / ...
    provider_type = Column(String(50), nullable=True)    # government | state | private
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(50), nullable=True)             # crop | livestock | weather | equipment | asset | ...
    category = Column(String(80), nullable=True)         # Crop Insurance | Livestock Insurance | ...
    coverage = Column(Text, nullable=True)               # what is covered
    exclusions = Column(Text, nullable=True)             # what is not covered
    eligibility = Column(Text, nullable=True)
    premium_information = Column(Text, nullable=True)    # human-readable premium terms
    premium_rate = Column(Float, nullable=True)          # published rate (e.g. 2.0 = 2% of sum insured)
    coverage_amount = Column(Float, nullable=True)       # published typical sum insured (optional)
    premium_amount = Column(Float, nullable=True)        # published typical premium (optional)
    policy_duration_months = Column(Integer, nullable=True)
    policy_duration_text = Column(String(120), nullable=True)
    state = Column(String(120), nullable=True)           # "All India" or specific state
    district = Column(String(120), nullable=True)
    applicable_crops = Column(JSON, nullable=True)
    applicable_livestock = Column(JSON, nullable=True)
    applicable_assets = Column(JSON, nullable=True)
    claim_conditions = Column(Text, nullable=True)
    required_documents = Column(JSON, nullable=True)
    application_process = Column(Text, nullable=True)
    renewal_process = Column(Text, nullable=True)
    contact_information = Column(Text, nullable=True)
    official_url = Column(String(500), nullable=True)
    source = Column(String(200), nullable=True)
    source_url = Column(String(500), nullable=True)
    government_backed = Column(Boolean, default=False)
    private = Column(Boolean, default=False)
    scheme_name = Column(String(300), nullable=True)     # related govt scheme (display only)
    scheme_id = Column(String(36), ForeignKey("government_schemes.id"), nullable=True)
    status = Column(String(20), default="active")
    last_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scheme = relationship("GovernmentScheme")
    saved_records = relationship("SavedInsurance", back_populates="product")


class SavedInsurance(Base):
    """Per-farmer bookmarks for catalogue products (no duplicate saves)."""

    __tablename__ = "saved_insurance"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    insurance_id = Column(String(36), ForeignKey("insurance_products.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    farmer = relationship("User")
    product = relationship("InsuranceProduct", back_populates="saved_records")

    __table_args__ = (
        UniqueConstraint("farmer_id", "insurance_id", name="uq_saved_insurance_farmer_product"),
    )


class InsuranceApplication(Base):
    """A farmer's application against a catalogue insurance product."""

    __tablename__ = "insurance_applications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(20), unique=True, index=True)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    insurance_id = Column(String(36), ForeignKey("insurance_products.id"), nullable=False)
    applicant_name = Column(String(200), nullable=True)
    phone_number = Column(String(15), nullable=True)
    email = Column(String(200), nullable=True)
    aadhaar_number = Column(String(12), nullable=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    farm_size = Column(Float, nullable=True)
    crop = Column(String(120), nullable=True)
    livestock_type = Column(String(120), nullable=True)
    asset_type = Column(String(120), nullable=True)
    coverage_requested = Column(Float, nullable=True)
    premium_estimate = Column(Float, nullable=True)
    premium_rate_note = Column(String(200), nullable=True)
    reference_number = Column(String(20), unique=True, index=True)
    status = Column(String(20), default="submitted")
    policy_id = Column(String(36), ForeignKey("insurance_policies.id"), nullable=True)
    notes = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farmer = relationship("User")
    product = relationship("InsuranceProduct")
    documents = relationship(
        "InsuranceApplicationDocument",
        back_populates="application",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_insurance_applications_farmer", "farmer_id"),
        Index("ix_insurance_applications_product", "insurance_id"),
    )


class InsuranceApplicationDocument(Base):
    """Documents a farmer uploaded against their own insurance application."""

    __tablename__ = "insurance_application_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(36), ForeignKey("insurance_applications.id"), nullable=False)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    document_type = Column(String(120), nullable=False)
    file_name = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(120), nullable=True)
    storage_path = Column(String(500), nullable=True)
    status = Column(String(20), default="uploaded")
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("InsuranceApplication", back_populates="documents")
    farmer = relationship("User")


class InsurancePayment(Base):
    """Verified premium payment transactions against a farmer's policy."""

    __tablename__ = "insurance_payments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    payment_id = Column(String(20), unique=True, index=True)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    policy_id = Column(String(36), ForeignKey("insurance_policies.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    payment_date = Column(DateTime, default=datetime.utcnow)
    reference_number = Column(String(100), nullable=True)
    method = Column(String(30), default="wallet")
    premium_period = Column(String(100), nullable=True)   # e.g. "2026-27" or "Renewal 2026"
    status = Column(String(20), default="completed")     # completed only after backend confirmation
    wallet_transaction_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    farmer = relationship("User")
    policy = relationship("InsurancePolicy", back_populates="payments")

    __table_args__ = (
        Index("ix_insurance_payments_farmer", "farmer_id"),
    )


class InsuranceClaimDocument(Base):
    """Documents/photos a farmer uploaded against their own claim."""

    __tablename__ = "insurance_claim_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    claim_id = Column(String(36), ForeignKey("insurance_claims.id"), nullable=False)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    document_type = Column(String(120), nullable=False)
    file_name = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(120), nullable=True)
    storage_path = Column(String(500), nullable=True)
    status = Column(String(20), default="uploaded")
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    claim = relationship("InsuranceClaim", back_populates="documents_rel")
    farmer = relationship("User")