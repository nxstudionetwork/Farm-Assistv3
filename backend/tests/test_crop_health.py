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
from app.utils.auth import hash_password, create_access_token


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


def test_crop_health_auth_and_empty_state(db):
    user = create_user(db, "FA-CH-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    token = get_token(user)

    r_unauth = client.get("/api/v1/crop-health/overview")
    assert r_unauth.status_code == 401

    headers = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/v1/crop-health/overview", headers=headers)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["farms"] == []
    assert d["plots"] == []
    assert d["crops"] == []
    assert d["has_crop"] is False
    assert d["health"]["available"] is False
    assert d["health"]["status_label"] == "Insufficient Data"
    assert d["health"]["score"] is None
    assert d["whats_happening"]
    assert isinstance(d["crop_needs"], list)
    assert isinstance(d["what_may_happen"], list)
    assert len(d["actions"]) > 0

    r_ai = client.get("/api/v1/crop-health/ai-overview", headers=headers)
    assert r_ai.status_code == 200
    d_ai = r_ai.json()["data"]
    assert d_ai["status"] == "insufficient"
    assert d_ai["overview"] is None
    assert "Not enough" in d_ai["message"]


def test_crop_health_isolation_and_data_flow(db):
    user_a = create_user(db, "FA-CH-00000002", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    user_b = create_user(db, "FA-CH-00000003", "Farmer Suresh", "9123456780", "suresh@farm.com")

    headers_a = {"Authorization": f"Bearer {get_token(user_a)}"}
    headers_b = {"Authorization": f"Bearer {get_token(user_b)}"}

    sowing = (datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%d")

    f_a = Farm(
        farm_id="FA-CHF-0001",
        user_id=user_a.id,
        farm_name="Ramesh Farm",
        district="Guntur",
        soil_type="Clay Loam",
        water_source="Borewell",
        irrigation_method="Drip",
    )
    db.add(f_a)
    db.commit()

    p_a = FarmPlot(
        plot_id="FA-CHP-0001",
        farm_id=f_a.id,
        plot_name="Plot A1",
        area=2.0,
        soil_type="Clay Loam",
    )
    db.add(p_a)
    db.commit()

    crop_rice = Crop(
        crop_id="FA-CHC-0001",
        name="Rice",
        variety="Sona Masuri",
        category="Cereals",
        growth_duration_days=120,
    )
    db.add(crop_rice)
    db.commit()

    cyc_a = CropCycle(
        cycle_id="FA-CHY-0001",
        farm_id=f_a.id,
        plot_id=p_a.id,
        crop_id=crop_rice.id,
        sowing_date=sowing,
        current_stage="Vegetative",
        status="active",
    )
    db.add(cyc_a)

    db.add(
        SoilRecord(
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
    )
    db.add(
        IrrigationRecord(
            plot_id=p_a.id,
            method="Drip",
            duration_minutes=60.0,
            irrigation_date=datetime.utcnow(),
        )
    )
    db.commit()

    f_b = Farm(
        farm_id="FA-CHF-0002",
        user_id=user_b.id,
        farm_name="Suresh Farm",
        soil_type="Sandy",
    )
    db.add(f_b)
    db.commit()

    r_a = client.get("/api/v1/crop-health/overview", headers=headers_a)
    assert r_a.status_code == 200
    d_a = r_a.json()["data"]
    assert len(d_a["farms"]) == 1
    assert d_a["farms"][0]["farm_name"] == "Ramesh Farm"
    assert d_a["has_crop"] is True
    assert d_a["crop"]["crop_name"] == "Rice"
    assert d_a["health"]["available"] is True
    assert d_a["health"]["score"] is not None
    assert d_a["growth_stage"]["current_stage"] == "vegetative"
    assert d_a["growth_stage"]["days_since_sowing"] == 45
    assert d_a["soil"]["available"] is True
    assert d_a["irrigation"]["available"] is True

    r_iso = client.get(f"/api/v1/crop-health/overview?farm_id={f_b.id}", headers=headers_a)
    assert r_iso.status_code == 404

    r_b = client.get("/api/v1/crop-health/overview", headers=headers_b)
    assert r_b.status_code == 200
    d_b = r_b.json()["data"]
    assert d_b["farms"][0]["farm_name"] == "Suresh Farm"
    assert d_b["has_crop"] is False

    r_ai = client.get("/api/v1/crop-health/ai-overview", headers=headers_a)
    assert r_ai.status_code == 200
    d_ai = r_ai.json()["data"]
    assert d_ai["status"] == "ok"
    ov = d_ai["overview"]
    assert ov["current_condition"]
    assert len(ov["what_is_going_well"]) > 0
    assert len(ov["recommended_next_steps"]) > 0
