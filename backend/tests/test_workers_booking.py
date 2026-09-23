import os
import sys
from datetime import datetime

# Isolate from the production DB: MUST be set before any app import so the
# engine + config are built against this dedicated test database.
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_workers_booking_api.db"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import Base, SessionLocal, engine
from app.models import (
    User,
    Farm,
    FarmPlot,
    Worker,
    WorkerBooking,
    WorkerBookingStatusHistory,
    Notification,
)
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


def _make_user(session, suffix, phone_prefix="94"):
    user = User(
        full_name=f"Booking Farmer {suffix}",
        phone_number=f"{phone_prefix}{suffix:08d}",
        email=f"wb{suffix}@test.example",
        password_hash=hash_password("1234"),
        preferred_language="en",
        role="farmer",
        is_verified=True,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_farm(session, user):
    farm = Farm(
        farm_name=f"Booking Farm {user.full_name}",
        user_id=user.id,
        is_active=True,
    )
    session.add(farm)
    session.commit()
    session.refresh(farm)
    return farm


def _make_plot(session, farm):
    plot = FarmPlot(
        plot_name="Booking Plot",
        farm_id=farm.id,
        is_active=True,
    )
    session.add(plot)
    session.commit()
    session.refresh(plot)
    return plot


def _make_worker(session):
    worker = Worker(
        full_name="Booking Worker",
        phone_number="9450000001",
        skills=["ploughing", "harvesting", "irrigation"],
        hourly_rate=80.0,
        daily_rate=700.0,
        is_verified=True,
        is_available=True,
    )
    session.add(worker)
    session.commit()
    session.refresh(worker)
    return worker


def _headers(user):
    token = create_access_token({"sub": user.id, "phone": user.phone_number})
    return {"Authorization": f"Bearer {token}"}


def _today():
    return datetime.utcnow().strftime("%Y-%m-%d")


def _create_booking(
    headers, farm_id, worker_id, plot_id, booking_date="2099-12-31", start_time="09:00"
):
    return client.post(
        "/api/v1/worker-bookings",
        json={
            "worker_id": worker_id,
            "farm_id": farm_id,
            "plot_id": plot_id,
            "work_type": "Harvesting",
            "booking_date": booking_date,
            "start_time": start_time,
            "end_time": "17:00",
            "duration_days": 2,
            "hours_per_day": 8,
            "notes": "Weekend harvest",
        },
        headers=headers,
    )


def _update_status(headers, booking_id, status, **extra):
    payload = {"status": status}
    payload.update(extra)
    return client.put(
        f"/api/v1/worker-bookings/{booking_id}", json=payload, headers=headers
    )


def _get_booking(headers, booking_id):
    return client.get(
        f"/api/v1/worker-bookings/{booking_id}", headers=headers
    )


@pytest.fixture
def farmer(db):
    return _make_user(db, 1)


@pytest.fixture
def other_farmer(db):
    return _make_user(db, 2)


@pytest.fixture
def farm(db, farmer):
    return _make_farm(db, farmer)


@pytest.fixture
def plot(db, farm):
    return _make_plot(db, farm)


@pytest.fixture
def worker(db):
    return _make_worker(db)


class TestCreateDefaults:
    def test_create_makes_pending_booking_with_history_and_notification(
        self, db, farmer, farm, plot, worker
    ):
        headers = _headers(farmer)
        resp = _create_booking(headers, farm.id, worker.id, plot.id)
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        booking = db.query(WorkerBooking).filter(
            WorkerBooking.booking_id == data["booking_id"]
        ).first()
        assert booking is not None
        assert booking.status == "pending"
        assert booking.total_cost == 1400.0  # 2 days x 700

        history = db.query(WorkerBookingStatusHistory).filter(
            WorkerBookingStatusHistory.booking_id == booking.id
        ).all()
        assert history, "expected an initial pending status-history row"
        assert any(h.new_status == "pending" for h in history)

        notif = db.query(Notification).filter(
            Notification.reference_id == booking.id,
            Notification.reference_type == "worker_booking",
        ).first()
        assert notif is not None
        assert "Created" in (notif.title or "")

    def test_overlap_same_worker_rejected(self, farmer, farm, plot, worker):
        headers = _headers(farmer)
        _create_booking(headers, farm.id, worker.id, plot.id, "2099-12-31")
        resp = _create_booking(headers, farm.id, worker.id, plot.id, "2099-12-31")
        assert resp.status_code == 400


class TestLifecycle:
    def test_happy_path(self, farmer, farm, plot, worker):
        headers = _headers(farmer)
        bid = _create_booking(
            headers, farm.id, worker.id, plot.id, _today(), "00:00"
        ).json()["data"]["booking_id"]

        for status in ["confirmed", "in_progress", "completed"]:
            resp = _update_status(headers, bid, status)
            assert resp.status_code == 200, resp.text

        detail = _get_booking(headers, bid).json()["data"]
        assert detail["status"] == "completed"
        statuses = [h["new_status"] for h in detail.get("status_history", [])]
        assert statuses == ["pending", "confirmed", "in_progress", "completed"]

    def test_invalid_jump_pending_to_completed_rejected(self, farmer, farm, plot, worker):
        headers = _headers(farmer)
        bid = _create_booking(headers, farm.id, worker.id, plot.id).json()["data"]["booking_id"]
        resp = _update_status(headers, bid, "completed")
        assert resp.status_code == 400

    def test_terminal_status_is_final(self, farmer, farm, plot, worker):
        headers = _headers(farmer)
        bid = _create_booking(
            headers, farm.id, worker.id, plot.id, _today(), "00:00"
        ).json()["data"]["booking_id"]
        for status in ["confirmed", "in_progress", "completed"]:
            _update_status(headers, bid, status)
        resp = _update_status(headers, bid, "cancelled")
        assert resp.status_code == 400

    def test_cancel_records_reason(self, farmer, farm, plot, worker):
        headers = _headers(farmer)
        bid = _create_booking(headers, farm.id, worker.id, plot.id).json()["data"]["booking_id"]
        resp = _update_status(headers, bid, "cancelled", cancel_reason="Rain forecast")
        assert resp.status_code == 200
        detail = _get_booking(headers, bid).json()["data"]
        assert detail["status"] == "cancelled"
        assert detail.get("cancel_reason") == "Rain forecast"


def _force_past_and_sweep(db, bid, booking_service):
    booking = db.query(WorkerBooking).filter(WorkerBooking.booking_id == bid).first()
    booking.booking_date = "2020-01-01"  # long past -> overdue
    db.commit()
    summary = booking_service.run_overdue_sweep(db)
    return summary


@pytest.mark.usefixtures("setup_db")
class TestMissedSweep:
    def _sweep_helper(self, db, bid):
        booking = db.query(WorkerBooking).filter(WorkerBooking.booking_id == bid).first()
        booking.booking_date = "2020-01-01"
        db.commit()
        db.refresh(booking)
        return db

    def test_overdue_pending_becomes_missed_with_history_and_notification(
        self, db, farmer, farm, plot, worker
    ):
        headers = _headers(farmer)
        bid = _create_booking(headers, farm.id, worker.id, plot.id).json()["data"]["booking_id"]
        booking = db.query(WorkerBooking).filter(WorkerBooking.booking_id == bid).first()
        booking.booking_date = "2020-01-01"
        db.commit()

        from app.services.worker_booking_service import run_overdue_sweep

        summary = run_overdue_sweep(db)
        assert summary["missed"] == 1

        db.refresh(booking)
        assert booking.status == "missed"
        assert booking.missed_at is not None

        detail = _get_booking(headers, bid).json()["data"]
        assert detail["status"] == "missed"
        statuses = [h["new_status"] for h in detail.get("status_history", [])]
        assert "missed" in statuses

        notif = db.query(Notification).filter(
            Notification.reference_id == booking.id,
            Notification.title.ilike("%Missed%"),
        ).first()
        assert notif is not None

    def test_missed_can_be_recovered_to_completed(self, db, farmer, farm, plot, worker):
        headers = _headers(farmer)
        bid = _create_booking(headers, farm.id, worker.id, plot.id).json()["data"]["booking_id"]
        booking = db.query(WorkerBooking).filter(WorkerBooking.booking_id == bid).first()
        booking.booking_date = "2020-01-01"
        db.commit()

        from app.services.worker_booking_service import run_overdue_sweep

        run_overdue_sweep(db)
        db.refresh(booking)
        assert booking.status == "missed"

        resp = _update_status(headers, bid, "completed")
        assert resp.status_code == 200, resp.text
        detail = _get_booking(headers, bid).json()["data"]
        assert detail["status"] == "completed"

    def test_completed_booking_never_becomes_missed(self, db, farmer, farm, plot, worker):
        headers = _headers(farmer)
        bid = _create_booking(
            headers, farm.id, worker.id, plot.id, _today(), "00:00"
        ).json()["data"]["booking_id"]
        for status in ["confirmed", "in_progress", "completed"]:
            _update_status(headers, bid, status)

        booking = db.query(WorkerBooking).filter(WorkerBooking.booking_id == bid).first()
        booking.booking_date = "2020-01-01"
        db.commit()

        from app.services.worker_booking_service import run_overdue_sweep

        summary = run_overdue_sweep(db)
        assert summary["missed"] == 0
        db.refresh(booking)
        assert booking.status == "completed"


class TestOwnership:
    def test_farmer_cannot_access_another_farmers_booking(
        self, db, farmer, other_farmer, farm, plot, worker
    ):
        headers_a = _headers(farmer)
        bid = _create_booking(
            headers_a, farm.id, worker.id, plot.id
        ).json()["data"]["booking_id"]

        headers_b = _headers(other_farmer)
        resp = _get_booking(headers_b, bid)
        assert resp.status_code == 404

        resp = _update_status(headers_b, bid, "completed")
        assert resp.status_code == 404

    def test_list_only_shows_own_bookings(
        self, db, farmer, other_farmer, farm, plot, worker
    ):
        headers_a = _headers(farmer)
        _create_booking(headers_a, farm.id, worker.id, plot.id)

        headers_b = _headers(other_farmer)
        resp = client.get("/api/v1/worker-bookings", headers=headers_b)
        assert resp.status_code == 200
        assert resp.json()["data"]["items"] == []
