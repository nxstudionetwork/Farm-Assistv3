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


def test_complete_e2e_messages_lifecycle(db):
    # 1. Setup Farmers
    farmer_a = create_user(db, "FA-AS-00000001", "Farmer Ramesh", "9876543210", "ramesh@farm.com")
    farmer_b = create_user(db, "FA-AS-00000002", "Farmer Suresh", "9123456780", "suresh@farm.com")
    farmer_c = create_user(db, "FA-AS-00000003", "Farmer Priya", "9333344444", "priya@farm.com")

    headers_a = {"Authorization": f"Bearer {get_token(farmer_a)}"}
    headers_b = {"Authorization": f"Bearer {get_token(farmer_b)}"}
    headers_c = {"Authorization": f"Bearer {get_token(farmer_c)}"}

    # 2. Search Farmers (Farm ID, Phone, Name)
    # Search by Farm ID
    r_search_fid = client.get("/api/v1/messages/users/search?q=FA-AS-00000002", headers=headers_a)
    assert r_search_fid.status_code == 200
    assert len(r_search_fid.json()["data"]["users"]) == 1
    assert r_search_fid.json()["data"]["users"][0]["full_name"] == "Farmer Suresh"

    # Search by 10-digit Phone
    r_search_ph = client.get("/api/v1/messages/users/search?q=9123456780", headers=headers_a)
    assert r_search_ph.status_code == 200
    assert len(r_search_ph.json()["data"]["users"]) == 1

    # Search by Name
    r_search_nm = client.get("/api/v1/messages/users/search?q=Suresh", headers=headers_a)
    assert r_search_nm.status_code == 200
    assert len(r_search_nm.json()["data"]["users"]) == 1

    # 3. Create Conversation between Farmer A and Farmer B
    r_conv = client.post("/api/v1/messages/conversations", headers=headers_a, json={"farmer_id": "FA-AS-00000002"})
    assert r_conv.status_code == 201
    conv_id = r_conv.json()["data"]["id"]

    # 4. Verification of Isolation: Farmer C has 0 conversations
    r_conv_c = client.get("/api/v1/messages/conversations", headers=headers_c)
    assert r_conv_c.status_code == 200
    assert len(r_conv_c.json()["data"]["conversations"]) == 0

    # 5. Farmer A sends message to Farmer B
    r_msg1 = client.post(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_a, json={
        "content": "Hello Suresh, check the wheat crop disease photo.",
        "message_type": "text"
    })
    assert r_msg1.status_code == 201
    msg1_id = r_msg1.json()["data"]["id"]
    assert r_msg1.json()["data"]["status"] == "sent"

    # 6. Farmer B checks unread count & reads conversation
    r_unread_b = client.get("/api/v1/messages/unread-count", headers=headers_b)
    assert r_unread_b.status_code == 200
    assert r_unread_b.json()["data"]["unread_count"] == 1

    # Farmer B marks as read
    r_read_b = client.put(f"/api/v1/messages/conversations/{conv_id}/read", headers=headers_b)
    assert r_read_b.status_code == 200

    r_unread_b_after = client.get("/api/v1/messages/unread-count", headers=headers_b)
    assert r_unread_b_after.json()["data"]["unread_count"] == 0

    # 7. Emoji Reaction
    r_react = client.post(f"/api/v1/messages/conversations/{conv_id}/messages/{msg1_id}/reactions", headers=headers_b, json={
        "emoji": "👍"
    })
    assert r_react.status_code == 201

    # 8. Mute conversation
    r_mute = client.put(f"/api/v1/messages/conversations/{conv_id}/mute", headers=headers_b)
    assert r_mute.status_code == 200
    assert r_mute.json()["data"]["muted"] is True

    # 9. Farmer B marks conversation as unread manually
    r_unread_toggle = client.put(f"/api/v1/messages/conversations/{conv_id}/unread", headers=headers_b)
    assert r_unread_toggle.status_code == 200

    # 10. Presence
    r_online = client.post("/api/v1/messages/presence/online", headers=headers_a)
    assert r_online.status_code == 200
    r_pres = client.get(f"/api/v1/messages/presence/{farmer_a.id}", headers=headers_b)
    assert r_pres.status_code == 200
    assert r_pres.json()["data"]["is_online"] is True

    # 11. Security Check: Farmer C unauthorized access blocked
    r_unauth_msgs = client.get(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_c)
    assert r_unauth_msgs.status_code == 403

    r_unauth_send = client.post(f"/api/v1/messages/conversations/{conv_id}/messages", headers=headers_c, json={
        "content": "Intruder message",
        "message_type": "text"
    })
    assert r_unauth_send.status_code == 403

    # 12. Delete message
    r_del_msg = client.delete(f"/api/v1/messages/conversations/{conv_id}/messages/{msg1_id}", headers=headers_a)
    assert r_del_msg.status_code == 200

    # 13. Delete conversation
    r_del_conv = client.delete(f"/api/v1/messages/conversations/{conv_id}", headers=headers_a)
    assert r_del_conv.status_code == 200
