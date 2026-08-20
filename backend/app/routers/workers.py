from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.worker import (
    Worker, WorkerAvailability, WorkerBooking, Equipment, EquipmentBooking
)

router = APIRouter(prefix="/api/v1", tags=["Workers & Equipment"])


class WorkerBookingCreate(BaseModel):
    worker_id: str
    booking_date: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    work_type: Optional[str] = None
    duration_days: int = Field(default=1, ge=1)
    hours_per_day: Optional[float] = None
    farm_id: Optional[str] = None
    notes: Optional[str] = None


class WorkerBookingUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class EquipmentBookingCreate(BaseModel):
    equipment_id: str
    booking_date: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_days: int = Field(default=1, ge=1)


@router.get("/workers")
def list_workers(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    skill: Optional[str] = None,
    location: Optional[str] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
    is_available: Optional[bool] = None,
    min_rating: Optional[float] = None,
    min_rate: Optional[float] = None,
    max_rate: Optional[float] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("rating", regex="^(rating|daily_rate|experience_years|created_at)$"),
    sort_order: Optional[str] = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Worker)
    if is_available is not None:
        q = q.filter(Worker.is_available == is_available)
    if location:
        q = q.filter(Worker.village.ilike(f"%{location}%"))
    if district:
        q = q.filter(Worker.district.ilike(f"%{district}%"))
    if state:
        q = q.filter(Worker.state.ilike(f"%{state}%"))
    if min_rating is not None:
        q = q.filter(Worker.rating >= min_rating)
    if min_rate is not None:
        q = q.filter(Worker.daily_rate >= min_rate)
    if max_rate is not None:
        q = q.filter(Worker.daily_rate <= max_rate)
    if search:
        q = q.filter(
            Worker.full_name.ilike(f"%{search}%")
            | Worker.bio.ilike(f"%{search}%")
        )

    sort_col = getattr(Worker, sort_by, Worker.rating)
    if sort_order == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [
                {
                    "id": w.id,
                    "worker_id": w.worker_id,
                    "full_name": w.full_name,
                    "village": w.village,
                    "district": w.district,
                    "state": w.state,
                    "skills": w.skills,
                    "experience_years": w.experience_years,
                    "hourly_rate": w.hourly_rate,
                    "daily_rate": w.daily_rate,
                    "rating": w.rating,
                    "total_reviews": w.total_reviews,
                    "is_verified": w.is_verified,
                    "is_available": w.is_available,
                    "bio": w.bio,
                    "profile_image": w.profile_image,
                }
                for w in items
            ],
        },
    }


@router.get("/workers/{worker_id}")
def get_worker(worker_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    avail = db.query(WorkerAvailability).filter(WorkerAvailability.worker_id == worker.id).all()

    return {
        "status": "success",
        "data": {
            "id": worker.id,
            "worker_id": worker.worker_id,
            "full_name": worker.full_name,
            "phone_number": worker.phone_number,
            "village": worker.village,
            "district": worker.district,
            "state": worker.state,
            "skills": worker.skills,
            "experience_years": worker.experience_years,
            "hourly_rate": worker.hourly_rate,
            "daily_rate": worker.daily_rate,
            "rating": worker.rating,
            "total_reviews": worker.total_reviews,
            "is_verified": worker.is_verified,
            "is_available": worker.is_available,
            "bio": worker.bio,
            "profile_image": worker.profile_image,
            "availability": [
                {
                    "day_of_week": a.day_of_week,
                    "start_time": a.start_time,
                    "end_time": a.end_time,
                    "is_available": a.is_available,
                }
                for a in avail
            ],
        },
    }


@router.post("/worker-bookings", status_code=201)
def create_worker_booking(
    payload: WorkerBookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    worker = db.query(Worker).filter(Worker.id == payload.worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    if not worker.is_available:
        raise HTTPException(status_code=400, detail="Worker is not available")

    existing = (
        db.query(WorkerBooking)
        .filter(
            WorkerBooking.worker_id == worker.id,
            WorkerBooking.booking_date == payload.booking_date,
            WorkerBooking.status.in_(["pending", "confirmed"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Worker is already booked for this date")

    total_cost = 0.0
    if worker.daily_rate and payload.duration_days:
        total_cost = worker.daily_rate * payload.duration_days
    elif worker.hourly_rate and payload.hours_per_day and payload.duration_days:
        total_cost = worker.hourly_rate * payload.hours_per_day * payload.duration_days

    bkg_id = generate_id("FA-BKG", db, WorkerBooking)
    booking = WorkerBooking(
        booking_id=bkg_id,
        farmer_id=current_user.id,
        worker_id=worker.id,
        farm_id=payload.farm_id,
        work_type=payload.work_type,
        booking_date=payload.booking_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        duration_days=payload.duration_days,
        hours_per_day=payload.hours_per_day,
        total_cost=total_cost,
        notes=payload.notes,
        status="pending",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    return {
        "status": "success",
        "data": {
            "id": booking.id,
            "booking_id": booking.booking_id,
            "worker_name": worker.full_name,
            "booking_date": booking.booking_date,
            "total_cost": booking.total_cost,
            "status": booking.status,
            "message": "Booking created successfully",
        },
    }


@router.get("/worker-bookings")
def list_worker_bookings(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(WorkerBooking).filter(WorkerBooking.farmer_id == current_user.id)
    if status:
        q = q.filter(WorkerBooking.status == status)

    total = q.count()
    items = q.order_by(WorkerBooking.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "id": b.id,
                    "booking_id": b.booking_id,
                    "worker_id": b.worker_id,
                    "work_type": b.work_type,
                    "booking_date": b.booking_date,
                    "start_time": b.start_time,
                    "end_time": b.end_time,
                    "duration_days": b.duration_days,
                    "total_cost": b.total_cost,
                    "status": b.status,
                    "created_at": str(b.created_at) if b.created_at else None,
                }
                for b in items
            ],
        },
    }


@router.put("/worker-bookings/{booking_id}")
def update_worker_booking(
    booking_id: str,
    payload: WorkerBookingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = db.query(WorkerBooking).filter(
        WorkerBooking.booking_id == booking_id,
        WorkerBooking.farmer_id == current_user.id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if payload.status:
        valid = ["pending", "confirmed", "in_progress", "completed", "cancelled"]
        if payload.status not in valid:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid)}")
        booking.status = payload.status
    if payload.notes is not None:
        booking.notes = payload.notes
    booking.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)

    return {
        "status": "success",
        "data": {
            "id": booking.id,
            "booking_id": booking.booking_id,
            "status": booking.status,
            "message": "Booking updated successfully",
        },
    }


@router.get("/equipment")
def list_equipment(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    is_available: Optional[bool] = None,
    location: Optional[str] = None,
    search: Optional[str] = None,
    min_rate: Optional[float] = None,
    max_rate: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Equipment)
    if is_available is not None:
        q = q.filter(Equipment.is_available == is_available)
    if type:
        q = q.filter(Equipment.type.ilike(f"%{type}%"))
    if location:
        q = q.filter(Equipment.location.ilike(f"%{location}%"))
    if search:
        q = q.filter(
            Equipment.name.ilike(f"%{search}%")
            | Equipment.description.ilike(f"%{search}%")
        )
    if min_rate is not None:
        q = q.filter(Equipment.daily_rate >= min_rate)
    if max_rate is not None:
        q = q.filter(Equipment.daily_rate <= max_rate)

    total = q.count()
    items = q.order_by(Equipment.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [
                {
                    "id": e.id,
                    "equipment_id": e.equipment_id,
                    "name": e.name,
                    "type": e.type,
                    "brand": e.brand,
                    "model": e.model,
                    "description": e.description,
                    "daily_rate": e.daily_rate,
                    "hourly_rate": e.hourly_rate,
                    "is_available": e.is_available,
                    "location": e.location,
                    "image_url": e.image_url,
                }
                for e in items
            ],
        },
    }


@router.post("/equipment-bookings", status_code=201)
def book_equipment(
    payload: EquipmentBookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equipment = db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    if not equipment.is_available:
        raise HTTPException(status_code=400, detail="Equipment is not available")

    total_cost = (equipment.daily_rate or 0) * payload.duration_days
    bkg_id = generate_id("FA-EQB", db, EquipmentBooking)
    booking = EquipmentBooking(
        booking_id=bkg_id,
        equipment_id=equipment.id,
        farmer_id=current_user.id,
        booking_date=payload.booking_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        duration_days=payload.duration_days,
        total_cost=total_cost,
        status="pending",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    return {
        "status": "success",
        "data": {
            "id": booking.id,
            "booking_id": booking.booking_id,
            "equipment_name": equipment.name,
            "booking_date": booking.booking_date,
            "total_cost": booking.total_cost,
            "status": booking.status,
            "message": "Equipment booked successfully",
        },
    }
