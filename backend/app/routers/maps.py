from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
import httpx

from app.database.connection import get_db
from app.utils.auth import get_current_user
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.models.crop import Crop, CropCycle, CropTask, SoilRecord, IrrigationRecord, FarmJournal
from app.routers.sensors import Sensor, SENSOR_TYPE_MAP

router = APIRouter(prefix="/api/v1", tags=["Maps"])


@router.get("/maps/geocode")
def geocode_address(
    address: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": address,
                    "format": "json",
                    "limit": 5,
                    "countrycodes": "in",
                },
                headers={"User-Agent": "FarmAssist/1.0"},
            )
            resp.raise_for_status()
            results = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")

    if not results:
        return {"status": "success", "data": {"results": [], "message": "No results found"}}

    return {
        "status": "success",
        "data": {
            "results": [
                {
                    "display_name": r.get("display_name"),
                    "latitude": float(r.get("lat", 0)),
                    "longitude": float(r.get("lon", 0)),
                    "type": r.get("type"),
                    "importance": r.get("importance"),
                }
                for r in results
            ]
        },
    }


@router.get("/maps/reverse-geocode")
def reverse_geocode(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "json",
                },
                headers={"User-Agent": "FarmAssist/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Reverse geocoding service unavailable")

    if not data or "error" in data:
        return {"status": "success", "data": {"address": None, "message": "No address found for these coordinates"}}

    addr = data.get("address", {})
    return {
        "status": "success",
        "data": {
            "display_name": data.get("display_name"),
            "address": {
                "house_number": addr.get("house_number"),
                "road": addr.get("road"),
                "village": addr.get("village") or addr.get("hamlet"),
                "mandal": addr.get("suburb") or addr.get("county"),
                "district": addr.get("district") or addr.get("state_district"),
                "state": addr.get("state"),
                "pincode": addr.get("postcode"),
                "country": addr.get("country"),
            },
            "latitude": latitude,
            "longitude": longitude,
        },
    }

from app.config import settings

@router.get("/maps/key")
def get_maps_key(current_user: User = Depends(get_current_user)):
    """Return Google Maps API key for the frontend.
    The key is read from settings and sent only to authenticated users.
    """
    return {"status": "success", "data": {"google_maps_api_key": settings.GOOGLE_MAPS_API_KEY}}


def _stamp(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _farm_payload(f: Farm) -> dict:
    return {
        "id": f.id,
        "farm_id": f.farm_id,
        "name": f.farm_name,
        "address": f.address,
        "village": f.village,
        "mandal": f.mandal,
        "district": f.district,
        "state": f.state,
        "pincode": f.pincode,
        "latitude": f.latitude,
        "longitude": f.longitude,
        "has_location": f.latitude is not None and f.longitude is not None,
        "total_area": f.total_area,
        "area_unit": f.area_unit or "Acres",
        "soil_type": f.soil_type,
        "water_source": f.water_source,
        "irrigation_method": f.irrigation_method,
        "farm_type": f.farm_type,
        "is_active": bool(f.is_active),
        "created_at": _stamp(f.created_at),
        "updated_at": _stamp(f.updated_at),
    }


def _cycle_payload(cycle: Optional[CropCycle], crop: Optional[Crop]) -> Optional[dict]:
    if not cycle:
        return None
    return {
        "id": cycle.id,
        "cycle_id": cycle.cycle_id,
        "cycle_status": cycle.status,
        "current_stage": cycle.current_stage,
        "sowing_date": cycle.sowing_date,
        "expected_harvest_date": cycle.expected_harvest_date,
        "actual_harvest_date": cycle.actual_harvest_date,
        "seed_quantity": cycle.seed_quantity,
        "seed_unit": cycle.seed_unit,
        "crop": {
            "crop_id": crop.crop_id if crop else None,
            "name": crop.name if crop else None,
            "variety": crop.variety if crop else None,
            "category": crop.category if crop else None,
            "season": crop.season if crop else None,
        },
    }


def _task_payload(t: CropTask) -> dict:
    return {
        "id": t.id,
        "task_id": t.task_id,
        "crop_cycle_id": t.crop_cycle_id,
        "title": t.title,
        "description": t.description,
        "category": t.category,
        "status": t.status,
        "priority": t.priority,
        "due_date": t.due_date,
        "due_time": t.due_time,
        "created_at": _stamp(t.created_at),
    }


def _sensor_payload(s: Sensor) -> dict:
    info = (SENSOR_TYPE_MAP or {}).get(s.sensor_type) or {}
    return {
        "id": s.id,
        "sensor_id": s.sensor_id,
        "name": s.sensor_name,
        "farm_id": s.farm_id,
        "plot_id": s.plot_id,
        "type": s.sensor_type,
        "type_label": info.get("label") or s.sensor_type,
        "type_icon": info.get("icon"),
        "type_color": info.get("color"),
        "unit": info.get("unit"),
        "location": s.location,
        "status": s.status,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "has_location": s.latitude is not None and s.longitude is not None,
        "last_seen": _stamp(s.last_seen),
        "last_reading": s.last_reading if isinstance(s.last_reading, dict) else None,
        "battery_level": s.battery_level,
    }


@router.get("/maps/farm-map")
def get_farm_map_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Efficient, authenticated aggregate of everything Farm Map needs.

    Returns only records owned by the authenticated farmer.
    """
    farms = (
        db.query(Farm)
        .filter(Farm.user_id == current_user.id, Farm.is_active == True)  # noqa: E712
        .order_by(Farm.created_at.asc())
        .all()
    )
    if not farms:
        return {
            "status": "success",
            "data": {
                "farms": [],
                "plots": [],
                "counts": {"farms": 0, "plots": 0, "active_cycles": 0, "sensors": 0, "tasks": 0},
                "generated_at": _stamp(datetime.utcnow()),
            },
        }

    farm_ids = [f.id for f in farms]

    plots = (
        db.query(FarmPlot)
        .filter(FarmPlot.farm_id.in_(farm_ids), FarmPlot.is_active == True)  # noqa: E712
        .order_by(FarmPlot.created_at.asc())
        .all()
    )
    plot_ids = [p.id for p in plots]

    crop_id_by_cycle = {}
    cycle_by_plot = {}
    cycles = (
        db.query(CropCycle)
        .options(joinedload(CropCycle.crop))
        .join(Farm, Farm.id == CropCycle.farm_id)
        .filter(Farm.user_id == current_user.id)
        .order_by(CropCycle.created_at.desc())
        .all()
    )
    for c in cycles:
        if c.plot_id:
            existing = cycle_by_plot.get(c.plot_id)
            if existing is None or (existing.status != "active" and c.status == "active"):
                cycle_by_plot[c.plot_id] = c
        crop_id_by_cycle[c.id] = c.crop

    task_by_plot = {}
    tasks = []
    if plot_ids:
        tasks = (
            db.query(CropTask)
            .join(CropCycle, CropCycle.id == CropTask.crop_cycle_id)
            .filter(CropCycle.plot_id.in_(plot_ids))
            .order_by(CropCycle.created_at.desc(), CropTask.created_at.desc())
            .limit(200)
            .all()
        )
    for t in tasks:
        task_by_plot.setdefault(t.crop_cycle.plot_id, []).append(_task_payload(t))

    sensors = (
        db.query(Sensor)
        .filter(Sensor.user_id == current_user.id, Sensor.farm_id.in_(farm_ids))
        .order_by(Sensor.created_at.desc())
        .all()
    )
    sensors_by_plot = {}
    farm_sensors_by_farm = {}
    for s in sensors:
        item = _sensor_payload(s)
        if s.plot_id:
            sensors_by_plot.setdefault(s.plot_id, []).append(item)
        else:
            farm_sensors_by_farm.setdefault(s.farm_id, []).append(item)

    soil_by_plot = {}
    if plot_ids:
        for r in (
            db.query(SoilRecord)
            .filter(SoilRecord.plot_id.in_(plot_ids))
            .order_by(SoilRecord.test_date.desc())
            .all()
        ):
            if r.plot_id not in soil_by_plot:
                soil_by_plot[r.plot_id] = {
                    "ph_level": r.ph_level,
                    "nitrogen": r.nitrogen,
                    "phosphorus": r.phosphorus,
                    "potassium": r.potassium,
                    "organic_matter": r.organic_matter,
                    "moisture": r.moisture,
                    "soil_type": r.soil_type,
                    "test_date": _stamp(r.test_date),
                }

    irrigation_by_plot = {}
    if plot_ids:
        for r in (
            db.query(IrrigationRecord)
            .filter(IrrigationRecord.plot_id.in_(plot_ids))
            .order_by(IrrigationRecord.irrigation_date.desc())
            .all()
        ):
            if r.plot_id not in irrigation_by_plot:
                irrigation_by_plot[r.plot_id] = {
                    "method": r.method,
                    "duration_minutes": r.duration_minutes,
                    "water_quantity": r.water_quantity,
                    "water_unit": r.water_unit,
                    "irrigation_date": _stamp(r.irrigation_date),
                }

    activity_by_plot = {}
    if plot_ids:
        journal = (
            db.query(FarmJournal)
            .filter(FarmJournal.plot_id.in_(plot_ids))
            .order_by(FarmJournal.entry_date.desc())
            .limit(300)
            .all()
        )
        for r in journal:
            if len(activity_by_plot.get(r.plot_id, [])) >= 5:
                continue
            activity_by_plot.setdefault(r.plot_id, []).append(
                {
                    "id": r.id,
                    "activity": r.activity,
                    "notes": r.notes,
                    "entry_date": _stamp(r.entry_date),
                }
            )

    plot_map = {p.id: p for p in plots}
    farm_by_id = {f.id: f for f in farms}

    plot_out = []
    for p in plots:
        cycle = cycle_by_plot.get(p.id)
        crop = crop_id_by_cycle.get(cycle.id) if cycle else None
        plot_out.append(
            {
                "id": p.id,
                "plot_id": p.plot_id,
                "farm_id": p.farm_id,
                "name": p.plot_name,
                "area": p.area,
                "area_unit": (farm_by_id[p.farm_id].area_unit if p.farm_id in farm_by_id else "Acres") or "Acres",
                "latitude": p.latitude,
                "longitude": p.longitude,
                "has_location": p.latitude is not None and p.longitude is not None,
                "boundary_coordinates": p.boundary_coordinates,
                "has_boundary": bool(
                    p.boundary_coordinates
                    and (isinstance(p.boundary_coordinates, dict) or (
                        isinstance(p.boundary_coordinates, list) and len(p.boundary_coordinates) >= 3
                    ))
                ),
                "soil_type": p.soil_type,
                "is_active": bool(p.is_active),
                "created_at": _stamp(p.created_at),
                "updated_at": _stamp(p.updated_at),
                "crop": _cycle_payload(cycle, crop),
                "sensors": sensors_by_plot.get(p.id, []),
                "tasks": task_by_plot.get(p.id, []),
                "soil_latest": soil_by_plot.get(p.id),
                "irrigation_latest": irrigation_by_plot.get(p.id),
                "activity": activity_by_plot.get(p.id, []),
            }
        )

    farm_out = []
    for f in farms:
        item = _farm_payload(f)
        item["plots"] = [pl for pl in plot_out if pl["farm_id"] == f.id]
        item["plot_count"] = len(item["plots"])
        item["sensors"] = farm_sensors_by_farm.get(f.id, [])  # farm-level sensors (plot_id null)
        farm_out.append(item)

    return {
        "status": "success",
        "data": {
            "farms": farm_out,
            "plots": plot_out,
            "counts": {
                "farms": len(farm_out),
                "plots": len(plot_out),
                "active_cycles": sum(1 for pl in plot_out if pl["crop"] and pl["crop"]["cycle_status"] == "active"),
                "sensors": len(sensors),
                "tasks": len(tasks),
            },
            "generated_at": _stamp(datetime.utcnow()),
        },
    }
