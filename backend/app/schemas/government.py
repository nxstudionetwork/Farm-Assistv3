from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


class GovernmentSchemeResponse(BaseModel):
    id: str
    scheme_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    eligibility: Optional[str] = None
    benefits: Optional[str] = None
    state: Optional[str] = None
    crop: Optional[str] = None
    category: Optional[str] = None
    application_deadline: Optional[str] = None
    documents_required: Optional[Any] = None
    how_to_apply: Optional[str] = None
    website: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SchemeApplicationCreate(BaseModel):
    scheme_id: str
    documents: Optional[Any] = None
    notes: Optional[str] = None


class SchemeApplicationResponse(BaseModel):
    id: str
    application_id: Optional[str] = None
    farmer_id: str
    scheme_id: str
    status: Optional[str] = None
    documents: Optional[Any] = None
    notes: Optional[str] = None
    application_date: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InsurancePolicyCreate(BaseModel):
    farm_id: Optional[str] = None
    policy_type: str
    provider: Optional[str] = None
    policy_number: Optional[str] = None
    premium: Optional[float] = None
    coverage_amount: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    details: Optional[Any] = None


class InsurancePolicyResponse(BaseModel):
    id: str
    policy_id: Optional[str] = None
    user_id: str
    farm_id: Optional[str] = None
    policy_type: str
    provider: Optional[str] = None
    policy_number: Optional[str] = None
    premium: Optional[float] = None
    coverage_amount: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    details: Optional[Any] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InsuranceClaimCreate(BaseModel):
    policy_id: str
    farm_id: Optional[str] = None
    reason: Optional[str] = None
    damage_description: Optional[str] = None
    documents: Optional[Any] = None
    claim_amount: Optional[float] = None


class InsuranceClaimResponse(BaseModel):
    id: str
    claim_id: Optional[str] = None
    user_id: str
    policy_id: str
    farm_id: Optional[str] = None
    reason: Optional[str] = None
    damage_description: Optional[str] = None
    documents: Optional[Any] = None
    claim_amount: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
