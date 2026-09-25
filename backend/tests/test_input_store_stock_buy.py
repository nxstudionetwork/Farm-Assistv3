import os
import sys
import itertools

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
    Product,
)
from app.models.listing_cart import ListingCartItem
from app.models.notification import Notification
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction
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


_CAT_SEQ = itertools.count(1)


def make_listing(owner_id, title="Wheat", quantity=10, price=250.0, status="active", is_active=True):
    with SessionLocal() as session:
        slug = f"produce-{owner_id[:8]}-{next(_CAT_SEQ)}"
        cat = MarketplaceCategory(name="Produce", slug=slug, group="produce")
        session.add(cat)
        session.commit()
        session.refresh(cat)
        listing = MarketplaceListing(
            listing_id=f"FA-LST-{owner_id[:8]}-{next(_CAT_SEQ)}",
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


# ───────────────────────────── listing cart ─────────────────────────────


def make_wallet(owner_id, balance=50000.0, pin="1234"):
    with SessionLocal() as session:
        user = session.query(User).filter(User.id == owner_id).one()
        w = Wallet(
            wallet_id=f"FA-WLT-{owner_id[:8]}",
            user_id=owner_id,
            farmer_id=user.farmer_id,
            balance=balance,
            wallet_pin_hash=hash_password(pin) if pin else None,
            is_active=True,
            is_setup_complete=bool(pin),
            upi_id="w@farmassist",
        )
        session.add(w)
        session.commit()
    return owner_id


def wallet_balance(owner_id):
    with SessionLocal() as session:
        return round(float(session.query(Wallet).filter(Wallet.user_id == owner_id).one().balance), 2)


def test_add_to_cart_merges_quantity_and_blocks_oversell():
    with SessionLocal() as session:
        seller_id = make_user(session, 30)
        buyer_id = make_user(session, 31)
    listing_id = make_listing(seller_id, quantity=10, price=100.0)

    first = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/cart",
        json={"quantity": 2},
        headers=auth(buyer_id),
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["count"] == 1
    assert first.json()["data"]["total"] == 200.0

    second = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/cart",
        json={"quantity": 3},
        headers=auth(buyer_id),
    )
    assert second.status_code == 200
    # same listing merges into one row rather than duplicating
    assert second.json()["data"]["count"] == 1
    assert second.json()["data"]["items"][0]["quantity"] == 5

    over = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/cart",
        json={"quantity": 6},
        headers=auth(buyer_id),
    )
    assert over.status_code == 409
    assert "available" in over.json()["detail"].lower()


def test_cannot_add_own_listing_to_cart():
    with SessionLocal() as session:
        owner_id = make_user(session, 32)
    listing_id = make_listing(owner_id)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/cart",
        json={"quantity": 1},
        headers=auth(owner_id),
    )
    assert res.status_code == 400
    assert "own listing" in res.json()["detail"].lower()


def test_cart_is_private_to_its_owner():
    with SessionLocal() as session:
        seller_id = make_user(session, 33)
        buyer_id = make_user(session, 34)
        other_id = make_user(session, 35)
    listing_id = make_listing(seller_id)

    client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/cart",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )

    mine = client.get("/api/v1/marketplace/browse/cart", headers=auth(buyer_id))
    assert mine.json()["data"]["count"] == 1

    theirs = client.get("/api/v1/marketplace/browse/cart", headers=auth(other_id))
    assert theirs.json()["data"]["count"] == 0
    assert theirs.json()["data"]["items"] == []


def test_update_and_remove_cart_item():
    with SessionLocal() as session:
        seller_id = make_user(session, 36)
        buyer_id = make_user(session, 37)
    listing_id = make_listing(seller_id, quantity=8, price=50.0)

    added = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/cart",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )
    item_id = added.json()["data"]["items"][0]["id"]

    updated = client.patch(
        f"/api/v1/marketplace/browse/cart/{item_id}",
        json={"quantity": 4},
        headers=auth(buyer_id),
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["items"][0]["quantity"] == 4
    assert updated.json()["data"]["total"] == 200.0

    over = client.patch(
        f"/api/v1/marketplace/browse/cart/{item_id}",
        json={"quantity": 99},
        headers=auth(buyer_id),
    )
    assert over.status_code == 409

    removed = client.delete(f"/api/v1/marketplace/browse/cart/{item_id}", headers=auth(buyer_id))
    assert removed.status_code == 200
    assert removed.json()["data"]["count"] == 0

    missing = client.delete(f"/api/v1/marketplace/browse/cart/{item_id}", headers=auth(buyer_id))
    assert missing.status_code == 404


def test_cart_item_of_another_user_cannot_be_touched():
    with SessionLocal() as session:
        seller_id = make_user(session, 38)
        buyer_id = make_user(session, 39)
        attacker_id = make_user(session, 40)
    listing_id = make_listing(seller_id)

    added = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/cart",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )
    item_id = added.json()["data"]["items"][0]["id"]

    stolen = client.delete(f"/api/v1/marketplace/browse/cart/{item_id}", headers=auth(attacker_id))
    assert stolen.status_code == 404
    # still present for the real owner
    assert client.get("/api/v1/marketplace/browse/cart", headers=auth(buyer_id)).json()["data"]["count"] == 1


def test_checkout_routes_each_item_to_its_own_seller_and_notifies():
    with SessionLocal() as session:
        seller_a = make_user(session, 41)
        seller_b = make_user(session, 42)
        buyer_id = make_user(session, 43)
    listing_a = make_listing(seller_a, title="Wheat", quantity=10, price=100.0)
    listing_b = make_listing(seller_b, title="Rice", quantity=10, price=250.0)

    for lid in (listing_a, listing_b):
        assert client.post(
            f"/api/v1/marketplace/browse/listings/{lid}/cart",
            json={"quantity": 2},
            headers=auth(buyer_id),
        ).status_code == 200

    res = client.post(
        "/api/v1/marketplace/browse/cart/checkout",
        json={"payment_method": "cod", "delivery_address": "Village 9"},
        headers=auth(buyer_id),
    )
    assert res.status_code == 201, res.text
    data = res.json()["data"]
    assert data["count"] == 2
    assert data["total"] == 700.0

    # each seller is told about only their own listing
    a_titles = [t for t, _ in notifications_for(seller_a)]
    b_titles = [t for t, _ in notifications_for(seller_b)]
    assert a_titles == ["New order received"]
    assert b_titles == ["New order received"]
    assert "Wheat" in notifications_for(seller_a)[0][1]
    assert "Rice" in notifications_for(seller_b)[0][1]

    # stock reduced on both listings and the cart is emptied
    assert sold_quantity(listing_a) == 2
    assert sold_quantity(listing_b) == 2
    assert client.get("/api/v1/marketplace/browse/cart", headers=auth(buyer_id)).json()["data"]["count"] == 0


def test_checkout_empty_cart_is_rejected():
    with SessionLocal() as session:
        buyer_id = make_user(session, 44)
    res = client.post(
        "/api/v1/marketplace/browse/cart/checkout",
        json={"payment_method": "cod"},
        headers=auth(buyer_id),
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_checkout_is_idempotent_on_double_submit():
    with SessionLocal() as session:
        seller_id = make_user(session, 45)
        buyer_id = make_user(session, 46)
    listing_id = make_listing(seller_id, quantity=10, price=100.0)

    client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/cart",
        json={"quantity": 2},
        headers=auth(buyer_id),
    )

    body = {"payment_method": "cod", "idempotency_key": "cart-key-1"}
    first = client.post("/api/v1/marketplace/browse/cart/checkout", json=body, headers=auth(buyer_id))
    assert first.status_code == 201

    # replay after re-adding the same item must not create a second order
    client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/cart",
        json={"quantity": 2},
        headers=auth(buyer_id),
    )
    second = client.post("/api/v1/marketplace/browse/cart/checkout", json=body, headers=auth(buyer_id))
    assert second.status_code == 200
    assert second.json()["data"]["count"] == 1
    assert sold_quantity(listing_id) == 2

    with SessionLocal() as session:
        assert session.query(MarketplaceSale).filter(MarketplaceSale.listing_id == listing_id).count() == 1


def test_checkout_fails_atomically_when_one_item_is_unavailable():
    with SessionLocal() as session:
        seller_a = make_user(session, 47)
        seller_b = make_user(session, 48)
        buyer_id = make_user(session, 49)
    listing_a = make_listing(seller_a, title="Wheat", quantity=10, price=100.0)
    listing_b = make_listing(seller_b, title="Rice", quantity=1, price=100.0)

    for lid, qty in ((listing_a, 2), (listing_b, 5)):
        # add more than listing_b can honour, bypassing the cart guard
        assert client.post(
            f"/api/v1/marketplace/browse/listings/{lid}/cart",
            json={"quantity": 1},
            headers=auth(buyer_id),
        ).status_code == 200

    with SessionLocal() as session:
        item = (
            session.query(ListingCartItem)
            .filter(ListingCartItem.listing_id == listing_b)
            .first()
        )
        item.quantity = 5
        session.commit()

    res = client.post(
        "/api/v1/marketplace/browse/cart/checkout",
        json={"payment_method": "cod"},
        headers=auth(buyer_id),
    )
    assert res.status_code == 409
    # nothing was written for the good listing either
    assert sold_quantity(listing_a) == 0
    assert sold_quantity(listing_b) == 0


# ─────────────────────────────── wallet ───────────────────────────────


def test_buy_now_with_wallet_debits_balance():
    with SessionLocal() as session:
        seller_id = make_user(session, 50)
        buyer_id = make_user(session, 51)
    make_wallet(buyer_id, balance=5000.0, pin="1234")
    listing_id = make_listing(seller_id, quantity=10, price=250.0)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 2, "payment_method": "wallet", "wallet_pin": "1234"},
        headers=auth(buyer_id),
    )
    assert res.status_code == 201, res.text
    assert res.json()["data"]["payment_status"] == "paid"
    assert wallet_balance(buyer_id) == 4500.0

    with SessionLocal() as session:
        txns = session.query(WalletTransaction).filter(WalletTransaction.user_id == buyer_id).all()
        assert len(txns) == 1
        assert txns[0].transaction_type == "debit"
        assert round(float(txns[0].amount), 2) == 500.0
        assert round(float(txns[0].balance_after), 2) == 4500.0


def test_buy_now_wallet_rejects_bad_pin_and_insufficient_balance():
    with SessionLocal() as session:
        seller_id = make_user(session, 52)
        buyer_id = make_user(session, 53)
    # balance deliberately below the Rs 500 order total
    make_wallet(buyer_id, balance=100.0, pin="1234")
    listing_id = make_listing(seller_id, quantity=10, price=250.0)

    bad_pin = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1, "payment_method": "wallet", "wallet_pin": "9999"},
        headers=auth(buyer_id),
    )
    assert bad_pin.status_code == 401
    assert wallet_balance(buyer_id) == 100.0
    assert sold_quantity(listing_id) == 0

    poor = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 2, "payment_method": "wallet", "wallet_pin": "1234"},
        headers=auth(buyer_id),
    )
    assert poor.status_code == 400
    assert "insufficient" in poor.json()["detail"].lower()
    assert wallet_balance(buyer_id) == 100.0
    assert sold_quantity(listing_id) == 0

    # no wallet at all is rejected rather than silently falling back to COD
    with SessionLocal() as session:
        no_wallet_id = make_user(session, 58)
    no_wallet_listing = make_listing(seller_id, title="Maize", quantity=5, price=10.0)
    res = client.post(
        f"/api/v1/marketplace/browse/listings/{no_wallet_listing}/purchase",
        json={"quantity": 1, "payment_method": "wallet", "wallet_pin": "1234"},
        headers=auth(no_wallet_id),
    )
    assert res.status_code == 404
    assert sold_quantity(no_wallet_listing) == 0


def test_cancelling_a_wallet_order_refunds_the_buyer():
    with SessionLocal() as session:
        seller_id = make_user(session, 54)
        buyer_id = make_user(session, 55)
    make_wallet(buyer_id, balance=5000.0, pin="1234")
    listing_id = make_listing(seller_id, quantity=10, price=250.0)

    created = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 2, "payment_method": "wallet", "wallet_pin": "1234"},
        headers=auth(buyer_id),
    )
    sale_id = created.json()["data"]["sale_id"]
    assert wallet_balance(buyer_id) == 4500.0

    cancelled = client.post(
        f"/api/v1/marketplace/browse/purchases/{sale_id}/cancel",
        headers=auth(buyer_id),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["payment_status"] == "refunded"
    assert wallet_balance(buyer_id) == 5000.0
    assert sold_quantity(listing_id) == 0

    with SessionLocal() as session:
        kinds = [
            t.transaction_type
            for t in session.query(WalletTransaction).filter(WalletTransaction.user_id == buyer_id).all()
        ]
        assert kinds == ["debit", "credit"]


def test_cod_cancellation_does_not_touch_the_wallet():
    with SessionLocal() as session:
        seller_id = make_user(session, 56)
        buyer_id = make_user(session, 57)
    make_wallet(buyer_id, balance=5000.0, pin="1234")
    listing_id = make_listing(seller_id, quantity=10, price=250.0)

    created = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1, "payment_method": "cod"},
        headers=auth(buyer_id),
    )
    client.post(
        f"/api/v1/marketplace/browse/purchases/{created.json()['data']['sale_id']}/cancel",
        headers=auth(buyer_id),
    )
    assert wallet_balance(buyer_id) == 5000.0


# ────────────────────── appears on the shared Orders page ──────────────────────


def test_stock_purchase_shows_up_in_orders_and_purchases():
    with SessionLocal() as session:
        seller_id = make_user(session, 60)
        buyer_id = make_user(session, 61)
    listing_id = make_listing(seller_id, title="Wheat", quantity=10, price=250.0)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 2, "payment_method": "cod"},
        headers=auth(buyer_id),
    )
    sale_id = res.json()["data"]["sale_id"]

    orders = client.get("/api/v1/orders", headers=auth(buyer_id)).json()["data"]
    assert orders["total"] == 1
    row = orders["items"][0]
    assert row["order_id"] == sale_id
    assert row["order_type"] == "listing"
    assert row["status"] == "placed"
    assert row["status_label"] == "Placed"
    assert round(float(row["total_amount"]), 2) == 500.0
    assert row["summary"]["product_name"] == "Wheat"
    assert row["can_cancel"] is True

    # seller does not see the buyer's order on their own orders page
    assert client.get("/api/v1/orders", headers=auth(seller_id)).json()["data"]["total"] == 0


def test_orders_status_filter_and_progression_for_stock_purchase():
    with SessionLocal() as session:
        seller_id = make_user(session, 62)
        buyer_id = make_user(session, 63)
    listing_id = make_listing(seller_id, quantity=10, price=100.0)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )
    sale_id = res.json()["data"]["sale_id"]

    placed = client.get("/api/v1/orders?status=placed", headers=auth(buyer_id)).json()["data"]
    assert placed["total"] == 1

    shipped = client.get("/api/v1/orders?status=shipped", headers=auth(buyer_id)).json()["data"]
    assert shipped["total"] == 0

    client.post(
        f"/api/v1/marketplace/browse/sales/{sale_id}/status?status=dispatched",
        headers=auth(seller_id),
    )
    moved = client.get("/api/v1/orders?status=out_for_delivery", headers=auth(buyer_id)).json()["data"]
    assert moved["total"] == 1
    assert moved["items"][0]["status"] == "out_for_delivery"


def test_cancelled_stock_purchase_moves_to_cancelled_in_orders():
    with SessionLocal() as session:
        seller_id = make_user(session, 64)
        buyer_id = make_user(session, 65)
    listing_id = make_listing(seller_id, quantity=10, price=100.0)

    res = client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )
    client.post(
        f"/api/v1/marketplace/browse/purchases/{res.json()['data']['sale_id']}/cancel",
        headers=auth(buyer_id),
    )

    cancelled = client.get("/api/v1/orders?status=cancelled", headers=auth(buyer_id)).json()["data"]
    assert cancelled["total"] == 1
    assert cancelled["items"][0]["can_cancel"] is False


def test_orders_merge_keeps_product_orders_intact():
    """A buyer with both kinds of order sees both, newest first."""
    with SessionLocal() as session:
        seller_id = make_user(session, 66)
        buyer_id = make_user(session, 67)
    listing_id = make_listing(seller_id, title="Wheat", quantity=10, price=250.0)

    # a real product order via the existing flow
    with SessionLocal() as session:
        buyer = session.query(User).filter(User.id == buyer_id).one()
        cat = MarketplaceCategory(name="Seeds", slug=f"seeds-{buyer_id[:8]}", group="seeds")
        session.add(cat)
        session.commit()
        session.refresh(cat)
        product = Product(
            product_id=f"FA-PRD-{buyer_id[:8]}",
            name="Hybrid Paddy Seed",
            category_id=cat.id,
            price=500.0,
            stock_quantity=50,
            unit="kg",
            is_active=True,
        )
        session.add(product)
        session.commit()
        session.refresh(product)
        product_id = product.id

    placed = client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": product_id, "quantity": 1}],
            "payment_method": "cod",
            "delivery_name": "Buyer",
            "delivery_phone": "9000000000",
            "delivery_address": "Village 3",
        },
        headers=auth(buyer_id),
    )
    assert placed.status_code == 201, placed.text

    client.post(
        f"/api/v1/marketplace/browse/listings/{listing_id}/purchase",
        json={"quantity": 1},
        headers=auth(buyer_id),
    )

    orders = client.get("/api/v1/orders", headers=auth(buyer_id)).json()["data"]
    assert orders["total"] == 2
    kinds = {row["order_type"] for row in orders["items"]}
    assert kinds == {"product", "listing"}
    # every row keeps the shape my-orders.html already renders
    for row in orders["items"]:
        assert row["order_id"]
        assert row["status_label"]
        assert row["total_amount"] is not None
        assert "summary" in row
