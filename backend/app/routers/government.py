from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.government import (
    GovernmentScheme, SchemeApplication,
    InsurancePolicy, InsuranceClaim,
)

router = APIRouter(prefix="/api/v1", tags=["Government & Insurance"])


class SchemeApplyRequest(BaseModel):
    notes: Optional[str] = None


class InsurancePolicyCreate(BaseModel):
    policy_type: Optional[str] = None
    provider: Optional[str] = None
    policy_number: Optional[str] = None
    premium: Optional[float] = None
    coverage_amount: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    farm_id: Optional[str] = None
    details: Optional[dict] = None
    # Frontend-friendly aliases
    type: Optional[str] = None
    name: Optional[str] = None
    coverage: Optional[float] = None
    crop: Optional[str] = None
    duration_months: Optional[int] = None


class InsuranceClaimCreate(BaseModel):
    policy_id: str
    reason: Optional[str] = None
    damage_description: Optional[str] = None
    claim_amount: Optional[float] = None
    farm_id: Optional[str] = None
    documents: Optional[list] = None
    # Frontend-friendly aliases
    amount: Optional[float] = None
    description: Optional[str] = None


@router.get("/government-schemes")
def list_schemes(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    state: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(GovernmentScheme)
    if search:
        q = q.filter(
            GovernmentScheme.name.ilike(f"%{search}%")
            | GovernmentScheme.description.ilike(f"%{search}%")
        )
    if state:
        q = q.filter(GovernmentScheme.state.ilike(f"%{state}%"))
    if category:
        q = q.filter(GovernmentScheme.category.ilike(f"%{category}%"))
    if status:
        q = q.filter(GovernmentScheme.status == status)
    else:
        q = q.filter(GovernmentScheme.status == "active")

    total = q.count()
    items = q.order_by(GovernmentScheme.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [
                {
                    "id": s.id,
                    "scheme_id": s.scheme_id,
                    "name": s.name,
                    "description": s.description,
                    "eligibility": s.eligibility,
                    "benefits": s.benefits,
                    "state": s.state,
                    "crop": s.crop,
                    "category": s.category,
                    "application_deadline": s.application_deadline,
                    "status": s.status,
                }
                for s in items
            ],
        },
    }


@router.get("/government-schemes/{scheme_id}")
def get_scheme(scheme_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    scheme = db.query(GovernmentScheme).filter(GovernmentScheme.id == scheme_id).first()
    if not scheme:
        scheme = db.query(GovernmentScheme).filter(GovernmentScheme.scheme_id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")

    return {
        "status": "success",
        "data": {
            "id": scheme.id,
            "scheme_id": scheme.scheme_id,
            "name": scheme.name,
            "description": scheme.description,
            "eligibility": scheme.eligibility,
            "benefits": scheme.benefits,
            "state": scheme.state,
            "crop": scheme.crop,
            "category": scheme.category,
            "application_deadline": scheme.application_deadline,
            "documents_required": scheme.documents_required,
            "how_to_apply": scheme.how_to_apply,
            "website": scheme.website,
            "status": scheme.status,
        },
    }


@router.post("/government-schemes/{scheme_id}/apply", status_code=201)
def apply_scheme(
    scheme_id: str,
    payload: SchemeApplyRequest = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scheme = db.query(GovernmentScheme).filter(GovernmentScheme.id == scheme_id).first()
    if not scheme:
        scheme = db.query(GovernmentScheme).filter(GovernmentScheme.scheme_id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")

    existing = (
        db.query(SchemeApplication)
        .filter(
            SchemeApplication.farmer_id == current_user.id,
            SchemeApplication.scheme_id == scheme.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="You have already applied to this scheme")

    app_id = generate_id("FA-SCH", db, SchemeApplication)
    application = SchemeApplication(
        application_id=app_id,
        farmer_id=current_user.id,
        scheme_id=scheme.id,
        notes=(payload.notes if payload else None),
        status="submitted",
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    return {
        "status": "success",
        "data": {
            "id": application.id,
            "application_id": application.application_id,
            "scheme_name": scheme.name,
            "status": application.status,
            "message": "Application submitted successfully",
        },
    }


@router.get("/scheme-applications")
def list_scheme_applications(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(SchemeApplication).filter(SchemeApplication.farmer_id == current_user.id)
    if status:
        q = q.filter(SchemeApplication.status == status)

    total = q.count()
    items = q.order_by(SchemeApplication.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "id": a.id,
                    "application_id": a.application_id,
                    "scheme_id": a.scheme_id,
                    "status": a.status,
                    "notes": a.notes,
                    "application_date": str(a.application_date) if a.application_date else None,
                }
                for a in items
            ],
        },
    }


@router.get("/insurance-policies")
def list_insurance_policies(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(InsurancePolicy).filter(InsurancePolicy.user_id == current_user.id)
    if status:
        q = q.filter(InsurancePolicy.status == status)

    total = q.count()
    items = q.order_by(InsurancePolicy.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "id": p.id,
                    "policy_id": p.policy_id,
                    "policy_type": p.policy_type,
                    "provider": p.provider,
                    "policy_number": p.policy_number,
                    "premium": p.premium,
                    "coverage_amount": p.coverage_amount,
                    "start_date": p.start_date,
                    "end_date": p.end_date,
                    "status": p.status,
                    # Frontend-friendly aliases used by the insurance page
                    "name": p.provider or p.policy_type,
                    "number": p.policy_number,
                    "coverage": p.coverage_amount,
                    "crop": (p.details or {}).get("crop"),
                }
                for p in items
            ],
        },
    }


@router.post("/insurance-policies", status_code=201)
def create_insurance_policy(
    payload: InsurancePolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    policy_type = payload.policy_type or payload.type or "Crop Insurance"
    provider = payload.provider or payload.name
    coverage_amount = payload.coverage_amount if payload.coverage_amount is not None else payload.coverage
    details = payload.details or {}
    if payload.crop and "crop" not in details:
        details["crop"] = payload.crop
    if payload.duration_months:
        details["duration_months"] = payload.duration_months

    pol_id = generate_id("FA-INS", db, InsurancePolicy)
    policy = InsurancePolicy(
        policy_id=pol_id,
        user_id=current_user.id,
        farm_id=payload.farm_id,
        policy_type=policy_type,
        provider=provider,
        policy_number=payload.policy_number,
        premium=payload.premium,
        coverage_amount=coverage_amount,
        start_date=payload.start_date,
        end_date=payload.end_date,
        details=details,
        status="active",
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)

    return {
        "status": "success",
        "data": {
            "id": policy.id,
            "policy_id": policy.policy_id,
            "policy_type": policy.policy_type,
            "status": policy.status,
            "message": "Insurance policy created successfully",
        },
    }


@router.get("/insurance-claims")
def list_insurance_claims(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(InsuranceClaim).filter(InsuranceClaim.user_id == current_user.id)
    if status:
        q = q.filter(InsuranceClaim.status == status)

    total = q.count()
    items = q.order_by(InsuranceClaim.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "id": c.id,
                    "claim_id": c.claim_id,
                    "policy_id": c.policy_id,
                    "reason": c.reason,
                    "claim_amount": c.claim_amount,
                    "status": c.status,
                    "created_at": str(c.created_at) if c.created_at else None,
                }
                for c in items
            ],
        },
    }


@router.post("/insurance-claims", status_code=201)
def create_insurance_claim(
    payload: InsuranceClaimCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    policy = db.query(InsurancePolicy).filter(InsurancePolicy.id == payload.policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Insurance policy not found")

    reason = payload.reason or payload.description or "General claim"
    claim_amount = payload.claim_amount if payload.claim_amount is not None else payload.amount

    claim_id = generate_id("FA-CLM", db, InsuranceClaim)
    claim = InsuranceClaim(
        claim_id=claim_id,
        user_id=current_user.id,
        policy_id=policy.id,
        farm_id=payload.farm_id,
        reason=reason,
        damage_description=payload.damage_description,
        claim_amount=claim_amount,
        documents=payload.documents,
        status="submitted",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    return {
        "status": "success",
        "data": {
            "id": claim.id,
            "claim_id": claim.claim_id,
            "policy_id": claim.policy_id,
            "reason": claim.reason,
            "status": claim.status,
            "message": "Insurance claim submitted successfully",
        },
    }
