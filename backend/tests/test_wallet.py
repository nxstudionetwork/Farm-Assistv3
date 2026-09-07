import sys
import os

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_farm_assist.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction, BankAccount, MoneyRequest
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


def test_wallet_setup_flow(db):
    user_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    token_a = get_token(user_a)
    headers = {"Authorization": f"Bearer {token_a}"}

    # Initial get creates wallet record
    r = client.get("/api/v1/wallet", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["balance"] == 0.0
    assert data["is_setup_complete"] is False

    # Setup PIN
    r = client.post("/api/v1/wallet/setup", headers=headers, json={"wallet_pin": "1234", "confirm_pin": "1234"})
    assert r.status_code == 200
    assert r.json()["data"]["is_setup_complete"] is True

    # Verify PIN endpoint
    r = client.post("/api/v1/wallet/verify-pin", headers=headers, json={"wallet_pin": "1234"})
    assert r.status_code == 200
    assert r.json()["data"]["verified"] is True

    # Wrong PIN
    r = client.post("/api/v1/wallet/verify-pin", headers=headers, json={"wallet_pin": "9999"})
    assert r.status_code == 401


def test_add_money_and_limits(db):
    user_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    token_a = get_token(user_a)
    headers = {"Authorization": f"Bearer {token_a}"}

    # Setup PIN first
    client.post("/api/v1/wallet/setup", headers=headers, json={"wallet_pin": "1234", "confirm_pin": "1234"})

    # Add 5000
    r = client.post("/api/v1/wallet/add-money", headers=headers, json={"amount": 5000.0, "payment_method": "upi"})
    assert r.status_code == 200
    assert r.json()["data"]["wallet"]["balance"] == 5000.0

    # Summary
    r = client.get("/api/v1/wallet/summary", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["balance"] == 5000.0
    assert r.json()["data"]["total_credits"] == 5000.0


def test_search_recipient_by_phone_and_farmer_id(db):
    user_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    user_b = create_user(db, "FA-AS-00000002", "Farmer Suresh", "9123456780", "suresh@farm.com")
    token_a = get_token(user_a)
    headers = {"Authorization": f"Bearer {token_a}"}

    # Search by 10-digit phone
    r = client.post("/api/v1/wallet/search-user", headers=headers, json={"query": "9123456780"})
    assert r.status_code == 200
    assert r.json()["data"]["found"] is True
    assert r.json()["data"]["user"]["full_name"] == "Farmer Suresh"

    # Search by Farmer ID
    r = client.post("/api/v1/wallet/search-user", headers=headers, json={"query": "FA-AS-00000002"})
    assert r.status_code == 200
    assert r.json()["data"]["found"] is True

    # Search by short numeric ID
    r = client.post("/api/v1/wallet/search-user", headers=headers, json={"query": "2"})
    assert r.status_code == 200
    assert r.json()["data"]["found"] is True

    # Self search
    r = client.post("/api/v1/wallet/search-user", headers=headers, json={"query": "9876543210"})
    assert r.status_code == 200
    assert r.json()["data"]["found"] is False


def test_transfer_money_atomic_and_isolation(db):
    user_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    user_b = create_user(db, "FA-AS-00000002", "Farmer Suresh", "9123456780", "suresh@farm.com")
    token_a = get_token(user_a)
    token_b = get_token(user_b)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Setup both wallets
    client.post("/api/v1/wallet/setup", headers=headers_a, json={"wallet_pin": "1234", "confirm_pin": "1234"})
    client.post("/api/v1/wallet/setup", headers=headers_b, json={"wallet_pin": "5678", "confirm_pin": "5678"})

    # Add 10000 to Farmer A
    client.post("/api/v1/wallet/add-money", headers=headers_a, json={"amount": 10000.0})

    # Transfer 3500 from A to B
    r = client.post("/api/v1/wallet/transfer", headers=headers_a, json={
        "recipient_id": "FA-AS-00000002",
        "amount": 3500.0,
        "note": "Payment for tractor rental",
        "wallet_pin": "1234",
    })
    assert r.status_code == 200
    assert r.json()["data"]["wallet"]["balance"] == 6500.0

    # Verify Farmer B balance is 3500
    r_b = client.get("/api/v1/wallet", headers=headers_b)
    assert r_b.status_code == 200
    assert r_b.json()["data"]["balance"] == 3500.0

    # Farmer A transactions
    r_txns_a = client.get("/api/v1/wallet/transactions", headers=headers_a)
    assert r_txns_a.status_code == 200
    assert len(r_txns_a.json()["data"]["items"]) == 2

    # Farmer B transactions
    r_txns_b = client.get("/api/v1/wallet/transactions", headers=headers_b)
    assert r_txns_b.status_code == 200
    assert len(r_txns_b.json()["data"]["items"]) == 1
    assert r_txns_b.json()["data"]["items"][0]["transaction_type"] == "credit"
    assert r_txns_b.json()["data"]["items"][0]["amount"] == 3500.0


def test_bank_accounts_crud(db):
    user_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    token_a = get_token(user_a)
    headers = {"Authorization": f"Bearer {token_a}"}

    # Add bank account
    r = client.post("/api/v1/wallet/bank-accounts", headers=headers, json={
        "bank_name": "State Bank of India",
        "account_holder_name": "Ramesh Kumar",
        "account_number": "123456789012",
        "ifsc_code": "SBIN0001234",
        "account_type": "savings",
    })
    assert r.status_code == 200
    account_id = r.json()["data"]["account_id"]
    assert r.json()["data"]["masked_account_number"] == "XXXX XXXX 9012"

    # List bank accounts
    r = client.get("/api/v1/wallet/bank-accounts", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["data"]["items"]) == 1

    # Remove bank account
    r = client.delete(f"/api/v1/wallet/bank-accounts/{account_id}", headers=headers)
    assert r.status_code == 200

    # List again
    r = client.get("/api/v1/wallet/bank-accounts", headers=headers)
    assert len(r.json()["data"]["items"]) == 0
