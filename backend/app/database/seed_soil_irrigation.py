"""Seed script for Soil & Irrigation demo data.

Populates real database records for the demo farmer (phone 9849912345):
- Farm Plots
- Crop Cycles (linked to global Crop catalog)
- SoilRecords (historical soil health tests)
- IrrigationRecords (past irrigation logs)
- Sensors & SensorReadings (soil moisture & soil temperature series)
- MonitoringThresholds

Idempotent: skips any entity that already has records.
All rows are created as regular database entities owned by the user.
"""

from datetime import datetime, timedelta
import random

from sqlalchemy.orm import Session
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.models.crop import Crop, CropCycle, SoilRecord, IrrigationRecord
from app.models.monitoring import MonitoringThreshold
from app.routers.sensors import Sensor, SensorReading
from app.utils.auth import generate_id


DEMO_PHONE = "9849912345"


def seed_soil_irrigation_demo(db: Session) -> dict:
    user = db.query(User).filter(User.phone_number == DEMO_PHONE).first()
    if not user:
        user = db.query(User).filter(User.is_active == True).first()
    if not user:
        return {"status": "skipped", "reason": "No active user found to seed"}

    # 1. Farm
    farm = db.query(Farm).filter(Farm.user_id == user.id, Farm.is_active is not False).first()
    if not farm:
        farm_id = generate_id("FA-FRM", db, Farm)
        farm = Farm(
            farm_id=farm_id,
            user_id=user.id,
            farm_name="Green Field Model Farm",
            address="Near Canal Road, Tenali Mandal",
            village="Tenali",
            mandal="Tenali",
            district="Guntur",
            state="Andhra Pradesh",
            pincode="522201",
            latitude=16.2430,
            longitude=80.6410,
            total_area=5.0,
            area_unit="Acres",
            soil_type="Black Cotton Soil",
            water_source="Borewell & Canal",
            irrigation_method="Drip & Sprinkler",
            farm_type="Irrigated Crop Farm",
            is_active=True,
        )
        db.add(farm)
        db.commit()
        db.refresh(farm)

    # 2. Farm Plots
    existing_plots = db.query(FarmPlot).filter(FarmPlot.farm_id == farm.id).all()
    if not existing_plots:
        plot1_code = generate_id("FA-PLT", db, FarmPlot)
        p1 = FarmPlot(
            plot_id=plot1_code,
            farm_id=farm.id,
            plot_name="North Plot (Rice & Chilli)",
            area=2.5,
            latitude=16.2440,
            longitude=80.6420,
            soil_type="Clay Loam",
            is_active=True,
        )
        db.add(p1)

        plot2_code = generate_id("FA-PLT", db, FarmPlot)
        p2 = FarmPlot(
            plot_id=plot2_code,
            farm_id=farm.id,
            plot_name="South Plot (Cotton)",
            area=2.5,
            latitude=16.2420,
            longitude=80.6400,
            soil_type="Black Cotton Soil",
            is_active=True,
        )
        db.add(p2)
        db.commit()
        plots = [p1, p2]
    else:
        plots = existing_plots

    p1 = plots[0]
    p2 = plots[1] if len(plots) > 1 else plots[0]

    # 3. Crop Cycles
    existing_cycles = db.query(CropCycle).filter(CropCycle.farm_id == farm.id).all()
    if not existing_cycles:
        # Find catalog crops
        crops = db.query(Crop).all()
        crop_by_name = {c.name.strip().lower(): c for c in crops}

        paddy_crop = crop_by_name.get("rice") or crop_by_name.get("chilli") or (crops[0] if crops else None)
        chilli_crop = crop_by_name.get("chilli") or (crops[1] if len(crops) > 1 else paddy_crop)
        cotton_crop = crop_by_name.get("cotton") or (crops[2] if len(crops) > 2 else paddy_crop)

        created_cycles = []
        if paddy_crop:
            c1_code = generate_id("FA-CYC", db, CropCycle)
            c1 = CropCycle(
                cycle_id=c1_code,
                farm_id=farm.id,
                plot_id=p1.id,
                crop_id=paddy_crop.id,
                sowing_date=(datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%d"),
                expected_harvest_date=(datetime.utcnow() + timedelta(days=60)).strftime("%Y-%m-%d"),
                seed_quantity=25.0,
                seed_unit="kg",
                fertilizer_usage="Basal DAP 50kg, Top dressing Urea 40kg at 30 days",
                pesticide_usage="Neem oil spray 2L/acre",
                irrigation_schedule="Irrigate every 3 days; maintain 3-5 cm standing water during tillering stage.",
                current_stage="Vegetative / Tillering",
                status="active",
            )
            db.add(c1)
            created_cycles.append(c1)

        if chilli_crop and chilli_crop.id != (paddy_crop.id if paddy_crop else None):
            c2_code = generate_id("FA-CYC", db, CropCycle)
            c2 = CropCycle(
                cycle_id=c2_code,
                farm_id=farm.id,
                plot_id=p1.id,
                crop_id=chilli_crop.id,
                sowing_date=(datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%d"),
                expected_harvest_date=(datetime.utcnow() + timedelta(days=75)).strftime("%Y-%m-%d"),
                seed_quantity=0.5,
                seed_unit="kg",
                fertilizer_usage="10:26:26 NPK 50kg + Compost 2 tonnes",
                pesticide_usage="Biological bio-pesticide spray for thrips",
                irrigation_schedule="Drip irrigation 2 hours every alternate day; avoid waterlogging.",
                current_stage="Flowering & Fruit Set",
                status="active",
            )
            db.add(c2)
            created_cycles.append(c2)

        if cotton_crop:
            c3_code = generate_id("FA-CYC", db, CropCycle)
            c3 = CropCycle(
                cycle_id=c3_code,
                farm_id=farm.id,
                plot_id=p2.id,
                crop_id=cotton_crop.id,
                sowing_date=(datetime.utcnow() - timedelta(days=75)).strftime("%Y-%m-%d"),
                expected_harvest_date=(datetime.utcnow() + timedelta(days=75)).strftime("%Y-%m-%d"),
                seed_quantity=2.0,
                seed_unit="packets",
                fertilizer_usage="Urea 50kg split in 3 doses, MOP 30kg",
                pesticide_usage="Pheromone traps installed + targeted spray",
                irrigation_schedule="Drip irrigation 3 hours every 4 days. Critical watering at square and boll formation.",
                current_stage="Boll Development",
                status="active",
            )
            db.add(c3)
            created_cycles.append(c3)

        db.commit()

    # 4. Soil Records
    p1_soil_count = db.query(SoilRecord).filter(SoilRecord.plot_id == p1.id).count()
    if p1_soil_count == 0:
        s1 = SoilRecord(
            plot_id=p1.id,
            ph_level=6.6,
            nitrogen=340.0,
            phosphorus=22.0,
            potassium=210.0,
            organic_matter=1.4,
            moisture=48.0,
            soil_type="Clay Loam",
            test_date=datetime.utcnow() - timedelta(days=60),
            notes="Baseline soil testing done prior to Paddy sowing.",
        )
        s2 = SoilRecord(
            plot_id=p1.id,
            ph_level=6.5,
            nitrogen=350.0,
            phosphorus=24.0,
            potassium=220.0,
            organic_matter=1.5,
            moisture=52.0,
            soil_type="Clay Loam",
            test_date=datetime.utcnow() - timedelta(days=30),
            notes="Mid-season soil check. Nutrients in recommended range.",
        )
        s3 = SoilRecord(
            plot_id=p1.id,
            ph_level=6.4,
            nitrogen=360.0,
            phosphorus=25.0,
            potassium=215.0,
            organic_matter=1.5,
            moisture=44.0,
            soil_type="Clay Loam",
            test_date=datetime.utcnow() - timedelta(days=4),
            notes="Recent soil health test. Soil structure good, moisture adequate.",
        )
        db.add_all([s1, s2, s3])

    p2_soil_count = db.query(SoilRecord).filter(SoilRecord.plot_id == p2.id).count()
    if p2_soil_count == 0:
        s4 = SoilRecord(
            plot_id=p2.id,
            ph_level=7.2,
            nitrogen=290.0,
            phosphorus=14.0,
            potassium=150.0,
            organic_matter=0.9,
            moisture=38.0,
            soil_type="Black Cotton Soil",
            test_date=datetime.utcnow() - timedelta(days=45),
            notes="Initial Cotton field soil test.",
        )
        s5 = SoilRecord(
            plot_id=p2.id,
            ph_level=7.1,
            nitrogen=310.0,
            phosphorus=16.0,
            potassium=165.0,
            organic_matter=1.0,
            moisture=36.0,
            soil_type="Black Cotton Soil",
            test_date=datetime.utcnow() - timedelta(days=6),
            notes="Routine soil test. Organic matter slightly low.",
        )
        db.add_all([s4, s5])
    db.commit()

    # 5. Irrigation Records
    p1_irr_count = db.query(IrrigationRecord).filter(IrrigationRecord.plot_id == p1.id).count()
    if p1_irr_count == 0:
        i1 = IrrigationRecord(
            plot_id=p1.id,
            method="Drip",
            duration_minutes=120.0,
            water_quantity=2500.0,
            water_unit="Liters",
            irrigation_date=datetime.utcnow() - timedelta(days=12),
            notes="Morning drip cycle.",
        )
        i2 = IrrigationRecord(
            plot_id=p1.id,
            method="Drip",
            duration_minutes=150.0,
            water_quantity=3000.0,
            water_unit="Liters",
            irrigation_date=datetime.utcnow() - timedelta(days=6),
            notes="Full plot drip watering.",
        )
        i3 = IrrigationRecord(
            plot_id=p1.id,
            method="Drip",
            duration_minutes=120.0,
            water_quantity=2500.0,
            water_unit="Liters",
            irrigation_date=datetime.utcnow() - timedelta(days=2),
            notes="Regular scheduled drip irrigation.",
        )
        db.add_all([i1, i2, i3])

    p2_irr_count = db.query(IrrigationRecord).filter(IrrigationRecord.plot_id == p2.id).count()
    if p2_irr_count == 0:
        i4 = IrrigationRecord(
            plot_id=p2.id,
            method="Sprinkler",
            duration_minutes=90.0,
            water_quantity=2000.0,
            water_unit="Liters",
            irrigation_date=datetime.utcnow() - timedelta(days=10),
            notes="Sprinkler session for Cotton field.",
        )
        i5 = IrrigationRecord(
            plot_id=p2.id,
            method="Sprinkler",
            duration_minutes=90.0,
            water_quantity=2000.0,
            water_unit="Liters",
            irrigation_date=datetime.utcnow() - timedelta(days=3),
            notes="Routine sprinkler watering.",
        )
        db.add_all([i4, i5])
    db.commit()

    # 6. Sensors & SensorReadings
    sensor_count = db.query(Sensor).filter(Sensor.user_id == user.id, Sensor.farm_id == farm.id).count()
    if sensor_count == 0:
        sens1_code = generate_id("FA-SNS", db, Sensor)
        s1 = Sensor(
            sensor_id=sens1_code,
            user_id=user.id,
            farm_id=farm.id,
            plot_id=p1.id,
            sensor_type="soil_moisture",
            sensor_name="North Plot Moisture Node",
            location="North Plot - Central",
            is_active=True,
            status="connected",
            battery_level=88.0,
            last_reading={
                "metric": "soil_moisture",
                "value": 46.0,
                "unit": "%",
                "recorded_at": (datetime.utcnow() - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S"),
            },
            connected_at=datetime.utcnow() - timedelta(days=30),
            last_seen=datetime.utcnow() - timedelta(minutes=15),
        )
        db.add(s1)

        sens2_code = generate_id("FA-SNS", db, Sensor)
        s2 = Sensor(
            sensor_id=sens2_code,
            user_id=user.id,
            farm_id=farm.id,
            plot_id=p2.id,
            sensor_type="soil_moisture",
            sensor_name="South Plot Moisture Node",
            location="South Plot - Sector A",
            is_active=True,
            status="connected",
            battery_level=79.0,
            last_reading={
                "metric": "soil_moisture",
                "value": 36.0,
                "unit": "%",
                "recorded_at": (datetime.utcnow() - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S"),
            },
            connected_at=datetime.utcnow() - timedelta(days=30),
            last_seen=datetime.utcnow() - timedelta(minutes=20),
        )
        db.add(s2)
        db.commit()

        # Add time-series sensor readings over last 7 days
        for day in range(7, -1, -1):
            t_stamp = datetime.utcnow() - timedelta(days=day, hours=random.randint(1, 4))
            # Plot 1 moisture around 42-52%
            m1_val = round(random.uniform(42.0, 52.0), 1)
            sr1 = SensorReading(
                sensor_id=s1.id,
                user_id=user.id,
                farm_id=farm.id,
                plot_id=p1.id,
                reading_type="soil_moisture",
                value=m1_val,
                unit="%",
                recorded_at=t_stamp,
            )
            # Plot 1 soil temperature around 25-28C
            t1_val = round(random.uniform(25.0, 28.5), 1)
            sr1_t = SensorReading(
                sensor_id=s1.id,
                user_id=user.id,
                farm_id=farm.id,
                plot_id=p1.id,
                reading_type="soil_temperature",
                value=t1_val,
                unit="°C",
                recorded_at=t_stamp,
            )
            # Plot 2 moisture around 32-39%
            m2_val = round(random.uniform(32.0, 39.0), 1)
            sr2 = SensorReading(
                sensor_id=s2.id,
                user_id=user.id,
                farm_id=farm.id,
                plot_id=p2.id,
                reading_type="soil_moisture",
                value=m2_val,
                unit="%",
                recorded_at=t_stamp,
            )
            db.add_all([sr1, sr1_t, sr2])
        db.commit()

    # 7. Monitoring Thresholds
    thr_count = db.query(MonitoringThreshold).filter(MonitoringThreshold.user_id == user.id, MonitoringThreshold.farm_id == farm.id).count()
    if thr_count == 0:
        t1 = MonitoringThreshold(
            user_id=user.id,
            farm_id=farm.id,
            plot_id=p1.id,
            metric="soil_moisture",
            min_value=35.0,
            max_value=75.0,
        )
        t2 = MonitoringThreshold(
            user_id=user.id,
            farm_id=farm.id,
            plot_id=p2.id,
            metric="soil_moisture",
            min_value=30.0,
            max_value=65.0,
        )
        db.add_all([t1, t2])
        db.commit()

    return {
        "status": "seeded",
        "user_phone": user.phone_number,
        "farm_id": farm.farm_id,
        "plots": [p1.plot_name, p2.plot_name],
    }
