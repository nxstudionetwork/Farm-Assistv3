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


def test_crop_health_companion_sections(db):
    """Overview must expose the crop cycle, plan, watch and symptom catalogue."""
    user = create_user(db, "FA-CH-00000004", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    headers = {"Authorization": f"Bearer {get_token(user)}"}

    sowing = (datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%d")

    f_a = Farm(
        farm_id="FA-CHF-0003", user_id=user.id, farm_name="Ramesh Farm",
        district="Guntur", soil_type="Clay Loam",
    )
    db.add(f_a)
    db.commit()
    p_a = FarmPlot(
        plot_id="FA-CHP-0002", farm_id=f_a.id, plot_name="Plot A1",
        area=2.0, soil_type="Clay Loam",
    )
    db.add(p_a)
    db.commit()
    crop_rice = Crop(
        crop_id="FA-CHC-0002", name="Rice", variety="Sona Masuri",
        category="Cereals", growth_duration_days=120,
    )
    db.add(crop_rice)
    db.commit()
    cyc_a = CropCycle(
        cycle_id="FA-CHY-0002", farm_id=f_a.id, plot_id=p_a.id,
        crop_id=crop_rice.id, sowing_date=sowing,
        current_stage="Vegetative", status="active",
    )
    db.add(cyc_a)
    db.commit()

    r = client.get("/api/v1/crop-health/overview", headers=headers)
    assert r.status_code == 200
    d = r.json()["data"]

    # Cycle timeline: 10 canonical stages, current = vegetative
    cyc = d["cycle"]
    assert cyc is not None
    assert cyc["crop"] == "Rice"
    assert len(cyc["stages"]) == 10
    assert cyc["current_stage"] == "vegetative"
    assert cyc["current_label"] == "Vegetative Growth"
    keys = [s["key"] for s in cyc["stages"]]
    assert "land_prep" in keys and "harvest" in keys and "post_harvest" in keys
    assert any(s["state"] == "current" for s in cyc["stages"])
    assert any(s["state"] == "completed" for s in cyc["stages"])
    assert any(s["state"] == "upcoming" for s in cyc["stages"])
    assert cyc["previous_stage"] and cyc["previous_stage"]["key"] == "germination"
    assert cyc["next_stage"] and cyc["next_stage"]["key"] == "flowering"

    # per-stage clickable detail is present for every stage
    assert "stage_details" in d
    assert len(d["stage_details"]) == 10
    sd = d["stage_details"]["vegetative"]
    assert sd["label"]
    assert isinstance(sd["activities"], list) and len(sd["activities"]) > 0
    assert isinstance(sd["watch"], list)
    assert sd["meaning"]  # general-reference stage description

    # Plan grouped into now / this_week / coming_up
    plan = d["plan"]
    assert plan is not None
    assert isinstance(plan["now"], list)
    assert isinstance(plan["this_week"], list)
    assert isinstance(plan["coming_up"], list)
    assert len(plan["now"]) + len(plan["this_week"]) + len(plan["coming_up"]) > 0
    for bucket in ("now", "this_week", "coming_up"):
        for item in plan[bucket]:
            assert item["action"]
            assert item["stage"]
            assert item["bucket"] == bucket
            assert "priority" in item
            assert "can_track" in item

    # Watch-for-this items carry observe/why/confirm/next
    watch = d["watch"]
    assert isinstance(watch, list) and len(watch) > 0
    for w in watch:
        assert w["title"] and w["observe"] and w["why"]
        assert "confirm" in w and "next" in w

    # Symptom catalogue has the 12 built-in codes
    syms = d["symptom_catalogue"]
    assert isinstance(syms, list) and len(syms) >= 12
    codes = {s["code"] for s in syms}
    assert "wilting" in codes and "water_stress" in codes and "virus_symptoms" in codes

    r_plan = client.get("/api/v1/crop-health/plan", headers=headers)
    assert r_plan.status_code == 200
    assert r_plan.json()["data"]["has_crop"] is True
    assert "plan" in r_plan.json()["data"]
    assert "cycle" in r_plan.json()["data"]


def test_crop_health_check_records_history(db):
    """POST /check evaluates symptoms, persists, and appears in history."""
    user = create_user(db, "FA-CH-00000005", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    headers = {"Authorization": f"Bearer {get_token(user)}"}
    sowing = (datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%d")

    f_a = Farm(farm_id="FA-CHF-0004", user_id=user.id, farm_name="Ramesh Farm")
    db.add(f_a)
    db.commit()
    p_a = FarmPlot(plot_id="FA-CHP-0003", farm_id=f_a.id, plot_name="Plot A1", area=2.0)
    db.add(p_a)
    db.commit()
    crop_wheat = Crop(
        crop_id="FA-CHC-0003", name="Wheat", variety="HD-2967",
        category="Cereals", growth_duration_days=120,
    )
    db.add(crop_wheat)
    db.commit()
    cyc = CropCycle(
        cycle_id="FA-CHY-0003", farm_id=f_a.id, plot_id=p_a.id,
        crop_id=crop_wheat.id, sowing_date=sowing,
        current_stage="Vegetative", status="active",
    )
    db.add(cyc)
    db.commit()

    payload = {
        "symptoms": ["yellowing_lower", "water_stress"],
        "observations": "Lower leaves turning yellow, plants look dry.",
    }

    r = client.post("/api/v1/crop-health/check", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["result"]["health_status"] in ("watch", "attention", "critical")
    assert "Possible concern" in d["result"]["possible_concern"]
    assert "Recommended action" in d["result"]["recommended_action"]
    assert "Follow-up" in d["result"]["follow_up"]
    assert d["check"]["check_id"].startswith("FA-CHK-")
    assert d["check"]["crop_cycle_id"] == cyc.id
    assert d["check"]["user_id"] == user.id
    assert d["check"]["symptom_codes"] == ["yellowing_lower", "water_stress"]

    # Plan history surfaces the recorded check
    r_over = client.get("/api/v1/crop-health/overview", headers=headers)
    checks = r_over.json()["data"]["health_checks"]
    assert len(checks) == 1
    assert checks[0]["check_id"].startswith("FA-CHK-")

    # Dedicated /checks endpoint
    r_checks = client.get("/api/v1/crop-health/checks", headers=headers)
    assert r_checks.status_code == 200
    cdata = r_checks.json()["data"]
    assert cdata["has_checks"] is True
    assert len(cdata["checks"]) == 1


def test_crop_health_check_isolation(db):
    """A farmer cannot read or reach another farmer's checks or cycle ids."""
    user_a = create_user(db, "FA-CH-00000006", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    user_b = create_user(db, "FA-CH-00000007", "Farmer Suresh", "9123456780", "suresh@farm.com")
    headers_a = {"Authorization": f"Bearer {get_token(user_a)}"}
    headers_b = {"Authorization": f"Bearer {get_token(user_b)}"}
    sowing = (datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%d")

    f_a = Farm(farm_id="FA-CHF-0005", user_id=user_a.id, farm_name="Ramesh Farm")
    db.add(f_a)
    db.commit()
    p_a = FarmPlot(plot_id="FA-CHP-0004", farm_id=f_a.id, plot_name="Plot A1", area=2.0)
    db.add(p_a)
    db.commit()
    crop_rice = Crop(
        crop_id="FA-CHC-0004", name="Rice", variety="Sona Masuri",
        category="Cereals", growth_duration_days=120,
    )
    db.add(crop_rice)
    db.commit()
    cyc_a = CropCycle(
        cycle_id="FA-CHY-0004", farm_id=f_a.id, plot_id=p_a.id,
        crop_id=crop_rice.id, sowing_date=sowing,
        current_stage="Vegetative", status="active",
    )
    db.add(cyc_a)
    db.commit()

    r_check = client.post("/api/v1/crop-health/check", json={
        "symptoms": ["wilting"], "observations": "Several plants drooping.",
    }, headers=headers_a)
    assert r_check.status_code == 200

    # User B gets their own farm + cycle so the scope resolves independently.
    f_b = Farm(farm_id="FA-CHF-0006", user_id=user_b.id, farm_name="Suresh Farm")
    db.add(f_b)
    db.commit()
    p_b = FarmPlot(plot_id="FA-CHP-0005", farm_id=f_b.id, plot_name="Plot B1", area=1.5)
    db.add(p_b)
    db.commit()
    cyc_b = CropCycle(
        cycle_id="FA-CHY-0005", farm_id=f_b.id, plot_id=p_b.id,
        crop_id=crop_rice.id, sowing_date=sowing,
        current_stage="Vegetative", status="active",
    )
    db.add(cyc_b)
    db.commit()

    # user B cannot read A's cycle history by id, nor fetch overview via farm_id
    r_b_cycle = client.get(
        f"/api/v1/crop-health/checks?cycle_id={cyc_a.id}", headers=headers_b
    )
    assert r_b_cycle.status_code == 404

    r_b_farm = client.get(f"/api/v1/crop-health/overview?farm_id={f_a.id}", headers=headers_b)
    assert r_b_farm.status_code == 404

    # user B cannot POST a check scoped to A's cycle
    r_b_post = client.post("/api/v1/crop-health/check", json={
        "cycle_id": cyc_a.id, "symptoms": ["wilting"],
    }, headers=headers_b)
    assert r_b_post.status_code == 404

    # and only A can see the stored check
    r_b_hist = client.get("/api/v1/crop-health/checks", headers=headers_b)
    assert r_b_hist.status_code == 200
    assert r_b_hist.json()["data"]["has_checks"] is False
    r_b_over = client.get("/api/v1/crop-health/overview", headers=headers_b)
    assert r_b_over.json()["data"]["health_checks"] == []
    r_a_over = client.get("/api/v1/crop-health/overview", headers=headers_a)
    assert len(r_a_over.json()["data"]["health_checks"]) == 1


def test_crop_health_recognises_legacy_farm_with_null_is_active(db):
    """A registered Farm whose is_active is NULL (legacy row) must never be
    hidden, otherwise Crop Health would wrongly show the "Add Farm" empty
    state even though the farmer owns a Farm."""
    user = create_user(db, "FA-CH-00000007", "Farmer Legacy", "9676543210", "legacy@farm.com")
    headers = {"Authorization": f"Bearer {get_token(user)}"}

    farm = Farm(
        farm_id="FA-CHF-0007",
        user_id=user.id,
        farm_name="Legacy Farm",
        is_active=None,
    )
    db.add(farm)
    db.commit()

    r = client.get("/api/v1/crop-health/overview", headers=headers)
    assert r.status_code == 200
    d = r.json()["data"]
    assert len(d["farms"]) == 1
    assert d["farms"][0]["farm_name"] == "Legacy Farm"
    assert d["has_crop"] is False

    # Explicitly deactivated farms stay hidden - that is a deliberate state.
    farm2 = Farm(
        farm_id="FA-CHF-0008",
        user_id=user.id,
        farm_name="Closed Farm",
        is_active=False,
    )
    db.add(farm2)
    db.commit()

    r2 = client.get("/api/v1/crop-health/overview", headers=headers)
    assert r2.status_code == 200
    d2 = r2.json()["data"]
    assert len(d2["farms"]) == 1
    assert d2["farms"][0]["farm_name"] == "Legacy Farm"
