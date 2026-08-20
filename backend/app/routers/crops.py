from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.models.crop import Crop, CropCycle, CropTask, FarmJournal
from app.utils.auth import get_current_user, generate_id

router = APIRouter(prefix="/api/v1", tags=["Crops"])


class CropCreateRequest(BaseModel):
    name: str
    variety: Optional[str] = None
    category: Optional[str] = None
    season: Optional[str] = None
    growth_duration_days: Optional[float] = None


class CropCycleCreateRequest(BaseModel):
    farm_id: str
    plot_id: Optional[str] = None
    crop_id: str
    sowing_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    seed_quantity: Optional[float] = None
    seed_unit: Optional[str] = None
    fertilizer_usage: Optional[str] = None
    pesticide_usage: Optional[str] = None
    irrigation_schedule: Optional[str] = None
    notes: Optional[str] = None


class CropCycleUpdateRequest(BaseModel):
    plot_id: Optional[str] = None
    crop_id: Optional[str] = None
    sowing_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    actual_harvest_date: Optional[str] = None
    current_stage: Optional[str] = None
    seed_quantity: Optional[float] = None
    seed_unit: Optional[str] = None
    fertilizer_usage: Optional[str] = None
    pesticide_usage: Optional[str] = None
    irrigation_schedule: Optional[str] = None
    yield_quantity: Optional[float] = None
    yield_unit: Optional[str] = None
    revenue: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class CropTaskCreateRequest(BaseModel):
    crop_cycle_id: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: Optional[str] = "medium"


class CropTaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


class JournalCreateRequest(BaseModel):
    farm_id: Optional[str] = None
    plot_id: Optional[str] = None
    activity: str
    notes: Optional[str] = None


def _crop_dict(crop: Crop) -> dict:
    return {
        "id": crop.id,
        "crop_id": crop.crop_id,
        "name": crop.name,
        "variety": crop.variety,
        "category": crop.category,
        "season": crop.season,
        "growth_duration_days": crop.growth_duration_days,
    }


def _cycle_dict(cycle: CropCycle) -> dict:
    return {
        "id": cycle.id,
        "cycle_id": cycle.cycle_id,
        "farm_id": cycle.farm_id,
        "plot_id": cycle.plot_id,
        "crop_id": cycle.crop_id,
        "sowing_date": cycle.sowing_date,
        "expected_harvest_date": cycle.expected_harvest_date,
        "actual_harvest_date": cycle.actual_harvest_date,
        "current_stage": cycle.current_stage,
        "seed_quantity": cycle.seed_quantity,
        "seed_unit": cycle.seed_unit,
        "fertilizer_usage": cycle.fertilizer_usage,
        "pesticide_usage": cycle.pesticide_usage,
        "irrigation_schedule": cycle.irrigation_schedule,
        "yield_quantity": cycle.yield_quantity,
        "yield_unit": cycle.yield_unit,
        "revenue": cycle.revenue,
        "notes": cycle.notes,
        "status": cycle.status,
        "created_at": str(cycle.created_at) if cycle.created_at else None,
    }


def _task_dict(task: CropTask) -> dict:
    return {
        "id": task.id,
        "task_id": task.task_id,
        "crop_cycle_id": task.crop_cycle_id,
        "title": task.title,
        "description": task.description,
        "category": task.category,
        "due_date": task.due_date,
        "due_time": task.due_time,
        "status": task.status,
        "priority": task.priority,
        "completed_at": str(task.completed_at) if task.completed_at else None,
        "created_at": str(task.created_at) if task.created_at else None,
    }


def _journal_dict(entry: FarmJournal) -> dict:
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "farm_id": entry.farm_id,
        "plot_id": entry.plot_id,
        "activity": entry.activity,
        "notes": entry.notes,
        "entry_date": str(entry.entry_date) if entry.entry_date else None,
        "created_at": str(entry.created_at) if entry.created_at else None,
    }


def _get_user_farm_ids(db: Session, user_id: str) -> List[str]:
    farms = db.query(Farm.id).filter(Farm.user_id == user_id, Farm.is_active == True).all()
    return [f.id for f in farms]


def _verify_cycle_ownership(db: Session, cycle_id: str, user_id: str) -> CropCycle:
    cycle = db.query(CropCycle).filter(CropCycle.cycle_id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    farm = db.query(Farm).filter(Farm.id == cycle.farm_id, Farm.user_id == user_id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="Not authorized")
    return cycle


@router.get("/crops", response_model=dict)
def list_crops(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crops = db.query(Crop).all()
    return {
        "status": "success",
        "data": [_crop_dict(c) for c in crops],
    }


@router.post("/crops", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_crop(
    payload: CropCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crop_id = generate_id("FA-CRP", db, Crop)

    crop = Crop(
        crop_id=crop_id,
        name=payload.name,
        variety=payload.variety,
        category=payload.category,
        season=payload.season,
        growth_duration_days=payload.growth_duration_days,
    )
    db.add(crop)
    db.commit()
    db.refresh(crop)

    return {
        "status": "success",
        "message": "Crop created successfully",
        "data": _crop_dict(crop),
    }


@router.get("/crop-cycles", response_model=dict)
def list_crop_cycles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_ids = _get_user_farm_ids(db, current_user.id)
    cycles = db.query(CropCycle).filter(CropCycle.farm_id.in_(farm_ids)).all()
    return {
        "status": "success",
        "data": [_cycle_dict(c) for c in cycles],
    }


@router.post("/crop-cycles", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_crop_cycle(
    payload: CropCycleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm = db.query(Farm).filter(Farm.id == payload.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    crop = db.query(Crop).filter(Crop.id == payload.crop_id).first()
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    if payload.plot_id:
        plot = db.query(FarmPlot).filter(FarmPlot.id == payload.plot_id, FarmPlot.farm_id == farm.id).first()
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found in this farm")

    cycle_id = generate_id("FA-CYC", db, CropCycle)

    cycle = CropCycle(
        cycle_id=cycle_id,
        farm_id=payload.farm_id,
        plot_id=payload.plot_id,
        crop_id=payload.crop_id,
        sowing_date=payload.sowing_date,
        expected_harvest_date=payload.expected_harvest_date,
        seed_quantity=payload.seed_quantity,
        seed_unit=payload.seed_unit,
        fertilizer_usage=payload.fertilizer_usage,
        pesticide_usage=payload.pesticide_usage,
        irrigation_schedule=payload.irrigation_schedule,
        notes=payload.notes,
    )
    db.add(cycle)
    db.commit()
    db.refresh(cycle)

    return {
        "status": "success",
        "message": "Crop cycle created successfully",
        "data": _cycle_dict(cycle),
    }


@router.put("/crop-cycles/{cycle_id}", response_model=dict)
def update_crop_cycle(
    cycle_id: str,
    payload: CropCycleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = _verify_cycle_ownership(db, cycle_id, current_user.id)

    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] == "completed":
        cycle.actual_harvest_date = cycle.actual_harvest_date or datetime.utcnow().strftime("%Y-%m-%d")

    for field, value in update_data.items():
        setattr(cycle, field, value)

    db.commit()
    db.refresh(cycle)

    return {
        "status": "success",
        "message": "Crop cycle updated successfully",
        "data": _cycle_dict(cycle),
    }


@router.delete("/crop-cycles/{cycle_id}", response_model=dict)
def delete_crop_cycle(
    cycle_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = _verify_cycle_ownership(db, cycle_id, current_user.id)

    db.delete(cycle)
    db.commit()

    return {"status": "success", "message": "Crop cycle deleted successfully"}


@router.get("/crop-tasks", response_model=dict)
def list_crop_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_ids = _get_user_farm_ids(db, current_user.id)
    cycle_ids = [c.id for c in db.query(CropCycle.id).filter(CropCycle.farm_id.in_(farm_ids)).all()]
    tasks = db.query(CropTask).filter(CropTask.crop_cycle_id.in_(cycle_ids)).all()

    return {
        "status": "success",
        "data": [_task_dict(t) for t in tasks],
    }


@router.post("/crop-tasks", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_crop_task(
    payload: CropTaskCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cycle = db.query(CropCycle).filter(CropCycle.id == payload.crop_cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")

    farm = db.query(Farm).filter(Farm.id == cycle.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="Not authorized")

    task_id = generate_id("FA-TSK", db, CropTask)

    task = CropTask(
        task_id=task_id,
        crop_cycle_id=payload.crop_cycle_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        due_date=payload.due_date,
        due_time=payload.due_time,
        priority=payload.priority,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    return {
        "status": "success",
        "message": "Task created successfully",
        "data": _task_dict(task),
    }


@router.put("/crop-tasks/{task_id}", response_model=dict)
def update_crop_task(
    task_id: str,
    payload: CropTaskUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.query(CropTask).filter(CropTask.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    cycle = db.query(CropCycle).filter(CropCycle.id == task.crop_cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Crop cycle not found")
    farm = db.query(Farm).filter(Farm.id == cycle.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="Not authorized")

    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] == "completed":
        task.completed_at = datetime.utcnow()

    for field, value in update_data.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)

    return {
        "status": "success",
        "message": "Task updated successfully",
        "data": _task_dict(task),
    }


@router.post("/farm-journal", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_journal_entry(
    payload: JournalCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.farm_id:
        farm = db.query(Farm).filter(Farm.id == payload.farm_id, Farm.user_id == current_user.id).first()
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")

    entry = FarmJournal(
        user_id=current_user.id,
        farm_id=payload.farm_id,
        plot_id=payload.plot_id,
        activity=payload.activity,
        notes=payload.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {
        "status": "success",
        "message": "Journal entry created successfully",
        "data": _journal_dict(entry),
    }


@router.get("/farm-journal", response_model=dict)
def list_journal_entries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = (
        db.query(FarmJournal)
        .filter(FarmJournal.user_id == current_user.id)
        .order_by(FarmJournal.created_at.desc())
        .all()
    )

    return {
        "status": "success",
        "data": [_journal_dict(e) for e in entries],
    }
