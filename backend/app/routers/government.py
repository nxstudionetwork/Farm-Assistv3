from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, cast, String

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.government import (
    GovernmentScheme, SavedScheme, SchemeApplication,
    InsurancePolicy, InsuranceClaim,
)
from app.services.notification_service import create_scheme_notification
from app.services import scheme_sync_service as scheme_sync

router = APIRouter(prefix="/api/v1", tags=["Government & Insurance"])

# Fixed category list used by the UI's quick-filter bar.
SCHEME_CATEGORIES = [
    "Income Support", "Crop Insurance", "Agricultural Loans", "Subsidies",
    "Irrigation", "Equipment & Machinery", "Seeds & Fertilizers", "Livestock",
    "Horticulture", "Organic Farming", "Women Farmers", "Small & Marginal Farmers",
    "Farmer Welfare", "State Schemes", "Central Schemes",
]


class SchemeApplyRequest(BaseModel):
    notes: Optional[str] = None


class EligibilityRequest(BaseModel):
    farmer_type: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    land_size_hectares: Optional[float] = None
    crop: Optional[str] = None
    age: Optional[int] = None
    income_category: Optional[str] = None
    gender: Optional[str] = None


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
    sort: Optional[str] = None,
    saved_only: int = Query(0, ge=0, le=1),
    recommended: int = Query(0, ge=0, le=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(GovernmentScheme)

    # Recommended scope is resolved separately (below) so the base list query
    # is not polluted by the per-user scratch filtering logic.
    if not recommended:
        if search:
            like = f"%{search}%"
            q = q.filter(
                or_(
                    GovernmentScheme.name.ilike(like),
                    GovernmentScheme.description.ilike(like),
                    GovernmentScheme.department.ilike(like),
                    GovernmentScheme.category.ilike(like),
                    GovernmentScheme.state.ilike(like),
                    GovernmentScheme.crop.ilike(like),
                    GovernmentScheme.benefit_type.ilike(like),
                    GovernmentScheme.benefits.ilike(like),
                    GovernmentScheme.eligibility.ilike(like),
                    cast(GovernmentScheme.related_crops, String).ilike(like),
                    cast(GovernmentScheme.eligible_farmer_types, String).ilike(like),
                )
            )
        if state:
            # Show central/all-India schemes in every state, plus state-specific matches.
            from sqlalchemy import func as _func
            q = q.filter(
                or_(
                    GovernmentScheme.state.ilike(f"%{state}%"),
                    GovernmentScheme.state.is_(None),
                    GovernmentScheme.state == "",
                    GovernmentScheme.state.ilike("%all india%"),
                    GovernmentScheme.state.ilike("%national%"),
                )
            )
        if category:
            base = category.lower()
            if base in ("central", "central schemes"):
                q = q.filter(GovernmentScheme.level == "central")
            elif base in ("state", "state schemes"):
                q = q.filter(GovernmentScheme.level == "state")
            else:
                q = q.filter(GovernmentScheme.category.ilike(f"%{category}%"))

    if status:
        q = q.filter(GovernmentScheme.status == status)
    else:
        q = q.filter(GovernmentScheme.status == "active")

    # ----- user-specific saved scope -----
    saved_ids = {s.scheme_id for s in _saved(db, current_user.id)} if saved_only else set()
    if saved_only:
        q = q.filter(GovernmentScheme.id.in_(saved_ids))

    total = q.count()

    if recommended:
        items = _recommended(db, current_user, q)
        q_total = len(items)
    else:
        q_total = total
        if sort == "deadline":
            q = q.order_by(GovernmentScheme.application_deadline.asc())
        elif sort == "alpha":
            q = q.order_by(GovernmentScheme.name.asc())
        elif sort == "recent":
            q = q.order_by(GovernmentScheme.updated_at.desc(), GovernmentScheme.created_at.desc())
        else:
            q = q.order_by(GovernmentScheme.created_at.desc())
        items = q.offset((page - 1) * limit).limit(limit).all()

    payload = [_scheme_dict(s, saved_ids) for s in items]
    return {
        "status": "success",
        "data": {
            "total": q_total,
            "page": page,
            "limit": limit,
            "total_pages": (q_total + limit - 1) // limit if q_total else 0,
            "items": payload,
        },
    }


def _saved(db: Session, farmer_id: str):
    return db.query(SavedScheme).filter(SavedScheme.farmer_id == farmer_id).all()


def _scheme_dict(s: GovernmentScheme, saved_ids=None) -> dict:
    saved_ids = saved_ids or set()
    return {
        "id": s.id,
        "scheme_id": s.scheme_id,
        "name": s.name,
        "description": s.description,
        "department": s.department,
        "level": s.level,
        "category": s.category,
        "benefit_type": s.benefit_type,
        "eligibility": s.eligibility,
        "benefits": s.benefits,
        "overview": s.overview,
        "objectives": s.objectives,
        "state": s.state,
        "crop": s.crop,
        "application_deadline": s.application_deadline,
        "start_date": s.start_date,
        "documents_required": s.documents_required or [],
        "how_to_apply": s.how_to_apply,
        "application_process": s.application_process,
        "website": s.website,
        "source": s.source,
        "source_url": s.source_url,
        "contact_information": s.contact_information,
        "faqs": s.faqs or [],
        "eligible_farmer_types": s.eligible_farmer_types or [],
        "land_category": s.land_category,
        "income_category": s.income_category,
        "status": s.status,
        "last_verified_at": str(s.last_verified_at) if s.last_verified_at else None,
        "created_at": str(s.created_at) if s.created_at else None,
        "is_saved": s.id in saved_ids,
    }


@router.get("/government-schemes/categories")
def list_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from sqlalchemy import func
    rows = db.query(GovernmentScheme.category, func.count(GovernmentScheme.id)).filter(
        GovernmentScheme.status == "active"
    ).group_by(GovernmentScheme.category).all()
    counts = {k: v for k, v in rows if k}
    central = (
        db.query(func.count(GovernmentScheme.id))
        .filter(GovernmentScheme.level == "central", GovernmentScheme.status == "active")
        .scalar()
        or 0
    )
    state = (
        db.query(func.count(GovernmentScheme.id))
        .filter(GovernmentScheme.level == "state", GovernmentScheme.status == "active")
        .scalar()
        or 0
    )

    cats = []
    # Prefer the curated display order for categories that actually exist.
    for name in SCHEME_CATEGORIES:
        if counts.get(name):
            cats.append({"name": name, "count": counts[name], "has_schemes": True})
    # Any real categories not in the curated list still get a chip.
    extra = sorted(((c, v) for c, v in counts.items() if c not in SCHEME_CATEGORIES), key=lambda kv: -kv[1])
    for name, cnt in extra:
        cats.append({"name": name, "count": cnt, "has_schemes": True})
    if central:
        cats.append({"name": "Central Schemes", "count": central, "has_schemes": True, "level": "central"})
    if state:
        cats.append({"name": "State Schemes", "count": state, "has_schemes": True, "level": "state"})

    return {"status": "success", "data": {"categories": cats}}


@router.get("/government-schemes/saved")
def saved_schemes(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    saved = _saved(db, current_user.id)
    saved_ids = {s.scheme_id for s in saved}
    q = db.query(GovernmentScheme).filter(GovernmentScheme.id.in_(saved_ids))
    total = q.count()
    items = q.order_by(GovernmentScheme.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [_scheme_dict(s, saved_ids) for s in items],
        },
    }


@router.post("/government-schemes/{scheme_id}/save", status_code=201)
def save_scheme(scheme_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    scheme = _find_scheme(db, scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")
    existing = (
        db.query(SavedScheme)
        .filter(SavedScheme.farmer_id == current_user.id, SavedScheme.scheme_id == scheme.id)
        .first()
    )
    if existing:
        return {"status": "success", "data": {"is_saved": True, "message": "Scheme already saved"}}
    db.add(SavedScheme(farmer_id=current_user.id, scheme_id=scheme.id))
    db.commit()
    return {"status": "success", "data": {"is_saved": True, "message": "Scheme saved"}}


@router.delete("/government-schemes/{scheme_id}/save")
def unsave_scheme(scheme_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    scheme = _find_scheme(db, scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")
    rec = (
        db.query(SavedScheme)
        .filter(SavedScheme.farmer_id == current_user.id, SavedScheme.scheme_id == scheme.id)
        .first()
    )
    if rec:
        db.delete(rec)
        db.commit()
    return {"status": "success", "data": {"is_saved": False, "message": "Scheme removed from saved"}}


@router.post("/government-schemes/check-eligibility")
def check_eligibility(payload: EligibilityRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    schemes = db.query(GovernmentScheme).filter(GovernmentScheme.status == "active").all()
    results = []
    for s in schemes:
        reasons = _match_reasons(s, payload)
        eligible = len(reasons) == 0
        results.append({
            "scheme_id": s.scheme_id,
            "id": s.id,
            "name": s.name,
            "category": s.category,
            "likely_eligible": eligible,
            "matching": list(reasons),
        })
    results.sort(key=lambda x: not x["likely_eligible"])
    return {
        "status": "success",
        "data": {
            "results": results,
            "disclaimer": "Based on the information provided, you may meet the listed criteria. Final eligibility is determined by the government department.",
            "total_results": len(results),
        },
    }


@router.get("/government-schemes/recommended")
def recommended_schemes(
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(GovernmentScheme).filter(GovernmentScheme.status == "active")
    items = _recommended(db, current_user, q)[:limit]
    saved_ids = {s.scheme_id for s in _saved(db, current_user.id)}
    return {
        "status": "success",
        "data": {"items": [_scheme_dict(s, saved_ids) for s in items], "total": len(items)},
    }


def _find_scheme(db: Session, scheme_id: str):
    scheme = db.query(GovernmentScheme).filter(GovernmentScheme.id == scheme_id).first()
    if not scheme:
        scheme = db.query(GovernmentScheme).filter(GovernmentScheme.scheme_id == scheme_id).first()
    return scheme


@router.get("/government-schemes/states")
def scheme_states(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Distinct states (with live scheme counts) for the filter panel."""
    return {"status": "success", "data": {"states": scheme_sync.list_states(db)}}


@router.get("/government-schemes/sync")
def scheme_sync_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Freshness metadata only — never hits the network."""
    return {"status": "success", "data": scheme_sync.scheme_freshness(db)}


@router.post("/government-schemes/sync")
def run_scheme_sync(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Trigger a verification pass against the configured official sources.

    Throttled server-side; callers get an explicit, honest result and nothing
    is fabricated when a source is unreachable/not configured.
    """
    report = scheme_sync.sync_from_sources(db, trigger="manual", force=True)
    report["freshness"] = scheme_sync.scheme_freshness(db)
    return {"status": "success", "data": report}


@router.get("/government-schemes/{scheme_id}")
def get_scheme(scheme_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    scheme = _find_scheme(db, scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")
    saved_ids = {s.scheme_id for s in _saved(db, current_user.id)}
    return {"status": "success", "data": _scheme_dict(scheme, saved_ids)}


# ---------------------------------------------------------------------------
# Eligibility matching + recommendations helpers
# ---------------------------------------------------------------------------
def _match_reasons(s: GovernmentScheme, p: EligibilityRequest) -> List[str]:
    """Return the list of *unmet* criteria. An empty list means all declared
    criteria match and the user is considered 'likely eligible'."""
    reasons = []
    low = s.eligibility or ""

    if s.eligible_farmer_types:
        ftype = (p.farmer_type or "").lower()
        if ftype and ftype not in ("", "any", "all"):
            allowed = [x.lower() for x in s.eligible_farmer_types]
            joined = " ".join(s.eligible_farmer_types).lower()
            if ftype not in allowed and ftype not in joined:
                reasons.append("Farmer type")
        elif s.land_category and p.land_size_hectares is not None:
            try:
                if s.land_category and s.land_category not in ("All", "all"):
                    reasons.append("Land holding size")
            except Exception:
                pass

    if p.age is not None and s.name and ("Maan Dhan" in s.name.lower() or "pension" in s.name.lower()):
        if not (18 <= p.age <= 40):
            reasons.append("Age (18-40 for pension schemes)")

    return reasons


def _recommended(db: Session, user: User, base_query) -> list:
    """Return schemes ordered by relevance to the authenticated farmer."""
    profile = getattr(user, "farmer_profile", None)
    state = None
    crops = []
    land = None
    farmer_type = None
    if profile:
        if profile.farm_location:
            # farm_location may contain a state/district label
            state = profile.farm_location
        if profile.preferred_crops:
            crops = [c.strip().lower() for c in profile.preferred_crops.split(",") if c.strip()]
        if profile.farming_type:
            farmer_type = profile.farming_type
    addr = None
    try:
        from app.models.user import UserAddress
        addr = db.query(UserAddress).filter(UserAddress.user_id == user.id, UserAddress.is_primary == True).first()  # noqa: E712
    except Exception:
        addr = None
    if addr and addr.state:
        state = state or addr.state

    schemes = base_query.all()

    def score(s: GovernmentScheme) -> int:
        sc = 0
        text = (s.name + " " + (s.description or "") + " " + (s.eligibility or "")).lower()
        if s.related_crops:
            for c in crops:
                if any(c in (rc or "").lower() for rc in s.related_crops):
                    sc += 3
                    break
        if state and s.state and state.lower() in s.state.lower():
            sc += 2
        if farmer_type:
            ft = farmer_type.lower()
            if s.eligible_farmer_types and ft in [x.lower() for x in s.eligible_farmer_types]:
                sc += 2
        if s.level == "central":
            sc += 1
        return sc

    scored = sorted(schemes, key=lambda s: score(s), reverse=True)
    nonzero = [s for s in scored if score(s) > 0] or scored
    return nonzero


@router.post("/government-schemes/{scheme_id}/apply", status_code=201)
def apply_scheme(
    scheme_id: str,
    payload: SchemeApplyRequest = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scheme = _find_scheme(db, scheme_id)
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

    create_scheme_notification(db, current_user.id, scheme.name, "submitted")

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
    items = q.order_by(SchemeApplication.application_date.desc()).offset((page - 1) * limit).limit(limit).all()

    result = []
    for a in items:
        scheme = db.query(GovernmentScheme).filter(GovernmentScheme.id == a.scheme_id).first()
        result.append({
            "id": a.id,
            "application_id": a.application_id,
            "scheme_id": a.scheme_id,
            "scheme_name": scheme.name if scheme else None,
            "scheme_category": scheme.category if scheme else None,
            "deadline": scheme.application_deadline if scheme else None,
            "status": a.status,
            "notes": a.notes,
            "applied_date": str(a.application_date) if a.application_date else None,
            "updated_at": str(a.updated_at) if a.updated_at else None,
        })

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": result,
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
    if policy.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only create a claim for your own policy")

    reason = payload.reason or payload.description or "General claim"
    claim_amount = payload.claim_amount if payload.claim_amount is not None else payload.amount

    # Validate and cap the claim amount against the policy coverage
    if claim_amount is not None:
        try:
            claim_amount = round(float(claim_amount), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid claim amount")
        if claim_amount <= 0:
            raise HTTPException(status_code=400, detail="Claim amount must be greater than zero")
        if policy.coverage_amount and claim_amount > float(policy.coverage_amount):
            raise HTTPException(
                status_code=400,
                detail=f"Claim amount exceeds policy coverage of {policy.coverage_amount}",
            )

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
