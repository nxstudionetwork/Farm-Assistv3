"""Seed the unclaimed sensor device catalogue.

Registers realistic IoT devices (sensors) in the ``sensors`` table with the
reserved owner ``system-device-registry`` so farmers can discover and claim
them through the Sensors page verify -> connect flow. Idempotent: it only
adds devices when the unclaimed catalogue is below the target size.
"""

import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.models  # noqa: F401  (register mappers incl. Sensor)
import app.routers.sensors  # noqa: F401

from sqlalchemy import or_
from app.database.connection import SessionLocal, engine, Base
from app.models.farm import gen_uuid, Farm
from app.routers.sensors import Sensor, UNCLAIMED_OWNER, SENSOR_TYPES

DEVICES_PER_TYPE = 3
NAME_PREFIX = {
    "soil_moisture": "Soil Moisture Node",
    "soil_temperature": "Soil Temperature Node",
    "temperature": "Air Temperature Node",
    "humidity": "Humidity Node",
    "water_level": "Water Level Sensor",
    "light": "Light Sensor",
    "air_quality": "Air Quality Node",
}


def _device_code(sensor_type: str, index: int) -> str:
    abbr = {
        "soil_moisture": "SM",
        "soil_temperature": "ST",
        "temperature": "AT",
        "humidity": "HM",
        "water_level": "WL",
        "light": "LT",
        "air_quality": "AQ",
    }[sensor_type]
    return f"SENSOR-{abbr}-{index:05d}"


def seed_sensor_devices(db, per_type=DEVICES_PER_TYPE):
    locations = (
        db.query(Farm.village, Farm.district, Farm.state)
        .filter(Farm.is_active == True)  # noqa: E712
        .distinct()
        .all()
    )
    loc_pool = [(v or "", d or "", s or "") for v, d, s in locations]

    added = 0
    for meta in SENSOR_TYPES:
        st = meta["key"]
        existing = (
            db.query(Sensor)
            .filter(Sensor.user_id == UNCLAIMED_OWNER, Sensor.sensor_type == st)
            .count()
        )
        for i in range(existing, per_type):
            code = _device_code(st, i + 1)
            existing_any = (
                db.query(Sensor)
                .filter(or_(Sensor.device_identifier == code, Sensor.sensor_id == code))
                .first()
            )
            if existing_any:
                # id may have been claimed already; bump the counter range
                continue
            village, district, state = loc_pool[(i + existing) % len(loc_pool)] if loc_pool else ("", "", "")
            sensor = Sensor(
                id=gen_uuid(),
                sensor_id=code,
                user_id=UNCLAIMED_OWNER,
                device_identifier=code,
                sensor_type=st,
                sensor_name=f"{NAME_PREFIX.get(st, st.capitalize())} {code.split('-')[-1]}",
                location=(village or "").strip() or None,
                is_active=True,
                status="ready",
                battery_level=None,
            )
            db.add(sensor)
            added += 1
    if added:
        db.commit()
    return {"devices_seeded": added}


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        res = seed_sensor_devices(db)
        total = db.query(Sensor).filter(Sensor.user_id == UNCLAIMED_OWNER).count()
        print("Sensor device catalogue:")
        print(f"  Added: {res['devices_seeded']}")
        print(f"  Unclaimed devices total: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()