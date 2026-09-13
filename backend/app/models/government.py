from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, Integer, ForeignKey, Text, JSON, Boolean, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class GovernmentScheme(Base):
    __tablename__ = "government_schemes"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    scheme_id = Column(String(20), unique=True, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    eligibility = Column(Text, nullable=True)
    benefits = Column(Text, nullable=True)
    state = Column(String(100), nullable=True)
    crop = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)
    application_deadline = Column(String(20), nullable=True)
    documents_required = Column(JSON, nullable=True)
    how_to_apply = Column(Text, nullable=True)
    website = Column(String(500), nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    # ----- Government scheme enrichment (real, verified scheme metadata) -----
    department = Column(String(300), nullable=True)          # e.g. Ministry of Agriculture & Farmers Welfare
    level = Column(String(30), default="central")            # central | state
    overview = Column(Text, nullable=True)                   # longer official overview
    objectives = Column(Text, nullable=True)                 # goals as delimited text
    application_process = Column(Text, nullable=True)        # step-by-step never-steps text
    contact_information = Column(Text, nullable=True)        # helpdesk / helpline / email
    source = Column(String(200), nullable=True)              # e.g. Official Government Portal
    source_url = Column(String(500), nullable=True)          # official scheme page
    start_date = Column(String(20), nullable=True)           # scheme launch date
    faqs = Column(JSON, nullable=True)                       # list of {question, answer}
    eligible_farmer_types = Column(JSON, nullable=True)      # e.g. ["small","marginal","all"]
    related_crops = Column(JSON, nullable=True)              # crops the scheme targets
    land_category = Column(String(100), nullable=True)       # e.g. "< 2 hectares"
    income_category = Column(String(100), nullable=True)     # e.g. "< Rs 2 lakh / yr"
    benefit_type = Column(String(50), nullable=True)         # subsidy | loan | income | insurance | pension
    last_verified_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SavedScheme(Base):
    __tablename__ = "saved_schemes"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    scheme_id = Column(String(36), ForeignKey("government_schemes.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    farmer = relationship("User", back_populates="saved_schemes")
    scheme = relationship("GovernmentScheme")

    __table_args__ = (
        UniqueConstraint("farmer_id", "scheme_id", name="uq_saved_schemes_farmer_scheme"),
    )


class SchemeApplication(Base):
    __tablename__ = "scheme_applications"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    application_id = Column(String(20), unique=True, index=True)
    farmer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    scheme_id = Column(String(36), ForeignKey("government_schemes.id"), nullable=False)
    status = Column(String(20), default="submitted")
    documents = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    application_date = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    farmer = relationship("User", back_populates="scheme_applications")
    scheme = relationship("GovernmentScheme")


class SchemeDocument(Base):
    __tablename__ = "scheme_documents"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    application_id = Column(String(36), ForeignKey("scheme_applications.id"), nullable=False)
    document_type = Column(String(100), nullable=False)
    file_url = Column(String(500), nullable=True)
    file_name = Column(String(200), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class InsurancePolicy(Base):
    """A farmer's insurance policy (reused as the ``farmer_policies`` table).

    The Insurance page's policy lifecycle is built on this existing table so the
    project has a single policy store: applications link to products, and when an
    application is submitted a ``pending_verification`` policy is created here.
    Columns below marked "insurance" power the full product-based insurance flow.
    """

    __tablename__ = "insurance_policies"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    policy_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    policy_type = Column(String(100), nullable=False)
    provider = Column(String(200), nullable=True)
    policy_number = Column(String(100), nullable=True)
    premium = Column(Float, nullable=True)
    coverage_amount = Column(Float, nullable=True)
    start_date = Column(String(10), nullable=True)
    end_date = Column(String(10), nullable=True)
    status = Column(String(20), default="active")
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ---- insurance product-driven fields (additive) ----
    product_id = Column(String(36), ForeignKey("insurance_products.id"), nullable=True)
    application_id = Column(String(36), ForeignKey("insurance_applications.id"), nullable=True)
    insured_item = Column(String(300), nullable=True)         # crop / livestock / asset summary
    sum_insured = Column(Float, nullable=True)                # coverage amount (alias of coverage_amount)
    premium_paid = Column(Float, nullable=True)               # total premium paid so far
    premium_due = Column(Float, nullable=True)                # pending premium amount
    premium_due_date = Column(String(10), nullable=True)      # next premium due date
    renewal_date = Column(String(10), nullable=True)          # next renewal date
    renewal_count = Column(Integer, default=0)
    policy_holder_name = Column(String(200), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="insurance_policies")
    farm = relationship("Farm", back_populates="insurance_policies")
    claims = relationship("InsuranceClaim", back_populates="policy")
    product = relationship("InsuranceProduct", foreign_keys=[product_id])
    payments = relationship("InsurancePayment", back_populates="policy")


class InsuranceClaim(Base):
    """A farmer's insurance claim (extended for the full claims lifecycle)."""

    __tablename__ = "insurance_claims"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    claim_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    policy_id = Column(String(36), ForeignKey("insurance_policies.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    reason = Column(String(300), nullable=True)
    damage_description = Column(Text, nullable=True)
    documents = Column(JSON, nullable=True)
    claim_amount = Column(Float, nullable=True)
    status = Column(String(20), default="submitted")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ---- insurance claim lifecycle fields (additive) ----
    claim_number = Column(String(20), unique=True, index=True)
    incident_date = Column(String(10), nullable=True)         # date of the covered incident
    incident_location = Column(String(300), nullable=True)    # farm / block / village
    estimated_loss = Column(Float, nullable=True)             # farmer-estimated loss amount
    description = Column(Text, nullable=True)                 # alias for damage_description
    assessment_amount = Column(Float, nullable=True)          # insurer-assessed amount (when available)
    settled_at = Column(String(10), nullable=True)

    user = relationship("User", back_populates="insurance_claims")
    policy = relationship("InsurancePolicy", back_populates="claims")
    farm = relationship("Farm", back_populates="insurance_claims")
    documents_rel = relationship(
        "InsuranceClaimDocument",
        back_populates="claim",
        cascade="all, delete-orphan",
    )


class SchemeSyncLog(Base):
    """Audit log of government-scheme fetch/verification attempts.

    Powers honest freshness labels on the schemes page ("Live", "Verified",
    "Last updated", or "Unavailable"). A row is only ever written when the
    backend actually attempts a contact with a configured official source --
    never fabricated.
    """
    __tablename__ = "scheme_sync_logs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    status = Column(String(20), nullable=False, index=True)  # success | failed | not_configured | cached
    trigger = Column(String(20), default="api")              # api | manual
    source = Column(String(200), nullable=True)
    records_fetched = Column(Integer, default=0)
    records_stored = Column(Integer, default=0)
    message = Column(String(500), nullable=True)
    synced_at = Column(DateTime, default=datetime.utcnow, index=True)
