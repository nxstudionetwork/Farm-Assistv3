import sys
import os

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
from app.models.user import User
from app.models.messages import Conversation, ConversationParticipant, Message, Contact
from app.utils.auth import hash_password, create_access_token

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


def create_user(db, farmer_id, full_name, phone, email):
    user = User(
        farmer_id=farmer_id,
        full_name=full_name,
        phone_number=phone,
        email=email,
        password_hash=hash_password("pass123"),
        is_verified=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_token(user):
    return create_access_token({"sub": user.id, "phone": user.phone_number})


def test_conversation_creation_and_isolation(db):
    user_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    user_b = create_user(db, "FA-AS-00000002", "Farmer Suresh", "9123456780", "suresh@farm.com")
    user_c = create_user(db, "FA-AS-00000003", "Farmer Priya", "9333344444", "priya@farm.com")

    token_a = get_token(user_a)
    token_b = get_token(user_b)
    token_c = get_token(user_c)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    headers_c = {"Authorization": f"Bearer {token_c}"}

    # Farmer A creates conversation with Farmer B
    r = client.post("/api/v1/messages/conversations", headers=headers_a, json={"farmer_id": "FA-AS-00000002"})
    assert r.status_code == 201
    conv_id = r.json()["data"]["id"]

    # Farmer A sees conversation
    r_a = client.get("/api/v1/messages/conversations", headers=headers_a)
    assert r_a.status_code == 200
    assert len(r_a.json()["data"]["conversations"]) == 1

    # Farmer B sees conversation
    r_b = client.get("/api/v1/messages/conversations", headers=headers_b)
    assert r_b.status_code == 200
    assert len(r_b.json()["data"]["conversations"]) == 1

    # Farmer C does NOT see Farmer A-B conversation (Isolation)
    r_c = client.get("/api/v1/messages/conversations", headers=headers_c)
    assert r_c.status_code == 200
    assert len(r_c.json()["data"]["conversations"]) == 0


def test_send_and_read_messages(db):
    user_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    user_b = create_user(db, "FA-AS-00000002", "Farmer Suresh", "9123456780", "suresh@farm.com")
    user_c = create_user(db, "FA-AS-00000003", "Farmer Priya", "9333344444", "priya@farm.com")

    token_a = get_token(user_a)
    token_b = get_token(user_b)
    token_c = get_token(user_c)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    headers_c = {"Authorization": f"Bearer {token_c}"}

    # Create conv
    r = client.post("/api/v1/messages/conversations", headers=headers_a, json={"farmer_id": "FA-AS-00000002"})
    conv_id = r.json()["data"]["id"]

    # Farmer A sends message
    r_send = client.post(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_a, json={
        "content": "Hello Suresh, how is the wheat harvest going?",
        "message_type": "text"
    })
    assert r_send.status_code == 201

    # Farmer B checks unread count
    r_unread = client.get("/api/v1/messages/unread-count", headers=headers_b)
    assert r_unread.status_code == 200
    assert r_unread.json()["data"]["unread_count"] == 1

    # Farmer B reads messages
    r_msgs = client.get(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_b)
    assert r_msgs.status_code == 200
    assert len(r_msgs.json()["data"]["messages"]) == 1

    # Farmer B marks as read
    r_read = client.put(f"/api/v1/messages/conversations/{conv_id}/read", headers=headers_b)
    assert r_read.status_code == 200

    # Unread count now 0
    r_unread2 = client.get("/api/v1/messages/unread-count", headers=headers_b)
    assert r_unread2.json()["data"]["unread_count"] == 0

    # Farmer C cannot access conversation messages (Forbidden)
    r_unauth = client.get(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_c)
    assert r_unauth.status_code == 403


def test_delivered_then_read_status_flow(db):
    user_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    user_b = create_user(db, "FA-AS-00000002", "Farmer Suresh", "9123456780", "suresh@farm.com")
    headers_a = {"Authorization": f"Bearer {get_token(user_a)}"}
    headers_b = {"Authorization": f"Bearer {get_token(user_b)}"}

    r = client.post("/api/v1/messages/conversations", headers=headers_a, json={"farmer_id": "FA-AS-00000002"})
    conv_id = r.json()["data"]["id"]

    # Farmer A sends -> status is "sent" in the send response
    r = client.post(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_a, json={
        "content": "Check the paddy field status",
        "message_type": "text"
    })
    assert r.status_code == 201
    assert r.json()["data"]["status"] == "sent"
    msg_id = r.json()["data"]["id"]
    assert r.json()["data"]["delivered_at"] is None

    # Farmer A (sender) listing does NOT advance the status
    r = client.get(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_a)
    assert r.json()["data"]["messages"][0]["status"] == "sent"

    # Farmer B (recipient) lists -> delivered + delivered_at set
    r = client.get(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_b)
    m = r.json()["data"]["messages"][0]
    assert m["status"] == "delivered"
    assert m["delivered_at"] is not None

    # Farmer B opens conversation -> read + read_at set
    r = client.put(f"/api/v1/messages/conversations/{conv_id}/read", headers=headers_b)
    assert r.status_code == 200
    r = client.get(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_b)
    m = r.json()["data"]["messages"][0]
    assert m["status"] == "read"
    assert m["read_at"] is not None

    # Sender sees delivered/read regardless of listing order
    r = client.get(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_a)
    assert r.json()["data"]["messages"][0]["status"] == "read"


def test_user_search(db):
    user_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    user_b = create_user(db, "FA-AS-00000002", "Farmer Suresh", "9123456780", "suresh@farm.com")
    token_a = get_token(user_a)
    headers = {"Authorization": f"Bearer {token_a}"}

    # Search by name
    r = client.get("/api/v1/messages/users/search?q=Suresh", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["data"]["users"]) == 1
    assert r.json()["data"]["users"][0]["full_name"] == "Farmer Suresh"

    # Search by 10-digit phone
    r = client.get("/api/v1/messages/users/search?q=9123456780", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["data"]["users"]) == 1

    # Search by Farmer ID
    r = client.get("/api/v1/messages/users/search?q=FA-AS-00000002", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["data"]["users"]) == 1
