import os
import sys

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_input_store.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import Base, SessionLocal, engine
from app.models.marketplace import Product, ProductCategory, ProductCrop, Seller
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
        ("Hybrid Paddy Seed", 420, 500, "rice", 25.0),
        ("Wheat Seed HD-3086", 160, 200, "wheat", 0.0),
        ("Organic Neem Oil", 320, 380, "vegetables", 40.0),
        ("Cotton Seed Bt", 890, 950, "cotton", 12.0),
    ]
    for name, price, mrp, crop, stock in data:
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
            tags={"organic": "organic" in name.lower()},
        )
        session.add(product)
        session.commit()
        session.refresh(product)
        if crop:
            session.add(ProductCrop(product_id=product.id, crop_name=crop))
    session.commit()


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