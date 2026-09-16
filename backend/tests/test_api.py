import sys
import os

# Isolate tests from the production database. This must be set BEFORE any app
# import so that app.config/connection build the engine against a test DB.
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
from app.models import *
from app.utils.auth import hash_password, normalize_farmer_id, generate_farmer_id

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


@pytest.fixture
def test_user(db):
    user = User(
        full_name="Test Farmer",
        phone_number="9999999999",
        email="test@farm.com",
        password_hash=hash_password("1234"),
        preferred_language="en",
        role="farmer",
        is_verified=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user):
    response = client.post("/api/v1/auth/login", json={
        "phone_number": "9999999999",
        "password": "1234"
    })
    data = response.json()
    if "data" in data:
        return data["data"]["access_token"]
    elif "access_token" in data:
        return data["access_token"]
    return None


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


class TestHealthCheck:
    def test_health(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestAuth:
    def test_normalize_farmer_id_variants(self):
        assert normalize_farmer_id("9") == "FA-AS-00000009"
        assert normalize_farmer_id("100") == "FA-AS-00000100"
        assert normalize_farmer_id("12345678") == "FA-AS-12345678"
        assert normalize_farmer_id("FA-AS-9") == "FA-AS-00000009"
        assert normalize_farmer_id("FA-AS-00000009") == "FA-AS-00000009"

    def test_generate_farmer_id_uses_eight_digit_padding(self, db):
        user = User(
            full_name="Padded Farmer",
            phone_number="7777777777",
            email="padded@farm.com",
            password_hash=hash_password("1234"),
            preferred_language="en",
            role="farmer",
            is_verified=True,
            is_active=True,
            farmer_id="FA-AS-23",
        )
        db.add(user)
        db.commit()

        generated = generate_farmer_id(db)
        assert generated == "FA-AS-00000024"

    def test_login_accepts_numeric_farmer_id(self, db, test_user):
        test_user.farmer_id = "FA-AS-00000009"
        test_user.password_hash = hash_password("1234")
        db.add(test_user)
        db.commit()
        db.refresh(test_user)

        response = client.post("/api/v1/auth/login", json={
            "farmer_id": "9",
            "pin": "1234"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["user"]["farmer_id"] == "FA-AS-00000009"

    def test_register(self):
        response = client.post("/api/v1/auth/register", json={
            "full_name": "New Farmer",
            "phone_number": "8888888888",
            "email": "new@farm.com",
            "password": "1234",
            "preferred_language": "en"
        })
        assert response.status_code in [200, 201]
        data = response.json().get("data", {})
        assert data.get("farmer_id")
        assert data.get("access_token")
        import re as _re
        assert _re.match(r"^FA-AS-\d{8}$", data["farmer_id"])

    def test_register_requires_pin(self):
        response = client.post("/api/v1/auth/register", json={
            "full_name": "No Pin Farmer",
            "phone_number": "8888888889",
        })
        assert response.status_code == 400

    def test_login_success(self, test_user):
        response = client.post("/api/v1/auth/login", json={
            "phone_number": "9999999999",
            "password": "1234"
        })
        assert response.status_code == 200

    def test_login_wrong_password(self, test_user):
        response = client.post("/api/v1/auth/login", json={
            "phone_number": "9999999999",
            "password": "wrong"
        })
        assert response.status_code in [400, 401]

    def test_get_me(self, auth_headers):
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200

    def test_unauthorized(self):
        response = client.get("/api/v1/auth/me")
        assert response.status_code in [401, 403]


class TestFarms:
    def test_create_farm(self, auth_headers):
        response = client.post("/api/v1/farms", json={
            "farm_name": "Test Farm",
            "total_area": 10.0,
            "area_unit": "Acres",
            "state": "Telangana",
            "district": "Hyderabad"
        }, headers=auth_headers)
        assert response.status_code in [200, 201]

    def test_list_farms(self, auth_headers):
        response = client.get("/api/v1/farms", headers=auth_headers)
        assert response.status_code == 200

    def test_create_plot(self, auth_headers):
        farm_resp = client.post("/api/v1/farms", json={
            "farm_name": "Plot Test Farm",
            "total_area": 5.0,
            "area_unit": "Acres"
        }, headers=auth_headers)
        farm_data = farm_resp.json()
        farm_id = farm_data.get("data", {}).get("farm_id") or farm_data.get("farm_id")
        if farm_id:
            response = client.post(f"/api/v1/farms/{farm_id}/plots", json={
                "plot_name": "Test Plot",
                "area": 2.5
            }, headers=auth_headers)
            assert response.status_code in [200, 201]


class TestCrops:
    def test_list_crops(self, auth_headers):
        response = client.get("/api/v1/crops", headers=auth_headers)
        assert response.status_code == 200

    def test_create_crop(self, auth_headers):
        response = client.post("/api/v1/crops", json={
            "name": "Test Crop",
            "variety": "Test Variety",
            "category": "Cereal",
            "season": "Kharif"
        }, headers=auth_headers)
        assert response.status_code in [200, 201]


class TestFinance:
    def test_finance_summary(self, auth_headers):
        response = client.get("/api/v1/finance/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_income" in data or "data" in data

    def test_create_transaction(self, auth_headers):
        response = client.post(
            "/api/v1/transactions",
            json={"type": "expense", "category": "Seeds", "amount": 5000, "description": "Seed purchase"},
            headers=auth_headers
        )
        assert response.status_code in [200, 201]

    def test_create_transaction_rejects_query_params(self, auth_headers):
        response = client.post(
            "/api/v1/transactions?type=expense&category=Seeds&amount=5000",
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_create_expense(self, auth_headers):
        response = client.post(
            "/api/v1/expenses",
            json={"category": "Fertilizer", "amount": 2500, "description": "Urea"},
            headers=auth_headers
        )
        assert response.status_code in [200, 201]

    def test_create_income(self, auth_headers):
        response = client.post(
            "/api/v1/income",
            json={"category": "Crop Sale", "amount": 15000, "source": "Mandi"},
            headers=auth_headers
        )
        assert response.status_code in [200, 201]

    def test_list_transactions(self, auth_headers):
        response = client.get("/api/v1/transactions", headers=auth_headers)
        assert response.status_code == 200


class TestWorkers:
    def test_list_workers(self, auth_headers):
        response = client.get("/api/v1/workers", headers=auth_headers)
        assert response.status_code == 200

    def test_list_equipment(self, auth_headers):
        response = client.get("/api/v1/equipment", headers=auth_headers)
        assert response.status_code == 200


class TestMarketplace:
    def test_list_products(self, auth_headers):
        response = client.get("/api/v1/products", headers=auth_headers)
        assert response.status_code == 200

    def test_create_product(self, auth_headers):
        response = client.post(
            "/api/v1/products",
            json={"name": "Organic Rice", "price": 90.0, "unit": "kg", "stock_quantity": 100},
            headers=auth_headers
        )
        assert response.status_code in [200, 201]

    def test_list_categories(self, auth_headers):
        response = client.get("/api/v1/product-categories", headers=auth_headers)
        assert response.status_code == 200

    def test_create_order(self, auth_headers):
        product_resp = client.post(
            "/api/v1/products",
            json={"name": "Pesticide", "price": 350.0, "unit": "ltr", "stock_quantity": 50},
            headers=auth_headers
        )
        product_id = product_resp.json().get("data", {}).get("product_id") or product_resp.json().get("product_id")
        if not product_id:
            pytest.skip("product creation failed")
        response = client.post(
            "/api/v1/orders",
            json={"items": [{"product_id": product_id, "quantity": 2}]},
            headers=auth_headers
        )
        assert response.status_code in [200, 201]


class TestGovernment:
    def test_list_schemes(self, auth_headers):
        response = client.get("/api/v1/government-schemes", headers=auth_headers)
        assert response.status_code == 200

    def test_list_insurance(self, auth_headers):
        response = client.get("/api/v1/insurance-policies", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_create_insurance_aliases(self, auth_headers):
        response = client.post(
            "/api/v1/insurance-policies",
            json={"type": "crop", "name": "PMFBY", "coverage": 200000, "crop": "Rice"},
            headers=auth_headers
        )
        assert response.status_code in [200, 201]


class TestNotifications:
    def test_list_notifications(self, auth_headers):
        response = client.get("/api/v1/notifications", headers=auth_headers)
        assert response.status_code == 200


class TestWeather:
    def test_current_weather(self, auth_headers):
        response = client.get("/api/v1/weather/current?latitude=17.05&longitude=79.28", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


class TestAI:
    def test_chat(self, auth_headers):
        response = client.post(
            "/api/v1/ai/chat",
            json={"message": "What fertilizer should I use for rice?"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "response" in data["data"] and isinstance(data["data"]["response"], str)
        assert "conversation_id" in data["data"]

    def test_chat_rejects_query_param(self, auth_headers):
        response = client.post(
            "/api/v1/ai/chat?message=hello",
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_recommendations_body(self, auth_headers):
        response = client.post("/api/v1/ai/recommendations", json={}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "recommendations" in data["data"]

    def test_analyze_farm(self, auth_headers):
        farm_resp = client.post("/api/v1/farms", json={
            "farm_name": "AI Analysis Farm",
            "total_area": 4.0,
            "area_unit": "Acres",
        }, headers=auth_headers)
        assert farm_resp.status_code in [200, 201]
        farm_id = farm_resp.json().get("data", {}).get("farm_id")
        response = client.post("/api/v1/ai/analyze-farm", json={"farm_id": farm_id}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["analysis"]["farm_id"] == farm_id

    def test_analyze_farm_fallback(self, auth_headers):
        client.post("/api/v1/farms", json={
            "farm_name": "Fallback Farm",
            "total_area": 3.0,
            "area_unit": "Acres",
        }, headers=auth_headers)
        response = client.post("/api/v1/ai/analyze-farm", json={}, headers=auth_headers)
        assert response.status_code == 200

    def test_diagnose(self, auth_headers):
        response = client.post(
            "/api/v1/ai/diagnose",
            json={"symptoms": "yellow leaves", "crop_type": "rice"},
            headers=auth_headers
        )
        assert response.status_code == 200


class TestCommunity:
    def test_list_posts(self, auth_headers):
        response = client.get("/api/v1/posts", headers=auth_headers)
        assert response.status_code == 200

    def test_create_post(self, auth_headers):
        response = client.post(
            "/api/v1/posts",
            json={"content": "Hello from test!", "title": "Test Post"},
            headers=auth_headers
        )
        assert response.status_code in [200, 201]

    def test_post_ownership_and_saved_data_are_user_scoped(self, db, auth_headers):
        post = client.post(
            "/api/v1/posts",
            json={"content": "A private test discussion", "title": "Ownership"},
            headers=auth_headers,
        ).json()["data"]

        other = User(
            full_name="Second Farmer",
            phone_number="8888888888",
            email="second@farm.com",
            password_hash=hash_password("1234"),
            preferred_language="en",
            role="farmer",
            is_active=True,
        )
        db.add(other)
        db.commit()
        login = client.post("/api/v1/auth/login", json={
            "phone_number": "8888888888", "password": "1234"
        })
        other_token = login.json()["data"]["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        assert client.patch(
            f"/api/v1/posts/{post['id']}",
            json={"content": "Unauthorized edit"},
            headers=other_headers,
        ).status_code == 403
        assert client.delete(
            f"/api/v1/posts/{post['id']}", headers=other_headers
        ).status_code == 403

        client.post(f"/api/v1/posts/{post['id']}/save", headers=auth_headers)
        saved_for_other = client.get("/api/v1/posts/saved/list", headers=other_headers)
        assert saved_for_other.status_code == 200
        assert saved_for_other.json()["data"]["items"] == []

    def test_create_post_rejects_query_params(self, auth_headers):
        response = client.post(
            "/api/v1/posts?content=hello",
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_list_experts(self, auth_headers):
        response = client.get("/api/v1/experts", headers=auth_headers)
        assert response.status_code == 200

    def test_create_consultation(self, auth_headers):
        experts = client.get("/api/v1/experts", headers=auth_headers).json()
        data = experts.get("data") if isinstance(experts.get("data"), dict) else {}
        experts_list = data.get("items") or data.get("experts") or experts.get("experts") or []
        if not experts_list:
            pytest.skip("no experts seeded")
        expert_id = experts_list[0].get("id") or experts_list[0].get("expert_id")
        response = client.post(
            "/api/v1/consultations",
            json={"expert_id": expert_id, "topic": "Pest control"},
            headers=auth_headers
        )
        assert response.status_code in [200, 201]


class TestUsers:
    def test_profile_update_phone(self, auth_headers):
        response = client.put(
            "/api/v1/users/profile",
            json={"phone_number": "7777777777", "full_name": "Updated Farmer"},
            headers=auth_headers
        )
        assert response.status_code == 200


class TestStorage:
    def test_storage_public_get_no_auth(self):
        # Public dirs are served without auth so they can be used in <img>/<video>
        # (browsers cannot attach Authorization headers). Missing file -> 404.
        response = client.get("/api/v1/storage/profile-pictures/does-not-exist.png")
        assert response.status_code == 404

    def test_storage_documents_protected(self):
        # documents/ is never served through the generic route.
        response = client.get("/api/v1/storage/documents/any.pdf")
        assert response.status_code in [400, 404, 403]

    def test_storage_messages_require_auth_or_participant(self, auth_headers):
        # Unknown message-file paths return 404 even for authenticated users.
        response = client.get("/api/v1/storage/messages/does-not-exist.png", headers=auth_headers)
        assert response.status_code in [400, 404, 403]

    def test_storage_traversal_blocked(self, auth_headers):
        response = client.get("/api/v1/storage/..%2F..%2F.env", headers=auth_headers)
        assert response.status_code in [400, 404, 403]


class TestServices:
    def test_list_services_catalog(self):
        response = client.get("/api/v1/services")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        items = data["data"]["items"]
        assert len(items) >= 80

    def test_category_filtering(self):
        response = client.get("/api/v1/services?category=crop-cultivation")
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) >= 10
        assert all(item["category"] == "crop-cultivation" for item in items)

    def test_search_services(self):
        response = client.get("/api/v1/services?search=drip")
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) >= 1

    def test_create_service_request_validates_phone(self, auth_headers):
        # Invalid 5-digit phone
        resp = client.post("/api/v1/service-requests", json={
            "service_name": "Soil NPK Test",
            "contact_phone": "12345",
            "preferred_date": "2026-12-01"
        }, headers=auth_headers)
        assert resp.status_code == 422

    def test_create_service_request_success(self, auth_headers):
        resp = client.post("/api/v1/service-requests", json={
            "service_name": "Drone Pesticide Spraying",
            "service_category": "pest-disease",
            "contact_phone": "9876543210",
            "preferred_date": "2026-12-10",
            "description": "3 acres paddy spray"
        }, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["service_request_id"].startswith("FA-SRQ")
        assert data["status"] == "pending"

    def test_list_farmer_service_requests(self, auth_headers):
        resp = client.get("/api/v1/service-requests", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert isinstance(items, list)

    def test_status_update_and_rating(self, auth_headers):
        # Create request
        req = client.post("/api/v1/service-requests", json={
            "service_name": "Soil Test",
            "contact_phone": "9876543210",
            "preferred_date": "2026-12-12"
        }, headers=auth_headers).json()["data"]

        req_id = req["service_request_id"]

        # Complete request
        upd = client.put(f"/api/v1/service-requests/{req_id}/status", json={"status": "completed"}, headers=auth_headers)
        assert upd.status_code == 200
        assert upd.json()["data"]["status"] == "completed"

        # Rate request
        rate = client.post(f"/api/v1/service-requests/{req_id}/rate", json={"rating": 5, "rating_feedback": "Excellent service"}, headers=auth_headers)
        assert rate.status_code == 200
        assert rate.json()["data"]["rating"] == 5

