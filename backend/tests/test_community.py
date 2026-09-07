"""Pytest coverage for the Community & Experts module.

Follows the same conventions as tests/test_farmbuzz.py: it points DATABASE_URL at a
dedicated SQLite file, rebuilds the schema for every test (drop at setup AND teardown,
so a stale test db can never bleed state into a run), and exercises the endpoints
through FastAPI's TestClient.

No fixture in this file persists anything between tests.
"""

import os
import sys

if "DATABASE_URL" not in os.environ:
    test_db = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_community.db"
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from datetime import date, timedelta

from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models import User, CommunityPost, CommunityGroup, Expert
from app.database.seed_communities import seed_communities
from app.utils.auth import hash_password

client = TestClient(app)


def _future(days=5):
    return (date.today() + timedelta(days=days)).isoformat()


def _past(days=1):
    return (date.today() - timedelta(days=days)).isoformat()


@pytest.fixture(scope="session", autouse=True)
def schema():
    # Build the full schema exactly once per session; tests wipe rows, not tables.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_tables(schema):
    # Cheap isolation: delete every row (foreign keys are off in SQLite by
    # default, so a blind DELETE per table is both safe and much faster than
    # recreating ~130 tables for every single test).
    session = SessionLocal()
    try:
        for table in Base.metadata.sorted_tables:
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def user_a(db):
    user = User(
        full_name="Farmer Alpha",
        phone_number="9011111111",
        email="alpha@farm.com",
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
        full_name="Farmer Beta",
        phone_number="9022222222",
        email="beta@farm.com",
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
    resp = client.post(
        "/api/v1/auth/login",
        json={"phone_number": "9011111111", "password": "1234"},
    )
    data = resp.json().get("data", {})
    return data.get("access_token")


@pytest.fixture
def token_b(user_b):
    resp = client.post(
        "/api/v1/auth/login",
        json={"phone_number": "9022222222", "password": "1234"},
    )
    data = resp.json().get("data", {})
    return data.get("access_token")


@pytest.fixture
def headers_a(token_a):
    return {"Authorization": f"Bearer {token_a}"}


@pytest.fixture
def headers_b(token_b):
    return {"Authorization": f"Bearer {token_b}"}


@pytest.fixture
def seeded_groups(db):
    """Seed the reference topic communities; returns the first group id."""
    seed_communities(db)
    group = db.query(CommunityGroup).order_by(CommunityGroup.name.asc()).first()
    return group


def make_post(headers, **overrides):
    payload = {
        "post_type": "question",
        "title": "Which paddy variety resists blast?",
        "content": "Leaf blast is spreading in my paddy field, which variety do you use?",
        "category": "Crop Protection",
        "crop": "Paddy",
        "location": "Nizamabad",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/posts", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


@pytest.fixture
def expert(db):
    row = Expert(
        expert_id="FA-EXP-900001",
        full_name="Dr. Agri Scientist",
        speciality="Plant Pathology",
        qualification="Ph.D. Plant Science",
        experience_years=12,
        bio="Pathology expert for paddy and vegetables.",
        consultation_fee=300,
        rating=4.5,
        total_consultations=10,
        is_available=True,
        location="Hyderabad",
        languages=["Telugu", "English"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --------------------------------------------------------------------------- auth
class TestAuthGates:
    def test_feed_requires_auth(self):
        resp = client.get("/api/v1/communities/feed")
        assert resp.status_code in (401, 403)

    def test_create_post_requires_auth(self):
        resp = client.post("/api/v1/posts", json={"content": "hello"})
        assert resp.status_code in (401, 403)

    def test_garbage_token_rejected(self):
        resp = client.get(
            "/api/v1/communities/feed",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code in (401, 403)


# --------------------------------------------------------------------------- posts
class TestCreatePost:
    def test_create_question(self, user_a, headers_a):
        data = make_post(headers_a, post_type="question")
        assert data["post_type"] == "question"
        assert data["title"] == "Which paddy variety resists blast?"
        assert data["category"] == "Crop Protection"
        assert data["crop"] == "Paddy"
        assert data["is_owner"] is True
        assert data["likes_count"] == 0
        assert data["post_id"].startswith("FA-PST-")
        assert data["author"]["full_name"] == "Farmer Alpha"

    def test_create_discussion_and_advice(self, user_a, headers_a):
        d = make_post(headers_a, post_type="discussion", title="Drip scheduling")
        assert d["post_type"] == "discussion"
        a = make_post(headers_a, post_type="advice", title="Seed treatment tip")
        assert a["post_type"] == "advice"

    def test_cannot_post_to_unknown_community(self, user_a, headers_a):
        resp = client.post(
            "/api/v1/posts",
            headers=headers_a,
            json={
                "content": "Where should this go?",
                "community_id": "no-such-group",
            },
        )
        assert resp.status_code == 404

    def test_rejects_invalid_post_type(self, user_a, headers_a):
        resp = client.post(
            "/api/v1/posts",
            headers=headers_a,
            json={"post_type": "nonsense", "title": "bad", "content": "bad type"},
        )
        assert resp.status_code == 400

    def test_rejects_empty_content(self, user_a, headers_a):
        resp = client.post(
            "/api/v1/posts", headers=headers_a, json={"content": "  "}
        )
        assert resp.status_code == 400


class TestFeed:
    def test_feed_shows_posts_and_owner_flags(self, user_a, user_b, headers_a, headers_b):
        mine = make_post(headers_a, post_type="question")
        make_post(headers_a, post_type="discussion", title="Drip scheduling")

        resp = client.get("/api/v1/communities/feed", headers=headers_b)
        assert resp.status_code == 200
        data = resp.json()["data"]
        ids = [i["id"] for i in data["items"]]
        assert mine["id"] in ids
        # B sees A's post as not owned.
        hit = next(i for i in data["items"] if i["id"] == mine["id"])
        assert hit["is_owner"] is False
        # A sees own post as owned.
        resp_a = client.get("/api/v1/communities/feed", headers=headers_a)
        hit_a = next(
            i for i in resp_a.json()["data"]["items"] if i["id"] == mine["id"]
        )
        assert hit_a["is_owner"] is True

    def test_feed_no_pii(self, user_a, user_b, headers_a, headers_b):
        make_post(headers_a)
        resp = client.get("/api/v1/communities/feed", headers=headers_b)
        blob = resp.text
        assert "9011111111" not in blob
        assert "alpha@farm.com" not in blob

    def test_feed_category_filter(self, user_a, headers_a, headers_b):
        make_post(headers_a, category="Irrigation", post_type="discussion")
        make_post(headers_a, category="Crop Protection", post_type="question")
        resp = client.get(
            "/api/v1/communities/feed",
            params={"category": "Irrigation"},
            headers=headers_b,
        )
        items = resp.json()["data"]["items"]
        assert items and all(i["category"] == "Irrigation" for i in items)

    def test_feed_search_content_and_name(self, user_a, user_b, headers_a, headers_b):
        make_post(headers_a, content="Trichoderma bio-agent worked well for me.",
                  post_type="advice", title="Seed treatment")
        # Content keyword
        r1 = client.get(
            "/api/v1/communities/feed", params={"search": "Trichoderma"},
            headers=headers_b,
        )
        assert len(r1.json()["data"]["items"]) >= 1
        # Author name
        r2 = client.get(
            "/api/v1/communities/feed", params={"search": "Farmer Alpha"},
            headers=headers_b,
        )
        assert len(r2.json()["data"]["items"]) >= 1
        # Gibberish -> empty
        r3 = client.get(
            "/api/v1/communities/feed", params={"search": "zzqqxx9917"},
            headers=headers_b,
        )
        assert len(r3.json()["data"]["items"]) == 0

    def test_feed_pagination(self, user_a, headers_a, headers_b):
        for i in range(4):
            make_post(headers_a, content=f"paginated post {i}")
        p1 = client.get(
            "/api/v1/communities/feed", params={"page": 1, "limit": 2},
            headers=headers_b,
        ).json()["data"]
        p2 = client.get(
            "/api/v1/communities/feed", params={"page": 2, "limit": 2},
            headers=headers_b,
        ).json()["data"]
        ids1 = [i["id"] for i in p1["items"]]
        ids2 = [i["id"] for i in p2["items"]]
        assert p1["total"] == 4
        assert p1["total_pages"] == 2
        assert not (set(ids1) & set(ids2))

    def test_feed_community_filter(self, user_a, user_b, headers_a, headers_b, seeded_groups):
        make_post(headers_a, community_id=seeded_groups.id, post_type="discussion")
        resp = client.get(
            "/api/v1/communities/feed",
            params={"community_id": seeded_groups.community_id},
            headers=headers_b,
        )
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["community_id"] == seeded_groups.id
        assert items[0]["community_name"] == seeded_groups.name


# --------------------------------------------------------------------------- ownership
class TestOwnership:
    def test_cannot_edit_others_post(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        resp = client.patch(
            f"/api/v1/posts/{post['post_id']}", headers=headers_b,
            json={"content": "hijacked"},
        )
        assert resp.status_code == 403

    def test_cannot_delete_others_post(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        resp = client.delete(f"/api/v1/posts/{post['post_id']}", headers=headers_b)
        assert resp.status_code == 403

    def test_edit_own_post_persists(self, user_a, headers_a):
        post = make_post(headers_a, post_type="discussion", title="Drip scheduling")
        resp = client.patch(
            f"/api/v1/posts/{post['post_id']}", headers=headers_a,
            json={"post_type": "experience", "title": "Drip scheduling lessons"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["post_type"] == "experience"
        assert data["title"] == "Drip scheduling lessons"

    def test_delete_own_post(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a, post_type="advice", title="cleanup me")
        pid = post["post_id"]
        resp = client.delete(f"/api/v1/posts/{pid}", headers=headers_a)
        assert resp.status_code == 200
        assert client.get(f"/api/v1/posts/{pid}", headers=headers_a).status_code == 404
        feed = client.get("/api/v1/communities/feed", headers=headers_b).json()["data"]
        assert pid not in [i["post_id"] for i in feed["items"]]


# --------------------------------------------------------------------------- detail
class TestPostDetail:
    def test_detail_embeds_comments_and_answers(
        self, user_a, user_b, headers_a, headers_b
    ):
        post = make_post(headers_a, post_type="question")
        client.post(
            f"/api/v1/posts/{post['post_id']}/comments", headers=headers_b,
            json={"content": "Great question"},
        )
        client.post(
            f"/api/v1/posts/{post['post_id']}/answers", headers=headers_b,
            json={"content": "Try TKM 6"},
        )
        resp = client.get(f"/api/v1/posts/{post['post_id']}", headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["comments"], list) and len(data["comments"]) == 1
        assert isinstance(data["answers"], list) and len(data["answers"]) == 1
        assert data["comments_count"] == 1
        assert data["answer_count"] == 1

    def test_missing_post_404(self, user_a, headers_a):
        resp = client.get("/api/v1/posts/FA-PST-does-not-exist", headers=headers_a)
        assert resp.status_code == 404
        body = resp.text.lower()
        assert "traceback" not in body
        assert "sqlalchemy" not in body


# --------------------------------------------------------------------------- likes
class TestLikes:
    def test_like_toggle(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        pid = post["post_id"]

        first = client.post(f"/api/v1/posts/{pid}/like", headers=headers_b).json()["data"]
        assert first["is_liked"] is True
        assert first["likes_count"] == 1

        second = client.post(f"/api/v1/posts/{pid}/like", headers=headers_b).json()["data"]
        assert second["is_liked"] is False
        assert second["likes_count"] == 0

        third = client.post(f"/api/v1/posts/{pid}/like", headers=headers_b).json()["data"]
        assert third["is_liked"] is True
        assert third["likes_count"] == 1

    def test_delete_like_idempotent(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        pid = post["post_id"]
        client.post(f"/api/v1/posts/{pid}/like", headers=headers_b)
        resp = client.delete(f"/api/v1/posts/{pid}/like", headers=headers_b)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_liked"] is False
        assert data["likes_count"] == 0
        # Unliking something never liked is still 200.
        again = client.delete(f"/api/v1/posts/{pid}/like", headers=headers_b)
        assert again.status_code == 200

    def test_like_missing_post_404(self, user_a, headers_a):
        resp = client.post("/api/v1/posts/FA-PST-nope/like", headers=headers_a)
        assert resp.status_code == 404


# --------------------------------------------------------------------------- saves
class TestSaves:
    def test_save_toggle_and_isolation(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        pid = post["post_id"]

        saved = client.post(f"/api/v1/posts/{pid}/save", headers=headers_b).json()["data"]
        assert saved["is_saved"] is True
        assert saved["saves_count"] == 1

        # B's saved list contains it; A's list is empty (isolation).
        b_list = client.get("/api/v1/posts/saved/list", headers=headers_b).json()["data"]
        assert b_list["total"] == 1
        assert b_list["items"][0]["post_id"] == pid
        a_list = client.get("/api/v1/posts/saved/list", headers=headers_a).json()["data"]
        assert a_list["total"] == 0

        # Toggle off removes it.
        unsaved = client.post(f"/api/v1/posts/{pid}/save", headers=headers_b).json()["data"]
        assert unsaved["is_saved"] is False
        assert unsaved["saves_count"] == 0
        b_list2 = client.get("/api/v1/posts/saved/list", headers=headers_b).json()["data"]
        assert b_list2["total"] == 0

    def test_delete_unsave_idempotent(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        pid = post["post_id"]
        client.post(f"/api/v1/posts/{pid}/save", headers=headers_b)
        resp = client.delete(f"/api/v1/posts/{pid}/save", headers=headers_b)
        assert resp.status_code == 200
        assert resp.json()["data"]["is_saved"] is False
        assert client.delete(
            f"/api/v1/posts/{pid}/save", headers=headers_b
        ).status_code == 200


# --------------------------------------------------------------------------- comments
class TestComments:
    def test_comment_and_reply(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        pid = post["post_id"]

        c = client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_b,
            json={"content": "Try TKM 6, it held up well last season."},
        )
        assert c.status_code == 201
        cid = c.json()["data"]["id"]
        assert c.json()["data"]["is_owner"] is True
        assert "Beta" in c.json()["data"]["author_name"]

        reply = client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_a,
            json={"content": "Thanks, what spacing did you keep?", "parent_comment_id": cid},
        )
        assert reply.status_code == 201
        assert reply.json()["data"]["parent_comment_id"] == cid
        assert "Beta" in (reply.json()["data"]["reply_to_name"] or "")

        listing = client.get(f"/api/v1/posts/{pid}/comments", headers=headers_a)
        assert len(listing.json()["data"]) == 2

        detail = client.get(f"/api/v1/posts/{pid}", headers=headers_a).json()["data"]
        assert detail["comments_count"] == 2

    def test_reply_keeps_single_level_thread(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        pid = post["post_id"]
        c1 = client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_b,
            json={"content": "top"},
        ).json()["data"]
        c2 = client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_a,
            json={"content": "reply 1", "parent_comment_id": c1["id"]},
        ).json()["data"]
        c3 = client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_a,
            json={"content": "reply 2", "parent_comment_id": c2["id"]},
        ).json()["data"]
        # A reply to a reply is flattened onto the top-level comment.
        assert c3["parent_comment_id"] == c1["id"]

    def test_comment_validation(self, user_a, headers_a):
        post = make_post(headers_a)
        pid = post["post_id"]
        assert client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_a,
            json={"content": " "},
        ).status_code == 400
        assert client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_a,
            json={"content": "x" * 2001},
        ).status_code == 400

    def test_comment_on_missing_post_404(self, user_a, headers_a):
        resp = client.post(
            "/api/v1/posts/FA-PST-nope/comments", headers=headers_a,
            json={"content": "hi"},
        )
        assert resp.status_code == 404

    def test_cannot_delete_others_comment(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        pid = post["post_id"]
        c = client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_a,
            json={"content": "mine"},
        ).json()["data"]
        resp = client.delete(f"/api/v1/comments/{c['id']}", headers=headers_b)
        assert resp.status_code == 403

    def test_delete_own_comment_decrements_count(
        self, user_a, user_b, headers_a, headers_b
    ):
        post = make_post(headers_a)
        pid = post["post_id"]
        c = client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_b,
            json={"content": "bye"},
        ).json()["data"]
        assert client.delete(
            f"/api/v1/comments/{c['id']}", headers=headers_b
        ).status_code == 200
        detail = client.get(f"/api/v1/posts/{pid}", headers=headers_a).json()["data"]
        assert detail["comments_count"] == 0


# --------------------------------------------------------------------------- answers
class TestAnswers:
    def test_answer_only_on_question(self, user_a, user_b, headers_a, headers_b):
        q = make_post(headers_a, post_type="question", title="A question")
        d = make_post(headers_a, post_type="discussion", title="A discussion")
        okay = client.post(
            f"/api/v1/posts/{q['post_id']}/answers", headers=headers_b,
            json={"content": "TKM 6 or improved Samba Mahsuri, both blast tolerant."},
        )
        assert okay.status_code == 201
        assert okay.json()["data"]["is_owner"] is True
        assert okay.json()["data"]["answer_id"].startswith("FA-ANS-")
        bad = client.post(
            f"/api/v1/posts/{d['post_id']}/answers", headers=headers_b,
            json={"content": "nope"},
        )
        assert bad.status_code == 400

    def test_best_answer_authorization(self, user_a, user_b, headers_a, headers_b):
        q = make_post(headers_a, post_type="question")
        ans = client.post(
            f"/api/v1/posts/{q['post_id']}/answers", headers=headers_b,
            json={"content": "TKM 6"},
        ).json()["data"]
        # The answerer cannot mark their own answer best.
        assert ans["can_mark_best"] is False
        as_b = client.post(
            f"/api/v1/posts/{q['post_id']}/answers/{ans['answer_id']}/best",
            headers=headers_b,
        )
        assert as_b.status_code == 403
        # The question author can, and only one best can exist at a time.
        mark = client.post(
            f"/api/v1/posts/{q['post_id']}/answers/{ans['answer_id']}/best",
            headers=headers_a,
        )
        assert mark.status_code == 200
        best = mark.json()["data"]
        assert best["is_best_answer"] is True
        assert sum(1 for a in best["answers"] if a["is_best_answer"]) == 1
        # Unmark toggles back off.
        unmark = client.post(
            f"/api/v1/posts/{q['post_id']}/answers/{ans['answer_id']}/best",
            headers=headers_a,
        ).json()["data"]
        assert unmark["is_best_answer"] is False

    def test_answer_validation(self, user_a, headers_a):
        q = make_post(headers_a, post_type="question")
        assert client.post(
            f"/api/v1/posts/{q['post_id']}/answers", headers=headers_a,
            json={"content": "  "},
        ).status_code == 400
        assert client.post(
            f"/api/v1/posts/{q['post_id']}/answers", headers=headers_a,
            json={"content": "x" * 5001},
        ).status_code == 400


# --------------------------------------------------------------------------- groups
class TestGroups:
    def test_seeded_catalog_and_join(self, user_a, user_b, headers_a, headers_b, seeded_groups):
        resp = client.get("/api/v1/communities/groups", headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert any(g["name"] == "Rice Farmers" for g in data["items"])

        gid = seeded_groups.community_id

        empty = client.get("/api/v1/communities/my-groups", headers=headers_a).json()["data"]
        assert empty["items"] == []

        join = client.post(f"/api/v1/communities/groups/{gid}/join", headers=headers_a)
        assert join.status_code == 200
        assert join.json()["data"]["is_joined"] is True

        again = client.post(f"/api/v1/communities/groups/{gid}/join", headers=headers_a)
        assert again.status_code == 200

        mine = client.get("/api/v1/communities/my-groups", headers=headers_a).json()["data"]
        assert len(mine["items"]) == 1
        theirs = client.get("/api/v1/communities/my-groups", headers=headers_b).json()["data"]
        assert theirs["items"] == []

        detail = client.get(
            f"/api/v1/communities/groups/{gid}", headers=headers_a
        ).json()["data"]
        assert detail["is_joined"] is True
        assert detail["member_count"] == 1

    def test_leave_group(self, user_a, headers_a, seeded_groups):
        gid = seeded_groups.community_id
        client.post(f"/api/v1/communities/groups/{gid}/join", headers=headers_a)
        leave = client.post(f"/api/v1/communities/groups/{gid}/leave", headers=headers_a)
        assert leave.status_code == 200
        assert leave.json()["data"]["is_joined"] is False
        assert client.get("/api/v1/communities/my-groups", headers=headers_a).json()["data"]["items"] == []

    def test_group_search(self, user_a, headers_a, seeded_groups):
        resp = client.get(
            "/api/v1/communities/groups",
            params={"search": seeded_groups.name[:6]},
            headers=headers_a,
        )
        assert len(resp.json()["data"]["items"]) >= 1
        gibberish = client.get(
            "/api/v1/communities/groups",
            params={"search": "zzqqxx9917"},
            headers=headers_a,
        )
        assert len(gibberish.json()["data"]["items"]) == 0

    def test_create_group_and_duplicate(self, user_a, headers_a):
        created = client.post(
            "/api/v1/communities/groups", headers=headers_a,
            json={"name": "Mango Growers", "category": "Horticulture", "description": "Mango advice"},
        )
        assert created.status_code == 201
        cid = created.json()["data"].get("community_id")
        assert cid and cid.startswith("FA-GRP-")
        dup = client.post(
            "/api/v1/communities/groups", headers=headers_a,
            json={"name": "Mango Growers"},
        )
        assert dup.status_code == 400
        missing = client.post(
            "/api/v1/communities/groups", headers=headers_a, json={"name": "  "}
        )
        assert missing.status_code == 400

    def test_unknown_group_404(self, user_a, headers_a):
        assert client.get("/api/v1/communities/groups/nope", headers=headers_a).status_code == 404
        assert client.post(
            "/api/v1/communities/groups/nope/join", headers=headers_a
        ).status_code == 404


# --------------------------------------------------------------------------- activity
class TestMyActivity:
    def test_stats_are_scoped_to_me(self, user_a, user_b, headers_a, headers_b):
        q = make_post(headers_a, post_type="question")
        make_post(headers_a, post_type="discussion", title="A discussion")
        # B comments, likes, answers, saves A's post.
        client.post(
            f"/api/v1/posts/{q['post_id']}/comments", headers=headers_b,
            json={"content": "nice"},
        )
        client.post(f"/api/v1/posts/{q['post_id']}/like", headers=headers_b)
        client.post(
            f"/api/v1/posts/{q['post_id']}/answers", headers=headers_b,
            json={"content": "TKM 6"},
        )
        client.post(f"/api/v1/posts/{q['post_id']}/save", headers=headers_b)

        resp = client.get("/api/v1/communities/my-activity", headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()["data"]
        stats = data["stats"]
        assert stats["posts"] >= 2
        assert stats["questions"] == 1
        assert stats["likes_received"] == 1
        assert stats["saved_posts"] == 0  # B saved it, not A
        assert all(i["is_owner"] for i in data["items"])

    def test_my_activity_isolated(self, user_a, user_b, headers_a, headers_b):
        make_post(headers_a)
        mine = client.get("/api/v1/communities/my-activity", headers=headers_a).json()["data"]
        theirs = client.get("/api/v1/communities/my-activity", headers=headers_b).json()["data"]
        my_ids = {i["id"] for i in mine["items"]}
        their_ids = {i["id"] for i in theirs["items"]}
        assert my_ids and not (my_ids & their_ids)
        assert theirs["stats"]["posts"] == 0


# --------------------------------------------------------------------------- profiles
class TestPublicProfile:
    def test_public_profile_privacy(self, user_a, user_b, headers_a, headers_b):
        make_post(headers_a)
        resp = client.get(f"/api/v1/farmers/{user_a.id}/profile", headers=headers_b)
        assert resp.status_code == 200
        data = resp.json()["data"]
        blob = resp.text.lower()
        assert "9011111111" not in blob
        assert "alpha@farm.com" not in blob
        assert "is_self" in data and data["is_self"] is False
        assert isinstance(data["is_following"], bool)
        assert data["posts_count"] >= 1
        assert len(data["posts"]) >= 1
        assert all(p["is_owner"] is False for p in data["posts"])

    def test_own_profile_is_self(self, user_a, headers_a):
        resp = client.get(f"/api/v1/farmers/{user_a.id}/profile", headers=headers_a)
        assert resp.json()["data"]["is_self"] is True

    def test_unknown_farmer_404(self, user_a, headers_a):
        resp = client.get("/api/v1/farmers/does-not-exist-999/profile", headers=headers_a)
        assert resp.status_code == 404

    def test_follow_state_reflected(self, user_a, user_b, headers_a, headers_b):
        resp = client.post(f"/api/v1/farmbuzz/users/{user_a.id}/follow", headers=headers_b)
        assert resp.status_code == 200
        assert resp.json()["data"]["following"] is True
        prof = client.get(
            f"/api/v1/farmers/{user_a.id}/profile", headers=headers_b
        ).json()["data"]
        assert prof["is_following"] is True
        assert prof["followers_count"] == 1
        client.post(f"/api/v1/farmbuzz/users/{user_a.id}/follow", headers=headers_b)
        prof2 = client.get(
            f"/api/v1/farmers/{user_a.id}/profile", headers=headers_b
        ).json()["data"]
        assert prof2["is_following"] is False
        assert prof2["followers_count"] == 0


# --------------------------------------------------------------------------- notifications
class TestNotifications:
    def test_engagement_notifies_post_author_only(
        self, user_a, user_b, headers_a, headers_b
    ):
        post = make_post(headers_a)
        pid = post["post_id"]
        client.post(f"/api/v1/posts/{pid}/comments", headers=headers_b, json={"content": "hello"})
        client.post(
            f"/api/v1/posts/{pid}/answers", headers=headers_b,
            json={"content": "an answer"},
        )
        client.post(f"/api/v1/posts/{pid}/like", headers=headers_b)

        def titles(headers):
            resp = client.get("/api/v1/notifications", params={"limit": 50}, headers=headers)
            data = resp.json().get("data", {})
            if isinstance(data, list):
                items = data
            else:
                items = data.get("items", [])
            return {str(i.get("title")) for i in items}

        titles_a = titles(headers_a)
        titles_b = titles(headers_b)
        assert "New Comment" in titles_a
        assert "New Answer" in titles_a
        assert "New Like" in titles_a
        # B (the actor / non-author) receives none of the post-author notifications.
        assert not ({"New Comment", "New Answer", "New Like"} & titles_b)

    def test_notifications_deep_link_to_post(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        client.post(
            f"/api/v1/posts/{post['post_id']}/comments", headers=headers_b,
            json={"content": "deep link"},
        )
        resp = client.get("/api/v1/notifications", params={"limit": 50}, headers=headers_a)
        data = resp.json().get("data", {})
        items = data if isinstance(data, list) else data.get("items", [])
        comm = [i for i in items if str(i.get("title")) == "New Comment"]
        assert comm
        assert str(comm[0].get("action_url")).startswith("community.html?post=")


# --------------------------------------------------------------------------- reports
class TestReports:
    def test_report_post_and_comment(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        pid = post["post_id"]
        comment = client.post(
            f"/api/v1/posts/{pid}/comments", headers=headers_b,
            json={"content": "spam"},
        ).json()["data"]

        r1 = client.post(
            "/api/v1/report", headers=headers_a,
            json={"post_id": pid, "reason": "spam", "description": "looks like spam"},
        )
        assert r1.status_code == 201
        assert r1.json()["data"]["report_id"].startswith("FA-RPT-")

        r2 = client.post(
            "/api/v1/report", headers=headers_a,
            json={"comment_id": comment["id"], "reason": "abuse"},
        )
        assert r2.status_code == 201

    def test_report_requires_target(self, user_a, headers_a):
        resp = client.post(
            "/api/v1/report", headers=headers_a, json={"reason": "spam"}
        )
        assert resp.status_code == 400
        resp2 = client.post(
            "/api/v1/report", headers=headers_a,
            json={"post_id": "FA-PST-nope", "reason": "spam"},
        )
        assert resp2.status_code == 404


# --------------------------------------------------------------------------- share
class TestShare:
    def test_share_increments_count(self, user_a, user_b, headers_a, headers_b):
        post = make_post(headers_a)
        resp = client.post(f"/api/v1/posts/{post['post_id']}/share", headers=headers_b)
        assert resp.status_code == 200
        assert resp.json()["data"]["shares_count"] == 1


# --------------------------------------------------------------------------- experts
class TestExperts:
    def test_list_and_get_expert(self, user_a, headers_a, expert):
        listing = client.get("/api/v1/experts", headers=headers_a).json()["data"]
        assert listing["total"] >= 1
        hit = next(i for i in listing["items"] if i["id"] == expert.id)
        assert hit["full_name"] == "Dr. Agri Scientist"
        assert hit["fee"] == 300

        detail = client.get(f"/api/v1/experts/{expert.id}", headers=headers_a).json()["data"]
        assert detail["speciality"] == "Plant Pathology"
        assert detail["is_available"] is True

    def test_expert_search_filter(self, user_a, headers_a, expert):
        resp = client.get(
            "/api/v1/experts", params={"search": "Agri"}, headers=headers_a
        )
        assert resp.json()["data"]["total"] >= 1
        resp2 = client.get(
            "/api/v1/experts", params={"speciality": "Pathology"}, headers=headers_a
        )
        assert resp2.json()["data"]["total"] >= 1
        resp3 = client.get(
            "/api/v1/experts", params={"is_available": True}, headers=headers_a
        )
        assert resp3.json()["data"]["total"] >= 1

    def test_slots(self, user_a, headers_a, expert):
        ok = client.get(
            f"/api/v1/experts/{expert.id}/slots",
            params={"date": _future(2)},
            headers=headers_a,
        )
        assert ok.status_code == 200
        data = ok.json()["data"]
        assert data["is_available"] is True
        assert len(data["slots"]) >= 1

    def test_slots_date_validation(self, user_a, headers_a, expert):
        missing = client.get(f"/api/v1/experts/{expert.id}/slots", headers=headers_a)
        assert missing.status_code == 400
        past = client.get(
            f"/api/v1/experts/{expert.id}/slots",
            params={"date": _past(1)},
            headers=headers_a,
        )
        assert past.status_code == 400


# --------------------------------------------------------------------------- consultations
class TestConsultations:
    def test_book_and_conflict(self, user_a, user_b, headers_a, headers_b, expert):
        payload = {
            "expert_id": expert.id,
            "topic": "Paddy blast management",
            "consultation_type": "crop",
            "consultation_method": "video",
            "scheduled_date": _future(5),
            "scheduled_time": "10:00 AM",
        }
        r1 = client.post("/api/v1/consultations", headers=headers_a, json=payload)
        assert r1.status_code == 201, r1.text
        con = r1.json()["data"]
        assert con["consultation_id"].startswith("FA-CNS-")
        assert con["status"] == "scheduled"
        assert con["expert_name"] == "Dr. Agri Scientist"

        # Same expert/date/time double-booking is rejected.
        r2 = client.post("/api/v1/consultations", headers=headers_b, json=payload)
        assert r2.status_code == 409

        # A different slot on the same day is fine.
        slot2 = dict(payload, scheduled_time="11:00 AM")
        r3 = client.post("/api/v1/consultations", headers=headers_b, json=slot2)
        assert r3.status_code == 201

    def test_booking_validation(self, user_a, headers_a, expert):
        base = {
            "expert_id": expert.id,
            "topic": "Valid topic",
            "scheduled_date": _future(5),
            "scheduled_time": "10:00 AM",
        }
        no_topic = client.post("/api/v1/consultations", headers=headers_a, json=dict(base, topic="  "))
        assert no_topic.status_code == 400
        no_date = client.post("/api/v1/consultations", headers=headers_a, json=dict(base, scheduled_date=None))
        assert no_date.status_code == 400
        past = client.post("/api/v1/consultations", headers=headers_a, json=dict(base, scheduled_date=_past(2)))
        assert past.status_code == 400
        bad_time = client.post("/api/v1/consultations", headers=headers_a, json=dict(base, scheduled_time="not-a-time"))
        assert bad_time.status_code == 400

    def test_list_is_isolated(self, user_a, user_b, headers_a, headers_b, expert):
        base = {
            "expert_id": expert.id,
            "topic": "Isolated topic",
            "scheduled_date": _future(5),
            "scheduled_time": "09:30 AM",
        }
        client.post("/api/v1/consultations", headers=headers_a, json=base)
        mine = client.get("/api/v1/consultations", headers=headers_a).json()["data"]
        assert mine["total"] == 1
        theirs = client.get("/api/v1/consultations", headers=headers_b).json()["data"]
        assert theirs["total"] == 0

    def test_access_control_and_reschedule(self, user_a, user_b, headers_a, headers_b, expert):
        payload = {
            "expert_id": expert.id,
            "topic": "Access control",
            "scheduled_date": _future(6),
            "scheduled_time": "02:00 PM",
        }
        con = client.post("/api/v1/consultations", headers=headers_a, json=payload).json()["data"]
        cid = con["consultation_id"]

        # Other farmer cannot view / update.
        assert client.get(f"/api/v1/consultations/{cid}", headers=headers_b).status_code == 403
        assert client.patch(
            f"/api/v1/consultations/{cid}", headers=headers_b, json={"status": "cancelled"}
        ).status_code == 403

        # Reschedule to a free slot.
        moved = client.patch(
            f"/api/v1/consultations/{cid}", headers=headers_a,
            json={"scheduled_date": _future(7), "scheduled_time": "03:00 PM"},
        )
        assert moved.status_code == 200
        assert moved.json()["data"]["scheduled_time"] == "03:00 PM"
        assert moved.json()["data"]["scheduled_date"] == _future(7)

        # Illegal direct transition scheduled -> completed.
        bad = client.patch(
            f"/api/v1/consultations/{cid}", headers=headers_a, json={"status": "completed"}
        )
        assert bad.status_code == 400

    def test_review_flow(self, user_a, headers_a, expert):
        payload = {
            "expert_id": expert.id,
            "topic": "Review flow",
            "scheduled_date": _future(4),
            "scheduled_time": "10:30 AM",
        }
        con = client.post("/api/v1/consultations", headers=headers_a, json=payload).json()["data"]
        cid = con["consultation_id"]

        # Not reviewable until completed.
        early = client.post(
            f"/api/v1/consultations/{cid}/review", headers=headers_a,
            json={"rating": 5},
        )
        assert early.status_code == 400

        client.patch(f"/api/v1/consultations/{cid}", headers=headers_a, json={"status": "confirmed"})
        client.patch(f"/api/v1/consultations/{cid}", headers=headers_a, json={"status": "in_progress"})
        client.patch(f"/api/v1/consultations/{cid}", headers=headers_a, json={"status": "completed"})

        review = client.post(
            f"/api/v1/consultations/{cid}/review", headers=headers_a,
            json={"rating": 5, "feedback": "Very helpful"},
        )
        assert review.status_code == 200
        assert review.json()["data"]["rating"] == 5

        # Double review rejected.
        again = client.post(
            f"/api/v1/consultations/{cid}/review", headers=headers_a,
            json={"rating": 4},
        )
        assert again.status_code == 400

        # Expert aggregate rating is updated.
        expert_row = client.get(f"/api/v1/experts/{expert.id}", headers=headers_a).json()["data"]
        assert expert_row["rating"] == 5.0


# --------------------------------------------------------------------------- backward-compat list
class TestLegacyListPosts:
    def test_list_posts(self, user_a, headers_a):
        make_post(headers_a)
        resp = client.get("/api/v1/posts", headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert data["items"][0]["author_name"] == "Farmer Alpha"

    def test_categories_endpoint(self, user_a, headers_a):
        resp = client.get("/api/v1/communities/categories", headers=headers_a)
        assert resp.status_code == 200
        cats = resp.json()["data"]
        assert "All" in cats
        assert "General" in cats
        assert "Pest & Disease" in cats