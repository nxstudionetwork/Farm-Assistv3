import sys
import os
from datetime import date, timedelta

# Isolate tests from the production database. Must be set BEFORE any app import.
if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_livestock.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import engine, Base
from app.models import User
from app.utils.auth import hash_password

client = TestClient(app)

PHONE_A = "9888100001"
PHONE_B = "9888100002"
PIN = "1234"


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _make_user(phone):
    u = User(
        full_name="Livestock Test Farmer",
        phone_number=phone,
        email=f"{phone}@farm.test",
        password_hash=hash_password(PIN),
        preferred_language="en",
        role="farmer",
        is_verified=True,
        is_active=True,
    )
    with engine.begin() as conn:
        pass
    from app.database.connection import SessionLocal
    session = SessionLocal()
    session.add(u)
    session.commit()
    session.refresh(u)
    session.close()
    return u


def _token(phone):
    r = client.post("/api/v1/auth/login", json={"phone_number": phone, "pin": PIN})
    assert r.status_code == 200, r.text
    data = r.json().get("data", {})
    return data.get("access_token")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _today(n=0):
    return (date.today() + timedelta(days=n)).isoformat()


@pytest.fixture
def token_a():
    _make_user(PHONE_A)
    return _token(PHONE_A)


def test_overview_empty_for_new_farmer(token_a):
    r = client.get("/api/v1/livestock/overview", headers=_auth(token_a))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 0
    assert data["by_type"] == {}
    assert data["total_expenses"] == 0
    assert data["production_records"] == 0


def test_livestock_crud_and_records(token_a):
    h = _auth(token_a)

    # empty list
    r = client.get("/api/v1/livestock", headers=h)
    assert r.status_code == 200 and r.json()["data"] == []

    # create requires name/type
    r = client.post("/api/v1/livestock", json={"name": "", "animal_type": "cow"}, headers=h)
    assert r.status_code == 400

    created = client.post("/api/v1/livestock", json={
        "name": "Lakshmi", "animal_type": "cow", "breed": "HF",
        "gender": "female", "weight_kg": 350, "health_status": "healthy",
        "photo_url": None, "notes": "test",
    }, headers=h)
    assert created.status_code == 200, created.text
    aid = created.json()["data"]["animal_id"]
    assert aid.startswith("FA-LVS")

    # get + full
    r = client.get(f"/api/v1/livestock/{aid}", headers=h)
    assert r.status_code == 200 and r.json()["data"]["name"] == "Lakshmi"
    full = client.get(f"/api/v1/livestock/{aid}/full", headers=h)
    assert full.status_code == 200
    assert full.json()["data"]["counts"]["weight"] == 0

    # overview counts reflect the new animal
    ov = client.get("/api/v1/livestock/overview", headers=h).json()["data"]
    assert ov["total"] == 1
    assert ov["by_type"]["cow"] == 1

    # record types
    assert client.post(f"/api/v1/livestock/{aid}/health", json={
        "record_date": _today(), "health_status": "monitoring",
        "symptoms": "fever", "follow_up_date": _today(-1),
    }, headers=h).status_code == 200
    assert client.post(f"/api/v1/livestock/{aid}/vaccinations", json={
        "vaccine_name": "FMD", "date_given": _today(), "next_due_date": _today(7),
    }, headers=h).status_code == 200
    assert client.post(f"/api/v1/livestock/{aid}/treatments", json={
        "treatment_date": _today(), "issue": "leg", "status": "ongoing",
    }, headers=h).status_code == 200
    assert client.post(f"/api/v1/livestock/{aid}/feeding", json={
        "feed_type": "Hay", "quantity": "5 kg", "record_date": _today(),
    }, headers=h).status_code == 200
    assert client.post(f"/api/v1/livestock/{aid}/breeding", json={
        "breeding_date": _today(), "method": "natural",
        "pregnancy_status": "pregnant", "expected_delivery_date": _today(20),
    }, headers=h).status_code == 200
    assert client.post(f"/api/v1/livestock/{aid}/weight", json={
        "weight_kg": 360, "measurement_date": _today(),
    }, headers=h).status_code == 200
    assert client.post(f"/api/v1/livestock/{aid}/production", json={
        "record_date": _today(), "product_type": "milk", "quantity": 5, "unit": "litres",
    }, headers=h).status_code == 200
    assert client.post(f"/api/v1/livestock/{aid}/expenses", json={
        "expense_date": _today(), "category": "feed", "amount": 250,
    }, headers=h).status_code == 200

    # lists have the records
    for path in ("health", "vaccinations", "treatments", "feeding", "breeding",
                 "weight", "production", "expenses"):
        r = client.get(f"/api/v1/livestock/{aid}/{path}", headers=h)
        assert r.status_code == 200, path
        assert len(r.json()["data"]) == 1, path

    # attention surfaced from real records (follow-up overdue + vaccination upcoming + delivery upcoming)
    att = client.get("/api/v1/livestock/attention/summary", headers=h)
    all_ev = att.json()["data"]["all"]
    assert att.status_code == 200
    assert any(e["type"] == "vaccination" and e["animal_id"] == aid for e in all_ev)
    assert any(e["type"] == "health_checkup" and e["animal_id"] == aid for e in all_ev)
    assert any(e["type"] == "breeding" and e["animal_id"] == aid for e in all_ev)

    # activity has real entries
    act = client.get("/api/v1/livestock/activity/recent", headers=h).json()["data"]
    kinds = {i["type"] for i in act}
    assert {"animal_added", "vaccination", "health", "expense"}.issubset(kinds)

    # update + photo_url round-trip
    upd = client.put(f"/api/v1/livestock/{aid}", json={
        "name": "Lakshmi II", "weight_kg": 370, "photo_url": "/images/x.jpg",
    }, headers=h)
    assert upd.status_code == 200
    assert upd.json()["data"]["photo_url"] == "/images/x.jpg"

    # delete (soft) + gone
    assert client.delete(f"/api/v1/livestock/{aid}", headers=h).status_code == 200
    assert client.get(f"/api/v1/livestock/{aid}", headers=h).status_code == 404
    ov = client.get("/api/v1/livestock/overview", headers=h).json()["data"]
    assert ov["total"] == 0


def test_cross_farmer_isolation(token_a):
    _make_user(PHONE_B)
    token_b = _token(PHONE_B)
    h_a = _auth(token_a)
    h_b = _auth(token_b)

    created = client.post("/api/v1/livestock", json={
        "name": "A's cow", "animal_type": "cow",
    }, headers=h_a)
    aid = created.json()["data"]["animal_id"]

    r = client.get(f"/api/v1/livestock/{aid}", headers=h_b)
    assert r.status_code == 404
    r = client.get(f"/api/v1/livestock/{aid}/full", headers=h_b)
    assert r.status_code == 404
    r = client.put(f"/api/v1/livestock/{aid}", json={"name": "hacked"}, headers=h_b)
    assert r.status_code == 404
    r = client.delete(f"/api/v1/livestock/{aid}", headers=h_b)
    assert r.status_code == 404
    r = client.get("/api/v1/livestock", headers=h_b)
    assert r.json()["data"] == []


def test_no_fake_zero_or_undefined(token_a):
    """After creation of one animal, overview fields must be real numbers, not None."""
    h = _auth(token_a)
    client.post("/api/v1/livestock", json={"name": "Bhola", "animal_type": "buffalo"}, headers=h)
    ov = client.get("/api/v1/livestock/overview", headers=h).json()["data"]
    assert ov["total"] == 1
    assert ov["healthy"] >= 0
    assert ov["needs_attention"] >= 0
    assert ov["by_type"]["buffalo"] == 1
    assert ov["by_type"].get("cow") is None