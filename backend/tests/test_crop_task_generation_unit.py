"""Focused unit tests for automatic crop-task generation and deduplication.

These run against a small in-memory SQLite database containing only the tables
the task generator touches, so they stay fast and independent of the full
application schema used by the API-level suite.
"""

import os
import sys
from datetime import date, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Sensor / SensorReading are declared in app.routers.sensors rather than
# app.models, so metadata is only complete once that router is imported.
import app.main  # noqa: F401
from app.models.crop import Crop, CropCycle, CropTask
from app.models.farm import Farm, FarmPlot, gen_uuid
from app.models.user import User
from app.routers.crops import _collect_suggestions, _norm_title
from app.services import weather_service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(bind=engine)
    Farm.__table__.create(bind=engine)
    FarmPlot.__table__.create(bind=engine)
    Crop.__table__.create(bind=engine)
    CropCycle.__table__.create(bind=engine)
    CropTask.__table__.create(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _user(db, name="Test Farmer"):
    user = User(
        id=gen_uuid(),
        full_name=name,
        email="{0}@example.com".format(gen_uuid()),
        password_hash="x",
        role="farmer",
    )
    db.add(user)
    db.commit()
    return user


def _cycle(db, owner, crop_name="Wheat", status="active", start_offset=-20):
    farm = Farm(
        id=gen_uuid(),
        user_id=owner.id,
        farm_name="Test Farm",
        district="Test District",
        is_active=True,
    )
    db.add(farm)
    plot = FarmPlot(
        id=gen_uuid(),
        farm_id=farm.id,
        plot_name="North Plot",
        area="2",
        is_active=True,
    )
    db.add(plot)
    crop = Crop(id=gen_uuid(), name=crop_name, growth_duration_days=120)
    db.add(crop)
    db.commit()

    cycle = CropCycle(
        id=gen_uuid(),
        farm_id=farm.id,
        crop_id=crop.id,
        plot_id=plot.id,
        sowing_date=(date.today() + timedelta(days=start_offset)).isoformat(),
        expected_harvest_date=(date.today() + timedelta(days=60)).isoformat(),
        status=status,
    )
    db.add(cycle)
    db.commit()
    return farm, cycle


@pytest.fixture(autouse=True)
def no_network_weather(monkeypatch):
    """Keep generation deterministic: no live weather calls."""

    async def _fail(*args, **kwargs):
        raise AssertionError("generation must not require a network weather call")

    monkeypatch.setattr(weather_service, "get_current_weather", _fail)


class TestCollectSuggestions:
    def test_generates_tasks_from_active_cycle_only(self, db):
        owner = _user(db)
        _cycle(db, owner, "Wheat", status="active")
        _cycle(db, owner, "Rice", status="completed")

        suggestions, _weather = _collect_suggestions(db, owner)

        assert suggestions
        assert all(s["crop_name"] == "Wheat" for s in suggestions)
        assert {s["source"] for s in suggestions} <= {
            "crop_stage",
            "climate",
            "crop_health",
        }

    def test_suggestions_are_deduplicated_per_cycle(self, db):
        owner = _user(db)
        _cycle(db, owner)

        suggestions, _weather = _collect_suggestions(db, owner)
        titles = [_norm_title(s["title"]) for s in suggestions]

        assert len(titles) == len(set(titles))

    def test_existing_pending_task_suppresses_duplicate(self, db):
        owner = _user(db)
        _farm, cycle = _cycle(db, owner)

        baseline, _weather = _collect_suggestions(db, owner)
        assert baseline

        db.add(
            CropTask(
                task_id="FA-TSK-0001",
                crop_cycle_id=cycle.id,
                title=baseline[0]["title"],
                category=baseline[0]["category"],
                due_date=baseline[0]["due_date"],
                priority=baseline[0]["priority"],
                status="pending",
            )
        )
        db.commit()

        after, _weather = _collect_suggestions(db, owner)
        assert baseline[0]["title"] not in [s["title"] for s in after]
        assert len(after) == len(baseline) - 1

    def test_completed_task_does_not_suppress_regeneration(self, db):
        owner = _user(db)
        _farm, cycle = _cycle(db, owner)

        baseline, _weather = _collect_suggestions(db, owner)
        db.add(
            CropTask(
                task_id="FA-TSK-0002",
                crop_cycle_id=cycle.id,
                title=baseline[0]["title"],
                category=baseline[0]["category"],
                due_date=baseline[0]["due_date"],
                priority=baseline[0]["priority"],
                status="completed",
            )
        )
        db.commit()

        after, _weather = _collect_suggestions(db, owner)
        assert baseline[0]["title"] in [s["title"] for s in after]

    def test_other_farmer_cycles_are_never_suggested(self, db):
        owner = _user(db)
        other = _user(db)
        _cycle(db, other, "Soybean")

        suggestions, _weather = _collect_suggestions(db, owner)

        assert suggestions == []

    def test_farmer_without_farms_returns_nothing(self, db):
        owner = _user(db)
        assert _collect_suggestions(db, owner) == ([], None)

    def test_suggestions_carry_growth_stage_context(self, db):
        owner = _user(db)
        _cycle(db, owner)

        suggestions, _weather = _collect_suggestions(db, owner)
        stage_tasks = [s for s in suggestions if s["source"] == "crop_stage"]

        assert stage_tasks
        assert all(s["growth_stage"] for s in stage_tasks)


class TestGenerateEndpoint:
    def test_generates_then_is_idempotent(self, db, monkeypatch):
        from app.routers import crops as crops_router

        owner = _user(db)
        _cycle(db, owner)
        user = SimpleNamespace(id=owner.id)

        first = crops_router.generate_crop_tasks(current_user=user, db=db)
        assert first["status"] == "success"
        created = first["data"]["tasks"]
        assert created
        assert all(t["source"] for t in created)
        assert all(t["task_id"].startswith("FA-TSK-") for t in created)

        stored = db.query(CropTask).all()
        assert len(stored) == len(created)

        # Calling again must not duplicate anything.
        second = crops_router.generate_crop_tasks(current_user=user, db=db)
        assert second["data"]["created_count"] == 0
        assert second["data"]["tasks"] == []
        assert db.query(CropTask).count() == len(created)

    def test_generated_tasks_carry_source_and_stage(self, db):
        from app.routers import crops as crops_router

        owner = _user(db)
        _cycle(db, owner)
        user = SimpleNamespace(id=owner.id)

        result = crops_router.generate_crop_tasks(current_user=user, db=db)
        stage_tasks = [t for t in result["data"]["tasks"] if t["source"] == "crop_stage"]

        assert stage_tasks
        assert all(t["growth_stage"] for t in stage_tasks)
        assert all(t["status"] == "pending" for t in result["data"]["tasks"])

    def test_farmer_without_cycles_generates_nothing(self, db):
        from app.routers import crops as crops_router

        owner = _user(db)
        user = SimpleNamespace(id=owner.id)

        result = crops_router.generate_crop_tasks(current_user=user, db=db)

        assert result["data"]["created_count"] == 0
        assert db.query(CropTask).count() == 0

    def test_generate_never_writes_to_another_farmers_cycle(self, db):
        from app.routers import crops as crops_router

        intruder = _user(db)
        victim = _user(db, name="Victim Farmer")
        _farm, victim_cycle = _cycle(db, victim, "Soybean")
        user = SimpleNamespace(id=intruder.id)

        result = crops_router.generate_crop_tasks(current_user=user, db=db)

        assert result["data"]["created_count"] == 0
        assert db.query(CropTask).filter(CropTask.crop_cycle_id == victim_cycle.id).count() == 0
