import os
import sys

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_documents_vault.db"
os.environ.setdefault("STORAGE_LOCAL_PATH", "test_documents_uploads")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database.connection import Base, SessionLocal, engine
from app.main import app
from app.models.user import User
from app.utils.auth import create_access_token, hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def make_user(session, suffix):
    user = User(
        farmer_id=f"FA-DOC-{suffix:07d}", full_name=f"Document Farmer {suffix}",
        phone_number=f"91000{suffix:05d}", email=f"document{suffix}@example.test",
        password_hash=hash_password("pass123"), is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def auth(user):
    return {"Authorization": "Bearer " + create_access_token({"sub": user.id, "phone": user.phone_number})}


def test_document_vault_persists_and_enforces_ownership():
    session = SessionLocal()
    try:
        owner, other = make_user(session, 1), make_user(session, 2)
        upload = client.post(
            "/api/v1/documents/upload",
            headers=auth(owner),
            files={"file": ("land-record.pdf", b"%PDF-1.4\nFarm Assist document", "application/pdf")},
            data={"document_category": "Land Documents", "description": "Owned by the first farmer"},
        )
        assert upload.status_code == 201
        doc_id = upload.json()["data"]["id"]

        listed = client.get("/api/v1/documents", headers=auth(owner))
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["data"]["items"]] == [doc_id]

        assert client.get(f"/api/v1/documents/{doc_id}/file", headers=auth(other)).status_code == 404
        served = client.get(f"/api/v1/documents/{doc_id}/file", headers=auth(owner))
        assert served.status_code == 200
        assert served.content.startswith(b"%PDF-")

        assert client.delete(f"/api/v1/documents/{doc_id}", headers=auth(owner)).status_code == 200
        assert client.get("/api/v1/documents", headers=auth(owner)).json()["data"]["items"] == []
        assert settings.STORAGE_MAX_FILE_SIZE_MB == 25
    finally:
        session.close()
