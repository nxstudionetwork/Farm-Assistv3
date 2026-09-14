import os
import sys
from datetime import date

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_input_store.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import Base, SessionLocal, engine
from app.models.marketplace import (
    Product, ProductCategory, ProductCrop, Seller,
    MarketplaceOrder, DeliveryTracking, FarmerRecentlyViewed,
)
from app.models.wallet import Wallet, WalletTransaction
from app.models.user import FarmerProfile, User
from app.utils.auth import create_access_token, hash_password


client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def user(session, suffix, crops="", has_profile=True):
    value = User(
        farmer_id=f"FA-IS-{suffix:08d}",
        full_name=f"Input Farmer {suffix}",
        phone_number=f"91000{suffix:05d}",
        email=f"input{suffix}@example.test",
        password_hash=hash_password("pass123"),
        is_active=True,
    )
    session.add(value)
    session.commit()
    session.refresh(value)
    if has_profile:
        profile = FarmerProfile(user_id=value.id, preferred_crops=crops)
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return value


def headers(value):
    return {"Authorization": "Bearer " + create_access_token({"sub": value.id, "phone": value.phone_number})}


def wallet(session, owner, balance=50000.0, pin="1234"):
    w = Wallet(
        wallet_id=f"FA-WLT-{str(owner.farmer_id)[-6:]}",
        user_id=owner.id,
        farmer_id=owner.farmer_id,
        balance=balance,
        wallet_pin_hash=hash_password(pin) if pin else None,
        is_active=True,
        is_setup_complete=bool(pin),
        upi_id=f"{owner.farmer_id.lower()}@farmassist",
    )
    session.add(w)
    session.commit()
    session.refresh(w)
    return w


def seed_catalogue(session, owner):
    cat = ProductCategory(name="Seeds", slug="seeds", icon="fa-seedling")
    session.add(cat)
    session.commit()
    session.refresh(cat)

    seller = Seller(
        user_id=owner.id,
        shop_name="Test Agri Mart",
        location="Nellore, Andhra Pradesh",
        is_verified=True,
        rating=4.6,
    )
    session.add(seller)
    session.commit()
    session.refresh(seller)

    data = [
        ("Hybrid Paddy Seed", 420, 500, "rice", 25.0, "Seed"),
        ("Wheat Seed HD-3086", 160, 200, "wheat", 0.0, "Seed"),
        ("Organic Neem Oil", 320, 380, "vegetables", 40.0, "Anti-Pest Oil"),
        ("Cotton Seed Bt", 890, 950, "cotton", 12.0, "Seed"),
    ]
    for name, price, mrp, crop, stock, product_type in data:
        product = Product(
            product_id=f"INP-T-{name[:3].upper()}-{price}",
            name=name,
            price=price,
            original_price=mrp,
            unit="kg",
            stock_quantity=stock,
            min_order_quantity=1,
            is_active=True,
            category_id=cat.id,
            seller_id=seller.id,
            brand="TestBrand",
            tags={"organic": "organic" in name.lower(), "product_type": product_type},
        )
        session.add(product)
        session.commit()
        session.refresh(product)
        if crop:
            session.add(ProductCrop(product_id=product.id, crop_name=crop))
    session.commit()

    equipment_cat = ProductCategory(name="Sprayer Pumps", slug="sprayer-pumps", icon="fa-spray-can")
    session.add(equipment_cat)
    session.commit()
    session.refresh(equipment_cat)
    sprayer = Product(
        product_id="INP-T-SPR-999",
        name="Knapsack Sprayer 16L",
        price=1800,
        original_price=2100,
        unit="unit",
        stock_quantity=5,
        min_order_quantity=1,
        is_active=True,
        category_id=equipment_cat.id,
        seller_id=seller.id,
        brand="TestBrand",
        tags={"product_type": "Sprayer"},
    )
    session.add(sprayer)
    session.commit()
    session.refresh(sprayer)
    return sprayer


def test_list_products_pagination_sort_and_filters():
    session = SessionLocal()
    try:
        farmer = user(session, 1)
        seed_catalogue(session, farmer)

        response = client.get("/api/v1/input-store/products", headers=headers(farmer))
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["total"] == 4
        assert len(payload["items"]) == 4
        assert payload["total_pages"] == 1

        filtered = client.get(
            "/api/v1/input-store/products",
            headers=headers(farmer),
            params={"min_price": 300, "max_price": 500, "sort_by": "price", "sort_order": "desc"},
        ).json()["data"]
        assert filtered["total"] == 2
        assert filtered["items"][0]["name"] == "Hybrid Paddy Seed"

        only_stock = client.get(
            "/api/v1/input-store/products", headers=headers(farmer), params={"in_stock": True}
        ).json()["data"]
        assert only_stock["total"] == 3

        searched = client.get(
            "/api/v1/input-store/products", headers=headers(farmer), params={"search": "paddy"}
        ).json()["data"]
        assert searched["total"] == 1
        assert searched["items"][0]["name"] == "Hybrid Paddy Seed"

        multi_search = client.get(
            "/api/v1/input-store/products", headers=headers(farmer), params={"search": "rice seeds"}
        ).json()["data"]
        assert multi_search["total"] == 1
        assert multi_search["items"][0]["name"] == "Hybrid Paddy Seed"

        phrase_search = client.get(
            "/api/v1/input-store/products", headers=headers(farmer), params={"search": "organic neem"}
        ).json()["data"]
        assert phrase_search["total"] == 1
        assert phrase_search["items"][0]["name"] == "Organic Neem Oil"

        crop_alias = client.get(
            "/api/v1/input-store/products", headers=headers(farmer), params={"crop": "rice"}
        ).json()["data"]
        assert crop_alias["total"] == 1
        assert crop_alias["items"][0]["crops"] == ["rice"]

        crop_filter = client.get(
            "/api/v1/input-store/products", headers=headers(farmer), params={"crop": "rice"}
        ).json()["data"]
        assert crop_filter["total"] == 1
        assert crop_filter["items"][0]["crops"] == ["rice"]

        paged = client.get(
            "/api/v1/input-store/products", headers=headers(farmer), params={"limit": 2, "page": 2}
        ).json()["data"]
        assert len(paged["items"]) == 2
        assert paged["page"] == 2
    finally:
        session.close()


def test_categories_and_filters_endpoints():
    session = SessionLocal()
    try:
        farmer = user(session, 2)
        seed_catalogue(session, farmer)

        categories = client.get("/api/v1/input-store/categories", headers=headers(farmer)).json()["data"]["items"]
        assert any(c["slug"] == "seeds" and c["count"] == 4 for c in categories)

        filters = client.get("/api/v1/input-store/filters", headers=headers(farmer)).json()["data"]
        assert "TestBrand" in filters["brands"]
        assert filters["sellers"][0]["shop_name"] == "Test Agri Mart"
        assert "Rice" in filters["crops"]
        assert filters["price_range"]["max"] == 890
    finally:
        session.close()


def test_product_detail_and_404():
    session = SessionLocal()
    try:
        farmer = user(session, 3)
        seed_catalogue(session, farmer)
        listing = client.get("/api/v1/input-store/products", headers=headers(farmer)).json()["data"]["items"]
        item = next(i for i in listing if i["name"] == "Hybrid Paddy Seed")

        detail = client.get(f"/api/v1/input-store/products/{item['id']}", headers=headers(farmer))
        assert detail.status_code == 200
        assert detail.json()["data"]["name"] == "Hybrid Paddy Seed"

        missing = client.get("/api/v1/input-store/products/does-not-exist", headers=headers(farmer))
        assert missing.status_code == 404
    finally:
        session.close()


def test_recommended_uses_farmer_crops():
    session = SessionLocal()
    try:
        paddy_farmer = user(session, 4, crops="Rice, Wheat")
        seed_catalogue(session, paddy_farmer)

        recommended = client.get("/api/v1/input-store/recommended", headers=headers(paddy_farmer)).json()["data"]
        assert recommended["reason"] == "matched"
        names = {item["name"] for item in recommended["items"]}
        assert "Hybrid Paddy Seed" in names or "Wheat Seed HD-3086" in names

        bare_farmer = user(session, 5, crops="", has_profile=False)
        empty = client.get("/api/v1/input-store/recommended", headers=headers(bare_farmer)).json()["data"]
        assert empty["reason"] == "no_crops"
    finally:
        session.close()


def test_product_type_filter():
    session = SessionLocal()
    try:
        farmer = user(session, 6)
        seed_catalogue(session, farmer)

        seeds = client.get(
            "/api/v1/input-store/products", headers=headers(farmer), params={"product_type": "Seed"}
        ).json()["data"]
        assert seeds["total"] == 3

        oil = client.get(
            "/api/v1/input-store/products", headers=headers(farmer), params={"product_type": "Anti-Pest Oil"}
        ).json()["data"]
        assert oil["total"] == 1
        assert oil["items"][0]["name"] == "Organic Neem Oil"
        assert oil["items"][0]["product_type"] == "Anti-Pest Oil"

        filters_data = client.get("/api/v1/input-store/filters", headers=headers(farmer)).json()["data"]
        assert "Seed" in filters_data["product_types"]
        assert "Anti-Pest Oil" in filters_data["product_types"]
    finally:
        session.close()


def test_equipment_is_isolated_from_input_store():
    session = SessionLocal()
    try:
        farmer = user(session, 7)
        sprayer = seed_catalogue(session, farmer)

        listing = client.get("/api/v1/input-store/products", headers=headers(farmer)).json()["data"]
        assert listing["total"] == 4
        assert all("Sprayer" not in p["name"] for p in listing["items"])

        detail = client.get(f"/api/v1/input-store/products/{sprayer.id}", headers=headers(farmer))
        assert detail.status_code == 404

        categories = client.get("/api/v1/input-store/categories", headers=headers(farmer)).json()["data"]["items"]
        assert all(c["slug"] != "sprayer-pumps" for c in categories)
    finally:
        session.close()


def _first_product(session, farmer, name="Hybrid Paddy Seed"):
    listing = client.get("/api/v1/input-store/products", headers=headers(farmer)).json()["data"]["items"]
    return next(i for i in listing if i["name"] == name)


def _extra_product(session, stock=10, price=300, supports_cod=True, name="Trichoderma Bio-Pack", product_id="INP-T-NOCOD-1"):
    cat = ProductCategory(name="Biologicals", slug="biologicals", icon="fa-biohazard")
    session.add(cat)
    session.commit()
    session.refresh(cat)
    p = Product(
        product_id=product_id,
        name=name,
        price=price,
        original_price=price,
        unit="kg",
        stock_quantity=stock,
        min_order_quantity=1,
        is_active=True,
        category_id=cat.id,
        brand="BioAgro",
        supports_cod=supports_cod,
        tags={"product_type": "Bio-Pack"},
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_cod_order_is_placed_not_confirmed():
    session = SessionLocal()
    try:
        farmer = user(session, 20)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)

        resp = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": paddy["product_id"], "quantity": 2}],
            "delivery_address": "Nellore, Andhra Pradesh 524001",
            "payment_method": "cod",
        })
        assert resp.status_code == 201
        d = resp.json()["data"]
        assert d["status"] == "placed"
        assert d["status_label"] == "Placed"
        assert d["payment_status"] == "pending"
        assert d["payment_method"] == "cod"

        # Stock is actually decremented.
        stored = session.query(Product).filter(Product.product_id == paddy["product_id"]).first()
        assert stored.stock_quantity == 23

        listed = client.get("/api/v1/orders", headers=headers(farmer)).json()["data"]["items"]
        assert listed[0]["status"] == "placed"
        assert all(x["status"] != "confirmed" for x in listed)
    finally:
        session.close()


def test_wallet_payment_creates_order_and_debits():
    session = SessionLocal()
    try:
        farmer = user(session, 21)
        wallet(session, farmer, balance=5000.0)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)

        resp = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": paddy["product_id"], "quantity": 2}],
            "delivery_address": "Nellore, Andhra Pradesh 524001",
            "payment_method": "wallet",
            "wallet_pin": "1234",
        })
        assert resp.status_code == 201
        d = resp.json()["data"]
        assert d["payment_status"] == "paid"
        assert d["payment_method"] == "wallet"

        got_wallet = session.query(Wallet).filter(Wallet.user_id == farmer.id).first()
        assert round(got_wallet.balance, 2) == round(5000 - 2 * 420, 2)
        txn = session.query(WalletTransaction).filter(WalletTransaction.user_id == farmer.id).first()
        assert txn.transaction_type == "debit"
        assert txn.payment_method == "wallet_purchase"
        assert txn.reference_id == d["order_id"]
        assert txn.status == "completed"
    finally:
        session.close()


def test_wallet_insufficient_balance_writes_nothing():
    session = SessionLocal()
    try:
        farmer = user(session, 22)
        wallet(session, farmer, balance=100.0)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)

        resp = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": paddy["product_id"], "quantity": 1}],
            "payment_method": "wallet",
            "wallet_pin": "1234",
        })
        assert resp.status_code == 400
        assert "insufficient" in resp.json()["detail"].lower()
        # Nothing persisted: no order, no transaction, stock untouched.
        assert session.query(MarketplaceOrder).count() == 0
        assert session.query(WalletTransaction).filter(WalletTransaction.user_id == farmer.id).count() == 0
        assert session.query(Product).filter(Product.product_id == paddy["product_id"]).first().stock_quantity == 25
    finally:
        session.close()


def test_wallet_payment_rejects_wrong_pin():
    session = SessionLocal()
    try:
        farmer = user(session, 23)
        wallet(session, farmer, balance=5000.0)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)

        resp = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": paddy["product_id"], "quantity": 1}],
            "payment_method": "wallet",
            "wallet_pin": "9999",
        })
        assert resp.status_code == 401
        assert session.query(MarketplaceOrder).count() == 0
    finally:
        session.close()


def test_cod_unavailable_gated_but_wallet_still_works():
    session = SessionLocal()
    try:
        farmer = user(session, 24)
        wallet(session, farmer, balance=5000.0)
        no_cod = _extra_product(session, supports_cod=False)

        cod_resp = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": no_cod.product_id, "quantity": 1}],
            "payment_method": "cod",
        })
        assert cod_resp.status_code == 400
        assert "Cash on Delivery unavailable" in cod_resp.json()["detail"]
        assert session.query(MarketplaceOrder).count() == 0

        wallet_resp = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": no_cod.product_id, "quantity": 1}],
            "payment_method": "wallet",
            "wallet_pin": "1234",
        })
        assert wallet_resp.status_code == 201
        assert wallet_resp.json()["data"]["payment_status"] == "paid"
    finally:
        session.close()


def test_confirm_received_sets_status_and_cod_paid():
    session = SessionLocal()
    try:
        farmer = user(session, 25)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)
        order = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": paddy["product_id"], "quantity": 1}],
            "payment_method": "cod",
        }).json()["data"]

        r = client.post(f"/api/v1/orders/{order['order_id']}/confirm-received", headers=headers(farmer))
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "received"
        assert d["received_at"] is not None
        assert d["payment_status"] == "paid"
        assert d["can_reorder"] is True
        assert d["can_cancel"] is False
        assert d["can_confirm_received"] is False

        events = [t.status for t in session.query(DeliveryTracking).order_by(DeliveryTracking.timestamp).all()]
        assert events == ["placed", "received"]
    finally:
        session.close()


def test_tracking_endpoint_no_fabricated_person():
    session = SessionLocal()
    try:
        farmer = user(session, 26)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)
        order = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": paddy["product_id"], "quantity": 1}],
            "payment_method": "cod",
        }).json()["data"]

        t = client.get(f"/api/v1/orders/{order['order_id']}/tracking", headers=headers(farmer)).json()["data"]
        assert t["current_status"] == "placed"
        assert t["reference_number"] == order["order_id"]
        assert len(t["tracking"]) == 1
        assert t["tracking"][0]["status"] == "placed"
        # No assigned person yet -> explicitly null, never fabricated.
        assert t["person_in_charge"] is None
        assert t["company"] is None
    finally:
        session.close()


def test_reorder_checks_current_stock_and_price():
    session = SessionLocal()
    try:
        farmer = user(session, 27)
        wallet(session, farmer, balance=5000.0)
        seed_catalogue(session, farmer)
        listing = client.get("/api/v1/input-store/products", headers=headers(farmer)).json()["data"]["items"]
        pid = next(i["product_id"] for i in listing if i["name"] == "Hybrid Paddy Seed")

        order = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": pid, "quantity": 2}],
            "payment_method": "wallet",
            "wallet_pin": "1234",
        }).json()["data"]
        client.post(f"/api/v1/orders/{order['order_id']}/confirm-received", headers=headers(farmer))

        rr = client.post(f"/api/v1/orders/{order['order_id']}/reorder", headers=headers(farmer))
        assert rr.status_code == 200
        d = rr.json()["data"]
        assert any(x["product_id"] == pid for x in d["added"])
        assert d["skipped"] == []
        assert d["added"][0]["current_price"] == 420

        cart = client.get("/api/v1/cart", headers=headers(farmer)).json()["data"]
        assert cart["total"] == 2 * 420

        # Force the product out of stock; reorder must now skip it.
        stored = session.query(Product).filter(Product.product_id == pid).first()
        stored.stock_quantity = 0
        session.commit()
        rr2 = client.post(f"/api/v1/orders/{order['order_id']}/reorder", headers=headers(farmer))
        d2 = rr2.json()["data"]
        assert d2["added"] == []
        assert d2["skipped"] and d2["skipped"][0]["reason"] == "Out of stock"
    finally:
        session.close()


def test_cart_exposes_cod_availability():
    session = SessionLocal()
    try:
        farmer = user(session, 28)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)
        no_cod = _extra_product(session, supports_cod=False)

        client.post("/api/v1/cart", headers=headers(farmer), json={"product_id": paddy["product_id"], "quantity": 1})
        cart = client.get("/api/v1/cart", headers=headers(farmer)).json()["data"]
        assert cart["cod_available"] is True

        client.post("/api/v1/cart", headers=headers(farmer), json={"product_id": no_cod.product_id, "quantity": 1})
        cart = client.get("/api/v1/cart", headers=headers(farmer)).json()["data"]
        assert cart["cod_available"] is False
    finally:
        session.close()


def test_recently_viewed_uses_real_views_and_is_isolated():
    session = SessionLocal()
    try:
        farmer = user(session, 29)
        other = user(session, 30)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)

        v = client.post(f"/api/v1/products/{paddy['id']}/view", headers=headers(farmer))
        assert v.status_code == 200

        mine = client.get("/api/v1/products/recently-viewed", headers=headers(farmer)).json()["data"]
        assert len(mine["items"]) == 1
        assert mine["items"][0]["name"] == "Hybrid Paddy Seed"

        theirs = client.get("/api/v1/products/recently-viewed", headers=headers(other)).json()["data"]
        assert theirs["items"] == []
    finally:
        session.close()


def test_cancel_wallet_order_refunds_wallet():
    session = SessionLocal()
    try:
        farmer = user(session, 31)
        wt = wallet(session, farmer, balance=5000.0)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)

        order = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": paddy["product_id"], "quantity": 2}],
            "payment_method": "wallet",
            "wallet_pin": "1234",
        }).json()["data"]
        assert round(session.query(Wallet).filter(Wallet.user_id == farmer.id).first().balance, 2) == round(5000 - 840, 2)

        r = client.put(f"/api/v1/orders/{order['order_id']}?status=cancelled", headers=headers(farmer))
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["status"] == "cancelled"
        assert d["payment_status"] == "refunded"

        session.expire_all()
        got = session.query(Wallet).filter(Wallet.user_id == farmer.id).first()
        assert round(got.balance, 2) == 5000
        credit = session.query(WalletTransaction).filter(
            WalletTransaction.user_id == farmer.id,
            WalletTransaction.transaction_type == "credit",
        ).first()
        assert credit is not None and credit.payment_method == "refund"

        events = [t.status for t in session.query(DeliveryTracking).order_by(DeliveryTracking.timestamp).all()]
        assert events == ["placed", "cancelled"]
    finally:
        session.close()


def test_order_data_is_isolated_per_farmer():
    session = SessionLocal()
    try:
        owner = user(session, 32)
        intruder = user(session, 33)
        seed_catalogue(session, owner)
        paddy = _first_product(session, owner)

        order = client.post("/api/v1/orders", headers=headers(owner), json={
            "items": [{"product_id": paddy["product_id"], "quantity": 1}],
            "delivery_address": "Nellore, Andhra Pradesh 524001",
            "payment_method": "cod",
        }).json()["data"]
        oid = order["order_id"]

        assert client.get(f"/api/v1/orders/{oid}", headers=headers(intruder)).status_code == 404
        assert client.get(f"/api/v1/orders/{oid}/tracking", headers=headers(intruder)).status_code == 404
        assert client.post(f"/api/v1/orders/{oid}/confirm-received", headers=headers(intruder)).status_code == 404
        assert client.post(f"/api/v1/orders/{oid}/reorder", headers=headers(intruder)).status_code == 404
        assert client.put(f"/api/v1/orders/{oid}?status=cancelled", headers=headers(intruder)).status_code == 404

        # Owner's data untouched.
        t = client.get(f"/api/v1/orders/{oid}/tracking", headers=headers(owner)).json()["data"]
        assert t["current_status"] == "placed"
    finally:
        session.close()


def test_orders_always_carry_estimated_delivery():
    session = SessionLocal()
    try:
        farmer = user(session, 40)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)

        for method, body in [
            ("cod", {"payment_method": "cod"}),
            ("wallet", {"payment_method": "wallet", "wallet_pin": "1234"}),
        ]:
            wallet(session, farmer, balance=5000.0) if method == "wallet" else None
            resp = client.post("/api/v1/orders", headers=headers(farmer), json={
                "items": [{"product_id": paddy["product_id"], "quantity": 1}],
                "delivery_address": "Nellore, Andhra Pradesh 524001",
                **body,
            })
            assert resp.status_code == 201
            d = resp.json()["data"]
            assert d.get("estimated_delivery"), "order response must include estimated_delivery"
            assert len(d["estimated_delivery"]) == 10
            assert d["estimated_delivery"] >= date.today().isoformat()
    finally:
        session.close()


def test_orders_track_expected_delivery_and_no_fabricated_pic_in_detail():
    session = SessionLocal()
    try:
        farmer = user(session, 41)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)
        order = client.post("/api/v1/orders", headers=headers(farmer), json={
            "items": [{"product_id": paddy["product_id"], "quantity": 1}],
            "payment_method": "cod",
        }).json()["data"]

        detail = client.get(f"/api/v1/orders/{order['order_id']}", headers=headers(farmer)).json()["data"]
        assert detail["expected_delivery"] == detail["estimated_delivery"]
        assert detail["expected_delivery"] >= date.today().isoformat()
        assert detail["person_in_charge"] is None
        assert detail["company"] is None
        assert detail["can_confirm_received"] is True
    finally:
        session.close()


def test_product_payload_includes_expected_delivery():
    session = SessionLocal()
    try:
        farmer = user(session, 42)
        seed_catalogue(session, farmer)
        paddy = _first_product(session, farmer)

        detail = client.get(f"/api/v1/input-store/products/{paddy['id']}", headers=headers(farmer)).json()["data"]
        assert detail.get("expected_delivery")
        assert len(detail["expected_delivery"]) == 10
        assert detail["expected_delivery"] >= date.today().isoformat()

        listed = client.get("/api/v1/input-store/products", headers=headers(farmer)).json()["data"]
        assert all(p.get("expected_delivery") for p in listed["items"])
    finally:
        session.close()


def test_catalogue_config_covers_every_input_category_with_400_plus():
    from app.database import seed_input_store
    from app.input_store_taxonomy import INPUT_STORE_SLUGS

    configured = {slug for slug, _name, _icon in seed_input_store.CATEGORIES}
    assert configured == set(INPUT_STORE_SLUGS)

    total_rows = 0
    names = []
    for slug in configured:
        rows = seed_input_store.C.get(slug, [])
        assert len(rows) >= 400, f"{slug} has only {len(rows)} rows"
        total_rows += len(rows)
        for row in rows:
            assert row.get("name"), f"{slug} row missing name: {row}"
            names.append(row["name"])

    assert total_rows == len(names) == len(set(names)), "catalogue names must be globally unique"