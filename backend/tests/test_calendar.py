"""End-to-end tests for the Calendar module.

Covers sync, dedup, manual CRUD, auth isolation, filters, search, and edge cases.
"""

import os
import sys
from datetime import datetime, timedelta

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_calendar.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models import User
from app.utils.auth import hash_password, generate_id
from app.models.calendar import CalendarEvent
from app.models.farm import Farm, FarmPlot, gen_uuid
from app.models.crop import Crop, CropCycle, CropTask, FarmJournal
from app.models.notification import Notification

client = TestClient(app)


# ── Fixtures ────────────────────────────────────────────────────────────────

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


# ── Helpers ─────────────────────────────────────────────────────────────────

def _mk_user(db, phone, email, idx):
    user = User(
        full_name=f"Farmer {idx}",
        phone_number=phone,
        email=email,
        password_hash=hash_password("1234"),
        preferred_language="en",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(phone, email, pin="1234"):
    r = client.post(
        "/api/v1/auth/login",
        json={"phone_number": phone, "email": email, "pin": pin},
    )
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["data"]["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _mk_farm(db, user_id, name="Green Valley Farm"):
    farm = Farm(id=gen_uuid(), user_id=user_id, farm_name=name, total_area=10.0,
                area_unit="Acres", village="Village A", latitude=10.0, longitude=76.0)
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return farm


def _mk_crop(db, name="Rice"):
    crop = Crop(id=gen_uuid(), name=name, category="Cereal", growth_duration_days=90)
    db.add(crop)
    db.commit()
    db.refresh(crop)
    return crop


def _mk_cycle(db, farm_id, crop_id, status="active", sowing=None, expected_harvest=None):
    cycle = CropCycle(id=gen_uuid(), cycle_id=f"CC-{gen_uuid()[:8]}", farm_id=farm_id,
                      crop_id=crop_id, sowing_date=sowing, expected_harvest_date=expected_harvest,
                      status=status)
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return cycle


def _mk_task(db, cycle_id, title="Fertilize", due_date=None, due_time=None, status="pending"):
    task = CropTask(id=gen_uuid(), crop_cycle_id=cycle_id, title=title,
                    due_date=due_date, due_time=due_time, status=status)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _mk_manual_event(db, farmer_id, title="Test Event", start_dt=None, source_type="manual"):
    dt = start_dt or datetime.utcnow() + timedelta(days=1)
    event = CalendarEvent(
        farmer_id=farmer_id, title=title, event_type="manual", start_datetime=dt,
        status="scheduled", priority="normal", source_type=source_type,
    )
    event.event_id = generate_id("FA-CAL", db, CalendarEvent)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# ── Tests ───────────────────────────────────────────────────────────────────

def test_manual_event_crud(db):
    farmer = _mk_user(db, "9030000001", "cal1@farm.com", 1)
    token = _login("9030000001", "cal1@farm.com")
    h = _auth(token)

    # Create
    r = client.post("/api/v1/calendar/events", headers=h, json={
        "title": "Dhanya Sowing Day",
        "event_type": "manual",
        "start_datetime": "2026-03-15T09:00:00",
        "priority": "high",
        "farm_name": "Green Valley",
        "crop_name": "Rice",
    })
    assert r.status_code == 201
    ev = r.json()["data"]
    assert ev["title"] == "Dhanya Sowing Day"
    assert ev["event_id"].startswith("FA-CAL")
    assert ev["priority"] == "high"
    assert ev["farm_name"] == "Green Valley"
    eid = ev["id"]

    # Read
    r = client.get(f"/api/v1/calendar/events/{eid}", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "Dhanya Sowing Day"

    # Update
    r = client.put(f"/api/v1/calendar/events/{eid}", headers=h, json={
        "title": "Dhanya Sowing - Updated",
        "priority": "urgent",
    })
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "Dhanya Sowing - Updated"
    assert r.json()["data"]["priority"] == "urgent"

    # Delete (manual event: full delete)
    r = client.delete(f"/api/v1/calendar/events/{eid}", headers=h)
    assert r.status_code == 200

    # Verify gone
    r = client.get(f"/api/v1/calendar/events/{eid}", headers=h)
    assert r.status_code == 404


def test_auth_isolation(db):
    farmer_a = _mk_user(db, "9030000002", "cal2@farm.com", 2)
    farmer_b = _mk_user(db, "9030000003", "cal3@farm.com", 3)
    token_a = _login("9030000002", "cal2@farm.com")
    token_b = _login("9030000003", "cal3@farm.com")

    # Farmer A creates event
    r = client.post("/api/v1/calendar/events", headers=_auth(token_a), json={
        "title": "A's Private Event",
        "start_datetime": "2026-06-01T10:00:00",
    })
    assert r.status_code == 201
    eid = r.json()["data"]["id"]

    # Farmer B cannot see it
    r = client.get(f"/api/v1/calendar/events/{eid}", headers=_auth(token_b))
    assert r.status_code == 404

    # Farmer B's list is empty
    r = client.get("/api/v1/calendar/events", headers=_auth(token_b))
    assert r.json()["data"]["total"] == 0

    # Farmer B cannot update it
    r = client.put(f"/api/v1/calendar/events/{eid}", headers=_auth(token_b), json={
        "title": "Hacked!",
    })
    assert r.status_code == 404

    # Farmer B cannot delete it
    r = client.delete(f"/api/v1/calendar/events/{eid}", headers=_auth(token_b))
    assert r.status_code == 404


def test_list_filters_date_range(db):
    farmer = _mk_user(db, "9030000004", "cal4@farm.com", 4)
    token = _login("9030000004", "cal4@farm.com")
    h = _auth(token)

    # Create events on different dates
    base = datetime(2026, 7, 1, 9, 0, 0)
    for i in range(3):
        client.post("/api/v1/calendar/events", headers=h, json={
            "title": f"Event {i+1}",
            "start_datetime": (base + timedelta(days=i*10)).isoformat(),
        })

    # Filter: only events in July 1-11
    r = client.get("/api/v1/calendar/events?start_date=2026-07-01&end_date=2026-07-11", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 2  # Event 1 (Jul 1) + Event 2 (Jul 11)

    # Filter: only after July 15
    r = client.get("/api/v1/calendar/events?start_date=2026-07-15", headers=h)
    assert r.json()["data"]["total"] == 1  # Event 3 (Jul 21)


def test_list_filter_event_type(db):
    farmer = _mk_user(db, "9030000005", "cal5@farm.com", 5)
    token = _login("9030000005", "cal5@farm.com")
    h = _auth(token)

    base = datetime(2026, 8, 1, 9, 0, 0)
    for etype in ["task", "consultation", "task", "manual"]:
        client.post("/api/v1/calendar/events", headers=h, json={
            "title": f"{etype} event",
            "event_type": etype,
            "start_datetime": base.isoformat(),
        })
        base += timedelta(days=1)

    r = client.get("/api/v1/calendar/events?event_type=task", headers=h)
    assert r.json()["data"]["total"] == 2

    r = client.get("/api/v1/calendar/events?event_type=task,manual", headers=h)
    assert r.json()["data"]["total"] == 3


def test_list_filter_status_and_priority(db):
    farmer = _mk_user(db, "9030000006", "cal6@farm.com", 6)
    token = _login("9030000006", "cal6@farm.com")
    h = _auth(token)

    base = datetime(2026, 9, 1, 9, 0, 0)
    for status in ["scheduled", "completed", "cancelled"]:
        client.post("/api/v1/calendar/events", headers=h, json={
            "title": f"{status} event",
            "start_datetime": base.isoformat(),
        })
        base += timedelta(days=1)

    # Update statuses
    r = client.get("/api/v1/calendar/events", headers=h)
    for ev in r.json()["data"]["items"]:
        if "completed" in ev["title"]:
            client.put(f"/api/v1/calendar/events/{ev['id']}", headers=h, json={"status": "completed"})
        elif "cancelled" in ev["title"]:
            client.put(f"/api/v1/calendar/events/{ev['id']}", headers=h, json={"status": "cancelled"})

    r = client.get("/api/v1/calendar/events?status=scheduled", headers=h)
    assert r.json()["data"]["total"] == 1

    r = client.get("/api/v1/calendar/events?status=completed,cancelled", headers=h)
    assert r.json()["data"]["total"] == 2


def test_list_search(db):
    farmer = _mk_user(db, "9030000007", "cal7@farm.com", 7)
    token = _login("9030000007", "cal7@farm.com")
    h = _auth(token)

    base = datetime(2026, 10, 1, 9, 0, 0)
    for title in ["Rice Sowing", "Wheat Harvesting", "Rice Fertilizer"]:
        client.post("/api/v1/calendar/events", headers=h, json={
            "title": title,
            "start_datetime": base.isoformat(),
        })
        base += timedelta(days=1)

    r = client.get("/api/v1/calendar/events?search=Rice", headers=h)
    assert r.json()["data"]["total"] == 2

    r = client.get("/api/v1/calendar/events?search=Wheat", headers=h)
    assert r.json()["data"]["total"] == 1

    r = client.get("/api/v1/calendar/events?search=xyz", headers=h)
    assert r.json()["data"]["total"] == 0


def test_today_and_upcoming_endpoints(db):
    farmer = _mk_user(db, "9030000008", "cal8@farm.com", 8)
    token = _login("9030000008", "cal8@farm.com")
    h = _auth(token)

    now = datetime.utcnow()
    today_end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    today = today_end - timedelta(seconds=1)
    tomorrow = today_end + timedelta(hours=12)
    yesterday = today_end - timedelta(days=1) - timedelta(seconds=1)

    for title, dt in [("Today Event", today), ("Tomorrow Event", tomorrow), ("Yesterday Event", yesterday)]:
        client.post("/api/v1/calendar/events", headers=h, json={
            "title": title,
            "start_datetime": dt.isoformat(),
        })

    r = client.get("/api/v1/calendar/today", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["today"]) == 1
    assert data["today"][0]["title"] == "Today Event"
    assert len(data["overdue"]) == 1
    assert data["overdue"][0]["title"] == "Yesterday Event"

    r = client.get("/api/v1/calendar/upcoming", headers=h)
    assert r.status_code == 200
    upcoming = r.json()["data"]["items"]
    titles = [e["title"] for e in upcoming]
    assert "Today Event" in titles
    assert "Tomorrow Event" in titles
    assert "Yesterday Event" not in titles


def test_sync_creates_events_from_crop_tasks(db):
    farmer = _mk_user(db, "9030000009", "cal9@farm.com", 9)
    farm = _mk_farm(db, farmer.id, "Sunrise Farm")
    crop = _mk_crop(db, "Maize")
    cycle = _mk_cycle(db, farm.id, crop.id, sowing="2026-04-01", expected_harvest="2026-07-01")
    _mk_task(db, cycle.id, "Weeding", due_date="2026-04-15", due_time="09:00", status="pending")
    _mk_task(db, cycle.id, "Pest Control", due_date="2026-05-01", status="pending")

    token = _login("9030000009", "cal9@farm.com")
    h = _auth(token)

    r = client.post("/api/v1/calendar/sync", headers=h)
    assert r.status_code == 200
    summary = r.json()["data"]
    assert summary["synced_events"] >= 4  # 2 tasks + 2 crop cycle events (sowing + harvest)

    # Verify task events appear in list
    r = client.get("/api/v1/calendar/events?event_type=task", headers=h)
    assert r.json()["data"]["total"] == 2
    titles = [e["title"] for e in r.json()["data"]["items"]]
    assert "Weeding" in titles
    assert "Pest Control" in titles

    # Crop cycle events
    r = client.get("/api/v1/calendar/events?event_type=crop_activity", headers=h)
    assert r.json()["data"]["total"] == 2


def test_sync_dedup_second_sync_does_not_duplicate(db):
    farmer = _mk_user(db, "9030000010", "cal10@farm.com", 10)
    farm = _mk_farm(db, farmer.id, "Farm X")
    crop = _mk_crop(db, "Wheat")
    cycle = _mk_cycle(db, farm.id, crop.id, sowing="2026-05-01", expected_harvest="2026-08-01")
    _mk_task(db, cycle.id, "Sow Seeds", due_date="2026-05-01", status="pending")

    token = _login("9030000010", "cal10@farm.com")
    h = _auth(token)

    # First sync
    client.post("/api/v1/calendar/sync", headers=h)
    r1 = client.get("/api/v1/calendar/events", headers=h)
    count_after_first = r1.json()["data"]["total"]

    # Second sync — should not increase count
    client.post("/api/v1/calendar/sync", headers=h)
    r2 = client.get("/api/v1/calendar/events", headers=h)
    assert r2.json()["data"]["total"] == count_after_first


def test_synced_event_delete_marks_cancelled(db):
    farmer = _mk_user(db, "9030000011", "cal11@farm.com", 11)
    farm = _mk_farm(db, farmer.id, "Farm Y")
    crop = _mk_crop(db, "Cotton")
    cycle = _mk_cycle(db, farm.id, crop.id, sowing="2026-06-01")
    _mk_task(db, cycle.id, "Irrigation", due_date="2026-06-15", status="pending")

    token = _login("9030000011", "cal11@farm.com")
    h = _auth(token)

    client.post("/api/v1/calendar/sync", headers=h)
    r = client.get("/api/v1/calendar/events?event_type=task", headers=h)
    ev = r.json()["data"]["items"][0]
    eid = ev["id"]

    # Delete synced event → should become cancelled, not removed
    r = client.delete(f"/api/v1/calendar/events/{eid}", headers=h)
    assert r.status_code == 200

    r = client.get(f"/api/v1/calendar/events/{eid}", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "cancelled"


def test_filters_endpoint(db):
    farmer = _mk_user(db, "9030000012", "cal12@farm.com", 12)
    farm = _mk_farm(db, farmer.id, "Filters Farm")
    crop = _mk_crop(db, "Maize")
    cycle = _mk_cycle(db, farm.id, crop.id)
    _mk_task(db, cycle.id, "Test Task", due_date="2026-11-01", status="pending")

    token = _login("9030000012", "cal12@farm.com")
    h = _auth(token)

    # Sync so we have event types
    client.post("/api/v1/calendar/sync", headers=h)

    r = client.get("/api/v1/calendar/filters", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "farms" in data
    assert len(data["farms"]) >= 1
    assert "Maize" in data.get("crop_names", [])
    assert "task" in data.get("event_types", [])
    assert "priorities" in data


def test_event_by_event_id_lookup(db):
    farmer = _mk_user(db, "9030000013", "cal13@farm.com", 13)
    token = _login("9030000013", "cal13@farm.com")
    h = _auth(token)

    r = client.post("/api/v1/calendar/events", headers=h, json={
        "title": "Lookup Test",
        "start_datetime": "2026-12-01T10:00:00",
    })
    event_id = r.json()["data"]["event_id"]

    r = client.get(f"/api/v1/calendar/events/{event_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "Lookup Test"


def test_update_fields_persists(db):
    farmer = _mk_user(db, "9030000014", "cal14@farm.com", 14)
    token = _login("9030000014", "cal14@farm.com")
    h = _auth(token)

    r = client.post("/api/v1/calendar/events", headers=h, json={
        "title": "Before",
        "start_datetime": "2026-01-15T08:00:00",
        "priority": "low",
        "reminder_config": "15m",
    })
    eid = r.json()["data"]["id"]

    client.put(f"/api/v1/calendar/events/{eid}", headers=h, json={
        "title": "After",
        "start_datetime": "2026-01-20T09:00:00",
        "priority": "urgent",
        "reminder_config": "1h",
    })

    r = client.get(f"/api/v1/calendar/events/{eid}", headers=h)
    ev = r.json()["data"]
    assert ev["title"] == "After"
    assert ev["priority"] == "urgent"
    assert ev["reminder_config"] == "1h"
    assert "2026-01-20" in ev["start_datetime"]


def test_empty_search_returns_no_results(db):
    farmer = _mk_user(db, "9030000015", "cal15@farm.com", 15)
    token = _login("9030000015", "cal15@farm.com")
    h = _auth(token)

    client.post("/api/v1/calendar/events", headers=h, json={
        "title": "Something",
        "start_datetime": "2026-03-01T10:00:00",
    })

    r = client.get("/api/v1/calendar/events?search=nonexistent", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0


def test_completed_task_synced_as_completed_status(db):
    farmer = _mk_user(db, "9030000016", "cal16@farm.com", 16)
    farm = _mk_farm(db, farmer.id, "Completed Farm")
    crop = _mk_crop(db, "Maize")
    cycle = _mk_cycle(db, farm.id, crop.id)
    _mk_task(db, cycle.id, "Done Task", due_date="2026-04-01", status="completed")

    token = _login("9030000016", "cal16@farm.com")
    h = _auth(token)

    client.post("/api/v1/calendar/sync", headers=h)
    r = client.get("/api/v1/calendar/events?event_type=task", headers=h)
    items = r.json()["data"]["items"]
    completed = [e for e in items if e["status"] == "completed"]
    assert len(completed) >= 1
    assert completed[0]["title"] == "Done Task"


def test_farm_journal_synced_as_farm_activity(db):
    farmer = _mk_user(db, "9030000017", "cal17@farm.com", 17)
    farm = _mk_farm(db, farmer.id, "Journal Farm")
    plot = FarmPlot(id=gen_uuid(), farm_id=farm.id, plot_name="Plot A", area=2.0)
    db.add(plot)
    db.commit()
    journal = FarmJournal(
        id=gen_uuid(), user_id=farmer.id, farm_id=farm.id, plot_id=plot.id,
        activity="Planted cover crop", notes="Green manure broadcast",
        entry_date=datetime.utcnow(),
    )
    db.add(journal)
    db.commit()

    token = _login("9030000017", "cal17@farm.com")
    h = _auth(token)

    client.post("/api/v1/calendar/sync", headers=h)
    r = client.get("/api/v1/calendar/events?event_type=farm_activity", headers=h)
    items = r.json()["data"]["items"]
    assert len(items) >= 1
    ev = items[0]
    assert ev["title"] == "Planted cover crop"
    assert ev["status"] == "completed"
    assert ev["plot_name"] == "Plot A"
    assert ev["farm_name"] == "Journal Farm"


def test_plot_filter_and_filters_include_plots(db):
    farmer = _mk_user(db, "9030000018", "cal18@farm.com", 18)
    farm = _mk_farm(db, farmer.id, "Plot Filter Farm")
    plot = FarmPlot(id=gen_uuid(), farm_id=farm.id, plot_name="North Plot", area=1.5)
    db.add(plot)
    db.commit()

    token = _login("9030000018", "cal18@farm.com")
    h = _auth(token)
    client.post("/api/v1/calendar/events", headers=h, json={
        "title": "Spray Event",
        "start_datetime": "2026-07-10T09:00:00",
        "farm_id": farm.id,
        "farm_name": "Plot Filter Farm",
        "plot_id": plot.id,
        "plot_name": "North Plot",
    })
    client.post("/api/v1/calendar/events", headers=h, json={
        "title": "Other Event",
        "start_datetime": "2026-07-10T09:00:00",
    })

    r = client.get(f"/api/v1/calendar/events?plot_id={plot.id}", headers=h)
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Spray Event"
    assert items[0]["plot_name"] == "North Plot"

    r = client.get("/api/v1/calendar/filters", headers=h)
    data = r.json()["data"]
    assert "plots" in data
    assert any(p["id"] == plot.id and p["name"] == "North Plot" for p in data["plots"])


def test_reminder_creates_notification_and_dedupes(db):
    farmer = _mk_user(db, "9030000019", "cal19@farm.com", 19)
    token = _login("9030000019", "cal19@farm.com")
    h = _auth(token)

    start = datetime.utcnow() + timedelta(minutes=30)
    r = client.post("/api/v1/calendar/events", headers=h, json={
        "title": "Pipe Change",
        "start_datetime": start.isoformat(),
        "reminder_config": "1h",
    })
    eid = r.json()["data"]["id"]

    # 1 hour before a start 30 minutes away is already due -> 1 notification.
    r = client.post("/api/v1/calendar/reminders/process", headers=h)
    assert r.json()["data"]["reminders_sent"] == 1

    notifs = db.query(Notification).filter(
        Notification.user_id == farmer.id,
        Notification.reference_type == "calendar_reminder",
    ).all()
    assert len(notifs) == 1
    assert "Pipe Change" in notifs[0].title

    # No duplicate on re-processing.
    r = client.post("/api/v1/calendar/reminders/process", headers=h)
    assert r.json()["data"]["reminders_sent"] == 0
    assert db.query(Notification).filter(
        Notification.user_id == farmer.id,
        Notification.reference_type == "calendar_reminder",
    ).count() == 1

    # Dedup key carries the event_id + offset + reminder time.
    assert notifs[0].reference_id.startswith("FA-CAL")
    assert "3600" in notifs[0].reference_id  # 1h in seconds


def test_reminder_reschedule_does_not_refire_old(db):
    farmer = _mk_user(db, "9030000020", "cal20@farm.com", 20)
    token = _login("9030000020", "cal20@farm.com")
    h = _auth(token)

    start = datetime.utcnow() + timedelta(minutes=20)
    r = client.post("/api/v1/calendar/events", headers=h, json={
        "title": "Pay Visit",
        "start_datetime": start.isoformat(),
        "reminder_config": "30m",
    })
    eid = r.json()["data"]["id"]

    client.post("/api/v1/calendar/reminders/process", headers=h)
    assert db.query(Notification).filter(
        Notification.user_id == farmer.id,
        Notification.reference_type == "calendar_reminder",
    ).count() == 1

    # Reschedule far into the future -> old reminder key no longer fires and
    # the new (future) reminder is not yet due.
    future = datetime.utcnow() + timedelta(days=10)
    client.put(f"/api/v1/calendar/events/{eid}", headers=h, json={
        "start_datetime": future.isoformat(),
    })
    client.post("/api/v1/calendar/reminders/process", headers=h)
    assert db.query(Notification).filter(
        Notification.user_id == farmer.id,
        Notification.reference_type == "calendar_reminder",
    ).count() == 1


def test_recurring_event_expands_occurrences(db):
    farmer = _mk_user(db, "9030000021", "cal21@farm.com", 21)
    token = _login("9030000021", "cal21@farm.com")
    h = _auth(token)

    client.post("/api/v1/calendar/events", headers=h, json={
        "title": "Weekly Review",
        "start_datetime": "2026-09-01T10:00:00",
        "recurrence": "weekly",
    })

    r = client.get("/api/v1/calendar/events?start_date=2026-09-01&end_date=2026-09-30", headers=h)
    items = r.json()["data"]["items"]
    occurrences = [e for e in items if e["title"] == "Weekly Review"]
    # Sept 1, 8, 15, 22, 29 → 5 occurrences
    assert len(occurrences) == 5
    dates = [e["start_datetime"][:10] for e in occurrences]
    assert set(dates) == {"2026-09-01", "2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29"}
