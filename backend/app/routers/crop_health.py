"""Crop Health & Care API.

Answers four farmer questions for the *authenticated* farmer's own crop:
  1. How is my crop?            -> overall status + health score
  2. What is happening to it?   -> condition overview + plain explanation
  3. What does it need now?     -> practical crop needs + prioritised actions
  4. What could happen next?    -> cautious, data-backed outlook

Everything is derived from real records already stored by Farm Assist:
CropCycle (crop, plot, sowing date, stage, care notes), CropTask, FarmJournal,
SoilRecord, IrrigationRecord, monitoring sensors/alerts and live weather.

No value is invented. A factor with no supporting record is reported as
unavailable and simply excluded from the health score; when too few factors
carry real data the API returns "insufficient" instead of a fabricated number.

Ownership is always resolved server-side through
Authenticated Farmer -> Farm -> Plot -> CropCycle. Client supplied ids are
validated against the caller's own farms and never trusted to reach another
farmer's data.
"""

from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database.connection import get_db
from app.models.crop import (
    Crop,
    CropCycle,
    CropTask,
    FarmJournal,
    IrrigationRecord,
    SoilRecord,
)
from app.models.farm import Farm, FarmPlot
from app.models.monitoring import MonitoringAlert
from app.models.user import User
from app.routers.sensors import Sensor
from app.services.ai_service import chat_with_ai
from app.services.weather_service import get_current_weather
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/crop-health", tags=["Crop Health"])

# ---------------------------------------------------------------------------
# Reference bands. Guidance targets, never readings.
# ---------------------------------------------------------------------------
SOIL_TARGETS = {
    "default": {
        "ph": (6.0, 7.5),
        "moisture": (35.0, 65.0),
        "nitrogen": (280.0, 560.0),
        "phosphorus": (10.0, 25.0),
        "potassium": (110.0, 280.0),
        "organic_matter": (0.5, 2.5),
    },
    "rice": {"ph": (5.5, 7.0), "moisture": (50.0, 80.0), "nitrogen": (300.0, 600.0)},
    "paddy": {"ph": (5.5, 7.0), "moisture": (50.0, 80.0), "nitrogen": (300.0, 600.0)},
    "wheat": {"ph": (6.0, 7.5), "moisture": (40.0, 60.0)},
    "cotton": {"ph": (6.0, 8.0), "moisture": (35.0, 60.0)},
    "maize": {"ph": (5.8, 7.0), "moisture": (40.0, 65.0)},
    "chilli": {"ph": (6.0, 7.0), "moisture": (40.0, 65.0)},
    "tomato": {"ph": (6.0, 7.0), "moisture": (45.0, 70.0)},
    "groundnut": {"ph": (6.0, 7.5), "moisture": (35.0, 60.0)},
    "soybean": {"ph": (6.0, 7.5), "moisture": (40.0, 65.0)},
    "sugarcane": {"ph": (6.0, 7.5), "moisture": (45.0, 75.0)},
    "turmeric": {"ph": (5.5, 7.5), "moisture": (45.0, 70.0)},
}

POOR_MOISTURE = 30.0

# Canonical crop lifecycle used across the page.
STAGE_ORDER = ["seedling", "vegetative", "flowering", "fruiting", "harvest"]
STAGE_LABELS = {
    "seedling": "Seedling",
    "vegetative": "Vegetative",
    "flowering": "Flowering",
    "fruiting": "Fruiting",
    "harvest": "Harvest",
}
STAGE_ALIASES = {
    "germinat": "seedling",
    "nursery": "seedling",
    "sprout": "seedling",
    "tiller": "vegetative",
    "vegetat": "vegetative",
    "growth": "vegetative",
    "jointing": "vegetative",
    "booting": "flowering",
    "heading": "flowering",
    "panicle": "flowering",
    "flower": "flowering",
    "bloom": "flowering",
    "silking": "flowering",
    "pod": "fruiting",
    "grain fill": "fruiting",
    "grain-fill": "fruiting",
    "fruiting": "fruiting",
    "fruit": "fruiting",
    "boll": "fruiting",
    "tuber": "fruiting",
    "ripening": "fruiting",
    "matur": "harvest",
    "harvest": "harvest",
}

# Factor weights. Weights are re-normalised over whichever factors actually
# carry data, so a missing subsystem never counts against the farmer.
FACTOR_WEIGHTS = {
    "growth": 0.25,
    "water": 0.25,
    "soil": 0.20,
    "weather": 0.15,
    "pest": 0.10,
    "care": 0.05,
}
STATUS_POINTS = {"good": 100.0, "attention": 55.0, "critical": 20.0}

PEST_KEYWORDS = (
    "pest", "insect", "disease", "fungus", "fungal", "blight", "rust",
    "worm", "borer", "aphid", "whitefly", "hopper", "mite", "rot",
    "mildew", "smut", "caterpillar", "thrip",
)
# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.utcnow()


def _stamp(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def _day(value) -> Optional[date]:
    """Parse a stored date (date/datetime/'YYYY-MM-DD' string) into a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _targets_for(crop_name: Optional[str]) -> dict:
    targets = dict(SOIL_TARGETS["default"])
    if crop_name:
        key = crop_name.strip().lower()
        for name, band in SOIL_TARGETS.items():
            if name != "default" and name in key:
                targets.update(band)
                break
    return targets


def _normalize_stage(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = str(raw).strip().lower().replace("_", " ")
    if key in STAGE_ORDER:
        return key
    for alias, target in STAGE_ALIASES.items():
        if alias in key:
            return target
    return None


def _stage_boundaries(duration: Optional[float]) -> list:
    """Day thresholds (from sowing) at which each lifecycle stage begins."""
    if not duration or duration <= 0:
        return [0, 40, 80, 120, 150]
    total = float(duration)
    return [0, int(total * 0.15), int(total * 0.45), int(total * 0.70), int(total * 0.90)]


def _expected_stage(days: Optional[int], duration: Optional[float]) -> Optional[str]:
    if days is None:
        return None
    boundaries = _stage_boundaries(duration)
    index = 0
    for i, start in enumerate(boundaries):
        if days >= start:
            index = i
    return STAGE_ORDER[index]


def _grade(value: Optional[float], band) -> str:
    if value is None or not band:
        return "unknown"
    low, high = band
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "good"


# ---------------------------------------------------------------------------
# Ownership-scoped resolution
# ---------------------------------------------------------------------------
def _resolve_scope(
    db: Session,
    user: User,
    farm_id: Optional[str],
    plot_id: Optional[str],
    cycle_id: Optional[str],
):
    """Resolve the authorised Farm -> Plot -> Crop cycle scope for the caller."""
    farms = (
        db.query(Farm)
        .filter(Farm.user_id == user.id, Farm.is_active == True)  # noqa: E712
        .order_by(Farm.created_at.asc())
        .all()
    )
    if farm_id:
        farm = next((f for f in farms if f.id == farm_id or f.farm_id == farm_id), None)
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")
        farms = [farm]
    if not farms:
        return [], [], [], None, None, None

    farm_ids = [f.id for f in farms]
    cycles = (
        db.query(CropCycle)
        .filter(CropCycle.farm_id.in_(farm_ids))
        .order_by(CropCycle.created_at.desc())
        .all()
    )

    plots = []
    for f in farms:
        plots.extend(
            db.query(FarmPlot)
            .filter(FarmPlot.farm_id == f.id)
            .order_by(FarmPlot.created_at.asc())
            .all()
        )
    if plot_id:
        plot = next((p for p in plots if p.id == plot_id or p.plot_id == plot_id), None)
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")
        plots = [plot]
        cycles = [c for c in cycles if c.plot_id == plot.id]

    selected_cycle = None
    if cycle_id:
        selected_cycle = next(
            (c for c in cycles if c.id == cycle_id or c.cycle_id == cycle_id), None
        )
        if not selected_cycle:
            raise HTTPException(status_code=404, detail="Crop not found for this scope")

    plot_ids_in_scope = {p.id for p in plots}
    if plot_ids_in_scope:
        cycles = [c for c in cycles if c.plot_id in plot_ids_in_scope or c.plot_id is None]

    # Default to the most recently created active cycle in scope.
    if selected_cycle is None and cycles:
        active = [c for c in cycles if (c.status or "active") == "active"]
        selected_cycle = active[0] if active else cycles[0]

    selected_plot = None
    if selected_cycle is not None and selected_cycle.plot_id:
        selected_plot = next((p for p in plots if p.id == selected_cycle.plot_id), None)
        if selected_plot is None:
            plots = [p for p in plots if p.id != selected_cycle.plot_id]
    if selected_plot is None and plots:
        selected_plot = plots[0]

    selected_farm = None
    if selected_plot is not None:
        selected_farm = next((f for f in farms if f.id == selected_plot.farm_id), None)
    if selected_farm is None and farms:
        selected_farm = farms[0]

    return farms, plots, cycles, selected_farm, selected_plot, selected_cycle


def _crop_options(db: Session, cycles) -> list:
    """Crop choices for the selector, built from the farmer's real cycles."""
    options = []
    seen = set()
    for c in cycles:
        crop = db.get(Crop, c.crop_id) if c.crop_id else None
        if not crop or c.id in seen:
            continue
        seen.add(c.id)
        options.append(
            {
                "cycle_id": c.id,
                "cycle_ref": c.cycle_id,
                "crop_id": crop.id,
                "crop_name": crop.name,
                "variety": crop.variety,
                "category": crop.category,
                "season": crop.season,
                "growth_duration_days": crop.growth_duration_days,
                "plot_id": c.plot_id,
                "plot_name": c.plot.plot_name if c.plot else None,
                "farm_id": c.farm_id,
                "farm_name": c.farm.farm_name if c.farm else None,
                "sowing_date": c.sowing_date,
                "current_stage": c.current_stage,
                "status": c.status,
            }
        )
    return options


# ---------------------------------------------------------------------------
# Record access (all plot-scoped)
# ---------------------------------------------------------------------------
def _latest_soil(db: Session, plot_ids) -> Optional[SoilRecord]:
    if not plot_ids:
        return None
    return (
        db.query(SoilRecord)
        .filter(SoilRecord.plot_id.in_(plot_ids))
        .order_by(SoilRecord.test_date.desc())
        .first()
    )


def _soil_history(db: Session, plot_ids, limit: int = 60) -> list:
    if not plot_ids:
        return []
    return (
        db.query(SoilRecord)
        .filter(SoilRecord.plot_id.in_(plot_ids))
        .order_by(SoilRecord.test_date.desc())
        .limit(limit)
        .all()
    )


def _soil_params(record: Optional[SoilRecord], crop_name: Optional[str]) -> list:
    targets = _targets_for(crop_name)
    meta = [
        ("moisture", "moisture", "Soil Moisture", "%"),
        ("ph", "ph_level", "Soil pH", ""),
        ("nitrogen", "nitrogen", "Nitrogen (N)", "kg/ha"),
        ("phosphorus", "phosphorus", "Phosphorus (P)", "kg/ha"),
        ("potassium", "potassium", "Potassium (K)", "kg/ha"),
        ("organic_matter", "organic_matter", "Organic Matter", "%"),
    ]
    params = []
    for key, attr, label, unit in meta:
        value = getattr(record, attr, None) if record else None
        band = targets.get(key)
        params.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "unit": unit,
                "status": _grade(value, band),
                "target_min": band[0] if band else None,
                "target_max": band[1] if band else None,
            }
        )
    return params


def _latest_irrigation(db: Session, plot_ids) -> Optional[IrrigationRecord]:
    if not plot_ids:
        return None
    return (
        db.query(IrrigationRecord)
        .filter(IrrigationRecord.plot_id.in_(plot_ids))
        .order_by(IrrigationRecord.irrigation_date.desc())
        .first()
    )


def _monitoring_current(db: Session, user: User, farm_ids, plot_ids) -> dict:
    if not farm_ids:
        return {}
    sensors = (
        db.query(Sensor)
        .filter(Sensor.user_id == user.id, Sensor.farm_id.in_(farm_ids))
        .all()
    )
    if plot_ids:
        sensors = [s for s in sensors if s.plot_id in plot_ids or s.plot_id is None]
    current = {}
    for s in sensors:
        reading = s.last_reading or {}
        metric = reading.get("metric")
        if not metric:
            continue
        entry = {
            "value": reading.get("value"),
            "unit": reading.get("unit"),
            "sensor_name": s.sensor_name,
            "recorded_at": reading.get("recorded_at"),
        }
        prev = current.get(metric)
        if prev is None or (entry.get("recorded_at") or "") > (prev.get("recorded_at") or ""):
            current[metric] = entry
    return current


def _alerts(db: Session, user: User, farm_ids, plot_ids, limit: int = 30) -> list:
    if not farm_ids:
        return []
    q = db.query(MonitoringAlert).filter(
        MonitoringAlert.user_id == user.id,
        MonitoringAlert.farm_id.in_(farm_ids),
    )
    if plot_ids:
        q = q.filter(MonitoringAlert.plot_id.in_(plot_ids))
    rows = q.order_by(MonitoringAlert.created_at.desc()).limit(limit).all()
    return [
        {
            "id": a.id,
            "metric": a.metric,
            "message": a.message,
            "severity": a.severity,
            "status": a.status,
            "created_at": _stamp(a.created_at),
        }
        for a in rows
    ]
def _factor(key, label, status, value, explanation, updated_at, available):
    return {
        "key": key,
        "label": label,
        "status": status,
        "value": value,
        "explanation": explanation,
        "updated_at": updated_at,
        "available": available,
    }


def _is_pest_alert(alert) -> bool:
    text = ((alert.get("metric") or "") + " " + (alert.get("message") or "")).lower()
    return any(keyword in text for keyword in PEST_KEYWORDS)


# ---------------------------------------------------------------------------
# Growth stage
# ---------------------------------------------------------------------------
def _stage_info(cycle: Optional[CropCycle], crop: Optional[Crop]) -> dict:
    today = _now().date()
    sow = _day(cycle.sowing_date) if cycle else None
    duration = crop.growth_duration_days if crop else None
    days = (today - sow).days if sow else None

    explicit = _normalize_stage(cycle.current_stage) if cycle else None
    expected = _expected_stage(days, duration)
    current = explicit or expected

    boundaries = _stage_boundaries(duration)
    progress = None
    if days is not None and duration and duration > 0:
        progress = max(0.0, min(1.0, days / float(duration)))

    next_stage = None
    to_next = None
    if days is not None and current in STAGE_ORDER:
        index = STAGE_ORDER.index(current)
        if index + 1 < len(STAGE_ORDER):
            next_stage = STAGE_ORDER[index + 1]
            to_next = max(0, boundaries[index + 1] - days)

    return {
        "sowing_date": sow.isoformat() if sow else None,
        "days_since_sowing": days,
        "growth_duration_days": duration,
        "current_stage": current,
        "current_stage_label": STAGE_LABELS.get(current) if current else None,
        "stage_recorded": bool(explicit),
        "expected_stage": expected,
        "expected_stage_label": STAGE_LABELS.get(expected) if expected else None,
        "expected_harvest_date": cycle.expected_harvest_date if cycle else None,
        "actual_harvest_date": cycle.actual_harvest_date if cycle else None,
        "next_stage": next_stage,
        "next_stage_label": STAGE_LABELS.get(next_stage) if next_stage else None,
        "days_to_next_stage": to_next,
        "progress_pct": round(progress * 100) if progress is not None else None,
        "stages": [
            {
                "key": key,
                "label": STAGE_LABELS[key],
                "start_day": boundaries[i],
                "is_current": key == current,
                "is_past": current is not None
                and STAGE_ORDER.index(key) < STAGE_ORDER.index(current),
            }
            for i, key in enumerate(STAGE_ORDER)
        ],
    }


# ---------------------------------------------------------------------------
# Individual factors
# ---------------------------------------------------------------------------
def _growth_factor(cycle: Optional[CropCycle], stage: dict) -> dict:
    label = "Growth"
    if cycle is None:
        return _factor("growth", label, "unknown", None,
                       "No crop cycle is recorded for this crop.", None, False)
    updated = _stamp(cycle.updated_at or cycle.created_at)
    days = stage["days_since_sowing"]
    duration = stage["growth_duration_days"]
    current = stage["current_stage"]
    expected = stage["expected_stage"]

    if days is None and current is None:
        return _factor("growth", label, "unknown", None,
                       "Planting date and growth stage are not recorded.", updated, False)

    if days is not None and duration and duration > 0 and days > duration * 1.15:
        return _factor("growth", label, "attention",
                       stage["current_stage_label"] or "Harvest due",
                       "The crop is past its expected growing duration of "
                       f"{duration:g} days. Check maturity and plan harvest.", updated, True)

    if current and expected:
        behind = STAGE_ORDER.index(expected) - STAGE_ORDER.index(current)
        if behind >= 2:
            return _factor("growth", label, "attention", STAGE_LABELS[current],
                           f"Growth appears slower than expected on day {days}. "
                           f"The crop is showing {STAGE_LABELS[current].lower()} while "
                           f"{STAGE_LABELS[expected].lower()} is typical at this age.",
                           updated, True)
        if behind == 1:
            return _factor("growth", label, "good", STAGE_LABELS[current],
                           f"Slightly behind the typical stage on day {days}, "
                           "but development is continuing normally.", updated, True)
        return _factor("growth", label, "good", STAGE_LABELS[current],
                       f"Development matches the expected {STAGE_LABELS[expected].lower()} stage.",
                       updated, True)

    return _factor("growth", label, "good",
                   stage["current_stage_label"] or "Recorded",
                   "A growth stage is recorded for this crop.", updated, True)


def _water_factor(moisture: Optional[float], crop_name: Optional[str],
                  latest_irrigation: Optional[IrrigationRecord]) -> dict:
    label = "Moisture"
    if moisture is None:
        return _factor("water", label, "unknown", None,
                       "No soil moisture reading is available for this plot.", None, False)
    targets = _targets_for(crop_name)
    low, high = targets["moisture"]
    value = f"{moisture:g}%"
    updated = _stamp(latest_irrigation.irrigation_date) if latest_irrigation else None
    if moisture < POOR_MOISTURE:
        return _factor("water", label, "critical", value,
                       f"Soil moisture is {moisture:g}%, well below the preferred "
                       f"{low:g}-{high:g}% for this crop.", updated, True)
    if moisture < low:
        return _factor("water", label, "attention", value,
                       f"Soil moisture is {moisture:g}%, slightly below the preferred "
                       f"{low:g}-{high:g}%.", updated, True)
    if moisture > high:
        return _factor("water", label, "attention", value,
                       f"Soil moisture is {moisture:g}%, above the preferred "
                       f"{low:g}-{high:g}%. Check drainage.", updated, True)
    return _factor("water", label, "good", value,
                   f"Soil moisture is {moisture:g}%, within the preferred "
                   f"{low:g}-{high:g}%.", updated, True)


def _soil_factor(params: list, record: Optional[SoilRecord]) -> dict:
    label = "Soil"
    graded = [p for p in params if p["status"] != "unknown"]
    if not graded:
        return _factor("soil", label, "unknown", None,
                       "No soil test is recorded for this plot.", None, False)
    updated = _stamp(record.test_date) if record else None
    value = f"{len(graded)} parameter(s) recorded"
    off = [p for p in graded if p["status"] in ("low", "high")]
    if not off:
        return _factor("soil", label, "good", value,
                       "All recorded soil parameters are within their preferred ranges.",
                       updated, True)
    if len(off) >= 3:
        return _factor("soil", label, "critical", value,
                       f"{len(off)} soil parameters are outside their preferred ranges.",
                       updated, True)
    names = ", ".join(p["label"] for p in off)
    return _factor("soil", label, "attention", value,
                   f"{names} outside the preferred range for this crop.", updated, True)


def _weather_factor(weather: Optional[dict]) -> dict:
    label = "Weather"
    if not weather:
        return _factor("weather", label, "unknown", None,
                       "Weather information is not available for this location.", None, False)

    temp = weather.get("temperature")
    humidity = weather.get("humidity")
    rain = weather.get("rain")
    wind = weather.get("wind_speed")
    description = weather.get("description") or "Current conditions"
    forecast = weather.get("forecast") or []

    issues = []
    if temp is not None and float(temp) >= 36:
        issues.append(f"high temperature ({float(temp):g}C)")
    if wind is not None and float(wind) >= 35:
        issues.append(f"strong wind ({float(wind):g} km/h)")
    wet_days = [d for d in forecast[:3] if float(d.get("precipitation") or 0) >= 5]
    if (rain is not None and float(rain) >= 10) or len(wet_days) >= 2:
        issues.append("heavy rain expected")
    if any("thunder" in str(d.get("description") or "").lower() for d in forecast[:3]):
        issues.append("thunderstorm in the forecast")

    value = f"{float(temp):g}C" if temp is not None else description
    if issues:
        return _factor("weather", label, "attention", value,
                       "Weather may stress the crop: " + ", ".join(issues) + ".",
                       _stamp(_now()), True)

    note = description
    if humidity is not None and float(humidity) >= 85:
        note += " High humidity - watch for fungal problems"
    return _factor("weather", label, "good", value, note + ".", _stamp(_now()), True)


def _pest_factor(alerts: list, cycle: Optional[CropCycle]) -> dict:
    label = "Pest & Disease"
    pest_alerts = [a for a in alerts if a["status"] == "active" and _is_pest_alert(a)]
    if pest_alerts:
        severe = any(a["severity"] == "critical" for a in pest_alerts)
        return _factor(
            "pest", label, "critical" if severe else "attention",
            f"{len(pest_alerts)} active alert(s)",
            pest_alerts[0]["message"], pest_alerts[0]["created_at"], True,
        )
    if cycle is not None and (cycle.pesticide_usage or "").strip():
        return _factor("pest", label, "attention", "Protection recorded",
                       "A pest or disease treatment is recorded for this crop. "
                       "Continue monitoring the treated area.",
                       _stamp(cycle.updated_at or cycle.created_at), True)
    return _factor("pest", label, "unknown", "Not Available",
                   "No pest or disease risk is recorded for this crop.", None, False)


def _care_factor(db: Session, cycle: Optional[CropCycle]) -> dict:
    label = "Crop Care"
    if cycle is None:
        return _factor("care", label, "unknown", None,
                       "No crop cycle is recorded for this crop.", None, False)
    tasks = db.query(CropTask).filter(CropTask.crop_cycle_id == cycle.id).all()
    if not tasks:
        return _factor("care", label, "unknown", "No tasks",
                       "No crop care tasks are logged for this crop.", None, False)
    today = _now().date().isoformat()
    completed = [t for t in tasks if t.status == "completed"]
    pending = [t for t in tasks if t.status != "completed"]
    overdue = [t for t in pending if t.due_date and t.due_date < today]
    value = f"{len(completed)}/{len(tasks)} completed"
    if overdue:
        return _factor("care", label, "attention", value,
                       f"{len(overdue)} crop care task(s) are overdue.", None, True)
    if pending:
        return _factor("care", label, "good", value,
                       f"{len(pending)} upcoming task(s); nothing is overdue.", None, True)
    return _factor("care", label, "good", value,
                   "All logged crop care tasks are completed.", None, True)


def _build_factors(db, cycle, crop, stage, soil_params, soil_record,
                   moisture, latest_irrigation, weather, alerts) -> list:
    return [
        _growth_factor(cycle, stage),
        _water_factor(moisture, crop.name if crop else None, latest_irrigation),
        _soil_factor(soil_params, soil_record),
        _weather_factor(weather),
        _pest_factor(alerts, cycle),
        _care_factor(db, cycle),
    ]


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------
def _band(score: int):
    if score >= 90:
        return "Excellent", "excellent"
    if score >= 78:
        return "Healthy", "healthy"
    if score >= 65:
        return "Good", "good"
    if score >= 50:
        return "Needs Attention", "needs_attention"
    if score >= 35:
        return "At Risk", "at_risk"
    return "Critical", "critical"


def _health_explanation(status_code: str, factors: list, crop_name: Optional[str]) -> str:
    name = crop_name or "Your crop"
    off = [f for f in factors if f["status"] in ("attention", "critical")]
    critical = [f for f in factors if f["status"] == "critical"]

    if status_code == "excellent":
        return (f"{name} is in excellent condition. All monitored factors are within "
                "their preferred ranges. Continue regular monitoring and routine care.")
    if status_code == "healthy":
        base = (f"{name} is currently developing well. Growth and condition factors are "
                "generally suitable")
        if off:
            base += f", although {off[0]['label'].lower()} needs watching"
        return base + ". Continued monitoring is recommended."
    if status_code == "good":
        base = f"{name} is in good condition overall."
        if off:
            base += " " + " ".join(f"{f['label']} needs attention." for f in off[:2])
        else:
            base += " No clear warning signs appear in the recorded data."
        return base
    if status_code == "needs_attention":
        base = f"{name} needs attention."
        if off:
            base += " " + " ".join(f["explanation"] for f in off[:2])
        return base + " Review the recommended actions below."
    base = f"{name} is under stress."
    focus = critical or off
    if focus:
        base += " " + " ".join(f["explanation"] for f in focus[:2])
    return base + " Act on the recommended actions as soon as possible."


def _compute_health(factors: list, crop_name: Optional[str]) -> dict:
    graded = [f for f in factors if f["status"] in STATUS_POINTS]
    if len(graded) < 2:
        return {
            "available": False,
            "score": None,
            "status_code": "insufficient",
            "status_label": "Insufficient Data",
            "explanation": ("We don't have enough recent information to calculate a "
                            "reliable crop health score."),
            "graded_factors": len(graded),
        }
    total_weight = sum(FACTOR_WEIGHTS.get(f["key"], 0.1) for f in graded)
    raw = sum(FACTOR_WEIGHTS.get(f["key"], 0.1) * STATUS_POINTS[f["status"]] for f in graded)
    score = int(round(max(0.0, min(100.0, raw / total_weight))))
    label, code = _band(score)
    return {
        "available": True,
        "score": score,
        "status_code": code,
        "status_label": label,
        "explanation": _health_explanation(code, graded, crop_name),
        "graded_factors": len(graded),
    }
# ---------------------------------------------------------------------------
# Narrative sections
# ---------------------------------------------------------------------------
def _factor_map(factors: list) -> dict:
    return {f["key"]: f for f in factors}


def _crop_needs(factors: list) -> list:
    fm = _factor_map(factors)
    needs = []

    water = fm.get("water")
    if water and water["status"] in ("attention", "critical"):
        needs.append({
            "icon": "fa-droplet", "label": "Water", "status": water["status"],
            "detail": ("Moisture appears lower than preferred. Check the crop's water "
                       "requirement before the next watering decision."),
        })
    elif water and water["status"] == "good":
        needs.append({
            "icon": "fa-droplet", "label": "Water", "status": "good",
            "detail": "Soil moisture is currently suitable. Keep monitoring before each irrigation.",
        })

    soil = fm.get("soil")
    if soil and soil["status"] in ("attention", "critical"):
        needs.append({
            "icon": "fa-seedling", "label": "Nutrients", "status": soil["status"],
            "detail": ("Nutrient information indicates that soil fertility should be "
                       "monitored before the next crop-care activity."),
        })
    elif not soil or not soil["available"]:
        needs.append({
            "icon": "fa-seedling", "label": "Nutrients", "status": "unknown",
            "detail": ("No soil or nutrient record is available yet. A soil test would show "
                       "what the soil currently provides."),
        })

    weather = fm.get("weather")
    if weather and weather["status"] == "attention":
        needs.append({
            "icon": "fa-cloud-sun", "label": "Weather Protection", "status": "attention",
            "detail": ("Current or forecast weather may increase crop stress. Monitor the crop "
                       "during the hottest or wettest part of the day."),
        })

    pest = fm.get("pest")
    if pest and pest["status"] in ("attention", "critical"):
        needs.append({
            "icon": "fa-shield-halved", "label": "Protection", "status": pest["status"],
            "detail": "Continue monitoring for the recorded pest or disease risk.",
        })

    growth = fm.get("growth")
    if growth and growth["status"] == "attention":
        needs.append({
            "icon": "fa-arrow-trend-up", "label": "Growth", "status": "attention",
            "detail": ("Development is not matching the expected growth stage. Compare the crop "
                       "with the expected stage and check for possible causes."),
        })

    care = fm.get("care")
    if care and care["status"] == "attention":
        needs.append({
            "icon": "fa-list-check", "label": "Crop Care", "status": "attention",
            "detail": "Some logged crop care tasks are overdue. Completing them keeps care on track.",
        })

    return needs


def _whats_happening(crop_name: Optional[str], stage: dict, factors: list,
                     status_code: str) -> str:
    name = crop_name or "Your crop"
    parts = []

    if stage.get("current_stage"):
        label = (stage.get("current_stage_label") or stage["current_stage"]).lower()
        sentence = f"{name} is currently in the {label} stage"
        days = stage.get("days_since_sowing")
        if days is not None and days >= 0:
            sentence += f", about {days} day(s) after planting"
        sentence += "."
        expected = stage.get("expected_stage")
        if expected and expected != stage["current_stage"]:
            sentence += (f" At this point {stage['expected_stage_label'].lower()} would "
                         "usually be expected.")
        parts.append(sentence)
    else:
        parts.append(f"{name} does not have a recorded planting date or growth stage yet.")

    off = [f for f in factors if f["status"] in ("attention", "critical")]
    good = [f for f in factors if f["status"] == "good"]

    if not factors or all(not f["available"] for f in factors):
        parts.append("There is not enough recorded information to describe the current condition.")
    elif off:
        parts.append("The available data suggests: " +
                     " ".join(f"{f['label']} - {f['explanation']}" for f in off[:3]))
    else:
        parts.append("Recorded conditions look stable, with no clear signs of stress in the "
                     "available data.")

    if good and not off:
        parts.append("Growth, water and the other monitored conditions are generally within "
                     "their preferred ranges.")

    return " ".join(parts)


def _what_may_happen(factors: list, status_code: str) -> list:
    fm = _factor_map(factors)
    water = fm.get("water")
    weather = fm.get("weather")
    pest = fm.get("pest")
    growth = fm.get("growth")
    outcomes = []

    if status_code in ("excellent", "healthy", "good"):
        outcomes.append({
            "condition": "If current conditions continue",
            "outlook": ("Growth is likely to continue normally if the current moisture, soil "
                        "and weather conditions are maintained."),
            "tone": "positive",
        })

    if water and water["status"] in ("attention", "critical"):
        outcomes.append({
            "condition": "If moisture remains low",
            "outlook": ("Continued moisture stress may slow growth and could reduce yield if it "
                        "continues through this stage."),
            "tone": "warning",
        })

    if weather and weather["status"] == "attention":
        outcomes.append({
            "condition": "If the weather stress continues",
            "outlook": ("Sustained heat, rain or wind may increase crop stress and affect "
                        "development and yield."),
            "tone": "warning",
        })

    if pest and pest["status"] in ("attention", "critical"):
        outcomes.append({
            "condition": "If the recorded risk increases",
            "outlook": ("The crop may become more vulnerable if the issue is not monitored and "
                        "addressed."),
            "tone": "warning",
        })

    if growth and growth["status"] == "attention":
        outcomes.append({
            "condition": "If growth stays behind schedule",
            "outlook": ("The crop may reach flowering or harvest later than planned, which can "
                        "affect the final yield."),
            "tone": "warning",
        })

    if not outcomes:
        outcomes.append({
            "condition": "With regular monitoring",
            "outlook": ("No strong warning signs appear in the available data. Keep monitoring so "
                        "any change is noticed early."),
            "tone": "neutral",
        })

    return outcomes


def _recommended_actions(factors: list, soil_available: bool) -> list:
    fm = _factor_map(factors)
    water = fm.get("water")
    soil = fm.get("soil")
    weather = fm.get("weather")
    pest = fm.get("pest")
    growth = fm.get("growth")
    care = fm.get("care")
    ordered = []

    if water and water["status"] in ("attention", "critical"):
        ordered.append(("Monitor moisture",
                        "Check the crop's moisture condition before the next watering decision.",
                        "fa-droplet", "high"))
    if pest and pest["status"] in ("attention", "critical"):
        ordered.append(("Watch for pest symptoms",
                        "Continue observing the crop for the recorded risk, especially under "
                        "the leaves and at the growing point.", "fa-shield-halved", "high"))
    if growth and growth["status"] == "attention":
        ordered.append(("Check crop growth",
                        "Compare current development with the expected growth stage and look "
                        "for possible causes.", "fa-arrow-trend-up", "high"))
    if weather and weather["status"] == "attention":
        ordered.append(("Protect the crop from weather",
                        "Act on the current weather risk during the most affected part of the day.",
                        "fa-cloud-sun", "medium"))
    if soil and soil["status"] in ("attention", "critical"):
        ordered.append(("Review nutrient condition",
                        "Check the available soil and nutrient information when planning the "
                        "next crop-care activity.", "fa-seedling", "medium"))
    if care and care["status"] == "attention":
        ordered.append(("Catch up on crop care tasks",
                        "Some logged crop care tasks are overdue. Completing them keeps the crop "
                        "on track.", "fa-list-check", "medium"))
    if not soil_available:
        ordered.append(("Consider a soil test",
                        "No soil record exists yet. A soil test will show what the soil "
                        "currently provides.", "fa-flask", "low"))
    if not ordered:
        ordered.append(("Continue routine care",
                        "Your crop currently appears to be in good condition. Continue regular "
                        "monitoring and routine care.", "fa-circle-check", "low"))

    return [
        {"step": i + 1, "title": title, "detail": detail, "icon": icon, "priority": priority}
        for i, (title, detail, icon, priority) in enumerate(ordered[:5])
    ]
# ---------------------------------------------------------------------------
# Health history (derived from real soil observations; never invented)
# ---------------------------------------------------------------------------
HEALTH_RANK = {
    "critical": 0,
    "at_risk": 1,
    "needs_attention": 2,
    "good": 3,
    "healthy": 4,
    "excellent": 5,
}


def _historical_status(record: SoilRecord, crop_name: Optional[str]):
    """Grade one recorded soil test into a health band, or None if unusable."""
    params = _soil_params(record, crop_name)
    graded = [p for p in params if p["status"] != "unknown"]
    if not graded:
        return None
    off = [p for p in graded if p["status"] in ("low", "high")]
    moisture = next((p for p in params if p["key"] == "moisture"), None)
    severe_moisture = (
        moisture is not None
        and moisture["value"] is not None
        and moisture["value"] < POOR_MOISTURE
    )
    if severe_moisture or len(off) >= 3:
        return "critical", "Critical"
    if len(off) >= 2:
        return "at_risk", "At Risk"
    if len(off) == 1:
        return "needs_attention", "Needs Attention"
    return "good", "Good"


def _health_history(db: Session, plot_ids, crop_name: Optional[str],
                    health: dict) -> dict:
    points = []

    if health.get("available"):
        points.append({
            "date": _now().date().isoformat(),
            "label": "Today",
            "status_code": health["status_code"],
            "status_label": health["status_label"],
            "score": health.get("score"),
            "source": "current assessment",
        })

    records = _soil_history(db, plot_ids, limit=24)
    seen_dates = {p["date"] for p in points}
    for record in records:
        day = _day(record.test_date)
        if day is None:
            continue
        graded = _historical_status(record, crop_name)
        if graded is None:
            continue
        iso = day.isoformat()
        if iso in seen_dates:
            continue
        seen_dates.add(iso)
        points.append({
            "date": iso,
            "label": iso,
            "status_code": graded[0],
            "status_label": graded[1],
            "score": None,
            "source": "soil test",
        })

    points.sort(key=lambda p: p["date"], reverse=True)
    points = points[:8]

    if len(points) < 2:
        return {
            "available": False,
            "points": points,
            "trend": None,
            "trend_label": None,
            "message": "Crop health history will appear as more records become available.",
        }

    latest, previous = points[0], points[1]
    latest_rank = HEALTH_RANK.get(latest["status_code"], 3)
    previous_rank = HEALTH_RANK.get(previous["status_code"], 3)
    if latest_rank > previous_rank:
        trend, label = "improving", "Improving"
    elif latest_rank < previous_rank:
        trend, label = "declining", "Declining"
    else:
        trend, label = "stable", "Stable"

    return {
        "available": True,
        "points": points,
        "trend": trend,
        "trend_label": label,
        "message": None,
    }


# ---------------------------------------------------------------------------
# Recent crop events
# ---------------------------------------------------------------------------
def _recent_events(db: Session, user: User, cycle: Optional[CropCycle],
                   plot_ids, alerts: list) -> list:
    events = []

    if cycle is not None:
        sow = _day(cycle.sowing_date)
        crop = db.get(Crop, cycle.crop_id) if cycle.crop_id else None
        if sow:
            events.append({
                "date": sow.isoformat(),
                "type": "planting",
                "icon": "fa-seedling",
                "title": "Crop planted",
                "detail": (crop.name if crop else "Crop")
                + (f" ({crop.variety})" if crop and crop.variety else ""),
            })
        if cycle.current_stage:
            stamp = _day(cycle.updated_at or cycle.created_at)
            if stamp:
                events.append({
                    "date": stamp.isoformat(),
                    "type": "stage",
                    "icon": "fa-arrow-trend-up",
                    "title": "Growth stage updated",
                    "detail": cycle.current_stage,
                })
        if (cycle.fertilizer_usage or "").strip():
            stamp = _day(cycle.updated_at or cycle.created_at)
            if stamp:
                events.append({
                    "date": stamp.isoformat(),
                    "type": "fertilizer",
                    "icon": "fa-flask",
                    "title": "Fertilizer application recorded",
                    "detail": cycle.fertilizer_usage.strip()[:140],
                })
        if (cycle.pesticide_usage or "").strip():
            stamp = _day(cycle.updated_at or cycle.created_at)
            if stamp:
                events.append({
                    "date": stamp.isoformat(),
                    "type": "treatment",
                    "icon": "fa-shield-halved",
                    "title": "Treatment recorded",
                    "detail": cycle.pesticide_usage.strip()[:140],
                })

    if plot_ids:
        for record in _soil_history(db, plot_ids, limit=5):
            day = _day(record.test_date)
            if day:
                events.append({
                    "date": day.isoformat(),
                    "type": "soil",
                    "icon": "fa-vial",
                    "title": "Soil test recorded",
                    "detail": f"pH {record.ph_level:g}" if record.ph_level is not None else "Soil sample recorded",
                })

        irrigation_rows = (
            db.query(IrrigationRecord)
            .filter(IrrigationRecord.plot_id.in_(plot_ids))
            .order_by(IrrigationRecord.irrigation_date.desc())
            .limit(5)
            .all()
        )
        for record in irrigation_rows:
            day = _day(record.irrigation_date)
            if day:
                events.append({
                    "date": day.isoformat(),
                    "type": "irrigation",
                    "icon": "fa-droplet",
                    "title": "Irrigation recorded",
                    "detail": record.method or "Irrigation activity",
                })

    if cycle is not None:
        completed = (
            db.query(CropTask)
            .filter(CropTask.crop_cycle_id == cycle.id, CropTask.status == "completed")
            .order_by(CropTask.completed_at.desc())
            .limit(5)
            .all()
        )
        for task in completed:
            day = _day(task.completed_at)
            if day:
                events.append({
                    "date": day.isoformat(),
                    "type": "task",
                    "icon": "fa-circle-check",
                    "title": "Crop care task completed",
                    "detail": task.title,
                })

    journal_rows = (
        db.query(FarmJournal)
        .filter(FarmJournal.user_id == user.id)
        .order_by(FarmJournal.entry_date.desc())
        .limit(6)
        .all()
    )
    for entry in journal_rows:
        if plot_ids and entry.plot_id and entry.plot_id not in plot_ids:
            continue
        day = _day(entry.entry_date)
        if day:
            events.append({
                "date": day.isoformat(),
                "type": "journal",
                "icon": "fa-book",
                "title": "Farm activity logged",
                "detail": entry.activity,
            })

    for alert in alerts[:4]:
        stamp = (alert.get("created_at") or "")[:10]
        if stamp:
            events.append({
                "date": stamp,
                "type": "alert",
                "icon": "fa-triangle-exclamation",
                "title": "Monitoring alert",
                "detail": alert.get("message") or "Monitoring alert raised",
            })

    events.sort(key=lambda e: e["date"], reverse=True)
    return events[:8]
# ---------------------------------------------------------------------------
# AI context + narrative
# ---------------------------------------------------------------------------
def _build_ai_context(farm, plot, crop, cycle, stage, factors, health,
                      soil_record, soil_params, latest_irrigation,
                      monitoring_current, weather, alerts, events) -> list:
    lines = []
    crop_name = crop.name if crop else "unknown crop"
    lines.append(f"Selected crop: {crop_name}"
                 + (f" (variety: {crop.variety})" if crop and crop.variety else ""))
    if farm:
        lines.append(f"Farm: {farm.farm_name}. District: {farm.district or 'not recorded'}. "
                     f"Declared soil type: {farm.soil_type or 'not recorded'}. "
                     f"Water source: {farm.water_source or 'not recorded'}.")
    if plot:
        lines.append(f"Plot: {plot.plot_name}. Area: {plot.area or 'unknown'}. "
                     f"Soil type: {plot.soil_type or 'not recorded'}.")
    if cycle:
        lines.append(f"Crop cycle: status {cycle.status or 'active'}. "
                     f"Sowing date: {cycle.sowing_date or 'not recorded'}. "
                     f"Expected harvest: {cycle.expected_harvest_date or 'not recorded'}. "
                     f"Irrigation schedule: {cycle.irrigation_schedule or 'not set'}.")
    if stage:
        lines.append(f"Growth stage: {stage.get('current_stage_label') or 'not recorded'} "
                     f"(expected {stage.get('expected_stage_label') or 'unknown'}), "
                     f"day {stage.get('days_since_sowing') if stage.get('days_since_sowing') is not None else 'unknown'} "
                     f"after planting.")
    measured = [f"{p['label']}={p['value']}{p['unit']}" for p in soil_params if p["value"] is not None]
    lines.append("Soil measurements: " + (", ".join(measured) if measured else "none recorded."))
    if latest_irrigation:
        lines.append(f"Last irrigation: {latest_irrigation.method or 'method not recorded'} "
                     f"on {_stamp(latest_irrigation.irrigation_date)}.")
    else:
        lines.append("Last irrigation: no record.")
    if monitoring_current:
        lines.append("Live monitoring: " + ", ".join(
            f"{k}={v.get('value')}{v.get('unit') or ''}" for k, v in monitoring_current.items()))
    if weather:
        lines.append(f"Weather now: {weather.get('description')}, "
                     f"{weather.get('temperature')}C, humidity {weather.get('humidity')}%, "
                     f"rain {weather.get('rain')} mm.")
    if alerts:
        lines.append("Active monitoring alerts: " + "; ".join(a["message"] for a in alerts[:4]))
    graded = [f for f in factors if f["status"] != "unknown"]
    lines.append("Factor assessment: " + "; ".join(
        f"{f['label']}={f['status']}" for f in graded))
    if health.get("available"):
        lines.append(f"Rule-based health score: {health['score']}/100 ({health['status_label']}).")
    if events:
        lines.append("Recent crop events: " + "; ".join(
            f"{e['date']} {e['title']}"
            + (f" ({e['detail']})" if e.get('detail') else "") for e in events[:6]))
    return lines


def _ai_sections(crop_name, health, factors, needs, outcomes, actions, location_note):
    good = [f"{f['label']}: {f['explanation']}" for f in factors if f["status"] == "good"]
    off = [f"{f['label']}: {f['explanation']}"
           for f in factors if f["status"] in ("attention", "critical")]

    if health.get("available"):
        current = health["explanation"]
    else:
        current = (f"There is not enough recorded information yet to give a reliable "
                   f"assessment of {crop_name or 'this crop'}. "
                   "Add planting details, a soil test or a moisture reading to improve the overview.")

    if location_note:
        current = current + " " + location_note

    return {
        "current_condition": current,
        "what_is_going_well": good or [
            "Positive factors will appear here as more records are added."
        ],
        "what_needs_attention": off or [
            "No problems stand out in the data available right now."
        ],
        "what_the_crop_needs": [f"{n['label']}: {n['detail']}" for n in needs] or [
            "No specific action is required right now. Continue routine monitoring."
        ],
        "what_may_happen": [f"{o['condition']} - {o['outlook']}" for o in outcomes],
        "recommended_next_steps": [a["title"] for a in actions],
        "ai_summary": None,
        "model": "rules",
    }
# ---------------------------------------------------------------------------
# Shared payload assembly
# ---------------------------------------------------------------------------
async def _assemble(db, user, farm_id, plot_id, cycle_id):
    farms, plots, cycles, farm, plot, cycle = _resolve_scope(
        db, user, farm_id, plot_id, cycle_id
    )
    farm_ids = [f.id for f in farms]
    plot_ids = [plot.id] if plot else []

    crop = db.get(Crop, cycle.crop_id) if cycle and cycle.crop_id else None
    crop_name = crop.name if crop else None

    if plot:
        options = _crop_options(db, [c for c in cycles if c.plot_id == plot.id])
    else:
        options = _crop_options(db, cycles)

    soil_record = _latest_soil(db, plot_ids)
    soil_params = _soil_params(soil_record, crop_name)
    latest_irrigation = _latest_irrigation(db, plot_ids)
    monitoring_current = _monitoring_current(db, user, farm_ids, plot_ids)
    moisture = (monitoring_current.get("soil_moisture") or {}).get("value")
    if moisture is None and soil_record is not None:
        moisture = soil_record.moisture
    alerts = _alerts(db, user, farm_ids, plot_ids)

    weather = None
    lat = plot.latitude if plot else (farm.latitude if farm else None)
    lon = plot.longitude if plot else (farm.longitude if farm else None)
    if lat is not None and lon is not None:
        try:
            fetched = await get_current_weather(float(lat), float(lon))
            if fetched and not fetched.get("error"):
                weather = fetched
        except Exception:
            weather = None

    stage = _stage_info(cycle, crop)
    factors = _build_factors(db, cycle, crop, stage, soil_params, soil_record,
                             moisture, latest_irrigation, weather, alerts)
    health = _compute_health(factors, crop_name)
    needs = _crop_needs(factors)
    happening = _whats_happening(crop_name, stage, factors, health["status_code"])
    outcomes = _what_may_happen(factors, health["status_code"])
    actions = _recommended_actions(factors, soil_record is not None)
    history = _health_history(db, plot_ids, crop_name, health)
    events = _recent_events(db, user, cycle, plot_ids, alerts)

    return {
        "farms": farms,
        "plots": plots,
        "cycles": cycles,
        "farm": farm,
        "plot": plot,
        "cycle": cycle,
        "crop": crop,
        "crop_name": crop_name,
        "options": options,
        "soil_record": soil_record,
        "soil_params": soil_params,
        "latest_irrigation": latest_irrigation,
        "monitoring_current": monitoring_current,
        "moisture": moisture,
        "alerts": alerts,
        "weather": weather,
        "stage": stage,
        "factors": factors,
        "health": health,
        "needs": needs,
        "happening": happening,
        "outcomes": outcomes,
        "actions": actions,
        "history": history,
        "events": events,
    }


def _farm_dict(f) -> dict:
    return {
        "id": f.id,
        "farm_id": f.farm_id,
        "farm_name": f.farm_name,
        "village": f.village,
        "district": f.district,
        "state": f.state,
        "soil_type": f.soil_type,
        "water_source": f.water_source,
        "irrigation_method": f.irrigation_method,
        "total_area": f.total_area,
        "area_unit": f.area_unit,
        "latitude": f.latitude,
        "longitude": f.longitude,
    }


def _plot_dict(p) -> dict:
    return {
        "id": p.id,
        "plot_id": p.plot_id,
        "plot_name": p.plot_name,
        "farm_id": p.farm_id,
        "farm_name": p.farm.farm_name if p.farm else None,
        "area": p.area,
        "soil_type": p.soil_type,
        "latitude": p.latitude,
        "longitude": p.longitude,
    }


def _crop_cycle_dict(cycle, crop) -> Optional[dict]:
    if cycle is None:
        return None
    return {
        "cycle_id": cycle.id,
        "cycle_ref": cycle.cycle_id,
        "crop_id": cycle.crop_id,
        "crop_name": crop.name if crop else None,
        "variety": crop.variety if crop else None,
        "category": crop.category if crop else None,
        "season": crop.season if crop else None,
        "growth_duration_days": crop.growth_duration_days if crop else None,
        "status": cycle.status,
        "sowing_date": cycle.sowing_date,
        "expected_harvest_date": cycle.expected_harvest_date,
        "actual_harvest_date": cycle.actual_harvest_date,
        "current_stage": cycle.current_stage,
        "fertilizer_usage": cycle.fertilizer_usage,
        "pesticide_usage": cycle.pesticide_usage,
        "irrigation_schedule": cycle.irrigation_schedule,
        "notes": cycle.notes,
    }


@router.get("/overview", response_model=dict)
async def crop_health_overview(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    cycle_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ctx = await _assemble(db, current_user, farm_id, plot_id, cycle_id)
    factors = ctx["factors"]
    factor_by_key = {f["key"]: f for f in factors}

    soil_record = ctx["soil_record"]
    irrigation = ctx["latest_irrigation"]

    return {
        "status": "success",
        "data": {
            "farms": [_farm_dict(f) for f in ctx["farms"]],
            "plots": [_plot_dict(p) for p in ctx["plots"]],
            "crops": ctx["options"],
            "scope": {
                "farm_id": ctx["farm"].id if ctx["farm"] else None,
                "plot_id": ctx["plot"].id if ctx["plot"] else None,
                "cycle_id": ctx["cycle"].id if ctx["cycle"] else None,
                "farm": _farm_dict(ctx["farm"]) if ctx["farm"] else None,
                "plot": _plot_dict(ctx["plot"]) if ctx["plot"] else None,
                "crop": _crop_cycle_dict(ctx["cycle"], ctx["crop"]),
            },
            "crop": _crop_cycle_dict(ctx["cycle"], ctx["crop"]),
            "health": ctx["health"],
            "factors": factors,
            "condition": {
                "growth": factor_by_key.get("growth"),
                "water": factor_by_key.get("water"),
                "soil": factor_by_key.get("soil"),
                "weather": factor_by_key.get("weather"),
                "pest": factor_by_key.get("pest"),
                "care": factor_by_key.get("care"),
            },
            "soil": {
                "available": soil_record is not None,
                "soil_type": soil_record.soil_type if soil_record else (
                    ctx["plot"].soil_type if ctx["plot"] else None
                ),
                "test_date": _stamp(soil_record.test_date) if soil_record else None,
                "params": ctx["soil_params"],
            },
            "irrigation": {
                "available": irrigation is not None,
                "moisture": ctx["moisture"],
                "latest": {
                    "method": irrigation.method if irrigation else None,
                    "duration_minutes": irrigation.duration_minutes if irrigation else None,
                    "water_quantity": irrigation.water_quantity if irrigation else None,
                    "water_unit": irrigation.water_unit if irrigation else None,
                    "irrigation_date": _stamp(irrigation.irrigation_date) if irrigation else None,
                } if irrigation else None,
            },
            "monitoring": {
                "has_data": bool(ctx["monitoring_current"]),
                "current": ctx["monitoring_current"],
                "alerts": ctx["alerts"],
            },
            "weather": ctx["weather"],
            "whats_happening": ctx["happening"],
            "crop_needs": ctx["needs"],
            "what_may_happen": ctx["outcomes"],
            "growth_stage": ctx["stage"],
            "history": ctx["history"],
            "events": ctx["events"],
            "actions": ctx["actions"],
            "has_crop": ctx["cycle"] is not None,
            "refreshed_at": _stamp(_now()),
        },
    }


@router.get("/ai-overview", response_model=dict)
async def crop_health_ai_overview(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    cycle_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ctx = await _assemble(db, current_user, farm_id, plot_id, cycle_id)

    measured = (
        any(f["available"] for f in ctx["factors"])
        or ctx["soil_record"] is not None
        or ctx["latest_irrigation"] is not None
        or bool(ctx["monitoring_current"])
    )
    if not measured:
        return {
            "status": "success",
            "data": {
                "status": "insufficient",
                "overview": None,
                "message": ("Not enough crop information yet. Add planting details, a soil test "
                            "or a moisture reading to receive a crop health overview."),
                "model": None,
                "generated_at": _stamp(_now()),
            },
        }

    sections = _ai_sections(
        ctx["crop_name"], ctx["health"], ctx["factors"], ctx["needs"],
        ctx["outcomes"], ctx["actions"], None,
    )

    provider_configured = bool(
        settings.OPENAI_API_KEY or settings.GEMINI_API_KEY or settings.ANTHROPIC_API_KEY
    )
    if provider_configured:
        context_lines = _build_ai_context(
            ctx["farm"], ctx["plot"], ctx["crop"], ctx["cycle"], ctx["stage"],
            ctx["factors"], ctx["health"], ctx["soil_record"], ctx["soil_params"],
            ctx["latest_irrigation"], ctx["monitoring_current"], ctx["weather"],
            ctx["alerts"], ctx["events"],
        )
        prompt = (
            "You are an agricultural advisor for an Indian farmer. Using ONLY the real farm "
            "data below, write a short, plain-language crop health overview with these five "
            "sections: Current Condition, What's Going Well, What Needs Attention, "
            "What the Crop Needs, What May Happen. Never invent values that are not present "
            "in the data. Do not give specific chemical or pesticide dosage instructions.\n\n"
            + "\n".join(context_lines)
        )
        try:
            ai = await chat_with_ai(prompt)
            if ai.get("model") and ai["model"] != "local" and ai.get("response"):
                sections["ai_summary"] = ai["response"].strip()
                sections["model"] = ai["model"]
        except Exception:
            pass

    return {
        "status": "success",
        "data": {
            "status": "ok",
            "overview": sections,
            "message": None,
            "model": sections.get("model", "rules"),
            "generated_at": _stamp(_now()),
        },
    }
