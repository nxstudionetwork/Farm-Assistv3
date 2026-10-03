import json
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User, UserSettings
from app.models.farm import Farm, FarmPlot
from app.models.crop import Crop, CropCycle, CropTask, CropVariety, CultivationMethod
from app.models.finance import Expense
from app.models.hydroponics import (
    HydroponicUnit,
    HydroponicCrop,
    HydroponicWaterLog,
    HydroponicHealthRecord,
    HydroponicProductionRecord,
)
from app.utils.auth import get_current_user, generate_id
from app.utils.notification_helper import create_notification

router = APIRouter(prefix="/api/v1/hydroponics", tags=["Hydroponics"])

DEFAULT_PH_RANGE = (5.5, 6.5)
DEFAULT_EC_RANGE = (1.2, 2.5)

SYSTEMS = [
    {
        "id": "nft",
        "name": "Nutrient Film Technique (NFT)",
        "summary": "Thin nutrient film flows through shallow channels past the roots.",
        "best_for": "Leafy greens and herbs",
        "aeration": "low",
        "water_holding": "low",
        "suitable_crops": ["lettuce", "basil", "spinach", "mint", "coriander"],
    },
    {
        "id": "dwc",
        "name": "Deep Water Culture (DWC)",
        "summary": "Roots hang in an aerated nutrient reservoir.",
        "best_for": "Lettuce, leafy greens, herbs",
        "aeration": "high",
        "water_holding": "high",
        "suitable_crops": ["lettuce", "spinach", "basil", "pak choi", "mint"],
    },
    {
        "id": "ebb_flow",
        "name": "Ebb and Flow",
        "summary": "Tray floods and drains on a timer, reusing the same solution.",
        "best_for": "Mixed crops in trays",
        "aeration": "medium",
        "water_holding": "high",
        "suitable_crops": ["lettuce", "spinach", "pak choi", "strawberry", "herbs"],
    },
    {
        "id": "dutch_bucket",
        "name": "Dutch Bucket",
        "summary": "Media-filled buckets with drip irrigation and a drain line.",
        "best_for": "Vine crops and larger plants",
        "aeration": "medium",
        "water_holding": "high",
        "suitable_crops": ["tomato", "cucumber", "capsicum", "brinjal"],
    },
    {
        "id": "tower",
        "name": "Vertical Tower",
        "summary": "Stacked planting sites fed by a central reservoir.",
        "best_for": "Small spaces and terraces",
        "aeration": "medium",
        "water_holding": "medium",
        "suitable_crops": ["lettuce", "herbs", "spinach", "strawberry"],
    },
    {
        "id": "kratky",
        "name": "Kratky",
        "summary": "Passive non-circulating system, ideal for leaf crops.",
        "best_for": "Small home setups",
        "aeration": "low",
        "water_holding": "high",
        "suitable_crops": ["lettuce", "spinach", "pak choi", "herbs"],
    },
    {
        "id": "aeroponics",
        "name": "Aeroponics",
        "summary": "Roots misted in air, giving very high oxygen and water uptake.",
        "best_for": "Propagations and high-value crops",
        "aeration": "very high",
        "water_holding": "none",
        "suitable_crops": ["lettuce", "herbs", "strawberry", "tomato"],
    },
]

GROWTH_STAGES = [
    {
        "key": "germination",
        "label": "Germination",
        "day_from": 0,
        "day_to": 7,
        "focus": "Warm, humid and low light",
        "tasks": ["Check germination", "Maintain humidity", "Keep pH 5.8-6.2"],
    },
    {
        "key": "seedling",
        "label": "Seedling",
        "day_from": 8,
        "day_to": 21,
        "focus": "Root establishment and first true leaves",
        "tasks": ["Check pH and EC", "Introduce mild nutrients", "Thin seedlings"],
    },
    {
        "key": "vegetative",
        "label": "Vegetative growth",
        "day_from": 22,
        "day_to": 40,
        "focus": "Leaf and stem development",
        "tasks": ["Top up reservoir", "Check root colour", "Adjust EC weekly"],
    },
    {
        "key": "flowering",
        "label": "Flowering and fruiting",
        "day_from": 41,
        "day_to": 60,
        "focus": "Flower set and fruit development",
        "tasks": ["Review EC weekly", "Inspect for pests", "Balance nutrients"],
    },
    {
        "key": "harvest",
        "label": "Harvest",
        "day_from": 61,
        "day_to": 120,
        "focus": "Harvest at peak quality",
        "tasks": ["Harvest in cool hours", "Sanitise the system", "Reset for the next cycle"],
    },
]

#: Soilless nutrient targets are catalog data, not a hydroponics-owned crop list.
#: Every soilless crop is a normal :class:`Crop` carrying ``hydroponic_targets``
#: (seeded by :mod:`app.database.seed_crops`), so one crop record drives
#: hydroponics, tasks, crop health and the marketplace together. Crops without
#: targets fall back to :data:`DEFAULT_PH_RANGE` / :data:`DEFAULT_EC_RANGE`.
#: Resolved per request from the catalog by :func:`_crop_target`.

NUTRIENT_REFERENCE = [
    {
        "nutrient": "Nitrogen",
        "symptom": "Older leaves pale or yellow, stunted growth",
        "fix": "Raise the nitrogen component of the nutrient solution",
    },
    {
        "nutrient": "Phosphorus",
        "symptom": "Dark dull leaves, poor root development",
        "fix": "Add phosphate and confirm the root zone stays above 18 C",
    },
    {
        "nutrient": "Potassium",
        "symptom": "Brown scorched leaf edges, weak stems",
        "fix": "Increase potassium and re-check the EC after each change",
    },
    {
        "nutrient": "Calcium",
        "symptom": "Blossom end rot and tip burn on new growth",
        "fix": "Stabilise pH, keep the root zone cool and mix calcium separately",
    },
    {
        "nutrient": "Magnesium",
        "symptom": "Interveinal yellowing on older leaves",
        "fix": "Top up magnesium and verify the EC is not too high",
    },
    {
        "nutrient": "Iron",
        "symptom": "Yellowing of the youngest leaves",
        "fix": "Check pH is not above 6.5 and keep iron separate from phosphate",
    },
]

EQUIPMENT_CHECKLIST = [
    {"key": "reservoir", "label": "Nutrient reservoir with lid", "required_for": "all"},
    {"key": "pump", "label": "Circulation pump with timer", "required_for": ["nft", "ebb_flow", "dutch_bucket", "tower", "aeroponics"]},
    {"key": "air_pump", "label": "Air pump and air stone", "required_for": ["dwc", "aeroponics"]},
    {"key": "ph_meter", "label": "pH meter or pH strips", "required_for": "all"},
    {"key": "ec_meter", "label": "EC / TDS meter", "required_for": "all"},
    {"key": "channels", "label": "Net cups and channels or trays", "required_for": "all"},
    {"key": "medium", "label": "Growing medium (clay pebbles, coco, perlite)", "required_for": ["dutch_bucket", "ebb_flow", "tower"]},
    {"key": "lighting", "label": "Grow light or polyhouse shade net", "required_for": "all"},
    {"key": "thermometer", "label": "Water temperature thermometer", "required_for": "all"},
    {"key": "ph_down", "label": "pH down and pH up solutions", "required_for": "all"},
]

TASK_TEMPLATES = [
    {"key": "ph_ec", "title": "Check pH and EC", "category": "water", "interval_days": 2, "priority": "high"},
    {"key": "reservoir", "title": "Top up and stir the reservoir", "category": "water", "interval_days": 3, "priority": "medium"},
    {"key": "water_change", "title": "Change the nutrient solution", "category": "water", "interval_days": 14, "priority": "high"},
    {"key": "roots", "title": "Inspect root colour and smell", "category": "health", "interval_days": 7, "priority": "medium"},
    {"key": "pests", "title": "Scout plants for pests and disease", "category": "health", "interval_days": 7, "priority": "medium"},
    {"key": "clean", "title": "Clean channels, net cups and filters", "category": "maintenance", "interval_days": 21, "priority": "medium"},
    {"key": "harvest", "title": "Harvest ready crops", "category": "harvest", "interval_days": 0, "priority": "high"},
]

SETUP_CATEGORIES = [
    "Structure", "Reservoir", "Pipes and channels", "Pump and aeration",
    "Lighting", "Net cups and media", "Testing equipment", "Automation",
]
RUNNING_CATEGORIES = [
    "Seeds and seedlings", "Nutrients", "Growing media", "Electricity",
    "Water", "Labour", "Testing and consumables", "Repairs", "Other",
]


class HydroponicUnitCreate(BaseModel):
    name: str
    farm_id: str
    plot_id: Optional[str] = None
    system_type: Optional[str] = None
    status: Optional[str] = "planning"
    setup_location: Optional[str] = None
    setup_date: Optional[str] = None
    growing_area: Optional[float] = None
    area_unit: Optional[str] = "sq ft"
    channels: Optional[int] = None
    planting_sites: Optional[int] = None
    reservoir_capacity: Optional[float] = None
    reservoir_unit: Optional[str] = "Litres"
    water_source: Optional[str] = None
    pump_available: Optional[bool] = False
    air_pump_available: Optional[bool] = False
    lighting_setup: Optional[str] = None
    protection_structure: Optional[str] = None
    automation_available: Optional[bool] = False
    notes: Optional[str] = None


class HydroponicUnitUpdate(BaseModel):
    name: Optional[str] = None
    plot_id: Optional[str] = None
    system_type: Optional[str] = None
    status: Optional[str] = None
    setup_location: Optional[str] = None
    setup_date: Optional[str] = None
    growing_area: Optional[float] = None
    area_unit: Optional[str] = None
    channels: Optional[int] = None
    planting_sites: Optional[int] = None
    reservoir_capacity: Optional[float] = None
    reservoir_unit: Optional[str] = None
    water_source: Optional[str] = None
    pump_available: Optional[bool] = None
    air_pump_available: Optional[bool] = None
    lighting_setup: Optional[str] = None
    protection_structure: Optional[str] = None
    automation_available: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class HydroponicCropCreate(BaseModel):
    crop_name: str
    crop_id: Optional[str] = None
    variety: Optional[str] = None
    planting_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    plants_count: Optional[int] = None
    growing_area: Optional[float] = None
    area_unit: Optional[str] = "sq ft"
    expected_yield: Optional[float] = None
    yield_unit: Optional[str] = "kg"
    current_stage: Optional[str] = None
    notes: Optional[str] = None


class HydroponicCropUpdate(BaseModel):
    crop_name: Optional[str] = None
    variety: Optional[str] = None
    planting_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    actual_harvest_date: Optional[str] = None
    plants_count: Optional[int] = None
    growing_area: Optional[float] = None
    area_unit: Optional[str] = None
    expected_yield: Optional[float] = None
    yield_unit: Optional[str] = None
    actual_yield: Optional[float] = None
    current_stage: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class WaterLogCreate(BaseModel):
    recorded_date: Optional[str] = None
    water_quantity: Optional[float] = None
    water_unit: Optional[str] = "Litres"
    ph: Optional[float] = None
    ec: Optional[float] = None
    tds: Optional[float] = None
    water_temperature: Optional[float] = None
    nutrient_solution: Optional[str] = None
    nutrient_quantity: Optional[float] = None
    nutrient_unit: Optional[str] = "g"
    water_replaced: Optional[bool] = False
    notes: Optional[str] = None


class HealthRecordCreate(BaseModel):
    observed_date: Optional[str] = None
    hydroponic_crop_id: Optional[str] = None
    plant_appearance: Optional[str] = None
    leaf_condition: Optional[str] = None
    root_condition: Optional[str] = None
    growth_rate: Optional[str] = None
    deficiency_symptoms: Optional[str] = None
    pest_observation: Optional[str] = None
    water_condition: Optional[str] = None
    ph_issue: Optional[str] = None
    ec_issue: Optional[str] = None
    severity: Optional[str] = "low"
    status: Optional[str] = "observed"
    notes: Optional[str] = None


class ProductionCreate(BaseModel):
    hydroponic_crop_id: Optional[str] = None
    recorded_date: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = "kg"
    quality_grade: Optional[str] = None
    revenue: Optional[float] = None
    notes: Optional[str] = None


class CostCreate(BaseModel):
    cost_type: str = "running"
    category: str
    amount: float
    incurred_date: Optional[str] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None


class TaskGenerateRequest(BaseModel):
    interval_multiplier: Optional[float] = None
    include_all_templates: Optional[bool] = True


def _today() -> str:
    return date.today().isoformat()


def _add_days(base: Optional[str], days: int) -> str:
    if not base:
        base = _today()
    try:
        parsed = datetime.strptime(base[:10], "%Y-%m-%d").date()
    except ValueError:
        parsed = date.today()
    return (parsed + timedelta(days=days)).isoformat()


def _parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _csv_to_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _list_to_csv(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    parts = [str(part).strip() for part in value if str(part).strip()]
    return ", ".join(parts) if parts else None


def _farm_or_404(db: Session, farm_id: str, user_id: str) -> Farm:
    # Farms are addressed by their public FA-FARM id everywhere in the UI, but
    # older callers may still send the internal uuid, so accept both.
    farm = db.query(Farm).filter(
        or_(Farm.id == farm_id, Farm.farm_id == farm_id),
        Farm.user_id == user_id,
    ).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


def _farm_scope_filter(db: Session, farm_id: str, user_id: str):
    """Return the ``Farm`` for a caller-supplied id, or ``None`` when unknown.

    List endpoints take an optional ``farm_id`` that may be the public
    ``FA-FARM-*`` id or the internal uuid. Resolving it here means a bad id
    simply matches nothing instead of leaking a 404 from a list route, and the
    ownership check still runs.
    """
    if not farm_id:
        return None
    return db.query(Farm).filter(
        or_(Farm.id == farm_id, Farm.farm_id == farm_id),
        Farm.user_id == user_id,
    ).first()


def _unit_or_404(db: Session, unit_id: str, user_id: str) -> HydroponicUnit:
    unit = db.query(HydroponicUnit).filter(
        HydroponicUnit.unit_id == unit_id,
        HydroponicUnit.user_id == user_id,
    ).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Hydroponic unit not found")
    return unit


def _crop_or_404(db: Session, cycle_id: str, user_id: str) -> HydroponicCrop:
    crop = db.query(HydroponicCrop).filter(
        HydroponicCrop.cycle_id == cycle_id,
        HydroponicCrop.user_id == user_id,
    ).first()
    if not crop:
        raise HTTPException(status_code=404, detail="Hydroponic crop cycle not found")
    return crop


def _child_or_404(db: Session, model, id_field: str, public_id: str, user_id: str):
    record = db.query(model).filter(
        getattr(model, id_field) == public_id,
        model.user_id == user_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


def _unit_map(db: Session, unit_ids: List[str]) -> dict:
    if not unit_ids:
        return {}
    rows = db.query(HydroponicUnit.id, HydroponicUnit.unit_id, HydroponicUnit.name).filter(
        HydroponicUnit.id.in_(unit_ids)
    ).all()
    return {row[0]: {"unit_id": row[1], "name": row[2]} for row in rows}


def _crop_map(db: Session, crop_ids: List[str]) -> dict:
    if not crop_ids:
        return {}
    rows = (
        db.query(Crop.id, Crop.name, Crop.variety, Crop.lifecycle_stages, Crop.growth_duration_days)
        .filter(Crop.id.in_(crop_ids))
        .all()
    )
    return {
        row[0]: {
            "name": row[1],
            "variety": row[2],
            "lifecycle_stages": row[3] or [],
            "growth_duration_days": row[4],
        }
        for row in rows
    }


def _ensure_crop_catalog(db: Session) -> None:
    """Make sure the shared crop catalog is present before reading from it.

    The soilless targets live on :class:`Crop` rows, so a database whose crops
    were never seeded has nothing to report. ``seed_crops`` is idempotent and
    only re-runs when the catalog is actually empty, matching how
    ``/services`` re-seeds its own catalog on read.
    """
    from app.database.seed_crops import seed_crops

    if db.query(Crop.id).first() is None:
        seed_crops(db)


def _crop_target(db: Session, crop_name: Optional[str]) -> dict:
    """Soilless nutrient targets for a crop name, read from the catalog.

    Falls back to the linked :class:`Crop` row via a case-insensitive name match,
    then to an empty dict so callers can apply the generic default ranges. No
    hydroponics-owned crop list exists.
    """
    name = str(crop_name or "").strip()
    if not name:
        return {}
    _ensure_crop_catalog(db)
    crop = (
        db.query(Crop)
        .filter(func.lower(Crop.name) == name.lower())
        .order_by(Crop.is_catalog.desc())
        .first()
    )
    if crop is None or not crop.hydroponic_targets:
        return {}
    targets = crop.hydroponic_targets
    if isinstance(targets, str):
        try:
            targets = json.loads(targets)
        except ValueError:
            return {}
    return targets if isinstance(targets, dict) else {}


def _expected_range(db: Session, crop_name: Optional[str], key: str):
    target = _crop_target(db, crop_name)
    value = target.get(key)
    if value and len(value) == 2:
        return tuple(value)
    return DEFAULT_PH_RANGE if key == "ph" else DEFAULT_EC_RANGE


def _unit_range_alerts(db: Session, unit: HydroponicUnit) -> dict:
    latest = db.query(HydroponicWaterLog).filter(
        HydroponicWaterLog.unit_id == unit.id
    ).order_by(HydroponicWaterLog.recorded_date.desc(), HydroponicWaterLog.created_at.desc()).first()

    active_crop = db.query(HydroponicCrop).filter(
        HydroponicCrop.unit_id == unit.id,
        HydroponicCrop.status == "active",
    ).order_by(HydroponicCrop.planting_date.desc()).first()

    crop_name = active_crop.crop_name if active_crop else None
    ph_min, ph_max = _expected_range(db, crop_name, "ph")
    ec_min, ec_max = _expected_range(db, crop_name, "ec")

    result = {
        "ph_min": ph_min,
        "ph_max": ph_max,
        "ec_min": ec_min,
        "ec_max": ec_max,
        "crop_name": crop_name,
        "last_logged": None,
        "ph": None,
        "ec": None,
        "ph_status": "unknown",
        "ec_status": "unknown",
        "severity": "normal",
        "messages": [],
    }
    if not latest:
        result["severity"] = "warning"
        result["messages"].append("No water log recorded yet for this unit")
        return result

    result["last_logged"] = latest.recorded_date or (
        latest.created_at.date().isoformat() if latest.created_at else None
    )
    result["ph"] = latest.ph
    result["ec"] = latest.ec

    if latest.ph is not None:
        if latest.ph < ph_min or latest.ph > ph_max:
            result["ph_status"] = "alert"
            result["messages"].append(
                f"pH {latest.ph} is outside the {ph_min}-{ph_max} range for {crop_name or 'this crop'}"
            )
        else:
            result["ph_status"] = "ok"

    if latest.ec is not None:
        if latest.ec < ec_min or latest.ec > ec_max:
            result["ec_status"] = "alert"
            result["messages"].append(
                f"EC {latest.ec} is outside the {ec_min}-{ec_max} range for {crop_name or 'this crop'}"
            )
        else:
            result["ec_status"] = "ok"

    logged = _parse_date(latest.recorded_date) or (latest.created_at.date() if latest.created_at else None)
    if logged:
        days = (date.today() - logged).days
        if days > 2:
            result["messages"].append(f"Water log is {days} days old")
            result["severity"] = "warning"

    if result["ph_status"] == "alert" or result["ec_status"] == "alert":
        result["severity"] = "critical"
    elif result["severity"] == "normal" and result["messages"]:
        result["severity"] = "warning"

    return result


def _economics(db: Session, unit: HydroponicUnit) -> dict:
    expenses = db.query(Expense).filter(
        Expense.hydroponic_unit_id == unit.id
    ).all()

    setup_total = 0.0
    running_total = 0.0
    setup_rows = []
    running_rows = []
    for expense in expenses:
        entry = {
            "expense_id": expense.expense_id,
            "category": expense.category,
            "amount": expense.amount,
            "incurred_date": expense.expense_date.date().isoformat()
            if expense.expense_date else None,
            "vendor": expense.vendor,
            "notes": expense.description,
        }
        if (expense.subcategory or "").endswith("_setup"):
            setup_total += expense.amount or 0
            setup_rows.append(entry)
        else:
            running_total += expense.amount or 0
            running_rows.append(entry)

    production = db.query(HydroponicProductionRecord).filter(
        HydroponicProductionRecord.unit_id == unit.id
    ).all()
    revenue_total = sum((p.revenue or 0) for p in production)
    quantity_total = sum((p.quantity or 0) for p in production)

    total_cost = setup_total + running_total
    net_profit = revenue_total - total_cost
    margin = (net_profit / revenue_total * 100) if revenue_total else None
    roi = (net_profit / total_cost * 100) if total_cost else None

    return {
        "unit_id": unit.unit_id,
        "currency": "INR",
        "setup_investment": round(setup_total, 2),
        "running_cost": round(running_total, 2),
        "total_cost": round(total_cost, 2),
        "revenue": round(revenue_total, 2),
        "net_profit": round(net_profit, 2),
        "profit_margin_percent": round(margin, 2) if margin is not None else None,
        "roi_percent": round(roi, 2) if roi is not None else None,
        "production_quantity": round(quantity_total, 2),
        "harvest_records": len(production),
        "setup_records": sorted(setup_rows, key=lambda r: (r["incurred_date"] or ""), reverse=True),
        "running_records": sorted(running_rows, key=lambda r: (r["incurred_date"] or ""), reverse=True),
    }


def _serialize_crop(db: Session, crop: HydroponicCrop) -> dict:
    info = _crop_map(db, [crop.crop_id]).get(crop.crop_id, {})
    farm = db.query(Farm).filter(Farm.id == crop.farm_id).first() if crop.farm_id else None
    unit = db.query(HydroponicUnit).filter(HydroponicUnit.id == crop.unit_id).first()
    target = _crop_target(db, crop.crop_name)
    linked = db.query(Crop).filter(Crop.id == crop.crop_id).first() if crop.crop_id else None

    # The crop's own lifecycle, so grapes, tomato and rice each show their real
    # stages instead of a single generic soilless list.
    stages = (linked.lifecycle_stages if linked else None) or list(
        stage["key"] for stage in GROWTH_STAGES
    )

    # Days to harvest comes from the recorded date when the farmer gave one,
    # otherwise from the crop's own cycle length.
    harvest_in_days = None
    planted = _parse_date(crop.planting_date)
    recorded_harvest = _parse_date(crop.expected_harvest_date)
    duration = (
        target.get("days")
        or (linked.growth_duration_days if linked else None)
    )
    if recorded_harvest:
        harvest_in_days = (recorded_harvest - date.today()).days
    elif planted and duration:
        harvest_in_days = (planted + timedelta(days=int(duration)) - date.today()).days

    return {
        "cycle_id": crop.cycle_id,
        "crop_cycle_id": crop.crop_cycle_id,
        "unit_id": unit.unit_id if unit else None,
        "farm_id": farm.farm_id if farm else None,
        "crop_name": crop.crop_name,
        "variety": crop.variety,
        "crop_reference": info.get("name"),
        "planting_date": crop.planting_date,
        "expected_harvest_date": crop.expected_harvest_date,
        "actual_harvest_date": crop.actual_harvest_date,
        "plants_count": crop.plants_count,
        "growing_area": crop.growing_area,
        "area_unit": crop.area_unit,
        "expected_yield": crop.expected_yield,
        "actual_yield": crop.actual_yield,
        "yield_unit": crop.yield_unit,
        "current_stage": crop.current_stage,
        "lifecycle_stages": stages,
        "status": crop.status,
        "notes": crop.notes,
        "created_at": str(crop.created_at) if crop.created_at else None,
        "target_ph": list(_expected_range(db, crop.crop_name, "ph")),
        "target_ec": list(_expected_range(db, crop.crop_name, "ec")),
        "estimated_harvest_in_days": harvest_in_days,
    }


def _serialize_unit(db: Session, unit: HydroponicUnit, detail: bool = False) -> dict:
    farm = db.query(Farm).filter(Farm.id == unit.farm_id).first()
    plot = db.query(FarmPlot).filter(FarmPlot.id == unit.plot_id).first() if unit.plot_id else None

    crops = db.query(HydroponicCrop).filter(HydroponicCrop.unit_id == unit.id).order_by(
        HydroponicCrop.planting_date.desc()
    ).all()
    crop_ids = [c.crop_id for c in crops if c.crop_id]
    catalogue = _crop_map(db, crop_ids)

    crop_rows = [_serialize_crop(db, crop) for crop in crops]

    water_logs = db.query(HydroponicWaterLog).filter(
        HydroponicWaterLog.unit_id == unit.id
    ).order_by(
        HydroponicWaterLog.recorded_date.desc(), HydroponicWaterLog.created_at.desc()
    ).all()
    health = db.query(HydroponicHealthRecord).filter(
        HydroponicHealthRecord.unit_id == unit.id
    ).order_by(
        HydroponicHealthRecord.observed_date.desc(), HydroponicHealthRecord.created_at.desc()
    ).all()
    production = db.query(HydroponicProductionRecord).filter(
        HydroponicProductionRecord.unit_id == unit.id
    ).order_by(
        HydroponicProductionRecord.recorded_date.desc(),
        HydroponicProductionRecord.created_at.desc(),
    ).all()

    active_crops = [c for c in crop_rows if c["status"] == "active"]
    upcoming = [
        c for c in active_crops
        if c["estimated_harvest_in_days"] is not None and 0 <= c["estimated_harvest_in_days"] <= 30
    ]

    payload = {
        "unit_id": unit.unit_id,
        "name": unit.name,
        # The public FA-FARM id, because that is what every other endpoint and
        # the whole UI address farms by.
        "farm_id": farm.farm_id if farm else None,
        "farm_name": farm.farm_name if farm else None,
        "plot_id": unit.plot_id,
        "plot_name": plot.plot_name if plot else None,
        "system_type": unit.system_type,
        "status": unit.status,
        "setup_location": unit.setup_location,
        "setup_date": unit.setup_date,
        "growing_area": unit.growing_area,
        "area_unit": unit.area_unit,
        "channels": unit.channels,
        "planting_sites": unit.planting_sites,
        "reservoir_capacity": unit.reservoir_capacity,
        "reservoir_unit": unit.reservoir_unit,
        "water_source": unit.water_source,
        "pump_available": unit.pump_available,
        "air_pump_available": unit.air_pump_available,
        "lighting_setup": unit.lighting_setup,
        "protection_structure": unit.protection_structure,
        "automation_available": unit.automation_available,
        "is_active": unit.is_active,
        "notes": unit.notes,
        "created_at": str(unit.created_at) if unit.created_at else None,
        "updated_at": str(unit.updated_at) if unit.updated_at else None,
        "crop_count": len(crop_rows),
        "active_crop_count": len(active_crops),
        "water_log_count": len(water_logs),
        "health_record_count": len(health),
        "production_record_count": len(production),
        "water_status": _unit_range_alerts(db, unit),
        "economics": _economics(db, unit),
    }

    if detail:
        payload["crops"] = crop_rows
        payload["water_logs"] = [
            {
                "log_id": w.log_id,
                "recorded_date": w.recorded_date,
                "water_quantity": w.water_quantity,
                "water_unit": w.water_unit,
                "ph": w.ph,
                "ec": w.ec,
                "tds": w.tds,
                "water_temperature": w.water_temperature,
                "nutrient_solution": w.nutrient_solution,
                "nutrient_quantity": w.nutrient_quantity,
                "nutrient_unit": w.nutrient_unit,
                "water_replaced": w.water_replaced,
                "notes": w.notes,
                "created_at": str(w.created_at) if w.created_at else None,
            }
            for w in water_logs
        ]
        payload["health_records"] = [
            {
                "record_id": h.record_id,
                "observed_date": h.observed_date,
                "hydroponic_crop_id": h.hydroponic_crop_id,
                "plant_appearance": h.plant_appearance,
                "leaf_condition": h.leaf_condition,
                "root_condition": h.root_condition,
                "growth_rate": h.growth_rate,
                "deficiency_symptoms": h.deficiency_symptoms,
                "pest_observation": h.pest_observation,
                "water_condition": h.water_condition,
                "ph_issue": h.ph_issue,
                "ec_issue": h.ec_issue,
                "severity": h.severity,
                "status": h.status,
                "notes": h.notes,
                "created_at": str(h.created_at) if h.created_at else None,
            }
            for h in health
        ]
        payload["production_records"] = [
            {
                "production_id": p.production_id,
                "hydroponic_crop_id": p.hydroponic_crop_id,
                "recorded_date": p.recorded_date,
                "quantity": p.quantity,
                "unit": p.quantity_unit,
                "quality_grade": p.quality_grade,
                "revenue": p.revenue,
                "notes": p.notes,
                "created_at": str(p.created_at) if p.created_at else None,
            }
            for p in production
        ]
        payload["tasks"] = _unit_tasks(db, unit)
        payload["upcoming_harvests"] = upcoming

    return payload


def _unit_tasks(db: Session, unit: HydroponicUnit) -> List[dict]:
    cycle_ids = [
        row[0]
        for row in db.query(HydroponicCrop.crop_cycle_id)
        .filter(HydroponicCrop.unit_id == unit.id, HydroponicCrop.crop_cycle_id.isnot(None))
        .all()
    ]
    if not cycle_ids:
        return []
    tasks = db.query(CropTask).filter(CropTask.crop_cycle_id.in_(cycle_ids)).all()
    cycle_to_hydro = {
        row[0]: row[1]
        for row in db.query(HydroponicCrop.crop_cycle_id, HydroponicCrop.cycle_id)
        .filter(HydroponicCrop.unit_id == unit.id, HydroponicCrop.crop_cycle_id.isnot(None))
        .all()
    }
    # CropCycle ids are internal uuids, so publish the task's own public id.
    public_cycle = {row.id: row.cycle_id for row in db.query(CropCycle).filter(CropCycle.id.in_(cycle_ids)).all()}
    unit_public = unit.unit_id
    return [
        {
            "task_id": t.task_id,
            "title": t.title,
            "description": t.description,
            "category": t.category,
            "due_date": t.due_date,
            "status": t.status,
            "priority": t.priority,
            "source": t.source,
            "growth_stage": t.growth_stage,
            "crop_cycle_id": public_cycle.get(t.crop_cycle_id),
            "hydroponic_cycle_id": cycle_to_hydro.get(t.crop_cycle_id),
            "unit_id": unit_public,
        }
        for t in sorted(tasks, key=lambda x: (x.due_date or "9999"))
    ]


def _settings_for(db: Session, user_id: str):
    return db.query(UserSettings).filter(UserSettings.user_id == user_id).first()


@router.get("/catalog", response_model=dict)
def get_catalog(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Every crop that supports soilless production, straight from the shared
    # crop catalog. The list grows automatically as the catalog grows.
    _ensure_crop_catalog(db)
    soilless = (
        db.query(Crop)
        .filter(
            Crop.is_archived.is_(False),
            Crop.hydroponic_targets.isnot(None),
        )
        .order_by(Crop.name)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "systems": SYSTEMS,
            "growth_stages": GROWTH_STAGES,
            "crop_targets": [
                {
                    "crop": crop.name,
                    "crop_id": crop.id,
                    "category_code": crop.category_ref.code if crop.category_ref else None,
                    "ph_min": target["ph"][0],
                    "ph_max": target["ph"][1],
                    "ec_min": target["ec"][0],
                    "ec_max": target["ec"][1],
                    "days": target.get("days"),
                    "category": target.get("group"),
                }
                for crop in soilless
                for target in [crop.hydroponic_targets or {}]
                if len(target.get("ph") or ()) == 2 and len(target.get("ec") or ()) == 2
            ],
            "nutrient_reference": NUTRIENT_REFERENCE,
            "equipment_checklist": EQUIPMENT_CHECKLIST,
            "task_templates": TASK_TEMPLATES,
            "setup_cost_categories": SETUP_CATEGORIES,
            "running_cost_categories": RUNNING_CATEGORIES,
        },
    }


@router.get("/dashboard", response_model=dict)
def get_dashboard(
    farm_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(HydroponicUnit).filter(HydroponicUnit.user_id == current_user.id)
    if farm_id:
        farm = _farm_or_404(db, farm_id, current_user.id)
        query = query.filter(HydroponicUnit.farm_id == farm.id)
    units = query.all()
    unit_ids = [u.id for u in units]

    if unit_ids:
        crops = db.query(HydroponicCrop).filter(
            HydroponicCrop.user_id == current_user.id,
            HydroponicCrop.unit_id.in_(unit_ids),
        ).all()
    else:
        crops = []

    active_crops = [c for c in crops if c.status == "active"]
    harvesting = []
    for crop in active_crops:
        target = _crop_target(db, crop.crop_name)
        harvest_date = _parse_date(crop.expected_harvest_date)
        if not harvest_date and crop.planting_date and target.get("days"):
            harvest_date = _parse_date(crop.planting_date) + timedelta(days=target["days"])
        if harvest_date:
            remaining = (harvest_date - date.today()).days
            if 0 <= remaining <= 30:
                harvesting.append({
                    "cycle_id": crop.cycle_id,
                    "crop_name": crop.crop_name,
                    "expected_harvest_date": harvest_date.isoformat(),
                    "days_remaining": remaining,
                    "unit_id": crop.unit_id,
                })

    economics = [_economics(db, u) for u in units]
    revenue = sum(e["revenue"] for e in economics)
    cost = sum(e["total_cost"] for e in economics)

    alerts = []
    for unit in units:
        water_status = _unit_range_alerts(db, unit)
        if water_status["severity"] in ("warning", "critical"):
            alerts.append({
                "unit_id": unit.unit_id,
                "unit_name": unit.name,
                "severity": water_status["severity"],
                "messages": water_status["messages"],
            })

    unit_map = {u.id: u.unit_id for u in units}
    for item in harvesting:
        item["unit_public_id"] = unit_map.get(item["unit_id"])

    return {
        "status": "success",
        "data": {
            "farm_id": farm_id,
            "total_units": len(units),
            "active_units": len([u for u in units if u.status == "active"]),
            "total_crops": len(crops),
            "active_crops": len(active_crops),
            "harvesting_soon": sorted(harvesting, key=lambda x: x["days_remaining"]),
            "total_revenue": round(revenue, 2),
            "total_cost": round(cost, 2),
            "net_profit": round(revenue - cost, 2),
            "alerts": alerts,
            "currency": "INR",
        },
    }


@router.get("/recommendations", response_model=dict)
def get_recommendations(
    unit_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings_row = _settings_for(db, current_user.id)
    if settings_row is not None and not (
        getattr(settings_row, "ai_recommendations", True) and getattr(settings_row, "perm_analytics", True)
    ):
        return {
            "status": "success",
            "data": {
                "enabled": False,
                "message": "Recommendations are turned off in your settings",
                "recommendations": [],
            },
        }

    query = db.query(HydroponicUnit).filter(HydroponicUnit.user_id == current_user.id)
    if unit_id:
        query = query.filter(HydroponicUnit.unit_id == unit_id)
    units = query.all()
    unit_public = {u.id: u.unit_id for u in units}

    recommendations = []

    if not units:
        recommendations.append({
            "id": "start-with-a-unit",
            "priority": "high",
            "title": "Set up your first hydroponic unit",
            "detail": "Choose a system that matches the crops you want to grow and the space you have.",
            "action": "Add unit",
            "action_url": "hydroponics.html?action=new-unit",
        })

    for unit in units:
        water_status = _unit_range_alerts(db, unit)
        ph_min, ph_max = water_status["ph_min"], water_status["ph_max"]
        ec_min, ec_max = water_status["ec_min"], water_status["ec_max"]

        if water_status["ph_status"] == "alert":
            direction = "raise" if (water_status["ph"] or 0) < ph_min else "lower"
            recommendations.append({
                "id": f"ph-{unit.unit_id}",
                "priority": "high",
                "unit_id": unit_public[unit.id],
                "title": f"Correct pH in {unit.name}",
                "detail": f"The last log recorded pH {water_status['ph']}. {direction.capitalize()} it towards {ph_min}-{ph_max} using pH up or pH down, then re-check after an hour.",
                "action": "Log water reading",
                "action_url": f"hydroponics.html?unit={unit_public[unit.id]}&action=water-log",
            })
        if water_status["ec_status"] == "alert":
            direction = "raise" if (water_status["ec"] or 0) < ec_min else "dilute"
            recommendations.append({
                "id": f"ec-{unit.unit_id}",
                "priority": "high",
                "unit_id": unit_public[unit.id],
                "title": f"Correct EC in {unit.name}",
                "detail": f"The last log recorded EC {water_status['ec']}. To {direction} it, aim for {ec_min}-{ec_max} and let the plants re-balance before the next feed.",
                "action": "Log water reading",
                "action_url": f"hydroponics.html?unit={unit_public[unit.id]}&action=water-log",
            })
        if water_status["last_logged"] is None:
            recommendations.append({
                "id": f"first-log-{unit.unit_id}",
                "priority": "medium",
                "unit_id": unit_public[unit.id],
                "title": f"Start water logs for {unit.name}",
                "detail": "Record pH and EC at least every two days so the system can flag problems for you.",
                "action": "Log water reading",
                "action_url": f"hydroponics.html?unit={unit_public[unit.id]}&action=water-log",
            })

        if unit.system_type:
            system = next((s for s in SYSTEMS if s["id"] == unit.system_type), None)
            if system and system["aeration"] in ("high", "very high") and not unit.air_pump_available:
                recommendations.append({
                    "id": f"air-{unit.unit_id}",
                    "priority": "high",
                    "unit_id": unit_public[unit.id],
                    "title": f"Add aeration to {unit.name}",
                    "detail": f"{system['name']} needs constant air at the root zone. Without an air pump, roots suffocate and the system fouls quickly.",
                    "action": "View equipment list",
                    "action_url": "hydroponics.html?tab=guide",
                })

        active = db.query(HydroponicCrop).filter(
            HydroponicCrop.unit_id == unit.id,
            HydroponicCrop.status == "active",
        ).all()
        if not active and unit.status == "active":
            recommendations.append({
                "id": f"plant-{unit.unit_id}",
                "priority": "medium",
                "unit_id": unit_public[unit.id],
                "title": f"Start a crop in {unit.name}",
                "detail": "An active unit without a crop cycle cannot show production or profit.",
                "action": "Add crop",
                "action_url": f"hydroponics.html?unit={unit_public[unit.id]}&action=new-crop",
            })

    for unit in units:
        for crop in db.query(HydroponicCrop).filter(
            HydroponicCrop.unit_id == unit.id,
            HydroponicCrop.status == "active",
        ).all():
            target = _crop_target(db, crop.crop_name)
            harvest = _parse_date(crop.expected_harvest_date)
            if not harvest and crop.planting_date and target.get("days"):
                harvest = _parse_date(crop.planting_date) + timedelta(days=target["days"])
            if harvest:
                remaining = (harvest - date.today()).days
                if 0 <= remaining <= 10:
                    recommendations.append({
                        "id": f"harvest-{crop.cycle_id}",
                        "priority": "high",
                        "unit_id": unit_public[unit.id],
                        "title": f"{crop.crop_name} is ready in {remaining} days",
                        "detail": "Prepare net pots and crates, and record the harvest so the profit calculator picks it up.",
                        "action": "Record harvest",
                        "action_url": f"hydroponics.html?unit={unit_public[unit.id]}&action=production",
                    })

    location_allowed = (
        settings_row.privacy_location if settings_row is not None else True
    )
    order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: order.get(r["priority"], 3))

    return {
        "status": "success",
        "data": {
            "enabled": True,
            "recommendations": recommendations,
            "location_services_available": False,
            "location_services_message": (
                "Nearby hydroponic suppliers and installers are not available in Farm Assist yet. "
                "Equipment needs appear in the Input Store."
            ),
            "location_sharing_enabled": bool(location_allowed),
        },
    }


@router.get("/units", response_model=dict)
def list_units(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    farm_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(HydroponicUnit).filter(HydroponicUnit.user_id == current_user.id)
    if farm_id:
        farm = _farm_scope_filter(db, farm_id, current_user.id)
        query = query.filter(HydroponicUnit.farm_id == (farm.id if farm else None))
    if status_filter:
        query = query.filter(HydroponicUnit.status == status_filter)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                HydroponicUnit.name.ilike(like),
                HydroponicUnit.setup_location.ilike(like),
                HydroponicUnit.system_type.ilike(like),
            )
        )

    total = query.count()
    rows = query.order_by(HydroponicUnit.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    units = [_serialize_unit(db, unit) for unit in rows]

    return {
        "status": "success",
        "data": units,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
        },
    }


@router.post("/units", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_unit(
    payload: HydroponicUnitCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm = _farm_or_404(db, payload.farm_id, current_user.id)

    plot = None
    if payload.plot_id:
        plot = db.query(FarmPlot).filter(
            FarmPlot.id == payload.plot_id,
            FarmPlot.farm_id == farm.id,
        ).first()
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found in this farm")

    unit = HydroponicUnit(
        unit_id=generate_id("FA-HYD", db, HydroponicUnit),
        user_id=current_user.id,
        farm_id=farm.id,
        plot_id=plot.id if plot else None,
        name=payload.name.strip(),
        system_type=payload.system_type,
        status=payload.status or "planning",
        setup_location=payload.setup_location,
        setup_date=payload.setup_date,
        growing_area=payload.growing_area,
        area_unit=payload.area_unit or "sq ft",
        channels=payload.channels,
        planting_sites=payload.planting_sites,
        reservoir_capacity=payload.reservoir_capacity,
        reservoir_unit=payload.reservoir_unit or "Litres",
        water_source=payload.water_source,
        pump_available=bool(payload.pump_available),
        air_pump_available=bool(payload.air_pump_available),
        lighting_setup=payload.lighting_setup,
        protection_structure=payload.protection_structure,
        automation_available=bool(payload.automation_available),
        notes=payload.notes,
    )
    db.add(unit)
    db.commit()
    db.refresh(unit)

    create_notification(
        db,
        current_user.id,
        "Hydroponic unit added",
        f"{unit.name} was added to {farm.farm_name}.",
        notification_type="hydroponics",
        reference_id=unit.unit_id,
        reference_type="hydroponic_unit",
        icon="fa-seedling",
        action_url=f"hydroponics.html?unit={unit.unit_id}",
    )
    db.commit()

    return {
        "status": "success",
        "message": "Hydroponic unit created successfully",
        "data": _serialize_unit(db, unit, detail=True),
    }


@router.get("/units/{unit_id}", response_model=dict)
def get_unit(
    unit_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)
    return {"status": "success", "data": _serialize_unit(db, unit, detail=True)}


@router.put("/units/{unit_id}", response_model=dict)
def update_unit(
    unit_id: str,
    payload: HydroponicUnitUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)

    if payload.plot_id is not None:
        if payload.plot_id == "":
            unit.plot_id = None
        else:
            plot = db.query(FarmPlot).filter(
                FarmPlot.id == payload.plot_id, FarmPlot.farm_id == unit.farm_id
            ).first()
            if not plot:
                raise HTTPException(status_code=404, detail="Plot not found in this farm")
            unit.plot_id = plot.id

    for field in (
        "name", "system_type", "status", "setup_location", "setup_date",
        "growing_area", "area_unit", "channels", "planting_sites",
        "reservoir_capacity", "reservoir_unit", "water_source",
        "pump_available", "air_pump_available", "lighting_setup",
        "protection_structure", "automation_available", "is_active", "notes",
    ):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(unit, field, value)

    db.commit()
    db.refresh(unit)

    return {
        "status": "success",
        "message": "Hydroponic unit updated successfully",
        "data": _serialize_unit(db, unit, detail=True),
    }


@router.post("/units/{unit_id}/archive", response_model=dict)
def archive_unit(
    unit_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retire a unit without losing its logs, harvests or costs.

    Archiving is the default because a unit's history is the evidence behind its
    profit numbers; deleting a unit is a separate, explicit action.
    """
    unit = _unit_or_404(db, unit_id, current_user.id)
    unit.is_active = False
    unit.status = "inactive"
    db.commit()

    return {
        "status": "success",
        "message": "Hydroponic unit archived successfully",
        "data": _serialize_unit(db, unit),
    }


@router.delete("/units/{unit_id}", response_model=dict)
def delete_unit(
    unit_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)

    # The shared catalog Crops survive; only this unit's own records go.
    cycles = [
        row[0]
        for row in db.query(HydroponicCrop.crop_cycle_id)
        .filter(
            HydroponicCrop.unit_id == unit.id,
            HydroponicCrop.crop_cycle_id.isnot(None),
        )
        .all()
    ]
    if cycles:
        db.query(CropTask).filter(CropTask.crop_cycle_id.in_(cycles)).delete()
        db.query(CropCycle).filter(CropCycle.id.in_(cycles)).delete()

    db.query(HydroponicProductionRecord).filter(
        HydroponicProductionRecord.unit_id == unit.id
    ).delete()
    db.query(HydroponicHealthRecord).filter(
        HydroponicHealthRecord.unit_id == unit.id
    ).delete()
    db.query(HydroponicWaterLog).filter(HydroponicWaterLog.unit_id == unit.id).delete()
    db.query(HydroponicCrop).filter(HydroponicCrop.unit_id == unit.id).delete()
    # Costs stay in the finance ledger but lose the link to a unit that is gone.
    db.query(Expense).filter(Expense.hydroponic_unit_id == unit.id).update(
        {Expense.hydroponic_unit_id: None}, synchronize_session=False
    )
    db.delete(unit)
    db.commit()

    return {"status": "success", "message": "Hydroponic unit deleted successfully"}


@router.get("/crops", response_model=dict)
def list_crops(
    unit_id: Optional[str] = None,
    farm_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(HydroponicCrop).filter(HydroponicCrop.user_id == current_user.id)
    if unit_id:
        unit = _unit_or_404(db, unit_id, current_user.id)
        query = query.filter(HydroponicCrop.unit_id == unit.id)
    if farm_id:
        farm = _farm_scope_filter(db, farm_id, current_user.id)
        if not farm:
            return {"status": "success", "data": []}
        farm_unit_ids = [
            row[0]
            for row in db.query(HydroponicUnit.id)
            .filter(
                HydroponicUnit.user_id == current_user.id,
                HydroponicUnit.farm_id == farm.id,
            )
            .all()
        ]
        if not farm_unit_ids:
            return {"status": "success", "data": []}
        query = query.filter(HydroponicCrop.unit_id.in_(farm_unit_ids))
    if status_filter:
        query = query.filter(HydroponicCrop.status == status_filter)
    rows = query.order_by(HydroponicCrop.planting_date.desc()).all()
    units = _unit_map(db, [r.unit_id for r in rows])

    return {
        "status": "success",
        "data": [
            dict(_serialize_crop(db, crop), unit=units.get(crop.unit_id))
            for crop in rows
        ],
    }


@router.post("/units/{unit_id}/crops", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_crop(
    unit_id: str,
    payload: HydroponicCropCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)
    crop_name = (payload.crop_name or "").strip()
    if not crop_name and not payload.crop_id:
        raise HTTPException(status_code=422, detail="crop_name or crop_id is required")

    # Reuse the shared catalog crop whenever one matches. A new Crop is only
    # created for a genuinely unknown crop, and even then it is classified with
    # the hydroponic cultivation method and a real lifecycle so downstream
    # modules treat it like any other crop.
    # The catalog has to exist before the lookup below, otherwise a named crop
    # like "Tomato" would not be found and a second, non-catalog row would be
    # created next to the catalogued one.
    _ensure_crop_catalog(db)
    crop = None
    if payload.crop_id:
        crop = db.query(Crop).filter(Crop.id == payload.crop_id).first()
        if not crop:
            raise HTTPException(status_code=404, detail="Crop not found")
    if crop is None and crop_name:
        crop = (
            db.query(Crop)
            .filter(func.lower(Crop.name) == crop_name.lower())
            .order_by(Crop.is_catalog.desc())
            .first()
        )
    if crop is not None and not crop_name:
        crop_name = crop.name

    method = (
        db.query(CultivationMethod)
        .filter(CultivationMethod.code == "hydroponic")
        .first()
    )

    if crop is None:
        target = _crop_target(db, crop_name)
        stages = ["Germination", "Vegetative growth", "Flowering and fruiting", "Harvest"]
        crop = Crop(
            crop_id=generate_id("FA-CRP", db, Crop),
            name=crop_name,
            variety=payload.variety,
            category="Hydroponic",
            growth_duration_days=target.get("days"),
            lifecycle_stages=stages,
            suitable_cultivation_methods=["hydroponic"],
            hydroponic_targets=target or None,
            is_catalog=False,
        )
        db.add(crop)
        db.flush()

    # Link a named variety to the crop so cycles stay normalised instead of
    # carrying an unresolvable free-text variety.
    variety_id = None
    if payload.variety:
        variety = (
            db.query(CropVariety)
            .filter(
                CropVariety.crop_id == crop.id,
                func.lower(CropVariety.name) == payload.variety.strip().lower(),
            )
            .first()
        )
        if variety is None:
            variety = CropVariety(
                crop_id=crop.id,
                name=payload.variety.strip(),
                duration_days=crop.growth_duration_days,
                is_custom=True,
            )
            db.add(variety)
            db.flush()
        variety_id = variety.id

    planting_date = payload.planting_date or _today()
    expected_harvest = payload.expected_harvest_date
    target = _crop_target(db, crop_name)
    if not expected_harvest:
        duration = crop.growth_duration_days or target.get("days")
        if duration:
            expected_harvest = _add_days(planting_date, int(duration))

    stages = crop.lifecycle_stages or []
    initial_stage = stages[0] if stages else "germination"

    cycle = CropCycle(
        cycle_id=generate_id("FA-CYC", db, CropCycle),
        farm_id=unit.farm_id,
        plot_id=unit.plot_id,
        crop_id=crop.id,
        variety_id=variety_id,
        cultivation_method_id=method.id if method else None,
        sowing_date=planting_date,
        expected_harvest_date=expected_harvest,
        yield_unit=payload.yield_unit or crop.production_unit or "kg",
        current_stage=initial_stage,
        notes=f"Hydroponic cycle in {unit.name}",
        status="active",
    )
    db.add(cycle)
    db.flush()

    hydroponic_crop = HydroponicCrop(
        cycle_id=generate_id("FA-HYC", db, HydroponicCrop),
        user_id=current_user.id,
        unit_id=unit.id,
        farm_id=unit.farm_id,
        plot_id=unit.plot_id,
        crop_cycle_id=cycle.id,
        crop_id=crop.id,
        crop_name=crop_name,
        variety=payload.variety or (crop.variety if crop else None),
        planting_date=planting_date,
        expected_harvest_date=expected_harvest,
        plants_count=payload.plants_count,
        growing_area=payload.growing_area,
        area_unit=payload.area_unit or "sq ft",
        expected_yield=payload.expected_yield,
        yield_unit=payload.yield_unit or crop.production_unit or "kg",
        current_stage=payload.current_stage or initial_stage,
        status="active",
        notes=payload.notes,
    )
    db.add(hydroponic_crop)
    db.commit()
    db.refresh(hydroponic_crop)

    return {
        "status": "success",
        "message": "Crop cycle started successfully",
        "data": _serialize_crop(db, hydroponic_crop),
    }


@router.put("/crops/{cycle_id}", response_model=dict)
def update_crop(
    cycle_id: str,
    payload: HydroponicCropUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crop = _crop_or_404(db, cycle_id, current_user.id)

    for field in (
        "crop_name", "variety", "planting_date", "expected_harvest_date",
        "actual_harvest_date", "plants_count", "growing_area", "area_unit",
        "expected_yield", "yield_unit", "actual_yield", "current_stage",
        "status", "notes",
    ):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(crop, field, value)

    if crop.crop_cycle_id:
        cycle = db.query(CropCycle).filter(CropCycle.id == crop.crop_cycle_id).first()
        if cycle:
            if crop.planting_date:
                cycle.sowing_date = crop.planting_date
            if crop.expected_harvest_date:
                cycle.expected_harvest_date = crop.expected_harvest_date
            if crop.actual_harvest_date:
                cycle.actual_harvest_date = crop.actual_harvest_date
            if crop.yield_unit:
                cycle.yield_unit = crop.yield_unit
            if crop.actual_yield is not None:
                cycle.yield_quantity = crop.actual_yield
            if crop.status:
                cycle.status = crop.status
            # Keep the stage in step with the crop's own lifecycle so the cycle
            # timeline stays valid when the crop changes.
            if crop.current_stage is not None:
                cycle.current_stage = crop.current_stage

    # Re-point the cycle when the farmer renames the hydroponic crop to one that
    # already exists in the catalog, instead of stranding the cycle on a
    # duplicate crop row.
    new_name = (crop.crop_name or "").strip()
    if new_name:
        linked = db.query(Crop).filter(Crop.id == crop.crop_id).first() if crop.crop_id else None
        if linked is None or linked.name.strip().lower() != new_name.lower():
            match = (
                db.query(Crop)
                .filter(func.lower(Crop.name) == new_name.lower())
                .order_by(Crop.is_catalog.desc())
                .first()
            )
            if match is not None:
                crop.crop_id = match.id
                crop.variety = crop.variety or match.variety
                if crop.crop_cycle_id:
                    cycle = db.query(CropCycle).filter(CropCycle.id == crop.crop_cycle_id).first()
                    if cycle:
                        cycle.crop_id = match.id

    db.commit()
    db.refresh(crop)

    return {
        "status": "success",
        "message": "Crop cycle updated successfully",
        "data": _serialize_crop(db, crop),
    }


@router.post("/crops/{cycle_id}/close", response_model=dict)
def finish_crop(
    cycle_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crop = _crop_or_404(db, cycle_id, current_user.id)
    crop.status = "completed"
    if not crop.actual_harvest_date:
        crop.actual_harvest_date = _today()
    if crop.crop_cycle_id:
        cycle = db.query(CropCycle).filter(CropCycle.id == crop.crop_cycle_id).first()
        if cycle:
            cycle.status = "completed"
            cycle.actual_harvest_date = crop.actual_harvest_date
    db.commit()

    return {
        "status": "success",
        "message": "Crop cycle closed successfully",
        "data": _serialize_crop(db, crop),
    }


@router.delete("/crops/{cycle_id}", response_model=dict)
def delete_crop(
    cycle_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crop = _crop_or_404(db, cycle_id, current_user.id)

    # The catalog Crop is shared, so only the cycle this module created goes.
    if crop.crop_cycle_id:
        cycle = db.query(CropCycle).filter(CropCycle.id == crop.crop_cycle_id).first()
        if cycle:
            db.query(CropTask).filter(CropTask.crop_cycle_id == cycle.id).delete()
            db.delete(cycle)
    db.delete(crop)
    db.commit()

    return {"status": "success", "message": "Crop cycle deleted successfully"}


@router.get("/units/{unit_id}/water-logs", response_model=dict)
def list_water_logs(
    unit_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)
    rows = db.query(HydroponicWaterLog).filter(
        HydroponicWaterLog.unit_id == unit.id
    ).order_by(
        HydroponicWaterLog.recorded_date.desc(), HydroponicWaterLog.created_at.desc()
    ).all()

    return {
        "status": "success",
        "data": [
            {
                "log_id": w.log_id,
                "recorded_date": w.recorded_date,
                "water_quantity": w.water_quantity,
                "water_unit": w.water_unit,
                "ph": w.ph,
                "ec": w.ec,
                "tds": w.tds,
                "water_temperature": w.water_temperature,
                "nutrient_solution": w.nutrient_solution,
                "nutrient_quantity": w.nutrient_quantity,
                "nutrient_unit": w.nutrient_unit,
                "water_replaced": w.water_replaced,
                "notes": w.notes,
                "created_at": str(w.created_at) if w.created_at else None,
            }
            for w in rows
        ],
    }


@router.post("/units/{unit_id}/water-logs", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_water_log(
    unit_id: str,
    payload: WaterLogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)

    log = HydroponicWaterLog(
        log_id=generate_id("FA-HWL", db, HydroponicWaterLog),
        user_id=current_user.id,
        unit_id=unit.id,
        recorded_date=payload.recorded_date or _today(),
        water_quantity=payload.water_quantity,
        water_unit=payload.water_unit or "Litres",
        ph=payload.ph,
        ec=payload.ec,
        tds=payload.tds,
        water_temperature=payload.water_temperature,
        nutrient_solution=payload.nutrient_solution,
        nutrient_quantity=payload.nutrient_quantity,
        nutrient_unit=payload.nutrient_unit or "g",
        water_replaced=bool(payload.water_replaced),
        notes=payload.notes,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    alerts = _unit_range_alerts(db, unit)
    if alerts["severity"] == "critical":
        create_notification(
            db,
            current_user.id,
            "Water reading out of range",
            f"{unit.name}: " + "; ".join(alerts["messages"]),
            notification_type="hydroponics",
            reference_id=unit.unit_id,
            reference_type="hydroponic_unit",
            icon="fa-droplet",
            action_url=f"hydroponics.html?unit={unit.unit_id}",
        )
        db.commit()

    return {
        "status": "success",
        "message": "Water log saved successfully",
        "data": {
            "log_id": log.log_id,
            "recorded_date": log.recorded_date,
            "ph": log.ph,
            "ec": log.ec,
            "tds": log.tds,
            "water_quantity": log.water_quantity,
            "water_unit": log.water_unit,
            "water_replaced": log.water_replaced,
            "alerts": alerts,
        },
    }


@router.delete("/water-logs/{log_id}", response_model=dict)
def delete_water_log(
    log_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log = _child_or_404(db, HydroponicWaterLog, "log_id", log_id, current_user.id)
    db.delete(log)
    db.commit()
    return {"status": "success", "message": "Water log deleted successfully"}


@router.get("/units/{unit_id}/health-records", response_model=dict)
def list_health_records(
    unit_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)
    rows = db.query(HydroponicHealthRecord).filter(
        HydroponicHealthRecord.unit_id == unit.id
    ).order_by(
        HydroponicHealthRecord.observed_date.desc(),
        HydroponicHealthRecord.created_at.desc(),
    ).all()
    cycles = {
        row[0]: row[1]
        for row in db.query(HydroponicCrop.id, HydroponicCrop.cycle_id)
        .filter(HydroponicCrop.unit_id == unit.id)
        .all()
    }

    return {
        "status": "success",
        "data": [
            {
                "record_id": h.record_id,
                "observed_date": h.observed_date,
                "hydroponic_crop_id": h.hydroponic_crop_id,
                "cycle_id": cycles.get(h.hydroponic_crop_id),
                "plant_appearance": h.plant_appearance,
                "leaf_condition": h.leaf_condition,
                "root_condition": h.root_condition,
                "growth_rate": h.growth_rate,
                "deficiency_symptoms": h.deficiency_symptoms,
                "pest_observation": h.pest_observation,
                "water_condition": h.water_condition,
                "ph_issue": h.ph_issue,
                "ec_issue": h.ec_issue,
                "severity": h.severity,
                "status": h.status,
                "notes": h.notes,
                "created_at": str(h.created_at) if h.created_at else None,
            }
            for h in rows
        ],
    }


@router.post("/units/{unit_id}/health-records", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_health_record(
    unit_id: str,
    payload: HealthRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)

    hydroponic_crop = None
    if payload.hydroponic_crop_id:
        hydroponic_crop = db.query(HydroponicCrop).filter(
            HydroponicCrop.cycle_id == payload.hydroponic_crop_id,
            HydroponicCrop.unit_id == unit.id,
            HydroponicCrop.user_id == current_user.id,
        ).first()
        if not hydroponic_crop:
            raise HTTPException(status_code=404, detail="Crop cycle not found in this unit")

    record = HydroponicHealthRecord(
        record_id=generate_id("FA-HHH", db, HydroponicHealthRecord),
        user_id=current_user.id,
        unit_id=unit.id,
        hydroponic_crop_id=hydroponic_crop.id if hydroponic_crop else None,
        crop_cycle_id=hydroponic_crop.crop_cycle_id if hydroponic_crop else None,
        crop_id=hydroponic_crop.crop_id if hydroponic_crop else None,
        observed_date=payload.observed_date or _today(),
        plant_appearance=payload.plant_appearance,
        leaf_condition=payload.leaf_condition,
        root_condition=payload.root_condition,
        growth_rate=payload.growth_rate,
        deficiency_symptoms=payload.deficiency_symptoms,
        pest_observation=payload.pest_observation,
        water_condition=payload.water_condition,
        ph_issue=payload.ph_issue,
        ec_issue=payload.ec_issue,
        severity=payload.severity or "low",
        status=payload.status or "observed",
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    if (record.severity or "low") in ("medium", "high"):
        create_notification(
            db,
            current_user.id,
            "Crop health observation",
            f"{unit.name}: {record.deficiency_symptoms or record.notes or 'health issue recorded'}",
            notification_type="hydroponics",
            reference_id=record.record_id,
            reference_type="hydroponic_health",
            icon="fa-leaf",
            action_url=f"hydroponics.html?unit={unit.unit_id}&tab=health",
        )
        db.commit()

    return {
        "status": "success",
        "message": "Health observation saved successfully",
        "data": {
            "record_id": record.record_id,
            "hydroponic_crop_id": record.hydroponic_crop_id,
            "cycle_id": record.crop.cycle_id if record.crop else None,
            "observed_date": record.observed_date,
            "plant_appearance": record.plant_appearance,
            "leaf_condition": record.leaf_condition,
            "root_condition": record.root_condition,
            "growth_rate": record.growth_rate,
            "deficiency_symptoms": record.deficiency_symptoms,
            "pest_observation": record.pest_observation,
            "water_condition": record.water_condition,
            "ph_issue": record.ph_issue,
            "ec_issue": record.ec_issue,
            "severity": record.severity,
            "status": record.status,
            "notes": record.notes,
            "created_at": str(record.created_at) if record.created_at else None,
        },
    }


@router.delete("/health-records/{record_id}", response_model=dict)
def delete_health_record(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = _child_or_404(db, HydroponicHealthRecord, "record_id", record_id, current_user.id)
    db.delete(record)
    db.commit()
    return {"status": "success", "message": "Health record deleted successfully"}


@router.get("/units/{unit_id}/production", response_model=dict)
def list_production(
    unit_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)
    rows = db.query(HydroponicProductionRecord).filter(
        HydroponicProductionRecord.unit_id == unit.id
    ).order_by(
        HydroponicProductionRecord.recorded_date.desc(),
        HydroponicProductionRecord.created_at.desc(),
    ).all()
    cycles = {
        row[0]: row[1]
        for row in db.query(HydroponicCrop.id, HydroponicCrop.cycle_id)
        .filter(HydroponicCrop.unit_id == unit.id)
        .all()
    }

    return {
        "status": "success",
        "data": [
            {
                "production_id": p.production_id,
                "hydroponic_crop_id": p.hydroponic_crop_id,
                "cycle_id": cycles.get(p.hydroponic_crop_id),
                "recorded_date": p.recorded_date,
                "quantity": p.quantity,
                "unit": p.quantity_unit,
                "quality_grade": p.quality_grade,
                "revenue": p.revenue,
                "notes": p.notes,
                "created_at": str(p.created_at) if p.created_at else None,
            }
            for p in rows
        ],
    }


@router.post("/units/{unit_id}/production", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_production(
    unit_id: str,
    payload: ProductionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)

    hydroponic_crop = None
    if payload.hydroponic_crop_id:
        hydroponic_crop = db.query(HydroponicCrop).filter(
            HydroponicCrop.cycle_id == payload.hydroponic_crop_id,
            HydroponicCrop.unit_id == unit.id,
            HydroponicCrop.user_id == current_user.id,
        ).first()
        if not hydroponic_crop:
            raise HTTPException(status_code=404, detail="Crop cycle not found in this unit")

    record = HydroponicProductionRecord(
        production_id=generate_id("FA-HPR", db, HydroponicProductionRecord),
        user_id=current_user.id,
        unit_id=unit.id,
        hydroponic_crop_id=hydroponic_crop.id if hydroponic_crop else None,
        crop_cycle_id=hydroponic_crop.crop_cycle_id if hydroponic_crop else None,
        recorded_date=payload.recorded_date or _today(),
        quantity=payload.quantity,
        quantity_unit=payload.unit or "kg",
        quality_grade=payload.quality_grade,
        revenue=payload.revenue,
        notes=payload.notes,
    )
    db.add(record)
    db.flush()

    if hydroponic_crop:
        totals = db.query(HydroponicProductionRecord).filter(
            HydroponicProductionRecord.hydroponic_crop_id == hydroponic_crop.id
        ).all()
        total_quantity = sum((t.quantity or 0) for t in totals)
        total_revenue = sum((t.revenue or 0) for t in totals)
        hydroponic_crop.actual_yield = total_quantity
        if hydroponic_crop.crop_cycle_id:
            cycle = db.query(CropCycle).filter(CropCycle.id == hydroponic_crop.crop_cycle_id).first()
            if cycle:
                cycle.yield_quantity = total_quantity
                cycle.revenue = total_revenue
                if not cycle.actual_harvest_date:
                    cycle.actual_harvest_date = record.recorded_date

    db.commit()
    db.refresh(record)

    return {
        "status": "success",
        "message": "Harvest recorded successfully",
        "data": {
            "production_id": record.production_id,
            "recorded_date": record.recorded_date,
            "quantity": record.quantity,
            "unit": record.quantity_unit,
            "revenue": record.revenue,
            "economics": _economics(db, unit),
        },
    }


@router.delete("/production/{production_id}", response_model=dict)
def delete_production(
    production_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = _child_or_404(
        db, HydroponicProductionRecord, "production_id", production_id, current_user.id
    )
    crop_id = record.hydroponic_crop_id
    db.delete(record)
    db.commit()

    if crop_id:
        crop = db.query(HydroponicCrop).filter(HydroponicCrop.id == crop_id).first()
        if crop and crop.crop_cycle_id:
            totals = db.query(HydroponicProductionRecord).filter(
                HydroponicProductionRecord.hydroponic_crop_id == crop_id
            ).all()
            crop.actual_yield = sum((t.quantity or 0) for t in totals)
            cycle = db.query(CropCycle).filter(CropCycle.id == crop.crop_cycle_id).first()
            if cycle:
                cycle.yield_quantity = crop.actual_yield
                cycle.revenue = sum((t.revenue or 0) for t in totals)
            db.commit()

    return {"status": "success", "message": "Harvest record deleted successfully"}


@router.get("/units/{unit_id}/costs", response_model=dict)
def list_costs(
    unit_id: str,
    cost_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)
    query = db.query(Expense).filter(Expense.hydroponic_unit_id == unit.id)
    if cost_type:
        query = query.filter(Expense.subcategory == f"hydroponics_{cost_type}")
    rows = query.order_by(Expense.expense_date.desc()).all()

    return {
        "status": "success",
        "data": [
            {
                "expense_id": e.expense_id,
                "cost_type": (e.subcategory or "hydroponics_running").replace("hydroponics_", ""),
                "category": e.category,
                "amount": e.amount,
                "incurred_date": e.expense_date.date().isoformat() if e.expense_date else None,
                "vendor": e.vendor,
                "notes": e.description,
            }
            for e in rows
        ],
        "economics": _economics(db, unit),
    }


@router.post("/units/{unit_id}/costs", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_cost(
    unit_id: str,
    payload: CostCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)

    if payload.cost_type not in ("setup", "running"):
        raise HTTPException(status_code=400, detail="cost_type must be setup or running")
    if payload.amount is None or payload.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be zero or greater")

    expense = Expense(
        expense_id=generate_id("FA-EXP", db, Expense),
        user_id=current_user.id,
        farm_id=unit.farm_id,
        category=payload.category,
        subcategory=f"hydroponics_{payload.cost_type}",
        amount=payload.amount,
        description=payload.notes,
        vendor=payload.vendor,
        hydroponic_unit_id=unit.id,
    )
    if payload.incurred_date:
        try:
            expense.expense_date = datetime.strptime(payload.incurred_date[:10], "%Y-%m-%d")
        except ValueError:
            expense.expense_date = datetime.utcnow()
    else:
        expense.expense_date = datetime.utcnow()

    db.add(expense)
    db.commit()
    db.refresh(expense)

    return {
        "status": "success",
        "message": "Cost recorded successfully",
        "data": {
            "expense_id": expense.expense_id,
            "category": expense.category,
            "amount": expense.amount,
            "cost_type": payload.cost_type,
            "economics": _economics(db, unit),
        },
    }


@router.delete("/costs/{expense_id}", response_model=dict)
def delete_cost(
    expense_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    expense = db.query(Expense).filter(
        Expense.expense_id == expense_id,
        Expense.user_id == current_user.id,
        Expense.hydroponic_unit_id.isnot(None),
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Hydroponic cost not found")
    db.delete(expense)
    db.commit()
    return {"status": "success", "message": "Cost record deleted successfully"}


@router.get("/costs", response_model=dict)
def list_all_hydroponic_costs(
    farm_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.hydroponic_unit_id.isnot(None),
    )
    if farm_id:
        farm = _farm_scope_filter(db, farm_id, current_user.id)
        query = query.filter(Expense.farm_id == (farm.id if farm else None))
    rows = query.order_by(Expense.expense_date.desc()).all()
    units = _unit_map(db, [r.hydroponic_unit_id for r in rows])

    return {
        "status": "success",
        "data": [
            {
                "expense_id": e.expense_id,
                "unit": units.get(e.hydroponic_unit_id),
                "category": e.category,
                "cost_type": (e.subcategory or "hydroponics_running").replace("hydroponics_", ""),
                "amount": e.amount,
                "incurred_date": e.expense_date.date().isoformat() if e.expense_date else None,
                "vendor": e.vendor,
                "notes": e.description,
            }
            for e in rows
        ],
    }


@router.get("/units/{unit_id}/tasks", response_model=dict)
def list_unit_tasks(
    unit_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)
    return {"status": "success", "data": _unit_tasks(db, unit)}


@router.post("/units/{unit_id}/tasks/generate", response_model=dict, status_code=status.HTTP_201_CREATED)
def generate_unit_tasks(
    unit_id: str,
    payload: Optional[TaskGenerateRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unit = _unit_or_404(db, unit_id, current_user.id)
    payload = payload or TaskGenerateRequest()

    crops = db.query(HydroponicCrop).filter(
        HydroponicCrop.unit_id == unit.id,
        HydroponicCrop.status == "active",
        HydroponicCrop.crop_cycle_id.isnot(None),
    ).all()
    if not crops:
        raise HTTPException(
            status_code=400,
            detail="Start an active crop cycle in this unit before generating tasks",
        )

    multiplier = payload.interval_multiplier or 1.0
    if multiplier <= 0 or multiplier > 12:
        raise HTTPException(status_code=400, detail="interval_multiplier must be between 0 and 12")

    existing = set()
    for cycle_ids in db.query(CropTask.crop_cycle_id).filter(
        CropTask.crop_cycle_id.in_([c.crop_cycle_id for c in crops]),
        CropTask.source == "hydroponics",
    ).all():
        existing.add(cycle_ids[0])

    created = []
    for crop in crops:
        base_date = crop.planting_date or _today()
        for template in TASK_TEMPLATES:
            if template["key"] == "harvest":
                if not crop.expected_harvest_date:
                    continue
                due_date = crop.expected_harvest_date
            else:
                interval = max(1, int(round(template["interval_days"] * multiplier)))
                due_date = _add_days(base_date, interval)

            duplicate = db.query(CropTask).filter(
                CropTask.crop_cycle_id == crop.crop_cycle_id,
                CropTask.title == template["title"],
                CropTask.due_date == due_date,
            ).first()
            if duplicate:
                continue

            task = CropTask(
                task_id=generate_id("FA-TSK", db, CropTask),
                crop_cycle_id=crop.crop_cycle_id,
                title=template["title"],
                description=f"{template['title']} for {crop.crop_name} in {unit.name}",
                category=template["category"],
                due_date=due_date,
                status="pending",
                priority=template["priority"],
                source="hydroponics",
                growth_stage=crop.current_stage,
            )
            db.add(task)
            created.append({
                "task_id": task.task_id,
                "title": task.title,
                "category": task.category,
                "due_date": task.due_date,
                "priority": task.priority,
                "cycle_id": crop.cycle_id,
            })

    db.commit()

    return {
        "status": "success",
        "message": f"{len(created)} tasks generated",
        "data": created,
    }
