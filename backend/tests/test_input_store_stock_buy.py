import os
import sys

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_stock_buy.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import Base, SessionLocal, engine
from app.models.marketplace import (
    MarketplaceCategory,
    MarketplaceListing,
    MarketplaceSale,
)
from app.models.notification import Notification
from app.models.user import User
from app.utils.auth import create_access_token, hash_password


client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def make_user(session, suffix):
    value = User(
        farmer_id=f"FA-SB-{suffix:08d}",
        full_name=f"Stock Farmer {suffix}",
        phone_number=f"92000{suffix:05d}",
        email=f"stock{suffix}@example.test",
        password_hash=hash_password("pass123"),
        is_active=True,
    )
    session.add(value)
    session.commit()
    session.refresh(value)
    return value.id


def auth(user_id):
    return {"Authorization": "Bearer " + create_access_token({"sub": user_id})}


def make_listing(owner_id, title="Wheat", quantity=10, price=250.0, status="active", is_active=True):
    with SessionLocal() as session:
        cat = MarketplaceCategory(name="Produce", slug=f"produce-{owner_id[:8]}", group="produce")
        session.add(cat)
        session.commit()
        session.refresh(cat)
        listing = MarketplaceListing(
            listing_id=f"FA-LST-{owner_id[:8]}",
            user_id=owner_id,
            category_id=cat.id,
            listing_type="sell",
            title=title,
            description="Fresh produce",
            quantity=quantity,
            unit="kg",
            price=price,
            status=status,
            sold_quantity=0,
            is_active=is_active,
            is_deleted=False,
        )
        session.add(listing)
        session.commit()
        session.refresh(listing)
        return listing.id


def notifications_for(user_id):
    with SessionLocal() as session:
        return [
            (n.title, n.message)
            for n in session.query(Notification).filter(Notification.user_id == user_id).all()
        ]


def sold_quantity(listing_id):
    with SessionLocal() as session:
        return session.query(MarketplaceListing).filter(MarketplaceListing.id == listing_id).one().sold_quantity


def test_buy_now_creates_sale_notifies_seller_and_buyer():
    with SessionLocal() as session:
        seller_id = make_user(session, 1)
        buyer_id = make_user(session, 2)
    listing_id = make_listing(seller_id)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 2, "payment_method": "cod", "delivery_address": "Village 1"},
        headers=auth(buyer_id),
    )
    assert res.status_code == 201, res.text
    data = res.json()["data"]
    assert data["quantity"] == 2
    assert data["total_amount"] == 500.0
    assert data["status"] == "pending"
    assert sold_quantity(listing_id) == 2

    seller_notes = notifications_for(seller_id)
    buyer_notes = notifications_for(buyer_id)
    assert any(t == "New order received" for t, _ in seller_notes)
    assert any(t == "Order placed successfully" for t, _ in buyer_notes)

    seller_msg = [m for t, m in seller_notes if t == "New order received"][0]
    assert "Wheat" in seller_msg
    assert "2 kg" in seller_msg
    assert data["sale_id"] in seller_msg
    assert "pending" in seller_msg.lower()


def test_buyer_cannot_buy_own_listing():
    with SessionLocal() as session:
        owner_id = make_user(session, 3)
    listing_id = make_listing(owner_id)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1},
        headers=auth(owner_id),
    )
    assert res.status_code == 400
    assert "own listing" in res.json()["detail"].lower()


def test_purchase_requires_authentication():
    with SessionLocal() as session:
        seller_id = make_user(session, 4)
    listing_id = make_listing(seller_id)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1},
    )
    assert res.status_code in (401, 403)


def test_oversell_is_rejected_server_side():
    with SessionLocal() as session:
        seller_id = make_user(session, 5)
        buyer_id = make_user(session, 6)
    listing_id = make_listing(seller_id, quantity=3)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 5},
        headers=auth(buyer_id),
    )
    assert res.status_code == 409
    assert "available" in res.json()["detail"].lower()
    assert sold_quantity(listing_id) == 0


def test_duplicate_click_creates_only_one_order():
    with SessionLocal() as session:
        seller_id = make_user(session, 7)
        buyer_id = make_user(session, 8)
    listing_id = make_listing(seller_id, quantity=10)

    payload = {"quantity": 1, "payment_method": "cod", "idempotency_key": "same-click-key"}
    first = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json=payload,
        headers=auth(buyer_id),
    )
    second = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json=payload,
        headers=auth(buyer_id),
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["data"]["sale_id"] == second.json()["data"]["sale_id"]
    assert sold_quantity(listing_id) == 1

    with SessionLocal() as session:
        count = session.query(MarketplaceSale).filter(MarketplaceSale.listing_id == listing_id).count()
    assert count == 1


def test_inactive_listing_cannot_be_bought():
    with SessionLocal() as session:
        seller_id = make_user(session, 9)
        buyer_id = make_user(session, 10)
    listing_id = make_listing(seller_id, status="paused", is_active=False)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )
    assert res.status_code == 400
    assert "no longer available" in res.json()["detail"].lower()


def test_purchases_only_visible_to_the_buyer():
    with SessionLocal() as session:
        seller_id = make_user(session, 11)
        buyer_id = make_user(session, 12)
        other_id = make_user(session, 13)
    listing_id = make_listing(seller_id)

    client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )

    mine = client.get("/api/v1/marketplace/browse/purchases", headers=auth(buyer_id))
    assert mine.status_code == 200
    assert len(mine.json()["data"]) == 1

    theirs = client.get("/api/v1/marketplace/browse/purchases", headers=auth(other_id))
    assert theirs.status_code == 200
    assert theirs.json()["data"] == []


def test_cancel_releases_stock_and_notifies_seller():
    with SessionLocal() as session:
        seller_id = make_user(session, 14)
        buyer_id = make_user(session, 15)
    listing_id = make_listing(seller_id, quantity=5)

    created = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 2},
        headers=auth(buyer_id),
    )
    sale_id = created.json()["data"]["sale_id"]

    cancelled = client.post(
        f"/api/v1/marketplace/browse/purchases/{sale_id}/cancel",
        headers=auth(buyer_id),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"
    assert sold_quantity(listing_id) == 0
    assert any(t == "Order cancelled" for t, _ in notifications_for(seller_id))


def test_seller_status_change_notifies_buyer_and_others_are_rejected():
    with SessionLocal() as session:
        seller_id = make_user(session, 16)
        buyer_id = make_user(session, 17)
        stranger_id = make_user(session, 18)
    listing_id = make_listing(seller_id)

    created = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )
    sale_id = created.json()["data"]["sale_id"]

    denied = client.post(
        f"/api/v1/marketplace/browse/sales/{sale_id}/status?status=confirmed",
        headers=auth(stranger_id),
    )
    assert denied.status_code == 403

    ok = client.post(
        f"/api/v1/marketplace/browse/sales/{sale_id}/status?status=dispatched",
        headers=auth(seller_id),
    )
    assert ok.status_code == 200
    assert any(t == "Order dispatched" for t, _ in notifications_for(buyer_id))


def test_buyer_does_not_receive_seller_notification():
    with SessionLocal() as session:
        seller_id = make_user(session, 19)
        buyer_id = make_user(session, 20)
    listing_id = make_listing(seller_id)

    client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )

    seller_titles = [t for t, _ in notifications_for(seller_id)]
    assert "New order received" in seller_titles
    assert "Order placed successfully" not in seller_titles
