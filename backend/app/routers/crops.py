import asyncio
import re
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_, case, func

from app.database.connection import get_db
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.models.crop import Crop, CropCycle, CropTask, FarmJournal
from app.utils.auth import get_current_user, generate_id

TASK_STATUSES = ["pending", "in_progress", "completed"]
TASK_PRIORITIES = ["low", "medium", "high"]

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
        "farm_name": cycle.farm.farm_name if cycle.farm else None,
        "plot_id": cycle.plot_id,
        "plot_name": cycle.plot.plot_name if cycle.plot else None,
        "crop_id": cycle.crop_id,
        "crop_name": cycle.crop.name if cycle.crop else None,
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
    cycle = task.crop_cycle
    return {
        "id": task.id,
        "task_id": task.task_id,
        "crop_cycle_id": task.crop_cycle_id,
        "cycle_id": cycle.cycle_id if cycle else None,
        "farm_id": cycle.farm_id if cycle else None,
        "farm_name": cycle.farm.farm_name if cycle and cycle.farm else None,
        "plot_id": cycle.plot_id if cycle else None,
        "plot_name": cycle.plot.plot_name if cycle and cycle.plot else None,
        "crop_id": cycle.crop_id if cycle else None,
        "crop_name": cycle.crop.name if cycle and cycle.crop else None,
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
    q: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(pending|in_progress|completed|overdue)$"),
    priority: Optional[str] = Query(None, pattern="^(low|medium|high)$"),
    category: Optional[str] = None,
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_ids = _get_user_farm_ids(db, current_user.id)
    if not farm_ids:
        return {"status": "success", "data": []}

    qry = (
        db.query(CropTask)
        .join(CropCycle, CropTask.crop_cycle_id == CropCycle.id)
        .join(Crop, CropCycle.crop_id == Crop.id)
        .join(Farm, CropCycle.farm_id == Farm.id)
        .outerjoin(FarmPlot, CropCycle.plot_id == FarmPlot.id)
        .filter(CropCycle.farm_id.in_(farm_ids))
    )

    if q:
        term = f"%{q.strip()}%"
        qry = qry.filter(
            or_(
                CropTask.title.ilike(term),
                CropTask.description.ilike(term),
                CropTask.category.ilike(term),
                CropTask.status.ilike(term),
                Crop.name.ilike(term),
                Farm.farm_name.ilike(term),
                FarmPlot.plot_name.ilike(term),
            )
        )

    if status:
        if status == "overdue":
            today = date.today().strftime("%Y-%m-%d")
            qry = qry.filter(
                CropTask.status != "completed",
                CropTask.due_date.isnot(None),
                CropTask.due_date < today,
            )
        else:
            qry = qry.filter(CropTask.status == status)

    if priority:
        qry = qry.filter(CropTask.priority == priority)

    if category:
        qry = qry.filter(CropTask.category.ilike(category))

    if farm_id:
        if farm_id not in farm_ids:
            return {"status": "success", "data": []}
        qry = qry.filter(CropCycle.farm_id == farm_id)

    if plot_id:
        owned_plot_ids = [
            row[0]
            for row in db.query(FarmPlot.id).filter(FarmPlot.farm_id.in_(farm_ids)).all()
        ]
        if plot_id not in owned_plot_ids:
            return {"status": "success", "data": []}
        qry = qry.filter(CropCycle.plot_id == plot_id)

    if crop:
        qry = qry.filter(Crop.name.ilike(f"%{crop.strip()}%"))

    tasks = qry.order_by(
        case((CropTask.status != "completed", 0), else_=1),
        func.coalesce(CropTask.due_date, "9999-12-31").asc(),
        case(
            (CropTask.priority == "high", 0),
            (CropTask.priority == "medium", 1),
            else_=2,
        ),
        CropTask.created_at.asc(),
    ).all()

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
    elif "status" in update_data and update_data["status"] in ("pending", "in_progress"):
        task.completed_at = None

    for field, value in update_data.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)

    return {
        "status": "success",
        "message": "Task updated successfully",
        "data": _task_dict(task),
    }


@router.delete("/crop-tasks/{task_id}", response_model=dict)
def delete_crop_task(
    task_id: str,
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

    db.delete(task)
    db.commit()

    return {"status": "success", "message": "Task deleted successfully"}


# ==================== AI TASK SUGGESTIONS ====================

def _norm_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _date_from_today(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _cycle_stage(cycle: CropCycle, crop: Crop) -> str:
    if cycle.current_stage:
        return cycle.current_stage.strip().lower()
    sowing = cycle.sowing_date or cycle.created_at.strftime("%Y-%m-%d") if cycle.created_at else None
    if not sowing:
        return "vegetative"
    try:
        sd = date.fromisoformat(str(sowing)[:10])
        days = (date.today() - sd).days
    except Exception:
        return "vegetative"
    if days < 0:
        return "vegetative"
    duration = crop.growth_duration_days or 0
    if not duration or duration <= 0:
        if days < 40: return "seedling"
        if days < 80: return "vegetative"
        if days < 120: return "flowering"
        if days < 160: return "ripening"
        return "harvest"
    fraction = days / duration
    if fraction < 0.15: return "seedling"
    if fraction < 0.45: return "vegetative"
    if fraction < 0.70: return "flowering"
    if fraction <= 1.0: return "ripening"
    return "harvest"


_STAGE_TASKS = {
    "seedling": [
        {"title": "Thin seedlings and check germination", "category": "Crop Care", "off": 3, "priority": "high",
         "desc_extra": "Remove weak seedlings so healthy plants get enough space and sunlight."},
    ],
    "vegetative": [
        {"title": "Apply nitrogen top dressing", "category": "Crop Care", "off": 7, "priority": "high",
         "desc_extra": "Split nitrogen in 2-3 doses for better growth during the vegetative stage."},
        {"title": "Weed the field", "category": "Farm Management", "off": 2, "priority": "medium",
         "desc_extra": "Weeds compete for water and nutrients. Remove them before they flower."},
        {"title": "Inspect irrigation lines and water the crop", "category": "Irrigation", "off": 1, "priority": "high",
         "desc_extra": "Check moisture in the soil and ensure the irrigation system is working."},
    ],
    "flowering": [
        {"title": "Irrigate during flowering stage", "category": "Irrigation", "off": 1, "priority": "high",
         "desc_extra": "Water stress at flowering directly reduces grain and fruit formation."},
        {"title": "Apply flowering-stage nutrients", "category": "Crop Care", "off": 5, "priority": "medium",
         "desc_extra": "A small balanced dose at flowering supports better filling of grains and fruits."},
        {"title": "Monitor pests and diseases", "category": "Pest & Disease", "off": 1, "priority": "high",
         "desc_extra": "Scout the field weekly and inspect under leaves for eggs, larvae or fungal spots."},
    ],
    "ripening": [
        {"title": "Reduce irrigation before harvest", "category": "Irrigation", "off": 4, "priority": "medium",
         "desc_extra": "Cut back water once grains/fruits start maturing to improve quality."},
        {"title": "Install bird scaring devices", "category": "Farm Management", "off": 2, "priority": "low",
         "desc_extra": "Protect the maturing crop from bird and animal damage near harvest."},
    ],
    "harvest": [
        {"title": "Harvest the mature crop", "category": "Harvesting", "off": 2, "priority": "high",
         "desc_extra": "Harvest at the right moisture level to get the best market price."},
        {"title": "Plan post-harvest drying and storage", "category": "Harvesting", "off": 6, "priority": "medium",
         "desc_extra": "Arrange drying shade and clean storage to avoid moisture and pest loss after harvest."},
    ],
}


def _mk_suggestion(title, category, off, priority, description, cycle, crop, source, reason, links=None):
    return {
        "crop_cycle_id": cycle.id,
        "title": title,
        "description": description,
        "category": category,
        "due_date": _date_from_today(off),
        "priority": priority,
        "source": source,
        "reason": reason,
        "crop_id": crop.id if crop else None,
        "crop_name": crop.name if crop else None,
        "farm_id": cycle.farm_id,
        "farm_name": cycle.farm.farm_name if cycle.farm else None,
        "plot_id": cycle.plot_id,
        "plot_name": cycle.plot.plot_name if cycle.plot else None,
        "links": links or {},
    }


def _stage_suggestions(cycle: CropCycle, crop: Crop, stage: str) -> list:
    out = []
    crop_name = crop.name if crop else "your crop"
    for tpl in _STAGE_TASKS.get(stage, _STAGE_TASKS["vegetative"]):
        title = tpl["title"]
        if "irrigation lines" in title:
            title = "Inspect irrigation and water the " + crop_name
        elif "top dressing" in title:
            title = "Apply nitrogen top dressing to " + crop_name
        elif "flowering-stage nutrients" in title:
            title = "Apply flowering-stage nutrients to " + crop_name
        elif "Monitoring" in title or tpl["title"].startswith("Monitor"):
            title = tpl["title"] + " on " + crop_name
        elif tpl["title"].startswith("Thin"):
            title = "Thin " + crop_name + " seedlings and check germination"
        elif tpl["title"].startswith("Reduce"):
            title = "Reduce irrigation to " + crop_name + " before harvest"
        elif tpl["title"].startswith("Install"):
            title = "Install bird scaring devices near " + crop_name
        elif tpl["title"].startswith("Weed"):
            title = "Weed the " + crop_name + " field"
        elif tpl["title"].startswith("Harvest"):
            title = "Harvest mature " + crop_name
        elif tpl["title"].startswith("Plan"):
            title = "Plan post-harvest drying and storage for " + crop_name
        description = (
            "AI suggestion for the " + stage.replace("_", " ") + " stage of " + crop_name + "."
            + " " + tpl["desc_extra"]
            + (" Plot: " + cycle.plot.plot_name if cycle.plot else "")
        )
        out.append(_mk_suggestion(
            title, tpl["category"], tpl["off"], tpl["priority"], description,
            cycle, crop, "crop_stage",
            "Based on the current growth stage of " + crop_name,
        ))
    return out


def _climate_suggestions(cycle: CropCycle, crop: Crop, weather: Optional[dict]) -> list:
    out = []
    if not weather:
        return out
    forecast = weather.get("forecast") or []
    today_rain = 0.0
    tomorrow_rain = 0.0
    highest_temp = float(weather.get("temperature") or 0)
    wind = float(weather.get("wind_speed") or 0)
    storm = False
    for i in range(min(2, len(forecast))):
        day = forecast[i]
        prec = float(day.get("precipitation") or 0)
        if i == 0:
            today_rain += prec
        else:
            tomorrow_rain += prec
    for day in forecast:
        if int(day.get("weather_code") or 0) >= 95 or "thunderstorm" in str(day.get("description") or "").lower():
            storm = True
        try:
            tmax = float(day.get("max_temp") or 0)
            if tmax > highest_temp:
                highest_temp = tmax
        except Exception:
            pass

    plot = cycle.plot.plot_name if cycle.plot else None
    if today_rain >= 3 or tomorrow_rain >= 3:
        out.append(_mk_suggestion(
            "Avoid fertilizer and pesticide application before rain" + (" (" + plot + ")" if plot else ""),
            "Pest & Disease", 0, "high",
            "Your 7-day forecast shows significant rain within the next 48 hours. "
            "Apply fertilizer or sprays only after the rain clears to avoid runoff and wastage.",
            cycle, crop, "climate",
            "Live weather forecast for your farm",
        ))
    if storm:
        out.append(_mk_suggestion(
            "Secure crop area before the thunderstorm" + (" (" + plot + ")" if plot else ""),
            "Farm Management", 0, "high",
            "Thunderstorm conditions are forecast. Clear drainage channels, secure covers "
            "and avoid working in the field during the storm.",
            cycle, crop, "climate",
            "Live weather forecast for your farm",
        ))
    if highest_temp >= 36 and today_rain < 1:
        out.append(_mk_suggestion(
            "Provide irrigation to prevent heat stress" + (" (" + plot + ")" if plot else ""),
            "Irrigation", 1, "high",
            "Temperatures are expected to reach {:.0f}°C with little rain. Irrigate early morning "
            "or evening to protect the crop from heat stress.".format(highest_temp),
            cycle, crop, "climate",
            "Live weather forecast for your farm",
        ))
    if wind >= 35:
        out.append(_mk_suggestion(
            "Delay spraying until the wind slows down" + (" (" + plot + ")" if plot else ""),
            "Pest & Disease", 0, "medium",
            "Wind speed is high. Spraying now would drift the chemical away and waste it. "
            "Wait for a calm window, ideally early morning.",
            cycle, crop, "climate",
            "Live weather forecast for your farm",
        ))
    return out


def _crop_health_suggestion(cycle: CropCycle, crop: Crop, stage: str) -> list:
    crop_name = crop.name if crop else "your crop"
    return [_mk_suggestion(
        "Run a crop health check on " + crop_name + (" (" + cycle.plot.plot_name + ")" if cycle.plot else ""),
        "Crop Care", 1, "medium",
        "Scan " + crop_name + " during the " + stage.replace("_", " ") + " stage for yellowing, spots, "
        "wilting or pest damage. Early detection saves the crop. Use the Crop Health tool for a quick check.",
        cycle, crop, "crop_health",
        "Regular crop health monitoring to catch problems early",
        links={"crop_health": "crop-health.html", "farm": "farm.html"},
    )]


@router.get("/crop-tasks/ai-suggest", response_model=dict)
def suggest_ai_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms = db.query(Farm).filter(Farm.user_id == current_user.id, Farm.is_active == True).all()
    farm_ids = [f.id for f in farms]
    if not farm_ids:
        return {"status": "success", "data": {"weather": None, "suggestions": []}}

    cycles = (
        db.query(CropCycle)
        .filter(CropCycle.farm_id.in_(farm_ids), CropCycle.status.notin_(["completed", "harvested"]))
        .all()
    )
    if not cycles:
        return {"status": "success", "data": {"weather": None, "suggestions": []}}

    from app.services.weather_service import get_current_weather

    existing_titles = {}
    pending = (
        db.query(CropTask)
        .join(CropCycle, CropTask.crop_cycle_id == CropCycle.id)
        .filter(CropCycle.farm_id.in_(farm_ids), CropTask.status.in_(["pending", "in_progress"]))
        .all()
    )
    for t in pending:
        existing_titles.setdefault(t.crop_cycle_id, set()).add(_norm_title(t.title))

    weather_cache = {}
    suggestions = []
    priority_order = {"high": 0, "medium": 1, "low": 2}

    for cycle in cycles:
        crop = cycle.crop
        farm = cycle.farm
        if not crop or not farm:
            continue
        plot = cycle.plot
        lat = (plot.latitude if plot and plot.latitude else None) or farm.latitude
        lon = (plot.longitude if plot and plot.longitude else None) or farm.longitude

        weather = None
        if lat and lon:
            wkey = (round(float(lat), 3), round(float(lon), 3))
            if wkey in weather_cache:
                weather = weather_cache[wkey]
            else:
                try:
                    weather = asyncio.run(get_current_weather(float(lat), float(lon)))
                except Exception:
                    weather = None
                weather_cache[wkey] = weather

        stage = _cycle_stage(cycle, crop)
        candidates = _stage_suggestions(cycle, crop, stage)
        candidates += _climate_suggestions(cycle, crop, weather)
        candidates += _crop_health_suggestion(cycle, crop, stage)

        for cand in candidates:
            key = _norm_title(cand["title"])
            if key in existing_titles.get(cycle.id, set()):
                continue
            existing_titles.setdefault(cycle.id, set()).add(key)
            suggestions.append(cand)

    suggestions.sort(key=lambda s: (priority_order.get(s["priority"], 3), s["due_date"]))

    weather_out = None
    wf = farms[0]
    lat0, lon0 = wf.latitude, wf.longitude
    if lat0 is None or lon0 is None:
        for cycle in cycles:
            p = cycle.plot
            if p and p.latitude and p.longitude:
                lat0, lon0 = p.latitude, p.longitude
                break
    wkey = None
    if lat0 is not None and lon0 is not None:
        wkey = (round(float(lat0), 3), round(float(lon0), 3))
    if wkey:
        weather_out = weather_cache.get(wkey)
        if weather_out is None:
            try:
                weather_out = asyncio.run(get_current_weather(float(lat0), float(lon0)))
            except Exception:
                weather_out = None
            weather_cache[wkey] = weather_out
        if weather_out:
            weather_out = dict(weather_out)
    if weather_out:
        weather_out["location"] = wf.district or wf.farm_name
        weather_out["soil_type"] = wf.soil_type

    return {
        "status": "success",
        "data": {"weather": weather_out, "suggestions": suggestions[:12]},
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

    if payload.plot_id:
        # Validate the plot belongs to one of the current user's farms
        owned_farm_ids = [
            row[0]
            for row in db.query(Farm.id).filter(Farm.user_id == current_user.id).all()
        ]
        plot = None
        if owned_farm_ids:
            plot = (
                db.query(FarmPlot)
                .filter(FarmPlot.id == payload.plot_id, FarmPlot.farm_id.in_(owned_farm_ids))
                .first()
            )
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")
        if payload.farm_id and plot.farm_id != farm.id:
            raise HTTPException(
                status_code=400, detail="Plot does not belong to the given farm"
            )

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
