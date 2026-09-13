"""Agricultural Insurance router.

Real product catalogue + real, per-farmer insurance operations:

  * Insurance products (verified, insurer/government-published catalogue)
  * Categories / search / filters
  * Per-farmer saved insurance (no duplicates)
  * Eligibility checker (deterministic, transparent, never an approval)
  * Applications with backend-generated reference numbers
  * Policy records created when an application is submitted
  * Verified premium payments via the Farm Assist wallet (only the payment is
    marked completed after the wallet debit succeeds)
  * Policy renewal (user-confirmed, wallet payment where premium applies)
  * Claims with reference numbers, documents and a tracked status
  * Application / claim document upload & download (ownership-checked)

Every farmer-scoped query is server-side restricted to the authenticated user;
``farmer_id``/``user_id`` is always derived from the token, never from the
client. No cross-user data can be read or written.
"""

import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.database.connection import get_db
from app.database.seed_insurance_products import seed_insurance_products, CATEGORY_ORDER
from app.integrations.file_storage import FileStorageService
from app.utils.auth import get_current_user, generate_id, verify_password
from app.utils.notification_helper import create_notification
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.models.government import InsurancePolicy, InsuranceClaim, GovernmentScheme
from app.models.insurance import (
    InsuranceProduct,
    SavedInsurance,
    InsuranceApplication,
    InsuranceApplicationDocument,
    InsurancePayment,
    InsuranceClaimDocument,
)

router = APIRouter(prefix="/api/v1", tags=["Agricultural Insurance"])

POLICY_STATUSES = {
    "pending_verification",
    "active",
    "expired",
    "cancelled",
    "closed",
}
CLAIM_STATUSES = {
    "submitted",
    "under_review",
    "documents_required",
    "approved",
    "rejected",
    "settled",
    "closed",
}

# Category chips that are provider-type buckets rather than product categories.
TYPE_BUCKETS = {
    "Government Insurance": {"government_backed": True},
    "State Insurance": {"provider_type": "state"},
    "Private Insurance": {"private": True},
}


def _get_wallet(db: Session, user_id: str) -> Optional[Wallet]:
    return db.query(Wallet).filter(Wallet.user_id == user_id).first()


# --------------------------------------------------------------------------- #
# Serialization helpers
# --------------------------------------------------------------------------- #
def _parse_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [s.strip() for s in str(value).split("|") if s.strip()]


def _resolve_product(db: Session, product_id: str) -> Optional[InsuranceProduct]:
    return (
        db.query(InsuranceProduct)
        .filter(
            (InsuranceProduct.insurance_id == product_id) | (InsuranceProduct.id == product_id)
        )
        .first()
    )


def _score_status(end_date, status):
    if not end_date or status in ("cancelled", "closed"):
        return status
    if status != "active":
        return status
    today = datetime.utcnow().date()
    try:
        end = datetime.strptime(str(end_date), "%Y-%m-%d").date()
    except ValueError:
        return status
    if end < today:
        return "expired"
    if (end - today).days <= 30:
        return "expiring"
    return "active"


def _product_dict(p: InsuranceProduct, db: Session, user_id: Optional[str]) -> dict:
    saved = False
    if user_id:
        saved = (
            db.query(SavedInsurance)
            .filter(
                SavedInsurance.farmer_id == user_id,
                SavedInsurance.insurance_id == p.id,
            )
            .first()
        ) is not None

    return {
        "id": p.id,
        "insurance_id": p.insurance_id,
        "provider": p.provider,
        "provider_id": p.provider_id,
        "provider_type": p.provider_type,
        "name": p.name,
        "description": p.description,
        "type": p.type,
        "category": p.category,
        "coverage": p.coverage,
        "exclusions": p.exclusions,
        "eligibility": p.eligibility,
        "premium_information": p.premium_information,
        "premium_rate": p.premium_rate,
        "coverage_amount": p.coverage_amount,
        "premium_amount": p.premium_amount,
        "policy_duration_months": p.policy_duration_months,
        "policy_duration_text": p.policy_duration_text,
        "state": p.state,
        "district": p.district,
        "applicable_crops": _parse_list(p.applicable_crops),
        "applicable_livestock": _parse_list(p.applicable_livestock),
        "applicable_assets": _parse_list(p.applicable_assets),
        "claim_conditions": p.claim_conditions,
        "required_documents": _parse_list(p.required_documents),
        "application_process": p.application_process,
        "renewal_process": p.renewal_process,
        "contact_information": p.contact_information,
        "official_url": p.official_url,
        "source": p.source,
        "source_url": p.source_url,
        "government_backed": bool(p.government_backed),
        "private": bool(p.private),
        "scheme_name": p.scheme_name,
        "scheme_id": p.scheme_id,
        "status": p.status,
        "last_verified_at": str(p.last_verified_at) if p.last_verified_at else None,
        "is_saved": saved,
    }


def _application_dict(a: InsuranceApplication, db: Session) -> dict:
    product = (
        db.query(InsuranceProduct).filter(InsuranceProduct.id == a.insurance_id).first()
    )
    docs = (
        db.query(InsuranceApplicationDocument)
        .filter(InsuranceApplicationDocument.application_id == a.id)
        .all()
    )
    return {
        "id": a.id,
        "application_id": a.application_id,
        "reference_number": a.reference_number,
        "insurance_id": a.insurance_id,
        "product_name": product.name if product else None,
        "provider": product.provider if product else None,
        "category": product.category if product else None,
        "type": product.type if product else None,
        "coverage_requested": a.coverage_requested,
        "premium_estimate": a.premium_estimate,
        "premium_rate_note": a.premium_rate_note,
        "status": a.status,
        "policy_id": a.policy_id,
        "applicant_name": a.applicant_name,
        "phone_number": a.phone_number,
        "email": a.email,
        "state": a.state,
        "district": a.district,
        "farm_size": a.farm_size,
        "crop": a.crop,
        "livestock_type": a.livestock_type,
        "asset_type": a.asset_type,
        "submitted_at": str(a.submitted_at) if a.submitted_at else None,
        "updated_at": str(a.updated_at) if a.updated_at else None,
        "documents": [
            {
                "id": d.id,
                "document_type": d.document_type,
                "file_name": d.file_name,
                "file_size_bytes": d.file_size_bytes,
                "mime_type": d.mime_type,
                "status": d.status,
                "uploaded_at": str(d.uploaded_at) if d.uploaded_at else None,
            }
            for d in docs
        ],
        "required_documents": _parse_list(product.required_documents) if product else [],
    }


def _payment_dict(py: InsurancePayment) -> dict:
    return {
        "id": py.id,
        "payment_id": py.payment_id,
        "amount": round(float(py.amount), 2),
        "payment_date": str(py.payment_date) if py.payment_date else None,
        "reference_number": py.reference_number,
        "method": py.method,
        "premium_period": py.premium_period,
        "status": py.status,
        "wallet_transaction_id": py.wallet_transaction_id,
    }


def _policy_dict(p: InsurancePolicy, db: Session) -> dict:
    product = (
        db.query(InsuranceProduct).filter(InsuranceProduct.id == p.product_id).first()
    )
    claims = db.query(InsuranceClaim).filter(InsuranceClaim.policy_id == p.id).all()
    payments = (
        db.query(InsurancePayment)
        .filter(InsurancePayment.policy_id == p.id)
        .order_by(InsurancePayment.payment_date.desc())
        .all()
    )
    res_status = _score_status(p.end_date, p.status)
    return {
        "id": p.id,
        "policy_id": p.policy_id,
        "policy_number": p.policy_number or p.policy_id,
        "product_id": p.product_id,
        "product_name": product.name if product else None,
        "provider": p.provider or (product.provider if product else None),
        "policy_type": p.policy_type,
        "status": res_status,
        "raw_status": p.status,
        "coverage_amount": p.coverage_amount or p.sum_insured,
        "premium": p.premium,
        "premium_paid": round(float(p.premium_paid or 0), 2),
        "premium_due": round(float(p.premium_due or 0), 2) if p.premium_due is not None else None,
        "premium_due_date": p.premium_due_date,
        "start_date": p.start_date,
        "end_date": p.end_date,
        "renewal_date": p.renewal_date,
        "renewal_count": p.renewal_count or 0,
        "insured_item": p.insured_item,
        "details": p.details or {},
        "claims_count": len(claims),
        "payments_count": len(payments),
        # Frontend-friendly aliases
        "name": (product.name if product else None) or p.policy_type,
        "number": p.policy_number or p.policy_id,
        "coverage": p.coverage_amount or p.sum_insured,
        "claim_count": len(claims),
    }


def _claim_dict(c: InsuranceClaim, db: Session) -> dict:
    docs = (
        db.query(InsuranceClaimDocument)
        .filter(InsuranceClaimDocument.claim_id == c.id)
        .all()
    )
    policy = db.query(InsurancePolicy).filter(InsurancePolicy.id == c.policy_id).first()
    product = (
        db.query(InsuranceProduct).filter(InsuranceProduct.id == policy.product_id).first()
        if policy
        else None
    )
    return {
        "id": c.id,
        "claim_id": c.claim_id,
        "claim_number": c.claim_number or c.claim_id,
        "policy_id": c.policy_id,
        "policy_name": (product.name if product else None) or (policy.policy_type if policy else None),
        "policy_number": policy.policy_number if policy else None,
        "reason": c.reason,
        "description": c.description or c.damage_description,
        "incident_date": c.incident_date,
        "incident_location": c.incident_location,
        "claim_amount": c.claim_amount,
        "estimated_loss": c.estimated_loss,
        "assessment_amount": c.assessment_amount,
        "status": c.status,
        "status_label": c.status.replace("_", " ").title(),
        "created_at": str(c.created_at) if c.created_at else None,
        "updated_at": str(c.updated_at) if c.updated_at else None,
        "settled_at": c.settled_at,
        # Frontend-friendly aliases used by views
        "amount": c.claim_amount or c.estimated_loss,
        "documents": [
            {
                "id": d.id,
                "document_type": d.document_type,
                "file_name": d.file_name,
                "file_size_bytes": d.file_size_bytes,
                "mime_type": d.mime_type,
                "status": d.status,
                "uploaded_at": str(d.uploaded_at) if d.uploaded_at else None,
            }
            for d in docs
        ],
    }


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
@router.get("/insurance/categories")
def insurance_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_insurance_products(db)
    rows = (
        db.query(InsuranceProduct.category, func.count(InsuranceProduct.id))
        .filter(InsuranceProduct.status == "active")
        .group_by(InsuranceProduct.category)
        .all()
    )
    counts = {c: n for c, n in rows if c}

    ordered = []
    for cat in CATEGORY_ORDER:
        if cat == "All":
            continue
        # Provider-type buckets
        if cat in TYPE_BUCKETS:
            q = db.query(func.count(InsuranceProduct.id)).filter(
                InsuranceProduct.status == "active"
            )
            for field, value in TYPE_BUCKETS[cat].items():
                q = q.filter(getattr(InsuranceProduct, field) == value)
            ordered.append({"name": cat, "count": int(q.scalar() or 0)})
            continue
        ordered.append({"name": cat, "count": int(counts.get(cat, 0))})
    ordered.sort(key=lambda x: x["count"], reverse=True)
    total = int(
        db.query(func.count(InsuranceProduct.id))
        .filter(InsuranceProduct.status == "active")
        .scalar()
        or 0
    )
    return {"status": "success", "data": {"categories": ordered, "total": total}}


@router.get("/insurance/filters")
def insurance_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_insurance_products(db)
    providers = [
        r[0]
        for r in db.query(InsuranceProduct.provider)
        .filter(InsuranceProduct.status == "active", InsuranceProduct.provider.isnot(None))
        .distinct()
        .order_by(InsuranceProduct.provider)
        .all()
    ]
    states = [
        r[0]
        for r in db.query(InsuranceProduct.state)
        .filter(InsuranceProduct.status == "active", InsuranceProduct.state.isnot(None))
        .distinct()
        .order_by(InsuranceProduct.state)
        .all()
    ]
    types = [
        r[0]
        for r in db.query(InsuranceProduct.type)
        .filter(InsuranceProduct.status == "active", InsuranceProduct.type.isnot(None))
        .distinct()
        .order_by(InsuranceProduct.type)
        .all()
    ]
    return {
        "status": "success",
        "data": {"providers": providers, "states": states, "types": types},
    }


@router.get("/insurance/products")
def list_insurance_products(
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    search: Optional[str] = None,
    category: Optional[str] = None,
    provider: Optional[str] = None,
    state: Optional[str] = None,
    type_filter: Optional[str] = Query(None, alias="type"),
    sort: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_insurance_products(db)
    q = db.query(InsuranceProduct).filter(InsuranceProduct.status == "active")

    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                InsuranceProduct.name.ilike(term),
                InsuranceProduct.provider.ilike(term),
                InsuranceProduct.category.ilike(term),
                InsuranceProduct.description.ilike(term),
                InsuranceProduct.eligibility.ilike(term),
                InsuranceProduct.state.ilike(term),
                InsuranceProduct.type.ilike(term),
            )
        )
    if category and category != "All":
        if category in TYPE_BUCKETS:
            for field, value in TYPE_BUCKETS[category].items():
                q = q.filter(getattr(InsuranceProduct, field) == value)
        else:
            q = q.filter(InsuranceProduct.category == category)
    if provider:
        q = q.filter(InsuranceProduct.provider == provider)
    if state:
        q = q.filter(
            or_(
                InsuranceProduct.state == "All India",
                InsuranceProduct.state == f"All India (notified states and reference stations)",
                InsuranceProduct.state.ilike(f"%{state}%"),
            )
        )
    if type_filter:
        q = q.filter(InsuranceProduct.type == type_filter)

    total = q.count()
    if sort == "name":
        q = q.order_by(InsuranceProduct.name.asc())
    elif sort == "provider":
        q = q.order_by(InsuranceProduct.provider.asc())
    else:
        q = q.order_by(InsuranceProduct.name.asc())

    items = q.offset((page - 1) * limit).limit(limit).all()
    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total else 0,
            "items": [_product_dict(p, db, current_user.id) for p in items],
        },
    }


@router.get("/insurance/search")
def search_insurance_products(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_insurance_products(db)
    term = f"%{q.strip()}%"
    items = (
        db.query(InsuranceProduct)
        .filter(
            InsuranceProduct.status == "active",
            or_(
                InsuranceProduct.name.ilike(term),
                InsuranceProduct.provider.ilike(term),
                InsuranceProduct.category.ilike(term),
                InsuranceProduct.description.ilike(term),
                InsuranceProduct.eligibility.ilike(term),
                InsuranceProduct.state.ilike(term),
                InsuranceProduct.type.ilike(term),
            ),
        )
        .order_by(InsuranceProduct.name.asc())
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "total": len(items),
            "query": q.strip(),
            "items": [_product_dict(p, db, current_user.id) for p in items],
        },
    }


@router.get("/insurance/products/saved")
def saved_insurance_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        db.query(SavedInsurance)
        .filter(SavedInsurance.farmer_id == current_user.id)
        .order_by(SavedInsurance.created_at.desc())
    )
    total = q.count()
    rows = q.offset((page - 1) * limit).limit(limit).all()
    items = []
    for row in rows:
        p = (
            db.query(InsuranceProduct)
            .filter(InsuranceProduct.id == row.insurance_id)
            .first()
        )
        if p:
            item = _product_dict(p, db, current_user.id)
            item["saved_at"] = str(row.created_at) if row.created_at else None
            items.append(item)
    return {
        "status": "success",
        "data": {"total": total, "page": page, "limit": limit, "items": items},
    }


@router.get("/insurance/products/{product_id}")
def get_insurance_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_insurance_products(db)
    p = _resolve_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Insurance product not found")
    return {"status": "success", "data": _product_dict(p, db, current_user.id)}


# --------------------------------------------------------------------------- #
# Saved insurance (write actions)
# --------------------------------------------------------------------------- #
@router.post("/insurance/products/{product_id}/save", status_code=201)
def save_insurance_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _resolve_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Insurance product not found")
    existing = (
        db.query(SavedInsurance)
        .filter(
            SavedInsurance.farmer_id == current_user.id,
            SavedInsurance.insurance_id == p.id,
        )
        .first()
    )
    if existing:
        return {"status": "success", "data": {"is_saved": True, "message": "Insurance already saved"}}
    db.add(SavedInsurance(farmer_id=current_user.id, insurance_id=p.id))
    db.commit()
    return {"status": "success", "data": {"is_saved": True, "message": "Insurance saved"}}


@router.delete("/insurance/products/{product_id}/save")
def unsave_insurance_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _resolve_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Insurance product not found")
    existing = (
        db.query(SavedInsurance)
        .filter(
            SavedInsurance.farmer_id == current_user.id,
            SavedInsurance.insurance_id == p.id,
        )
        .first()
    )
    if not existing:
        return {"status": "success", "data": {"is_saved": False, "message": "Insurance was not saved"}}
    db.delete(existing)
    db.commit()
    return {"status": "success", "data": {"is_saved": False, "message": "Insurance removed from saved"}}


# --------------------------------------------------------------------------- #
# Eligibility checker
# --------------------------------------------------------------------------- #
class EligibilityRequest(BaseModel):
    insurance_id: str
    state: Optional[str] = None
    district: Optional[str] = None
    crop: Optional[str] = None
    season: Optional[str] = None
    farm_size_acres: Optional[float] = None
    livestock_type: Optional[str] = None
    asset_type: Optional[str] = None
    insurance_type: Optional[str] = None


def _check_eligibility(p: InsuranceProduct, req: EligibilityRequest) -> dict:
    """Deterministic, transparent heuristic based ONLY on published product fields.

    The verdict is explicitly indicative: Farm Assist never approves insurance
    and never guarantees a payout. Final eligibility is decided by the
    insurer/government authority from its own rules.
    """
    now = datetime.utcnow()
    matched = []
    missing = []
    warnings = []

    eligibility_text = (p.eligibility or "").lower()
    state = (req.state or "").strip().lower()
    if not state:
        warnings.append("No state supplied — state-wise availability not verified.")
    elif p.state and p.state.strip().lower() != "all india":
        p_state = p.state.strip().lower()
        if state in p_state or p_state in state:
            matched.append(f"Product availability covers {p.state}.")
        else:
            missing.append(f"Product availability lists {p.state}; your state does not obviously match.")
    elif p.state and "all india" in p.state.strip().lower():
        matched.append("Product is available nationwide (All India).")

    insurance_type = (req.insurance_type or "").strip().lower()
    if insurance_type:
        p_type = (p.type or "").lower()
        if p_type and (insurance_type in p_type or p_type in insurance_type):
            matched.append(f"Insurance type '{req.insurance_type}' matches the product type.")
        elif p_type:
            warnings.append(f"Product is classified as '{p.type}'; check the coverage matches your need.")
        else:
            warnings.append("Product type is not published.")

    crop = (req.crop or "").strip().lower()
    if crop:
        crops = _parse_list(p.applicable_crops)
        if any(c.lower() in crop or crop in c.lower() for c in crops):
            matched.append(f"Crop '{req.crop}' appears in the listed applicable crops.")
        elif crops:
            warnings.append(f"Crop '{req.crop}' is not explicitly named in the applicable crops.")
        else:
            warnings.append("Applicable crops are not published for this product.")

    livestock_type = (req.livestock_type or "").strip().lower()
    if livestock_type:
        livestock = _parse_list(p.applicable_livestock)
        if any(l.lower() in livestock_type or livestock_type in l.lower() for l in livestock):
            matched.append(f"Livestock type '{req.livestock_type}' appears in the listed applicable livestock.")
        elif livestock:
            warnings.append(f"Livestock type '{req.livestock_type}' is not explicitly named.")
        else:
            warnings.append("Applicable livestock are not published for this product.")

    asset_type = (req.asset_type or "").strip().lower()
    if asset_type:
        assets = _parse_list(p.applicable_assets)
        if any(a.lower() in asset_type or asset_type in a.lower() for a in assets):
            matched.append(f"Asset type '{req.asset_type}' appears in the listed applicable assets.")
        elif assets:
            warnings.append(f"Asset type '{req.asset_type}' is not explicitly named.")
        else:
            warnings.append("Applicable assets are not published for this product.")

    if req.farm_size_acres is not None and req.farm_size_acres > 0:
        if any(kw in eligibility_text for kw in ["acre", "hectare", "size", "land"]):
            matched.append("Farm size is referenced in the eligibility criteria.")
        else:
            warnings.append("No farm-size threshold is published for this product.")

    if eligibility_text and "farmer" in eligibility_text:
        matched.append("The product targets farmers, which this profile represents.")
    elif p.eligibility:
        warnings.append("Eligibility is published but no specific farmer-type criteria matched the supplied inputs.")

    if not matched and not warnings and not missing:
        warnings.append("Eligibility criteria are not published for this product — contact the provider directly.")

    if missing:
        verdict = "not_likely"
        status_label = "Likely not eligible"
        headline = "Some published criteria are not met"
    elif matched:
        verdict = "likely_eligible"
        status_label = "Possibly eligible"
        headline = "Matches the published criteria"
    else:
        verdict = "needs_review"
        status_label = "Needs review"
        headline = "Criteria could not be fully verified"

    return {
        "verdict": verdict,
        "status_label": status_label,
        "headline": headline,
        "matched": matched,
        "missing": missing,
        "warnings": warnings,
        "disclaimer": (
            "This is an indicative check based only on insurer/government-published information. "
            "Farm Assist does not approve insurance policies and this result is not cover approval. "
            "Final eligibility, premium and acceptance are decided solely by the insurer or the "
            "appropriate government authority."
        ),
        "checked_at": str(now),
    }


@router.post("/insurance/check-eligibility")
def check_insurance_eligibility(
    payload: EligibilityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_insurance_products(db)
    p = _resolve_product(db, payload.insurance_id)
    if not p:
        raise HTTPException(status_code=404, detail="Insurance product not found")

    result = _check_eligibility(p, payload)
    product = _product_dict(p, db, current_user.id)
    return {
        "status": "success",
        "message": "Eligibility check completed",
        "data": {"result": result, "product": product},
    }


# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
class ApplicationCreate(BaseModel):
    insurance_id: str
    applicant_name: Optional[str] = None
    phone_number: str
    email: Optional[str] = None
    aadhaar_number: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    farm_size: Optional[float] = None
    crop: Optional[str] = None
    livestock_type: Optional[str] = None
    asset_type: Optional[str] = None
    coverage_requested: Optional[float] = None
    season: Optional[str] = None
    notes: Optional[str] = None


def _estimate_premium(p: InsuranceProduct, coverage: Optional[float]) -> dict:
    """Derive a premium estimate ONLY from published data.

    When the provider publishes a rate (e.g. PMFBY 2% of sum insured), the
    estimate is that published rate applied to the requested coverage. When no
    rate is published, no estimate is fabricated.
    """
    if coverage is None:
        return {"estimate": None, "note": None}
    if p.premium_rate:
        estimate = round(float(coverage) * float(p.premium_rate) / 100.0, 2)
        note = f"As published: {p.premium_rate}% of sum insured (verify before applying)."
        return {"estimate": estimate, "note": note}
    if p.premium_amount:
        return {"estimate": float(p.premium_amount), "note": "As published by the provider (verify before applying)."}
    return {"estimate": None, "note": "Premium not published for this product — the provider will confirm."}


@router.post("/insurance/applications", status_code=201)
def create_insurance_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_insurance_products(db)
    p = _resolve_product(db, payload.insurance_id)
    if not p:
        raise HTTPException(status_code=404, detail="Insurance product not found")

    coverage = payload.coverage_requested
    if coverage is not None:
        try:
            coverage = round(float(coverage), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid coverage amount")
        if coverage <= 0:
            raise HTTPException(status_code=400, detail="Coverage amount must be greater than zero")
        if p.coverage_amount and coverage > float(p.coverage_amount):
            raise HTTPException(
                status_code=400,
                detail=f"Coverage amount exceeds the published sum insured of ₹{float(p.coverage_amount):,.2f} for this product.",
            )

    phone = (payload.phone_number or "").strip()
    digits = re.sub(r"\D", "", phone)
    if not (10 <= len(digits) <= 13):
        raise HTTPException(status_code=400, detail="Phone number must contain 10-13 digits")
    aadhaar = (payload.aadhaar_number or "").strip()
    if aadhaar and (not aadhaar.isdigit() or len(aadhaar) != 12):
        raise HTTPException(status_code=400, detail="Aadhaar must be exactly 12 digits")

    premium = _estimate_premium(p, coverage)
    application_id = generate_id("FA-IAPP", db, InsuranceApplication)

    app = InsuranceApplication(
        application_id=application_id,
        reference_number=application_id,
        farmer_id=current_user.id,
        insurance_id=p.id,
        applicant_name=(payload.applicant_name or "").strip() or (current_user.full_name or None),
        phone_number=phone,
        email=(payload.email or "").strip() or None,
        aadhaar_number=aadhaar or None,
        state=(payload.state or "").strip() or None,
        district=(payload.district or "").strip() or None,
        farm_size=payload.farm_size,
        crop=(payload.crop or "").strip() or None,
        livestock_type=(payload.livestock_type or "").strip() or None,
        asset_type=(payload.asset_type or "").strip() or None,
        coverage_requested=coverage,
        premium_estimate=premium["estimate"],
        premium_rate_note=premium["note"],
        status="submitted",
        notes=(payload.notes or "").strip() or None,
        submitted_at=datetime.utcnow(),
    )
    db.add(app)
    db.flush()

    # Create the farmer's policy record (pending verification until premium is
    # confirmed and the insurer activates the cover).
    today = datetime.utcnow().date().isoformat()
    months = p.policy_duration_months or 12
    end_date = (datetime.utcnow() + timedelta(days=30 * months)).date().isoformat()
    policy_id = generate_id("FA-POLY", db, InsurancePolicy)
    policy = InsurancePolicy(
        policy_id=policy_id,
        policy_number=policy_id,
        user_id=current_user.id,
        policy_type=p.type or p.category or "Agricultural Insurance",
        provider=p.provider,
        product_id=p.id,
        application_id=app.id,
        policy_holder_name=(payload.applicant_name or "").strip() or (current_user.full_name or None),
        insured_item=(
            (payload.crop or payload.livestock_type or payload.asset_type or "")
            .strip() or None
        ),
        coverage_amount=coverage or p.coverage_amount,
        sum_insured=coverage or p.coverage_amount,
        premium=premium["estimate"],
        premium_paid=0.0,
        premium_due=premium["estimate"],
        premium_due_date=str(
            (datetime.utcnow() + timedelta(days=15)).date().isoformat()
        ) if premium["estimate"] else None,
        start_date=today,
        end_date=end_date,
        renewal_date=end_date,
        renewal_count=0,
        status="pending_verification",
        details={
            "crop": payload.crop,
            "livestock_type": payload.livestock_type,
            "asset_type": payload.asset_type,
            "season": payload.season,
            "district": payload.district,
            "premium_rate_note": premium["note"],
        },
    )
    db.add(policy)
    db.flush()
    app.policy_id = policy.id

    create_notification(
        db=db,
        user_id=current_user.id,
        title="Insurance Application Submitted",
        message=(
            f"Application {application_id} for {p.name} has been submitted to {p.provider}. "
            "Policy record created pending verification — pay the premium from My Policies to "
            "complete your cover."
        ),
        notification_type="government",
        reference_id=app.id,
        reference_type="insurance_application",
        icon="fa-shield-halved",
        action_url="insurance.html",
    )
    db.commit()
    db.refresh(app)

    return {
        "status": "success",
        "message": "Insurance application submitted",
        "data": _application_dict(app, db),
    }


@router.get("/insurance/applications")
def list_insurance_applications(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(InsuranceApplication).filter(InsuranceApplication.farmer_id == current_user.id)
    if status_filter:
        q = q.filter(InsuranceApplication.status == status_filter)
    total = q.count()
    items = (
        q.order_by(InsuranceApplication.submitted_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [_application_dict(a, db) for a in items],
        },
    }


@router.get("/insurance/applications/{application_id}")
def get_insurance_application(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = db.query(InsuranceApplication).filter(
        InsuranceApplication.application_id == application_id,
        InsuranceApplication.farmer_id == current_user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Insurance application not found")
    return {"status": "success", "data": _application_dict(app, db)}


@router.post("/insurance/applications/{application_id}/documents", status_code=201)
async def upload_insurance_application_document(
    application_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = db.query(InsuranceApplication).filter(
        InsuranceApplication.application_id == application_id,
        InsuranceApplication.farmer_id == current_user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Insurance application not found")
    if not document_type or not document_type.strip():
        raise HTTPException(status_code=400, detail="Document type is required")

    try:
        saved = await FileStorageService.save_upload(
            file,
            subdir="insurance-documents",
            encrypt=True,
            validate_signature=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    doc = InsuranceApplicationDocument(
        application_id=app.id,
        farmer_id=current_user.id,
        document_type=document_type.strip().lower(),
        file_name=saved["file_name"],
        file_size_bytes=saved["size_bytes"],
        mime_type=saved["content_type"] or FileStorageService.detect_mime(b""),
        storage_path=saved["path"],
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "status": "success",
        "message": "Document uploaded",
        "data": {
            "id": doc.id,
            "document_type": doc.document_type,
            "file_name": doc.file_name,
            "file_size_bytes": doc.file_size_bytes,
            "status": doc.status,
            "uploaded_at": str(doc.uploaded_at) if doc.uploaded_at else None,
        },
    }


@router.get("/insurance/applications/{application_id}/documents/{document_id}/file")
def download_insurance_application_document(
    application_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = db.query(InsuranceApplication).filter(
        InsuranceApplication.application_id == application_id,
        InsuranceApplication.farmer_id == current_user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Insurance application not found")
    doc = db.query(InsuranceApplicationDocument).filter(
        InsuranceApplicationDocument.id == document_id,
        InsuranceApplicationDocument.application_id == app.id,
        InsuranceApplicationDocument.farmer_id == current_user.id,
    ).first()
    if not doc or not doc.storage_path:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        content = FileStorageService.read_document(doc.storage_path)
    except ValueError:
        raise HTTPException(status_code=500, detail="Could not read document")

    return Response(
        content=content,
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{doc.file_name or "document"}"',
            "Content-Length": str(len(content)),
        },
    )


# --------------------------------------------------------------------------- #
# Policies (farmer's own policies only)
# --------------------------------------------------------------------------- #
@router.get("/insurance/policies")
def list_farmer_policies(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(InsurancePolicy).filter(InsurancePolicy.user_id == current_user.id)
    items = q.order_by(InsurancePolicy.created_at.desc()).all()
    items = [_policy_dict(p, db) for p in items]
    if status_filter == "active":
        items = [i for i in items if i["status"] in ("active", "expiring")]
    elif status_filter:
        items = [i for i in items if i["status"] == status_filter]
    return {"status": "success", "data": {"total": len(items), "items": items}}


@router.get("/insurance/policies/{policy_id}")
def get_farmer_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.query(InsurancePolicy).filter(
        InsurancePolicy.policy_id == policy_id,
        InsurancePolicy.user_id == current_user.id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found")
    data = _policy_dict(p, db)
    data["claims"] = [
        _claim_dict(c, db)
        for c in db.query(InsuranceClaim)
        .filter(InsuranceClaim.policy_id == p.id)
        .order_by(InsuranceClaim.created_at.desc())
        .all()
    ]
    data["payments"] = [
        _payment_dict(py)
        for py in db.query(InsurancePayment)
        .filter(InsurancePayment.policy_id == p.id)
        .order_by(InsurancePayment.payment_date.desc())
        .all()
    ]
    return {"status": "success", "data": data}


@router.get("/insurance/policies/{policy_id}/payments")
def list_policy_payments(
    policy_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.query(InsurancePolicy).filter(
        InsurancePolicy.policy_id == policy_id,
        InsurancePolicy.user_id == current_user.id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found")
    rows = (
        db.query(InsurancePayment)
        .filter(InsurancePayment.policy_id == p.id)
        .order_by(InsurancePayment.payment_date.desc())
        .all()
    )
    return {
        "status": "success",
        "data": {"policy": _policy_dict(p, db), "total": len(rows), "items": [_payment_dict(r) for r in rows]},
    }


# --------------------------------------------------------------------------- #
# Premium payment (wallet-backed, never trusted until backend confirms)
# --------------------------------------------------------------------------- #
class PremiumPaymentRequest(BaseModel):
    amount: Optional[float] = None
    wallet_pin: str


@router.post("/insurance/policies/{policy_id}/pay-premium")
def pay_insurance_premium(
    policy_id: str,
    payload: PremiumPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.query(InsurancePolicy).filter(
        InsurancePolicy.policy_id == policy_id,
        InsurancePolicy.user_id == current_user.id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found")
    if p.status in ("cancelled", "closed"):
        raise HTTPException(status_code=400, detail=f"Cannot pay premium on a '{p.status}' policy")

    amount = payload.amount
    due = round(float(p.premium_due or 0), 2)
    if amount is None:
        if due <= 0:
            raise HTTPException(status_code=400, detail="No premium is due on this policy")
        amount = due
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Premium amount must be greater than zero")
    if due > 0 and amount > due:
        raise HTTPException(
            status_code=400,
            detail=f"Amount exceeds the pending premium of ₹{due:,.2f}",
        )

    wallet = _get_wallet(db, current_user.id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if not wallet.is_active:
        raise HTTPException(status_code=403, detail="Wallet is inactive")
    if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
        raise HTTPException(status_code=403, detail="Complete wallet setup before paying a premium")
    if not verify_password((payload.wallet_pin or "").strip(), wallet.wallet_pin_hash):
        raise HTTPException(status_code=401, detail="Invalid wallet PIN")

    balance = round(float(wallet.balance or 0), 2)
    if balance < amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance — you have ₹{balance:,.2f}",
        )

    try:
        new_balance = round(balance - amount, 2)
        payment = InsurancePayment(
            payment_id=generate_id("FA-IPAY", db, InsurancePayment),
            farmer_id=current_user.id,
            policy_id=p.id,
            amount=amount,
            payment_date=datetime.utcnow(),
            reference_number=generate_id("FA-IPREF", db, InsurancePayment),
            method="wallet",
            status="pending",
        )
        db.add(payment)
        db.flush()

        txn = WalletTransaction(
            transaction_id=generate_id("FA-WTX", db, WalletTransaction),
            wallet_id=wallet.id,
            user_id=current_user.id,
            transaction_type="debit",
            amount=amount,
            balance_after=new_balance,
            description=f"Insurance premium for {p.policy_type} ({p.provider or 'provider'}) — {payment.payment_id}",
            reference_id=payment.payment_id,
            payment_method="insurance_premium",
            status="completed",
        )
        db.add(txn)

        p.premium_paid = round(float(p.premium_paid or 0) + amount, 2)
        if due > 0:
            p.premium_due = round(due - amount, 2)
        if p.status == "pending_verification" and (p.premium_due is None or p.premium_due <= 0):
            p.status = "active"
        p.updated_at = datetime.utcnow()

        payment.status = "completed"
        payment.wallet_transaction_id = txn.transaction_id
        wallet.balance = new_balance

        create_notification(
            db=db,
            user_id=current_user.id,
            title="Insurance Premium Paid",
            message=(
                f"₹{amount:,.2f} was debited from your wallet for {p.policy_type or 'your policy'} "
                f"(Ref: {payment.payment_id}). "
                + ("Your policy has been activated." if p.status == "active" else "The remaining premium balance is still due.")
            ),
            notification_type="government",
            reference_id=payment.payment_id,
            reference_type="insurance_payment",
            icon="fa-shield-halved",
            action_url="insurance.html",
        )
        db.commit()
        db.refresh(payment)
        db.refresh(txn)
        db.refresh(wallet)
        db.refresh(p)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Premium payment failed, please try again")

    return {
        "status": "success",
        "message": f"₹{amount:,.2f} premium paid successfully",
        "data": {
            "policy": _policy_dict(p, db),
            "payment": {
                "payment_id": payment.payment_id,
                "amount": round(float(payment.amount), 2),
                "reference_number": payment.reference_number,
                "status": payment.status,
            },
            "wallet_transaction": {
                "transaction_id": txn.transaction_id,
                "balance_after": float(wallet.balance or 0),
            },
        },
    }


@router.post("/insurance/policies/{policy_id}/renew")
def renew_insurance_policy(
    policy_id: str,
    wallet_pin: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Renew a policy for another period with the user's explicit confirmation.

    When the policy has a published premium, renewal charges that premium from
    the wallet (using the provided PIN); when no premium is published, the
    renewal proceeds without a payment and the provider confirms the terms.
    """
    p = db.query(InsurancePolicy).filter(
        InsurancePolicy.policy_id == policy_id,
        InsurancePolicy.user_id == current_user.id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Policy not found")
    res_status = _score_status(p.end_date, p.status)
    if res_status not in ("active", "expiring"):
        raise HTTPException(status_code=400, detail=f"Cannot renew a '{res_status}' policy")

    product = (
        db.query(InsuranceProduct).filter(InsuranceProduct.id == p.product_id).first()
    )
    self_service = bool(product and product.policy_duration_text is not None)
    renewal_premium = round(float(p.premium or 0), 2) if p.premium is not None else None

    if renewal_premium and renewal_premium > 0:
        if not wallet_pin or not wallet_pin.strip():
            raise HTTPException(status_code=400, detail="Wallet PIN required to pay the renewal premium")
        wallet = _get_wallet(db, current_user.id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")
        if not wallet.is_active:
            raise HTTPException(status_code=403, detail="Wallet is inactive")
        if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
            raise HTTPException(status_code=403, detail="Complete wallet setup before renewing")
        if not verify_password(wallet_pin.strip(), wallet.wallet_pin_hash):
            raise HTTPException(status_code=401, detail="Invalid wallet PIN")
        balance = round(float(wallet.balance or 0), 2)
        if balance < renewal_premium:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient wallet balance — you have ₹{balance:,.2f}",
            )
        new_balance = round(balance - renewal_premium, 2)
    else:
        wallet = None
        renewal_premium = None
        new_balance = None

    try:
        months = (product.policy_duration_months if product else None) or 12
        if p.end_date and p.end_date[:4].isdigit():
            base = datetime.strptime(p.end_date, "%Y-%m-%d")
        else:
            base = datetime.utcnow()
        new_end = base + timedelta(days=30 * months)

        if renewal_premium:
            payment = InsurancePayment(
                payment_id=generate_id("FA-IPAY", db, InsurancePayment),
                farmer_id=current_user.id,
                policy_id=p.id,
                amount=renewal_premium,
                payment_date=datetime.utcnow(),
                reference_number=generate_id("FA-IPREF", db, InsurancePayment),
                method="wallet",
                premium_period="Renewal",
                status="pending",
            )
            db.add(payment)
            db.flush()
            txn = WalletTransaction(
                transaction_id=generate_id("FA-WTX", db, WalletTransaction),
                wallet_id=wallet.id,
                user_id=current_user.id,
                transaction_type="debit",
                amount=renewal_premium,
                balance_after=new_balance,
                description=f"Renewal premium for {p.policy_type} ({p.provider or 'provider'}) — {payment.payment_id}",
                reference_id=payment.payment_id,
                payment_method="insurance_renewal",
                status="completed",
            )
            db.add(txn)
            payment.status = "completed"
            payment.wallet_transaction_id = txn.transaction_id
            wallet.balance = new_balance
            p.premium_paid = round(float(p.premium_paid or 0) + renewal_premium, 2)
            p.premium_due = 0.0 if p.premium_due is not None else None

        p.end_date = new_end.date().isoformat()
        p.renewal_date = new_end.date().isoformat()
        p.renewal_count = (p.renewal_count or 0) + 1
        if p.status == "expired" or p.status == "pending_verification":
            p.status = "active"
        p.updated_at = datetime.utcnow()

        create_notification(
            db=db,
            user_id=current_user.id,
            title="Insurance Policy Renewed",
            message=(
                f"{p.policy_type} renewed for another period with {p.provider or 'your provider'}. "
                f"New cover runs until {new_end.date().isoformat()}."
                + (f" Renewal premium ₹{renewal_premium:,.2f} paid from your wallet." if renewal_premium else " No premium due at renewal — the provider will confirm terms as published.")
            ),
            notification_type="government",
            reference_id=p.id,
            reference_type="insurance_policy_renewal",
            icon="fa-shield-halved",
            action_url="insurance.html",
        )
        db.commit()
        db.refresh(p)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Renewal failed, please try again")

    return {
        "status": "success",
        "message": "Policy renewed successfully",
        "data": {
            "policy": _policy_dict(p, db),
            "renewal_count": p.renewal_count,
            "renewal_date": p.renewal_date,
            "renewal_premium_paid": renewal_premium,
        },
    }


# --------------------------------------------------------------------------- #
# Claims
# --------------------------------------------------------------------------- #
class ClaimCreate(BaseModel):
    policy_id: str
    reason: str
    description: Optional[str] = None
    incident_date: Optional[str] = None
    incident_location: Optional[str] = None
    estimated_loss: Optional[float] = None
    claim_amount: Optional[float] = None


def _validate_date(value):
    if not value:
        return None
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Incident date must be in YYYY-MM-DD format")
    return value


@router.post("/insurance/claims", status_code=201)
def create_insurance_claim(
    payload: ClaimCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    policy = db.query(InsurancePolicy).filter(
        InsurancePolicy.policy_id == payload.policy_id,
        InsurancePolicy.user_id == current_user.id,
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    res_status = _score_status(policy.end_date, policy.status)
    if res_status not in ("active", "expiring"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot file a claim on a policy with status '{res_status or policy.status}'",
        )

    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Claim reason is required")

    loss = payload.estimated_loss if payload.estimated_loss is not None else payload.claim_amount
    if loss is not None:
        try:
            loss = round(float(loss), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid claim/estimated loss amount")
        if loss <= 0:
            raise HTTPException(status_code=400, detail="Estimated loss must be greater than zero")
        coverage = policy.coverage_amount or policy.sum_insured
        if coverage and loss > float(coverage):
            raise HTTPException(
                status_code=400,
                detail=f"Estimated loss exceeds the policy coverage of ₹{float(coverage):,.2f}",
            )

    incident_date = _validate_date(payload.incident_date)

    claim_id = generate_id("FA-CLM", db, InsuranceClaim)
    claim = InsuranceClaim(
        claim_id=claim_id,
        claim_number=claim_id,
        user_id=current_user.id,
        policy_id=policy.id,
        reason=reason,
        damage_description=(payload.description or "").strip() or None,
        description=(payload.description or "").strip() or None,
        incident_date=incident_date,
        incident_location=(payload.incident_location or "").strip() or None,
        estimated_loss=loss,
        claim_amount=loss,
        status="submitted",
    )
    db.add(claim)
    db.commit()
    db.refresh(claim)

    create_notification(
        db=db,
        user_id=current_user.id,
        title="Insurance Claim Submitted",
        message=(
            f"Claim {claim_id} for {reason} was submitted against {policy.policy_type}. "
            "Your claim will be reviewed by the provider."
        ),
        notification_type="government",
        reference_id=claim.id,
        reference_type="insurance_claim",
        icon="fa-file-invoice",
        action_url="insurance.html",
    )
    db.commit()

    return {
        "status": "success",
        "message": "Insurance claim submitted successfully",
        "data": _claim_dict(claim, db),
    }


@router.get("/insurance/claims")
def list_insurance_claims(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(InsuranceClaim).filter(InsuranceClaim.user_id == current_user.id)
    if status_filter:
        q = q.filter(InsuranceClaim.status == status_filter)
    total = q.count()
    items = (
        q.order_by(InsuranceClaim.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [_claim_dict(c, db) for c in items],
        },
    }


@router.get("/insurance/claims/{claim_id}")
def get_insurance_claim(
    claim_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    claim = db.query(InsuranceClaim).filter(
        InsuranceClaim.claim_id == claim_id,
        InsuranceClaim.user_id == current_user.id,
    ).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Insurance claim not found")
    return {"status": "success", "data": _claim_dict(claim, db)}


@router.post("/insurance/claims/{claim_id}/documents", status_code=201)
async def upload_insurance_claim_document(
    claim_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    claim = db.query(InsuranceClaim).filter(
        InsuranceClaim.claim_id == claim_id,
        InsuranceClaim.user_id == current_user.id,
    ).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Insurance claim not found")
    if not document_type or not document_type.strip():
        raise HTTPException(status_code=400, detail="Document type is required")

    try:
        saved = await FileStorageService.save_upload(
            file,
            subdir="insurance-claim-documents",
            encrypt=True,
            validate_signature=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    doc = InsuranceClaimDocument(
        claim_id=claim.id,
        farmer_id=current_user.id,
        document_type=document_type.strip().lower(),
        file_name=saved["file_name"],
        file_size_bytes=saved["size_bytes"],
        mime_type=saved["content_type"] or FileStorageService.detect_mime(b""),
        storage_path=saved["path"],
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "status": "success",
        "message": "Document uploaded",
        "data": {
            "id": doc.id,
            "document_type": doc.document_type,
            "file_name": doc.file_name,
            "file_size_bytes": doc.file_size_bytes,
            "status": doc.status,
            "uploaded_at": str(doc.uploaded_at) if doc.uploaded_at else None,
        },
    }


@router.get("/insurance/claims/{claim_id}/documents/{document_id}/file")
def download_insurance_claim_document(
    claim_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    claim = db.query(InsuranceClaim).filter(
        InsuranceClaim.claim_id == claim_id,
        InsuranceClaim.user_id == current_user.id,
    ).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Insurance claim not found")
    doc = db.query(InsuranceClaimDocument).filter(
        InsuranceClaimDocument.id == document_id,
        InsuranceClaimDocument.claim_id == claim.id,
        InsuranceClaimDocument.farmer_id == current_user.id,
    ).first()
    if not doc or not doc.storage_path:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        content = FileStorageService.read_document(doc.storage_path)
    except ValueError:
        raise HTTPException(status_code=500, detail="Could not read document")

    return Response(
        content=content,
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{doc.file_name or "document"}"',
            "Content-Length": str(len(content)),
        },
    )


# --------------------------------------------------------------------------- #
# Overview / dashboard
# --------------------------------------------------------------------------- #
@router.get("/insurance/overview")
def insurance_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    policies = [
        _policy_dict(p, db)
        for p in db.query(InsurancePolicy)
        .filter(InsurancePolicy.user_id == current_user.id)
        .order_by(InsurancePolicy.created_at.desc())
        .all()
    ]
    active = [p for p in policies if p["status"] in ("active", "expiring")]
    expiring = [p for p in policies if p["status"] == "expiring"]
    total_coverage = round(
        sum(float(p["coverage_amount"] or 0) for p in active), 2
    )
    total_premium = round(sum(float(p["premium_paid"] or 0) for p in policies), 2)

    claims = (
        db.query(InsuranceClaim)
        .filter(InsuranceClaim.user_id == current_user.id)
        .all()
    )
    open_claims = [c for c in claims if c.status in ("submitted", "under_review", "documents_required")]

    applications_count = (
        db.query(InsuranceApplication)
        .filter(InsuranceApplication.farmer_id == current_user.id)
        .count()
    )
    saved_count = (
        db.query(SavedInsurance)
        .filter(SavedInsurance.farmer_id == current_user.id)
        .count()
    )

    next_premium = None
    next_due_date = None
    for p in policies:
        due = p.get("premium_due")
        if due and due > 0:
            if next_due_date is None or (p.get("premium_due_date") and p["premium_due_date"] < next_due_date):
                next_due_date = p.get("premium_due_date")
                next_premium = due

    total_premium_due = round(
        sum(float(p.get("premium_due") or 0) for p in policies), 2
    )

    return {
        "status": "success",
        "data": {
            "has_policies": bool(policies),
            "total_policies": len(policies),
            "active_policies_count": len(active),
            "expiring_count": len(expiring),
            "total_coverage": total_coverage,
            "total_premium_paid": total_premium,
            "total_premium_due": total_premium_due,
            "next_premium_due": next_premium,
            "next_premium_due_date": next_due_date,
            "open_claims_count": len(open_claims),
            "total_claims": len(claims),
            "applications_count": applications_count,
            "saved_count": saved_count,
        },
    }