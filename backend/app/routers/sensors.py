"""Sensors API - sensor management + real-time farm monitoring.

Every endpoint is scoped to the authenticated farmer. Ownership is resolved
server-side for sensor, farm and plot references; the frontend is never
trusted with farm/plot/sensor ids for authorization.

Registered devices that are not yet assigned to any farmer use the reserved
owner ``UNCLAIMED_OWNER`` so they can be discovered and claimed through the
verify -> connect flow.
"""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Boolean, JSON, or_, func
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.base import Base
from app.models.farm import gen_uuid
from app.models.user import User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["Sensors"])

UNCLAIMED_OWNER = "system-device-registry"

SENSOR_TYPES = [
    {
        "key": "soil_moisture",
        "label": "Soil Moisture",
        "unit": "%",
        "icon": "fa-tint",
        "color": "#3498db",
        "description": "Measures volumetric water content in the soil.",
    },
    {
        "key": "soil_temperature",
        "label": "Soil Temperature",
        "unit": "\u00b0C",
        "icon": "fa-temperature-half",
        "color": "#e67e22",
        "description": "Measures the temperature of the soil profile.",
    },
    {
        "key": "temperature",
        "label": "Air Temperature",
        "unit": "\u00b0C",
        "icon": "fa-temperature-high",
        "color": "#e67e22",
        "description": "Measures ambient air temperature near the sensor.",
    },
    {
        "key": "humidity",
        "label": "Humidity",
        "unit": "%",
        "icon": "fa-droplet",
        "color": "#40916C",
        "description": "Measures relative air humidity.",
    },
    {
        "key": "water_level",
        "label": "Water Level",
        "unit": "%",
        "icon": "fa-water",
        "color": "#5b8def",
        "description": "Measures water level in tanks, ponds or reservoirs.",
    },
    {
        "key": "light",
        "label": "Light Intensity",
        "unit": "lux",
        "icon": "fa-sun",
        "color": "#f39c12",
        "description": "Measures ambient light intensity for the field.",
    },
    {
        "key": "air_quality",
        "label": "Air Quality",
        "unit": "\u00b5g/m\u00b3",
        "icon": "fa-wind",
        "color": "#9b59b6",
        "description": "Measures suspended particulate matter in the air.",
    },
]

# General sensor categories for farmer-registered hardware (Add Sensor flow).
SENSOR_CATEGORIES = [
    {
        "key": "soil",
        "label": "Soil Sensor",
        "unit": "",
        "icon": "fa-seedling",
        "color": "#2D8659",
        "description": "Tracks soil moisture, temperature, pH and nutrients in the field.",
    },
    {
        "key": "weather",
        "label": "Weather Sensor",
        "unit": "",
        "icon": "fa-cloud-sun",
        "color": "#3498db",
        "description": "Tracks temperature, humidity, pressure, light and rainfall.",
    },
    {
        "key": "water",
        "label": "Water Sensor",
        "unit": "",
        "icon": "fa-water",
        "color": "#5b8def",
        "description": "Tracks water levels, temperatures and flow rates.",
    },
    {
        "key": "irrigation",
        "label": "Irrigation Sensor",
        "unit": "",
        "icon": "fa-sprinkler",
        "color": "#40916C",
        "description": "Monitors irrigation lines, valves and flow.",
    },
    {
        "key": "environmental",
        "label": "Environmental Sensor",
        "unit": "",
        "icon": "fa-leaf",
        "color": "#9b59b6",
        "description": "Monitors air quality, light and ambient conditions.",
    },
    {
        "key": "multi_sensor",
        "label": "Multi-Sensor",
        "unit": "",
        "icon": "fa-microchip",
        "color": "#e67e22",
        "description": "A device that reports several different readings at once.",
    },
    {
        "key": "other",
        "label": "Other Sensor",
        "unit": "",
        "icon": "fa-microchip",
        "color": "#7f8c8d",
        "description": "Any other farm sensor hardware.",
    },
]

SENSOR_TYPE_MAP = {t["key"]: t for t in SENSOR_TYPES + SENSOR_CATEGORIES}

#: metric key -> (label, unit, min, max). Ingested readings are validated
#: against this whitelist so unsupported or out-of-range values are rejected.
SENSOR_METRICS = {
    "soil_moisture": ("Soil Moisture", "%", 0.0, 100.0),
    "soil_temperature": ("Soil Temperature", "\u00b0C", -40.0, 100.0),
    "temperature": ("Air Temperature", "\u00b0C", -60.0, 70.0),
    "humidity": ("Relative Humidity", "%", 0.0, 100.0),
    "pressure": ("Atmospheric Pressure", "hPa", 780.0, 1100.0),
    "light": ("Light Intensity", "lux", 0.0, 300000.0),
    "light_intensity": ("Light Intensity", "lux", 0.0, 300000.0),
    "rainfall": ("Rainfall", "mm", 0.0, 10000.0),
    "air_quality": ("Air Quality", "\u00b5g/m\u00b3", 0.0, 2000.0),
    "water_level": ("Water Level", "%", 0.0, 100.0),
    "water_temperature": ("Water Temperature", "\u00b0C", -10.0, 80.0),
    "flow_rate": ("Flow Rate", "L/min", 0.0, 100000.0),
    "tank_level": ("Tank Level", "%", 0.0, 100.0),
    "ph": ("Soil pH", "", 0.0, 14.0),
    "soil_ph": ("Soil pH", "", 0.0, 14.0),
    "ec": ("Soil EC", "\u00b5S/cm", 0.0, 20000.0),
    "soil_ec": ("Soil EC", "\u00b5S/cm", 0.0, 20000.0),
    "nitrogen": ("Nitrogen", "ppm", 0.0, 5000.0),
    "phosphorus": ("Phosphorus", "ppm", 0.0, 5000.0),
    "potassium": ("Potassium", "ppm", 0.0, 5000.0),
    "soil_nitrogen": ("Nitrogen", "ppm", 0.0, 5000.0),
    "soil_phosphorus": ("Phosphorus", "ppm", 0.0, 5000.0),
    "soil_potassium": ("Potassium", "ppm", 0.0, 5000.0),
    "battery": ("Battery", "%", 0.0, 100.0),
    "battery_percentage": ("Battery", "%", 0.0, 100.0),
    "battery_voltage": ("Battery Voltage", "V", 0.0, 24.0),
    "signal_strength": ("Signal Strength", "%", 0.0, 100.0),
    "device_uptime": ("Device Uptime", "min", 0.0, None),
}

#: category -> common metrics the hardware typically reports (informational
#: hints, never fabricated readings). Used for the Add Sensor form guidance.
SENSOR_TYPE_METRICS = {
    "soil": [
        "soil_moisture", "soil_temperature", "soil_ph", "soil_ec",
        "soil_nitrogen", "soil_phosphorus", "soil_potassium",
        "battery_percentage", "signal_strength",
    ],
    "weather": [
        "temperature", "humidity", "pressure", "light_intensity", "rainfall",
        "battery_percentage", "signal_strength",
    ],
    "water": [
        "water_level", "water_temperature", "flow_rate", "tank_level",
        "battery_percentage", "signal_strength",
    ],
    "irrigation": [
        "soil_moisture", "flow_rate", "battery_percentage", "signal_strength",
    ],
    "environmental": [
        "temperature", "humidity", "light_intensity", "air_quality",
        "pressure", "rainfall", "battery_percentage", "signal_strength",
    ],
    "multi_sensor": list(SENSOR_METRICS.keys()),
    "other": [],
}

DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,99}$")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_auth_token() -> str:
    return secrets.token_urlsafe(32)


class Sensor(Base):
    __tablename__ = "sensors"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    sensor_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    sensor_type = Column(String(50), nullable=False)
    sensor_name = Column(String(200), nullable=True)
    location = Column(String(200), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default="connected")  # connected|connecting|offline|error|never_connected|disconnected
    device_identifier = Column(String(100), nullable=True)
    auth_token_hash = Column(String(128), nullable=True)
    auth_token_prefix = Column(String(16), nullable=True)
    metrics_supported = Column(JSON, nullable=True)
    battery_level = Column(Float, nullable=True)
    last_reading = Column(JSON, nullable=True)
    connected_at = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    sensor_id = Column(String(36), ForeignKey("sensors.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    reading_type = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    received_at = Column(DateTime, nullable=True)
    payload = Column(JSON, nullable=True)


class SensorVerifyIn(BaseModel):
    device_identifier: str = Field(..., min_length=1, max_length=100)
    sensor_type: Optional[str] = Field(None, max_length=50)


class SensorConnectIn(BaseModel):
    device_identifier: str = Field(..., min_length=1, max_length=100)
    farm_id: str
    plot_id: Optional[str] = None
    sensor_name: Optional[str] = Field(None, max_length=200)


class SensorUpdateIn(BaseModel):
    sensor_name: Optional[str] = Field(None, max_length=200)
    farm_id: Optional[str] = None
    plot_id: Optional[str] = None


class SensorRegisterIn(BaseModel):
    device_identifier: str = Field(..., min_length=3, max_length=100)
    sensor_type: str = Field(..., min_length=1, max_length=50)
    farm_id: str = Field(..., min_length=1)
    plot_id: Optional[str] = None
    sensor_name: Optional[str] = Field(None, max_length=200)
    zone: Optional[str] = Field(None, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    supported_metrics: Optional[List[str]] = Field(None, max_length=50)


class SensorIngestIn(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=100)
    timestamp: Optional[str] = Field(None, max_length=64)
    data: Optional[dict] = None


def _stamp(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def _now() -> datetime:
    return datetime.utcnow()


def _metric_label(metric: str) -> str:
    meta = SENSOR_TYPE_MAP.get(metric)
    return meta["label"] if meta else metric.replace("_", " ").title()


def _new_code() -> str:
    import random

    return "SEN" + str(random.randint(10000000, 99999999))


def _latest_by_metric(db: Session, sensor_ids):
    """Latest reading per metric for each sensor id (from stored readings)."""
    out = {}
    if not sensor_ids:
        return out
    rows = (
        db.query(
            SensorReading.sensor_id,
            SensorReading.reading_type,
            SensorReading.value,
            SensorReading.unit,
            SensorReading.recorded_at,
        )
        .filter(SensorReading.sensor_id.in_(sensor_ids))
        .order_by(SensorReading.recorded_at.desc())
        .limit(600)
        .all()
    )
    for r in rows:
        sid, metric, value, unit, recorded = r
        bucket = out.setdefault(sid, {})
        if metric not in bucket:
            bucket[metric] = {
                "metric": metric,
                "value": value,
                "unit": unit,
                "recorded_at": _stamp(recorded),
            }
    return out


def _resolve_owned(db: Session, user: User, ref: str, raise_if_missing: bool = True):
    """Resolve a sensor by internal id or public sensor_id, owned by user."""
    sensor = (
        db.query(Sensor)
        .filter(
            Sensor.user_id == user.id,
            (Sensor.id == ref) | (Sensor.sensor_id == ref),
        )
        .first()
    )
    if raise_if_missing and not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor


def _sensor_dict(db: Session, s: Sensor) -> dict:
    farm_name = plot_name = None
    from app.models.farm import Farm, FarmPlot

    if s.farm_id:
        f = db.query(Farm).filter(Farm.id == s.farm_id).first()
        farm_name = f.farm_name if f else None
    if s.plot_id:
        p = db.query(FarmPlot).filter(FarmPlot.id == s.plot_id).first()
        plot_name = p.plot_name if p else None

    latest = _latest_by_metric(db, [s.id]).get(s.id, {})
    metrics = list(latest.keys())
    if s.last_reading and isinstance(s.last_reading, dict):
        m = s.last_reading.get("metric")
        if m and m not in latest:
            latest[m] = {
                "metric": m,
                "value": s.last_reading.get("value"),
                "unit": s.last_reading.get("unit"),
                "recorded_at": s.last_reading.get("recorded_at"),
            }
            metrics.append(m)

    return {
        "id": s.id,
        "sensor_id": s.sensor_id,
        "sensor_type": s.sensor_type,
        "sensor_type_label": _metric_label(s.sensor_type),
        "sensor_name": s.sensor_name,
        "location": s.location,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "farm_id": s.farm_id,
        "farm_name": farm_name,
        "plot_id": s.plot_id,
        "plot_name": plot_name,
        "is_active": bool(s.is_active),
        "status": s.status,
        "device_identifier": s.device_identifier,
        "auth_configured": bool(s.auth_token_prefix),
        "auth_token_prefix": s.auth_token_prefix,
        "metrics_supported": s.metrics_supported,
        "battery_level": s.battery_level,
        "last_reading": s.last_reading,
        "latest": latest,
        "available_metrics": metrics,
        "connected_at": _stamp(s.connected_at),
        "last_seen": _stamp(s.last_seen),
        "created_at": _stamp(s.created_at),
    }


def _parse_reading_time(raw: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string as UTC. Returns None when missing/invalid."""
    if not raw:
        return None
    t = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@router.get("/sensors", response_model=dict)
def list_sensors(
    sensor_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List sensors registered to the current farmer (never other users' devices)."""
    from app.routers.monitoring import _refresh_offline_status

    q = db.query(Sensor).filter(Sensor.user_id == current_user.id)
    if sensor_type:
        q = q.filter(Sensor.sensor_type == sensor_type)
    if is_active is not None:
        q = q.filter(Sensor.is_active == is_active)

    total = q.count()
    items = (
        q.order_by(Sensor.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    for s in items:
        _refresh_offline_status(db, current_user, s)
    data = [_sensor_dict(db, s) for s in items]
    return {"status": "success", "data": data, "total": total}


@router.get("/sensors/types", response_model=dict)
def sensor_types(current_user: User = Depends(get_current_user)):
    """Supported sensor types / measurement catalogue (incl. device categories)."""

    return {"status": "success", "data": SENSOR_TYPES + SENSOR_CATEGORIES}


@router.get("/sensors/available", response_model=dict)
def available_sensors(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registered devices that are not yet connected to any farmer."""
    rows = (
        db.query(Sensor)
        .filter(Sensor.user_id == UNCLAIMED_OWNER, Sensor.is_active == True)  # noqa: E712
        .order_by(Sensor.sensor_type, Sensor.created_at.asc())
        .all()
    )
    data = []
    for s in rows:
        meta = SENSOR_TYPE_MAP.get(s.sensor_type, {})
        data.append({
            "sensor_id": s.sensor_id,
            "device_identifier": s.device_identifier,
            "sensor_type": s.sensor_type,
            "sensor_type_label": meta.get("label", _metric_label(s.sensor_type)),
            "unit": meta.get("unit"),
            "icon": meta.get("icon"),
            "sensor_name": s.sensor_name,
            "location": s.location,
        })
    return {"status": "success", "data": data, "total": len(data)}


@router.post("/sensors/verify", response_model=dict)
def verify_sensor(
    body: SensorVerifyIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify a device id before connecting: exists, supported, available,
    not already owned by another farmer and compatible with the requested type."""
    ident = (body.device_identifier or "").strip()
    if not ident:
        raise HTTPException(status_code=400, detail="Sensor ID is required")

    sensor = (
        db.query(Sensor)
        .filter(or_(Sensor.device_identifier == ident, Sensor.sensor_id == ident))
        .first()
    )
    if not sensor:
        raise HTTPException(
            status_code=404,
            detail="Sensor not found or unavailable. Check the Sensor ID and try again.",
        )

    if body.sensor_type:
        requested = body.sensor_type.strip().lower()
        if requested != sensor.sensor_type:
            raise HTTPException(
                status_code=400,
                detail=f"Sensor type does not match this device. It is a {_metric_label(sensor.sensor_type)} sensor.",
            )

    meta = SENSOR_TYPE_MAP.get(sensor.sensor_type, {})

    if sensor.user_id == UNCLAIMED_OWNER:
        return {
            "status": "success",
            "data": {
                "verified": True,
                "already_connected": False,
                "available": True,
                "message": "Sensor found",
                "sensor": {
                    "sensor_id": sensor.sensor_id,
                    "device_identifier": sensor.device_identifier,
                    "sensor_type": sensor.sensor_type,
                    "sensor_type_label": meta.get("label", _metric_label(sensor.sensor_type)),
                    "unit": meta.get("unit"),
                    "icon": meta.get("icon"),
                    "sensor_name": sensor.sensor_name,
                },
            },
        }

    if sensor.user_id != current_user.id:
        raise HTTPException(
            status_code=409,
            detail="This sensor is already connected to another account.",
        )

    if sensor.is_active and sensor.status != "disconnected":
        return {
            "status": "success",
            "data": {
                "verified": True,
                "already_connected": True,
                "available": False,
                "message": "This sensor is already connected to your account.",
                "sensor": _sensor_dict(db, sensor),
            },
        }

    return {
        "status": "success",
        "data": {
            "verified": True,
            "already_connected": False,
            "available": True,
            "message": "Sensor found",
            "reconnect": True,
            "sensor": {
                "sensor_id": sensor.sensor_id,
                "device_identifier": sensor.device_identifier,
                "sensor_type": sensor.sensor_type,
                "sensor_type_label": meta.get("label", _metric_label(sensor.sensor_type)),
                "unit": meta.get("unit"),
                "icon": meta.get("icon"),
                "sensor_name": sensor.sensor_name,
            },
        },
    }


@router.post("/sensors/connect", response_model=dict, status_code=201)
def connect_sensor(
    body: SensorConnectIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Connect a verified device to the authenticated farmer's farm/plot."""
    from app.routers.monitoring import _create_notification

    ident = (body.device_identifier or "").strip()
    if not ident:
        raise HTTPException(status_code=400, detail="Sensor ID is required")

    sensor = (
        db.query(Sensor)
        .filter(or_(Sensor.device_identifier == ident, Sensor.sensor_id == ident))
        .first()
    )
    if not sensor:
        raise HTTPException(
            status_code=404,
            detail="Sensor not found or unavailable. Verify the Sensor ID first.",
        )

    if sensor.user_id != UNCLAIMED_OWNER and sensor.user_id != current_user.id:
        raise HTTPException(
            status_code=409,
            detail="This sensor is already connected to another account.",
        )
    if (
        sensor.user_id == current_user.id
        and sensor.is_active
        and sensor.status != "disconnected"
    ):
        raise HTTPException(
            status_code=409,
            detail="This sensor is already connected to your account.",
        )

    from app.models.farm import Farm, FarmPlot

    farm = (
        db.query(Farm)
        .filter(Farm.id == body.farm_id, Farm.user_id == current_user.id)
        .first()
    )
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    plot = None
    if body.plot_id:
        plot = (
            db.query(FarmPlot)
            .filter(FarmPlot.id == body.plot_id, FarmPlot.farm_id == farm.id)
            .first()
        )
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")

    reconnect = sensor.user_id == current_user.id
    sensor.user_id = current_user.id
    sensor.farm_id = farm.id
    sensor.plot_id = plot.id if plot else None
    if body.sensor_name and body.sensor_name.strip():
        sensor.sensor_name = body.sensor_name.strip()
    if not (sensor.sensor_name or "").strip():
        sensor.sensor_name = f"{_metric_label(sensor.sensor_type)} Sensor"
    if not sensor.sensor_id:
        sensor.sensor_id = _new_code()
    sensor.status = "connected"
    sensor.is_active = True
    sensor.connected_at = sensor.connected_at or _now()
    sensor.last_seen = _now()
    db.add(sensor)
    db.commit()
    db.refresh(sensor)

    _create_notification(
        db,
        current_user,
        "Sensor connected",
        f"Sensor {sensor.sensor_name or sensor.sensor_id} (id {sensor.sensor_id}) is now connected to farm {farm.farm_name}.",
        ref_id=sensor.id,
        ref_type="sensor",
    )
    db.commit()

    return {
        "status": "success",
        "message": "Sensor connected",
        "data": _sensor_dict(db, sensor),
    }


@router.post("/sensors/register", response_model=dict, status_code=201)
def register_sensor(
    body: SensorRegisterIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a farmer's own physical sensor device.

    - Device ID is required, unique and validated (alphanumeric characters).
    - Farm is required and must belong to the authenticated farmer; the plot
      (field), if given, must belong to that farm.
    - A secure auth token is generated server-side and only its SHA-256 hash is
      stored. The plaintext token is returned exactly once.
    - The sensor starts in ``never_connected`` and only goes online once it
      submits authenticated readings to POST /sensors/data.
    """
    from app.models.farm import Farm, FarmPlot

    ident = (body.device_identifier or "").strip()
    if not DEVICE_ID_RE.match(ident):
        raise HTTPException(
            status_code=400,
            detail="Device ID must be 3-100 characters using only letters, numbers and . _ : - (no spaces).",
        )

    sensor_type = (body.sensor_type or "").strip().lower()
    if sensor_type not in SENSOR_TYPE_MAP:
        raise HTTPException(
            status_code=400,
            detail="Unknown sensor type. Choose one of the supported types.",
        )

    farm = (
        db.query(Farm)
        .filter(Farm.id == body.farm_id, Farm.user_id == current_user.id)
        .first()
    )
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    plot = None
    if body.plot_id:
        plot = (
            db.query(FarmPlot)
            .filter(FarmPlot.id == body.plot_id, FarmPlot.farm_id == farm.id)
            .first()
        )
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")

    existing = (
        db.query(Sensor)
        .filter(
            or_(
                func.lower(Sensor.device_identifier) == ident.lower(),
                func.lower(Sensor.sensor_id) == ident.lower(),
            )
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="This Device ID is already registered. Use a different Device ID or check the printed code.",
        )

    token = _new_auth_token()
    sensor_type_meta = SENSOR_TYPE_MAP.get(sensor_type, {})
    zone = (body.zone or "").strip()
    location = zone or ", ".join([farm.village or "", farm.district or ""]).strip(", ") or farm.farm_name
    latitude = body.latitude if body.latitude is not None else farm.latitude
    longitude = body.longitude if body.longitude is not None else farm.longitude

    name = (body.sensor_name or "").strip()
    if not name:
        name = f"{sensor_type_meta.get('label', sensor_type)} Sensor"

    supported = None
    if body.supported_metrics:
        cleaned = [m for m in body.supported_metrics if m in SENSOR_METRICS]
        supported = cleaned or None

    sensor = Sensor(
        id=gen_uuid(),
        sensor_id=_new_code(),
        user_id=current_user.id,
        farm_id=farm.id,
        plot_id=plot.id if plot else None,
        sensor_type=sensor_type,
        sensor_name=name,
        location=location[:200],
        latitude=latitude,
        longitude=longitude,
        is_active=True,
        status="never_connected",
        device_identifier=ident,
        auth_token_hash=_hash_token(token),
        auth_token_prefix=token[:10],
        metrics_supported=supported,
        created_at=_now(),
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)

    data = dict(_sensor_dict(db, sensor))
    data["auth_token"] = token
    db.commit()
    return {
        "status": "success",
        "message": "Sensor registered. Auth token generated - copy it now, it is shown only once.",
        "data": data,
    }


@router.post("/sensors/data", response_model=dict, status_code=201)
def ingest_sensor_data(
    body: SensorIngestIn,
    x_sensor_token: Optional[str] = Header(None, alias="X-Sensor-Token"),
    db: Session = Depends(get_db),
):
    """Authenticated data submission from physical sensor hardware.

    The sensor authenticates with its Device ID + auth token (no farmer JWT).
    Readings are validated against the supported-metrics whitelist (type and
    range). A sensor-provided ISO timestamp is stored as ``recorded_at`` when
    valid, and the server receive time is always stored as ``received_at``.
    """
    ident = (body.device_id or "").strip()
    if not ident:
        raise HTTPException(status_code=400, detail="device_id is required")
    if not x_sensor_token:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Sensor-Token header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sensor = (
        db.query(Sensor)
        .filter(or_(Sensor.device_identifier == ident, Sensor.sensor_id == ident))
        .first()
    )
    if not sensor:
        raise HTTPException(status_code=401, detail="Unknown Device ID.")
    if not sensor.is_active:
        raise HTTPException(status_code=401, detail="Sensor is inactive.")
    if not sensor.auth_token_hash or not secrets.compare_digest(
        sensor.auth_token_hash, _hash_token(x_sensor_token)
    ):
        raise HTTPException(status_code=401, detail="Invalid sensor auth token.")

    payload = body.data
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=400, detail="No reading data provided.")

    received_at = _now()
    recorded_at = _parse_reading_time(body.timestamp) or received_at

    readings = []
    battery = None
    for metric, value in payload.items():
        meta = SENSOR_METRICS.get(metric)
        if not meta:
            raise HTTPException(
                status_code=422,
                detail={
                    "metric": metric,
                    "message": f"Unsupported metric '{metric}'.",
                    "supported": list(SENSOR_METRICS.keys()),
                },
            )
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422, detail=f"Metric '{metric}' must be a numeric value."
            )
        label, unit, lo, hi = meta
        if lo is not None and num < lo:
            raise HTTPException(
                status_code=422,
                detail=f"Metric '{metric}' value {num} is below the supported range ({lo} to {hi} {unit}).".strip(),
            )
        if hi is not None and num > hi:
            raise HTTPException(
                status_code=422,
                detail=f"Metric '{metric}' value {num} exceeds the supported range ({lo} to {hi} {unit}).".strip(),
            )
        readings.append(
            SensorReading(
                id=gen_uuid(),
                sensor_id=sensor.id,
                user_id=sensor.user_id,
                farm_id=sensor.farm_id,
                plot_id=sensor.plot_id,
                reading_type=metric,
                value=num,
                unit=unit,
                recorded_at=recorded_at,
                received_at=received_at,
                payload={metric: num},
            )
        )
        if metric in ("battery", "battery_percentage") and battery is None:
            battery = num

    if not readings:
        raise HTTPException(status_code=400, detail="No valid readings in payload.")

    first = readings[0]
    sensor.last_reading = {
        "metric": first.reading_type,
        "value": first.value,
        "unit": first.unit,
        "recorded_at": _stamp(first.recorded_at),
    }
    sensor.last_seen = received_at
    sensor.connected_at = sensor.connected_at or received_at
    if sensor.status != "connected":
        sensor.status = "connected"
    if battery is not None:
        sensor.battery_level = round(battery, 2)
    db.add_all(readings)
    db.add(sensor)
    db.commit()

    return {
        "status": "success",
        "message": "Readings recorded.",
        "data": {
            "received_at": _stamp(received_at),
            "recorded_at": _stamp(recorded_at),
            "count": len(readings),
            "metrics": [r.reading_type for r in readings],
        },
    }


@router.post("/sensors/{sensor_id}/rotate-token", response_model=dict)
def rotate_sensor_token(
    sensor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Regenerate a sensor's auth token. The old token stops working immediately."""
    sensor = _resolve_owned(db, current_user, sensor_id)
    token = _new_auth_token()
    sensor.auth_token_hash = _hash_token(token)
    sensor.auth_token_prefix = token[:10]
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    data = dict(_sensor_dict(db, sensor))
    data["auth_token"] = token
    return {
        "status": "success",
        "message": "Auth token rotated. The new token is shown only once - copy it now.",
        "data": data,
    }


@router.get("/sensors/{sensor_id}/readings", response_model=dict)
def get_reading_history(
    sensor_id: str,
    hours: int = Query(24, ge=1, le=336),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Real stored readings for a single owned sensor (chronological)."""
    sensor = _resolve_owned(db, current_user, sensor_id)
    since = _now() - timedelta(hours=hours)
    rows = (
        db.query(SensorReading)
        .filter(
            SensorReading.sensor_id == sensor.id,
            SensorReading.recorded_at >= since,
        )
        .order_by(SensorReading.recorded_at.asc())
        .limit(1000)
        .all()
    )
    data = [
        {
            "metric": r.reading_type,
            "value": r.value,
            "unit": r.unit,
            "recorded_at": _stamp(r.recorded_at),
            "received_at": _stamp(r.received_at),
        }
        for r in rows
    ]
    metrics = {}
    for d in data:
        metrics.setdefault(d["metric"], []).append(d)
    return {
        "status": "success",
        "data": data,
        "total": len(data),
        "metrics": metrics,
        "sensor": _sensor_dict(db, sensor),
    }


@router.get("/sensors/{sensor_id}/status", response_model=dict)
def sensor_status(
    sensor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Current connection status, latest reading and battery for a sensor."""
    from app.routers.monitoring import _refresh_offline_status

    sensor = _resolve_owned(db, current_user, sensor_id)
    _refresh_offline_status(db, current_user, sensor)
    db.refresh(sensor)
    latest = _latest_by_metric(db, [sensor.id]).get(sensor.id, {})
    return {
        "status": "success",
        "data": {
            **_sensor_dict(db, sensor),
            "latest": latest,
        },
    }


@router.get("/sensors/{sensor_id}/alerts", response_model=dict)
def sensor_alerts(
    sensor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alerts tied to an owned sensor (from the shared MonitoringAlert table)."""
    from app.models.monitoring import MonitoringAlert

    sensor = _resolve_owned(db, current_user, sensor_id)
    rows = (
        db.query(MonitoringAlert)
        .filter(
            MonitoringAlert.user_id == current_user.id,
            MonitoringAlert.sensor_id == sensor.id,
        )
        .order_by(MonitoringAlert.created_at.desc())
        .limit(50)
        .all()
    )
    data = [
        {
            "id": a.id,
            "alert_id": a.alert_id,
            "alert_type": a.alert_type,
            "metric": a.metric,
            "message": a.message,
            "severity": a.severity,
            "status": a.status,
            "is_read": bool(a.is_read),
            "created_at": _stamp(a.created_at),
            "resolved_at": _stamp(a.resolved_at),
        }
        for a in rows
    ]
    return {"status": "success", "data": data, "total": len(data)}


@router.post("/sensors/{sensor_id}/refresh", response_model=dict)
def refresh_sensor(
    sensor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Refetch latest sensor state; applies real offline-status transitions."""
    sensor = _resolve_owned(db, current_user, sensor_id)
    from app.routers.monitoring import _refresh_offline_status

    _refresh_offline_status(db, current_user, sensor)
    db.refresh(sensor)
    return {
        "status": "success",
        "message": "Sensor data updated.",
        "data": _sensor_dict(db, sensor),
    }


@router.post("/sensors/{sensor_id}/reconnect", response_model=dict)
def reconnect_sensor(
    sensor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reactivate a previously disconnected sensor owned by this farmer."""
    sensor = _resolve_owned(db, current_user, sensor_id)
    sensor.status = "connected"
    sensor.is_active = True
    sensor.last_seen = _now()
    sensor.connected_at = sensor.connected_at or _now()
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return {
        "status": "success",
        "message": "Sensor reconnected.",
        "data": _sensor_dict(db, sensor),
    }


@router.post("/sensors/{sensor_id}/disconnect", response_model=dict)
def disconnect_sensor(
    sensor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disconnect an owned sensor. Historical readings are preserved."""
    from app.routers.monitoring import _create_notification

    sensor = _resolve_owned(db, current_user, sensor_id)
    sensor.status = "disconnected"
    sensor.is_active = False
    db.add(sensor)
    db.commit()
    _create_notification(
        db,
        current_user,
        "Sensor disconnected",
        f"Sensor {sensor.sensor_name or sensor.sensor_id} has been disconnected from your account.",
        ref_id=sensor.id,
        ref_type="sensor",
    )
    db.commit()
    return {"status": "success", "message": "Sensor disconnected"}


@router.patch("/sensors/{sensor_id}", response_model=dict)
def update_sensor(
    sensor_id: str,
    body: SensorUpdateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update sensor configuration: name, farm and/or plot."""
    from app.models.farm import Farm, FarmPlot

    sensor = _resolve_owned(db, current_user, sensor_id)

    if body.sensor_name is not None:
        sensor.sensor_name = body.sensor_name.strip() or None

    if body.farm_id is not None:
        farm = (
            db.query(Farm)
            .filter(Farm.id == body.farm_id, Farm.user_id == current_user.id)
            .first()
        )
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")
        sensor.farm_id = farm.id
        if body.plot_id is None:
            sensor.plot_id = None

    if body.plot_id is not None:
        if not sensor.farm_id:
            raise HTTPException(status_code=400, detail="Select a farm before assigning a plot.")
        plot = (
            db.query(FarmPlot)
            .filter(FarmPlot.id == body.plot_id, FarmPlot.farm_id == sensor.farm_id)
            .first()
        )
        if not plot:
            raise HTTPException(status_code=404, detail="Plot not found")
        sensor.plot_id = plot.id

    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return {
        "status": "success",
        "message": "Sensor updated.",
        "data": _sensor_dict(db, sensor),
    }


@router.get("/sensors/{sensor_id}", response_model=dict)
def get_sensor(
    sensor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sensor = _resolve_owned(db, current_user, sensor_id)
    return {"status": "success", "data": _sensor_dict(db, sensor)}