"""Smart Monitoring API.

Real-time / recorded monitoring of the authenticated farmer's own farms,
plots, connected devices and farm activities. No mock data: everything is
derived from database records owned by the authenticated user. Farmer
isolation is enforced on every query.
"""

import asyncio
import random
import uuid
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database.connection import get_db
from app.models.farm import Farm, FarmPlot
from app.models.user import User
from app.models.crop import Crop, CropCycle, CropTask
from app.models.monitoring import MonitoringAlert, MonitoringThreshold
from app.models.notification import Notification
from app.services.weather_service import get_current_weather
from app.services.ai_service import chat_with_ai
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/monitoring", tags=["Monitoring"])

OFFLINE_AFTER_SECONDS = 15 * 60
DRONE_WINDOW_START = "09:00"
DRONE_WINDOW_END = "17:00"

METRICS = {
    "soil_moisture": ("Soil Moisture", "%"),
    "temperature": ("Temperature", "\u00b0C"),
    "soil_temperature": ("Soil Temperature", "\u00b0C"),
    "humidity": ("Humidity", "%"),
    "water_level": ("Water Level", "%"),
    "air_quality": ("Air Quality", "\u00b5g/m\u00b3"),
    "light": ("Light Intensity", "lux"),
}

VALID_METRICS = set(METRICS.keys())


def _now():
    return datetime.utcnow()


def _stamp(dt: Optional[datetime]):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def _new_code(prefix: str) -> str:
    return prefix + str(random.randint(10000000, 99999999))


def _metric_label(metric: str) -> str:
    meta = METRICS.get(metric)
    return meta[0] if meta else metric.replace("_", " ").title()


def _resolve_scope(
    db: Session,
    user: User,
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
):
    """Resolve the authorized monitoring scope (farms/plots) for the user.

    Never trusts ids from the frontend: every farm must belong to user,
    every plot must belong to the farm.
    """
    farms_q = db.query(Farm).filter(Farm.user_id == user.id)
    if farm_id:
        farm = farms_q.filter(Farm.id == farm_id).first()
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")
        farm_objs = [farm]
    else:
        farm_objs = farms_q.all()

    plots = []
    for f in farm_objs:
        p_q = db.query(FarmPlot).filter(FarmPlot.farm_id == f.id)
        if plot_id:
            p = p_q.filter(FarmPlot.id == plot_id).first()
            if not p:
                raise HTTPException(status_code=404, detail="Plot not found")
            plots.append(p)
        else:
            plots.extend(p_q.all())
    return farm_objs, plots


class SensorConnectIn(BaseModel):
    farm_id: str
    plot_id: Optional[str] = None
    sensor_name: Optional[str] = Field(None, max_length=200)
    sensor_type: str = Field(..., min_length=1, max_length=50)
    device_identifier: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    battery_level: Optional[float] = None


class ReadingIn(BaseModel):
    metric: str
    value: float
    unit: Optional[str] = None
    recorded_at: Optional[str] = None


class ThresholdIn(BaseModel):
    farm_id: str
    plot_id: Optional[str] = None
    metric: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class MonitoringTaskIn(BaseModel):
    farm_id: str
    plot_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = "medium"


def _sensor_dict_with_context(s, farm, plot):
    return {
        "id": s.id,
        "sensor_id": s.sensor_id,
        "sensor_type": s.sensor_type,
        "sensor_name": s.sensor_name,
        "status": s.status,
        "is_active": bool(s.is_active),
        "device_identifier": s.device_identifier,
        "battery_level": s.battery_level,
        "farm_id": s.farm_id,
        "farm_name": farm.farm_name if farm else None,
        "plot_id": s.plot_id,
        "plot_name": plot.plot_name if plot else None,
        "metric": s.sensor_type if s.sensor_type in VALID_METRICS else None,
        "latest_reading": s.last_reading,
        "connected_at": _stamp(s.connected_at),
        "last_seen": _stamp(s.last_seen),
        "created_at": _stamp(s.created_at),
    }


def _alerts_for(db, user, farm_ids, plot_ids, status=None, limit=100):
    from app.routers.sensors import Sensor
    q = db.query(MonitoringAlert).filter(
        MonitoringAlert.user_id == user.id,
        MonitoringAlert.farm_id.in_(farm_ids) if farm_ids else False,
    )
    if plot_ids:
        q = q.filter(
            (MonitoringAlert.plot_id.in_(plot_ids)) |
            (MonitoringAlert.plot_id.is_(None))
        )
    if status:
        q = q.filter(MonitoringAlert.status == status)
    rows = q.order_by(MonitoringAlert.created_at.desc()).limit(limit).all()
    farms = {f.id: f for f in db.query(Farm).filter(Farm.id.in_([a.farm_id for a in rows])).all()}
    plots = {p.id: p for p in db.query(FarmPlot).filter(FarmPlot.id.in_([a.plot_id for a in rows if a.plot_id])).all()}
    sensors = {s.id: s for s in db.query(Sensor).filter(Sensor.id.in_([a.sensor_id for a in rows if a.sensor_id])).all()}
    out = []
    for a in rows:
        out.append({
            "id": a.id,
            "alert_id": a.alert_id,
            "alert_type": a.alert_type,
            "metric": a.metric,
            "message": a.message,
            "severity": a.severity,
            "status": a.status,
            "is_read": bool(a.is_read),
            "farm_id": a.farm_id,
            "farm_name": farms.get(a.farm_id).farm_name if farms.get(a.farm_id) else None,
            "plot_id": a.plot_id,
            "plot_name": plots.get(a.plot_id).plot_name if plots.get(a.plot_id) else None,
            "sensor_id": a.sensor_id,
            "sensor_name": sensors.get(a.sensor_id).sensor_name if sensors.get(a.sensor_id) else None,
            "created_at": _stamp(a.created_at),
            "resolved_at": _stamp(a.resolved_at),
        })
    return out


def _create_notification(db, user, title, message, ref_id=None, ref_type="alert"):
    n = Notification(
        id=str(uuid.uuid4()),
        notification_id=_new_code("NTF"),
        user_id=user.id,
        title=title,
        message=message,
        notification_type="sensor",
        reference_id=ref_id,
        reference_type=ref_type,
        icon="fa-microchip",
        action_url="/monitoring.html",
    )
    db.add(n)
    return n


@router.get("/farms", response_model=dict)
def monitoring_farms(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    farms = (
        db.query(Farm)
        .filter(Farm.user_id == current_user.id)
        .order_by(Farm.created_at.asc())
        .all()
    )
    out = []
    for f in farms:
        plot_count = (
            db.query(FarmPlot).filter(FarmPlot.farm_id == f.id).count()
        )
        out.append({
            "id": f.id,
            "farm_id": f.farm_id,
            "farm_name": f.farm_name,
            "district": f.district,
            "village": f.village,
            "latitude": f.latitude,
            "longitude": f.longitude,
            "plot_count": plot_count,
        })
    return {"status": "success", "data": out}


@router.get("/plots", response_model=dict)
def monitoring_plots(
    farm_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, None)
    farm_map = {f.id: f for f in farm_objs}
    out = []
    for p in plots:
        f = farm_map.get(p.farm_id)
        out.append({
            "id": p.id,
            "plot_id": p.plot_id,
            "plot_name": p.plot_name,
            "farm_id": p.farm_id,
            "farm_name": f.farm_name if f else None,
            "area": p.area,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "soil_type": p.soil_type,
            "boundary_coordinates": p.boundary_coordinates,
        })
    return {"status": "success", "data": out}


@router.get("/sensors", response_model=dict)
def monitoring_sensors(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    farm_ids = [f.id for f in farm_objs]
    plot_ids = [p.id for p in plots]
    from app.routers.sensors import Sensor

    q = db.query(Sensor).filter(Sensor.user_id == current_user.id)
    if farm_ids:
        q = q.filter(Sensor.farm_id.in_(farm_ids))
    if plot_ids:
        q = q.filter(or_(Sensor.plot_id.in_(plot_ids), Sensor.plot_id.is_(None)))
    sensors = q.order_by(Sensor.created_at.asc()).all()
    farm_map = {f.id: f for f in farm_objs}
    plot_map = {p.id: p for p in plots}
    for s in sensors:
        _refresh_offline_status(db, current_user, s)
    out = [
        _sensor_dict_with_context(
            s,
            farm_map.get(s.farm_id),
            plot_map.get(s.plot_id),
        )
        for s in sensors
    ]
    return {"status": "success", "data": out, "total": len(out)}


def _refresh_offline_status(db: Session, user: User, sensor) -> None:
    """Real status transitions: a connected sensor with a stale last_seen is offline."""
    changed = False
    now = _now()
    if sensor.status == "connected" and sensor.last_seen:
        if (now - sensor.last_seen.replace(tzinfo=None)).total_seconds() > OFFLINE_AFTER_SECONDS:
            sensor.status = "offline"
            changed = True
    elif sensor.status == "connecting" and sensor.last_seen:
        if (now - sensor.last_seen.replace(tzinfo=None)).total_seconds() > OFFLINE_AFTER_SECONDS:
            sensor.status = "offline"
            changed = True
    if changed:
        db.add(sensor)
        db.commit()
        existing = (
            db.query(MonitoringAlert)
            .filter(
                MonitoringAlert.user_id == user.id,
                MonitoringAlert.sensor_id == sensor.id,
                MonitoringAlert.alert_type == "offline",
                MonitoringAlert.status == "active",
            )
            .first()
        )
        if not existing and sensor.farm_id:
            message = f"Sensor \u201c{sensor.sensor_name or sensor.sensor_id}\u201d has been offline since {_stamp(sensor.last_seen)}."
            alert = MonitoringAlert(
                id=str(uuid.uuid4()),
                alert_id=_new_code("MAL"),
                user_id=user.id,
                farm_id=sensor.farm_id,
                plot_id=sensor.plot_id,
                sensor_id=sensor.id,
                alert_type="offline",
                message=message,
                severity="warning",
                status="active",
            )
            db.add(alert)
            _create_notification(
                db, user, "Sensor offline", message,
                ref_id=alert.id, ref_type="alert",
            )
            db.commit()


@router.post("/sensors/connect", response_model=dict, status_code=201)
def connect_sensor(
    body: SensorConnectIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.routers.sensors import Sensor

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

    sensor_type = body.sensor_type.strip().lower()
    if sensor_type and sensor_type not in VALID_METRICS:
        raise HTTPException(status_code=400, detail="Unsupported sensor metric")

    existing = None
    if body.device_identifier:
        existing = (
            db.query(Sensor)
            .filter(
                Sensor.user_id == current_user.id,
                Sensor.device_identifier == body.device_identifier.strip(),
            )
            .first()
        )
        if existing:
            existing.farm_id = farm.id
            existing.plot_id = plot.id if plot else None
            existing.status = "connected"
            existing.is_active = True
            existing.connected_at = existing.connected_at or _now()
            existing.last_seen = _now()
            db.add(existing)
            db.commit()
            return {
                "status": "success",
                "message": "Sensor reconnected",
                "data": _sensor_dict_with_context(
                    existing,
                    farm,
                    plot,
                ),
            }

    sensor = Sensor(
        id=str(uuid.uuid4()),
        sensor_id=_new_code("SEN"),
        user_id=current_user.id,
        farm_id=farm.id,
        plot_id=plot.id if plot else None,
        sensor_type=sensor_type,
        sensor_name=body.sensor_name or f"{_metric_label(sensor_type)} Sensor",
        location=body.location,
        latitude=plot.latitude if plot and not body.location else None,
        longitude=plot.longitude if plot and not body.location else None,
        is_active=True,
        status="connected",
        device_identifier=body.device_identifier.strip() if body.device_identifier else None,
        battery_level=body.battery_level,
        connected_at=_now(),
        last_seen=_now(),
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return {
        "status": "success",
        "message": "Sensor connected",
        "data": _sensor_dict_with_context(sensor, farm, plot),
    }


@router.post("/sensors/{sensor_id}/disconnect", response_model=dict)
def disconnect_sensor(
    sensor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.routers.sensors import Sensor

    sensor = (
        db.query(Sensor)
        .filter(Sensor.id == sensor_id, Sensor.user_id == current_user.id)
        .first()
    )
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    sensor.status = "disconnected"
    sensor.is_active = False
    db.add(sensor)
    db.commit()
    return {"status": "success", "message": "Sensor disconnected"}


@router.post("/sensors/{sensor_id}/readings", response_model=dict, status_code=201)
def ingest_reading(
    sensor_id: str,
    body: ReadingIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.routers.sensors import Sensor, SensorReading

    sensor = (
        db.query(Sensor)
        .filter(Sensor.id == sensor_id, Sensor.user_id == current_user.id)
        .first()
    )
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    metric = body.metric.strip().lower()
    if metric not in VALID_METRICS:
        raise HTTPException(status_code=400, detail="Unsupported metric")

    recorded = _now()
    if body.recorded_at:
        try:
            recorded = datetime.fromisoformat(str(body.recorded_at).replace("Z", ""))
        except ValueError:
            recorded = _now()

    reading = SensorReading(
        id=str(uuid.uuid4()),
        sensor_id=sensor.id,
        user_id=current_user.id,
        farm_id=sensor.farm_id,
        plot_id=sensor.plot_id,
        reading_type=metric,
        value=float(body.value),
        unit=body.unit or (METRICS.get(metric, ("", ""))[1] or None),
        recorded_at=recorded,
    )
    sensor.last_reading = {
        "metric": metric,
        "value": float(body.value),
        "unit": body.unit or (METRICS.get(metric, ("", ""))[1] or None),
        "recorded_at": _stamp(recorded),
    }
    sensor.status = "connected"
    sensor.is_active = True
    sensor.last_seen = recorded
    db.add(reading)
    db.add(sensor)
    db.commit()

    created = _evaluate_thresholds(db, current_user, sensor, metric, float(body.value))
    return {
        "status": "success",
        "message": "Reading recorded",
        "data": {
            "sensor_id": sensor.sensor_id,
            "metric": metric,
            "value": float(body.value),
            "recorded_at": _stamp(recorded),
            "alerts_created": created,
        },
    }


def _evaluate_thresholds(db: Session, user: User, sensor, metric: str, value: float) -> int:
    thr = (
        db.query(MonitoringThreshold)
        .filter(
            MonitoringThreshold.user_id == user.id,
            MonitoringThreshold.farm_id == sensor.farm_id,
            MonitoringThreshold.metric == metric,
            MonitoringThreshold.plot_id == sensor.plot_id,
        )
        .first()
    )
    if not thr:
        thr = (
            db.query(MonitoringThreshold)
            .filter(
                MonitoringThreshold.user_id == user.id,
                MonitoringThreshold.farm_id == sensor.farm_id,
                MonitoringThreshold.metric == metric,
                MonitoringThreshold.plot_id.is_(None),
            )
            .first()
        )
    if not thr:
        return 0

    below = thr.min_value is not None and value < thr.min_value
    above = thr.max_value is not None and value > thr.max_value
    if not below and not above:
        return 0

    kind = "below_threshold" if below else "above_threshold"
    label = _metric_label(metric)
    direction = "below" if below else "above"
    bound = thr.min_value if below else thr.max_value
    plot_name = None
    if sensor.plot_id:
        p = db.query(FarmPlot).get(sensor.plot_id)
        plot_name = p.plot_name if p else None
    message = (
        f"{label} is {direction} your configured threshold "
        f"({bound}{METRICS.get(metric, ('', ''))[1] or ''}) in plot "
        f"{plot_name or (sensor.plot_id or 'this farm')}."
    )

    existing = (
        db.query(MonitoringAlert)
        .filter(
            MonitoringAlert.user_id == user.id,
            MonitoringAlert.farm_id == sensor.farm_id,
            MonitoringAlert.plot_id == sensor.plot_id,
            MonitoringAlert.sensor_id == sensor.id,
            MonitoringAlert.metric == metric,
            MonitoringAlert.alert_type == kind,
            MonitoringAlert.status == "active",
        )
        .first()
    )
    if existing:
        return 0

    severity = "critical" if above else "warning"
    alert = MonitoringAlert(
        id=str(uuid.uuid4()),
        alert_id=_new_code("MAL"),
        user_id=user.id,
        farm_id=sensor.farm_id,
        plot_id=sensor.plot_id,
        sensor_id=sensor.id,
        alert_type=kind,
        metric=metric,
        message=message,
        severity=severity,
        status="active",
    )
    db.add(alert)
    _create_notification(
        db,
        user,
        f"Smart Monitoring: {label} alert",
        message,
        ref_id=alert.id,
        ref_type="alert",
    )
    db.commit()
    return 1


@router.get("/overview", response_model=dict)
def monitoring_overview(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    farm_ids = [f.id for f in farm_objs]
    plot_ids = [p.id for p in plots]

    from app.routers.sensors import Sensor

    # sensors within scope
    q = db.query(Sensor).filter(
        Sensor.user_id == current_user.id,
    )
    if farm_ids:
        q = q.filter(Sensor.farm_id.in_(farm_ids))
    sensors = q.all()
    if plot_ids:
        sensors = [s for s in sensors if s.plot_id in plot_ids or s.plot_id is None]
    for s in sensors:
        _refresh_offline_status(db, current_user, s)

    # latest readings
    latest = {}
    for s in sensors:
        if s.last_reading and s.last_reading.get("metric"):
            m = s.last_reading["metric"]
            cur = latest.get(m)
            if cur is None:
                latest[m] = {
                    "value": s.last_reading.get("value"),
                    "unit": s.last_reading.get("unit"),
                    "sensor_id": s.sensor_id,
                    "sensor_name": s.sensor_name,
                    "recorded_at": s.last_reading.get("recorded_at"),
                }
    # prefer newest recorded_at
    for s in sensors:
        if s.last_reading and s.last_reading.get("metric"):
            m = s.last_reading["metric"]
            cur = latest.get(m)
            if cur and cur.get("recorded_at") and s.last_reading.get("recorded_at"):
                if s.last_reading["recorded_at"] > cur["recorded_at"]:
                    latest[m] = {
                        "value": s.last_reading.get("value"),
                        "unit": s.last_reading.get("unit"),
                        "sensor_id": s.sensor_id,
                        "sensor_name": s.sensor_name,
                        "recorded_at": s.last_reading.get("recorded_at"),
                    }

    # crop info per plot
    plot_crops = {}
    for p in plots:
        cycle = (
            db.query(CropCycle)
            .filter(CropCycle.plot_id == p.id, CropCycle.status == "active")
            .order_by(CropCycle.created_at.desc())
            .first()
        )
        if not cycle:
            cycle = (
                db.query(CropCycle)
                .filter(CropCycle.plot_id == p.id)
                .order_by(CropCycle.created_at.desc())
                .first()
            )
        if cycle:
            crop = db.query(Crop).get(cycle.crop_id) if cycle.crop_id else None
            plot_crops[p.id] = {
                "cycle_id": cycle.id,
                "cycle_code": cycle.cycle_id,
                "crop_id": crop.id if crop else None,
                "crop_name": crop.name if crop else None,
                "variety": crop.variety if crop else None,
                "sowing_date": cycle.sowing_date,
                "expected_harvest_date": cycle.expected_harvest_date,
                "current_stage": cycle.current_stage,
                "status": cycle.status,
            }

    # thresholds
    thr_q = db.query(MonitoringThreshold).filter(
        MonitoringThreshold.user_id == current_user.id,
    )
    if farm_ids:
        thr_q = thr_q.filter(MonitoringThreshold.farm_id.in_(farm_ids))
    thresholds = thr_q.all()

    # monitoring status
    has_data = any(
        s.last_reading and s.last_reading.get("metric") for s in sensors
    )
    active_threshold_alerts = len(
        _alerts_for(
            db, current_user, farm_ids, plot_ids,
            status="active",
        )
    )
    if not has_data:
        farm_status = "no_data"
        farm_status_label = "Monitoring status unavailable"
    elif active_threshold_alerts:
        farm_status = "attention"
        farm_status_label = "Needs Attention"
    else:
        farm_status = "healthy"
        farm_status_label = "Healthy"

    # weather for first farm/plot with coordinates
    weather = None
    target = None
    lat = lon = None
    if plot_ids:
        target = plots[0]
        lat, lon = target.latitude, target.longitude
    if lat is None and farm_objs:
        target = farm_objs[0]
        lat, lon = target.latitude, target.longitude
    if lat and lon:
        try:
            weather = asyncio.run(get_current_weather(float(lat), float(lon)))
        except Exception:
            weather = None
        if weather:
            weather = dict(weather)
            loc_farm = None
            if isinstance(target, FarmPlot):
                loc_farm = db.query(Farm).get(target.farm_id) if target.farm_id else None
            else:
                loc_farm = target
            weather["location"] = (
                (getattr(loc_farm, "district", None) or "")
                + (" - " + getattr(target, "village", None) if getattr(target, "village", None) else "")
            ).strip(" -") or (getattr(loc_farm, "farm_name", None) or "")

    alerts = _alerts_for(db, current_user, farm_ids, plot_ids, limit=50)
    active_alerts = [a for a in alerts if a["status"] == "active"]

    farm_map = {f.id: f for f in farm_objs}
    plot_map = {p.id: p for p in plots}

    return {
        "status": "success",
        "data": {
            "farms": [
                {
                    "id": f.id,
                    "farm_id": f.farm_id,
                    "farm_name": f.farm_name,
                    "district": f.district,
                    "village": f.village,
                    "soil_type": f.soil_type,
                    "latitude": f.latitude,
                    "longitude": f.longitude,
                }
                for f in farm_objs
            ],
            "plots": [
                {
                    "id": p.id,
                    "plot_id": p.plot_id,
                    "plot_name": p.plot_name,
                    "farm_id": p.farm_id,
                    "farm_name": farm_map.get(p.farm_id).farm_name if farm_map.get(p.farm_id) else None,
                    "area": p.area,
                    "soil_type": p.soil_type,
                    "latitude": p.latitude,
                    "longitude": p.longitude,
                    "boundary_coordinates": p.boundary_coordinates,
                }
                for p in plots
            ],
            "sensors": [
                _sensor_dict_with_context(s, farm_map.get(s.farm_id), plot_map.get(s.plot_id))
                for s in sensors
            ],
            "current": latest,
            "metrics_meta": METRICS,
            "plot_crops": plot_crops,
            "thresholds": [
                {
                    "id": t.id,
                    "farm_id": t.farm_id,
                    "plot_id": t.plot_id,
                    "metric": t.metric,
                    "min_value": t.min_value,
                    "max_value": t.max_value,
                }
                for t in thresholds
            ],
            "farm_status": farm_status,
            "farm_status_label": farm_status_label,
            "has_data": has_data,
            "active_alerts": active_alerts,
            "recent_alerts": alerts[:10],
            "weather": weather,
            "refreshed_at": _stamp(_now()),
        },
    }


@router.get("/history", response_model=dict)
def monitoring_history(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    days: int = Query(7, ge=1, le=3650),
    metric: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    farm_ids = [f.id for f in farm_objs]
    plot_ids = [p.id for p in plots]
    from app.routers.sensors import Sensor, SensorReading

    sensor_ids = [
        s.id
        for s in db.query(Sensor).filter(
            Sensor.user_id == current_user.id,
        ).all()
        if (not farm_ids or s.farm_id in farm_ids)
        and (s.plot_id in plot_ids or s.plot_id is None)
    ]
    if not sensor_ids:
        return {"status": "success", "data": {}}
    since = _now() - timedelta(days=days)
    q = db.query(SensorReading).filter(
        SensorReading.sensor_id.in_(sensor_ids),
        SensorReading.recorded_at >= since,
    )
    # scope filtering via farm/plot on the reading record, else sensor match
    q = q.filter(
        SensorReading.plot_id.in_(plot_ids) if plot_ids
        else SensorReading.farm_id.in_(farm_ids)
    )
    if metric:
        if metric not in VALID_METRICS:
            raise HTTPException(status_code=400, detail="Unsupported metric")
        q = q.filter(SensorReading.reading_type == metric)
    rows = q.order_by(SensorReading.recorded_at.asc()).all()

    buckets = {}
    for r in rows:
        buckets.setdefault(r.reading_type, []).append({
            "t": _stamp(r.recorded_at),
            "value": r.value,
            "unit": r.unit,
        })

    # downsample to ~300 points per metric (real points only, no synthesis)
    for m in list(buckets.keys()):
        pts = buckets[m]
        if len(pts) > 300:
            step = len(pts) / 300.0
            buckets[m] = [pts[int(i * step)] for i in range(300)]
    return {"status": "success", "data": buckets}


@router.get("/alerts", response_model=dict)
def monitoring_alerts_list(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    farm_ids = [f.id for f in farm_objs]
    plot_ids = [p.id for p in plots]
    alerts = _alerts_for(db, current_user, farm_ids, plot_ids, status=status)
    return {"status": "success", "data": alerts}


@router.post("/alerts/{alert_id}/acknowledge", response_model=dict)
def acknowledge_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alert = (
        db.query(MonitoringAlert)
        .filter(MonitoringAlert.id == alert_id, MonitoringAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = "acknowledged"
    alert.is_read = True
    alert.read_at = _now()
    db.add(alert)
    db.commit()
    return {"status": "success", "message": "Alert acknowledged"}


@router.post("/alerts/{alert_id}/resolve", response_model=dict)
def resolve_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alert = (
        db.query(MonitoringAlert)
        .filter(MonitoringAlert.id == alert_id, MonitoringAlert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = "resolved"
    alert.is_read = True
    alert.read_at = _now()
    alert.resolved_at = _now()
    db.add(alert)
    db.commit()
    return {"status": "success", "message": "Alert resolved"}


@router.get("/thresholds", response_model=dict)
def monitoring_thresholds(
    farm_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(MonitoringThreshold).filter(
        MonitoringThreshold.user_id == current_user.id
    )
    if farm_id:
        q = q.filter(MonitoringThreshold.farm_id == farm_id)
    rows = q.all()
    return {
        "status": "success",
        "data": [
            {
                "id": t.id,
                "farm_id": t.farm_id,
                "plot_id": t.plot_id,
                "metric": t.metric,
                "min_value": t.min_value,
                "max_value": t.max_value,
            }
            for t in rows
        ],
    }


@router.post("/thresholds", response_model=dict, status_code=201)
def create_threshold(
    body: ThresholdIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.metric not in VALID_METRICS:
        raise HTTPException(status_code=400, detail="Unsupported metric")
    farm_objs, plots = _resolve_scope(db, current_user, body.farm_id, body.plot_id)
    farm = farm_objs[0]
    plot = plots[0] if plots and body.plot_id else None

    existing = (
        db.query(MonitoringThreshold)
        .filter(
            MonitoringThreshold.user_id == current_user.id,
            MonitoringThreshold.farm_id == farm.id,
            MonitoringThreshold.plot_id == (plot.id if plot else None),
            MonitoringThreshold.metric == body.metric,
        )
        .first()
    )
    if existing:
        existing.min_value = body.min_value
        existing.max_value = body.max_value
        existing.updated_at = _now()
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return {
            "status": "success",
            "message": "Threshold updated",
            "data": {"id": existing.id, "metric": existing.metric},
        }

    thr = MonitoringThreshold(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        farm_id=farm.id,
        plot_id=plot.id if plot else None,
        metric=body.metric,
        min_value=body.min_value,
        max_value=body.max_value,
    )
    db.add(thr)
    db.commit()
    db.refresh(thr)
    return {
        "status": "success",
        "message": "Threshold saved",
        "data": {"id": thr.id, "metric": thr.metric},
    }


@router.patch("/thresholds/{threshold_id}", response_model=dict)
def update_threshold(
    threshold_id: str,
    body: ThresholdIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    thr = (
        db.query(MonitoringThreshold)
        .filter(
            MonitoringThreshold.id == threshold_id,
            MonitoringThreshold.user_id == current_user.id,
        )
        .first()
    )
    if not thr:
        raise HTTPException(status_code=404, detail="Threshold not found")
    thr.min_value = body.min_value
    thr.max_value = body.max_value
    thr.updated_at = _now()
    db.add(thr)
    db.commit()
    return {"status": "success", "message": "Threshold updated", "data": {"id": thr.id}}


@router.post("/tasks", response_model=dict, status_code=201)
def create_monitoring_task(
    body: MonitoringTaskIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a real task in the existing Tasks system for the plot's crop cycle."""
    farm_objs, plots = _resolve_scope(db, current_user, body.farm_id, body.plot_id)
    farm = farm_objs[0]
    if not plots:
        raise HTTPException(status_code=400, detail="Select a plot to create a monitoring task")

    cycle = (
        db.query(CropCycle)
        .filter(CropCycle.plot_id == plots[0].id, CropCycle.status == "active")
        .order_by(CropCycle.created_at.desc())
        .first()
    )
    if not cycle:
        raise HTTPException(status_code=400, detail="No active crop cycle for this plot. Add a crop cycle under My Farm first.")

    task = CropTask(
        id=str(uuid.uuid4()),
        task_id=_new_code("FA-TSK"),
        crop_cycle_id=cycle.id,
        title=body.title,
        description=body.description,
        category=body.category or "Farm Management",
        due_date=body.due_date or (date.today() + timedelta(days=1)).isoformat(),
        priority=body.priority or "medium",
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    _create_notification(
        db,
        current_user,
        "Monitoring task created",
        f"Task \u201c{task.title}\u201d was added from Smart Monitoring.",
        ref_id=task.id,
        ref_type="task",
    )
    db.commit()
    return {
        "status": "success",
        "message": "Task created",
        "data": {
            "id": task.id,
            "task_id": task.task_id,
            "title": task.title,
            "category": task.category,
            "due_date": task.due_date,
            "priority": task.priority,
            "status": task.status,
        },
    }


@router.get("/insights", response_model=dict)
async def monitoring_insights(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    farm_ids = [f.id for f in farm_objs]
    plot_ids = [p.id for p in plots]
    from app.routers.sensors import Sensor

    sensors = db.query(Sensor).filter(
        Sensor.user_id == current_user.id,
    ).all()
    if farm_ids:
        sensors = [s for s in sensors if s.farm_id in farm_ids]
    if plot_ids:
        sensors = [s for s in sensors if s.plot_id in plot_ids or s.plot_id is None]

    observed = []
    for s in sensors:
        if s.last_reading and s.last_reading.get("metric"):
            observed.append(
                f"{s.sensor_name or s.sensor_id} ({s.sensor_type}): "
                f"{s.last_reading.get('value')}{s.last_reading.get('unit', '')} "
                f"at {s.last_reading.get('recorded_at')}"
            )
    alerts = _alerts_for(db, current_user, farm_ids, plot_ids, status="active", limit=10)
    if not observed and not alerts:
        return {
            "status": "success",
            "data": {
                "observed": [],
                "interpretation": "No monitoring data available for analysis yet.",
                "recommendations": [],
                "model": "-",
            },
        }

    summary_lines = [
        "OBSERVED MONITORING DATA (only real field readings):",
    ]
    summary_lines.append("\n".join(observed) if observed else "No recent sensor readings.")
    if alerts:
        summary_lines.append("ACTIVE ALERTS:")
        summary_lines.append("\n".join(f"- {a['message']}" for a in alerts))
    if plots:
        summary_lines.append(f"PLOT: {plots[0].plot_name} ({plots[0].farm.farm_name if plots[0].farm else ''})")

    prompt = (
        "You are a crop monitoring analyst for Farm Assist. Analyze these REAL observed "
        "sensor readings and alerts. Summarize: 1) trends and concerns, 2) any unusual "
        "readings, 3) recommended actions. Never invent sensor values. Keep it concise.\n\n"
        + "\n".join(summary_lines)
    )
    try:
        ai = await chat_with_ai(prompt)
    except Exception:
        ai = {"response": "Analysis temporarily unavailable.", "model": "local"}
    return {
        "status": "success",
        "data": {
            "observed": observed,
            "alerts": alerts,
            "interpretation": ai.get("response", ""),
            "recommendations": [],
            "model": ai.get("model", "local"),
        },
    }


@router.get("/drone/availability", response_model=dict)
def drone_availability(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    start = 9 * 60
    end = 17 * 60
    available = start <= now_min < end
    return {
        "status": "success",
        "data": {
            "available": available,
            "window_start": DRONE_WINDOW_START,
            "window_end": DRONE_WINDOW_END,
            "now": now.strftime("%H:%M"),
            "message": "Drone operations are available from 9:00 AM to 5:00 PM."
            if not available
            else "Drone operations are currently available.",
        },
    }


@router.get("/drone/context", response_model=dict)
def drone_context(
    farm_id: str,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authorized drone context. Server-side operating-hours gate + ownership."""
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    available = (9 * 60) <= now_min < (17 * 60)
    if not available:
        raise HTTPException(
            status_code=403,
            detail="Drone operations are available from 9:00 AM to 5:00 PM.",
        )

    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    farm = farm_objs[0] if farm_objs else None
    plot = plots[0] if plots else None
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    crop = None
    cycle = None
    if plot:
        cycle = (
            db.query(CropCycle)
            .filter(CropCycle.plot_id == plot.id, CropCycle.status == "active")
            .order_by(CropCycle.created_at.desc())
            .first()
        )
        if cycle:
            c = db.query(Crop).get(cycle.crop_id) if cycle.crop_id else None
            crop = {"name": c.name if c else None, "variety": c.variety if c else None}

    return {
        "status": "success",
        "data": {
            "farm": {
                "id": farm.id,
                "farm_id": farm.farm_id,
                "farm_name": farm.farm_name,
                "district": farm.district,
                "village": farm.village,
                "latitude": farm.latitude,
                "longitude": farm.longitude,
                "total_area": farm.total_area,
                "area_unit": farm.area_unit,
            },
            "plot": {
                "id": plot.id,
                "plot_id": plot.plot_id,
                "plot_name": plot.plot_name,
                "area": plot.area,
                "latitude": plot.latitude,
                "longitude": plot.longitude,
                "soil_type": plot.soil_type,
                "boundary_coordinates": plot.boundary_coordinates,
            }
            if plot
            else None,
            "crop": crop,
            "window": {
                "start": DRONE_WINDOW_START,
                "end": DRONE_WINDOW_END,
                "now": now.strftime("%H:%M"),
            },
            "stream": {
                "configured": False,
                "mode": "demo",
                "label": "Live drone feed is not currently configured.",
            },
        },
    }