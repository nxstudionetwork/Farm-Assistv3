import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.farm import Farm
from app.models.service import ServiceRequest, AgriculturalService
from app.models.notification import Notification
from app.database.seed_services import seed_agricultural_services

router = APIRouter(prefix="/api/v1", tags=["Services"])


class ServiceRequestCreate(BaseModel):
    service_id: Optional[str] = None
    service_name: str
    service_category: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    urgency: Optional[str] = "normal"
    is_custom: Optional[bool] = False
    farm_id: Optional[str] = None

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v):
        if v is not None and v.strip():
            digits = re.sub(r"\D", "", v)
            if len(digits) == 12 and digits.startswith("91"):
                digits = digits[2:]
            if len(digits) != 10:
                raise ValueError("Contact phone number must be exactly 10 digits")
            return digits
        return v

    @field_validator("preferred_date")
    @classmethod
    def validate_date(cls, v):
        if v is not None and v.strip():
            try:
                d = datetime.fromisoformat(v.strip().split("T")[0]).date()
                if d < datetime.utcnow().date():
                    raise ValueError("Preferred date cannot be in the past")
            except ValueError as e:
                if "past" in str(e):
                    raise e
                raise ValueError("Invalid date format. Use YYYY-MM-DD")
        return v


class ServiceRequestStatusUpdate(BaseModel):
    status: str
    assigned_expert: Optional[str] = None
    resolution_notes: Optional[str] = None


class ServiceRatingSubmit(BaseModel):
    rating: int
    rating_feedback: Optional[str] = None

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v):
        if v < 1 or v > 5:
            raise ValueError("Rating must be between 1 and 5 stars")
        return v


def estimate_response_time(category: Optional[str], is_custom: bool) -> str:
    if is_custom:
        return "48 hours"
    mapping = {
        "crop-cultivation": "< 2 hours",
        "seeds-planting": "< 2 hours",
        "soil-health": "< 1 hour",
        "fertilizers-nutrients": "< 2 hours",
        "pest-management": "< 1 hour",
        "crop-disease": "< 1 hour",
        "irrigation-water": "24 hours",
        "farm-machinery": "< 24 hours",
        "farm-labour": "< 6 hours",
        "harvesting": "< 24 hours",
        "post-harvest": "24 hours",
        "storage-warehousing": "24 hours",
        "transport-logistics": "< 6 hours",
        "livestock": "< 6 hours",
        "veterinary": "< 1 hour",
        "dairy-poultry": "< 6 hours",
        "organic-farming": "2-3 days",
        "sustainable-agri": "2-3 days",
        "government-schemes": "2-3 days",
        "agri-finance": "< 24 hours",
        "crop-insurance": "2-3 days",
        "expert-consultancy": "< 2 hours",
        "market-selling": "< 3 hours",
        "agri-technology": "< 24 hours",
        "other-services": "< 24 hours",
        "crop-services": "< 30 min",
        "soil-fertilizer": "< 2 hours",
        "pest-disease": "< 1 hour",
        "irrigation": "24 hours",
        "equipment-labour": "< 2 hours",
        "consultation": "< 30 min",
        "farm-work": "24 hours",
        "documentation": "2-3 days",
        "financial": "< 24 hours",
    }
    return mapping.get((category or "").lower(), "24 hours")


def build_timeline(status_str: str, created_at: datetime) -> list:
    submitted = created_at.strftime("%b %d, %Y %I:%M %p") if created_at else ""
    entries = [{"title": "Request Submitted", "time": submitted, "done": True}]
    if status_str in ("pending", "received", "accepted", "in-progress", "completed", "cancelled"):
        entries.append({
            "title": "Received & Under Review",
            "time": submitted if status_str != "pending" else "Pending",
            "done": status_str != "pending",
        })
    if status_str in ("accepted", "in-progress", "completed"):
        entries.append({
            "title": "Service Accepted & Scheduled",
            "time": submitted if status_str in ("in-progress", "completed") else "Pending",
            "done": status_str in ("in-progress", "completed"),
        })
    if status_str in ("in-progress", "completed"):
        entries.append({
            "title": "Service In Progress",
            "time": "Pending" if status_str == "in-progress" else submitted,
            "done": status_str == "completed",
        })
    if status_str == "completed":
        entries.append({"title": "Completed", "time": submitted, "done": True})
    if status_str == "cancelled":
        entries.append({"title": "Cancelled / Closed", "time": "Cancelled", "done": False})
    return entries


def serialize_service(s: AgriculturalService) -> dict:
    return {
        "id": s.id,
        "service_id": s.service_id,
        "name": s.name,
        "category": s.category,
        "description": s.description,
        "full_description": s.full_description or s.description,
        "deliverables": s.deliverables or "• On-field specialist assessment & diagnostic audit\n• Digital advisory report with step-by-step guidance\n• Customized input & application schedule\n• Direct specialist follow-up support",
        "eligibility": s.eligibility or "All registered farmers, land owners, and agricultural leaseholders with verified farm records.",
        "service_duration": s.service_duration or "1 to 2 Hours (On-Site Execution)",
        "required_documents": s.required_documents or "Farmer ID, Land Record Copy (Khatian/7-12), Farm Plot Photo",
        "icon": s.icon,
        "color": s.color,
        "availability": s.availability,
        "response_time": s.response_time,
        "price_info": s.price_info,
        "provider_name": s.provider_name,
        "location_coverage": s.location_coverage,
        "rating": s.rating,
        "is_active": s.is_active,
    }


def serialize_request(req: ServiceRequest) -> dict:
    return {
        "id": req.id,
        "service_request_id": req.service_request_id,
        "service_id": req.service_id,
        "service_name": req.service_name,
        "service_category": req.service_category,
        "contact_name": req.contact_name,
        "contact_phone": req.contact_phone,
        "description": req.description,
        "location": req.location,
        "preferred_date": str(req.preferred_date).split(" ")[0] if req.preferred_date else None,
        "preferred_time": req.preferred_time,
        "farm_id": req.farm_id,
        "budget_min": req.budget_min,
        "budget_max": req.budget_max,
        "urgency": req.urgency,
        "is_custom": bool(req.is_custom),
        "status": req.status,
        "assigned_expert": req.assigned_expert,
        "resolution_notes": req.resolution_notes,
        "estimated_response_time": req.estimated_response_time,
        "rating": req.rating,
        "rating_feedback": req.rating_feedback,
        "created_at": str(req.created_at) if req.created_at else None,
        "timeline": build_timeline(req.status, req.created_at),
    }


# === CATALOG ENDPOINTS ===

@router.get("/services")
def list_agricultural_services(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=200),
    category: Optional[str] = None,
    search: Optional[str] = None,
    availability: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Retrieve catalog of agricultural services with category and search filtering."""
    # Ensure seed services exist
    seed_agricultural_services(db)

    q = db.query(AgriculturalService).filter(AgriculturalService.is_active == True)

    if category and category.lower() != "all":
        q = q.filter(AgriculturalService.category == category.lower())

    if availability and availability.lower() != "all":
        q = q.filter(AgriculturalService.availability == availability.lower())

    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(
            AgriculturalService.name.ilike(term)
            | AgriculturalService.category.ilike(term)
            | AgriculturalService.description.ilike(term)
            | AgriculturalService.provider_name.ilike(term)
        )

    total = q.count()
    items = q.order_by(AgriculturalService.created_at.asc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if limit > 0 else 1,
            "items": [serialize_service(s) for s in items],
        },
    }


@router.get("/services/categories")
def get_service_categories(db: Session = Depends(get_db)):
    """Retrieve service category counts."""
    seed_agricultural_services(db)
    counts = (
        db.query(AgriculturalService.category, func.count(AgriculturalService.id))
        .filter(AgriculturalService.is_active == True)
        .group_by(AgriculturalService.category)
        .all()
    )
    total_all = db.query(AgriculturalService).filter(AgriculturalService.is_active == True).count()
    cat_map = {"all": total_all}
    for cat, count in counts:
        cat_map[cat] = count
    return {"status": "success", "data": cat_map}


@router.get("/services/completed")
def list_completed_services(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve services completed for the logged-in farmer."""
    completed = (
        db.query(ServiceRequest)
        .filter(
            ServiceRequest.user_id == current_user.id,
            ServiceRequest.status == "completed",
        )
        .order_by(ServiceRequest.updated_at.desc())
        .all()
    )
    return {"status": "success", "data": [serialize_request(r) for r in completed]}


@router.get("/services/{service_id}")
def get_service_detail(service_id: str, db: Session = Depends(get_db)):
    """Retrieve detailed service by ID or service_id."""
    svc = (
        db.query(AgriculturalService)
        .filter(
            or_(
                AgriculturalService.id == service_id,
                AgriculturalService.service_id == service_id,
            )
        )
        .first()
    )
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"status": "success", "data": serialize_service(svc)}


# === SERVICE REQUEST ENDPOINTS ===

@router.get("/service-requests")
def list_service_requests(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve logged-in farmer's service requests with strict user data isolation."""
    q = db.query(ServiceRequest).filter(ServiceRequest.user_id == current_user.id)

    if status and status.lower() != "all":
        st = status.lower()
        if st == "active":
            q = q.filter(ServiceRequest.status.in_(["pending", "received", "accepted", "in-progress", "submitted"]))
        elif st == "completed":
            q = q.filter(ServiceRequest.status == "completed")
        else:
            q = q.filter(ServiceRequest.status == st)

    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(
            ServiceRequest.service_name.ilike(term)
            | ServiceRequest.service_request_id.ilike(term)
            | ServiceRequest.description.ilike(term)
        )

    total = q.count()
    items = (
        q.order_by(ServiceRequest.created_at.desc())
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
            "total_pages": (total + limit - 1) // limit if limit > 0 else 1,
            "items": [serialize_request(r) for r in items],
        },
    }


@router.post("/service-requests", status_code=201)
def create_service_request(
    payload: ServiceRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new service request and generate an in-app notification in DB."""
    # Verify farm ownership if farm_id is provided
    if payload.farm_id:
        farm = db.query(Farm).filter(Farm.id == payload.farm_id, Farm.user_id == current_user.id).first()
        if not farm:
            # Check by farm_id string
            farm = db.query(Farm).filter(Farm.farm_id == payload.farm_id, Farm.user_id == current_user.id).first()
        if not farm:
            payload.farm_id = None  # reset to null if invalid farm

    req_id = generate_id("FA-SRQ", db, ServiceRequest)
    pref_date = None
    if payload.preferred_date:
        try:
            pref_date = datetime.fromisoformat(payload.preferred_date.strip().split("T")[0])
        except ValueError:
            pref_date = None

    req = ServiceRequest(
        service_request_id=req_id,
        user_id=current_user.id,
        service_id=payload.service_id,
        farm_id=payload.farm_id,
        service_name=payload.service_name.strip(),
        service_category=payload.service_category,
        contact_name=(payload.contact_name or current_user.full_name or "").strip(),
        contact_phone=(payload.contact_phone or current_user.phone_number or "").strip(),
        description=(payload.description or "").strip() or None,
        location=(payload.location or "").strip() or None,
        preferred_date=pref_date,
        preferred_time=payload.preferred_time,
        budget_min=payload.budget_min,
        budget_max=payload.budget_max,
        urgency=payload.urgency or "normal",
        is_custom=bool(payload.is_custom),
        status="pending",
        estimated_response_time=estimate_response_time(
            payload.service_category, bool(payload.is_custom)
        ),
    )
    db.add(req)
    db.flush()

    # Automatically generate in-app notification in database
    notif_id = generate_id("FA-NOT", db, Notification)
    notif = Notification(
        notification_id=notif_id,
        user_id=current_user.id,
        title="Service Request Received",
        message=f"Your request for '{req.service_name}' has been received. Request ID: {req.service_request_id}",
        notification_type="service_request",
        reference_id=req.service_request_id,
        reference_type="service_request",
        icon="fa-concierge-bell",
        action_url=f"services.html?req={req.service_request_id}",
        is_read=False,
    )
    db.add(notif)
    db.commit()
    db.refresh(req)

    return {
        "status": "success",
        "message": f"Service request {req.service_request_id} created successfully",
        "data": serialize_request(req),
    }


@router.post("/custom-service-requests", status_code=201)
def create_custom_service_request(
    payload: ServiceRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    custom_payload = payload.model_copy(update={"is_custom": True})
    return create_service_request(custom_payload, db, current_user)


@router.get("/service-requests/{request_id}")
def get_service_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = (
        db.query(ServiceRequest)
        .filter(
            or_(
                ServiceRequest.id == request_id,
                ServiceRequest.service_request_id == request_id,
            ),
            ServiceRequest.user_id == current_user.id,
        )
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")
    return {"status": "success", "data": serialize_request(req)}


@router.put("/service-requests/{request_id}/status")
def update_service_request_status(
    request_id: str,
    payload: ServiceRequestStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = (
        db.query(ServiceRequest)
        .filter(
            or_(
                ServiceRequest.id == request_id,
                ServiceRequest.service_request_id == request_id,
            ),
            ServiceRequest.user_id == current_user.id,
        )
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    allowed = {"pending", "received", "accepted", "in-progress", "completed", "cancelled"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status option")

    req.status = payload.status
    if payload.assigned_expert is not None:
        req.assigned_expert = payload.assigned_expert
    if payload.resolution_notes is not None:
        req.resolution_notes = payload.resolution_notes

    # Automatically generate in-app notification for status update
    status_label = payload.status.replace("-", " ").replace("_", " ").title()
    notif_id = generate_id("FA-NOT", db, Notification)
    notif = Notification(
        notification_id=notif_id,
        user_id=current_user.id,
        title=f"Service Request {status_label}",
        message=f"Your request for '{req.service_name}' status is now '{status_label}'. Request ID: {req.service_request_id}",
        notification_type="service_request",
        reference_id=req.service_request_id,
        reference_type="service_request",
        icon="fa-concierge-bell",
        action_url=f"services.html?req={req.service_request_id}",
        is_read=False,
    )
    db.add(notif)

    db.commit()
    db.refresh(req)
    return {"status": "success", "message": "Service request status updated", "data": serialize_request(req)}


@router.post("/service-requests/{request_id}/rate")
def rate_completed_service(
    request_id: str,
    payload: ServiceRatingSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = (
        db.query(ServiceRequest)
        .filter(
            or_(
                ServiceRequest.id == request_id,
                ServiceRequest.service_request_id == request_id,
            ),
            ServiceRequest.user_id == current_user.id,
        )
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")

    if req.status != "completed":
        raise HTTPException(status_code=400, detail="Only completed service requests can be rated")

    req.rating = payload.rating
    if payload.rating_feedback:
        req.rating_feedback = payload.rating_feedback.strip()

    db.commit()
    db.refresh(req)
    return {"status": "success", "message": "Rating submitted successfully", "data": serialize_request(req)}
