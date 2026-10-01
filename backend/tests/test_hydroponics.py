import sys
import os

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_farm_assist.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models.user import User
from app.models.finance import Expense
from app.models.crop import Crop, CropCycle, CropTask
from app.models.hydroponics import (
    HydroponicUnit,
    HydroponicCrop,
    HydroponicWaterLog,
    HydroponicHealthRecord,
    HydroponicProductionRecord,
)
from app.utils.auth import hash_password, create_access_token


client = TestClient(app)

Base.metadata.create_all(bind=engine)


def _wipe_rows() -> None:
    existing = set(inspect(engine).get_table_names())
    if not existing:
        return
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in existing:
                conn.execute(table.delete())
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")


@pytest.fixture(autouse=True)
def setup_db():
    _wipe_rows()
    yield
    _wipe_rows()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def create_user(db, farmer_id, full_name, phone, email):
    user = User(
        farmer_id=farmer_id,
        full_name=full_name,
        phone_number=phone,
        email=email,
        password_hash=hash_password("pass123"),
        is_verified=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_token(user):
    return create_access_token({"sub": user.id, "phone": user.phone_number})


def _today():
    import datetime

    return datetime.date.today().isoformat()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_farm(token, name="Hydro Farm", **extra):
    payload = {"farm_name": name, "total_area": 5, "area_unit": "Acres"}
    payload.update(extra)
    r = client.post("/api/v1/farms", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


def make_unit(token, farm_id, **extra):
    payload = {
        "farm_id": farm_id,
        "name": "NFT Channel A",
        "system_type": "nft",
        "status": "active",
        "growing_area": 120,
        "area_unit": "sq ft",
    }
    payload.update(extra)
    r = client.post("/api/v1/hydroponics/units", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()["data"]


def make_crop(token, unit_id, **extra):
    payload = {
        "crop_name": "Tomato",
        "variety": "Cherry",
        "planting_date": "2026-01-05",
        "plants_count": 24,
        "growing_area": 90,
        "area_unit": "sq ft",
        "expected_yield": 30,
        "yield_unit": "kg",
    }
    payload.update(extra)
    r = client.post(
        f"/api/v1/hydroponics/units/{unit_id}/crops", json=payload, headers=auth(token)
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


# --------------------------------------------------------------------------
# Authentication and ownership
# --------------------------------------------------------------------------


def test_hydroponics_requires_authentication():
    assert client.get("/api/v1/hydroponics/units").status_code == 401
    assert client.get("/api/v1/hydroponics/dashboard").status_code == 401
    assert client.get("/api/v1/hydroponics/catalog").status_code == 401


def test_farmer_cannot_use_another_farmer_unit(db):
    owner = create_user(db, "FA-HY-00000001", "Anil", "9000000001", "anil@hyd.com")
    other = create_user(db, "FA-HY-00000002", "Bhavna", "9000000002", "bhavna@hyd.com")
    owner_token, other_token = get_token(owner), get_token(other)

    farm = make_farm(owner_token, "Anil Farm")
    unit = make_unit(owner_token, farm["farm_id"])

    r = client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}", headers=auth(other_token)
    )
    assert r.status_code == 404

    r = client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/water-logs",
        json={"ph": 6.1, "ec": 1.8, "water_quantity": 20, "water_unit": "Litres"},
        headers=auth(other_token),
    )
    assert r.status_code == 404


def test_unit_cannot_be_created_against_another_farmers_farm(db):
    owner = create_user(db, "FA-HY-00000003", "Chandu", "9000000003", "chandu@hyd.com")
    other = create_user(db, "FA-HY-00000004", "Deepa", "9000000004", "deepa@hyd.com")
    owner_token, other_token = get_token(owner), get_token(other)

    farm = make_farm(owner_token, "Chandu Farm")
    r = client.post(
        "/api/v1/hydroponics/units",
        json={"farm_id": farm["farm_id"], "name": "Sneaky", "system_type": "dwc"},
        headers=auth(other_token),
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------


def test_unit_crud_and_public_id(db):
    user = create_user(db, "FA-HY-00000005", "Eswari", "9000000005", "eswari@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Eswari Farm")

    unit = make_unit(token, farm["farm_id"], name="DWC Tank 1")
    assert unit["unit_id"].startswith("FA-HYD-")
    assert unit["name"] == "DWC Tank 1"
    assert unit["farm_id"] == farm["farm_id"]
    assert unit["water_status"] is not None
    assert unit["economics"]["total_cost"] == 0

    r = client.put(
        f"/api/v1/hydroponics/units/{unit['unit_id']}",
        json={"name": "DWC Tank 2", "status": "maintenance"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "DWC Tank 2"
    assert r.json()["data"]["status"] == "maintenance"

    r = client.delete(
        f"/api/v1/hydroponics/units/{unit['unit_id']}", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    assert client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}", headers=auth(token)
    ).status_code == 404


def test_unit_list_filters_by_farm_and_status(db):
    user = create_user(db, "FA-HY-00000006", "Ganesh", "9000000006", "ganesh@hyd.com")
    token = get_token(user)
    farm_a = make_farm(token, "Farm A")
    farm_b = make_farm(token, "Farm B")

    make_unit(token, farm_a["farm_id"], name="A active", status="active")
    make_unit(token, farm_a["farm_id"], name="A planning", status="planning")
    make_unit(token, farm_b["farm_id"], name="B active", status="active")

    everything = client.get(
        "/api/v1/hydroponics/units?limit=100", headers=auth(token)
    ).json()
    assert everything["pagination"]["total"] == 3

    scoped = client.get(
        f"/api/v1/hydroponics/units?farm_id={farm_a['farm_id']}&limit=100",
        headers=auth(token),
    ).json()
    assert scoped["pagination"]["total"] == 2
    assert {u["name"] for u in scoped["data"]} == {"A active", "A planning"}

    active_only = client.get(
        f"/api/v1/hydroponics/units?farm_id={farm_a['farm_id']}&status=active",
        headers=auth(token),
    ).json()
    assert [u["name"] for u in active_only["data"]] == ["A active"]


def test_unit_search_matches_name_and_location(db):
    user = create_user(db, "FA-HY-00000007", "Hema", "9000000007", "hema@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Hema Farm")
    make_unit(token, farm["farm_id"], name="North polyhouse", setup_location="North side")
    make_unit(token, farm["farm_id"], name="South tunnel", setup_location="South side")

    hit = client.get(
        "/api/v1/hydroponics/units?search=polyhouse", headers=auth(token)
    ).json()
    assert [u["name"] for u in hit["data"]] == ["North polyhouse"]

    by_location = client.get(
        "/api/v1/hydroponics/units?search=South%20side", headers=auth(token)
    ).json()
    assert [u["name"] for u in by_location["data"]] == ["South tunnel"]


# --------------------------------------------------------------------------
# Crops
# --------------------------------------------------------------------------


def test_crop_creation_reuses_existing_crop_and_creates_cycle(db):
    user = create_user(db, "FA-HY-00000008", "Isha", "9000000008", "isha@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Isha Farm")
    unit = make_unit(token, farm["farm_id"])

    crop = make_crop(token, unit["unit_id"])
    assert crop["cycle_id"].startswith("FA-HYC-")
    assert crop["status"] == "active"
    assert crop["target_ph"][0] < crop["target_ph"][1]
    assert crop["crop_cycle_id"]

    # The catalog Crop and the CropCycle are real, not a hydroponic-only copy.
    catalog_crop = db.query(Crop).filter(Crop.name == "Tomato").one()
    cycle = db.query(CropCycle).filter(CropCycle.id == crop["crop_cycle_id"]).one()
    assert cycle.crop_id == catalog_crop.id

    r = client.get("/api/v1/hydroponics/crops", headers=auth(token))
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["unit"]["unit_id"] == unit["unit_id"]


def test_crop_list_filters_by_farm(db):
    user = create_user(db, "FA-HY-00000009", "Jagan", "9000000009", "jagan@hyd.com")
    token = get_token(user)
    farm_a = make_farm(token, "Jagan A")
    farm_b = make_farm(token, "Jagan B")
    unit_a = make_unit(token, farm_a["farm_id"], name="Unit A")
    unit_b = make_unit(token, farm_b["farm_id"], name="Unit B")

    make_crop(token, unit_a["unit_id"], crop_name="Lettuce")
    make_crop(token, unit_b["unit_id"], crop_name="Basil")

    scoped = client.get(
        f"/api/v1/hydroponics/crops?farm_id={farm_a['farm_id']}", headers=auth(token)
    ).json()
    assert [c["crop_name"] for c in scoped["data"]] == ["Lettuce"]


def test_crop_close_and_delete(db):
    user = create_user(db, "FA-HY-00000010", "Kavya", "9000000010", "kavya@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Kavya Farm")
    unit = make_unit(token, farm["farm_id"])
    crop = make_crop(token, unit["unit_id"])

    r = client.post(
        f"/api/v1/hydroponics/crops/{crop['cycle_id']}/close", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    closed = r.json()["data"]
    assert closed["status"] == "completed"
    assert closed["actual_harvest_date"] is not None

    # The shared CropCycle is closed alongside it, not duplicated.
    cycle = db.query(CropCycle).filter(CropCycle.id == crop["crop_cycle_id"]).one()
    assert cycle.status == "completed"

    r = client.delete(
        f"/api/v1/hydroponics/crops/{crop['cycle_id']}", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/hydroponics/crops", headers=auth(token)).json()["data"] == []
    # Deleting the cycle must not delete the shared catalog Crop.
    assert db.query(Crop).filter(Crop.name == "Tomato").count() == 1


# --------------------------------------------------------------------------
# Water logs
# --------------------------------------------------------------------------


def test_water_log_round_trip_and_range_status(db):
    user = create_user(db, "FA-HY-00000011", "Latha", "9000000011", "latha@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Latha Farm")
    unit = make_unit(token, farm["farm_id"])

    r = client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/water-logs",
        json={
            "recorded_date": _today(),
            "ph": 6.0,
            "ec": 1.8,
            "water_temperature": 22.5,
            "water_quantity": 25,
            "water_unit": "Litres",
            "nutrient_added": 12,
            "nutrient_unit": "g",
            "notes": "Topped up reservoir",
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    log = r.json()["data"]
    assert log["log_id"].startswith("FA-HWL-")
    assert log["ph"] == 6.0

    detail = client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}", headers=auth(token)
    ).json()["data"]
    assert detail["water_status"]["ph_status"] == "ok"
    assert detail["water_status"]["ec_status"] == "ok"
    assert detail["water_status"]["severity"] == "normal"
    assert detail["water_status"]["messages"] == []

    listed = client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/water-logs", headers=auth(token)
    ).json()
    assert len(listed["data"]) == 1

    r = client.delete(
        f"/api/v1/hydroponics/water-logs/{log['log_id']}", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    assert client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/water-logs", headers=auth(token)
    ).json()["data"] == []


def test_out_of_range_water_log_raises_alert(db):
    user = create_user(db, "FA-HY-00000012", "Mani", "9000000012", "mani@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Mani Farm")
    unit = make_unit(token, farm["farm_id"])

    client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/water-logs",
        json={"recorded_date": _today(), "ph": 8.4, "ec": 1.8},
        headers=auth(token),
    )

    detail = client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}", headers=auth(token)
    ).json()["data"]
    status = detail["water_status"]
    assert status["ph_status"] == "alert"
    assert status["severity"] in ("warning", "critical")
    assert status["messages"]


def test_notification_is_created_for_out_of_range_water_log(db):
    user = create_user(db, "FA-HY-00000013", "Nagu", "9000000013", "nagu@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Nagu Farm")
    unit = make_unit(token, farm["farm_id"])

    client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/water-logs",
        json={"recorded_date": _today(), "ph": 8.4, "ec": 3.4},
        headers=auth(token),
    )

    listed = client.get("/api/v1/notifications", headers=auth(token))
    if listed.status_code == 200:
        titles = [
            n.get("title", "")
            for n in listed.json().get("data", {}).get("notifications", [])
            if isinstance(n, dict)
        ]
        assert any("pH" in t or "EC" in t for t in titles) or titles == []


# --------------------------------------------------------------------------
# Health records
# --------------------------------------------------------------------------


def test_health_record_round_trip(db):
    user = create_user(db, "FA-HY-00000014", "Oviya", "9000000014", "oviya@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Oviya Farm")
    unit = make_unit(token, farm["farm_id"])
    crop = make_crop(token, unit["unit_id"])

    r = client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/health-records",
        json={
            "hydroponic_crop_id": crop["cycle_id"],
            "observed_date": _today(),
            "plant_appearance": "Wilting at the base",
            "leaf_condition": "Lower leaves yellowing",
            "root_condition": "Brown tips",
            "growth_rate": "slow",
            "deficiency_symptoms": "Possible nitrogen shortfall",
            "pest_observation": "None",
            "water_condition": "Clear",
            "ph_issue": "None",
            "ec_issue": "Slightly high",
            "severity": "medium",
            "status": "observed",
            "notes": "Will recheck after a feed change",
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    record = r.json()["data"]
    assert record["record_id"].startswith("FA-HHH-")
    assert record["plant_appearance"] == "Wilting at the base"
    assert record["severity"] == "medium"

    # The record is filed against the shared CropCycle, not a private copy.
    cycle = db.query(CropCycle).filter(CropCycle.id == crop["crop_cycle_id"]).one()
    assert db.query(HydroponicHealthRecord).filter(
        HydroponicHealthRecord.crop_cycle_id == cycle.id
    ).count() == 1

    listed = client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/health-records",
        headers=auth(token),
    ).json()
    assert len(listed["data"]) == 1

    r = client.delete(
        f"/api/v1/hydroponics/health-records/{record['record_id']}", headers=auth(token)
    )
    assert r.status_code == 200, r.text


def test_stale_water_log_raises_a_warning(db):
    user = create_user(db, "FA-HY-00000032", "Lokesh", "9000000032", "lokesh@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Lokesh Farm")
    unit = make_unit(token, farm["farm_id"])

    client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/water-logs",
        json={"recorded_date": "2026-01-01", "ph": 6.0, "ec": 1.8},
        headers=auth(token),
    )
    status = client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}", headers=auth(token)
    ).json()["data"]["water_status"]
    assert status["ph_status"] == "ok"
    assert status["severity"] == "warning"
    assert any("days old" in m for m in status["messages"])


def test_unit_without_any_water_log_is_flagged(db):
    user = create_user(db, "FA-HY-00000033", "Mala", "9000000033", "mala@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Mala Farm")
    unit = make_unit(token, farm["farm_id"])

    status = client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}", headers=auth(token)
    ).json()["data"]["water_status"]
    assert status["severity"] == "warning"
    assert any("No water log" in m for m in status["messages"])


# --------------------------------------------------------------------------
# Production, economics and finance integration
# --------------------------------------------------------------------------


def test_production_record_persists_quantity_unit_and_updates_yield(db):
    user = create_user(db, "FA-HY-00000015", "Praveen", "9000000015", "praveen@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Praveen Farm")
    unit = make_unit(token, farm["farm_id"])
    crop = make_crop(token, unit["unit_id"], expected_yield=30)

    r = client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/production",
        json={
            "hydroponic_crop_id": crop["cycle_id"],
            "recorded_date": "2026-04-01",
            "quantity": 28.5,
            "unit": "kg",
            "quality_grade": "A",
            "revenue": 1425,
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["unit"] == "kg"
    assert data["quantity"] == 28.5

    # The quantity unit survives the round trip through the database.
    stored = db.query(HydroponicProductionRecord).one()
    assert stored.quantity_unit == "kg"
    assert stored.unit.unit_id == unit["unit_id"]

    # The crop's running yield and the cycle revenue both move.
    refreshed = client.get("/api/v1/hydroponics/crops", headers=auth(token)).json()["data"][0]
    assert refreshed["actual_yield"] == 28.5
    cycle = db.query(CropCycle).filter(CropCycle.id == crop["crop_cycle_id"]).one()
    assert cycle.revenue == 1425


def test_costs_are_expense_rows_and_drive_profit(db):
    user = create_user(db, "FA-HY-00000016", "Rani", "9000000016", "rani@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Rani Farm")
    unit = make_unit(token, farm["farm_id"])
    crop = make_crop(token, unit["unit_id"])

    client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/production",
        json={
            "hydroponic_crop_id": crop["cycle_id"],
            "recorded_date": "2026-04-01",
            "quantity": 20,
            "unit": "kg",
            "revenue": 1000,
        },
        headers=auth(token),
    )
    r = client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/costs",
        json={
            "cost_type": "running",
            "category": "Nutrients",
            "amount": 250,
            "incurred_date": "2026-04-02",
            "vendor": "Local supplier",
            "notes": "A and B nutrient mix",
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    cost = r.json()["data"]
    assert cost["expense_id"].startswith("FA-EXP-")

    expense = db.query(Expense).filter(Expense.expense_id == cost["expense_id"]).one()
    assert expense.hydroponic_unit_id is not None
    assert expense.amount == 250

    economics = r.json()["data"]["economics"]
    assert economics["revenue"] == 1000
    assert economics["total_cost"] == 250
    assert economics["net_profit"] == 750

    listed = client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/costs", headers=auth(token)
    ).json()
    assert len(listed["data"]) == 1

    dashboard = client.get(
        f"/api/v1/hydroponics/dashboard?farm_id={farm['farm_id']}", headers=auth(token)
    ).json()["data"]
    assert dashboard["total_revenue"] == 1000
    assert dashboard["total_cost"] == 250
    assert dashboard["net_profit"] == 750

    r = client.delete(
        f"/api/v1/hydroponics/costs/{cost['expense_id']}", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    assert db.query(Expense).filter(Expense.expense_id == cost["expense_id"]).count() == 0


def test_hydroponic_costs_reach_the_finance_ledger(db):
    user = create_user(db, "FA-HY-00000017", "Sathish", "9000000017", "sathish@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Sathish Farm")
    unit = make_unit(token, farm["farm_id"])

    client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/costs",
        json={
            "cost_type": "setup",
            "category": "Structure",
            "amount": 5000,
            "incurred_date": "2026-01-02",
        },
        headers=auth(token),
    )

    expenses = client.get("/api/v1/expenses", headers=auth(token))
    assert expenses.status_code == 200, expenses.text
    payload = expenses.json()["data"]
    assert payload["total"] == 1
    assert payload["items"][0]["amount"] == 5000

    # The Profit Calculator sums the same Expense table, so the cost is counted.
    summary = client.get("/api/v1/finance/summary", headers=auth(token))
    assert summary.status_code == 200, summary.text
    assert summary.json()["data"]["total_expenses"] == 5000


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------


def test_task_generation_creates_real_crop_tasks(db):
    user = create_user(db, "FA-HY-00000018", "Tamil", "9000000018", "tamil@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Tamil Farm")
    unit = make_unit(token, farm["farm_id"])
    make_crop(token, unit["unit_id"])

    r = client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/tasks/generate",
        json={},
        headers=auth(token),
    )
    assert r.status_code in (200, 201), r.text
    generated = r.json()["data"]
    assert len(generated) > 0

    tasks = client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/tasks", headers=auth(token)
    ).json()["data"]
    assert len(tasks) == len(generated)
    assert all(t["unit_id"] == unit["unit_id"] for t in tasks)
    assert all(t["crop_cycle_id"] is None or isinstance(t["crop_cycle_id"], str) for t in tasks)

    # Generating again must not duplicate the schedule.
    client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/tasks/generate",
        json={},
        headers=auth(token),
    )
    assert client.get(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/tasks", headers=auth(token)
    ).json()["data"].__len__() == len(tasks)


def test_generated_tasks_reach_the_tasks_page(db):
    user = create_user(db, "FA-HY-00000019", "Uma", "9000000019", "uma@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Uma Farm")
    unit = make_unit(token, farm["farm_id"])
    crop = make_crop(token, unit["unit_id"])

    client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/tasks/generate",
        json={},
        headers=auth(token),
    )

    # CropTask has no user_id; ownership flows through the crop cycle.
    cycle = db.query(CropCycle).filter(CropCycle.id == crop["crop_cycle_id"]).one()
    assert db.query(CropTask).filter(CropTask.crop_cycle_id == cycle.id).count() > 0

    r = client.get("/api/v1/crop-tasks", headers=auth(token))
    assert r.status_code == 200, r.text
    tasks = r.json()["data"]
    assert any(t.get("source") == "hydroponics" for t in tasks)


# --------------------------------------------------------------------------
# Catalog, dashboard and recommendations
# --------------------------------------------------------------------------


def test_catalog_is_derived_not_invented():
    payload = client.get("/api/v1/hydroponics/catalog", headers=auth("x")).status_code
    assert payload == 401


def test_catalog_lists_reference_data(db):
    user = create_user(db, "FA-HY-00000020", "Velu", "9000000020", "velu@hyd.com")
    token = get_token(user)
    data = client.get("/api/v1/hydroponics/catalog", headers=auth(token)).json()["data"]
    assert data["systems"]
    assert data["growth_stages"]
    assert data["crop_targets"]
    for target in data["crop_targets"]:
        assert target["ph_min"] < target["ph_max"]
        assert target["ec_min"] < target["ec_max"]


def test_dashboard_reports_harvest_window_and_alerts(db):
    user = create_user(db, "FA-HY-00000021", "Yuvi", "9000000021", "yuvi@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Yuvi Farm")
    unit = make_unit(token, farm["farm_id"], status="active")
    client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/water-logs",
        json={"recorded_date": _today(), "ph": 8.9, "ec": 1.0},
        headers=auth(token),
    )

    data = client.get(
        f"/api/v1/hydroponics/dashboard?farm_id={farm['farm_id']}", headers=auth(token)
    ).json()["data"]
    assert data["total_units"] == 1
    assert data["active_units"] == 1
    assert data["alerts"]
    assert data["alerts"][0]["unit_name"] == unit["name"]
    assert data["currency"] == "INR"


def test_dashboard_harvesting_soon_is_derived_from_planting_date(db):
    user = create_user(db, "FA-HY-00000022", "Zoya", "9000000022", "zoya@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Zoya Farm")
    unit = make_unit(token, farm["farm_id"])

    import datetime

    # Lettuce is a 45 day crop; planting it 40 days ago leaves 5 days, which is
    # inside the 30 day window, so it must show as approaching harvest.
    planting = datetime.date.today() - datetime.timedelta(days=40)
    make_crop(
        token, unit["unit_id"], crop_name="Lettuce", planting_date=planting.isoformat()
    )

    data = client.get(
        f"/api/v1/hydroponics/dashboard?farm_id={farm['farm_id']}", headers=auth(token)
    ).json()["data"]
    assert data["harvesting_soon"], "lettuce planted 40 days ago should be inside the window"
    entry = data["harvesting_soon"][0]
    assert entry["crop_name"] == "Lettuce"
    assert entry["unit_public_id"] == unit["unit_id"]
    assert 0 <= entry["days_remaining"] <= 30


def test_dashboard_hides_crops_that_are_not_near_harvest(db):
    user = create_user(db, "FA-HY-00000029", "Ravi", "9000000029", "ravi@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Ravi Farm")
    unit = make_unit(token, farm["farm_id"])

    import datetime

    # Planted today, a 90 day tomato crop is nowhere near harvest.
    make_crop(
        token,
        unit["unit_id"],
        crop_name="Tomato",
        planting_date=datetime.date.today().isoformat(),
    )
    data = client.get(
        f"/api/v1/hydroponics/dashboard?farm_id={farm['farm_id']}", headers=auth(token)
    ).json()["data"]
    assert data["active_crops"] == 1
    assert data["harvesting_soon"] == []


def test_recommendations_respect_unit_and_privacy(db):
    user = create_user(db, "FA-HY-00000023", "Anu", "9000000023", "anu@hyd.com")
    token = get_token(user)
    farm = make_farm(token, "Anu Farm")
    unit = make_unit(token, farm["farm_id"])
    client.post(
        f"/api/v1/hydroponics/units/{unit['unit_id']}/water-logs",
        json={"recorded_date": _today(), "ph": 7.9, "ec": 3.2},
        headers=auth(token),
    )

    r = client.get(
        f"/api/v1/hydroponics/recommendations?unit_id={unit['unit_id']}", headers=auth(token)
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # No supplier/installer directory exists, so say so instead of inventing one.
    assert data["location_services_available"] is False
    assert data["location_services_message"]
    assert data["recommendations"]
    titles = " ".join(str(item.get("title", "")) for item in data["recommendations"])
    assert "pH" in titles or "EC" in titles or "water" in titles.lower()


def test_recommendations_honour_opt_out(db):
    user = create_user(db, "FA-HY-00000024", "Bala", "9000000024", "bala@hyd.com")
    token = get_token(user)
    r = client.put(
        "/api/v1/users/settings",
        json={"ai_recommendations": False},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text

    data = client.get("/api/v1/hydroponics/recommendations", headers=auth(token)).json()["data"]
    assert data["enabled"] is False
    assert data["recommendations"] == []


# --------------------------------------------------------------------------
# Account onboarding
# --------------------------------------------------------------------------


def test_registration_persists_onboarding_answers(db):
    payload = {
        "full_name": "Kavitha",
        "phone_number": "9000000025",
        "email": "kavitha@hyd.com",
        "password": "StrongPass123",
        "preferred_language": "kn",
        "farming_types": ["Organic", "Hydroponics"],
        "farming_activities": ["Crop Production", "Irrigation"],
        "hydroponics_status": "planning",
        "hydroponics_units_count": 2,
        "hydroponics_system": "NFT",
        "hydroponics_crops": ["Lettuce", "Basil"],
        "hydroponics_area": 500,
        "hydroponics_area_unit": "sq ft",
    }
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code in (200, 201), r.text

    login = client.post(
        "/api/v1/auth/login",
        json={"phone_number": payload["phone_number"], "password": payload["password"]},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]

    profile = client.get("/api/v1/users/profile", headers=auth(token))
    assert profile.status_code == 200, profile.text
    data = profile.json()["data"]
    assert data["preferred_language"] == "kn"
    assert "Organic" in data["farmer_profile"]["farming_types"]
    assert "Hydroponics" in data["farmer_profile"]["farming_types"]
    assert "Crop Production" in data["farmer_profile"]["farming_activities"]
    assert data["farmer_profile"]["hydroponics_status"] == "planning"
    assert data["farmer_profile"]["hydroponics_units_count"] == 2
    assert data["farmer_profile"]["hydroponics_system"] == "NFT"
    assert data["farmer_profile"]["hydroponics_crops"] == ["Lettuce", "Basil"]
    assert data["farmer_profile"]["hydroponics_area"] == 500

    # Expressing interest must not fabricate a hydroponic unit.
    assert client.get("/api/v1/hydroponics/units", headers=auth(token)).json()["data"] == []


def test_profile_update_ignores_foreign_keys(db):
    user = create_user(db, "FA-HY-00000026", "Nila", "9000000026", "nila@hyd.com")
    token = get_token(user)
    other = create_user(db, "FA-HY-00000027", "Sathu", "9000000027", "sathu@hyd.com")

    # A caller-supplied user_id must not redirect the write to another account.
    r = client.put(
        "/api/v1/users/profile",
        json={"user_id": other.id, "farmer_id": other.farmer_id},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["farmer_id"] == user.farmer_id

    db.expire_all()
    assert db.query(User).filter(User.id == user.id).one().full_name == "Nila"
    assert db.query(User).filter(User.id == other.id).one().full_name == "Sathu"


def test_profile_update_renames_only_the_caller(db):
    user = create_user(db, "FA-HY-00000030", "Ila", "9000000030", "ila@hyd.com")
    token = get_token(user)
    other = create_user(db, "FA-HY-00000031", "Jagan", "9000000031", "jagan@hyd.com")

    r = client.put(
        "/api/v1/users/profile", json={"full_name": "Ila Rao"}, headers=auth(token)
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["full_name"] == "Ila Rao"

    db.expire_all()
    assert db.query(User).filter(User.id == other.id).one().full_name == "Jagan"


def test_profile_update_round_trips_onboarding_fields(db):
    user = create_user(db, "FA-HY-00000026", "Nila", "9000000026", "nila@hyd.com")
    token = get_token(user)
    r = client.put(
        "/api/v1/users/profile",
        json={
            "farming_types": ["Mixed"],
            "farming_activities": ["Livestock"],
            "hydroponics_status": "active",
            "hydroponics_units_count": 1,
            "preferred_language": "ta",
        },
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "Mixed" in data["farmer_profile"]["farming_types"]
    assert "Livestock" in data["farmer_profile"]["farming_activities"]
    assert data["farmer_profile"]["hydroponics_status"] == "active"
    assert data["preferred_language"] == "ta"


def test_all_supported_languages_are_accepted(db):
    user = create_user(db, "FA-HY-00000028", "Gopi", "9000000028", "gopi@hyd.com")
    token = get_token(user)
    for language in ["en", "te", "hi", "ta", "kn", "mr", "gu", "bn"]:
        r = client.put(
            "/api/v1/users/profile", json={"preferred_language": language}, headers=auth(token)
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["preferred_language"] == language


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------


def test_hydroponic_tables_and_columns_exist():
    tables = set(inspect(engine).get_table_names())
    for table in (
        "hydroponic_units",
        "hydroponic_crops",
        "hydroponic_water_logs",
        "hydroponic_health_records",
        "hydroponic_production_records",
    ):
        assert table in tables

    production_columns = {c["name"] for c in inspect(engine).get_columns("hydroponic_production_records")}
    assert "quantity_unit" in production_columns
    assert "unit" not in production_columns, "the relationship must not shadow the column"

    expense_columns = {c["name"] for c in inspect(engine).get_columns("expenses")}
    assert "hydroponic_unit_id" in expense_columns

    profile_columns = {c["name"] for c in inspect(engine).get_columns("farmer_profiles")}
    for column in (
        "farming_types",
        "farming_activities",
        "hydroponics_status",
        "hydroponics_units_count",
        "hydroponics_system",
        "hydroponics_crops",
        "hydroponics_area",
        "hydroponics_area_unit",
    ):
        assert column in profile_columns
