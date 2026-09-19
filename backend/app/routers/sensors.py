"""Sensors API - sensor management + real-time farm monitoring.

Every endpoint is scoped to the authenticated farmer. Ownership is resolved
server-side for sensor, farm and plot references; the frontend is never
trusted with farm/plot/sensor ids for authorization.

Registered devices that are not yet assigned to any farmer use the reserved
owner ``UNCLAIMED_OWNER`` so they can be discovered and claimed through the
verify -> connect flow.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Boolean, JSON, or_
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
SENSOR_TYPE_MAP = {t["key"]: t for t in SENSOR_TYPES}


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
    status = Column(String(20), default="connected")  # connected|connecting|offline|error
    device_identifier = Column(String(100), nullable=True)
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
        "battery_level": s.battery_level,
        "last_reading": s.last_reading,
        "latest": latest,
        "available_metrics": metrics,
        "connected_at": _stamp(s.connected_at),
        "last_seen": _stamp(s.last_seen),
        "created_at": _stamp(s.created_at),
    }


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
    """Supported sensor types / measurement catalogue."""

    return {"status": "success", "data": SENSOR_TYPES}


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