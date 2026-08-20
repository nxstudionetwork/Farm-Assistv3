from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.service import ServiceRequest

router = APIRouter(prefix="/api/v1", tags=["Services"])


class ServiceRequestCreate(BaseModel):
    service_name: str
    service_category: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    description: Optional[str] = None
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    urgency: Optional[str] = "normal"
    is_custom: Optional[bool] = False
    farm_id: Optional[str] = None


class ServiceRequestStatusUpdate(BaseModel):
    status: str
    assigned_expert: Optional[str] = None
    resolution_notes: Optional[str] = None


def estimate_response_time(category: Optional[str], is_custom: bool) -> str:
    if is_custom:
        return "48 hours"
    mapping = {
        "consultation": "< 30 min",
        "farm-work": "24 hours",
        "documentation": "2-3 days",
        "financial": "< 24 hours",
    }
    return mapping.get((category or "").lower(), "24 hours")


def build_timeline(status: str, created_at: datetime) -> list:
    submitted = created_at.strftime("%b %d, %Y %I:%M %p") if created_at else ""
    entries = [{"title": "Request Submitted", "time": submitted, "done": True}]
    if status in ("pending", "in-progress", "completed", "cancelled"):
        entries.append({
            "title": "Under Review",
            "time": submitted if status != "pending" else "Pending",
            "done": status != "pending",
        })
    if status in ("in-progress", "completed"):
        entries.append({
            "title": "Service In Progress",
            "time": "Pending" if status == "in-progress" else submitted,
            "done": status == "completed",
        })
    if status == "completed":
        entries.append({"title": "Completed", "time": submitted, "done": True})
    if status == "cancelled":
        entries.append({"title": "Closed", "time": "Pending", "done": False})
    return entries


def serialize(req: ServiceRequest) -> dict:
    return {
        "id": req.id,
        "service_request_id": req.service_request_id,
        "service_name": req.service_name,
        "service_category": req.service_category,
        "contact_name": req.contact_name,
        "contact_phone": req.contact_phone,
        "description": req.description,
        "preferred_date": str(req.preferred_date) if req.preferred_date else None,
        "preferred_time": req.preferred_time,
        "budget_min": req.budget_min,
        "budget_max": req.budget_max,
        "urgency": req.urgency,
        "is_custom": bool(req.is_custom),
        "status": req.status,
        "assigned_expert": req.assigned_expert,
        "resolution_notes": req.resolution_notes,
        "estimated_response_time": req.estimated_response_time,
        "created_at": str(req.created_at) if req.created_at else None,
        "timeline": build_timeline(req.status, req.created_at),
    }


@router.get("/service-requests")
def list_service_requests(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(ServiceRequest).filter(ServiceRequest.user_id == current_user.id)
    if status:
        q = q.filter(ServiceRequest.status == status)
    if search:
        term = f"%{search}%"
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
            "total_pages": (total + limit - 1) // limit,
            "items": [serialize(r) for r in items],
        },
    }


@router.post("/service-requests", status_code=201)
def create_service_request(
    payload: ServiceRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req_id = generate_id("FA-SRQ", db, ServiceRequest)
    pref_date = None
    if payload.preferred_date:
        try:
            pref_date = datetime.fromisoformat(payload.preferred_date)
        except ValueError:
            pref_date = None

    req = ServiceRequest(
        service_request_id=req_id,
        user_id=current_user.id,
        farm_id=payload.farm_id,
        service_name=payload.service_name,
        service_category=payload.service_category,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        description=payload.description,
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
    db.commit()
    db.refresh(req)
    return {
        "status": "success",
        "message": "Service request created successfully",
        "data": serialize(req),
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
            ServiceRequest.service_request_id == request_id,
            ServiceRequest.user_id == current_user.id,
        )
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")
    return {"status": "success", "data": serialize(req)}


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
            ServiceRequest.service_request_id == request_id,
            ServiceRequest.user_id == current_user.id,
        )
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")
    allowed = {"pending", "in-progress", "completed", "cancelled"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status")
    req.status = payload.status
    if payload.assigned_expert is not None:
        req.assigned_expert = payload.assigned_expert
    if payload.resolution_notes is not None:
        req.resolution_notes = payload.resolution_notes
    db.commit()
    db.refresh(req)
    return {"status": "success", "message": "Status updated", "data": serialize(req)}
