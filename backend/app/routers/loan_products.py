"""Agricultural Loans router.

Real catalogue + real, per-farmer financing operations:

  * Loan products (verified, lender-published catalogue)
  * Categories / filter options / search
  * Per-farmer saved loans (no duplicates)
  * Eligibility checker (stored per farmer, lender decides)
  * Loan applications with backend-generated reference numbers
  * Application documents (private, ownership-checked)
  * Farmer loans + repayment history (ownership-scoped)
  * Verified repayments via the Farm Assist wallet (only marked
    completed after the wallet debit succeeds)

Every farmer-scoped query is server-side restricted to the authenticated user;
``farmer_id`` is always derived from the token, never trusted from the client.
"""

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.database.connection import get_db
from app.database.seed_loan_products import seed_loan_products, CATEGORY_ORDER
from app.integrations.file_storage import FileStorageService
from app.utils.auth import get_current_user, generate_id, verify_password
from app.utils.notification_helper import create_notification
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
from app.models.loan_product import (
    AgriculturalLoanProduct,
    SavedAgriculturalLoan,
    AgriculturalLoanApplication,
    AgriculturalLoanDocument,
    AgriculturalFarmerLoan,
    AgriculturalLoanRepayment,
    AgriculturalLoanEligibility,
)

router = APIRouter(prefix="/api/v1", tags=["Agricultural Loans"])


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


def _resolve_product(db: Session, product_id: str) -> AgriculturalLoanProduct:
    p = db.query(AgriculturalLoanProduct).filter(
        (AgriculturalLoanProduct.product_id == product_id)
        | (AgriculturalLoanProduct.id == product_id)
    ).first()
    return p


def _product_dict(p: AgriculturalLoanProduct, db: Session, user_id: Optional[str]) -> dict:
    saved = False
    if user_id:
        saved = (
            db.query(SavedAgriculturalLoan)
            .filter(
                SavedAgriculturalLoan.farmer_id == user_id,
                SavedAgriculturalLoan.product_id == p.id,
            )
            .first()
        ) is not None

    max_amount = p.max_amount
    if max_amount is not None:
        max_amount = round(float(max_amount), 2)

    return {
        "id": p.id,
        "product_id": p.product_id,
        "lender": p.lender,
        "lender_id": p.lender_id,
        "lender_type": p.lender_type,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "loan_type": p.loan_type,
        "min_amount": round(float(p.min_amount), 2) if p.min_amount is not None else None,
        "max_amount": max_amount,
        "interest_rate": p.interest_rate,
        "interest_rate_annual": p.interest_rate_annual,
        "tenure_months": p.tenure_months,
        "tenure_text": p.tenure_text,
        "repayment_frequency": p.repayment_frequency,
        "eligibility": p.eligibility,
        "collateral_requirement": p.collateral_requirement,
        "required_documents": _parse_list(p.required_documents),
        "application_method": p.application_method,
        "fees": p.fees,
        "official_url": p.official_url,
        "source": p.source,
        "source_url": p.source_url,
        "state": p.state,
        "government_backed": bool(p.government_backed),
        "scheme_name": p.scheme_name,
        "scheme_id": p.scheme_id,
        "status": p.status,
        "last_verified_at": str(p.last_verified_at) if p.last_verified_at else None,
        "is_saved": saved,
    }


def _application_dict(a: AgriculturalLoanApplication, db: Session) -> dict:
    product = db.query(AgriculturalLoanProduct).filter(AgriculturalLoanProduct.id == a.product_id).first()
    docs = db.query(AgriculturalLoanDocument).filter(
        AgriculturalLoanDocument.application_id == a.id
    ).all()
    return {
        "id": a.id,
        "application_id": a.application_id,
        "reference_number": a.reference_number,
        "product_id": a.product_id,
        "loan_name": product.name if product else None,
        "lender": product.lender if product else None,
        "category": product.category if product else None,
        "requested_amount": a.requested_amount,
        "purpose": a.purpose,
        "applicant_name": a.applicant_name,
        "phone_number": a.phone_number,
        "email": a.email,
        "state": a.state,
        "district": a.district,
        "farm_size": a.farm_size,
        "crop": a.crop,
        "land_type": a.land_type,
        "status": a.status,
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


def _farmer_loan_dict(fl: AgriculturalFarmerLoan, db: Session) -> dict:
    repayments = db.query(AgriculturalLoanRepayment).filter(
        AgriculturalLoanRepayment.farmer_loan_id == fl.id
    ).order_by(AgriculturalLoanRepayment.payment_date.desc()).all()
    return {
        "id": fl.id,
        "farmer_loan_id": fl.farmer_loan_id,
        "application_id": fl.application_id,
        "lender": fl.lender,
        "loan_name": fl.loan_name,
        "principal_amount": fl.principal_amount,
        "outstanding_amount": fl.outstanding_amount,
        "interest_rate_annual": fl.interest_rate_annual,
        "emi_amount": fl.emi_amount,
        "tenure_months": fl.tenure_months,
        "next_payment": fl.next_payment,
        "next_due_date": str(fl.next_due_date) if fl.next_due_date else None,
        "status": fl.status,
        "disbursed_at": str(fl.disbursed_at) if fl.disbursed_at else None,
        "repayments_count": len(repayments),
    }


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
@router.get("/loans/categories")
def loan_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_loan_products(db)
    rows = (
        db.query(AgriculturalLoanProduct.category, func.count(AgriculturalLoanProduct.id))
        .filter(AgriculturalLoanProduct.status == "active")
        .group_by(AgriculturalLoanProduct.category)
        .all()
    )
    counts = {c: n for c, n in rows if c}
    ordered = []
    for cat in CATEGORY_ORDER:
        if cat == "All":
            continue
        ordered.append({"name": cat, "count": int(counts.get(cat, 0))})
    ordered.sort(key=lambda x: x["count"], reverse=True)
    total = int(db.query(func.count(AgriculturalLoanProduct.id)).filter(
        AgriculturalLoanProduct.status == "active"
    ).scalar() or 0)
    return {"status": "success", "data": {"categories": ordered, "total": total}}


@router.get("/loans/filters")
def loan_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_loan_products(db)
    q = db.query(AgriculturalLoanProduct).filter(AgriculturalLoanProduct.status == "active")
    lenders = [r[0] for r in db.query(AgriculturalLoanProduct.lender).filter(
        AgriculturalLoanProduct.status == "active", AgriculturalLoanProduct.lender.isnot(None)
    ).distinct().order_by(AgriculturalLoanProduct.lender).all()]
    states = [r[0] for r in db.query(AgriculturalLoanProduct.state).filter(
        AgriculturalLoanProduct.status == "active", AgriculturalLoanProduct.state.isnot(None)
    ).distinct().order_by(AgriculturalLoanProduct.state).all()]
    return {
        "status": "success",
        "data": {
            "lenders": lenders,
            "states": states,
            "government_backed": True,
            "collateral_options": True,
        },
    }


@router.get("/loans/products")
def list_loan_products(
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    search: Optional[str] = None,
    category: Optional[str] = None,
    lender: Optional[str] = None,
    state: Optional[str] = None,
    government_backed: Optional[int] = Query(None, ge=0, le=1),
    collateral_free: Optional[int] = Query(None, ge=0, le=1),
    sort: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_loan_products(db)
    q = db.query(AgriculturalLoanProduct).filter(AgriculturalLoanProduct.status == "active")

    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                AgriculturalLoanProduct.name.ilike(term),
                AgriculturalLoanProduct.lender.ilike(term),
                AgriculturalLoanProduct.category.ilike(term),
                AgriculturalLoanProduct.description.ilike(term),
                AgriculturalLoanProduct.eligibility.ilike(term),
                AgriculturalLoanProduct.state.ilike(term),
                AgriculturalLoanProduct.loan_type.ilike(term),
            )
        )
    if category and category != "All":
        q = q.filter(AgriculturalLoanProduct.category == category)
    if lender:
        q = q.filter(AgriculturalLoanProduct.lender == lender)
    if state:
        q = q.filter(or_(
            AgriculturalLoanProduct.state == "All India",
            AgriculturalLoanProduct.state.ilike(f"%{state}%"),
        ))
    if government_backed is not None:
        q = q.filter(AgriculturalLoanProduct.government_backed == bool(government_backed))
    if collateral_free is not None:
        if collateral_free:
            q = q.filter(
                or_(
                    AgriculturalLoanProduct.collateral_requirement.is_(None),
                    AgriculturalLoanProduct.collateral_requirement.ilike("%nil%"),
                )
            )
        else:
            q = q.filter(AgriculturalLoanProduct.collateral_requirement.isnot(None))

    total = q.count()
    if sort == "amount_asc":
        q = q.order_by(AgriculturalLoanProduct.max_amount.asc().nullslast())
    elif sort == "amount_desc":
        q = q.order_by(AgriculturalLoanProduct.max_amount.desc().nullslast())
    elif sort == "rate":
        q = q.order_by(AgriculturalLoanProduct.interest_rate_annual.asc().nullslast())
    elif sort == "name":
        q = q.order_by(AgriculturalLoanProduct.name.asc())
    else:
        q = q.order_by(AgriculturalLoanProduct.last_verified_at.desc().nullslast(), AgriculturalLoanProduct.name.asc())

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


@router.get("/loans/search")
def search_loan_products(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_loan_products(db)
    term = f"%{q.strip()}%"
    items = (
        db.query(AgriculturalLoanProduct)
        .filter(
            AgriculturalLoanProduct.status == "active",
            or_(
                AgriculturalLoanProduct.name.ilike(term),
                AgriculturalLoanProduct.lender.ilike(term),
                AgriculturalLoanProduct.category.ilike(term),
                AgriculturalLoanProduct.description.ilike(term),
                AgriculturalLoanProduct.eligibility.ilike(term),
                AgriculturalLoanProduct.state.ilike(term),
            ),
        )
        .order_by(AgriculturalLoanProduct.name.asc())
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": [_product_dict(p, db, current_user.id) for p in items],
    }


@router.get("/loans/products/saved")
def saved_loan_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        db.query(SavedAgriculturalLoan)
        .filter(SavedAgriculturalLoan.farmer_id == current_user.id)
        .order_by(SavedAgriculturalLoan.created_at.desc())
    )
    total = q.count()
    rows = q.offset((page - 1) * limit).limit(limit).all()
    items = []
    for row in rows:
        p = db.query(AgriculturalLoanProduct).filter(AgriculturalLoanProduct.id == row.product_id).first()
        if p:
            item = _product_dict(p, db, current_user.id)
            item["saved_at"] = str(row.created_at) if row.created_at else None
            items.append(item)
    return {
        "status": "success",
        "data": {"total": total, "page": page, "limit": limit, "items": items},
    }


@router.get("/loans/products/{product_id}")
def get_loan_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_loan_products(db)
    p = _resolve_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Loan product not found")
    return {"status": "success", "data": _product_dict(p, db, current_user.id)}


# --------------------------------------------------------------------------- #
# Saved loans (write actions)
# --------------------------------------------------------------------------- #
# Saved loans
# --------------------------------------------------------------------------- #
@router.post("/loans/products/{product_id}/save", status_code=201)
def save_loan_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _resolve_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Loan product not found")
    existing = (
        db.query(SavedAgriculturalLoan)
        .filter(SavedAgriculturalLoan.farmer_id == current_user.id, SavedAgriculturalLoan.product_id == p.id)
        .first()
    )
    if existing:
        return {"status": "success", "data": {"is_saved": True, "message": "Loan already saved"}}
    db.add(SavedAgriculturalLoan(farmer_id=current_user.id, product_id=p.id))
    db.commit()
    return {"status": "success", "data": {"is_saved": True, "message": "Loan saved"}}


@router.delete("/loans/products/{product_id}/save")
def unsave_loan_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _resolve_product(db, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Loan product not found")
    existing = (
        db.query(SavedAgriculturalLoan)
        .filter(SavedAgriculturalLoan.farmer_id == current_user.id, SavedAgriculturalLoan.product_id == p.id)
        .first()
    )
    if not existing:
        return {"status": "success", "data": {"is_saved": False, "message": "Loan was not saved"}}
    db.delete(existing)
    db.commit()
    return {"status": "success", "data": {"is_saved": False, "message": "Loan removed from saved"}}


# --------------------------------------------------------------------------- #
# Eligibility checker
# --------------------------------------------------------------------------- #
class EligibilityRequest(BaseModel):
    product_id: str
    farmer_type: Optional[str] = None          # individual | group | self_help_group | joint_liability_group | ...
    farmer_category: Optional[str] = None      # marginal | small | semi_medium | medium | large
    state: Optional[str] = None
    district: Optional[str] = None
    crop: Optional[str] = None
    farm_size_acres: Optional[float] = None
    loan_amount: Optional[float] = None
    has_existing_agri_loan: Optional[bool] = None
    age: Optional[int] = None
    gender: Optional[str] = None


def _parse_rate(value) -> Optional[float]:
    """Best-effort numeric extraction from a rate string (e.g. \"9.2% p.a.\")."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"(\d+(?:\.\d+)?)", str(value))
    return float(m.group(1)) if m else None


def _check_eligibility(p: AgriculturalLoanProduct, req: EligibilityRequest) -> dict:
    """Deterministic, transparent heuristic based ONLY on published product fields.

    The verdict is explicitly indicative: Farm Assist never approves loans and
    does not claim the lender's decision. Criteria are derived from the stored
    eligibility text and amount/tenure ranges for the product.
    """
    now = datetime.utcnow()
    matched = []
    missing = []
    warnings = []

    # 1) Published amount range
    amount = req.loan_amount
    if amount is not None and p.min_amount is not None and p.max_amount is not None:
        if p.min_amount <= amount <= p.max_amount:
            matched.append(f"Requested amount ₹{amount:,.0f} falls within the published range (₹{p.min_amount:,.0f} – ₹{p.max_amount:,.0f}).")
        elif amount > p.max_amount:
            missing.append(f"Requested amount exceeds the published maximum of ₹{p.max_amount:,.0f}.")
        else:
            warnings.append(f"Requested amount is below the typical minimum of ₹{p.min_amount:,.0f}; check with the lender.")
    elif amount is not None and p.max_amount is not None and amount > p.max_amount:
        missing.append(f"Requested amount exceeds the published maximum of ₹{p.max_amount:,.0f}.")
    else:
        warnings.append("Amount range not published for this product — unable to verify amount fit.")

    # 2) Farmer type / category
    eligibility_text = (p.eligibility or "").lower()
    farmer_type = (req.farmer_type or "").lower()
    farmer_category = (req.farmer_category or "").lower()

    if farmer_type:
        fm_kw = farmer_type.replace("_", " ")
        if any(token in eligibility_text for token in [fm_kw, fm_kw.replace(" ", "")]):
            matched.append(f"Farmer type '{farmer_type.replace('_', ' ')}' appears in the listed criteria.")
        elif eligibility_text and ("farmer" in eligibility_text):
            warnings.append("Farmer type is not precisely specified in the published criteria.")
        else:
            warnings.append("No farmer-type requirement is published for this product.")
    if farmer_category:
        fc_kw = farmer_category.replace("_", " ")
        if any(token in eligibility_text for token in [fc_kw, fc_kw.replace(" ", "")]):
            matched.append(f"Farmer category '{farmer_category.replace('_', ' ')}' appears in the listed criteria.")
        else:
            warnings.append("Farmer category is not validated against published criteria.")

    # 3) State / district recency
    state = (req.state or "").strip().lower()
    if not state:
        warnings.append("No state supplied — state-wise availability not verified.")
    elif p.state and p.state.strip().lower() != "all india":
        p_state = p.state.strip().lower()
        if state in p_state or p_state in state:
            matched.append(f"Product availability covers {p.state}.")
        else:
            missing.append(f"Product availability lists {p.state}; your state does not obviously match.")
    elif p.state and p.state.strip().lower() == "all india":
        matched.append("Product is available All India.")

    # 4) Crop / purpose
    crop = (req.crop or "").strip().lower()
    if crop:
        if crop in eligibility_text:
            matched.append(f"Crop '{req.crop}' appears in the listed criteria.")
        else:
            warnings.append(f"Crop '{req.crop}' is not explicitly named in the published criteria.")

    # 5) Landholding
    if req.farm_size_acres is not None and req.farm_size_acres > 0:
        if any(kw in eligibility_text for kw in ["acre", "hectare", "landholding", "land holding", "own land"]):
            matched.append("Landholding is referenced in the eligibility criteria.")
        else:
            warnings.append("No landholding threshold is published for this product.")

    # 6) Existing loan
    if req.has_existing_agri_loan is not None:
        if any(kw in eligibility_text for kw in ["fresh", "no outstanding", "existing loan"]):
            warnings.append("Existing-dues policy: verify with the lender whether prior loans affect this product.")
        else:
            warnings.append("No existing-dues policy is published for this product.")

    # 7) Companion products threshold
    if not matched and not warnings and not missing:
        warnings.append("No detailed eligibility criteria are published for this product — contact the lender directly.")

    # Verdict
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

    result = {
        "verdict": verdict,
        "status_label": status_label,
        "headline": headline,
        "matched": matched,
        "missing": missing,
        "warnings": warnings,
        "disclaimer": (
            "This is an indicative check based only on lender-published information. "
            "Farm Assist does not sanction loans and this result is not loan approval. "
            "Final eligibility and approval are decided solely by the lender."
        ),
        "checked_at": str(now),
    }
    return result


@router.post("/loans/check-eligibility")
def check_loan_eligibility(
    payload: EligibilityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_loan_products(db)
    p = _resolve_product(db, payload.product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Loan product not found")

    result = _check_eligibility(p, payload)
    record = AgriculturalLoanEligibility(
        farmer_id=current_user.id,
        product_id=p.id,
        inputs=payload.dict(),
        result=result,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    product = _product_dict(p, db, current_user.id)
    return {
        "status": "success",
        "message": "Eligibility check completed",
        "data": {
            "check_id": record.id,
            "result": result,
            "product": product,
        },
    }


# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
class ApplicationCreate(BaseModel):
    product_id: str
    applicant_name: Optional[str] = None
    phone_number: str
    email: Optional[str] = None
    aadhaar_number: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    farm_size: Optional[float] = None
    crop: Optional[str] = None
    land_type: Optional[str] = None
    purpose: Optional[str] = None
    requested_amount: float
    notes: Optional[str] = None


def _next_reference(db: Session) -> str:
    rows = db.query(AgriculturalLoanApplication.application_id).all()
    nums = []
    for (value,) in rows:
        if value and value.startswith("FA-LAPP-"):
            try:
                nums.append(int(value.split("-")[-1]))
            except ValueError:
                continue
    return f"FA-LAPP-{str((max(nums) + 1) if nums else 1).zfill(6)}"


@router.post("/loans/applications", status_code=201)
def create_loan_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seed_loan_products(db)
    p = _resolve_product(db, payload.product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Loan product not found")

    amount = round(float(payload.requested_amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Requested amount must be greater than zero")
    if p.max_amount is not None and amount > float(p.max_amount):
        raise HTTPException(
            status_code=400,
            detail=f"Requested amount exceeds the published maximum of ₹{float(p.max_amount):,.2f} for this product.",
        )
    if amount < 100 and p.min_amount is None:
        raise HTTPException(status_code=400, detail="Requested amount too low")

    phone = (payload.phone_number or "").strip()
    digits = re.sub(r"\D", "", phone)
    if not (10 <= len(digits) <= 13):
        raise HTTPException(status_code=400, detail="Phone number must contain 10-13 digits")
    aadhaar = (payload.aadhaar_number or "").strip()
    if aadhaar and (not aadhaar.isdigit() or len(aadhaar) != 12):
        raise HTTPException(status_code=400, detail="Aadhaar must be exactly 12 digits")

    application_id = _next_reference(db)
    app = AgriculturalLoanApplication(
        id=None,
        application_id=application_id,
        farmer_id=current_user.id,
        product_id=p.id,
        applicant_name=(payload.applicant_name or "").strip() or (current_user.full_name or None),
        phone_number=phone,
        email=(payload.email or "").strip() or None,
        aadhaar_number=aadhaar or None,
        state=(payload.state or "").strip() or None,
        district=(payload.district or "").strip() or None,
        farm_size=payload.farm_size,
        crop=(payload.crop or "").strip() or None,
        land_type=(payload.land_type or "").strip() or None,
        purpose=(payload.purpose or "").strip() or None,
        requested_amount=amount,
        status="submitted",
        notes=(payload.notes or "").strip() or None,
        reference_number=application_id,
        submitted_at=datetime.utcnow(),
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    create_notification(
        db=db,
        user_id=current_user.id,
        title="Loan Application Submitted",
        message=(
            f"Application {application_id} for {p.name} (₹{amount:,.2f}) has been "
            "submitted. The lender will review it directly — Farm Assist does not "
            "approve loans."
        ),
        notification_type="loan",
        reference_id=app.id,
        reference_type="loan_application",
        icon="fa-hand-holding-dollar",
        action_url="loans.html",
    )
    db.commit()

    return {
        "status": "success",
        "message": "Loan application submitted",
        "data": _application_dict(app, db),
    }


@router.get("/loans/applications")
def list_loan_applications(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(AgriculturalLoanApplication).filter(AgriculturalLoanApplication.farmer_id == current_user.id)
    if status_filter:
        q = q.filter(AgriculturalLoanApplication.status == status_filter)
    total = q.count()
    items = (
        q.order_by(AgriculturalLoanApplication.submitted_at.desc())
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


@router.get("/loans/applications/{application_id}")
def get_loan_application(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = db.query(AgriculturalLoanApplication).filter(
        AgriculturalLoanApplication.application_id == application_id,
        AgriculturalLoanApplication.farmer_id == current_user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Loan application not found")
    return {"status": "success", "data": _application_dict(app, db)}


@router.patch("/loans/applications/{application_id}")
def update_loan_application(
    application_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = db.query(AgriculturalLoanApplication).filter(
        AgriculturalLoanApplication.application_id == application_id,
        AgriculturalLoanApplication.farmer_id == current_user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Loan application not found")
    allowed = {"purpose", "notes"}
    for key, value in payload.items():
        if key in allowed:
            setattr(app, key, value)
    db.commit()
    db.refresh(app)
    return {"status": "success", "message": "Application updated", "data": _application_dict(app, db)}


# --------------------------------------------------------------------------- #
# Application documents (private, ownership-checked)
# --------------------------------------------------------------------------- #
@router.post("/loans/applications/{application_id}/documents", status_code=201)
async def upload_loan_application_document(
    application_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = db.query(AgriculturalLoanApplication).filter(
        AgriculturalLoanApplication.application_id == application_id,
        AgriculturalLoanApplication.farmer_id == current_user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Loan application not found")
    if not document_type or not document_type.strip():
        raise HTTPException(status_code=400, detail="Document type is required")

    try:
        saved = await FileStorageService.save_upload(
            file,
            subdir="loan-documents",
            encrypt=True,
            validate_signature=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    doc = AgriculturalLoanDocument(
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


@router.get("/loans/applications/{application_id}/documents/{document_id}/file")
def download_loan_application_document(
    application_id: str,
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = db.query(AgriculturalLoanApplication).filter(
        AgriculturalLoanApplication.application_id == application_id,
        AgriculturalLoanApplication.farmer_id == current_user.id,
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Loan application not found")
    doc = db.query(AgriculturalLoanDocument).filter(
        AgriculturalLoanDocument.id == document_id,
        AgriculturalLoanDocument.application_id == app.id,
        AgriculturalLoanDocument.farmer_id == current_user.id,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.storage_path:
        raise HTTPException(status_code=404, detail="Document file missing")

    try:
        content = FileStorageService.read_document(doc.storage_path)
    except ValueError:
        raise HTTPException(status_code=500, detail="Could not read document")

    mime = doc.mime_type or "application/octet-stream"
    response = Response(
        content=content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.file_name or "document"}"',
            "Content-Length": str(len(content)),
        },
    )
    return response


# --------------------------------------------------------------------------- #
# Farmer loans + repayments
# --------------------------------------------------------------------------- #
@router.get("/loans/farmer-loans")
def list_farmer_loans(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(AgriculturalFarmerLoan).filter(AgriculturalFarmerLoan.farmer_id == current_user.id)
    if status_filter:
        q = q.filter(AgriculturalFarmerLoan.status == status_filter)
    items = q.order_by(AgriculturalFarmerLoan.created_at.desc()).all()
    return {
        "status": "success",
        "data": {"total": len(items), "items": [_farmer_loan_dict(fl, db) for fl in items]},
    }


@router.get("/loans/farmer-loans/{farmer_loan_id}/repayments")
def list_farmer_loan_repayments(
    farmer_loan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fl = db.query(AgriculturalFarmerLoan).filter(
        AgriculturalFarmerLoan.farmer_loan_id == farmer_loan_id,
        AgriculturalFarmerLoan.farmer_id == current_user.id,
    ).first()
    if not fl:
        raise HTTPException(status_code=404, detail="Farmer loan not found")
    rows = (
        db.query(AgriculturalLoanRepayment)
        .filter(AgriculturalLoanRepayment.farmer_loan_id == fl.id)
        .order_by(AgriculturalLoanRepayment.payment_date.desc())
        .all()
    )
    return {
        "status": "success",
        "data": {
            "farmer_loan": _farmer_loan_dict(fl, db),
            "total": len(rows),
            "items": [
                {
                    "repayment_id": r.repayment_id,
                    "amount": round(float(r.amount), 2),
                    "payment_date": str(r.payment_date) if r.payment_date else None,
                    "reference_number": r.reference_number,
                    "method": r.method,
                    "status": r.status,
                    "wallet_transaction_id": r.wallet_transaction_id,
                }
                for r in rows
            ],
        },
    }


@router.get("/loans/overview")
def loan_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_loans = (
        db.query(AgriculturalFarmerLoan)
        .filter(
            AgriculturalFarmerLoan.farmer_id == current_user.id,
            AgriculturalFarmerLoan.status == "active",
        )
        .all()
    )
    all_loans = (
        db.query(AgriculturalFarmerLoan)
        .filter(AgriculturalFarmerLoan.farmer_id == current_user.id)
        .all()
    )
    total_outstanding = round(
        sum(float(fl.outstanding_amount or 0) for fl in active_loans), 2
    )
    total_borrowed = round(
        sum(float(fl.principal_amount or 0) for fl in all_loans), 2
    )
    total_repaid = float(
        db.query(func.coalesce(func.sum(AgriculturalLoanRepayment.amount), 0.0))
        .filter(
            AgriculturalLoanRepayment.farmer_id == current_user.id,
            AgriculturalLoanRepayment.status == "completed",
        )
        .scalar()
        or 0
    )
    monthly_emi = round(sum(float(fl.emi_amount or 0) for fl in active_loans), 2)

    next_due = None
    next_amount = None
    for fl in active_loans:
        if fl.next_due_date:
            if next_due is None or fl.next_due_date < next_due:
                next_due = fl.next_due_date
                next_amount = fl.next_payment

    applications = (
        db.query(AgriculturalLoanApplication)
        .filter(AgriculturalLoanApplication.farmer_id == current_user.id)
        .count()
    )

    return {
        "status": "success",
        "data": {
            "has_loans": bool(all_loans),
            "active_loans_count": len(active_loans),
            "total_outstanding": total_outstanding,
            "total_borrowed": total_borrowed,
            "total_repaid": round(total_repaid, 2),
            "monthly_emi": monthly_emi,
            "next_due_date": str(next_due) if next_due else None,
            "next_payment": next_amount,
            "applications_count": applications,
        },
    }


class RepaymentRequest(BaseModel):
    amount: float = Field(..., gt=0)
    wallet_pin: str


@router.post("/loans/farmer-loans/{farmer_loan_id}/repay")
def repay_loan(
    farmer_loan_id: str,
    payload: RepaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fl = db.query(AgriculturalFarmerLoan).filter(
        AgriculturalFarmerLoan.farmer_loan_id == farmer_loan_id,
        AgriculturalFarmerLoan.farmer_id == current_user.id,
    ).first()
    if not fl:
        raise HTTPException(status_code=404, detail="Farmer loan not found")
    if fl.status not in ("active",):
        raise HTTPException(status_code=400, detail=f"Cannot repay a loan with status '{fl.status}'")

    amount = round(float(payload.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    outstanding = round(float(fl.outstanding_amount or 0), 2)
    if outstanding <= 0:
        raise HTTPException(status_code=400, detail="This loan has no outstanding balance")
    if amount > outstanding:
        raise HTTPException(
            status_code=400,
            detail=f"Amount exceeds the outstanding balance of ₹{outstanding:,.2f}",
        )

    wallet = _get_wallet(db, current_user.id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if not wallet.is_active:
        raise HTTPException(status_code=403, detail="Wallet is inactive")
    if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
        raise HTTPException(status_code=403, detail="Complete wallet setup before repaying a loan")
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

        repayment = AgriculturalLoanRepayment(
            repayment_id=generate_id("FA-RPY", db, AgriculturalLoanRepayment),
            farmer_loan_id=fl.id,
            farmer_id=current_user.id,
            amount=amount,
            payment_date=datetime.utcnow(),
            reference_number=generate_id("FA-RREF", db, AgriculturalLoanRepayment),
            method="wallet",
            status="pending",
        )
        db.add(repayment)
        db.flush()

        txn = WalletTransaction(
            transaction_id=generate_id("FA-WTX", db, WalletTransaction),
            wallet_id=wallet.id,
            user_id=current_user.id,
            transaction_type="debit",
            amount=amount,
            balance_after=new_balance,
            description=f"Loan repayment for {fl.loan_name or 'agricultural loan'} ({fl.lender or 'lender'}) — {repayment.repayment_id}",
            reference_id=repayment.repayment_id,
            payment_method="loan_payment",
            status="completed",
        )
        db.add(txn)

        new_outstanding = round(outstanding - amount, 2)
        fl.outstanding_amount = new_outstanding
        fl.next_payment = new_outstanding if new_outstanding > 0 else None
        if new_outstanding > 0:
            if fl.next_due_date:
                fl.next_due_date = fl.next_due_date.replace(month=min(fl.next_due_date.month + 1, 12))
        else:
            fl.status = "closed"
            fl.next_due_date = None

        repayment.status = "completed"
        repayment.wallet_transaction_id = txn.transaction_id
        wallet.balance = new_balance

        create_notification(
            db=db,
            user_id=current_user.id,
            title="Loan Repayment Received",
            message=(
                f"₹{amount:,.2f} was debited from your wallet towards "
                f"{fl.loan_name or 'your loan'} (Ref: {repayment.repayment_id}). "
                f"Remaining outstanding: ₹{new_outstanding:,.2f}."
            ),
            notification_type="loan",
            reference_id=repayment.repayment_id,
            reference_type="loan_repayment",
            icon="fa-hand-holding-dollar",
            action_url="loans.html",
        )
        db.commit()
        db.refresh(repayment)
        db.refresh(txn)
        db.refresh(wallet)
        db.refresh(fl)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Repayment failed, please try again")

    return {
        "status": "success",
        "message": f"₹{amount:,.2f} repaid successfully",
        "data": {
            "farmer_loan": _farmer_loan_dict(fl, db),
            "repayment": {
                "repayment_id": repayment.repayment_id,
                "amount": round(float(repayment.amount), 2),
                "reference_number": repayment.reference_number,
                "status": repayment.status,
            },
            "wallet_transaction": {
                "transaction_id": txn.transaction_id,
                "balance_after": float(wallet.balance or 0),
            },
        },
    }