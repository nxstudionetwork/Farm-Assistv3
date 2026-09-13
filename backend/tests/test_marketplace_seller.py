import os
import sys

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_marketplace_seller.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import Base, SessionLocal, engine
from app.database.seed_marketplace import seed_marketplace_categories
from app.models.marketplace import MarketplaceCategory, MarketplaceEnquiry
from app.models.user import User, FarmerProfile
from app.utils.auth import create_access_token, hash_password


client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        session.query(MarketplaceCategory).delete()
        seed_marketplace_categories(session)
    finally:
        session.close()
    yield
    Base.metadata.drop_all(bind=engine)


def make_user(session, suffix, full_name=None):
    u = User(
        farmer_id=f"FA-SELL-{suffix:08d}",
        full_name=full_name or f"Seller {suffix}",
        phone_number=f"91000{suffix:05d}",
        email=f"seller{suffix}@example.test",
        password_hash=hash_password("pass123"),
        is_active=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def auth(u):
    return {"Authorization": "Bearer " + create_access_token({"sub": u.id, "phone": u.phone_number})}


def category_id(session, slug="rice"):
    cat = session.query(MarketplaceCategory).filter(MarketplaceCategory.slug == slug).first()
    return cat.id


def create_listing(session, user_owner, title="Fresh Rice 20kg", **overrides):
    payload = {
        "title": title,
        "category_id": category_id(session),
        "description": "Organically grown paddy, freshly harvested.",
        "quantity": 100,
        "unit": "kg",
        "price": 42,
        "pricing_type": "fixed",
        "location": "Warangal, Telangana",
        "availability": "Ready now",
        "harvest_date": "2026-09-01",
        "quality_grade": "Grade A",
        "contact_method": "in-app",
        "status": "active",
        "images": ["http://localhost/uploads/marketplace/img1.jpg", "http://localhost/uploads/marketplace/img2.jpg"],
    }
    payload.update(overrides)
    res = client.post("/api/v1/marketplace/listings", headers=auth(user_owner), json=payload)
    assert res.status_code == 201, res.text
    return res.json()["data"]


def test_categories_seeded_and_grouped():
    res = client.get("/api/v1/marketplace/categories", headers=auth(make_user(SessionLocal(), 1)))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total"] == 16
    assert len(data["produce"]) == 8
    assert len(data["items"]) == 8


def test_create_search_status_and_ownership_scoping():
    session = SessionLocal()
    try:
        owner = make_user(session, 2)
        other = make_user(session, 3)

        planted = create_listing(session, owner)
        assert planted["listing_id"].startswith("FA-LST-")
        assert len(planted["images"]) == 2
        assert planted["remaining_quantity"] == 100

        create_listing(session, owner, title="Used Tractor", category_id=category_id(session, "machinery"),
                       quantity=1, unit="unit", price=850000, condition_type="used", brand="Mahindra", model="Bhoomiputra")

        mine = client.get("/api/v1/marketplace/listings", headers=auth(owner))
        assert mine.status_code == 200
        assert mine.json()["data"]["total"] == 2

        scoped = client.get("/api/v1/marketplace/listings", headers=auth(other))
        assert scoped.json()["data"]["total"] == 0

        searched = client.get("/api/v1/marketplace/listings?search=tractor", headers=auth(owner))
        assert searched.json()["data"]["total"] == 1
        assert searched.json()["data"]["items"][0]["title"] == "Used Tractor"

        by_status = client.get("/api/v1/marketplace/listings?status=active", headers=auth(owner))
        assert by_status.json()["data"]["total"] == 2

        filtered = client.get("/api/v1/marketplace/listings?group=produce", headers=auth(owner))
        assert filtered.json()["data"]["total"] == 1
    finally:
        session.close()


def test_update_and_status_transitions():
    session = SessionLocal()
    try:
        owner = make_user(session, 4)
        listing = create_listing(session, owner)

        updated = client.put(
            f"/api/v1/marketplace/listings/{listing['id']}",
            headers=auth(owner),
            json={"price": 45, "title": "Fresh premium rice", "status": "paused"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["price"] == 45
        assert updated.json()["data"]["status"] == "paused"

        paused = client.patch(
            f"/api/v1/marketplace/listings/{listing['id']}/status",
            headers=auth(owner),
            json={"status": "active"},
        )
        assert paused.json()["data"]["status"] == "active"

        sold = client.patch(
            f"/api/v1/marketplace/listings/{listing['id']}/status",
            headers=auth(owner),
            json={"status": "sold"},
        )
        assert sold.json()["data"]["status"] == "sold"
        assert sold.json()["data"]["sold_quantity"] == 100

        cannot_reactivate = client.patch(
            f"/api/v1/marketplace/listings/{listing['id']}/status",
            headers=auth(owner),
            json={"status": "active"},
        )
        assert cannot_reactivate.status_code == 400

        stranger = make_user(session, 5)
        forbidden = client.patch(
            f"/api/v1/marketplace/listings/{listing['id']}/status",
            headers=auth(stranger),
            json={"status": "paused"},
        )
        assert forbidden.status_code == 404
    finally:
        session.close()


def test_record_sale_updates_listing_stock_and_dashboard():
    session = SessionLocal()
    try:
        owner = make_user(session, 6)

        res = client.post("/api/v1/marketplace/listings", headers=auth(owner), json={
            "title": "Rice for sale",
            "category_id": category_id(session),
            "quantity": 100,
            "unit": "kg",
            "price": 40,
            "images": [],
        })
        listing = res.json()["data"]

        partial = client.post(f"/api/v1/marketplace/listings/{listing['id']}/sales", headers=auth(owner), json={
            "buyer_name": "Bharath Mill",
            "buyer_phone": "9800012345",
            "quantity": 40,
            "unit_price": 42,
            "payment_status": "partial",
            "status": "confirmed",
        })
        assert partial.status_code == 201
        sale = partial.json()["data"]
        assert sale["sale_id"].startswith("FA-SAL-")
        assert sale["total_amount"] == 1680.0
        assert sale["status"] == "confirmed"

        after = client.get(f"/api/v1/marketplace/listings/{listing['id']}", headers=auth(owner)).json()["data"]
        assert after["remaining_quantity"] == 60

        completed = client.patch(f"/api/v1/marketplace/sales/{sale['id']}", headers=auth(owner), json={
            "status": "completed", "payment_status": "paid",
        })
        assert completed.json()["data"]["status"] == "completed"
        assert completed.json()["data"]["payment_status"] == "paid"

        after_complete = client.get(f"/api/v1/marketplace/listings/{listing['id']}", headers=auth(owner)).json()["data"]
        assert after_complete["remaining_quantity"] == 60
        assert after_complete["sold_quantity"] == 40

        dash = client.get("/api/v1/marketplace/dashboard", headers=auth(owner)).json()["data"]
        assert dash["active_listings"] == 1
        assert dash["total_sales"]["count"] == 1
        assert dash["total_sales"]["value"] == 1680.0

        insights = client.get("/api/v1/marketplace/insights", headers=auth(owner)).json()["data"]
        assert insights["has_data"] is True
        assert insights["total_quantity_sold"] == 40
        assert insights["total_sales_value"] == 1680.0
    finally:
        session.close()


def test_pending_sale_cannot_exceed_stock_and_insufficient_qty_rejected():
    session = SessionLocal()
    try:
        owner = make_user(session, 7)
        listing = create_listing(session, owner, quantity=10, unit="kg", price=50)

        too_many = client.post(f"/api/v1/marketplace/listings/{listing['id']}/sales", headers=auth(owner), json={
            "buyer_name": "Over Buyer", "quantity": 99, "status": "pending",
        })
        assert too_many.status_code == 400

        stranger = make_user(session, 8)
        hidden = client.get(f"/api/v1/marketplace/sales", headers=auth(stranger))
        assert hidden.json()["data"]["total"] == 0

        no_sale = client.post(f"/api/v1/marketplace/listings/{listing['id']}/sales", headers=auth(stranger), json={
            "buyer_name": "Not owner", "quantity": 2,
        })
        assert no_sale.status_code == 404
    finally:
        session.close()


def test_delete_soft_cancels_listing_with_history():
    session = SessionLocal()
    try:
        owner = make_user(session, 9)
        listing = create_listing(session, owner)
        client.post(f"/api/v1/marketplace/listings/{listing['id']}/sales", headers=auth(owner), json={
            "buyer_name": "Keep History", "quantity": 5, "status": "completed",
        })

        deleted = client.delete(f"/api/v1/marketplace/listings/{listing['id']}", headers=auth(owner))
        assert deleted.status_code == 200
        assert deleted.json()["data"]["soft_deleted"] is True

        gone = client.get(f"/api/v1/marketplace/listings/{listing['id']}", headers=auth(owner))
        assert gone.status_code == 404

        # Default list hides soft-deleted listings; sales history is preserved.
        default = client.get("/api/v1/marketplace/listings", headers=auth(owner)).json()["data"]
        assert default["total"] == 0
        sales_history = client.get("/api/v1/marketplace/sales", headers=auth(owner)).json()["data"]
        assert sales_history["total"] == 1
    finally:
        session.close()


def test_hard_delete_without_sales():
    session = SessionLocal()
    try:
        owner = make_user(session, 10)
        listing = create_listing(session, owner)

        deleted = client.delete(f"/api/v1/marketplace/listings/{listing['id']}", headers=auth(owner))
        assert deleted.status_code == 200
        assert deleted.json()["data"]["soft_deleted"] is False

        zero = client.get("/api/v1/marketplace/listings", headers=auth(owner)).json()["data"]
        assert zero["total"] == 0
    finally:
        session.close()


def test_buyers_strip_matches_enquiry_senders_and_crop_preferences():
    session = SessionLocal()
    try:
        owner = make_user(session, 20)
        listing = create_listing(session, owner)

        enquirer = make_user(session, 21, full_name="Enquirer Buyer")
        session.add(MarketplaceEnquiry(
            listing_id=listing["id"],
            buyer_user_id=enquirer.id,
            buyer_phone="9900011221",
            buyer_name="Enquirer Buyer",
            message="I want to buy rice",
            status="new",
        ))

        pref_user = make_user(session, 22, full_name="Pref Buyer")
        session.add(FarmerProfile(
            user_id=pref_user.id,
            farmer_id=f"FA-PRF-{22:08d}",
            preferred_crops="rice, paddy",
        ))
        session.commit()

        res = client.get("/api/v1/marketplace/buyers", headers=auth(owner))
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["total"] == 2

        by_id = {it["id"]: it for it in data["items"]}
        assert enquirer.id in by_id and pref_user.id in by_id

        enq = by_id[enquirer.id]
        assert enq["enquiries_count"] == 1
        assert enq["phone_number"] == "9900011221"
        assert enq["matched_listings"]["count"] == 1
        assert enq["location"] is None or isinstance(enq["location"], str)

        pref = by_id[pref_user.id]
        assert pref["matched_listings"]["count"] == 1
        assert any("Rice" in p or "rice" in p for p in pref["preferences"])

        stranger = make_user(session, 23)
        hidden = client.get("/api/v1/marketplace/buyers", headers=auth(stranger))
        assert hidden.json()["data"]["total"] == 0
    finally:
        session.close()


def test_buyer_recommend_toggle_and_direct_message():
    session = SessionLocal()
    try:
        owner = make_user(session, 30)
        listing = create_listing(session, owner)
        buyer = make_user(session, 31, full_name="Recommendable Buyer")
        session.add(MarketplaceEnquiry(
            listing_id=listing["id"],
            buyer_user_id=buyer.id,
            buyer_phone="9900011888",
            buyer_name="Recommendable Buyer",
            message="Hi, rice available?",
            status="new",
        ))
        session.commit()

        rec = client.post(f"/api/v1/marketplace/buyers/{buyer.id}/recommend", headers=auth(owner), json={"recommended": True})
        assert rec.status_code == 200
        rid = rec.json()["data"]["recommendation_id"]
        assert rid.startswith("FA-BRC-")

        res = client.get("/api/v1/marketplace/buyers", headers=auth(owner)).json()["data"]
        assert res["total"] == 1
        assert res["items"][0]["is_recommended"] is True
        assert res["items"][0]["recommendation_id"] == rid

        again = client.post(f"/api/v1/marketplace/buyers/{buyer.id}/recommend", headers=auth(owner), json={"recommended": True})
        assert again.json()["data"]["recommendation_id"] == rid

        off = client.post(f"/api/v1/marketplace/buyers/{buyer.id}/recommend", headers=auth(owner), json={"recommended": False})
        assert off.json()["data"]["recommended"] is False
        after = client.get("/api/v1/marketplace/buyers", headers=auth(owner)).json()["data"]
        assert after["items"][0]["is_recommended"] is False

        msg = client.post(f"/api/v1/marketplace/buyers/{buyer.id}/message", headers=auth(owner), json={"message": "Hello! Fresh rice available."})
        assert msg.status_code == 201, msg.text
        md = msg.json()["data"]
        assert md["message_id"].startswith("FA-MSG-")
        assert md["conversation_public_id"].startswith("FA-CNV-")

        convo = client.get(f"/api/v1/messages/conversations/{md['conversation_public_id']}/messages", headers=auth(owner))
        assert convo.status_code == 200
        assert any(m["message_id"] == md["message_id"] for m in convo.json()["data"]["messages"])

        self_msg = client.post(f"/api/v1/marketplace/buyers/{owner.id}/message", headers=auth(owner), json={"message": "hi"})
        assert self_msg.status_code == 400
    finally:
        session.close()