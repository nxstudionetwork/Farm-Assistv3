"""Sustainability dashboard: API contract, period filtering, CRUD and the
regressions found while finishing the feature.

Covered regressions:
  * indicator basis text must not repeat "of farm area" (was rendered as
    "... over 40.00 Acres of farm area of farm area").
  * the frontend must define every SustainabilityPage method it calls
    (``renderReports`` was called but never defined, which silently killed the
    whole Reports block: rows, download and delete buttons never appeared).
"""

import os
import re
import sys

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_sustainability.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"
else:
    # conftest.py points every module at one shared test database, and those
    # modules call Base.metadata.drop_all() on it. A second pytest process
    # running another module then drops these tables mid-run ("no such table:
    # users"). Give this module its own throwaway database so it cannot collide
    # with a parallel test session. Never the real database.
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_sustainability.db"
    )

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import itertools
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models import User, Farm, FarmPlot
from app.utils.auth import create_access_token

REPO_ROOT = Path(__file__).resolve().parents[2]

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def make_user(db, farmer_id, phone):
    user = User(
        farmer_id=farmer_id,
        full_name="Sustainability Tester",
        phone_number=phone,
        email=f"{farmer_id.lower()}@farm.com",
        password_hash="x",
        is_verified=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


_SEQ = itertools.count(1)


def make_farm(db, user, name, total_area, unit="Acres"):
    farm = Farm(
        farm_id="FA-SUSF-%05d" % next(_SEQ),
        user_id=user.id,
        farm_name=name,
        village="Test Village",
        district="Test District",
        total_area=total_area,
        area_unit=unit,
    )
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return farm


def make_plot(db, farm, name, area):
    plot = FarmPlot(
        plot_id="FA-SUSP-%05d" % next(_SEQ),
        farm_id=farm.id,
        plot_name=name,
        area=area,
    )
    db.add(plot)
    db.commit()
    db.refresh(plot)
    return plot


def token_for(user):
    return create_access_token({"sub": user.id, "phone": user.phone_number})


def auth(user):
    return {"Authorization": f"Bearer {token_for(user)}"}


# --------------------------------------------------------------------------- #
# API behaviour
# --------------------------------------------------------------------------- #

def test_dashboard_requires_auth():
    assert client.get("/api/v1/sustainability/dashboard").status_code == 401


def test_dashboard_empty_state(db):
    user = make_user(db, "FA-SUS-00000001", "9800000001")
    r = client.get("/api/v1/sustainability/dashboard", headers=auth(user))
    assert r.status_code == 200
    d = r.json()["data"]

    assert d["farms"] == []
    assert d["records"] == {"water": [], "energy": [], "practices": [], "soil": []}
    assert d["indicators"], "indicators block must always render"
    assert d["calculations"], "the 'how each number is calculated' list must render"
    assert d["notes"], "notes block must always render"
    for key in ("water_per_acre", "energy_per_acre"):
        indicator = next(i for i in d["indicators"] if i["key"] == key)
        assert indicator["available"] is False


def test_energy_and_practice_round_trip(db):
    user = make_user(db, "FA-SUS-00000002", "9800000002")
    farm = make_farm(db, user, "Green Valley", 40.0)
    plot = make_plot(db, farm, "North Field", 12.0)
    headers = auth(user)

    today = date.today().isoformat()
    r = client.post(
        "/api/v1/sustainability/energy",
        headers=headers,
        json={
            "farm_id": farm.id,
            "plot_id": plot.id,
            "energy_type": "Solar",
            "quantity": 250,
            "unit": "kWh",
            "usage_date": today,
            "source": "Panels",
            "cost": 1200,
            "notes": "rooftop array",
        },
    )
    assert r.status_code == 201, r.text
    energy_id = r.json()["data"]["record"]["id"]


    r = client.post(
        "/api/v1/sustainability/practices",
        headers=headers,
        json={
            "farm_id": farm.id,
            "plot_id": plot.id,
            "practice_name": "Composting",
            "category": "soil",
            "status": "completed",
            "area_hectares": 3.5,
            "started_on": today,
            "notes": "vermicompost beds",
        },
    )
    assert r.status_code == 201, r.text
    practice_id = r.json()["data"]["record"]["id"]


    d = client.get("/api/v1/sustainability/dashboard", headers=headers).json()["data"]
    assert [e["id"] for e in d["records"]["energy"]] == [energy_id]
    assert [p["id"] for p in d["records"]["practices"]] == [practice_id]

    summary = d["summary"]
    assert summary["energy_usage"]["available"] is True
    assert summary["practices"]["available"] is True
    assert summary["practices"]["count"] == 1

    single = client.get(
        f"/api/v1/sustainability/dashboard?farm_id={farm.id}", headers=headers
    ).json()["data"]
    assert single["single_farm"] is True
    assert single["scope"]["farm_id"] == farm.id
    assert single["records"]["energy"], "farm filter must keep the record"
    assert single["indicators"], "indicators must still render when filtered"

    by_plot = client.get(
        f"/api/v1/sustainability/dashboard?farm_id={farm.id}&plot_id={plot.id}",
        headers=headers,
    ).json()["data"]
    assert by_plot["single_plot"] is True
    assert by_plot["scope"]["plot_id"] == plot.id
    assert len(by_plot["records"]["energy"]) == 1

    # A farm with more than one plot must not be treated as single-plot scope.
    make_plot(db, farm, "South Field", 8.0)
    two_plots = client.get(
        f"/api/v1/sustainability/dashboard?farm_id={farm.id}", headers=headers
    ).json()["data"]
    assert two_plots["single_farm"] is True
    assert two_plots["single_plot"] is False

    # A farm that has no plots at all must still render, with no plot options.
    empty = make_farm(db, user, "No Plot Farm", 5.0)
    no_plots = client.get(
        f"/api/v1/sustainability/dashboard?farm_id={empty.id}", headers=headers
    ).json()["data"]
    assert no_plots["farms"][0]["plots"] == []
    assert no_plots["single_plot"] is False
    assert no_plots["indicators"], "a farm with no plots must still render"

    assert client.delete(
        f"/api/v1/sustainability/energy/{energy_id}", headers=headers
    ).status_code == 200
    assert client.delete(
        f"/api/v1/sustainability/practices/{practice_id}", headers=headers
    ).status_code == 200


    d = client.get("/api/v1/sustainability/dashboard", headers=headers).json()["data"]
    assert d["records"]["energy"] == []
    assert d["records"]["practices"] == []


def test_indicator_basis_text_is_not_duplicated(db):
    """Regression: basis text said "... of farm area of farm area"."""
    user = make_user(db, "FA-SUS-00000003", "9800000003")
    make_farm(db, user, "Basis Farm", 40.0)

    r = client.get("/api/v1/sustainability/dashboard", headers=auth(user))
    assert r.status_code == 200
    payload = r.text

    assert "of farm area of farm area" not in payload
    d = r.json()["data"]
    for key in ("water_per_acre", "energy_per_acre"):
        indicator = next(i for i in d["indicators"] if i["key"] == key)
        basis = indicator["basis"]
        assert basis.count("of farm area") <= 1, basis
        assert "farm area of farm area" not in basis
        if indicator["available"]:
            assert basis.startswith("Total "), basis


def test_period_filtering(db):
    user = make_user(db, "FA-SUS-00000004", "9800000004")
    farm = make_farm(db, user, "Period Farm", 20.0)
    headers = auth(user)

    old = (date.today() - timedelta(days=400)).isoformat()
    new = date.today().isoformat()
    for usage_date, qty in ((old, 100), (new, 5)):
        assert client.post(
            "/api/v1/sustainability/energy",
            headers=headers,
            json={
                "farm_id": farm.id,
                "energy_type": "Diesel",
                "quantity": qty,
                "unit": "Litres",
                "usage_date": usage_date,
            },
        ).status_code == 201


    # The dashboard derives its period from date_from/date_to; there is no
    # `period` query parameter.
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    all_time = client.get(
        "/api/v1/sustainability/dashboard", headers=headers
    ).json()["data"]
    recent = client.get(
        f"/api/v1/sustainability/dashboard?date_from={cutoff}", headers=headers
    ).json()["data"]
    custom = client.get(
        f"/api/v1/sustainability/dashboard?date_from={new}&date_to={new}",
        headers=headers,
    ).json()["data"]


    assert len(all_time["records"]["energy"]) == 2
    assert len(recent["records"]["energy"]) == 1
    assert recent["records"]["energy"][0]["quantity"] == 5
    assert len(custom["records"]["energy"]) == 1
    assert custom["period"]["from"] == new
    assert custom["period"]["to"] == new


def test_validation_and_ownership(db):
    user = make_user(db, "FA-SUS-00000005", "9800000005")
    intruder = make_user(db, "FA-SUS-00000006", "9800000006")
    farm = make_farm(db, intruder, "Not Yours", 10.0)
    headers = auth(user)

    missing = client.post(
        "/api/v1/sustainability/energy",
        headers=headers,
        json={"farm_id": farm.id, "energy_type": "Solar", "quantity": 1},
    )
    assert missing.status_code == 422

    # A farm owned by somebody else must not be usable.
    stolen = client.post(
        "/api/v1/sustainability/energy",
        headers=headers,
        json={
            "farm_id": farm.id,
            "energy_type": "Solar",
            "quantity": 1,
            "usage_date": date.today().isoformat(),
        },
    )
    assert stolen.status_code in (400, 403, 404), stolen.text

    assert client.delete(
        f"/api/v1/sustainability/energy/does-not-exist", headers=headers
    ).status_code in (400, 404)


# --------------------------------------------------------------------------- #
# Frontend wiring
# --------------------------------------------------------------------------- #

def _sus_script() -> str:
    return (REPO_ROOT / "frontend" / "js" / "script.js").read_text(encoding="utf-8")


def test_every_sustainability_handler_is_defined():
    """Regression: ``renderReports()`` was called but never defined, so report
    rows and their download/delete buttons never rendered."""
    src = _sus_script()
    start = src.index("/* ===== SUSTAINABILITY ===== */")
    end = src.index("window.SustainabilityPage = SUS;", start)
    section = src[start:end]

    defined = set(re.findall(r"^\s{2}([A-Za-z_$][\w$]*)\s*:\s*function", section, re.M))
    called = set(re.findall(r"\b(?:this|self|SUS)\.([A-Za-z_$][\w$]*)\s*\(", section))
    called |= set(re.findall(r"SustainabilityPage\.([A-Za-z_$][\w$]*)\s*\(", src))

    missing = sorted(m for m in called if m not in defined)
    assert not missing, f"SustainabilityPage methods called but never defined: {missing}"


def test_reports_block_has_a_stable_host():
    """``renderReports()`` can only patch the DOM if the reports block is
    rendered inside a container it can find by id."""
    src = _sus_script()
    assert "renderReports: function" in src
    assert "getElementById('sus-reports')" in src
    assert "'<section class=\"sus-section\" id=\"sus-reports\">'" in src

