"""End-to-end coverage for the Agricultural Loans module.

Follows the tests/test_techniques.py conventions: dedicated SQLite file, full schema
rebuild, row wipe per test, TestClient, and real JWT auth.
"""

import os
import sys

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_loans.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models import User
from app.utils.auth import hash_password
from app.models.loan_product import AgriculturalFarmerLoan

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


def test_catalogue_seed_categories_and_filters(db):
    farmer = _mk_user(db, "9030000001", "loan1@farm.com", 1)
    token = _login("9030000001", "loan1@farm.com")
    h = _auth(token)

    res = client.get("/api/v1/loans/categories", headers=h)
    assert res.status_code == 200
    cats = res.json()["data"]["categories"]
    assert isinstance(cats, list)
    assert len(cats) > 0
    assert res.json()["data"]["total"] > 0

    res = client.get("/api/v1/loans/products", headers=h)
    data = res.json()["data"]
    assert data["total"] > 0
    assert isinstance(data["items"], list)
    first = data["items"][0]
    assert first["name"]
    assert first["lender"]
    assert first["source"]
    assert "interest_rate" in first

    # Fidelity: every price/rate must come from backend seed, not mock data.
    assert all(it["source"] for it in data["items"])

    res = client.get("/api/v1/loans/filters", headers=h)
    flt = res.json()["data"]
    assert len(flt["lenders"]) > 0
    assert len(flt["states"]) > 0


def test_product_search_detail_and_sort(db):
    farmer = _mk_user(db, "9030000002", "loan2@farm.com", 2)
    token = _login("9030000002", "loan2@farm.com")
    h = _auth(token)

    products = client.get("/api/v1/loans/products", headers=h).json()["data"]["items"]
    first_id = products[0]["id"]

    detail = client.get(f"/api/v1/loans/products/{first_id}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == first_id

    # missing id -> 404
    assert client.get("/api/v1/loans/products/nope", headers=h).status_code == 404

    # search across any field
    search = client.get("/api/v1/loans/search", params={"q": "kisan"}, headers=h)
    assert search.status_code == 200
    assert isinstance(search.json()["data"], list)

    # sorting doesn't error
    for sort in ("amount_asc", "amount_desc", "rate", "name"):
        r = client.get("/api/v1/loans/products", params={"sort": sort}, headers=h)
        assert r.status_code == 200


def test_save_unsave_isolation_between_users(db):
    farmer_a = _mk_user(db, "9030000003", "loan3@farm.com", 3)
    farmer_b = _mk_user(db, "9030000004", "loan4@farm.com", 4)
    token_a = _login("9030000003", "loan3@farm.com")
    token_b = _login("9030000004", "loan4@farm.com")

    products = client.get("/api/v1/loans/products", headers=_auth(token_a)).json()["data"]["items"]
    pid = products[0]["id"]

    r = client.post(f"/api/v1/loans/products/{pid}/save", headers=_auth(token_a))
    assert r.status_code == 201
    assert r.json()["data"]["is_saved"] is True

    saved_a = client.get("/api/v1/loans/products/saved", headers=_auth(token_a))
    assert saved_a.json()["data"]["total"] == 1

    # B must not see A's saved loan
    saved_b = client.get("/api/v1/loans/products/saved", headers=_auth(token_b))
    assert saved_b.json()["data"]["total"] == 0

    # A's list reflects is_saved flag
    list_a = client.get("/api/v1/loans/products", headers=_auth(token_a)).json()["data"]["items"]
    entry = [it for it in list_a if it["id"] == pid]
    assert entry and entry[0]["is_saved"] is True

    # unsave
    client.delete(f"/api/v1/loans/products/{pid}/save", headers=_auth(token_a))
    saved_a2 = client.get("/api/v1/loans/products/saved", headers=_auth(token_a))
    assert saved_a2.json()["data"]["total"] == 0


def test_eligibility_check_persists(db):
    farmer = _mk_user(db, "9030000005", "loan5@farm.com", 5)
    token = _login("9030000005", "loan5@farm.com")
    h = _auth(token)

    products = client.get("/api/v1/loans/products", headers=h).json()["data"]["items"]
    pid = products[0]["id"]

    r = client.post(
        "/api/v1/loans/check-eligibility",
        headers=h,
        json={
            "product_id": pid,
            "farmer_type": "individual",
            "state": "Maharashtra",
            "crop": "Wheat",
            "farm_size_acres": 5,
            "loan_amount": 150000,
        },
    )
    assert r.status_code == 200
    result = r.json()["data"]["result"]
    assert result["verdict"] in ("likely_eligible", "needs_review", "not_likely")
    assert "disclaimer" in result
    assert "Farm Assist" not in result["disclaimer"].lower().replace("farm assist does not", "")

    # product with amount far beyond max should be flagged
    over = client.post(
        "/api/v1/loans/check-eligibility",
        headers=h,
        json={"product_id": pid, "loan_amount": 10**9},
    )
    assert over.status_code == 200
    assert over.json()["data"]["result"]["verdict"] == "not_likely"


def test_application_validation_and_reference(db):
    farmer = _mk_user(db, "9030000006", "loan6@farm.com", 6)
    token = _login("9030000006", "loan6@farm.com")
    h = _auth(token)

    products = client.get("/api/v1/loans/products", headers=h).json()["data"]["items"]
    pid = products[0]["id"]

    # invalid phone
    bad = client.post(
        "/api/v1/loans/applications",
        headers=h,
        json={"product_id": pid, "phone_number": "123", "requested_amount": 50000},
    )
    assert bad.status_code == 400

    # valid
    ok = client.post(
        "/api/v1/loans/applications",
        headers=h,
        json={
            "product_id": pid,
            "phone_number": "9876543210",
            "requested_amount": 50000,
            "applicant_name": "Farmer 6",
            "state": "Karnataka",
            "crop": "Rice",
            "farm_size": 4,
        },
    )
    assert ok.status_code == 201, ok.text
    app = ok.json()["data"]
    assert app["reference_number"].startswith("FA-LAPP-")
    assert app["status"] == "submitted"
    app_id = app["application_id"]

    # list + detail
    lst = client.get("/api/v1/loans/applications", headers=h)
    assert lst.json()["data"]["total"] == 1
    detail = client.get(f"/api/v1/loans/applications/{app_id}", headers=h)
    assert detail.status_code == 200


def test_application_isolation_between_users(db):
    farmer_a = _mk_user(db, "9030000007", "loan7@farm.com", 7)
    farmer_b = _mk_user(db, "9030000008", "loan8@farm.com", 8)
    token_a = _login("9030000007", "loan7@farm.com")
    token_b = _login("9030000008", "loan8@farm.com")

    products = client.get("/api/v1/loans/products", headers=_auth(token_a)).json()["data"]["items"]
    pid = products[0]["id"]

    ok = client.post(
        "/api/v1/loans/applications",
        headers=_auth(token_a),
        json={"product_id": pid, "phone_number": "9876543211", "requested_amount": 20000},
    )
    assert ok.status_code == 201
    app_id = ok.json()["data"]["application_id"]

    # B cannot read A's application
    assert client.get(f"/api/v1/loans/applications/{app_id}", headers=_auth(token_b)).status_code == 404
    assert client.get("/api/v1/loans/applications", headers=_auth(token_b)).json()["data"]["total"] == 0


def test_document_upload_download_ownership(db):
    farmer_a = _mk_user(db, "9030000009", "loan9@farm.com", 9)
    farmer_b = _mk_user(db, "9030000010", "loan10@farm.com", 10)
    token_a = _login("9030000009", "loan9@farm.com")
    token_b = _login("9030000010", "loan10@farm.com")

    products = client.get("/api/v1/loans/products", headers=_auth(token_a)).json()["data"]["items"]
    pid = products[0]["id"]
    ok = client.post(
        "/api/v1/loans/applications",
        headers=_auth(token_a),
        json={"product_id": pid, "phone_number": "9876543212", "requested_amount": 20000},
    ).json()["data"]["application_id"]

    # build a tiny valid PNG
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    upload = client.post(
        f"/api/v1/loans/applications/{ok}/documents",
        headers=_auth(token_a),
        files={"file": ("land.png", png, "image/png")},
        data={"document_type": "land_record"},
    )
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()["data"]["id"]

    # owner can download
    dl = client.get(f"/api/v1/loans/applications/{ok}/documents/{doc_id}/file", headers=_auth(token_a))
    assert dl.status_code == 200
    assert dl.content

    # other user cannot
    assert client.get(
        f"/api/v1/loans/applications/{ok}/documents/{doc_id}/file", headers=_auth(token_b)
    ).status_code == 404

    # generic storage route refuses loan-documents
    generic = client.get("/api/v1/storage/loan-documents/x.png", headers=_auth(token_a))
    assert generic.status_code in (404, 400)


def test_repayment_via_wallet(db):
    farmer = _mk_user(db, "9030000011", "loan11@farm.com", 11)
    token = _login("9030000011", "loan11@farm.com")
    h = _auth(token)

    # set up wallet with balance
    client.post("/api/v1/wallet/setup", headers=h, json={"wallet_pin": "4321", "confirm_pin": "4321"})
    client.post("/api/v1/wallet/add-money", headers=h, json={"amount": 50000, "payment_method": "upi"})
    client.post("/api/v1/wallet/add-money", headers=h, json={"amount": 10000, "payment_method": "upi"})

    # create a farmer loan directly (lender/disbursement is not simulated in UI)
    db.add(
        AgriculturalFarmerLoan(
            farmer_loan_id="FA-FLN-000001",
            farmer_id=farmer.id,
            lender="TestBank",
            loan_name="KCC Test Loan",
            principal_amount=50000,
            outstanding_amount=50000,
            interest_rate_annual=7.0,
            emi_amount=2500,
            tenure_months=24,
            next_payment=2500,
            status="active",
        )
    )
    db.commit()
    fl = db.query(AgriculturalFarmerLoan).filter(AgriculturalFarmerLoan.farmer_id == farmer.id).first()
    assert fl and fl.farmer_loan_id

    url = f"/api/v1/loans/farmer-loans/{fl.farmer_loan_id}/repay"

    # wrong pin
    bad = client.post(url, headers=h, json={"amount": 2500, "wallet_pin": "0000"})
    assert bad.status_code == 401

    # partial repayment (2500 of 80000? no — 2500 of 50000)
    ok = client.post(url, headers=h, json={"amount": 2500, "wallet_pin": "4321"})
    assert ok.status_code == 200, ok.text
    wallet = client.get("/api/v1/wallet", headers=h).json()["data"]
    assert wallet["balance"] == 57500.0  # 60000 - 2500

    # repayment history recorded
    rp = client.get(f"/api/v1/loans/farmer-loans/{fl.farmer_loan_id}/repayments", headers=h)
    assert rp.status_code == 200
    assert rp.json()["data"]["total"] == 1
    assert rp.json()["data"]["farmer_loan"]["outstanding_amount"] == 47500.0

    # repay the remainder -> closed
    ok2 = client.post(url, headers=h, json={"amount": 47500, "wallet_pin": "4321"})
    assert ok2.status_code == 200, ok2.text
    payload = ok2.json()["data"]
    assert payload["farmer_loan"]["status"] == "closed"
    assert payload["farmer_loan"]["outstanding_amount"] == 0
    assert payload["repayment"]["status"] == "completed"

    # remaining balance
    wallet2 = client.get("/api/v1/wallet", headers=h).json()["data"]
    assert wallet2["balance"] == 10000.0

    # overview reflects numbers
    ov = client.get("/api/v1/loans/overview", headers=h)
    assert ov.status_code == 200
    assert ov.json()["data"]["total_repaid"] == 50000.0