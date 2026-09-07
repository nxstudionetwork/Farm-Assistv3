from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Boolean, JSON
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.base import Base
from app.models.farm import gen_uuid
from app.models.user import User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["Sensors"])


class Sensor(Base):
    __tablename__ = "sensors"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    sensor_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    sensor_type = Column(String(50), nullable=False)
    sensor_name = Column(String(200), nullable=True)
    location = Column(String(200), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    battery_level = Column(Float, nullable=True)
    last_reading = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    sensor_id = Column(String(36), ForeignKey("sensors.id"), nullable=False)
    reading_type = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)


def _sensor_dict(s: Sensor) -> dict:
    return {
        "id": s.id,
        "sensor_id": s.sensor_id,
        "sensor_type": s.sensor_type,
        "sensor_name": s.sensor_name,
        "location": s.location,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "is_active": s.is_active,
        "battery_level": s.battery_level,
        "last_reading": s.last_reading,
        "created_at": str(s.created_at) if s.created_at else None,
    }


@router.get("/sensors", response_model=dict)
def list_sensors(
    sensor_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List sensors registered to the current farmer (never other users' devices)."""
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
    return {"status": "success", "data": [_sensor_dict(s) for s in items], "total": total}


@router.get("/sensors/{sensor_type}/readings", response_model=dict)
def get_readings(
    sensor_type: str,
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sensors = (
        db.query(Sensor)
        .filter(Sensor.user_id == current_user.id, Sensor.sensor_type == sensor_type)
        .all()
    )
    if not sensors:
        return {"status": "success", "data": [], "sensor_type": sensor_type}

    sensor_ids = [s.id for s in sensors]
    since = datetime.utcnow() - timedelta(hours=hours)
    readings = (
        db.query(SensorReading)
        .filter(
            SensorReading.sensor_id.in_(sensor_ids),
            SensorReading.recorded_at >= since,
        )
        .order_by(SensorReading.recorded_at.desc())
        .limit(200)
        .all()
    )
    return {
        "status": "success",
        "data": [
            {
                "value": r.value,
                "unit": r.unit,
                "recorded_at": str(r.recorded_at) if r.recorded_at else None,
            }
            for r in readings
        ],
        "sensor_type": sensor_type,
    }


@router.get("/sensors/{sensor_id}", response_model=dict)
def get_sensor(
    sensor_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sensor = (
        db.query(Sensor)
        .filter(
            Sensor.user_id == current_user.id,
            (Sensor.id == sensor_id) | (Sensor.sensor_id == sensor_id),
        )
        .first()
    )
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return {"status": "success", "data": _sensor_dict(sensor)}