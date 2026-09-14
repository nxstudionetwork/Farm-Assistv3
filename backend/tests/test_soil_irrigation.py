import sys
import os

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_farm_assist.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.models.crop import Crop, CropCycle, SoilRecord, IrrigationRecord
from app.utils.auth import hash_password, create_access_token, generate_id

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


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


def test_soil_irrigation_auth_and_empty_state(db):
    user = create_user(db, "FA-SI-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    token = get_token(user)

    # 1. Unauthenticated request -> 401
    r_unauth = client.get("/api/v1/soil-irrigation/overview")
    assert r_unauth.status_code == 401

    # 2. Authenticated user with no farm -> empty structures, success
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/v1/soil-irrigation/overview", headers=headers)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["farms"] == []
    assert d["plots"] == []
    assert d["crops"] == []
    assert d["soil"]["available"] is False
    assert d["irrigation"]["available"] is False

    # 3. AI overview on empty user -> status 'insufficient'
    r_ai = client.get("/api/v1/soil-irrigation/ai-overview", headers=headers)
    assert r_ai.status_code == 200
    d_ai = r_ai.json()["data"]
    assert d_ai["status"] == "insufficient"
    assert "Not enough data" in d_ai["message"]


def test_soil_irrigation_isolation_and_data_flow(db):
    user_a = create_user(db, "FA-SI-00000002", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    user_b = create_user(db, "FA-SI-00000003", "Farmer Suresh", "9123456780", "suresh@farm.com")

    headers_a = {"Authorization": f"Bearer {get_token(user_a)}"}
    headers_b = {"Authorization": f"Bearer {get_token(user_b)}"}

    # Farmer A setup
    f_a = Farm(
        farm_id="FA-FRM-0001",
        user_id=user_a.id,
        farm_name="Ramesh Farm",
        soil_type="Clay Loam",
        water_source="Borewell",
        irrigation_method="Drip",
        latitude=16.24,
        longitude=80.64,
    )
    db.add(f_a)
    db.commit()

    p_a = FarmPlot(
        plot_id="FA-PLT-0001",
        farm_id=f_a.id,
        plot_name="Plot A1",
        area=2.0,
        soil_type="Clay Loam",
    )
    db.add(p_a)

    crop_rice = Crop(
        crop_id="FA-CRP-0001",
        name="Rice",
        variety="Sona Masuri",
        category="Cereals",
        growth_duration_days=120,
    )
    db.add(crop_rice)
    db.commit()

    cyc_a = CropCycle(
        cycle_id="FA-CYC-0001",
        farm_id=f_a.id,
        plot_id=p_a.id,
        crop_id=crop_rice.id,
        sowing_date="2026-06-01",
        current_stage="Vegetative",
        irrigation_schedule="Water every 3 days",
        status="active",
    )
    db.add(cyc_a)

    s_a = SoilRecord(
        plot_id=p_a.id,
        ph_level=6.5,
        nitrogen=320.0,
        phosphorus=20.0,
        potassium=200.0,
        organic_matter=1.5,
        moisture=50.0,
        soil_type="Clay Loam",
        test_date=datetime.utcnow(),
    )
    db.add(s_a)

    i_a = IrrigationRecord(
        plot_id=p_a.id,
        method="Drip",
        duration_minutes=120.0,
        water_quantity=2000.0,
        water_unit="Liters",
        irrigation_date=datetime.utcnow(),
    )
    db.add(i_a)
    db.commit()

    # Farmer B setup
    f_b = Farm(
        farm_id="FA-FRM-0002",
        user_id=user_b.id,
        farm_name="Suresh Farm",
        soil_type="Sandy",
        water_source="Canal",
        irrigation_method="Flood",
    )
    db.add(f_b)
    db.commit()

    p_b = FarmPlot(
        plot_id="FA-PLT-0002",
        farm_id=f_b.id,
        plot_name="Plot B1",
        area=3.0,
    )
    db.add(p_b)
    db.commit()

    # 1. Farmer A gets overview -> sees own farm & data
    r_a = client.get("/api/v1/soil-irrigation/overview", headers=headers_a)
    assert r_a.status_code == 200
    d_a = r_a.json()["data"]
    assert len(d_a["farms"]) == 1
    assert d_a["farms"][0]["farm_name"] == "Ramesh Farm"
    assert len(d_a["plots"]) == 1
    assert d_a["plots"][0]["plot_name"] == "Plot A1"
    assert len(d_a["crops"]) == 1
    assert d_a["crops"][0]["crop_name"] == "Rice"
    assert d_a["soil"]["available"] is True
    assert d_a["soil"]["status"]["code"] == "healthy"
    assert d_a["irrigation"]["available"] is True
    assert d_a["irrigation"]["status"]["code"] == "sufficient"

    # 2. Farmer A passes Farmer B's farm_id -> 404 Isolation
    r_iso_farm = client.get(f"/api/v1/soil-irrigation/overview?farm_id={f_b.id}", headers=headers_a)
    assert r_iso_farm.status_code == 404

    # 3. Farmer A passes Farmer B's plot_id -> 404 Isolation
    r_iso_plot = client.get(f"/api/v1/soil-irrigation/overview?plot_id={p_b.id}", headers=headers_a)
    assert r_iso_plot.status_code == 404

    # 4. Farmer B gets overview -> sees own farm, no Farmer A data
    r_b = client.get("/api/v1/soil-irrigation/overview", headers=headers_b)
    assert r_b.status_code == 200
    d_b = r_b.json()["data"]
    assert d_b["farms"][0]["farm_name"] == "Suresh Farm"
    assert d_b["soil"]["available"] is False

    # 5. AI Overview for Farmer A -> status 'ok' with data-driven sections
    r_ai = client.get("/api/v1/soil-irrigation/ai-overview", headers=headers_a)
    assert r_ai.status_code == 200
    d_ai = r_ai.json()["data"]
    assert d_ai["status"] == "ok"
    assert d_ai["overview"]["overall_condition"] is not None
    assert len(d_ai["overview"]["what_is_good"]) > 0
