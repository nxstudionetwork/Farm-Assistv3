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
from datetime import datetime, timedelta
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


class TestComments:
    def test_list_comments(self, user_a, headers_a, headers_b):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Comments welcome", "category": "Community",
        }).json()["data"]
        pid = post["post_id"]
        client.post(f"/api/v1/farmbuzz/posts/{pid}/comment", headers=headers_b, json={"content": "Nice!"})
        client.post(f"/api/v1/farmbuzz/posts/{pid}/comment", headers=headers_a, json={"content": "Thanks"})
        resp = client.get(f"/api/v1/farmbuzz/posts/{pid}/comments")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert data["items"][0]["content"] == "Nice!"
        assert data["items"][0]["author"]["full_name"] == "Farmer B"
        assert data["items"][0]["is_mine"] is False
        resp_b = client.get(f"/api/v1/farmbuzz/posts/{pid}/comments", headers=headers_b)
        assert resp_b.json()["data"]["items"][0]["is_mine"] is True

    def test_comment_owner_can_delete(self, user_a, headers_a, headers_b):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Delete flow", "category": "Community",
        }).json()["data"]
        pid = post["post_id"]
        comment = client.post(f"/api/v1/farmbuzz/posts/{pid}/comment", headers=headers_b, json={"content": "Bye"}).json()["data"]
        resp = client.delete(f"/api/v1/farmbuzz/posts/{pid}/comments/{comment['id']}", headers=headers_b)
        assert resp.status_code == 200
        data = client.get(f"/api/v1/farmbuzz/posts/{pid}/comments").json()["data"]
        assert data["total"] == 0

    def test_post_author_can_delete(self, user_a, headers_a, headers_b):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Moderation", "category": "Community",
        }).json()["data"]
        pid = post["post_id"]
        comment = client.post(f"/api/v1/farmbuzz/posts/{pid}/comment", headers=headers_b, json={"content": "Spam"}).json()["data"]
        resp = client.delete(f"/api/v1/farmbuzz/posts/{pid}/comments/{comment['id']}", headers=headers_a)
        assert resp.status_code == 200

    def test_stranger_cannot_delete(self, user_a, user_b, headers_a, db):
        stranger = User(
            full_name="Stranger",
            phone_number="9333333333",
            email="c@farm.com",
            password_hash=hash_password("1234"),
            preferred_language="en",
            role="farmer",
            is_active=True,
        )
        db.add(stranger)
        db.commit()
        db.refresh(stranger)
        resp_s = client.post(
            "/api/v1/auth/login", json={"phone_number": "9333333333", "password": "1234"}
        )
        headers_s = {"Authorization": "Bearer " + resp_s.json()["data"]["access_token"]}

        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Anyone else?", "category": "Community",
        }).json()["data"]
        pid = post["post_id"]
        comment = client.post(f"/api/v1/farmbuzz/posts/{pid}/comment", headers=headers_a, json={"content": "mine"}).json()["data"]
        resp = client.delete(f"/api/v1/farmbuzz/posts/{pid}/comments/{comment['id']}", headers=headers_s)
        assert resp.status_code == 403

    def test_delete_requires_auth(self, user_a, headers_a):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Auth", "category": "Farming",
        }).json()["data"]
        resp = client.delete(f"/api/v1/farmbuzz/posts/{post['post_id']}/comments/some-id")
        assert resp.status_code in (401, 403)


class TestViews:
    def test_view_dedup_per_user(self, user_a, headers_a, headers_b):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Watch this", "category": "Farming",
        }).json()["data"]
        pid = post["post_id"]
        first = client.post(f"/api/v1/farmbuzz/posts/{pid}/view", headers=headers_b).json()["data"]
        assert first["is_new_view"] is True
        assert first["views_count"] == 1
        second = client.post(f"/api/v1/farmbuzz/posts/{pid}/view", headers=headers_b).json()["data"]
        assert second["is_new_view"] is False
        assert second["views_count"] == 1

    def test_owner_view_not_counted(self, user_a, headers_a):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Own count", "category": "Farming",
        }).json()["data"]
        data = client.post(f"/api/v1/farmbuzz/posts/{post['post_id']}/view", headers=headers_a).json()["data"]
        assert data["is_new_view"] is False
        assert data["views_count"] == 0

    def test_anonymous_view_counts_once(self, user_a, headers_a):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Public", "category": "Farming",
        }).json()["data"]
        pid = post["post_id"]
        first = client.post(f"/api/v1/farmbuzz/posts/{pid}/view").json()["data"]
        assert first["is_new_view"] is True
        assert first["views_count"] == 1


class TestReport:
    def test_report_and_duplicate(self, user_a, headers_a, headers_b):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Report me", "category": "Community",
        }).json()["data"]
        pid = post["post_id"]
        resp = client.post(f"/api/v1/farmbuzz/posts/{pid}/report", headers=headers_b, json={"reason": "Spam", "description": "Looks like spam"})
        assert resp.status_code == 201
        resp2 = client.post(f"/api/v1/farmbuzz/posts/{pid}/report", headers=headers_b, json={"reason": "Spam"})
        assert resp2.status_code == 409

    def test_cannot_report_own(self, user_a, headers_a):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Mine", "category": "Farming",
        }).json()["data"]
        resp = client.post(f"/api/v1/farmbuzz/posts/{post['post_id']}/report", headers=headers_a, json={"reason": "Other"})
        assert resp.status_code == 400


class TestSaved:
    def test_saved_list(self, user_a, headers_a, headers_b):
        p1 = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={"caption": "One", "category": "Farming"}).json()["data"]
        p2 = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={"caption": "Two", "category": "Tip"}).json()["data"]
        client.post(f"/api/v1/farmbuzz/posts/{p1['post_id']}/save", headers=headers_b)
        resp = client.get("/api/v1/farmbuzz/saved", headers=headers_b)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["post_id"] == p1["post_id"]
        # unsave -> empty
        client.post(f"/api/v1/farmbuzz/posts/{p1['post_id']}/save", headers=headers_b)
        assert client.get("/api/v1/farmbuzz/saved", headers=headers_b).json()["data"]["total"] == 0

    def test_saved_requires_auth(self):
        resp = client.get("/api/v1/farmbuzz/saved")
        assert resp.status_code in (401, 403)


class TestStories:
    def test_create_text_story(self, user_a, headers_a):
        resp = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "text",
            "caption": "Harvest day update",
            "expires_in_hours": 1,
        })
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["media_type"] == "text"
        assert data["caption"] == "Harvest day update"
        assert data["author"]["full_name"] == "Farmer A"
        assert data["is_mine"] is True
        assert "story_id" in data

    def test_create_media_story_url_must_be_upload(self, user_a, headers_a):
        resp = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "image",
            "media_url": "/api/v1/farmbuzz/media/story.png",
            "caption": "Field shot",
        })
        assert resp.status_code == 201
        resp = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "image",
            "media_url": "https://evil.example.com/x.png",
        })
        assert resp.status_code == 400

    def test_validation(self, user_a, headers_a):
        resp = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "text",
            "caption": "",
        })
        assert resp.status_code == 400
        resp = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "text",
            "caption": "Too long story",
            "expires_in_hours": 200,
        })
        assert resp.status_code == 400

    def test_requires_auth(self):
        resp = client.post("/api/v1/farmbuzz/stories", json={"media_type": "text", "caption": "hi"})
        assert resp.status_code in (401, 403)

    def test_list_and_view_dedup(self, user_a, user_b, headers_a, headers_b):
        story = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "text",
            "caption": "Morning update",
        }).json()["data"]
        sid = story["id"]
        listing = client.get("/api/v1/farmbuzz/stories").json()["data"]
        assert listing["total"] >= 1
        assert any(s["id"] == sid for s in listing["items"])
        first = client.post(f"/api/v1/farmbuzz/stories/{sid}/view", headers=headers_b).json()["data"]
        assert first["is_new_view"] is True
        assert first["views_count"] == 1
        second = client.post(f"/api/v1/farmbuzz/stories/{sid}/view", headers=headers_b).json()["data"]
        assert second["is_new_view"] is False
        assert second["views_count"] == 1

    def test_owner_view_not_counted(self, user_a, headers_a):
        story = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "text",
            "caption": "Self view",
        }).json()["data"]
        data = client.post(f"/api/v1/farmbuzz/stories/{story['id']}/view", headers=headers_a).json()["data"]
        assert data["is_new_view"] is False
        assert data["views_count"] == 0

    def test_delete_story(self, user_a, headers_a):
        story = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "text",
            "caption": "Temporary",
        }).json()["data"]
        resp = client.delete(f"/api/v1/farmbuzz/stories/{story['id']}", headers=headers_a)
        assert resp.status_code == 200
        listing = client.get("/api/v1/farmbuzz/stories").json()["data"]
        assert all(s["id"] != story["id"] for s in listing["items"])

    def test_cannot_delete_others_story(self, user_a, user_b, headers_a, headers_b):
        story = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "text",
            "caption": "Mine only",
        }).json()["data"]
        resp = client.delete(f"/api/v1/farmbuzz/stories/{story['id']}", headers=headers_b)
        assert resp.status_code == 403

    def test_expired_stories_hidden(self, user_a, headers_a, db):
        story = client.post("/api/v1/farmbuzz/stories", headers=headers_a, json={
            "media_type": "text",
            "caption": "Will expire",
        }).json()["data"]
        row = db.query(FarmBuzzStory).filter(FarmBuzzStory.id == story["id"]).first()
        assert row is not None
        row.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
        listing = client.get("/api/v1/farmbuzz/stories").json()["data"]
        assert all(s["id"] != story["id"] for s in listing["items"])


class TestInteractions:
    def test_record_events(self, user_a, user_b, headers_a, headers_b, db):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Event test",
        }).json()["data"]
        pid = post["post_id"]
        for etype in ("qualified_view", "watch", "complete", "replay", "skip"):
            resp = client.post(f"/api/v1/farmbuzz/posts/{pid}/event", headers=headers_b, json={
                "event_type": etype,
                "watch_duration_ms": 2400,
                "completion_pct": 95,
            })
            assert resp.status_code == 201
            assert resp.json()["data"]["recorded"] is True
        rows = db.query(FarmBuzzInteraction).filter(FarmBuzzInteraction.post_id == post["id"]).all()
        types = {r.event_type for r in rows}
        assert types == {"qualified_view", "watch", "complete", "replay", "skip"}
        assert all(r.watch_duration_ms == 2400 for r in rows)

    def test_invalid_event_type(self, user_a, headers_a, headers_b):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Event test",
        }).json()["data"]
        resp = client.post(f"/api/v1/farmbuzz/posts/{post['post_id']}/event", headers=headers_b, json={
            "event_type": "pause",
        })
        assert resp.status_code == 400

    def test_owner_events_not_recorded(self, user_a, headers_a, db):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Self event",
        }).json()["data"]
        resp = client.post(f"/api/v1/farmbuzz/posts/{post['post_id']}/event", headers=headers_a, json={
            "event_type": "qualified_view",
            "watch_duration_ms": 3000,
        })
        assert resp.status_code == 201
        assert resp.json()["data"]["recorded"] is False
        rows = db.query(FarmBuzzInteraction).filter(FarmBuzzInteraction.post_id == post["id"]).all()
        assert rows == []

    def test_duration_and_completion_clamped(self, user_a, headers_a, headers_b, db):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Clamp test",
        }).json()["data"]
        client.post(f"/api/v1/farmbuzz/posts/{post['post_id']}/event", headers=headers_b, json={
            "event_type": "watch",
            "watch_duration_ms": 99999999,
            "completion_pct": 250,
        })
        row = db.query(FarmBuzzInteraction).filter(FarmBuzzInteraction.post_id == post["id"]).first()
        assert row is not None
        assert row.watch_duration_ms == 3600000
        assert row.completion_pct == 100

    def test_requires_auth(self, user_a, headers_a):
        post = client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "caption": "Auth test",
        }).json()["data"]
        resp = client.post(f"/api/v1/farmbuzz/posts/{post['post_id']}/event", json={"event_type": "watch"})
        assert resp.status_code in (401, 403)


class TestRecommendedShorts:
    def test_recommended_returns_shorts(self, user_a, headers_a):
        client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "content_type": "short",
            "title": "Recommended short",
            "caption": "demo #farming",
            "category": "Farming",
        })
        resp = client.get("/api/v1/farmbuzz/shorts/recommended", params={"limit": 10, "page": 1}, headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert data["items"]
        assert all(i["content_type"] == "short" for i in data["items"])

    def test_recommended_public(self, user_a, headers_a):
        client.post("/api/v1/farmbuzz/posts", headers=headers_a, json={
            "content_type": "short",
            "title": "Public short",
            "caption": "demo",
            "category": "Farming",
        })
        resp = client.get("/api/v1/farmbuzz/shorts/recommended", params={"limit": 5})
        assert resp.status_code == 200
        assert resp.json()["data"]["items"]
        assert len(resp.json()["data"]["items"]) <= 5
