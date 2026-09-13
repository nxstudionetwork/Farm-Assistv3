"""End-to-end coverage for the Farm Techniques + Bookmarks module.

Follows the tests/test_community.py conventions: dedicated SQLite file, full schema
rebuild, row wipe per test, TestClient, and real JWT auth.
"""

import os
import sys

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_techniques.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models import User
from app.utils.auth import hash_password

client = TestClient(app)


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


def test_techniques_list_and_categories(db):
    farmer = _mk_user(db, "9020000001", "tech1@farm.com", 1)
    token = _login("9020000001", "tech1@farm.com")
    h = _auth(token)

    cats = client.get("/api/v1/techniques/categories/all", headers=h)
    assert cats.status_code == 200
    assert isinstance(cats.json()["data"], list)
    assert len(cats.json()["data"]) > 0, "seed data should populate categories"

    r = client.get("/api/v1/techniques", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, list)
    assert len(data) > 0, "seed data should populate techniques"

    first = data[0]
    assert first["id"]
    assert first["title"]
    assert first["category"]
    assert "steps" in first


def test_bookmark_flow_isolation_between_users(db):
    farmer_a = _mk_user(db, "9020000002", "tech2@farm.com", 2)
    farmer_b = _mk_user(db, "9020000003", "tech3@farm.com", 3)
    token_a = _login("9020000002", "tech2@farm.com")
    token_b = _login("9020000003", "tech3@farm.com")

    temps = client.get("/api/v1/techniques", headers=_auth(token_a)).json()["data"]
    assert temps, "seed techniques must exist"
    tex_id = temps[0]["id"]

    # Farmer A bookmarks
    r = client.post(f"/api/v1/techniques/{tex_id}/bookmark", headers=_auth(token_a))
    assert r.status_code == 200
    assert r.json()["data"]["bookmarked"] is True

    # Farmer A sees 1 bookmark
    list_a = client.get("/api/v1/techniques/bookmarks/list", headers=_auth(token_a))
    assert len(list_a.json()["data"]) == 1

    # Farmer B sees 0 bookmarks (per-user isolation)
    list_b = client.get("/api/v1/techniques/bookmarks/list", headers=_auth(token_b))
    assert len(list_b.json()["data"]) == 0

    # Bookmarked flag reflects on list for A only
    list_a2 = client.get("/api/v1/techniques", headers=_auth(token_a)).json()["data"]
    bm_a = [t for t in list_a2 if t["id"] == tex_id]
    assert bm_a and bm_a[0]["bookmarked"] is True

    list_b2 = client.get("/api/v1/techniques", headers=_auth(token_b)).json()["data"]
    bm_b = [t for t in list_b2 if t["id"] == tex_id]
    assert bm_b and bm_b[0]["bookmarked"] is False

    # Toggle off for A
    r = client.post(f"/api/v1/techniques/{tex_id}/bookmark", headers=_auth(token_a))
    assert r.json()["data"]["bookmarked"] is False
    list_a3 = client.get("/api/v1/techniques/bookmarks/list", headers=_auth(token_a))
    assert len(list_a3.json()["data"]) == 0


def test_technique_detail_related_and_persistence(db):
    farmer = _mk_user(db, "9020000004", "tech4@farm.com", 4)
    token = _login("9020000004", "tech4@farm.com")
    h = _auth(token)

    temps = client.get("/api/v1/techniques", headers=h).json()["data"]
    tex_id = temps[0]["id"]

    d = client.get(f"/api/v1/techniques/{tex_id}", headers=h)
    assert d.status_code == 200
    data = d.json()["data"]
    assert data["id"] == tex_id
    assert isinstance(data.get("related"), list)

    # Bookmark persists across "sessions" (new token for same user)
    client.post(f"/api/v1/techniques/{tex_id}/bookmark", headers=h)
    new_token = _login("9020000004", "tech4@farm.com")
    list_res = client.get("/api/v1/techniques/bookmarks/list", headers=_auth(new_token))
    assert len(list_res.json()["data"]) == 1