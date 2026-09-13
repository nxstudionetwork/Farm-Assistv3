"""Agricultural loan catalogue + farmer financing domain models.

New, additive tables used by /api/v1/loans/* (loan_products router). These are
kept separate from the legacy ``loans`` table so existing finance features are
unaffected. All farmer-scoped records carry a ``farmer_id``/``user_id`` foreign
key and every query is scoped to the authenticated user server-side.
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


class AgriculturalLoanProduct(Base):
    """A real, lender-published agricultural financing product (catalogue)."""

    __tablename__ = "agricultural_loan_products"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    product_id = Column(String(20), unique=True, index=True)
    lender_id = Column(String(24), nullable=True)
    lender = Column(String(200), nullable=False)
    lender_type = Column(String(50), nullable=True)   # scheduled_bank | cooperative | nabard | government | private_bank
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(80), nullable=True)
    loan_type = Column(String(50), nullable=True)     # Term Loan | Cash Credit | Overdraft | ...
    min_amount = Column(Float, nullable=True)
    max_amount = Column(Float, nullable=True)
    interest_rate = Column(String(200), nullable=True)   # human-readable, e.g. "7% p.a. (4% effective)"
    interest_rate_annual = Column(Float, nullable=True)  # headline annual rate for sorting/filtering
    tenure_months = Column(Integer, nullable=True)
    tenure_text = Column(String(100), nullable=True)
    repayment_frequency = Column(String(50), nullable=True)
    eligibility = Column(Text, nullable=True)
    collateral_requirement = Column(String(300), nullable=True)
    required_documents = Column(JSON, nullable=True)
    application_method = Column(String(300), nullable=True)
    fees = Column(String(300), nullable=True)
    official_url = Column(String(500), nullable=True)
    source = Column(String(200), nullable=True)
    source_url = Column(String(500), nullable=True)
    state = Column(String(120), nullable=True)          # "All India" or specific states
    government_backed = Column(Boolean, default=False)
    scheme_name = Column(String(300), nullable=True)    # related govt scheme (display only)
    scheme_id = Column(String(36), ForeignKey("government_schemes.id"), nullable=True)
    status = Column(String(20), default="active")
    last_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scheme = relationship("GovernmentScheme")
    saved_records = relationship("SavedAgriculturalLoan", back_populates="product")


class SavedAgriculturalLoan(Base):
    """Per-farmer bookmarks for catalogue products."""

    __tablename__ = "saved_agricultural_loans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("agricultural_loan_products.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    farmer = relationship("User")
    product = relationship("AgriculturalLoanProduct", back_populates="saved_records")

    __table_args__ = (
        UniqueConstraint("farmer_id", "product_id", name="uq_saved_agri_loan_farmer_product"),
    )


class AgriculturalLoanApplication(Base):
    """A farmer's application against a catalogue loan product."""

    __tablename__ = "agricultural_loan_applications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(20), unique=True, index=True)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("agricultural_loan_products.id"), nullable=False)
    applicant_name = Column(String(200), nullable=True)
    phone_number = Column(String(15), nullable=True)
    email = Column(String(200), nullable=True)
    aadhaar_number = Column(String(12), nullable=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    farm_size = Column(Float, nullable=True)
    crop = Column(String(120), nullable=True)
    land_type = Column(String(50), nullable=True)
    purpose = Column(String(300), nullable=True)
    requested_amount = Column(Float, nullable=False)
    status = Column(String(20), default="submitted")
    notes = Column(Text, nullable=True)
    reference_number = Column(String(20), nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farmer = relationship("User")
    product = relationship("AgriculturalLoanProduct")
    documents = relationship(
        "AgriculturalLoanDocument",
        back_populates="application",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_agri_loan_applications_farmer", "farmer_id"),
        Index("ix_agri_loan_applications_product", "product_id"),
    )


class AgriculturalLoanDocument(Base):
    """Documents a farmer uploaded against their own application."""

    __tablename__ = "agricultural_loan_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    application_id = Column(String(36), ForeignKey("agricultural_loan_applications.id"), nullable=False)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    document_type = Column(String(120), nullable=False)
    file_name = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(120), nullable=True)
    storage_path = Column(String(500), nullable=True)
    status = Column(String(20), default="uploaded")
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("AgriculturalLoanApplication", back_populates="documents")
    farmer = relationship("User")


class AgriculturalFarmerLoan(Base):
    """A sanctioned/disbursed loan held by the farmer (their own financing)."""

    __tablename__ = "agricultural_farmer_loans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    farmer_loan_id = Column(String(20), unique=True, index=True)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    application_id = Column(String(36), ForeignKey("agricultural_loan_applications.id"), nullable=True)
    product_id = Column(String(36), ForeignKey("agricultural_loan_products.id"), nullable=True)
    lender = Column(String(200), nullable=True)
    loan_name = Column(String(300), nullable=True)
    principal_amount = Column(Float, nullable=False)
    outstanding_amount = Column(Float, nullable=True)
    interest_rate_annual = Column(Float, nullable=True)
    emi_amount = Column(Float, nullable=True)
    tenure_months = Column(Integer, nullable=True)
    next_payment = Column(Float, nullable=True)
    next_due_date = Column(DateTime, nullable=True)
    status = Column(String(20), default="active")  # active | approved | overdue | closed
    disbursed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farmer = relationship("User")
    application = relationship("AgriculturalLoanApplication")
    product = relationship("AgriculturalLoanProduct")
    repayments = relationship(
        "AgriculturalLoanRepayment",
        back_populates="farmer_loan",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_agri_farmer_loans_farmer", "farmer_id"),
    )


class AgriculturalLoanRepayment(Base):
    """Verified repayment transactions against a farmer's loan."""

    __tablename__ = "agricultural_loan_repayments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    repayment_id = Column(String(20), unique=True, index=True)
    farmer_loan_id = Column(String(36), ForeignKey("agricultural_farmer_loans.id"), nullable=False, index=True)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    payment_date = Column(DateTime, default=datetime.utcnow)
    reference_number = Column(String(100), nullable=True)
    method = Column(String(30), default="wallet")
    status = Column(String(20), default="completed")  # completed only after backend confirmation
    wallet_transaction_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    farmer_loan = relationship("AgriculturalFarmerLoan", back_populates="repayments")
    farmer = relationship("User")

    __table_args__ = (
        Index("ix_agri_loan_repayments_farmer", "farmer_id"),
    )


class AgriculturalLoanEligibility(Base):
    """History of the farmer's eligibility checks (stored, not fabricated)."""

    __tablename__ = "agricultural_loan_eligibility"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("agricultural_loan_products.id"), nullable=True)
    inputs = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    farmer = relationship("User")
    product = relationship("AgriculturalLoanProduct")