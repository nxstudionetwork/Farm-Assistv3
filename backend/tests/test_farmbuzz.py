import sys
import os

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_farm_assist.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models import *
from app.utils.auth import hash_password

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
def user_a(db):
    user = User(
        full_name="Farmer A",
        phone_number="9111111111",
        email="a@farm.com",
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
def user_b(db):
    user = User(
        full_name="Farmer B",
        phone_number="9222222222",
        email="b@farm.com",
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
def token_a(user_a):
    resp = client.post("/api/v1/auth/login", json={"phone_number": "9111111111", "password": "1234"})
    data = resp.json().get("data", {})
    return data.get("access_token")


@pytest.fixture
def token_b(user_b):
    resp = client.post("/api/v1/auth/login", json={"phone_number": "9222222222", "password": "1234"})
    data = resp.json().get("data", {})
    return data.get("access_token")


@pytest.fixture
def headers_a(token_a):
    return {"Authorization": f"Bearer {token_a}"}


@pytest.fixture
def headers_b(token_b):
    return {"Authorization": f"Bearer {token_b}"}


class TestFeed:
    def test_feed_public(self, user_a, headers_a):
        client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "content_type": "post",
            "title": "Drip irrigation demo",
            "caption": "Showing how drip saves 40% water #irrigation #drip",
            "category": "Tip",
            "location": "Nashik",
            "crop": "Tomato",
        })
        resp = client.get("/api/v1/farmbuzz/feed")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["content_type"] == "post"
        assert "irrigation" in item["hashtags"]
        assert "drip" in item["hashtags"]
        assert item["author"]["full_name"] == "Farmer A"

    def test_feed_filters(self, user_a, headers_a):
        client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "content_type": "short",
            "title": "Quick pest tip",
            "caption": "Neem spray short #tips",
            "category": "Tip",
        })
        resp = client.get("/api/v1/farmbuzz/feed", params={"content_type": "short"})
        items = resp.json()["data"]["items"]
        assert all(i["content_type"] == "short" for i in items)
        resp = client.get("/api/v1/farmbuzz/feed", params={"content_type": "post"})
        assert resp.json()["data"]["total"] == 0


class TestCreatePost:
    def test_requires_auth(self):
        resp = client.post("/api/v1/farmbuzz/posts", json={"caption": "hi"})
        assert resp.status_code in (401, 403)

    def test_create_invalid_category(self, headers_a):
        resp = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "test", "category": "Nope",
        })
        assert resp.status_code == 400

    def test_create_empty(self, headers_a):
        resp = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={"caption": "", "title": ""})
        assert resp.status_code == 400

    def test_delete_own(self, headers_a):
        created = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "content_type": "short", "title": "t", "caption": "c", "category": "Farming",
        }).json()["data"]
        pid = created["post_id"]
        resp = client.delete(f"/api/v1/farmbuzz/posts/{pid}", headers=headers_a)
        assert resp.status_code == 200
        resp = client.get(f"/api/v1/farmbuzz/posts/{pid}")
        assert resp.status_code == 404


class TestEngagement:
    def test_like_toggle(self, user_a, headers_a, headers_b):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Like me #hello", "category": "Community",
        }).json()["data"]
        pid = post["post_id"]

        resp = client.post(f"/api/v1/farmbuzz/posts/{pid}/like", headers=headers_b)
        assert resp.json()["data"]["is_liked"] is True
        resp = client.post(f"/api/v1/farmbuzz/posts/{pid}/like", headers=headers_b)
        assert resp.json()["data"]["is_liked"] is False
        assert resp.json()["data"]["likes_count"] == 0

    def test_comment(self, user_a, headers_a, headers_b):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Comment on me", "category": "Community",
        }).json()["data"]
        pid = post["post_id"]
        resp = client.post(f"/api/v1/farmbuzz/posts/{pid}/comment", headers=headers_b, json={"content": "Nice post!"})
        assert resp.status_code == 201
        resp = client.post(f"/api/v1/farmbuzz/posts/{pid}/comment", headers=headers_b, json={"content": ""})
        assert resp.status_code == 400

    def test_save_and_share(self, user_a, headers_a, headers_b):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Save me", "category": "Community",
        }).json()["data"]
        pid = post["post_id"]
        client.post(f"/api/v1/farmbuzz/posts/{pid}/save", headers=headers_b)
        client.post(f"/api/v1/farmbuzz/posts/{pid}/share", headers=headers_b)
        detail = client.get(f"/api/v1/farmbuzz/posts/{pid}", headers=headers_b).json()["data"]
        assert detail["is_saved"] is True
        assert detail["shares_count"] == 1


class TestFollow:
    def test_follow_unfollow(self, user_a, user_b, headers_a):
        resp = client.post(f"/api/v1/farmbuzz/users/{user_b.id}/follow", headers=headers_a)
        assert resp.json()["data"]["following"] is True
        resp = client.post(f"/api/v1/farmbuzz/users/{user_b.id}/follow", headers=headers_a)
        assert resp.json()["data"]["following"] is False

    def test_no_self_follow(self, user_a, headers_a):
        resp = client.post(f"/api/v1/farmbuzz/users/{user_a.id}/follow", headers=headers_a)
        assert resp.status_code == 400


class TestProfile:
    def test_my_profile(self, user_a, headers_a):
        resp = client.get("/api/v1/farmbuzz/profile", headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["full_name"] == "Farmer A"
        assert "followers_count" in data
        assert "posts_count" in data

    def test_update_profile(self, user_a, headers_a):
        resp = client.put("/api/v1/farmbuzz/profile", headers=headers_a, json={
            "bio": "Paddy & vegetable farmer",
            "farm_location": "Krishna District, AP",
            "crops": "Paddy, Brinjal",
            "farming_type": "Organic",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["bio"] == "Paddy & vegetable farmer"
        assert data["crops"] == "Paddy, Brinjal"


class TestSearch:
    def test_search_posts(self, user_a, headers_a):
        client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Zero tillage wheat experiment #zerotill", "category": "Crop",
        })
        resp = client.get("/api/v1/farmbuzz/search", params={"q": "wheat"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["posts"]) >= 1

    def test_search_hashtag(self, user_a, headers_a):
        client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Harvest time #kharif2026", "category": "Farming",
        })
        resp = client.get("/api/v1/farmbuzz/search", params={"q": "kharif", "type": "hashtag"})
        assert resp.status_code == 200
        assert len(resp.json()["data"]["hashtags"]) >= 1


class TestTrends:
    def test_trends(self, user_a, headers_a):
        client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Trending test post", "category": "Community",
        })
        resp = client.get("/api/v1/farmbuzz/trends")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["trends"]) >= 5
        assert isinstance(data["hot_posts"], list)


class TestMediaValidation:
    def test_reject_bad_type(self, headers_a):
        resp = client.post(
            "/api/v1/farmbuzz/media/upload?kind=image",
            headers=headers_a,
            files={"file": ("evil.exe", b"x" * 10, "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_upload_image(self, headers_a):
        resp = client.post(
            "/api/v1/farmbuzz/media/upload?kind=image",
            headers=headers_a,
            files={"file": ("field.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["url"].startswith("/api/v1/farmbuzz/media/")
