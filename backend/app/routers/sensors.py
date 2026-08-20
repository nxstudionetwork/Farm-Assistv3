from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.connection import get_db
from app.models.user import User
from app.models.farm import gen_uuid
from app.database.base import Base
from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Text, JSON, Boolean
from app.utils.auth import get_current_user, get_optional_user

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


MOCK_SENSORS = [
    {"sensor_id": "FA-SEN-000001", "sensor_type": "soil_moisture", "sensor_name": "Field-1 Soil Moisture", "location": "North Field", "is_active": True, "battery_level": 85, "last_reading": {"value": 42.5, "unit": "%", "status": "normal"}},
    {"sensor_id": "FA-SEN-000002", "sensor_type": "temperature", "sensor_name": "Greenhouse Temp", "location": "Greenhouse A", "is_active": True, "battery_level": 92, "last_reading": {"value": 28.3, "unit": "°C", "status": "normal"}},
    {"sensor_id": "FA-SEN-000003", "sensor_type": "humidity", "sensor_name": "Air Humidity Monitor", "location": "East Field", "is_active": True, "battery_level": 78, "last_reading": {"value": 65.0, "unit": "%", "status": "normal"}},
    {"sensor_id": "FA-SEN-000004", "sensor_type": "water_level", "sensor_name": "Borewell Level", "location": "Borewell #1", "is_active": True, "battery_level": 45, "last_reading": {"value": 3.2, "unit": "m", "status": "warning"}},
    {"sensor_id": "FA-SEN-000005", "sensor_type": "rain", "sensor_name": "Rain Gauge", "location": "Roof Top", "is_active": True, "battery_level": 60, "last_reading": {"value": 0.0, "unit": "mm", "status": "normal"}},
    {"sensor_id": "FA-SEN-000006", "sensor_type": "wind", "sensor_name": "Wind Speed Meter", "location": "Tower", "is_active": False, "battery_level": 15, "last_reading": {"value": 12.0, "unit": "km/h", "status": "low_battery"}},
]


@router.get("/sensors", response_model=dict)
def list_sensors(
    sensor_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    sensors = MOCK_SENSORS
    if sensor_type:
        sensors = [s for s in sensors if s["sensor_type"] == sensor_type]
    if is_active is not None:
        sensors = [s for s in sensors if s["is_active"] == is_active]
    return {"status": "success", "data": sensors, "total": len(sensors), "provider": "demo"}


@router.get("/sensors/{sensor_id}", response_model=dict)
def get_sensor(sensor_id: str):
    for s in MOCK_SENSORS:
        if s["sensor_id"] == sensor_id:
            return {"status": "success", "data": s}
    raise HTTPException(status_code=404, detail="Sensor not found")


MOCK_READINGS = {
    "soil_moisture": [{"value": 42.5, "recorded_at": "2026-07-30T10:00:00Z"}, {"value": 40.2, "recorded_at": "2026-07-30T09:00:00Z"}, {"value": 38.0, "recorded_at": "2026-07-30T08:00:00Z"}],
    "temperature": [{"value": 28.3, "recorded_at": "2026-07-30T10:00:00Z"}, {"value": 27.5, "recorded_at": "2026-07-30T09:00:00Z"}, {"value": 26.1, "recorded_at": "2026-07-30T08:00:00Z"}],
    "humidity": [{"value": 65.0, "recorded_at": "2026-07-30T10:00:00Z"}, {"value": 68.2, "recorded_at": "2026-07-30T09:00:00Z"}, {"value": 72.0, "recorded_at": "2026-07-30T08:00:00Z"}],
}


@router.get("/sensors/{sensor_type}/readings", response_model=dict)
def get_readings(sensor_type: str, hours: int = Query(24, ge=1, le=168)):
    readings = MOCK_READINGS.get(sensor_type, [])
    return {"status": "success", "data": readings, "sensor_type": sensor_type}
