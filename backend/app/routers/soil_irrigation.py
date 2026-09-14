"""Soil & Irrigation decision-support API.

Aggregates the authenticated farmer's real soil, irrigation, monitoring and
weather records into a single page payload, plus a data-driven overview and an
optional AI narrative. Every query is scoped through the ownership chain
Authenticated Farmer -> Farm -> Plot; ids supplied by the client are never
trusted and never used to reach another farmer's data.

Nothing here invents readings. When a parameter is missing it is reported as
unavailable, and the frontend renders an explicit empty state instead.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database.connection import get_db
from app.models.crop import Crop, CropCycle, IrrigationRecord, SoilRecord
from app.models.farm import Farm, FarmPlot
from app.models.monitoring import MonitoringAlert
from app.models.user import User
from app.routers.sensors import Sensor
from app.services.ai_service import chat_with_ai
from app.services.weather_service import get_current_weather
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/soil-irrigation", tags=["Soil & Irrigation"])

# Reference agronomic target ranges used to grade real measured values.
# These are guidance bands, not readings. "default" applies unless a crop
# specific band is known. NPK in kg/ha, moisture/organic matter in %.
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
    "turmeric": {"ph": (5.5, 7.5), "moisture": (45.0, 70.0)},
}

PARAM_META = [
    ("moisture", "Soil Moisture", "%", "Water currently held in the soil."),
    ("ph", "Soil pH", "", "Acidity / alkalinity of the soil."),
    ("nitrogen", "Nitrogen (N)", "kg/ha", "Supports leaf and stem growth."),
    ("phosphorus", "Phosphorus (P)", "kg/ha", "Supports roots and flowering."),
    ("potassium", "Potassium (K)", "kg/ha", "Supports overall plant strength."),
    ("organic_matter", "Organic Matter", "%", "Improves soil fertility and structure."),
]

POOR_MOISTURE = 30.0


def _now() -> datetime:
    return datetime.utcnow()


def _stamp(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def _targets_for(crop_name: Optional[str]) -> dict:
    targets = dict(SOIL_TARGETS["default"])
    if crop_name:
        key = crop_name.strip().lower()
        for name, band in SOIL_TARGETS.items():
            if name != "default" and name in key:
                targets.update(band)
                break
    return targets


def _resolve_scope(
    db: Session,
    user: User,
    farm_id: Optional[str],
    plot_id: Optional[str],
    crop_id: Optional[str],
):
    """Resolve the authorized farm/plot/crop scope for the user."""
    farms = (
        db.query(Farm)
        .filter(Farm.user_id == user.id, Farm.is_active is not False)
        .order_by(Farm.created_at.asc())
        .all()
    )
    if farm_id:
        farm = next((f for f in farms if f.id == farm_id), None)
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")
        farms = [farm]

    farm_ids = [f.id for f in farms]
    cycles = (
        db.query(CropCycle).filter(CropCycle.farm_id.in_(farm_ids)).all()
        if farm_ids
        else []
    )

    plots = []
    for f in farms:
        plots.extend(
            db.query(FarmPlot).filter(FarmPlot.farm_id == f.id).order_by(FarmPlot.created_at.asc()).all()
        )
    if plot_id:
        plot = next((p for p in plots if p.id == plot_id), None)
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")
        plots = [plot]

    if crop_id:
        crop_plots = {c.plot_id for c in cycles if c.crop_id == crop_id and c.plot_id}
        cycles = [c for c in cycles if c.crop_id == crop_id]
        if not crop_plots:
            raise HTTPException(status_code=404, detail="Crop not found for this farm")
        if plot_id:
            if plot_id not in crop_plots:
                raise HTTPException(status_code=404, detail="Crop not found for this plot")
        else:
            plots = [p for p in plots if p.id in crop_plots]

    plot_ids = [p.id for p in plots]
    return farms, plots, cycles


def _crop_filter_list(db: Session, cycles) -> list:
    """Distinct crops present in the scope, for the crop selector."""
    crops = {}
    for c in cycles:
        crop = db.get(Crop, c.crop_id) if c.crop_id else None
        if not crop:
            continue
        entry = crops.setdefault(
            crop.id,
            {
                "crop_id": crop.id,
                "crop_name": crop.name,
                "variety": crop.variety,
                "plots": [],
            },
        )
        if c.plot:
            entry["plots"].append({"plot_id": c.plot.id, "plot_name": c.plot.plot_name})
    return list(crops.values())


def _latest_soil(db: Session, plot_ids) -> Optional[SoilRecord]:
    if not plot_ids:
        return None
    return (
        db.query(SoilRecord)
        .filter(SoilRecord.plot_id.in_(plot_ids))
        .order_by(SoilRecord.test_date.desc())
        .first()
    )


def _soil_history(db: Session, plot_ids, limit: int = 50) -> list:
    if not plot_ids:
        return []
    rows = (
        db.query(SoilRecord)
        .filter(SoilRecord.plot_id.in_(plot_ids))
        .order_by(SoilRecord.test_date.desc())
        .limit(limit)
        .all()
    )
    plot_names = {p.id: p.plot_name for p in db.query(FarmPlot).filter(FarmPlot.id.in_(plot_ids)).all()}
    return [
        {
            "id": r.id,
            "plot_id": r.plot_id,
            "plot_name": plot_names.get(r.plot_id),
            "ph": r.ph_level,
            "ph_level": r.ph_level,
            "nitrogen": r.nitrogen,
            "phosphorus": r.phosphorus,
            "potassium": r.potassium,
            "organic_matter": r.organic_matter,
            "moisture": r.moisture,
            "soil_type": r.soil_type,
            "test_date": _stamp(r.test_date),
            "notes": r.notes,
        }
        for r in rows
    ]


def _soil_params(record: Optional[SoilRecord], crop_name: Optional[str]) -> list:
    targets = _targets_for(crop_name)
    params = []
    for key, label, unit, explanation in PARAM_META:
        value = getattr(record, {"ph": "ph_level"}.get(key, key), None) if record else None
        target = targets.get(key)
        status = "unknown"
        if value is not None and target:
            if value < target[0]:
                status = "low"
            elif value > target[1]:
                status = "high"
            else:
                status = "good"
        elif value is not None:
            status = "recorded"
        params.append(
            {
                "key": key,
                "label": label,
                "value": value,
                "unit": unit,
                "status": status,
                "target_min": target[0] if target else None,
                "target_max": target[1] if target else None,
                "explanation": explanation,
                "updated_at": _stamp(record.test_date) if record else None,
            }
        )
    return params


def _soil_status(params: list) -> dict:
    graded = [p for p in params if p["status"] in ("low", "high", "good")]
    if not graded:
        return {
            "code": "unavailable",
            "label": "Data unavailable",
            "explanation": "Add a soil test to see the overall soil health status.",
        }
    off = [p for p in graded if p["status"] in ("low", "high")]
    if not off:
        return {
            "code": "healthy",
            "label": "Healthy",
            "explanation": "Measured soil parameters are within their preferred ranges.",
        }
    if len(off) >= 3:
        return {
            "code": "critical",
            "label": "Critical",
            "explanation": f"{len(off)} soil parameters are outside their preferred ranges and need attention.",
        }
    first = off[0]
    direction = "below" if first["status"] == "low" else "above"
    return {
        "code": "attention",
        "label": "Needs Attention",
        "explanation": f"{first['label']} is {direction} the preferred range for this soil.",
    }


def _latest_irrigation(db: Session, plot_ids) -> Optional[IrrigationRecord]:
    if not plot_ids:
        return None
    return (
        db.query(IrrigationRecord)
        .filter(IrrigationRecord.plot_id.in_(plot_ids))
        .order_by(IrrigationRecord.irrigation_date.desc())
        .first()
    )


def _irrigation_history(db: Session, plot_ids, limit: int = 50) -> list:
    if not plot_ids:
        return []
    rows = (
        db.query(IrrigationRecord)
        .filter(IrrigationRecord.plot_id.in_(plot_ids))
        .order_by(IrrigationRecord.irrigation_date.desc())
        .limit(limit)
        .all()
    )
    plot_names = {p.id: p.plot_name for p in db.query(FarmPlot).filter(FarmPlot.id.in_(plot_ids)).all()}
    return [
        {
            "id": r.id,
            "plot_id": r.plot_id,
            "plot_name": plot_names.get(r.plot_id),
            "method": r.method,
            "duration_minutes": r.duration_minutes,
            "water_quantity": r.water_quantity,
            "water_unit": r.water_unit,
            "irrigation_date": _stamp(r.irrigation_date),
            "notes": r.notes,
        }
        for r in rows
    ]


def _monitoring_current(db: Session, user: User, farm_ids, plot_ids) -> dict:
    q = db.query(Sensor).filter(
        Sensor.user_id == user.id,
        Sensor.farm_id.in_(farm_ids) if farm_ids else True,
    )
    sensors = q.all()
    if plot_ids:
        sensors = [s for s in sensors if s.plot_id in plot_ids or s.plot_id is None]
    current = {}
    for s in sensors:
        lr = s.last_reading or {}
        metric = lr.get("metric")
        if not metric:
            continue
        entry = {
            "value": lr.get("value"),
            "unit": lr.get("unit"),
            "sensor_name": s.sensor_name,
            "recorded_at": lr.get("recorded_at"),
        }
        prev = current.get(metric)
        if prev is None or (entry.get("recorded_at") or "") > (prev.get("recorded_at") or ""):
            current[metric] = entry
    return current


def _alerts(db: Session, user: User, farm_ids, plot_ids) -> list:
    q = db.query(MonitoringAlert).filter(
        MonitoringAlert.user_id == user.id,
        MonitoringAlert.farm_id.in_(farm_ids) if farm_ids else True,
    )
    if plot_ids:
        q = q.filter(MonitoringAlert.plot_id.in_(plot_ids))
    rows = q.order_by(MonitoringAlert.created_at.desc()).limit(20).all()
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


def _irrigation_status(moisture: Optional[float], crop_name: Optional[str], latest_irrigation) -> dict:
    if moisture is None:
        return {
            "code": "unavailable",
            "label": "Data Unavailable",
            "explanation": "No soil moisture reading is available to judge irrigation need.",
        }
    targets = _targets_for(crop_name)
    low, high = targets["moisture"]
    if moisture < POOR_MOISTURE:
        return {
            "code": "water_needed",
            "label": "Water Needed",
            "explanation": f"Soil moisture is {moisture:g}%, well below the preferred {low:g}-{high:g}% range.",
        }
    if moisture < low:
        return {
            "code": "irrigation_recommended",
            "label": "Irrigation Recommended",
            "explanation": f"Soil moisture is {moisture:g}%, slightly below the preferred {low:g}-{high:g}% range.",
        }
    if moisture > high:
        return {
            "code": "overwatered",
            "label": "Overwatered",
            "explanation": f"Soil moisture is {moisture:g}%, above the preferred {low:g}-{high:g}% range. Reduce watering.",
        }
    return {
        "code": "sufficient",
        "label": "Moisture Sufficient",
        "explanation": f"Soil moisture is {moisture:g}%, within the preferred {low:g}-{high:g}% range.",
    }


def _recommendations(params, soil_status, irr_status, latest_irrigation, soil_available, alerts) -> list:
    recs = []

    def add(rtype, icon, title, detail, priority="medium"):
        recs.append({"type": rtype, "icon": icon, "title": title, "detail": detail, "priority": priority})

    moisture = next((p for p in params if p["key"] == "moisture"), None)
    ph = next((p for p in params if p["key"] == "ph"), None)
    nitrogen = next((p for p in params if p["key"] == "nitrogen"), None)
    om = next((p for p in params if p["key"] == "organic_matter"), None)

    if not soil_available:
        add("soil", "fa-flask", "Consider soil testing",
            "No soil test is recorded yet. A soil test gives accurate pH, nutrient and organic matter values.", "high")
    else:
        if moisture and moisture["status"] == "low":
            add("irrigation", "fa-droplet", "Improve irrigation",
                "Soil moisture is below the preferred range. Irrigate and re-check moisture before the next cycle.", "high")
        elif moisture and moisture["status"] == "high":
            add("irrigation", "fa-water", "Reduce watering",
                "Soil moisture is above the preferred range. Pause irrigation and check drainage.", "high")
        if ph and ph["status"] in ("low", "high"):
            add("soil", "fa-vial", "Monitor pH",
                "Soil pH is outside the preferred range for the selected crop. Monitor it and adjust according to a soil test.", "medium")
        if nitrogen and nitrogen["status"] == "low":
            add("soil", "fa-seedling", "Nutrients may be low",
                "Nitrogen is below the preferred range. Apply nutrients according to soil-test recommendations.", "medium")
        if om and om["status"] == "low":
            add("soil", "fa-leaf", "Improve organic matter",
                "Organic matter is low. Add compost or farmyard manure to improve soil structure and fertility.", "medium")
        if soil_status["code"] == "healthy":
            add("soil", "fa-circle-check", "Maintain current practice",
                "Soil parameters are within range. Keep monitoring moisture and schedule periodic soil tests.", "low")

    if latest_irrigation is None:
        add("irrigation", "fa-clipboard-list", "Log irrigation activity",
            "No irrigation record exists yet. Log irrigation events to track water usage and see trends.", "low")

    if alerts:
        add("monitoring", "fa-triangle-exclamation", "Review monitoring alerts",
            f"{len(alerts)} recent monitoring alert(s) are linked to this scope. Review them in Smart Monitoring.", "medium")

    if irr_status["code"] in ("water_needed", "irrigation_recommended"):
        add("irrigation", "fa-clock", "Monitor before irrigating",
            "Check soil moisture again before irrigating to avoid over-watering, and prefer early morning or evening.", "medium")

    return recs


def _build_context_lines(farm, plot, crop_info, params, soil_status, irr_status,
                         latest_irrigation, monitoring_current, weather, alerts, recommendations) -> list:
    lines = []
    if farm:
        lines.append(f"Farm: {farm.farm_name} ({farm.village or ''} {farm.district or ''}). "
                     f"Declared soil type: {farm.soil_type or 'not recorded'}. "
                     f"Water source: {farm.water_source or 'not recorded'}. "
                     f"Irrigation method: {farm.irrigation_method or 'not recorded'}.")
    if plot:
        lines.append(f"Plot: {plot.plot_name}. Area: {plot.area or 'unknown'}. Soil type: {plot.soil_type or 'not recorded'}.")
    if crop_info:
        lines.append(f"Crop: {crop_info.get('crop_name')} ({crop_info.get('variety') or 'variety not set'}), "
                     f"stage: {crop_info.get('current_stage') or 'not set'}. "
                     f"Irrigation schedule: {crop_info.get('irrigation_schedule') or 'not set'}.")

    measured = [f"{p['label']}={p['value']}{p['unit']}" for p in params if p["value"] is not None]
    lines.append("Soil measurements: " + (", ".join(measured) if measured else "none recorded."))
    lines.append(f"Soil status: {soil_status['label']} - {soil_status['explanation']}")

    if latest_irrigation:
        lines.append(f"Last irrigation: {latest_irrigation.method or 'method not recorded'}, "
                     f"{latest_irrigation.duration_minutes or '?'} minutes, "
                     f"{latest_irrigation.water_quantity or '?'} {latest_irrigation.water_unit or ''} "
                     f"on {_stamp(latest_irrigation.irrigation_date)}.")
    else:
        lines.append("Last irrigation: no record.")
    lines.append(f"Irrigation status: {irr_status['label']} - {irr_status['explanation']}")

    if monitoring_current:
        mon = ", ".join(f"{k}={v.get('value')}{v.get('unit') or ''}" for k, v in monitoring_current.items())
        lines.append(f"Live monitoring readings: {mon}")
    if weather:
        lines.append(f"Weather: {weather.get('description')}, temp {weather.get('temperature')} C, "
                     f"humidity {weather.get('humidity')}%, rain {weather.get('rain')} mm.")
        forecast = weather.get("forecast") or []
        wet = [d for d in forecast[:3] if (d.get("precipitation") or 0) > 2]
        if wet:
            lines.append("Rain expected in the next 3 days: " +
                         ", ".join(f"{d.get('date')} ({d.get('precipitation')}mm)" for d in wet))
    if alerts:
        lines.append("Active alerts: " + "; ".join(a["message"] for a in alerts))
    if recommendations:
        lines.append("Rule-based recommendations: " + "; ".join(r["title"] for r in recommendations))
    return lines


def _overview_sections(params, soil_status, irr_status, latest_irrigation, recommendations,
                       weather, monitoring_current, crop_name):
    good, attention = [], []

    for p in params:
        if p["status"] == "good":
            good.append(f"{p['label']} is within the preferred range.")
        elif p["status"] in ("low", "high"):
            attention.append(f"{p['label']} is {p['status']} the preferred range.")

    if irr_status["code"] == "sufficient":
        good.append("Soil moisture is within the available target range.")
    if latest_irrigation:
        good.append("Irrigation activity is recorded for this plot.")

    if irr_status["code"] in ("water_needed", "irrigation_recommended"):
        attention.append(irr_status["explanation"])
    if soil_status["code"] in ("attention", "critical"):
        attention.append(soil_status["explanation"])
    if not params or all(p["value"] is None for p in params):
        attention.append("No soil test data is recorded yet for this scope.")

    overall = soil_status["explanation"]
    if irr_status["code"] != "unavailable":
        overall += " " + irr_status["explanation"]

    water_advice = irr_status["explanation"]
    if weather:
        wet = [d for d in (weather.get("forecast") or [])[:2] if (d.get("precipitation") or 0) > 2]
        if wet:
            water_advice += " Rain is expected soon, so consider delaying irrigation."

    crop_insight = "Select a crop to see crop-specific soil and irrigation guidance."
    if crop_name:
        targets = _targets_for(crop_name)
        crop_insight = (
            f"For {crop_name}, keep soil moisture within {targets['moisture'][0]:g}-"
            f"{targets['moisture'][1]:g}% and pH within {targets['ph'][0]:g}-{targets['ph'][1]:g}. "
            "Monitor moisture before each irrigation and follow the crop's irrigation schedule."
        )
    actions = [r["title"] for r in recommendations]

    return {
        "overall_condition": overall,
        "what_is_good": good,
        "attention_needed": attention,
        "recommended_actions": actions,
        "water_advice": water_advice,
        "crop_insight": crop_insight,
    }


@router.get("/overview", response_model=dict)
async def soil_irrigation_overview(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, cycles = _resolve_scope(db, current_user, farm_id, plot_id, crop_id)
    farm_ids = [f.id for f in farms]
    plot_ids = [p.id for p in plots]

    crop_list = _crop_filter_list(db, cycles)

    selected_crop = None
    if crop_id:
        selected_crop = next((c for c in crop_list if c["crop_id"] == crop_id), None)
    crop_name = selected_crop["crop_name"] if selected_crop else None

    selected_farm = farms[0] if (farm_id and farms) else None
    selected_plot = plots[0] if (plot_id and plots) else None

    soil_record = _latest_soil(db, plot_ids)
    soil_history = _soil_history(db, plot_ids)
    params = _soil_params(soil_record, crop_name)
    soil_status = _soil_status(params)
    soil_available = soil_record is not None

    irr_record = _latest_irrigation(db, plot_ids)
    irr_history = _irrigation_history(db, plot_ids)
    monitoring_current = _monitoring_current(db, current_user, farm_ids, plot_ids)
    moisture_now = (monitoring_current.get("soil_moisture") or {}).get("value")
    if moisture_now is None and soil_record is not None:
        moisture_now = soil_record.moisture
    irr_status = _irrigation_status(moisture_now, crop_name, irr_record)

    total_water = sum(r["water_quantity"] or 0 for r in irr_history)
    total_duration = sum(r["duration_minutes"] or 0 for r in irr_history)
    methods = sorted({r["method"] for r in irr_history if r["method"]})
    irr_summary = {
        "event_count": len(irr_history),
        "total_water": round(total_water, 2) if total_water else None,
        "water_unit": next((r["water_unit"] for r in irr_history if r["water_unit"]), None),
        "total_duration_minutes": round(total_duration, 1) if total_duration else None,
        "methods": methods,
        "last_irrigation_date": irr_record.irrigation_date.strftime("%Y-%m-%d") if irr_record and irr_record.irrigation_date else None,
        "last_method": irr_record.method if irr_record else None,
    }

    alerts = _alerts(db, current_user, farm_ids, plot_ids)

    weather = None
    if plot_ids:
        lat, lon = plots[0].latitude, plots[0].longitude
    else:
        lat = lon = None
    if lat is None and farms:
        lat, lon = farms[0].latitude, farms[0].longitude
    if lat is not None and lon is not None:
        try:
            fetched = await get_current_weather(float(lat), float(lon))
            if fetched and not fetched.get("error"):
                weather = fetched
        except Exception:
            weather = None

    recommendations = _recommendations(
        params, soil_status, irr_status, irr_record, soil_available, alerts
    )

    has_data = bool(
        soil_available or irr_history or monitoring_current or weather
    )

    def _plot_dict(p):
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

    def _farm_dict(f):
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

    return {
        "status": "success",
        "data": {
            "farms": [_farm_dict(f) for f in farms],
            "plots": [_plot_dict(p) for p in plots],
            "crops": crop_list,
            "scope": {
                "farm_id": selected_farm.id if selected_farm else None,
                "plot_id": selected_plot.id if selected_plot else None,
                "crop_id": selected_crop["crop_id"] if selected_crop else None,
                "farm": _farm_dict(selected_farm) if selected_farm else None,
                "plot": _plot_dict(selected_plot) if selected_plot else None,
                "crop": selected_crop,
            },
            "soil": {
                "available": soil_available,
                "soil_type": soil_record.soil_type if soil_record else (selected_plot.soil_type if selected_plot else None),
                "latest": {
                    "plot_name": soil_history[0]["plot_name"] if soil_history else None,
                    "soil_type": soil_record.soil_type if soil_record else None,
                    "test_date": _stamp(soil_record.test_date) if soil_record else None,
                    "notes": soil_record.notes if soil_record else None,
                } if soil_record else None,
                "params": params,
                "status": soil_status,
                "history": soil_history,
            },
            "irrigation": {
                "available": bool(irr_history),
                "latest": {
                    "plot_name": next((p.plot_name for p in plots if irr_record and p.id == irr_record.plot_id), None),
                    "method": irr_record.method if irr_record else None,
                    "duration_minutes": irr_record.duration_minutes if irr_record else None,
                    "water_quantity": irr_record.water_quantity if irr_record else None,
                    "water_unit": irr_record.water_unit if irr_record else None,
                    "irrigation_date": _stamp(irr_record.irrigation_date) if irr_record else None,
                    "notes": irr_record.notes if irr_record else None,
                } if irr_record else None,
                "history": irr_history,
                "summary": irr_summary,
                "status": irr_status,
                "moisture": moisture_now,
            },
            "monitoring": {
                "has_data": bool(monitoring_current),
                "current": monitoring_current,
                "active_alerts": [a for a in alerts if a["status"] == "active"],
                "recent_alerts": alerts[:5],
            },
            "weather": weather,
            "recommendations": recommendations,
            "has_data": has_data,
            "refreshed_at": _stamp(_now()),
        },
    }


@router.get("/ai-overview", response_model=dict)
async def soil_irrigation_ai_overview(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms, plots, cycles = _resolve_scope(db, current_user, farm_id, plot_id, crop_id)
    farm_ids = [f.id for f in farms]
    plot_ids = [p.id for p in plots]

    crop_list = _crop_filter_list(db, cycles)
    selected_crop = next((c for c in crop_list if c["crop_id"] == crop_id), None) if crop_id else None
    crop_name = selected_crop["crop_name"] if selected_crop else None

    farm = farms[0] if farms else None
    plot = plots[0] if plots else None

    soil_record = _latest_soil(db, plot_ids)
    params = _soil_params(soil_record, crop_name)
    soil_status = _soil_status(params)
    irr_record = _latest_irrigation(db, plot_ids)
    monitoring_current = _monitoring_current(db, current_user, farm_ids, plot_ids)
    moisture_now = (monitoring_current.get("soil_moisture") or {}).get("value")
    if moisture_now is None and soil_record is not None:
        moisture_now = soil_record.moisture
    irr_status = _irrigation_status(moisture_now, crop_name, irr_record)
    alerts = _alerts(db, current_user, farm_ids, plot_ids)

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

    recommendations = _recommendations(
        params, soil_status, irr_status, irr_record, soil_record is not None, alerts
    )

    measured_any = any(p["value"] is not None for p in params) or bool(irr_record) or bool(monitoring_current)
    if not measured_any:
        return {
            "status": "success",
            "data": {
                "status": "insufficient",
                "overview": None,
                "message": "Not enough data for AI analysis. Add soil, sensor or irrigation information to receive a more accurate overview.",
                "model": None,
                "generated_at": _stamp(_now()),
            },
        }

    sections = _overview_sections(
        params, soil_status, irr_status, irr_record, recommendations, weather, monitoring_current, crop_name
    )

    model = "rules"
    provider_configured = bool(
        settings.OPENAI_API_KEY or settings.GEMINI_API_KEY or settings.ANTHROPIC_API_KEY
    )
    if provider_configured:
        crop_info = {
            "crop_name": crop_name,
            "variety": selected_crop.get("variety") if selected_crop else None,
            "current_stage": next((c.current_stage for c in cycles if c.crop_id == crop_id), None) if crop_id else None,
            "irrigation_schedule": next((c.irrigation_schedule for c in cycles if c.crop_id == crop_id), None) if crop_id else None,
        }
        context_lines = _build_context_lines(
            farm, plot, crop_info, params, soil_status, irr_status,
            irr_record, monitoring_current, weather, alerts, recommendations
        )
        prompt = (
            "You are an agricultural decision-support assistant for an Indian farmer. "
            "Using ONLY the real farm data below, write a concise overview (2-3 sentences) "
            "of the soil and irrigation condition. Never invent values. Do not add new facts.\n\n"
            + "\n".join(context_lines)
        )
        try:
            ai = await chat_with_ai(prompt)
            if ai.get("model") and ai["model"] != "local" and ai.get("response"):
                sections["overall_condition"] = ai["response"].strip()
                model = ai["model"]
        except Exception:
            return {
                "status": "success",
                "data": {
                    "status": "unavailable",
                    "overview": sections,
                    "message": "AI Overview is temporarily unavailable.",
                    "model": None,
                    "generated_at": _stamp(_now()),
                },
            }

    return {
        "status": "success",
        "data": {
            "status": "ok",
            "overview": sections,
            "message": None,
            "model": model,
            "generated_at": _stamp(_now()),
        },
    }