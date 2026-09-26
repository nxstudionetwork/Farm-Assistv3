import sys
import os

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_farm_assist.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models.user import User
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


def make_farm(token, name="Green Valley Farm", **extra):
    payload = {"farm_name": name, "total_area": 5, "area_unit": "Acres"}
    payload.update(extra)
    r = client.post("/api/v1/farms", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_farm_map_requires_authentication():
    assert client.get("/api/v1/maps/farm-map").status_code == 401


def test_farm_without_boundary_reports_no_boundary(db):
    user = create_user(db, "FA-FM-00000001", "Farmer Anil", "9000000001", "anil@farm.com")
    token = get_token(user)
    farm = make_farm(token, latitude=17.9, longitude=78.4)

    r = client.get("/api/v1/maps/farm-map", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()["data"]

    assert data["counts"]["farms"] == 1
    mapped = data["farms"][0]
    assert mapped["farm_id"] == farm["farm_id"]
    assert mapped["has_location"] is True
    # No boundary stored -> report the honest setup state, never invented geometry.
    assert mapped["has_boundary"] is False
    assert mapped["boundary_coordinates"] is None
    assert data["counts"]["plots"] == 0


def test_farm_boundary_round_trip(db):
    user = create_user(db, "FA-FM-00000002", "Farmer Bhavna", "9000000002", "bhavna@farm.com")
    token = get_token(user)

    boundary = [[17.9, 78.4], [17.91, 78.4], [17.91, 78.41], [17.9, 78.41]]
    farm = make_farm(
        token,
        latitude=17.905,
        longitude=78.405,
        boundary_coordinates={"type": "Polygon", "coordinates": [boundary]},
    )
    assert farm["boundary_coordinates"]["points"] == boundary

    r = client.get("/api/v1/maps/farm-map", headers={"Authorization": f"Bearer {token}"})
    mapped = r.json()["data"]["farms"][0]
    assert mapped["has_boundary"] is True
    assert mapped["boundary_coordinates"]["points"] == boundary


def test_farm_boundary_can_be_cleared(db):
    user = create_user(db, "FA-FM-00000003", "Farmer Chetan", "9000000003", "chetan@farm.com")
    token = get_token(user)
    headers = {"Authorization": f"Bearer {token}"}
    farm = make_farm(token, boundary_coordinates=[[1, 2], [3, 4], [5, 6]])

    r = client.put(f"/api/v1/farms/{farm['farm_id']}", json={"boundary_coordinates": None}, headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["boundary_coordinates"] is None

    mapped = client.get("/api/v1/maps/farm-map", headers=headers).json()["data"]["farms"][0]
    assert mapped["has_boundary"] is False


def test_invalid_boundaries_are_rejected(db):
    user = create_user(db, "FA-FM-00000004", "Farmer Deepa", "9000000004", "deepa@farm.com")
    token = get_token(user)
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/api/v1/farms",
        json={"farm_name": "Bad", "boundary_coordinates": [[91, 0], [0, 0], [0, 1]]},
        headers=headers,
    )
    assert r.status_code == 422
    assert "latitude/longitude" in r.json()["detail"]

    r = client.post(
        "/api/v1/farms",
        json={"farm_name": "Bad2", "boundary_coordinates": [["a", "b"], [0, 0], [0, 1]]},
        headers=headers,
    )
    assert r.status_code == 422


def test_plot_location_and_boundary_flow_through_farm_map(db):
    user = create_user(db, "FA-FM-00000005", "Farmer Esha", "9000000005", "esha@farm.com")
    token = get_token(user)
    headers = {"Authorization": f"Bearer {token}"}
    farm = make_farm(token, latitude=17.9, longitude=78.4)

    r = client.post(
        f"/api/v1/farms/{farm['farm_id']}/plots",
        json={
            "plot_name": "North Field",
            "area": 2.5,
            "latitude": 17.905,
            "longitude": 78.405,
            "boundary_coordinates": [[17.904, 78.404], [17.906, 78.404], [17.906, 78.406]],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    plot = r.json()["data"]
    assert plot["latitude"] == 17.905
    assert plot["boundary_coordinates"]["points"] == [
        [17.904, 78.404],
        [17.906, 78.404],
        [17.906, 78.406],
    ]

    mapped = client.get("/api/v1/maps/farm-map", headers=headers).json()["data"]
    mapped_plot = mapped["plots"][0]
    assert mapped_plot["name"] == "North Field"
    assert mapped_plot["has_location"] is True
    assert mapped_plot["has_boundary"] is True

    # Renaming + moving the field in My Farm is reflected by Farm Map.
    r = client.put(
        f"/api/v1/plots/{plot['plot_id']}",
        json={"plot_name": "North Field Renamed", "area": 3},
        headers=headers,
    )
    assert r.status_code == 200
    mapped = client.get("/api/v1/maps/farm-map", headers=headers).json()["data"]
    assert mapped["plots"][0]["name"] == "North Field Renamed"
    assert mapped["plots"][0]["area"] == 3


def test_farm_map_never_leaks_another_farmers_records(db):
    owner = create_user(db, "FA-FM-00000006", "Farmer Owner", "9000000006", "owner@farm.com")
    other = create_user(db, "FA-FM-00000007", "Farmer Other", "9000000007", "other@farm.com")
    owner_token = get_token(owner)
    other_token = get_token(other)

    farm = make_farm(owner_token, name="Owner Farm", boundary_coordinates=[[1, 2], [3, 4], [5, 6]])
    r = client.post(
        f"/api/v1/farms/{farm['farm_id']}/plots",
        json={"plot_name": "Secret Field"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    secret_plot = r.json()["data"]["plot_id"]

    other_headers = {"Authorization": f"Bearer {other_token}"}
    mapped = client.get("/api/v1/maps/farm-map", headers=other_headers).json()["data"]
    assert mapped["farms"] == []
    assert mapped["plots"] == []

    assert client.put(f"/api/v1/farms/{farm['farm_id']}", json={"farm_name": "Hijacked"}, headers=other_headers).status_code == 404
    assert client.put(f"/api/v1/plots/{secret_plot}", json={"plot_name": "Hijacked"}, headers=other_headers).status_code == 403


def test_farm_map_ignores_farmer_id_from_frontend(db):
    user = create_user(db, "FA-FM-00000008", "Farmer Grace", "9000000008", "grace@farm.com")
    token = get_token(user)
    headers = {"Authorization": f"Bearer {token}"}
    make_farm(token)

    # A farmer_id in the query string must not widen the result set.
    r = client.get(
        "/api/v1/maps/farm-map",
        params={"farmer_id": "FA-FM-00000006", "user_id": "someone-else"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["counts"]["farms"] == 1
