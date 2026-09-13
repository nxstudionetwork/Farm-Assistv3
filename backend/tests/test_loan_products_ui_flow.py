"""UI-flow sweep: exercises the exact endpoints/params the loans page calls
and asserts no server errors (500) anywhere in the flow.
"""

import os
import sys

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_loans_ui.db"
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


def _login(phone, email, pin="1234"):
    r = client.post(
        "/api/v1/auth/login",
        json={"phone_number": phone, "email": email, "pin": pin},
    )
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["data"]["access_token"]


def _no_5xx(res):
    assert res.status_code < 500, f"server error {res.status_code}: {res.text[:400]}"


def test_catalog_ui_sweep_no_server_errors():
    user = User(
        full_name="UI Sweep Farmer",
        phone_number="9090000001",
        email="uisweep@farm.com",
        password_hash=hash_password("1234"),
        preferred_language="en",
        is_active=True,
    )
    db = SessionLocal()
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    finally:
        db.close()

    token = _login("9090000001", "uisweep@farm.com")
    h = {"Authorization": f"Bearer {token}"}

    urls = [
        "/api/v1/loans/categories",
        "/api/v1/loans/filters",
        "/api/v1/loans/products",
        "/api/v1/loans/products?page=1&limit=12",
        "/api/v1/loans/products?page=2&limit=12",
        "/api/v1/loans/products?page=99&limit=12",
        "/api/v1/loans/products?search=kisan",
        "/api/v1/loans/products?search=crop+loan",
        "/api/v1/loans/products?lender=State+Bank+of+India",
        "/api/v1/loans/products?state=All+India",
        "/api/v1/loans/products?government_backed=1",
        "/api/v1/loans/products?government_backed=0",
        "/api/v1/loans/products?collateral_free=1",
        "/api/v1/loans/products?collateral_free=0",
        "/api/v1/loans/products?sort=amount_asc",
        "/api/v1/loans/products?sort=amount_desc",
        "/api/v1/loans/products?sort=rate",
        "/api/v1/loans/products?sort=name",
        "/api/v1/loans/search?q=kisan",
        "/api/v1/loans/products/saved?limit=50",
        "/api/v1/loans/applications?page=1&limit=10",
        "/api/v1/loans/applications?status=submitted",
        "/api/v1/loans/farmer-loans",
        "/api/v1/loans/overview",
    ]
    for url in urls:
        _no_5xx(client.get(url, headers=h))

    items = client.get("/api/v1/loans/products", headers=h).json()["data"]["items"]
    assert items, "expected seeded products"
    prod = items[0]
    pid = prod["product_id"] or prod["id"]

    _no_5xx(client.get(f"/api/v1/loans/products/{pid}", headers=h))
    _no_5xx(client.post(f"/api/v1/loans/products/{pid}/save", headers=h))
    res = client.get(f"/api/v1/loans/products/{pid}", headers=h)
    assert res.json()["data"]["is_saved"] is True

    _no_5xx(
        client.post(
            "/api/v1/loans/check-eligibility",
            headers=h,
            json={
                "product_id": pid,
                "farmer_type": "individual",
                "farmer_category": "small",
                "state": "Maharashtra",
                "district": "Nagpur",
                "crop": "Cotton",
                "farm_size_acres": 3.5,
                "loan_amount": 200000,
                "has_existing_agri_loan": False,
            },
        )
    )

    res = client.post(
        "/api/v1/loans/applications",
        headers=h,
        json={
            "product_id": pid,
            "applicant_name": "UI Sweep Farmer",
            "phone_number": "9090000001",
            "email": "uisweep@farm.com",
            "aadhaar_number": "123412341234",
            "state": "Maharashtra",
            "district": "Nagpur",
            "farm_size": 3.5,
            "crop": "Cotton",
            "land_type": "Owned",
            "purpose": "Buy seeds and fertilisers",
            "requested_amount": 200000,
            "notes": "ok",
        },
    )
    _no_5xx(res)
    app_id = res.json()["data"]["application_id"]

    _no_5xx(client.get(f"/api/v1/loans/applications/{app_id}", headers=h))
    _no_5xx(client.patch(f"/api/v1/loans/applications/{app_id}", headers=h, json={"notes": "updated"}))

    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64 + b"\xff\xd9"
    files = {"file": ("aadhar.jpg", jpeg, "image/jpeg")}
    res = client.post(
        f"/api/v1/loans/applications/{app_id}/documents",
        headers=h,
        data={"document_type": "aadhaar_card"},
        files=files,
    )
    _no_5xx(res)
    doc_id = res.json()["data"]["id"]

    _no_5xx(client.get(f"/api/v1/loans/applications/{app_id}/documents/{doc_id}/file", headers=h))
    _no_5xx(client.delete(f"/api/v1/loans/products/{pid}/save", headers=h))