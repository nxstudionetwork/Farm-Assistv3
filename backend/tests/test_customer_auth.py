"""
End-to-end tests for Customer authentication.

Customer accounts were added alongside the existing farmer ones, so the point of
these tests is not only "does a customer log in" but "did the farmer path stay
exactly as it was". Each flow below is a complete journey through the real HTTP
API against a real (temporary) database.

Run with:  pytest tests/test_customer_auth.py
"""

import os
import sys

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_customer_auth.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.database.connection import Base, SessionLocal, engine
from app.main import app
from app.models.customer import Customer, IdSequence
from app.models.user import User
from app.utils.auth import generate_customer_id, hash_password, normalize_customer_id

client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def register_customer(
    client,
    phone="9876543210",
    name="Asha Customer",
    pin="1234",
    email="asha@example.test",
    **extra,
):
    body = {
        "full_name": name,
        "phone_number": phone,
        "pin": pin,
        "email": email,
    }
    body.update(extra)
    return client.post("/api/v1/auth/register/customer", json=body)


def register_farmer(client, phone="9123456780", name="Ravi Farmer", pin="4321"):
    """Use the original, unmodified farmer registration endpoint."""
    return client.post(
        "/api/v1/auth/register",
        json={
            "full_name": name,
            "phone_number": phone,
            "pin": pin,
            "password": pin,
            "village": "Warangal",
            "district": "Warangal",
            "state": "Telangana",
        },
    )


# --------------------------------------------------------------------------- #
# Flow A - farmer registration and login are untouched
# --------------------------------------------------------------------------- #
def test_farmer_registration_and_login_still_work():
    created = register_farmer(client)
    assert created.status_code == 201, created.text

    farmer_id = created.json()["data"]["farmer_id"]
    assert farmer_id.startswith("FA-AS-"), farmer_id
    # The farmer path is unchanged: it still creates a farm and still returns a
    # farm ID alongside the farmer ID.
    assert created.json()["data"].get("farm_id", "").startswith("FA-FARM-")
    assert created.json()["data"]["user"]["role"] == "farmer"

    logged_in = client.post(
        "/api/v1/auth/login",
        json={"farmer_id": farmer_id, "pin": "4321", "role": "farmer"},
    )
    assert logged_in.status_code == 200, logged_in.text
    data = logged_in.json()["data"]
    assert data["user"]["farmer_id"] == farmer_id
    assert data["user"]["role"] == "farmer"
    assert data["access_token"]

    # A farmer session must not be able to reach a customer-only endpoint.
    denied = client.get(
        "/api/v1/customers/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert denied.status_code == 403, denied.text


def test_farmer_can_still_log_in_by_phone_without_a_role_hint():
    """The original phone login posted no role; that must keep working."""
    register_farmer(client)
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"phone_number": "9123456780", "pin": "4321"},
    )
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["data"]["user"]["role"] == "farmer"


# --------------------------------------------------------------------------- #
# Flow B - customer registration issues a real FA-CS-###### ID
# --------------------------------------------------------------------------- #
def test_customer_registration_returns_a_well_formed_customer_id():
    created = register_customer(client)
    assert created.status_code == 201, created.text

    data = created.json()["data"]
    customer_id = data["customer_id"]

    # Exactly the required shape: FA-CS- followed by six digits.
    assert len(customer_id) == len("FA-CS-000000"), customer_id
    assert customer_id.startswith("FA-CS-"), customer_id
    assert customer_id[6:].isdigit() and len(customer_id[6:]) == 6, customer_id

    # The ID is stored, is unique, and the account's role is on the user row.
    session = SessionLocal()
    try:
        customer = session.query(Customer).filter(Customer.customer_id == customer_id).first()
        assert customer is not None
        assert customer.user_id
        user = session.query(User).filter(User.id == customer.user_id).first()
        assert user.role == "customer"
        # A customer has no farmer ID, keeping the two namespaces disjoint.
        assert user.farmer_id is None
        # A customer has no farm.
        from app.models.user import FarmerProfile

        assert session.query(FarmerProfile).filter(
            FarmerProfile.user_id == user.id
        ).first() is None
    finally:
        session.close()

    # The welcome points are real and recorded, not just returned.
    assert data["points_balance"] == 100
    session = SessionLocal()
    try:
        from app.models.customer import CustomerPointsEntry

        entry = session.query(CustomerPointsEntry).filter(
            CustomerPointsEntry.customer_id == customer_id
        ).first()
        assert entry is not None
        assert entry.points == 100
        assert entry.balance_after == 100
    finally:
        session.close()


def test_customer_ids_are_sequential_and_unique():
    first = register_customer(client, phone="9876543210", email="one@example.test")
    second = register_customer(client, phone="9876543211", name="Bina Customer", email="two@example.test")
    third = register_customer(client, phone="9876543212", name="Cara Customer", email="three@example.test")

    ids = [
        first.json()["data"]["customer_id"],
        second.json()["data"]["customer_id"],
        third.json()["data"]["customer_id"],
    ]
    assert ids == ["FA-CS-000001", "FA-CS-000002", "FA-CS-000003"], ids
    assert len(set(ids)) == 3


def test_customer_registration_rejects_a_duplicate_phone():
    register_customer(client)
    again = register_customer(client, name="Someone Else", email="other@example.test")
    assert again.status_code == 400
    assert "already registered" in again.json()["detail"]


def test_a_phone_cannot_be_both_a_farmer_and_a_customer():
    register_farmer(client, phone="9123456780")
    clash = register_customer(client, phone="9123456780", email="clash@example.test")
    assert clash.status_code == 400
    assert "already registered" in clash.json()["detail"]


def test_customer_signup_does_not_ask_for_farming_details():
    """Only the fields a customer actually needs are accepted or required."""
    created = register_customer(
        client,
        address_line="12 Market Road",
        city="Warangal",
        district="Warangal",
        state="Telangana",
        pincode="506002",
        date_of_birth="1995-04-12",
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["customer"]["verification_status"] == "pending"

    # No farm, soil, crop or document information is required to register.
    minimal = client.post(
        "/api/v1/auth/register/customer",
        json={
            "full_name": "Dee Customer",
            "phone_number": "9876500000",
            "pin": "9999",
        },
    )
    assert minimal.status_code == 201, minimal.text
    assert minimal.json()["data"]["customer"]["email"] is None


# --------------------------------------------------------------------------- #
# Flow C - logout, then log back in with the Customer ID
# --------------------------------------------------------------------------- #
def test_customer_logs_out_and_back_in_with_their_customer_id():
    created = register_customer(client)
    customer_id = created.json()["data"]["customer_id"]
    token = created.json()["data"]["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/customers/me", headers=auth).status_code == 200

    logged_out = client.post("/api/v1/auth/logout", headers=auth)
    assert logged_out.status_code == 200, logged_out.text

    # The revoked token is genuinely dead, not merely forgotten by the browser.
    assert client.get("/api/v1/customers/me", headers=auth).status_code in (401, 403)

    logged_in = client.post(
        "/api/v1/auth/login",
        json={"customer_id": customer_id, "pin": "1234", "role": "customer"},
    )
    assert logged_in.status_code == 200, logged_in.text
    data = logged_in.json()["data"]
    assert data["user"]["role"] == "customer"
    assert data["user"]["customer"]["customer_id"] == customer_id
    assert data["customer_id"] == customer_id

    me = client.get("/api/v1/customers/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200, me.text
    assert me.json()["data"]["customer_id"] == customer_id


def test_customer_id_login_tolerates_lowercase_and_missing_padding():
    created = register_customer(client)
    customer_id = created.json()["data"]["customer_id"]

    for variant in [customer_id.lower(), "1", "FA-CS-1", customer_id.replace("-", " - ")]:
        logged_in = client.post(
            "/api/v1/auth/login",
            json={"customer_id": variant, "pin": "1234", "role": "customer"},
        )
        assert logged_in.status_code == 200, f"{variant!r} -> {logged_in.text}"


def test_customer_can_log_in_with_phone_or_email_as_the_alternative():
    """Phone and email are offered inside the customer form, not only on the farmer's."""
    register_customer(client, phone="9876543210", email="asha@example.test")

    by_phone = client.post(
        "/api/v1/auth/login",
        json={"phone_number": "9876543210", "pin": "1234", "role": "customer"},
    )
    assert by_phone.status_code == 200, by_phone.text
    assert by_phone.json()["data"]["user"]["role"] == "customer"

    by_email = client.post(
        "/api/v1/auth/login",
        json={"email": "asha@example.test", "pin": "1234", "role": "customer"},
    )
    assert by_email.status_code == 200, by_email.text
    assert by_email.json()["data"]["user"]["role"] == "customer"


def test_customer_login_rejects_a_wrong_pin():
    register_customer(client)
    customer_id = register_customer(client, phone="9876543211", email="b@example.test").json()["data"]["customer_id"]

    bad = client.post(
        "/api/v1/auth/login",
        json={"customer_id": customer_id, "pin": "0000", "role": "customer"},
    )
    assert bad.status_code == 401
    assert bad.json()["detail"] == "Invalid PIN"


def test_unknown_and_malformed_customer_ids_are_reported_distinctly():
    register_customer(client)

    unknown = client.post(
        "/api/v1/auth/login",
        json={"customer_id": "FA-CS-999999", "pin": "1234", "role": "customer"},
    )
    assert unknown.status_code == 401
    assert "not found" in unknown.json()["detail"].lower()

    malformed = client.post(
        "/api/v1/auth/login",
        json={"customer_id": "not-an-id", "pin": "1234", "role": "customer"},
    )
    assert malformed.status_code == 400
    assert "FA-CS-" in malformed.json()["detail"]


# --------------------------------------------------------------------------- #
# Flow D - neither ID works in the other form
# --------------------------------------------------------------------------- #
def test_a_farmer_id_in_the_customer_form_points_at_the_farmer_form():
    farmer_id = register_farmer(client).json()["data"]["farmer_id"]

    response = client.post(
        "/api/v1/auth/login",
        json={"customer_id": farmer_id, "pin": "4321", "role": "customer"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == (
        "This ID belongs to a Farmer account. Please use Farmer Login."
    )


def test_a_customer_id_in_the_farmer_form_points_at_the_customer_form():
    customer_id = register_customer(client).json()["data"]["customer_id"]

    response = client.post(
        "/api/v1/auth/login",
        json={"farmer_id": customer_id, "pin": "1234", "role": "farmer"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == (
        "This ID belongs to a Customer account. Please use Customer Login."
    )


def test_a_customer_phone_in_the_farmer_form_is_refused():
    register_customer(client, phone="9876543210", email="asha@example.test")

    response = client.post(
        "/api/v1/auth/login",
        json={"phone_number": "9876543210", "pin": "1234", "role": "farmer"},
    )
    assert response.status_code == 403, response.text
    assert "Customer Login" in response.json()["detail"]


def test_a_farmer_phone_in_the_customer_form_is_refused():
    register_farmer(client, phone="9123456780")

    response = client.post(
        "/api/v1/auth/login",
        json={"phone_number": "9123456780", "pin": "4321", "role": "customer"},
    )
    assert response.status_code == 403, response.text
    assert "Farmer Login" in response.json()["detail"]


def test_otp_lookup_is_role_aware():
    customer_id = register_customer(client).json()["data"]["customer_id"]

    farmer_form = client.post(
        "/api/v1/auth/lookup-profile",
        json={"customer_id": customer_id, "role": "farmer"},
    )
    assert farmer_form.status_code == 403
    assert "Customer Login" in farmer_form.json()["detail"]

    customer_form = client.post(
        "/api/v1/auth/lookup-profile",
        json={"customer_id": customer_id, "role": "customer"},
    )
    assert customer_form.status_code == 200, customer_form.text
    found = customer_form.json()["data"]
    assert found["role"] == "customer"
    assert found["customer_id"] == customer_id
    # The lookup never discloses the other namespace's ID.
    assert found["farmer_id"] is None


def test_lookup_by_phone_or_email_returns_the_customer_id():
    """A customer found by phone or email still needs its Customer ID.

    Only the customer_id branch loads the Customer row, so these two paths used
    to fall through and answer with a 500 instead of a profile.
    """
    customer_id = register_customer(
        client, phone="9876543210", email="asha@example.test"
    ).json()["data"]["customer_id"]

    for payload in (
        {"phone_number": "9876543210", "role": "customer"},
        {"email": "asha@example.test", "role": "customer"},
        {"phone_number": "9876543210"},
    ):
        response = client.post("/api/v1/auth/lookup-profile", json=payload)
        assert response.status_code == 200, (payload, response.text)
        found = response.json()["data"]
        assert found["role"] == "customer"
        assert found["customer_id"] == customer_id
        assert found["farmer_id"] is None

    # And the customer form still refuses a farmer reached the same way.
    register_farmer(client, phone="9123456780")
    refused = client.post(
        "/api/v1/auth/lookup-profile",
        json={"phone_number": "9123456780", "role": "customer"},
    )
    assert refused.status_code == 403
    assert "Farmer Login" in refused.json()["detail"]


# --------------------------------------------------------------------------- #
# Flow E - role is enforced on the server, not by the client
# --------------------------------------------------------------------------- #
def test_a_customer_cannot_reach_a_customer_endpoint_by_asking_for_an_id():
    """There is no ?customer_id= on any customer endpoint."""
    customer_a = register_customer(client, phone="9876543210", email="a@example.test")
    customer_b = register_customer(client, phone="9876543211", name="Bina Customer", email="b@example.test")

    token = customer_a.json()["data"]["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    b_id = customer_b.json()["data"]["customer_id"]

    # Every customer route answers from the token, so the attempt to name
    # another customer is either ignored or rejected -- never obeyed.
    for path in ("/api/v1/customers/me", "/api/v1/customers/me/points", "/api/v1/customers/me/dashboard"):
        response = client.get(f"{path}?customer_id={b_id}", headers=auth)
        assert response.status_code == 200, f"{path} -> {response.text}"
        if path.endswith("/me"):
            assert response.json()["data"]["customer_id"] != b_id

    impersonated = client.get(f"/api/v1/customers/me?customer_id={b_id}", headers=auth)
    assert impersonated.json()["data"]["customer_id"] == customer_a.json()["data"]["customer_id"]


def test_a_farmer_token_cannot_reach_customer_endpoints():
    farmer_id = register_farmer(client).json()["data"]["farmer_id"]
    token = client.post(
        "/api/v1/auth/login",
        json={"farmer_id": farmer_id, "pin": "4321", "role": "farmer"},
    ).json()["data"]["access_token"]

    for path in ("/api/v1/customers/me", "/api/v1/customers/me/points", "/api/v1/customers/me/dashboard"):
        response = client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403, f"{path} -> {response.text}"


def test_an_anonymous_caller_cannot_reach_customer_endpoints():
    assert client.get("/api/v1/customers/me").status_code in (401, 403)


def test_auth_me_reports_the_role_stored_in_the_database():
    """The client is told its role; it never gets to state it."""
    customer_id = register_customer(client).json()["data"]["customer_id"]
    token = client.post(
        "/api/v1/auth/login",
        json={"customer_id": customer_id, "pin": "1234", "role": "customer"},
    ).json()["data"]["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    data = me.json()["data"]
    assert data["role"] == "customer"
    assert data["customer_id"] == customer_id
    assert data["points_balance"] == 100
    assert data["farmer_id"] is None


def test_a_farmer_role_cannot_be_gained_by_registering_a_customer_with_a_farmer_shape():
    """A customer account is a customer regardless of what the request contains."""
    created = client.post(
        "/api/v1/auth/register/customer",
        json={
            "full_name": "Mallory Person",
            "phone_number": "9876543219",
            "pin": "1234",
            "farmer_id": "FA-AS-00000099",
            "role": "farmer",
        },
    )
    assert created.status_code == 201, created.text
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.phone_number == "9876543219").first()
        assert user.role == "customer"
        assert user.farmer_id is None
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Flow F - one customer can never see another customer's data
# --------------------------------------------------------------------------- #
def test_customers_cannot_read_each_others_profiles_or_points():
    a = register_customer(client, phone="9876543210", name="Asha Customer", email="a@example.test")
    b = register_customer(client, phone="9876543211", name="Bina Customer", email="b@example.test")

    a_auth = {"Authorization": f"Bearer {a.json()['data']['access_token']}"}
    b_auth = {"Authorization": f"Bearer {b.json()['data']['access_token']}"}

    a_me = client.get("/api/v1/customers/me", headers=a_auth).json()["data"]
    b_me = client.get("/api/v1/customers/me", headers=b_auth).json()["data"]

    assert a_me["customer_id"] == "FA-CS-000001"
    assert b_me["customer_id"] == "FA-CS-000002"
    assert a_me["full_name"] == "Asha Customer"
    assert b_me["full_name"] == "Bina Customer"


def test_customer_addresses_and_plants_are_private_to_their_owner():
    a = register_customer(
        client, phone="9876543210", name="Asha Customer", email="a@example.test",
        address_line="12 Market Road", city="Warangal", district="Warangal",
        state="Telangana", pincode="506002",
    )
    b = register_customer(client, phone="9876543211", name="Bina Customer", email="b@example.test")

    a_auth = {"Authorization": f"Bearer {a.json()['data']['access_token']}"}
    b_auth = {"Authorization": f"Bearer {b.json()['data']['access_token']}"}

    a_addresses = client.get("/api/v1/customers/me/addresses", headers=a_auth).json()["data"]
    assert len(a_addresses) == 1
    address_id = a_addresses[0]["id"]

    b_addresses = client.get("/api/v1/customers/me/addresses", headers=b_auth).json()["data"]
    assert b_addresses == []

    # B cannot read, change or delete A's address by guessing its identifier.
    assert client.put(f"/api/v1/customers/me/addresses/{address_id}", json={"city": "Hacked"}, headers=b_auth).status_code == 404
    assert client.delete(f"/api/v1/customers/me/addresses/{address_id}", headers=b_auth).status_code == 404

    still_there = client.get("/api/v1/customers/me/addresses", headers=a_auth).json()["data"]
    assert len(still_there) == 1
    assert still_there[0]["address_line"] == "12 Market Road"


def test_a_plant_added_by_one_customer_is_invisible_to_another():
    a = register_customer(client, phone="9876543210", email="a@example.test")
    b = register_customer(client, phone="9876543211", name="Bina Customer", email="b@example.test")
    a_auth = {"Authorization": f"Bearer {a.json()['data']['access_token']}"}
    b_auth = {"Authorization": f"Bearer {b.json()['data']['access_token']}"}

    # Point at a real row in the existing ``crops`` catalogue. The app's seed
    # data is loaded on startup, which TestClient does not trigger here, so add
    # the one crop this test needs directly -- same table the farmer side uses.
    from app.models.crop import Crop

    session = SessionLocal()
    try:
        crop = session.query(Crop).filter(Crop.name == "Tomato").first()
        if crop is None:
            crop = Crop(name="Tomato", crop_id="C-TOMATO")
            session.add(crop)
            session.commit()
        crop_id = crop.id
    finally:
        session.close()

    created = client.post(
        "/api/v1/customers/me/plants",
        json={"crop_id": crop_id, "nickname": "My tomato", "quantity": 3},
        headers=a_auth,
    )
    assert created.status_code in (200, 201), created.text
    plant = created.json()["data"]
    plant_id = plant["plant_id"]
    # The plant is stamped with its owner's Customer ID, read from the token.
    assert plant["customer_id"] == a.json()["data"]["customer_id"]
    assert plant["crop_name"], "expected the real crop name to be joined in"

    assert client.get("/api/v1/customers/me/plants", headers=b_auth).json()["data"]["plants"] == []
    assert client.put(f"/api/v1/customers/me/plants/{plant_id}", json={"quantity": 99}, headers=b_auth).status_code == 404
    assert client.delete(f"/api/v1/customers/me/plants/{plant_id}", headers=b_auth).status_code == 404

    # The owner can still change their own plant.
    updated = client.put(
        f"/api/v1/customers/me/plants/{plant_id}",
        json={"quantity": 5},
        headers=a_auth,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["quantity"] == 5

    plants = client.get("/api/v1/customers/me/plants", headers=a_auth).json()["data"]["plants"]
    assert len(plants) == 1
    assert plants[0]["quantity"] == 5


# --------------------------------------------------------------------------- #
# The ID itself
# --------------------------------------------------------------------------- #
def test_customer_id_formatting_rules():
    assert normalize_customer_id("FA-CS-000001") == "FA-CS-000001"
    assert normalize_customer_id("fa-cs-1") == "FA-CS-000001"
    assert normalize_customer_id(" 1 ") == "FA-CS-000001"
    # Beyond six digits is not a customer ID.
    assert normalize_customer_id("FA-CS-1234567") == ""
    # A farmer ID is never a customer ID.
    assert normalize_customer_id("FA-AS-00000001") == ""
    assert normalize_customer_id("FA-CS-00000X") == ""


def test_the_sequence_never_reissues_an_id_already_in_the_table():
    """Guards the collision case the database unique index would otherwise catch."""
    session = SessionLocal()
    try:
        first = generate_customer_id(session)
        # customers.user_id is NOT NULL, so the row standing in for "an ID that is
        # already taken" still needs a real owner to point at.
        owner = User(
            full_name="Existing Holder",
            phone_number="9000000001",
            password_hash=hash_password("1234"),
            role="customer",
            is_active=True,
        )
        session.add(owner)
        session.flush()
        session.add(Customer(user_id=owner.id, customer_id=first, full_name="Existing Holder"))
        session.commit()

        second = generate_customer_id(session)
        assert second != first
        assert second == "FA-CS-000002"

        # Deleting the counter row must not restart numbering over live rows.
        # The recovery path seeds from the highest ID actually in the table, so
        # it skips the row above. FA-CS-000002 is not in the table yet, so
        # handing it out again here is correct, not a collision.
        session.query(IdSequence).filter(IdSequence.scope == "customer_id").delete()
        session.commit()
        third = generate_customer_id(session)
        assert third != first, third
        assert int(third[6:]) >= 2, third
    finally:
        session.rollback()
        session.close()


def test_customer_settings_are_stored_per_customer():
    a = register_customer(client, phone="9876543210", email="a@example.test")
    b = register_customer(client, phone="9876543211", name="Bina Customer", email="b@example.test")
    a_auth = {"Authorization": f"Bearer {a.json()['data']['access_token']}"}
    b_auth = {"Authorization": f"Bearer {b.json()['data']['access_token']}"}

    before = client.get("/api/v1/customers/me/settings", headers=b_auth).json()["data"]
    assert before["notifications"]["orders"] is True

    updated = client.put(
        "/api/v1/customers/me/settings",
        json={"notifications": {"orders": False, "products": False}},
        headers=a_auth,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["notifications"]["orders"] is False

    # B is unaffected.
    after = client.get("/api/v1/customers/me/settings", headers=b_auth).json()["data"]
    assert after["notifications"]["orders"] is True