import os
import sys

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_marketplace_rentals.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.database.connection import Base, SessionLocal, engine
from app.database.seed_marketplace import seed_marketplace_categories
from app.models.marketplace import MarketplaceCategory, MarketplaceListing
from app.models.notification import Notification
from app.models.user import User
from app.utils.auth import create_access_token, hash_password


client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def database(create_tables):
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM marketplace_rental_requests"))
        session.execute(text("DELETE FROM marketplace_listing_images"))
        session.execute(text("DELETE FROM marketplace_enquiries"))
        session.execute(text("DELETE FROM marketplace_listings"))
        session.execute(text("DELETE FROM notifications"))
        session.execute(text("DELETE FROM users"))
        session.execute(text("DELETE FROM marketplace_categories"))
        seed_marketplace_categories(session)
    finally:
        session.close()
    yield


def make_user(session, suffix, full_name=None):
    u = User(
        farmer_id=f"FA-RENT-{suffix:08d}",
        full_name=full_name or f"Renter {suffix}",
        phone_number=f"91100{suffix:05d}",
        email=f"rental{suffix}@example.test",
        password_hash=hash_password("pass123"),
        is_active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def auth(u):
    return {"Authorization": "Bearer " + create_access_token({"sub": u.id, "phone": u.phone_number})}


def category_id(session, slug="machinery"):
    cat = session.query(MarketplaceCategory).filter(MarketplaceCategory.slug == slug).first()
    return cat.id


RENT_REQUIREMENTS = {
    "rental_period": "day",
    "min_rental_duration": "3 days",
    "available_from": "2026-10-01",
    "available_until": "2026-12-31",
    "security_deposit": 5000,
    "delivery_option": "both",
    "service_area": "Warangal, Telangana",
    "rental_terms": "Operator provided. Deposit refunded on return.",
}


def create_rent_listing(session, owner, title="Tractor on rent"):
    payload = {
        "title": title,
        "category_id": category_id(session),
        "description": "Mahindra 475 DI tractor, well maintained.",
        "quantity": 1,
        "unit": "unit",
        "price": 2500,
        "pricing_type": "fixed",
        "location": "Warangal, Telangana",
        "availability": "Available",
        "listing_type": "rent",
        "condition_type": "used",
        "brand": "Mahindra",
        "model": "475 DI",
        "contact_method": "in-app",
        "status": "active",
        "images": ["http://localhost/uploads/marketplace/tractor.jpg"],
        **RENT_REQUIREMENTS,
    }
    res = client.post("/api/v1/marketplace/listings", headers=auth(owner), json=payload)
    assert res.status_code == 201, res.text
    return res.json()["data"]


def request_period(headers, listing, start="2026-11-10", end="2026-11-12", **overrides):
    payload = {"start_date": start, "end_date": end, "requested_quantity": 1, "message": "Need it for land prep."}
    payload.update(overrides)
    return client.post(
        f"/api/v1/marketplace/rentals/listings/{listing['id']}/requests",
        headers=headers,
        json=payload,
    )


def notifications_for(session, user_id, ref_type="marketplace_rental_request"):
    return (
        session.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.reference_type == ref_type,
        )
        .order_by(Notification.created_at.desc())
        .all()
    )


def test_rental_request_full_flow_with_approval():
    session = SessionLocal()
    try:
        owner = make_user(session, 1)
        renter = make_user(session, 2)
        listing = create_rent_listing(session, owner)

        # The renter sees the listing in the Rent subform source (browse).
        browse = client.get(
            "/api/v1/marketplace/browse/listings?listing_type=rent&group=items",
            headers=auth(renter),
        )
        assert browse.status_code == 200
        assert browse.json()["data"]["total"] == 1
        assert browse.json()["data"]["items"][0]["id"] == listing["id"]
        assert browse.json()["data"]["items"][0]["can_rent"] is True
        assert browse.json()["data"]["items"][0]["is_owner"] is False
        # Owner never sees their own listing in browse.
        assert client.get(
            "/api/v1/marketplace/browse/listings?listing_type=rent&group=items",
            headers=auth(owner),
        ).json()["data"]["total"] == 0

        # Renter sends a request.
        res = request_period(auth(renter), listing)
        assert res.status_code == 201, res.text
        data = res.json()["data"]
        assert data["request_id"].startswith("FA-REQ-")
        assert data["status"] == "pending"
        assert data["is_requester"] is True
        assert data["listing"]["id"] == listing["id"]
        assert data["requester"]["full_name"] == renter.full_name

        # Owner got notified.
        owner_notes = notifications_for(session, owner.id)
        assert len(owner_notes) == 1
        assert owner_notes[0].action_url == "tools.html#incoming-rental-requests"
        assert owner_notes[0].notification_type == "market"

        # Owner sees it as incoming.
        incoming = client.get("/api/v1/marketplace/rentals/requests/incoming", headers=auth(owner))
        assert incoming.status_code == 200
        inc = incoming.json()["data"]["items"]
        assert len(inc) == 1
        assert inc[0]["status"] == "pending"
        assert inc[0]["is_owner"] is True
        assert inc[0]["requester"]["full_name"] == renter.full_name

        # Badge counts reflect it.
        counts = client.get("/api/v1/marketplace/rentals/requests/counts", headers=auth(owner)).json()["data"]
        assert counts["incoming"] == 1
        renter_counts = client.get("/api/v1/marketplace/rentals/requests/counts", headers=auth(renter)).json()["data"]
        assert renter_counts["outgoing"] == 1

        # Owner approves.
        dec = client.patch(
            f"/api/v1/marketplace/rentals/requests/{data['request_id']}/decision",
            headers=auth(owner),
            json={"decision": "approved"},
        )
        assert dec.status_code == 200, dec.text
        assert dec.json()["data"]["status"] == "approved"

        # Requester got notified.
        renter_notes = notifications_for(session, renter.id)
        assert len(renter_notes) == 1
        assert renter_notes[0].action_url == "tools.html#my-rental-requests"

        # Requester tracks it in "My Rent Requests".
        mine = client.get("/api/v1/marketplace/rentals/requests", headers=auth(renter)).json()["data"]["items"]
        assert mine[0]["status"] == "approved"
    finally:
        session.close()


def test_rental_request_rejection_notifies_requester_with_reason():
    session = SessionLocal()
    try:
        owner = make_user(session, 3)
        renter = make_user(session, 4)
        listing = create_rent_listing(session, owner, title="Tractor 2")

        res = request_period(auth(renter), listing)
        rid = res.json()["data"]["request_id"]

        dec = client.patch(
            f"/api/v1/marketplace/rentals/requests/{rid}/decision",
            headers=auth(owner),
            json={"decision": "rejected", "reason": "Already promised to another farmer"},
        )
        assert dec.status_code == 200, dec.text
        data = dec.json()["data"]
        assert data["status"] == "rejected"
        assert data["decline_reason"] == "Already promised to another farmer"

        notes = notifications_for(session, renter.id)
        assert len(notes) == 1
        assert notes[0].action_url == "tools.html#my-rental-requests"

        mine = client.get("/api/v1/marketplace/rentals/requests", headers=auth(renter)).json()["data"]["items"]
        assert mine[0]["status"] == "rejected"
        assert mine[0]["decline_reason"] == "Already promised to another farmer"
    finally:
        session.close()


def test_only_owner_can_decide():
    session = SessionLocal()
    try:
        owner = make_user(session, 5)
        renter = make_user(session, 6)
        stranger = make_user(session, 7)
        listing = create_rent_listing(session, owner)

        res = request_period(auth(renter), listing)
        rid = res.json()["data"]["request_id"]

        # The renter cannot approve their own request.
        r = client.patch(
            f"/api/v1/marketplace/rentals/requests/{rid}/decision",
            headers=auth(renter),
            json={"decision": "approved"},
        )
        assert r.status_code == 403

        # A stranger cannot decide either.
        r2 = client.patch(
            f"/api/v1/marketplace/rentals/requests/{rid}/decision",
            headers=auth(stranger),
            json={"decision": "rejected"},
        )
        assert r2.status_code == 403

        # Deciding twice is rejected.
        ok = client.patch(
            f"/api/v1/marketplace/rentals/requests/{rid}/decision",
            headers=auth(owner),
            json={"decision": "rejected"},
        )
        assert ok.status_code == 200
        again = client.patch(
            f"/api/v1/marketplace/rentals/requests/{rid}/decision",
            headers=auth(owner),
            json={"decision": "approved"},
        )
        assert again.status_code == 409
    finally:
        session.close()


def test_conflicting_periods_are_blocked():
    session = SessionLocal()
    try:
        owner = make_user(session, 8)
        renter_a = make_user(session, 9)
        renter_b = make_user(session, 10)
        listing = create_rent_listing(session, owner)

        # Renter A books + owner approves a period.
        ra = request_period(auth(renter_a), listing, start="2026-11-10", end="2026-11-15")
        assert ra.status_code == 201, ra.text
        rid = ra.json()["data"]["request_id"]
        assert client.patch(
            f"/api/v1/marketplace/rentals/requests/{rid}/decision",
            headers=auth(owner),
            json={"decision": "approved"},
        ).status_code == 200

        # Renter A cannot request the same period again.
        dup = request_period(auth(renter_a), listing, start="2026-11-12", end="2026-11-14")
        assert dup.status_code == 409

        # Renter B cannot book an overlapping period either.
        clash = request_period(auth(renter_b), listing, start="2026-11-14", end="2026-11-16")
        assert clash.status_code == 409

        # Renter B can still book a different period.
        free = request_period(auth(renter_b), listing, start="2026-12-01", end="2026-12-03")
        assert free.status_code == 201, free.text
    finally:
        session.close()


def test_request_date_and_listing_validation():
    session = SessionLocal()
    try:
        owner = make_user(session, 11)
        renter = make_user(session, 12)
        listing = create_rent_listing(session, owner)
        headers = auth(renter)

        # End before start.
        assert request_period(headers, listing, start="2026-11-15", end="2026-11-10").status_code == 400
        # Malformed dates.
        assert request_period(headers, listing, start="15-11-2026", end="2026-11-20").status_code == 400
        # Outside the listing's availability window.
        assert request_period(headers, listing, start="2025-06-01", end="2025-06-05").status_code == 400
        assert request_period(headers, listing, start="2027-03-01", end="2027-03-05").status_code == 400

        # A farmer cannot rent their own listing.
        self_req = request_period(auth(owner), listing)
        assert self_req.status_code == 400

        # Rent requests are rejected for sell listings.
        sell = client.post(
            "/api/v1/marketplace/listings",
            headers=auth(owner),
            json={
                "title": "Fresh Rice",
                "category_id": category_id(session, "rice"),
                "quantity": 10,
                "unit": "kg",
                "price": 40,
                "listing_type": "sell",
                "status": "active",
            },
        )
        assert sell.status_code == 201
        sell_id = sell.json()["data"]["id"]
        sell_req = request_period(headers, {"id": sell_id})
        assert sell_req.status_code == 400
        assert "not available for rent" in sell_req.json()["detail"]
    finally:
        session.close()


def test_requester_can_cancel_and_owner_is_notified():
    session = SessionLocal()
    try:
        owner = make_user(session, 13)
        renter = make_user(session, 14)
        listing = create_rent_listing(session, owner)

        res = request_period(auth(renter), listing)
        rid = res.json()["data"]["request_id"]

        cancel = client.patch(
            f"/api/v1/marketplace/rentals/requests/{rid}/cancel",
            headers=auth(renter),
        )
        assert cancel.status_code == 200, cancel.text
        assert cancel.json()["data"]["status"] == "cancelled"

        # Owner was notified about the cancellation (after the request-created note).
        notes = notifications_for(session, owner.id)
        assert len(notes) == 2
        assert notes[0].title == "Rental request cancelled"
        assert notes[0].action_url == "tools.html#incoming-rental-requests"

        # Cancelling twice / after completion is blocked.
        again = client.patch(
            f"/api/v1/marketplace/rentals/requests/{rid}/cancel",
            headers=auth(renter),
        )
        assert again.status_code == 409

        # Only the requester can cancel.
        r2 = client.patch(
            f"/api/v1/marketplace/rentals/requests/{res.json()['data']['request_id']}/cancel",
            headers=auth(owner),
        )
        assert r2.status_code == 403
    finally:
        session.close()


def test_categories_endpoint_filters_items_group():
    session = SessionLocal()
    try:
        u = make_user(session, 15)
        res = client.get("/api/v1/marketplace/browse/categories?group=items", headers=auth(u))
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["total"] >= 1
        assert all(c["group"] == "items" for c in data["items"])
    finally:
        session.close()