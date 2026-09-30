"""Focused unit tests for worker-booking status-history integrity.

These run against a small in-memory SQLite database containing only the tables
the booking service touches, so they stay fast and independent of the full
application schema used by the API-level suite.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# The Sensor / SensorReading models are declared in app.routers.sensors rather
# than app.models, so they only join the metadata once that router is imported.
# Importing app.main (as the application does at startup) guarantees a complete
# metadata before any mapper configuration is triggered.
import app.main  # noqa: F401
from app.models.farm import gen_uuid
from app.models.worker import Worker, WorkerBooking, WorkerBookingStatusHistory
from app.models.user import UserSettings
from app.models.notification import Notification
from app.services.worker_booking_service import (
    apply_status_transition,
    compute_booking_cost,
    mark_missed,
    record_status_history,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    WorkerBooking.__table__.create(bind=engine)
    WorkerBookingStatusHistory.__table__.create(bind=engine)
    UserSettings.__table__.create(bind=engine)
    Notification.__table__.create(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _booking(db, **overrides):
    fields = {
        "id": gen_uuid(),
        "booking_id": "FA-BKG-0001",
        "farmer_id": gen_uuid(),
        "worker_id": gen_uuid(),
        "booking_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "start_time": "00:00",
        "end_time": "17:00",
        "duration_days": 1,
        "status": "pending",
    }
    fields.update(overrides)
    booking = WorkerBooking(**fields)
    db.add(booking)
    db.flush()
    return booking


def _history(db, booking):
    return (
        db.query(WorkerBookingStatusHistory)
        .filter(WorkerBookingStatusHistory.booking_id == booking.id)
        .order_by(WorkerBookingStatusHistory.created_at, WorkerBookingStatusHistory.id)
        .all()
    )


class TestInitialHistoryRow:
    def test_creation_row_has_no_previous_status(self, db):
        booking = _booking(db)
        record_status_history(
            db, booking, new_status="pending", previous_status=None, note="Booking created."
        )
        rows = _history(db, booking)
        assert len(rows) == 1
        assert rows[0].previous_status is None
        assert rows[0].new_status == "pending"

    def test_paid_creation_row_also_has_no_previous_status(self, db):
        booking = _booking(db, status="confirmed")
        record_status_history(
            db, booking, new_status="confirmed", previous_status=None, note="Booking created."
        )
        rows = _history(db, booking)
        assert rows[0].previous_status is None
        assert rows[0].new_status == "confirmed"


class TestInProgressChain:
    def test_starting_pending_records_the_implicit_confirmation(self, db):
        booking = _booking(db, status="pending")
        record_status_history(
            db, booking, new_status="pending", previous_status=None, note="Booking created."
        )

        apply_status_transition(db, booking, "in_progress")

        rows = _history(db, booking)
        assert [r.new_status for r in rows] == ["pending", "confirmed", "in_progress"]
        assert [r.previous_status for r in rows] == [None, "pending", "confirmed"]
        assert booking.status == "in_progress"

    def test_starting_confirmed_does_not_add_a_confirmation_row(self, db):
        booking = _booking(db, status="confirmed")
        record_status_history(
            db, booking, new_status="confirmed", previous_status=None, note="Booking created."
        )

        apply_status_transition(db, booking, "in_progress")

        rows = _history(db, booking)
        assert [r.new_status for r in rows] == ["confirmed", "in_progress"]
        assert [r.previous_status for r in rows] == [None, "confirmed"]

    def test_history_is_a_continuous_chain(self, db):
        booking = _booking(db, status="pending")
        record_status_history(
            db, booking, new_status="pending", previous_status=None, note="Booking created."
        )
        apply_status_transition(db, booking, "in_progress")
        apply_status_transition(db, booking, "completed")

        rows = _history(db, booking)
        statuses = [r.new_status for r in rows]
        assert statuses == ["pending", "confirmed", "in_progress", "completed"]
        for previous_row, current_row in zip(rows, rows[1:]):
            assert current_row.previous_status == previous_row.new_status


class TestMissedSweep:
    def test_missed_row_points_at_the_live_status(self, db):
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        booking = _booking(db, status="confirmed", booking_date=yesterday)
        record_status_history(
            db, booking, new_status="confirmed", previous_status=None, note="Booking created."
        )

        assert mark_missed(db, booking) is True
        rows = _history(db, booking)
        assert rows[-1].new_status == "missed"
        assert rows[-1].previous_status == "confirmed"
        assert rows[-1].changed_by == "system"


class TestBookingCost:
    def test_daily_rate_charges_per_day_plus_ten_percent_gst(self):
        worker = Worker(daily_rate=700.0, hourly_rate=None)
        subtotal, gst, total = compute_booking_cost(worker, duration_days=2)
        assert subtotal == 1400.0
        assert gst == 140.0
        assert total == 1540.0

    def test_hourly_rate_charges_hours_times_days_plus_gst(self):
        worker = Worker(daily_rate=None, hourly_rate=50.0)
        subtotal, gst, total = compute_booking_cost(
            worker, duration_days=2, hours_per_day=8
        )
        assert subtotal == 800.0
        assert gst == 80.0
        assert total == 880.0

    def test_hourly_worker_without_hours_has_no_charge(self):
        worker = Worker(daily_rate=None, hourly_rate=50.0)
        subtotal, gst, total = compute_booking_cost(worker, duration_days=1, hours_per_day=0)
        assert subtotal == 0.0
        assert gst == 0.0
        assert total == 0.0

    def test_daily_rate_wins_when_both_are_set(self):
        worker = Worker(daily_rate=500.0, hourly_rate=60.0)
        subtotal, gst, total = compute_booking_cost(
            worker, duration_days=1, hours_per_day=8
        )
        assert subtotal == 500.0
        assert total == 550.0
