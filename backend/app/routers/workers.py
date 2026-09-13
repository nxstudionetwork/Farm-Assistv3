from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id, verify_password
from app.utils.notification_helper import create_notification
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.models.worker import (
    Worker, WorkerAvailability, WorkerBooking, WorkerPayment, WorkerReview,
    Equipment, EquipmentBooking
)
from app.models.wallet import Wallet, WalletTransaction

router = APIRouter(prefix="/api/v1", tags=["Workers & Equipment"])


class WorkerBookingCreate(BaseModel):
    worker_id: str
    farm_id: str
    plot_id: Optional[str] = None
    work_type: Optional[str] = None
    booking_date: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_days: int = Field(default=1, ge=1)
    hours_per_day: Optional[float] = None
    notes: Optional[str] = None
    wallet_pin: Optional[str] = None


class WorkerBookingUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class WorkerReviewCreate(BaseModel):
    rating: float = Field(ge=1, le=5)
    comment: Optional[str] = None
    booking_id: Optional[str] = None


class EquipmentBookingCreate(BaseModel):
    equipment_id: str
    booking_date: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_days: int = Field(default=1, ge=1)


def _get_wallet(db, user_id):
    return db.query(Wallet).filter(Wallet.user_id == user_id).first()


def _parse_time(t):
    if not t:
        return None
    try:
        parts = t.strip().split(":")
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        return h + m / 60.0
    except Exception:
        return None


def _times_overlap(s1, e1, s2, e2):
    if s1 is None or e1 is None or s2 is None or e2 is None:
        return True
    return s1 < e2 and s2 < e1


def _serialize_worker(w):
    return {
        "id": w.id,
        "worker_id": w.worker_id,
        "full_name": w.full_name,
        "phone_number": w.phone_number,
        "village": w.village,
        "district": w.district,
        "state": w.state,
        "skills": w.skills or [],
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


def _serialize_booking(b, worker=None, farm=None, plot=None, payment=None):
    return {
        "id": b.id,
        "booking_id": b.booking_id,
        "worker_id": b.worker_id,
        "worker_name": worker.full_name if worker else None,
        "worker_rating": worker.rating if worker else None,
        "worker_verified": worker.is_verified if worker else None,
        "worker_image": worker.profile_image if worker else None,
        "worker_skills": worker.skills if worker else None,
        "farm_id": b.farm_id,
        "farm_name": farm.farm_name if farm else None,
        "plot_id": b.plot_id,
        "plot_name": plot.plot_name if plot else None,
        "work_type": b.work_type,
        "booking_date": b.booking_date,
        "start_time": b.start_time,
        "end_time": b.end_time,
        "duration_days": b.duration_days,
        "hours_per_day": b.hours_per_day,
        "total_cost": b.total_cost,
        "status": b.status,
        "payment_status": payment.status if payment else "unpaid",
        "payment_amount": payment.amount if payment else None,
        "notes": b.notes,
        "created_at": str(b.created_at) if b.created_at else None,
        "updated_at": str(b.updated_at) if b.updated_at else None,
    }


@router.get("/workers")
def list_workers(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    skill: Optional[str] = None,
    work_type: Optional[str] = None,
    location: Optional[str] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
    is_available: Optional[bool] = None,
    min_rating: Optional[float] = None,
    min_rate: Optional[float] = None,
    max_rate: Optional[float] = None,
    min_experience: Optional[float] = None,
    max_experience: Optional[float] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("rating", regex="^(rating|daily_rate|experience_years|created_at|is_available)$"),
    sort_order: Optional[str] = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Worker)

    if is_available is not None:
        q = q.filter(Worker.is_available == is_available)
    if location:
        q = q.filter(
            Worker.village.ilike(f"%{location}%")
            | Worker.district.ilike(f"%{location}%")
        )
    if district:
        q = q.filter(Worker.district.ilike(f"%{district}%"))
    if state:
        q = q.filter(Worker.state.ilike(f"%{state}%"))
    if min_rating is not None:
        q = q.filter(Worker.rating >= min_rating)
    if min_rate is not None:
        q = q.filter(or_(Worker.daily_rate >= min_rate, Worker.hourly_rate >= min_rate))
    if max_rate is not None:
        q = q.filter(or_(Worker.daily_rate <= max_rate, Worker.hourly_rate <= max_rate))
    if min_experience is not None:
        q = q.filter(Worker.experience_years >= min_experience)
    if max_experience is not None:
        q = q.filter(Worker.experience_years <= max_experience)
    if skill:
        q = q.filter(Worker.skills.ilike(f"%{skill}%"))
    if work_type:
        wt_map = {
            "harvesting": ["harvest", "thresh", "baler", "combine", "reaper"],
            "planting": ["plant", "plough", "tillage", "tractor", "rotavator", "seed drill"],
            "seeding": ["seed", "sow", "row plant"],
            "weeding": ["weed", "hoe", "mulch"],
            "irrigation": ["irrigat", "drip", "sprinkler", "canal", "water"],
            "spraying": ["spray", "pesticide", "fertiliz", "drone"],
            "general farm work": ["general", "fenc", "clear", "load", "labor", "cattle", "milk", "livestock", "animal", "fodder", "team", "quality", "coordination", "maintenance", "gps"],
        }
        keywords = wt_map.get(work_type.lower(), [work_type.lower()])
        conditions = [Worker.skills.ilike(f"%{kw}%") for kw in keywords]
        q = q.filter(or_(*conditions))

    if search:
        like = f"%{search}%"
        q = q.filter(
            Worker.full_name.ilike(like)
            | Worker.bio.ilike(like)
            | Worker.village.ilike(like)
            | Worker.district.ilike(like)
            | Worker.state.ilike(like)
            | Worker.skills.ilike(like)
        )

    sort_col = getattr(Worker, sort_by, Worker.rating)
    if sort_by == "is_available":
        q = q.order_by(Worker.is_available.desc())
    elif sort_order == "asc":
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
            "total_pages": max(1, (total + limit - 1) // limit),
            "items": [_serialize_worker(w) for w in items],
        },
    }


@router.get("/workers/filters")
def get_worker_filters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    all_skills = set()
    all_locations = set()
    all_work_types = set()
    workers = db.query(Worker).all()
    for w in workers:
        if w.skills:
            for s in w.skills:
                all_skills.add(s)
        loc = ", ".join(filter(None, [w.village, w.district, w.state]))
        if loc:
            all_locations.add(loc)

    work_type_keywords = {
        "Harvesting": ["harvest", "thresh", "baler", "combine"],
        "Planting": ["plant", "plough", "tillage", "tractor"],
        "Seeding": ["seed", "sow"],
        "Weeding": ["weed", "hoe", "mulch"],
        "Irrigation": ["irrigat", "drip", "sprinkler", "canal"],
        "Spraying": ["spray", "pesticide", "fertiliz"],
        "General Farm Work": ["general", "fenc", "cattle", "milk"],
    }
    for s in all_skills:
        sl = s.lower()
        for wt, kws in work_type_keywords.items():
            if any(k in sl for k in kws):
                all_work_types.add(wt)
                break

    return {
        "status": "success",
        "data": {
            "skills": sorted(all_skills),
            "work_types": sorted(all_work_types),
            "locations": sorted(all_locations),
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

    reviews_q = (
        db.query(WorkerReview, User.full_name)
        .join(User, WorkerReview.reviewer_id == User.id)
        .filter(WorkerReview.worker_id == worker.id)
        .order_by(WorkerReview.created_at.desc())
        .limit(20)
        .all()
    )
    reviews = [
        {
            "id": r.id,
            "rating": r.rating,
            "comment": r.comment,
            "reviewer_name": uname,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r, uname in reviews_q
    ]

    completed_q = (
        db.query(WorkerBooking, Farm.farm_name)
        .outerjoin(Farm, WorkerBooking.farm_id == Farm.id)
        .filter(
            WorkerBooking.worker_id == worker.id,
            WorkerBooking.status == "completed",
        )
        .order_by(WorkerBooking.booking_date.desc())
        .limit(10)
        .all()
    )
    history = [
        {
            "work_type": b.work_type,
            "farm_name": fname or "Farm",
            "booking_date": b.booking_date,
            "duration_days": b.duration_days,
        }
        for b, fname in completed_q
    ]

    return {
        "status": "success",
        "data": {
            **_serialize_worker(worker),
            "availability": [
                {
                    "day_of_week": a.day_of_week,
                    "start_time": a.start_time,
                    "end_time": a.end_time,
                    "is_available": a.is_available,
                }
                for a in avail
            ],
            "reviews": reviews,
            "history": history,
        },
    }


@router.post("/workers/{worker_id}/reviews", status_code=201)
def add_worker_review(
    worker_id: str,
    payload: WorkerReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    if payload.booking_id:
        booking = (
            db.query(WorkerBooking)
            .filter(
                WorkerBooking.booking_id == payload.booking_id,
                WorkerBooking.farmer_id == current_user.id,
                WorkerBooking.worker_id == worker.id,
                WorkerBooking.status == "completed",
            )
            .first()
        )
        if not booking:
            raise HTTPException(status_code=400, detail="No completed booking found for this worker")

    existing = (
        db.query(WorkerReview)
        .filter(
            WorkerReview.worker_id == worker.id,
            WorkerReview.reviewer_id == current_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="You have already reviewed this worker")

    review = WorkerReview(
        id=generate_id("FA-WRV", db, WorkerReview),
        worker_id=worker.id,
        reviewer_id=current_user.id,
        rating=payload.rating,
        comment=payload.comment,
        created_at=datetime.utcnow(),
    )
    db.add(review)
    db.flush()

    avg = db.query(func.avg(WorkerReview.rating)).filter(WorkerReview.worker_id == worker.id).scalar()
    cnt = db.query(func.count(WorkerReview.id)).filter(WorkerReview.worker_id == worker.id).scalar()
    worker.rating = round(float(avg or 0), 2)
    worker.total_reviews = int(cnt or 0)
    worker.updated_at = datetime.utcnow()
    db.commit()

    return {
        "status": "success",
        "data": {
            "id": review.id,
            "rating": review.rating,
            "message": "Review added successfully",
        },
    }


@router.get("/workers/{worker_id}/reviews")
def get_worker_reviews(
    worker_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    q = (
        db.query(WorkerReview, User.full_name)
        .join(User, WorkerReview.reviewer_id == User.id)
        .filter(WorkerReview.worker_id == worker.id)
        .order_by(WorkerReview.created_at.desc())
    )
    total = q.count()
    rows = q.offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "items": [
                {
                    "id": r.id,
                    "rating": r.rating,
                    "comment": r.comment,
                    "reviewer_name": uname,
                    "created_at": str(r.created_at) if r.created_at else None,
                }
                for r, uname in rows
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
        raise HTTPException(status_code=400, detail="This worker is currently unavailable")

    farm = db.query(Farm).filter(
        or_(Farm.id == payload.farm_id, Farm.farm_id == payload.farm_id),
        Farm.user_id == current_user.id,
        Farm.is_active == True,
    ).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found or does not belong to you")

    if payload.plot_id:
        plot = db.query(FarmPlot).filter(
            FarmPlot.id == payload.plot_id,
            FarmPlot.farm_id == farm.id,
            FarmPlot.is_active == True,
        ).first()
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found on this farm")

    try:
        bdate = datetime.strptime(payload.booking_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    if bdate < datetime.utcnow().date():
        raise HTTPException(status_code=400, detail="Cannot book for a past date")

    new_s = _parse_time(payload.start_time)
    new_e = _parse_time(payload.end_time)
    if payload.duration_days < 1:
        raise HTTPException(status_code=400, detail="Duration must be at least 1 day")
    if new_s is not None and new_e is not None and new_e <= new_s:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    existing_bookings = (
        db.query(WorkerBooking)
        .filter(
            WorkerBooking.worker_id == worker.id,
            WorkerBooking.status.in_(["pending", "confirmed", "in_progress"]),
        )
        .all()
    )
    for eb in existing_bookings:
        try:
            eb_date = datetime.strptime(eb.booking_date, "%Y-%m-%d").date()
        except Exception:
            continue
        for day_offset in range(payload.duration_days):
            check_date = bdate + timedelta(days=day_offset)
            for eb_day in range(eb.duration_days or 1):
                eb_check = eb_date + timedelta(days=eb_day)
                if check_date == eb_check:
                    if new_s is not None and new_e is not None and eb.start_time and eb.end_time:
                        eb_s = _parse_time(eb.start_time)
                        eb_e = _parse_time(eb.end_time)
                        if _times_overlap(new_s, new_e, eb_s, eb_e):
                            raise HTTPException(
                                status_code=400,
                                detail="This worker is already booked during the selected time. Please choose another date or time.",
                            )
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="This worker is already booked on the selected date.",
                        )

    total_cost = 0.0
    if worker.daily_rate and payload.duration_days:
        total_cost = worker.daily_rate * payload.duration_days
    elif worker.hourly_rate and payload.hours_per_day and payload.duration_days:
        total_cost = worker.hourly_rate * payload.hours_per_day * payload.duration_days

    total_cost = round(total_cost, 2)

    wallet = _get_wallet(db, current_user.id)
    paid = False
    if payload.wallet_pin:
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found. Please set up your wallet first.")
        if not wallet.is_active:
            raise HTTPException(status_code=403, detail="Wallet is inactive")
        if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
            raise HTTPException(status_code=403, detail="Complete wallet setup before making a payment")
        if not verify_password(payload.wallet_pin.strip(), wallet.wallet_pin_hash):
            raise HTTPException(status_code=401, detail="Invalid wallet PIN")
        balance = round(float(wallet.balance or 0), 2)
        if balance < total_cost:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient wallet balance. You have \u20b9{balance:,.2f}, booking costs \u20b9{total_cost:,.2f}",
            )

    try:
        status = "pending"
        if payload.wallet_pin and total_cost > 0:
            new_balance = round(balance - total_cost, 2)

        bkg_id = generate_id("FA-BKG", db, WorkerBooking)
        booking = WorkerBooking(
            booking_id=bkg_id,
            farmer_id=current_user.id,
            worker_id=worker.id,
            farm_id=farm.id,
            plot_id=payload.plot_id,
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
        db.flush()

        payment_record = None
        if payload.wallet_pin and total_cost > 0:
            payment_record = WorkerPayment(
                id=generate_id("FA-WPAY", db, WorkerPayment),
                booking_id=booking.id,
                amount=total_cost,
                payment_method="wallet",
                payment_date=datetime.utcnow(),
                status="pending",
            )
            db.add(payment_record)
            db.flush()

            txn = WalletTransaction(
                transaction_id=generate_id("FA-WTX", db, WalletTransaction),
                wallet_id=wallet.id,
                user_id=current_user.id,
                transaction_type="debit",
                amount=total_cost,
                balance_after=new_balance,
                description=f"Worker booking {bkg_id} — {worker.full_name}",
                reference_id=bkg_id,
                payment_method="worker_booking",
                status="completed",
            )
            db.add(txn)

            wallet.balance = new_balance
            payment_record.status = "completed"
            paid = True
            booking.status = "confirmed"

        create_notification(
            db=db,
            user_id=current_user.id,
            title="Worker Booking Created",
            message=f"Booking {bkg_id} with {worker.full_name} for {payload.work_type or 'farm work'} on {payload.booking_date} has been {'confirmed' if paid else 'created'}.",
            notification_type="task",
            reference_id=booking.id,
            reference_type="worker_booking",
            icon="fa-user-check",
            action_url="workers.html",
        )

        db.commit()
        db.refresh(booking)
        if payment_record:
            db.refresh(payment_record)

        return {
            "status": "success",
            "data": {
                "id": booking.id,
                "booking_id": booking.booking_id,
                "worker_name": worker.full_name,
                "farm_name": farm.farm_name,
                "work_type": booking.work_type,
                "booking_date": booking.booking_date,
                "total_cost": booking.total_cost,
                "status": booking.status,
                "payment_status": "completed" if paid else "unpaid",
                "message": f"Booking {'confirmed and payment processed' if paid else 'created successfully'}.",
            },
        }

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to create booking. Please try again.")


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

    results = []
    for b in items:
        worker = db.query(Worker).filter(Worker.id == b.worker_id).first()
        farm = db.query(Farm).filter(Farm.id == b.farm_id).first() if b.farm_id else None
        plot = db.query(FarmPlot).filter(FarmPlot.id == b.plot_id).first() if b.plot_id else None
        payment = db.query(WorkerPayment).filter(WorkerPayment.booking_id == b.id).first()
        results.append(_serialize_booking(b, worker=worker, farm=farm, plot=plot, payment=payment))

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit),
            "items": results,
        },
    }


@router.get("/worker-bookings/{booking_id}")
def get_worker_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = db.query(WorkerBooking).filter(
        WorkerBooking.booking_id == booking_id,
        WorkerBooking.farmer_id == current_user.id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    worker = db.query(Worker).filter(Worker.id == booking.worker_id).first()
    farm = db.query(Farm).filter(Farm.id == booking.farm_id).first() if booking.farm_id else None
    plot = db.query(FarmPlot).filter(FarmPlot.id == booking.plot_id).first() if booking.plot_id else None
    payment = db.query(WorkerPayment).filter(WorkerPayment.booking_id == booking.id).first()

    return {
        "status": "success",
        "data": _serialize_booking(booking, worker=worker, farm=farm, plot=plot, payment=payment),
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

        if payload.status == "cancelled" and booking.status in ["pending", "confirmed", "in_progress"]:
            payment = db.query(WorkerPayment).filter(
                WorkerPayment.booking_id == booking.id,
                WorkerPayment.status == "completed",
            ).first()
            refund_amount = 0.0
            if payment:
                wallet = _get_wallet(db, current_user.id)
                if wallet:
                    refund_amount = round(float(payment.amount or 0), 2)
                    current_balance = round(float(wallet.balance or 0), 2)
                    new_balance = round(current_balance + refund_amount, 2)
                    txn = WalletTransaction(
                        transaction_id=generate_id("FA-WTX", db, WalletTransaction),
                        wallet_id=wallet.id,
                        user_id=current_user.id,
                        transaction_type="credit",
                        amount=refund_amount,
                        balance_after=new_balance,
                        description=f"Refund for cancelled booking {booking_id}",
                        reference_id=booking_id,
                        payment_method="wallet",
                        status="completed",
                    )
                    db.add(txn)
                    wallet.balance = new_balance
                    payment.status = "refunded"
                else:
                    refund_amount = 0.0

            booking.status = "cancelled"
            create_notification(
                db=db,
                user_id=current_user.id,
                title="Booking Cancelled",
                message=f"Booking {booking_id} has been cancelled."
                + (f" ₹{refund_amount:,.2f} has been refunded to your wallet." if refund_amount > 0 else ""),
                notification_type="task",
                reference_id=booking.id,
                reference_type="worker_booking",
                icon="fa-calendar-times",
                action_url="workers.html",
            )
        elif payload.status == "confirmed" and booking.status == "pending":
            booking.status = "confirmed"
            create_notification(
                db=db,
                user_id=current_user.id,
                title="Booking Confirmed",
                message=f"Booking {booking_id} has been confirmed.",
                notification_type="task",
                reference_id=booking.id,
                reference_type="worker_booking",
                icon="fa-calendar-check",
                action_url="workers.html",
            )
        elif payload.status == "in_progress" and booking.status == "confirmed":
            booking.status = "in_progress"
        elif payload.status == "completed" and booking.status == "in_progress":
            booking.status = "completed"
            create_notification(
                db=db,
                user_id=current_user.id,
                title="Booking Completed",
                message=f"Booking {booking_id} has been completed. You can now leave a review.",
                notification_type="task",
                reference_id=booking.id,
                reference_type="worker_booking",
                icon="fa-check-circle",
                action_url="workers.html",
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change status from '{booking.status}' to '{payload.status}'",
            )

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
            "total_pages": max(1, (total + limit - 1) // limit),
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
