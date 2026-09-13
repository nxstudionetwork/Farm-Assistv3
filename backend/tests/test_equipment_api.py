import os
import sys

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_equipment_api.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import Base, SessionLocal, engine
from app.models.marketplace import Product, ProductCategory, ProductCrop, Seller, EquipmentMetadata
from app.models.user import FarmerProfile, User
from app.models.worker import Equipment as RentalEquipment, EquipmentBooking
from app.utils.auth import create_access_token, hash_password


client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def user(session, suffix, crops="", has_profile=True, phone=None):
    value = User(
        farmer_id=f"FA-EQ-{suffix:08d}",
        full_name=f"Equipment Farmer {suffix}",
        phone_number=phone or f"92000{suffix:05d}",
        email=f"equip{suffix}@example.test",
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


def seed_equipment_catalogue(session, owner):
    hand_tools = ProductCategory(name="Hand Tools", slug="hand-tools", icon="fa-hand-holding-heart")
    equipment = ProductCategory(name="Equipment", slug="equipment", icon="fa-tractor")
    session.add_all([hand_tools, equipment])
    session.commit()
    session.refresh(hand_tools)
    session.refresh(equipment)

    seller = Seller(
        user_id=owner.id,
        shop_name="Test Agri Equipment",
        location="Nellore, Andhra Pradesh",
        is_verified=True,
        rating=4.5,
    )
    session.add(seller)
    session.commit()
    session.refresh(seller)

    def add_product(pid, name, price, mrp, stock, cat, brand, rating, meta, crop=None):
        product = Product(
            product_id=pid,
            name=name,
            price=price,
            original_price=mrp,
            unit="piece",
            stock_quantity=stock,
            min_order_quantity=1,
            is_active=True,
            category_id=cat.id,
            seller_id=seller.id,
            brand=brand,
            rating=rating,
            images=[f"https://img.example/{pid}.jpg"],
            tags={"equipment_type": meta.get("equipment_type"), "power_source": meta.get("power_source")},
        )
        session.add(product)
        session.commit()
        session.refresh(product)
        session.add(EquipmentMetadata(product_id=product.id, **meta))
        if crop:
            session.add(ProductCrop(product_id=product.id, crop_name=crop))
    session.commit()

    add_product(
        "AEQP-0001",
        "Solar Water Pump 2HP",
        25000,
        30000,
        5,
        equipment,
        "GreenLine",
        4.6,
        {
            "equipment_type": "Water Pump",
            "power_source": "Solar",
            "material": "Stainless Steel",
            "weight": "35kg",
            "dimensions": "60x40x50 cm",
            "warranty": "2 years",
            "suitable_use": "Irrigation",
            "operating_width": "N/A",
            "capacity": "5000 L/h",
        },
        crop="rice",
    )
    add_product(
        "AEQP-0002",
        "Battery Sprayer 16L",
        6500,
        8000,
        0,
        equipment,
        "FarmBest",
        4.2,
        {
            "equipment_type": "Sprayer",
            "power_source": "Battery",
            "material": "Plastic",
            "weight": "8kg",
            "dimensions": "45x30x55 cm",
            "warranty": "1 year",
            "suitable_use": "Spraying",
            "operating_width": "2m",
            "capacity": "16 L",
        },
    )
    add_product(
        "AEQP-0003",
        "Garden Trowel Set",
        300,
        None,
        50,
        hand_tools,
        "AgriTools",
        4.0,
        {
            "equipment_type": "Garden Tool",
            "power_source": "Manual",
            "material": "Carbon Steel",
            "weight": "0.5kg",
            "dimensions": "30 cm",
            "warranty": None,
            "suitable_use": "Planting",
            "operating_width": "8 cm",
            "capacity": None,
        },
        crop="vegetables",
    )
    add_product(
        "AEQP-0004",
        "Compost Fork",
        450,
        None,
        40,
        hand_tools,
        "AgriTools",
        3.8,
        {
            "equipment_type": "Garden Tool",
            "power_source": "Manual",
            "material": "Carbon Steel",
            "weight": "1.2kg",
            "dimensions": "110 cm",
            "warranty": None,
            "suitable_use": "Weeding",
            "operating_width": "15 cm",
            "capacity": None,
        },
    )
    add_product(
        "AEQP-0005",
        "Harvest Sickle",
        250,
        None,
        60,
        hand_tools,
        "SteelFarm",
        4.8,
        {
            "equipment_type": "Harvest Tool",
            "power_source": "Manual",
            "material": "High Carbon Steel",
            "weight": "0.4kg",
            "dimensions": "25 cm",
            "warranty": "6 months",
            "suitable_use": "Harvesting",
            "operating_width": "10 cm",
            "capacity": None,
        },
    )
    session.commit()


def seed_rentals(session, owner):
    tractor = RentalEquipment(
        equipment_id="FA-RNT-0001",
        name="Tractor 45HP",
        type="Tractor",
        brand="Mahindra",
        model="Yuvo 475",
        description="45HP tractor for ploughing and transport",
        daily_rate=2500,
        owner_id=owner.id,
        is_available=True,
        location="Nellore",
    )
    tiller = RentalEquipment(
        equipment_id="FA-RNT-0002",
        name="Power Tiller",
        type="Tiller",
        brand="Kubota",
        daily_rate=1800,
        owner_id=owner.id,
        is_available=False,
        location="Warangal",
    )
    session.add_all([tractor, tiller])
    session.commit()
    session.refresh(tractor)
    return tractor


def test_list_products_pagination_sort_and_filters():
    session = SessionLocal()
    try:
        farmer = user(session, 1)
        seed_equipment_catalogue(session, farmer)

        response = client.get("/api/equipment/products", headers=headers(farmer))
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["total"] == 5
        assert len(payload["items"]) == 5

        paged = client.get(
            "/api/equipment/products", headers=headers(farmer), params={"limit": 2, "page": 2}
        ).json()["data"]
        assert len(paged["items"]) == 2
        assert paged["page"] == 2

        sorted_asc = client.get(
            "/api/equipment/products", headers=headers(farmer), params={"sort_by": "price", "sort_order": "asc"}
        ).json()["data"]["items"]
        assert sorted_asc[0]["name"] == "Harvest Sickle"

        by_category = client.get(
            "/api/equipment/products", headers=headers(farmer), params={"category": "hand-tools"}
        ).json()["data"]
        assert by_category["total"] == 3

        searched = client.get(
            "/api/equipment/products", headers=headers(farmer), params={"search": "sprayer"}
        ).json()["data"]
        assert searched["total"] == 1
        assert searched["items"][0]["name"] == "Battery Sprayer 16L"

        power = client.get(
            "/api/equipment/products", headers=headers(farmer), params={"power_source": "Manual"}
        ).json()["data"]
        assert power["total"] == 3

        in_stock = client.get(
            "/api/equipment/products", headers=headers(farmer), params={"in_stock": True}
        ).json()["data"]
        assert in_stock["total"] == 4

        priced = client.get(
            "/api/equipment/products", headers=headers(farmer), params={"min_price": 500, "max_price": 10000}
        ).json()["data"]
        assert priced["total"] == 1

        branded = client.get(
            "/api/equipment/products", headers=headers(farmer), params={"brand": "AgriTools"}
        ).json()["data"]
        assert branded["total"] == 2

        top_rated = client.get(
            "/api/equipment/products", headers=headers(farmer), params={"min_rating": 4.5}
        ).json()["data"]
        assert top_rated["total"] == 2
    finally:
        session.close()


def test_categories_and_filters_endpoints():
    session = SessionLocal()
    try:
        farmer = user(session, 2)
        seed_equipment_catalogue(session, farmer)

        categories = client.get("/api/equipment/categories", headers=headers(farmer)).json()["data"]["items"]
        counts = {c["slug"]: c["count"] for c in categories}
        assert counts["hand-tools"] == 3
        assert counts["equipment"] == 2
        # Highest count first
        assert categories[0]["slug"] == "hand-tools"

        filters = client.get("/api/equipment/filters", headers=headers(farmer)).json()["data"]
        assert "GreenLine" in filters["brands"]
        assert {"Manual", "Solar", "Battery"}.issubset(set(filters["power_sources"]))
        assert filters["crops"] == ["Rice", "Vegetables"]
        assert filters["sellers"][0]["shop_name"] == "Test Agri Equipment"
        assert filters["price_range"] == {"min": 250.0, "max": 25000.0}
    finally:
        session.close()


def test_product_detail_and_404():
    session = SessionLocal()
    try:
        farmer = user(session, 3)
        seed_equipment_catalogue(session, farmer)

        listing = client.get("/api/equipment/products", headers=headers(farmer)).json()["data"]["items"]
        item = next(i for i in listing if i["name"] == "Solar Water Pump 2HP")

        detail = client.get(f"/api/equipment/products/{item['id']}", headers=headers(farmer))
        assert detail.status_code == 200
        data = detail.json()["data"]
        assert data["name"] == "Solar Water Pump 2HP"
        assert data["mrp"] == 30000
        assert data["discount"] == pytest.approx(16.7, abs=0.1)
        assert data["power_source"] == "Solar"
        assert data["crops"] == ["rice"]
        assert data["gallery_images"] == [f"https://img.example/AEQP-0001.jpg"]

        by_code = client.get("/api/equipment/products/AEQP-0002", headers=headers(farmer))
        assert by_code.status_code == 200
        assert by_code.json()["data"]["name"] == "Battery Sprayer 16L"

        missing = client.get(
            "/api/equipment/products/does-not-exist", headers=headers(farmer)
        )
        assert missing.status_code == 404
    finally:
        session.close()


def test_recommended_matches_farmer_crops():
    session = SessionLocal()
    try:
        paddy_farmer = user(session, 4, crops="Rice")
        seed_equipment_catalogue(session, paddy_farmer)

        recommended = client.get("/api/equipment/recommended", headers=headers(paddy_farmer)).json()["data"]
        assert recommended["farmer_crops"] == ["rice"]
        names = {item["name"] for item in recommended["items"]}
        assert "Solar Water Pump 2HP" in names
        assert all(item["recommendation_reason"].startswith("Recommended for your Rice crop") for item in recommended["items"])

        bare_farmer = user(session, 5, crops="", has_profile=False)
        fallback = client.get("/api/equipment/recommended", headers=headers(bare_farmer)).json()["data"]
        assert fallback["farmer_crops"] == []
        assert fallback["items"]
        assert fallback["items"][0]["recommendation_reason"] == "Essential high-rated farm equipment"
        assert fallback["items"][0]["name"] == "Harvest Sickle"
    finally:
        session.close()


def test_recently_viewed_and_post_view():
    session = SessionLocal()
    try:
        farmer = user(session, 6)
        seed_equipment_catalogue(session, farmer)

        listing = client.get("/api/equipment/products", headers=headers(farmer)).json()["data"]["items"]
        pump = next(i for i in listing if i["name"] == "Solar Water Pump 2HP")
        sickle = next(i for i in listing if i["name"] == "Harvest Sickle")

        posted = client.post(
            f"/api/equipment/viewed/{pump['product_id']}",
            headers=headers(farmer),
        )
        assert posted.status_code == 200

        # detail endpoint also records a view
        client.get(f"/api/equipment/products/{sickle['id']}", headers=headers(farmer))

        recent = client.get("/api/equipment/recent", headers=headers(farmer)).json()["data"]
        assert recent["count"] == 2
        assert {item["product_id"] for item in recent["items"]} == {"AEQP-0001", "AEQP-0005"}
    finally:
        session.close()


def test_compare_and_truncation():
    session = SessionLocal()
    try:
        farmer = user(session, 7)
        seed_equipment_catalogue(session, farmer)

        listing = client.get("/api/equipment/products", headers=headers(farmer)).json()["data"]["items"]
        two = listing[:2]
        compare = client.get(
            f"/api/equipment/compare?ids={two[0]['id']},{two[1]['id']}",
            headers=headers(farmer),
        )
        assert compare.status_code == 200
        comp = compare.json()["data"]
        assert comp["compared_count"] == 2
        assert {item["name"] for item in comp["items"]} == {two[0]["name"], two[1]["name"]}

        all_ids = ",".join(item["id"] for item in listing)
        truncated = client.get(f"/api/equipment/compare?ids={all_ids}", headers=headers(farmer)).json()["data"]
        assert truncated["compared_count"] == 4

        bad = client.get("/api/equipment/compare?ids=", headers=headers(farmer))
        assert bad.status_code == 400
    finally:
        session.close()


def test_rentals_list_book_and_my_bookings():
    session = SessionLocal()
    try:
        farmer = user(session, 8)
        seed_rentals(session, farmer)

        rentals = client.get("/api/equipment/rentals/list", headers=headers(farmer)).json()["data"]
        assert rentals["total"] == 2
        assert rentals["items"][0]["mode"] == "rent"

        searched = client.get(
            "/api/equipment/rentals/list", headers=headers(farmer), params={"search": "tractor"}
        ).json()["data"]
        assert searched["total"] == 1

        filtered = client.get(
            "/api/equipment/rentals/list", headers=headers(farmer), params={"type": "Tractor"}
        ).json()["data"]
        assert filtered["total"] == 1

        available = client.get(
            "/api/equipment/rentals/list", headers=headers(farmer), params={"is_available": True}
        ).json()["data"]
        assert available["total"] == 1

        rental_response = client.post(
            "/api/equipment/rentals/book",
            headers=headers(farmer),
            json={"equipment_id": "FA-RNT-0001", "duration_days": 2},
        )
        assert rental_response.status_code == 201
        booking = rental_response.json()["data"]
        assert booking["status"] == "confirmed"
        assert booking["total_cost"] == 5000
        assert booking["equipment_name"] == "Tractor 45HP"

        mine = client.get("/api/equipment/rentals/my-bookings", headers=headers(farmer)).json()["data"]["items"]
        assert len(mine) == 1
        assert mine[0]["booking_id"] == booking["booking_id"]
        assert mine[0]["duration_days"] == 2

        unavailable = client.post(
            "/api/equipment/rentals/book",
            headers=headers(farmer),
            json={"equipment_id": "FA-RNT-0002", "duration_days": 1},
        )
        assert unavailable.status_code == 409
    finally:
        session.close()