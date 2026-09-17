"""
Livestock Management Router - Farm Assist
All endpoints are strictly scoped to the authenticated farmer.
Backend derives farmer ownership from the JWT token; never trusts frontend-supplied IDs.
"""
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.livestock import (
    Livestock,
    LivestockHealthRecord,
    LivestockVaccination,
    LivestockTreatment,
    LivestockFeedingRecord,
    LivestockBreedingRecord,
    LivestockWeightRecord,
    LivestockProductionRecord,
    LivestockExpenseRecord,
)
from app.utils.notification_helper import create_notification
from app.models.notification import Notification

router = APIRouter(prefix="/api/v1/livestock", tags=["Livestock"])


# ─────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────

class AnimalCreate(BaseModel):
    name: str
    animal_type: str
    tag_id: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    weight_kg: Optional[float] = None
    color: Optional[str] = None
    source: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    location: Optional[str] = None
    health_status: Optional[str] = "healthy"
    photo_url: Optional[str] = None
    notes: Optional[str] = None


class AnimalUpdate(BaseModel):
    name: Optional[str] = None
    animal_type: Optional[str] = None
    tag_id: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    weight_kg: Optional[float] = None
    color: Optional[str] = None
    source: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    location: Optional[str] = None
    health_status: Optional[str] = None
    photo_url: Optional[str] = None
    notes: Optional[str] = None


class HealthRecordCreate(BaseModel):
    record_date: Optional[str] = None
    health_status: Optional[str] = None
    symptoms: Optional[str] = None
    observation: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    medicine: Optional[str] = None
    veterinarian: Optional[str] = None
    follow_up_date: Optional[str] = None
    notes: Optional[str] = None


class VaccinationCreate(BaseModel):
    vaccine_name: str
    date_given: Optional[str] = None
    next_due_date: Optional[str] = None
    dose: Optional[str] = None
    veterinarian: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "completed"


class TreatmentCreate(BaseModel):
    treatment_date: Optional[str] = None
    issue: Optional[str] = None
    treatment: Optional[str] = None
    medicine: Optional[str] = None
    veterinarian: Optional[str] = None
    status: Optional[str] = "ongoing"
    notes: Optional[str] = None


class FeedingRecordCreate(BaseModel):
    feed_type: Optional[str] = None
    quantity: Optional[str] = None
    frequency: Optional[str] = None
    feeding_time: Optional[str] = None
    water_requirement: Optional[str] = None
    notes: Optional[str] = None
    record_date: Optional[str] = None


class BreedingRecordCreate(BaseModel):
    breeding_date: Optional[str] = None
    method: Optional[str] = None
    partner_info: Optional[str] = None
    pregnancy_status: Optional[str] = None
    expected_delivery_date: Optional[str] = None
    actual_delivery_date: Optional[str] = None
    offspring_count: Optional[int] = None
    notes: Optional[str] = None


class WeightRecordCreate(BaseModel):
    measurement_date: Optional[str] = None
    weight_kg: float
    notes: Optional[str] = None


class ProductionRecordCreate(BaseModel):
    record_date: Optional[str] = None
    product_type: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    notes: Optional[str] = None


class ExpenseRecordCreate(BaseModel):
    expense_date: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    vendor: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────

def _get_animal_or_404(db: Session, animal_id: str, user_id: str) -> Livestock:
    """Get animal by animal_id, strictly scoped to the farmer."""
    animal = db.query(Livestock).filter(
        Livestock.animal_id == animal_id,
        Livestock.user_id == user_id,
        Livestock.is_active == True,
    ).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    return animal


def _animal_dict(a: Livestock) -> dict:
    return {
        "id": a.id,
        "animal_id": a.animal_id,
        "name": a.name,
        "tag_id": a.tag_id,
        "animal_type": a.animal_type,
        "breed": a.breed,
        "gender": a.gender,
        "date_of_birth": a.date_of_birth,
        "weight_kg": a.weight_kg,
        "color": a.color,
        "source": a.source,
        "purchase_date": a.purchase_date,
        "purchase_price": a.purchase_price,
        "location": a.location,
        "health_status": a.health_status,
        "photo_url": a.photo_url,
        "notes": a.notes,
        "created_at": str(a.created_at) if a.created_at else None,
        "updated_at": str(a.updated_at) if a.updated_at else None,
    }


def _vaccination_status(next_due: Optional[str]) -> str:
    """Derive a vaccination status badge from the next_due_date string."""
    if not next_due:
        return "completed"
    try:
        due = datetime.strptime(next_due, "%Y-%m-%d").date()
        today = date.today()
        if due < today:
            return "overdue"
        if due <= today + timedelta(days=30):
            return "due_soon"
        return "completed"
    except ValueError:
        return "completed"


# ─────────────────────────────────────────────────────────
# OVERVIEW / STATS
# ─────────────────────────────────────────────────────────

@router.get("/overview")
def get_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return livestock statistics for the authenticated farmer."""
    uid = current_user.id

    total = db.query(func.count(Livestock.id)).filter(
        Livestock.user_id == uid, Livestock.is_active == True
    ).scalar() or 0

    healthy = db.query(func.count(Livestock.id)).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        Livestock.health_status == "healthy",
    ).scalar() or 0

    monitoring = db.query(func.count(Livestock.id)).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        Livestock.health_status == "monitoring",
    ).scalar() or 0

    critical = db.query(func.count(Livestock.id)).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        Livestock.health_status == "critical",
    ).scalar() or 0

    needs_attention = db.query(func.count(Livestock.id)).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        Livestock.health_status.in_(["needs_attention", "critical"]),
    ).scalar() or 0

    # Count vaccinations that are overdue or due soon (includes overdue: no lower bound)
    today_str = date.today().isoformat()
    soon_str = (date.today() + timedelta(days=30)).isoformat()
    vacc_due = db.query(func.count(LivestockVaccination.id)).join(
        Livestock, Livestock.id == LivestockVaccination.animal_id
    ).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        LivestockVaccination.next_due_date.isnot(None),
        LivestockVaccination.next_due_date != "",
        LivestockVaccination.next_due_date <= soon_str,
    ).scalar() or 0

    vacc_overdue = db.query(func.count(LivestockVaccination.id)).join(
        Livestock, Livestock.id == LivestockVaccination.animal_id
    ).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        LivestockVaccination.next_due_date.isnot(None),
        LivestockVaccination.next_due_date != "",
        LivestockVaccination.next_due_date < today_str,
    ).scalar() or 0

    # Per-type breakdown
    type_counts = db.query(
        Livestock.animal_type,
        func.count(Livestock.id),
    ).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
    ).group_by(Livestock.animal_type).all()
    by_type = {row[0]: row[1] for row in type_counts}

    # Livestock expense + production totals (real values, 0 when none)
    total_expenses = db.query(
        func.coalesce(func.sum(LivestockExpenseRecord.amount), 0)
    ).filter(LivestockExpenseRecord.user_id == uid).scalar() or 0
    try:
        total_expenses = float(total_expenses)
    except (TypeError, ValueError):
        total_expenses = 0

    production_count = db.query(func.count(LivestockProductionRecord.id)).filter(
        LivestockProductionRecord.user_id == uid
    ).scalar() or 0

    return {
        "status": "success",
        "data": {
            "total": total,
            "healthy": healthy,
            "monitoring": monitoring,
            "needs_attention": needs_attention,
            "critical": critical,
            "vaccinations_due": vacc_due,
            "vaccinations_overdue": vacc_overdue,
            "by_type": by_type,
            "total_expenses": total_expenses,
            "production_records": production_count,
        },
    }


# ─────────────────────────────────────────────────────────
# ANIMAL CRUD
# ─────────────────────────────────────────────────────────

# Register this static path before the dynamic animal path below.  FastAPI
# resolves routes in declaration order, so otherwise "events" is interpreted
# as an animal_id and the upcoming-events endpoint is unreachable.
@router.get("/events/upcoming", include_in_schema=False)
def get_upcoming_events_ordered(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_upcoming_events(days=days, current_user=current_user, db=db)

@router.get("")
def list_animals(
    animal_type: Optional[str] = None,
    health_status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Livestock).filter(
        Livestock.user_id == current_user.id,
        Livestock.is_active == True,
    )
    if animal_type:
        query = query.filter(Livestock.animal_type == animal_type)
    if health_status:
        query = query.filter(Livestock.health_status == health_status)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Livestock.name.ilike(term),
                Livestock.tag_id.ilike(term),
                Livestock.breed.ilike(term),
            )
        )
    animals = query.order_by(Livestock.created_at.desc()).limit(limit).all()
    return {
        "status": "success",
        "data": [_animal_dict(a) for a in animals],
        "total": len(animals),
    }


@router.post("")
def create_animal(
    payload: AnimalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Animal name is required")
    if not payload.animal_type or not payload.animal_type.strip():
        raise HTTPException(status_code=400, detail="Animal type is required")

    animal_id = generate_id("FA-LVS", db, Livestock)
    animal = Livestock(
        animal_id=animal_id,
        user_id=current_user.id,
        name=payload.name.strip(),
        animal_type=payload.animal_type.lower().strip(),
        tag_id=payload.tag_id,
        breed=payload.breed,
        gender=payload.gender,
        date_of_birth=payload.date_of_birth,
        weight_kg=payload.weight_kg,
        color=payload.color,
        source=payload.source,
        purchase_date=payload.purchase_date,
        purchase_price=payload.purchase_price,
        location=payload.location,
        health_status=payload.health_status or "healthy",
        photo_url=payload.photo_url,
        notes=payload.notes,
    )
    db.add(animal)
    db.commit()
    db.refresh(animal)

    # Notify farmer
    try:
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Animal Added",
            message=f"{payload.name} has been added to your livestock.",
            notification_type="system",
            icon="fa-paw",
            action_url="livestock.html",
        )
        db.commit()
    except Exception:
        db.rollback()

    return {"status": "success", "message": "Animal added successfully", "data": _animal_dict(animal)}


@router.get("/{animal_id}")
def get_animal(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    return {"status": "success", "data": _animal_dict(animal)}


@router.put("/{animal_id}")
def update_animal(
    animal_id: str,
    payload: AnimalUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    updates = payload.model_dump(exclude_unset=True)
    for key, val in updates.items():
        setattr(animal, key, val)
    animal.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(animal)
    return {"status": "success", "message": "Animal updated successfully", "data": _animal_dict(animal)}


@router.delete("/{animal_id}")
def delete_animal(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    animal.is_active = False
    animal.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "message": "Animal removed successfully"}


# ─────────────────────────────────────────────────────────
# HEALTH RECORDS
# ─────────────────────────────────────────────────────────

@router.get("/{animal_id}/health")
def list_health_records(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    records = db.query(LivestockHealthRecord).filter(
        LivestockHealthRecord.animal_id == animal.id,
        LivestockHealthRecord.user_id == current_user.id,
    ).order_by(LivestockHealthRecord.created_at.desc()).all()
    data = [{
        "id": r.id,
        "record_id": r.record_id,
        "record_date": r.record_date,
        "health_status": r.health_status,
        "symptoms": r.symptoms,
        "observation": r.observation,
        "diagnosis": r.diagnosis,
        "treatment": r.treatment,
        "medicine": r.medicine,
        "veterinarian": r.veterinarian,
        "follow_up_date": r.follow_up_date,
        "notes": r.notes,
        "created_at": str(r.created_at) if r.created_at else None,
    } for r in records]
    return {"status": "success", "data": data}


@router.post("/{animal_id}/health")
def add_health_record(
    animal_id: str,
    payload: HealthRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    rec_id = generate_id("FA-LHR", db, LivestockHealthRecord)
    rec = LivestockHealthRecord(
        record_id=rec_id,
        animal_id=animal.id,
        user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )
    db.add(rec)
    # Update animal's health status if provided
    if payload.health_status:
        animal.health_status = payload.health_status
        animal.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rec)

    if payload.health_status and payload.health_status in ("needs_attention", "critical"):
        try:
            create_notification(
                db=db,
                user_id=current_user.id,
                title="Livestock Health Alert",
                message=f"{animal.name} health status updated to {payload.health_status}.",
                notification_type="system",
                icon="fa-heartbeat",
                action_url="livestock.html",
            )
            db.commit()
        except Exception:
            db.rollback()

    return {"status": "success", "message": "Health record added", "data": {"id": rec.id, "record_id": rec.record_id}}


# ─────────────────────────────────────────────────────────
# VACCINATIONS
# ─────────────────────────────────────────────────────────

@router.get("/{animal_id}/vaccinations")
def list_vaccinations(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    records = db.query(LivestockVaccination).filter(
        LivestockVaccination.animal_id == animal.id,
        LivestockVaccination.user_id == current_user.id,
    ).order_by(LivestockVaccination.created_at.desc()).all()
    data = [{
        "id": r.id,
        "vacc_id": r.vacc_id,
        "vaccine_name": r.vaccine_name,
        "date_given": r.date_given,
        "next_due_date": r.next_due_date,
        "dose": r.dose,
        "veterinarian": r.veterinarian,
        "notes": r.notes,
        "status": _vaccination_status(r.next_due_date),
        "created_at": str(r.created_at) if r.created_at else None,
    } for r in records]
    return {"status": "success", "data": data}


@router.post("/{animal_id}/vaccinations")
def add_vaccination(
    animal_id: str,
    payload: VaccinationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    vacc_id = generate_id("FA-LVC", db, LivestockVaccination)
    rec = LivestockVaccination(
        vacc_id=vacc_id,
        animal_id=animal.id,
        user_id=current_user.id,
        vaccine_name=payload.vaccine_name,
        date_given=payload.date_given,
        next_due_date=payload.next_due_date,
        dose=payload.dose,
        veterinarian=payload.veterinarian,
        notes=payload.notes,
        status=_vaccination_status(payload.next_due_date),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    if payload.next_due_date:
        try:
            create_notification(
                db=db,
                user_id=current_user.id,
                title="Vaccination Recorded",
                message=f"{payload.vaccine_name} for {animal.name}. Next due: {payload.next_due_date}.",
                notification_type="system",
                icon="fa-syringe",
                action_url="livestock.html",
            )
            db.commit()
        except Exception:
            db.rollback()

    return {"status": "success", "message": "Vaccination record added", "data": {"id": rec.id, "vacc_id": rec.vacc_id}}


# ─────────────────────────────────────────────────────────
# TREATMENTS
# ─────────────────────────────────────────────────────────

@router.get("/{animal_id}/treatments")
def list_treatments(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    records = db.query(LivestockTreatment).filter(
        LivestockTreatment.animal_id == animal.id,
        LivestockTreatment.user_id == current_user.id,
    ).order_by(LivestockTreatment.created_at.desc()).all()
    data = [{
        "id": r.id,
        "treatment_id": r.treatment_id,
        "treatment_date": r.treatment_date,
        "issue": r.issue,
        "treatment": r.treatment,
        "medicine": r.medicine,
        "veterinarian": r.veterinarian,
        "status": r.status,
        "notes": r.notes,
        "created_at": str(r.created_at) if r.created_at else None,
    } for r in records]
    return {"status": "success", "data": data}


@router.post("/{animal_id}/treatments")
def add_treatment(
    animal_id: str,
    payload: TreatmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    t_id = generate_id("FA-LTR", db, LivestockTreatment)
    rec = LivestockTreatment(
        treatment_id=t_id,
        animal_id=animal.id,
        user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"status": "success", "message": "Treatment record added", "data": {"id": rec.id, "treatment_id": rec.treatment_id}}


# ─────────────────────────────────────────────────────────
# FEEDING
# ─────────────────────────────────────────────────────────

@router.get("/{animal_id}/feeding")
def list_feeding_records(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    records = db.query(LivestockFeedingRecord).filter(
        LivestockFeedingRecord.animal_id == animal.id,
        LivestockFeedingRecord.user_id == current_user.id,
    ).order_by(LivestockFeedingRecord.created_at.desc()).all()
    data = [{
        "id": r.id,
        "feed_id": r.feed_id,
        "feed_type": r.feed_type,
        "quantity": r.quantity,
        "frequency": r.frequency,
        "feeding_time": r.feeding_time,
        "water_requirement": r.water_requirement,
        "record_date": r.record_date,
        "notes": r.notes,
        "created_at": str(r.created_at) if r.created_at else None,
    } for r in records]
    return {"status": "success", "data": data}


@router.post("/{animal_id}/feeding")
def add_feeding_record(
    animal_id: str,
    payload: FeedingRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    f_id = generate_id("FA-LFD", db, LivestockFeedingRecord)
    rec = LivestockFeedingRecord(
        feed_id=f_id,
        animal_id=animal.id,
        user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"status": "success", "message": "Feeding record added", "data": {"id": rec.id, "feed_id": rec.feed_id}}


# ─────────────────────────────────────────────────────────
# BREEDING
# ─────────────────────────────────────────────────────────

@router.get("/{animal_id}/breeding")
def list_breeding_records(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    records = db.query(LivestockBreedingRecord).filter(
        LivestockBreedingRecord.animal_id == animal.id,
        LivestockBreedingRecord.user_id == current_user.id,
    ).order_by(LivestockBreedingRecord.created_at.desc()).all()
    data = [{
        "id": r.id,
        "breeding_id": r.breeding_id,
        "breeding_date": r.breeding_date,
        "method": r.method,
        "partner_info": r.partner_info,
        "pregnancy_status": r.pregnancy_status,
        "expected_delivery_date": r.expected_delivery_date,
        "actual_delivery_date": r.actual_delivery_date,
        "offspring_count": r.offspring_count,
        "notes": r.notes,
        "created_at": str(r.created_at) if r.created_at else None,
    } for r in records]
    return {"status": "success", "data": data}


@router.post("/{animal_id}/breeding")
def add_breeding_record(
    animal_id: str,
    payload: BreedingRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    b_id = generate_id("FA-LBR", db, LivestockBreedingRecord)
    rec = LivestockBreedingRecord(
        breeding_id=b_id,
        animal_id=animal.id,
        user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    if payload.expected_delivery_date:
        try:
            create_notification(
                db=db,
                user_id=current_user.id,
                title="Breeding Record Added",
                message=f"{animal.name}: expected delivery on {payload.expected_delivery_date}.",
                notification_type="system",
                icon="fa-baby",
                action_url="livestock.html",
            )
            db.commit()
        except Exception:
            db.rollback()

    return {"status": "success", "message": "Breeding record added", "data": {"id": rec.id, "breeding_id": rec.breeding_id}}


# ─────────────────────────────────────────────────────────
# WEIGHT / GROWTH
# ─────────────────────────────────────────────────────────

@router.get("/{animal_id}/weight")
def list_weight_records(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    records = db.query(LivestockWeightRecord).filter(
        LivestockWeightRecord.animal_id == animal.id,
        LivestockWeightRecord.user_id == current_user.id,
    ).order_by(LivestockWeightRecord.created_at.asc()).all()
    data = [{
        "id": r.id,
        "weight_id": r.weight_id,
        "measurement_date": r.measurement_date,
        "weight_kg": r.weight_kg,
        "notes": r.notes,
        "created_at": str(r.created_at) if r.created_at else None,
    } for r in records]
    return {"status": "success", "data": data}


@router.post("/{animal_id}/weight")
def add_weight_record(
    animal_id: str,
    payload: WeightRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    if payload.weight_kg <= 0:
        raise HTTPException(status_code=400, detail="Weight must be greater than zero")
    w_id = generate_id("FA-LWR", db, LivestockWeightRecord)
    rec = LivestockWeightRecord(
        weight_id=w_id,
        animal_id=animal.id,
        user_id=current_user.id,
        measurement_date=payload.measurement_date or date.today().isoformat(),
        weight_kg=payload.weight_kg,
        notes=payload.notes,
    )
    db.add(rec)
    # Update animal's current weight
    animal.weight_kg = payload.weight_kg
    animal.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rec)
    return {"status": "success", "message": "Weight record added", "data": {"id": rec.id, "weight_id": rec.weight_id}}


# ─────────────────────────────────────────────────────────
# UPCOMING EVENTS (vaccinations + health follow-ups)
# ─────────────────────────────────────────────────────────

def _collect_attention_events(uid: str, db: Session, days: int = 30):
    """Shared helper: overdue + upcoming vaccinations, follow-ups, deliveries,
    ongoing treatments and critical animals. All queries scoped to the farmer."""
    today = date.today()
    today_str = today.isoformat()
    cutoff_str = (today + timedelta(days=days)).isoformat()
    # include overdue items up to 180 days back so genuinely overdue work appears
    overdue_floor = (today - timedelta(days=180)).isoformat()

    events = []

    # Vaccinations: ALL overdue (however old) + due soon. Overdue must never be hidden.
    vacc_records = db.query(LivestockVaccination, Livestock).join(
        Livestock, Livestock.id == LivestockVaccination.animal_id
    ).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        LivestockVaccination.next_due_date.isnot(None),
        LivestockVaccination.next_due_date != "",
        LivestockVaccination.next_due_date <= cutoff_str,
    ).all()
    for vacc, animal in vacc_records:
        vstatus = _vaccination_status(vacc.next_due_date)
        events.append({
            "type": "vaccination",
            "animal_id": animal.animal_id,
            "animal_name": animal.name,
            "animal_type": animal.animal_type,
            "event": vacc.vaccine_name,
            "date": vacc.next_due_date,
            "status": vstatus,
        })

    # Health follow-ups: overdue + upcoming
    health_records = db.query(LivestockHealthRecord, Livestock).join(
        Livestock, Livestock.id == LivestockHealthRecord.animal_id
    ).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        LivestockHealthRecord.follow_up_date.isnot(None),
        LivestockHealthRecord.follow_up_date != "",
        LivestockHealthRecord.follow_up_date >= overdue_floor,
        LivestockHealthRecord.follow_up_date <= cutoff_str,
    ).all()
    for rec, animal in health_records:
        fstatus = "overdue" if (rec.follow_up_date or "") < today_str else "upcoming"
        events.append({
            "type": "health_checkup",
            "animal_id": animal.animal_id,
            "animal_name": animal.name,
            "animal_type": animal.animal_type,
            "event": "Follow-up checkup",
            "date": rec.follow_up_date,
            "status": fstatus,
        })

    # Breeding expected delivery: upcoming + recently overdue
    breeding_records = db.query(LivestockBreedingRecord, Livestock).join(
        Livestock, Livestock.id == LivestockBreedingRecord.animal_id
    ).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        LivestockBreedingRecord.expected_delivery_date.isnot(None),
        LivestockBreedingRecord.expected_delivery_date != "",
        LivestockBreedingRecord.expected_delivery_date >= overdue_floor,
        LivestockBreedingRecord.expected_delivery_date <= cutoff_str,
    ).all()
    for rec, animal in breeding_records:
        bstatus = "overdue" if (rec.expected_delivery_date or "") < today_str else "upcoming"
        events.append({
            "type": "breeding",
            "animal_id": animal.animal_id,
            "animal_name": animal.name,
            "animal_type": animal.animal_type,
            "event": "Expected delivery",
            "date": rec.expected_delivery_date,
            "status": bstatus,
        })

    # Ongoing / follow-up treatments needing attention
    treatments = db.query(LivestockTreatment, Livestock).join(
        Livestock, Livestock.id == LivestockTreatment.animal_id
    ).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        LivestockTreatment.status.in_(["ongoing", "follow_up"]),
    ).order_by(LivestockTreatment.created_at.desc()).limit(20).all()
    for rec, animal in treatments:
        events.append({
            "type": "treatment",
            "animal_id": animal.animal_id,
            "animal_name": animal.name,
            "animal_type": animal.animal_type,
            "event": (rec.issue or "Ongoing treatment"),
            "date": rec.treatment_date,
            "status": "ongoing" if rec.status == "ongoing" else "upcoming",
        })

    # Critical / needs-attention animals without a dated event still surface
    flagged = db.query(Livestock).filter(
        Livestock.user_id == uid,
        Livestock.is_active == True,
        Livestock.health_status.in_(["critical", "needs_attention"]),
    ).order_by(Livestock.updated_at.desc()).limit(20).all()
    for animal in flagged:
        events.append({
            "type": "health_alert",
            "animal_id": animal.animal_id,
            "animal_name": animal.name,
            "animal_type": animal.animal_type,
            "event": "Needs veterinary attention",
            "date": None,
            "status": "overdue" if animal.health_status == "critical" else "upcoming",
        })

    def _sort_key(e):
        # overdue / undated first, then by date
        order = {"overdue": 0, "ongoing": 1, "due_soon": 2, "upcoming": 3, "completed": 4}
        return (order.get(e.get("status"), 5), e.get("date") or "")

    events.sort(key=_sort_key)
    return events


def get_upcoming_events(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    events = _collect_attention_events(current_user.id, db, days=days)
    return {"status": "success", "data": events}


@router.get("/attention/summary", include_in_schema=False)
def get_attention_summary_ordered(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_attention_summary(days=days, current_user=current_user, db=db)


@router.get("/activity/recent", include_in_schema=False)
def get_recent_activity_ordered(
    limit: int = Query(15, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_recent_activity(limit=limit, current_user=current_user, db=db)


def get_attention_summary(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Attention-required items derived only from real database records."""
    events = _collect_attention_events(current_user.id, db, days=days)
    overdue = [e for e in events if e.get("status") == "overdue"]
    upcoming = [e for e in events if e.get("status") in ("upcoming", "due_soon", "ongoing")]
    return {"status": "success", "data": {"overdue": overdue, "upcoming": upcoming, "all": events}}


def get_recent_activity(
    limit: int = Query(15, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent livestock activity built only from real records (no fake entries)."""
    uid = current_user.id
    items = []

    def _animal_name_map():
        animals = db.query(Livestock).filter(
            Livestock.user_id == uid, Livestock.is_active == True
        ).all()
        return {a.id: (a.name, a.animal_id, a.animal_type) for a in animals}

    names = _animal_name_map()

    def _push(ts, kind, title, subtitle, animal_pk=None):
        name, aid, atype = names.get(animal_pk, (None, None, None)) if animal_pk else (None, None, None)
        items.append({
            "type": kind,
            "title": title,
            "subtitle": subtitle,
            "animal_name": name,
            "animal_id": aid,
            "animal_type": atype,
            "at": str(ts) if ts else None,
        })

    recent_animals = db.query(Livestock).filter(
        Livestock.user_id == uid, Livestock.is_active == True
    ).order_by(Livestock.created_at.desc()).limit(5).all()
    for a in recent_animals:
        _push(a.created_at, "animal_added", f"{a.name} added", f"{(a.animal_type or '').title()} joined your livestock")

    for model, kind, title_fn, sub_fn in [
        (LivestockVaccination, "vaccination", lambda r: f"Vaccination: {r.vaccine_name}",
         lambda r: f"Due {r.next_due_date}" if r.next_due_date else "Recorded"),
        (LivestockHealthRecord, "health", lambda r: "Health record updated",
         lambda r: (r.diagnosis or r.symptoms or "Checkup recorded")),
        (LivestockFeedingRecord, "feeding", lambda r: f"Feeding: {r.feed_type or 'record'}",
         lambda r: (r.quantity or "Feeding recorded")),
        (LivestockProductionRecord, "production", lambda r: f"Production: {r.product_type or 'record'}",
         lambda r: (f"{r.quantity} {r.unit or ''}".strip() or "Recorded")),
        (LivestockExpenseRecord, "expense", lambda r: f"Expense: {r.category or 'record'}",
         lambda r: (f"₹{r.amount}" if r.amount else "Recorded")),
        (LivestockWeightRecord, "weight", lambda r: f"Weigh-in: {r.weight_kg} kg", lambda r: "Growth recorded"),
        (LivestockBreedingRecord, "breeding", lambda r: "Breeding record added",
         lambda r: (r.pregnancy_status or "Recorded")),
        (LivestockTreatment, "treatment", lambda r: f"Treatment: {r.issue or 'record'}",
         lambda r: (r.status or "Recorded")),
    ]:
        try:
            rows = db.query(model).filter(model.user_id == uid).order_by(
                model.created_at.desc()).limit(5).all()
            for r in rows:
                try:
                    _push(r.created_at, kind, title_fn(r), sub_fn(r), getattr(r, "animal_id", None))
                except Exception:
                    continue
        except Exception:
            continue

    def _ts(x):
        try:
            return x.get("at") or ""
        except Exception:
            return ""

    items.sort(key=_ts, reverse=True)
    return {"status": "success", "data": items[:limit]}


# ─────────────────────────────────────────────────────────
# PRODUCTION (MILK / EGGS / WOOL)
# ─────────────────────────────────────────────────────────

@router.get("/{animal_id}/production")
def list_production_records(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    records = db.query(LivestockProductionRecord).filter(
        LivestockProductionRecord.animal_id == animal.id,
        LivestockProductionRecord.user_id == current_user.id,
    ).order_by(LivestockProductionRecord.created_at.desc()).all()
    data = [{
        "id": r.id,
        "production_id": r.production_id,
        "record_date": r.record_date,
        "product_type": r.product_type,
        "quantity": r.quantity,
        "unit": r.unit,
        "notes": r.notes,
        "created_at": str(r.created_at) if r.created_at else None,
    } for r in records]
    return {"status": "success", "data": data}


@router.post("/{animal_id}/production")
def add_production_record(
    animal_id: str,
    payload: ProductionRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    p_id = generate_id("FA-LPR", db, LivestockProductionRecord)
    rec = LivestockProductionRecord(
        production_id=p_id,
        animal_id=animal.id,
        user_id=current_user.id,
        record_date=payload.record_date or date.today().isoformat(),
        product_type=payload.product_type,
        quantity=payload.quantity,
        unit=payload.unit,
        notes=payload.notes,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"status": "success", "message": "Production record added",
            "data": {"id": rec.id, "production_id": rec.production_id}}


# ─────────────────────────────────────────────────────────
# EXPENSES
# ─────────────────────────────────────────────────────────

@router.get("/{animal_id}/expenses")
def list_expense_records(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    records = db.query(LivestockExpenseRecord).filter(
        LivestockExpenseRecord.animal_id == animal.id,
        LivestockExpenseRecord.user_id == current_user.id,
    ).order_by(LivestockExpenseRecord.created_at.desc()).all()
    data = [{
        "id": r.id,
        "expense_id": r.expense_id,
        "expense_date": r.expense_date,
        "category": r.category,
        "amount": r.amount,
        "vendor": r.vendor,
        "description": r.description,
        "notes": r.notes,
        "created_at": str(r.created_at) if r.created_at else None,
    } for r in records]
    return {"status": "success", "data": data}


@router.post("/{animal_id}/expenses")
def add_expense_record(
    animal_id: str,
    payload: ExpenseRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    if payload.amount is not None and payload.amount < 0:
        raise HTTPException(status_code=400, detail="Amount cannot be negative")
    e_id = generate_id("FA-LEX", db, LivestockExpenseRecord)
    rec = LivestockExpenseRecord(
        expense_id=e_id,
        animal_id=animal.id,
        user_id=current_user.id,
        expense_date=payload.expense_date or date.today().isoformat(),
        category=payload.category,
        amount=payload.amount,
        vendor=payload.vendor,
        description=payload.description,
        notes=payload.notes,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {"status": "success", "message": "Expense record added",
            "data": {"id": rec.id, "expense_id": rec.expense_id}}


# ─────────────────────────────────────────────────────────
# FULL DETAIL (single secure fetch for the details panel)
# ─────────────────────────────────────────────────────────

@router.get("/{animal_id}/full")
def get_animal_full(
    animal_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Complete animal details + counts, always loaded from the backend by ID."""
    animal = _get_animal_or_404(db, animal_id, current_user.id)
    aid = animal.id
    uid = current_user.id

    def _count(model):
        return db.query(func.count(model.id)).filter(
            model.animal_id == aid, model.user_id == uid).scalar() or 0

    counts = {
        "health": _count(LivestockHealthRecord),
        "vaccinations": _count(LivestockVaccination),
        "treatments": _count(LivestockTreatment),
        "feeding": _count(LivestockFeedingRecord),
        "breeding": _count(LivestockBreedingRecord),
        "weight": _count(LivestockWeightRecord),
        "production": _count(LivestockProductionRecord),
        "expenses": _count(LivestockExpenseRecord),
    }

    latest_weight = db.query(LivestockWeightRecord).filter(
        LivestockWeightRecord.animal_id == aid,
        LivestockWeightRecord.user_id == uid,
    ).order_by(LivestockWeightRecord.created_at.desc()).first()

    upcoming = [e for e in _collect_attention_events(uid, db, days=60)
                if e.get("animal_id") == animal.animal_id][:5]

    return {
        "status": "success",
        "data": {
            "animal": _animal_dict(animal),
            "counts": counts,
            "latest_weight_kg": latest_weight.weight_kg if latest_weight else animal.weight_kg,
            "attention": upcoming,
        },
    }
