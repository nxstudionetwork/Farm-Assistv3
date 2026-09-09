"""Coverage for the Experts Hub categories and expert consultation notifications.

Same harness as tests/test_community.py: a dedicated SQLite file, schema rebuilt
per session, rows wiped per test, real auth tokens via the login endpoint.

These tests exercise the extra behaviour layered on top of the existing module:
  1. GET /experts?category=<label> filters against real speciality data
     (including the exact-inverse "Other Specialists" bucket).
  2. Booking, cancellation and rescheduling each create a real notification
     through the existing notification system (backend/database events).
"""

import os
import sys

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_experts_hub.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta

from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models import User, Expert
from app.models.notification import Notification
from app.utils.auth import hash_password

client = TestClient(app)


def _future(days=5):
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_tables(schema):
    session = SessionLocal()
    try:
        for table in Base.metadata.sorted_tables:
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def user_a(db):
    user = User(
        full_name="Expert Farmer Alpha",
        phone_number="9033333333",
        email="expert-alpha@farm.com",
        password_hash=hash_password("1234"),
        preferred_language="en",
        role="farmer",
        is_verified=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def token_a(user_a):
    resp = client.post(
        "/api/v1/auth/login",
        json={"phone_number": "9033333333", "password": "1234"},
    )
    data = resp.json().get("data", {})
    return data.get("access_token")


@pytest.fixture
def headers_a(token_a):
    return {"Authorization": f"Bearer {token_a}"}


def make_expert(db, expert_id, speciality, name="Dr. Test Expert",
                available=True, fee=300, rating=4.5):
    row = Expert(
        expert_id=expert_id,
        full_name=name,
        speciality=speciality,
        qualification="PhD Test Science",
        experience_years=8,
        bio=f"Test bio covering {speciality} for field crops.",
        consultation_fee=fee,
        rating=rating,
        total_consultations=10,
        is_available=available,
        location="Hyderabad",
        languages=["English"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def names(items):
    return {(i["full_name"], i["speciality"].lower()) for i in items}


def book(headers, expert_id, topic="Field crop question",
         date_value=None, time_value="10:00 AM"):
    payload = {
        "expert_id": expert_id,
        "topic": topic,
        "consultation_type": "Crop",
        "consultation_method": "Video",
        "scheduled_date": date_value or _future(5),
        "scheduled_time": time_value,
    }
    resp = client.post("/api/v1/consultations", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# --------------------------------------------------------------------------- categories
class TestExpertCategories:
    def test_category_filters_by_speciality(self, db, user_a, headers_a):
        soil = make_expert(db, "FA-CTEST-001", "Soil Science", name="Dr. Soil One")
        soil_micro = make_expert(db, "FA-CTEST-002", "Soil Health & Microbes", name="Dr. Soil Two")
        patho = make_expert(db, "FA-CTEST-003", "Plant Pathology", name="Dr. Path One")

        resp = client.get("/api/v1/experts", params={"category": "Soil Experts"}, headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["category"] == "Soil Experts"
        items = data["items"]
        assert len(items) == 2
        assert all("soil" in i["speciality"].lower() for i in items)
        assert patho.id not in {i["id"] for i in items}

    def test_all_category_returns_everything(self, db, user_a, headers_a):
        make_expert(db, "FA-CTEST-010", "Soil Science")
        make_expert(db, "FA-CTEST-011", "Plant Pathology")

        resp = client.get("/api/v1/experts", params={"category": "All"}, headers=headers_a)
        data = resp.json()["data"]
        assert data["category"] == "All"
        assert data["total"] == 2

    def test_other_specialists_is_the_inverse(self, db, user_a, headers_a):
        make_expert(db, "FA-CTEST-020", "Soil Science", name="Dr. Soil")
        make_expert(db, "FA-CTEST-021", "Plant Pathology", name="Dr. Path")
        make_expert(db, "FA-CTEST-022", "Apiculture & Bee Keeping", name="Dr. Bee")

        resp = client.get("/api/v1/experts", params={"category": "Other Specialists"}, headers=headers_a)
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["speciality"] == "Apiculture & Bee Keeping"

    def test_category_and_search_work_together(self, db, user_a, headers_a):
        make_expert(db, "FA-CTEST-030", "Soil Science", name="Dr. Venkatesh Soil")
        make_expert(db, "FA-CTEST-031", "Soil Health & Microbes", name="Dr. Anitha Microbes")

        resp = client.get(
            "/api/v1/experts",
            params={"category": "Soil Experts", "search": "Venkatesh"},
            headers=headers_a,
        )
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["full_name"] == "Dr. Venkatesh Soil"

    def test_unknown_category_is_ignored(self, db, user_a, headers_a):
        make_expert(db, "FA-CTEST-040", "Soil Science")
        resp = client.get("/api/v1/experts", params={"category": "Not A Category"}, headers=headers_a)
        assert resp.json()["data"]["total"] == 1


# --------------------------------------------------------------------------- notifications
class TestConsultationNotifications:
    def _latest(self, db, con_id):
        return db.query(Notification).filter(Notification.reference_id == con_id).all()

    def test_booking_creates_notification(self, db, user_a, headers_a):
        expert = make_expert(db, "FA-CTEST-100", "Soil Science", name="Dr. Notify One")
        con = book(headers_a, expert.id)

        notifs = self._latest(db, con["consultation_id"])
        assert len(notifs) == 1
        n = notifs[0]
        assert n.notification_type == "consultation"
        assert n.reference_type == "consultation"
        assert n.user_id == user_a.id
        assert n.icon == "fa-user-doctor"
        assert f"expert.html?ref={n.reference_id}" in (n.action_url or "")
        assert n.notification_id.startswith("FA-NOT-")
        assert "Dr. Notify One" in n.message
        assert con["consultation_id"] in n.message

    def test_cancel_creates_notification(self, db, user_a, headers_a):
        expert = make_expert(db, "FA-CTEST-101", "Plant Pathology", name="Dr. Notify Two")
        con = book(headers_a, expert.id)
        cid = con["consultation_id"]

        resp = client.patch(
            f"/api/v1/consultations/{cid}",
            headers=headers_a,
            json={"status": "cancelled", "cancel_reason": "Crop was sold"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"

        notifs = self._latest(db, cid)
        assert len(notifs) == 2  # booking + cancellation
        cancel = next(n for n in notifs if n.title == "Appointment Cancelled")
        assert cancel.user_id == user_a.id
        assert "sold" in cancel.message or cancel.reference_id == cid
        assert cancel.action_url == f"expert.html?ref={cid}"

    def test_reschedule_creates_notification(self, db, user_a, headers_a):
        expert = make_expert(db, "FA-CTEST-102", "Horticulture", name="Dr. Notify Three")
        con = book(headers_a, expert.id)
        cid = con["consultation_id"]

        resp = client.patch(
            f"/api/v1/consultations/{cid}",
            headers=headers_a,
            json={"scheduled_date": _future(8), "scheduled_time": "11:30 AM"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["scheduled_time"] == "11:30 AM"

        notifs = self._latest(db, cid)
        assert len(notifs) == 2  # booking + reschedule
        resched = next(n for n in notifs if n.title == "Appointment Rescheduled")
        assert resched.user_id == user_a.id
        assert _future(8) in resched.message

    def test_no_reschedule_notification_when_slot_unchanged(self, db, user_a, headers_a):
        expert = make_expert(db, "FA-CTEST-103", "Agronomy", name="Dr. Notify Four")
        con = book(headers_a, expert.id)
        cid = con["consultation_id"]

        resp = client.patch(
            f"/api/v1/consultations/{cid}",
            headers=headers_a,
            json={"notes": "Just adding a note, keeping my slot."},
        )
        assert resp.status_code == 200
        notifs = self._latest(db, cid)
        assert len(notifs) == 1  # booking only

    def test_completion_does_not_notify_cancel(self, db, user_a, headers_a):
        expert = make_expert(db, "FA-CTEST-104", "Irrigation", name="Dr. Notify Five")
        con = book(headers_a, expert.id)
        cid = con["consultation_id"]

        client.patch(f"/api/v1/consultations/{cid}", headers=headers_a, json={"status": "confirmed"})
        client.patch(f"/api/v1/consultations/{cid}", headers=headers_a, json={"status": "in_progress"})
        resp = client.patch(f"/api/v1/consultations/{cid}", headers=headers_a, json={"status": "completed"})
        assert resp.status_code == 200

        titles = {n.title for n in self._latest(db, cid)}
        assert "Appointment Cancelled" not in titles
        assert "Appointment Rescheduled" not in titles