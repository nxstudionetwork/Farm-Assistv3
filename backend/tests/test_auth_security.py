"""
Security regression tests for authentication, OTP handling and identity data.

These cover the failures that were previously unguarded and therefore silently
permitted:

* an OTP being echoed back to the client in a non-development environment,
* OTP issuance reporting success when no provider could actually deliver,
* unbounded resend and verify attempts,
* cleartext Aadhaar/PAN leaving the API,
* government identity being accepted without recorded consent,
* logout leaving the bearer token usable.

Run with:  pytest tests/test_auth_security.py
"""

import os
import sys

if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///./test_auth_security.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.config import settings
from app.database.connection import Base, SessionLocal, engine
from app.main import app
from app.models.user import OTPVerification, User, UserSession
from app.services import otp_service
from app.utils.auth import create_access_token, hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def production_like(monkeypatch):
    """
    Default every test to a production-shaped configuration with no delivery
    provider, so any accidental leak fails loudly. Individual tests opt in to a
    provider or to the development escape hatch explicitly.
    """
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "OTP_DEV_ECHO_ENABLED", False)
    monkeypatch.setattr(settings, "OTP_REQUIRE_DELIVERY", True)
    monkeypatch.setattr(settings, "SMS_PROVIDER_ENABLED", False)
    monkeypatch.setattr(settings, "SMS_API_KEY", "")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER_ENABLED", False)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 45)
    monkeypatch.setattr(settings, "OTP_MAX_SENDS_PER_HOUR", 5)
    monkeypatch.setattr(settings, "OTP_MAX_VERIFY_ATTEMPTS", 5)
    monkeypatch.setattr(settings, "OTP_TTL_SECONDS", 600)


@pytest.fixture
def phone_with_provider(monkeypatch):
    """A phone channel that reports a successful provider delivery."""
    monkeypatch.setattr(settings, "SMS_PROVIDER_ENABLED", True)
    monkeypatch.setattr(settings, "SMS_API_KEY", "test-key")
    monkeypatch.setattr(otp_service, "_deliver", lambda channel, destination, code: True)
    return "9876543210"


def make_user(session, suffix, **kwargs):
    user = User(
        farmer_id=f"FA-AS-{suffix:08d}",
        full_name=f"Security Farmer {suffix}",
        phone_number=f"98{str(suffix).zfill(8)}",
        email=f"security{suffix}@example.test",
        password_hash=hash_password("1234"),
        is_active=True,
        **kwargs,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def auth(user):
    return {"Authorization": "Bearer " + create_access_token({"sub": user.id, "phone": user.phone_number})}


# --------------------------------------------------------------------------
# OTP secrecy
# --------------------------------------------------------------------------

def test_otp_is_not_echoed_in_production(phone_with_provider):
    response = client.post("/api/v1/auth/send-otp", json={"phone_number": phone_with_provider})
    assert response.status_code == 200
    body = response.json()
    assert "debug_otp" not in body, "OTP leaked to the client in production"
    assert "debug_mode" not in body
    assert body["channel"] == "phone"
    # The response may acknowledge where the code went, but only masked.
    assert phone_with_provider not in str(body)
    assert body["masked"] == "98****10"


def test_dev_echo_flag_alone_does_not_leak_in_production(monkeypatch):
    """A stray OTP_DEV_ECHO_ENABLED=true must not leak from a production deploy."""
    monkeypatch.setattr(settings, "OTP_DEV_ECHO_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    assert otp_service.dev_echo_allowed() is False
    response = client.post("/api/v1/auth/send-otp", json={"phone_number": "9876543211"})
    assert response.status_code == 503
    assert "debug_otp" not in response.text


def test_dev_echo_requires_development_environment(monkeypatch):
    for env in ("staging", "production", "prod", "qa"):
        monkeypatch.setattr(settings, "OTP_DEV_ECHO_ENABLED", True)
        monkeypatch.setattr(settings, "APP_ENV", env)
        assert otp_service.dev_echo_allowed() is False, f"leak possible in {env}"


def test_otp_uses_secrets_not_random():
    """The generator must not be switched to random by a careless edit."""
    codes = {otp_service.generate_otp_code() for _ in range(50)}
    assert all(c.isdigit() and len(c) == otp_service.OTP_DIGITS for c in codes)
    assert len(codes) > 1
    source = open(otp_service.__file__, encoding="utf-8").read()
    assert "import random" not in source, "otp_service must not use random"


def test_otp_plaintext_is_never_persisted(phone_with_provider):
    client.post("/api/v1/auth/send-otp", json={"phone_number": phone_with_provider})
    session = SessionLocal()
    try:
        record = session.query(OTPVerification).order_by(OTPVerification.created_at.desc()).first()
        assert record is not None
        assert record.otp_hash, "OTP must be stored as a hash"
        assert not record.otp_hash.isdigit(), "OTP appears to be stored in plaintext"
    finally:
        session.close()


# --------------------------------------------------------------------------
# OTP fails closed and is rate limited
# --------------------------------------------------------------------------

def test_otp_send_fails_closed_without_a_provider():
    response = client.post("/api/v1/auth/send-otp", json={"phone_number": "9876543212"})
    assert response.status_code == 503
    assert "debug_otp" not in response.text
    # Nothing should have been stored, since it could never be delivered.
    session = SessionLocal()
    try:
        assert session.query(OTPVerification).count() == 0
    finally:
        session.close()


def test_otp_resend_is_rate_limited(phone_with_provider):
    first = client.post("/api/v1/auth/send-otp", json={"phone_number": phone_with_provider})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/send-otp", json={"phone_number": phone_with_provider})
    assert second.status_code == 429


def test_otp_hourly_send_cap(phone_with_provider, monkeypatch):
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr(settings, "OTP_MAX_SENDS_PER_HOUR", 3)
    codes = []
    for _ in range(3):
        assert client.post("/api/v1/auth/send-otp", json={"phone_number": phone_with_provider}).status_code == 200
    assert client.post("/api/v1/auth/send-otp", json={"phone_number": phone_with_provider}).status_code == 429


def test_otp_verify_attempts_are_capped(phone_with_provider, monkeypatch):
    monkeypatch.setattr(settings, "OTP_MAX_VERIFY_ATTEMPTS", 3)
    sent = client.post("/api/v1/auth/send-otp", json={"phone_number": phone_with_provider})
    code = otp_service.generate_otp_code()  # not the real code; used to burn attempts

    for _ in range(3):
        response = client.post(
            "/api/v1/auth/verify-otp",
            json={"phone_number": phone_with_provider, "otp_code": code},
        )
        assert response.status_code in (400, 401, 429)

    # The cap must now refuse with a rate-limit style error rather than 400 forever.
    final = client.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone_with_provider, "otp_code": code},
    )
    assert final.status_code == 429
    assert sent.status_code == 200


def test_expired_otp_is_rejected(phone_with_provider, monkeypatch):
    monkeypatch.setattr(settings, "OTP_DEV_ECHO_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "development")
    sent = client.post("/api/v1/auth/send-otp", json={"phone_number": phone_with_provider})
    code = sent.json()["debug_otp"]

    session = SessionLocal()
    try:
        record = session.query(OTPVerification).order_by(OTPVerification.created_at.desc()).first()
        record.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone_with_provider, "otp_code": code},
    )
    assert response.status_code in (400, 401)


def test_wrong_otp_message_does_not_confirm_existence(phone_with_provider):
    client.post("/api/v1/auth/send-otp", json={"phone_number": phone_with_provider})
    response = client.post(
        "/api/v1/auth/verify-otp",
        json={"phone_number": phone_with_provider, "otp_code": "000000"},
    )
    assert response.status_code in (400, 401)
    # The message must be identical whether or not a code was ever sent, so it
    # cannot be used to enumerate registered numbers.
    assert "expired" in response.json()["detail"].lower()


# --------------------------------------------------------------------------
# Identity data handling
# --------------------------------------------------------------------------

def _register(client, **overrides):
    payload = {
        "full_name": "Consent Farmer",
        "phone_number": "9812345678",
        "pin": "1234",
        "email": "consent@example.test",
    }
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def test_register_rejects_identity_without_consent():
    response = _register(client, aadhaar_number="123456789012")
    assert response.status_code == 400
    assert "consent" in response.json()["detail"].lower()


def test_register_accepts_identity_with_consent_and_marks_it_pending():
    response = _register(
        client,
        aadhaar_number="123456789012",
        identity_consent_given=True,
        identity_consent_version="v1",
    )
    assert response.status_code == 201, response.text

    session = SessionLocal()
    try:
        from app.models.user import FarmerProfile
        profile = session.query(FarmerProfile).order_by(FarmerProfile.created_at.desc()).first()
        assert profile.aadhaar_last4 == "9012"
        # Self-declared and format-checked only: it must not claim to be verified.
        assert profile.aadhaar_verification_status == "pending"
        assert profile.identity_verification_status == "pending"
        user = session.query(User).filter(User.id == profile.user_id).first()
        assert user.identity_consent_given is True
        assert user.identity_consent_at is not None
    finally:
        session.close()


def test_register_response_does_not_echo_aadhaar_or_pan():
    response = _register(
        client,
        aadhaar_number="123456789012",
        pan_number="ABCDE1234F",
        identity_consent_given=True,
    )
    assert response.status_code == 201, response.text
    text = response.text
    assert "123456789012" not in text, "full Aadhaar returned to the client"
    assert "ABCDE1234F" not in text, "full PAN returned to the client"
    assert "aadhaar_number" not in text
    assert "pan_number" not in text


def test_profile_endpoint_never_returns_raw_identity():
    session = SessionLocal()
    try:
        from app.models.user import FarmerProfile
        user = make_user(session, 4242)
        session.add(FarmerProfile(
            user_id=user.id,
            farmer_id=user.farmer_id,
            aadhaar_number="123456789012",
            aadhaar_last4="9012",
            aadhaar_verification_status="pending",
            pan_number="ABCDE1234F",
            pan_last4="1234F"[-4:],
            pan_verification_status="pending",
            farmer_card_number="AP-2024-99887766",
            farmer_card_last4="7766",
            farmer_card_verification_status="pending",
        ))
        session.commit()
        user_id = user.id
    finally:
        session.close()

    response = client.get("/api/v1/users/profile", headers=auth(_reload(user_id)))
    assert response.status_code == 200
    text = response.text
    assert "123456789012" not in text, "profile endpoint leaked full Aadhaar"
    assert "ABCDE1234F" not in text, "profile endpoint leaked full PAN"
    assert "AP-2024-99887766" not in text, "profile endpoint leaked full farmer card"
    assert "aadhaar_number" not in text
    assert "pan_number" not in text
    assert "farmer_card_number" not in text
    # Masked values and honest statuses are still available to the UI.
    assert "aadhaar_masked" in text
    assert "9012" in text


def _reload(user_id):
    session = SessionLocal()
    try:
        return session.query(User).filter(User.id == user_id).first()
    finally:
        session.close()


def test_changing_aadhaar_resets_verification_status():
    session = SessionLocal()
    try:
        from app.models.user import FarmerProfile
        user = make_user(session, 4343)
        profile = FarmerProfile(
            user_id=user.id, farmer_id=user.farmer_id,
            aadhaar_number="111111111111", aadhaar_last4="1111",
            aadhaar_verification_status="verified", identity_verification_status="verified",
        )
        session.add(profile)
        session.commit()
        user_id = user.id
    finally:
        session.close()

    response = client.put(
        "/api/v1/users/profile",
        headers=auth(_reload(user_id)),
        json={"aadhaar_number": "222222222222"},
    )
    assert response.status_code == 200, response.text
    session = SessionLocal()
    try:
        profile = session.query(FarmerProfile).filter(FarmerProfile.user_id == user_id).first()
        assert profile.aadhaar_last4 == "2222"
        assert profile.aadhaar_verification_status == "pending"
        assert profile.identity_verification_status == "pending"
    finally:
        session.close()


# --------------------------------------------------------------------------
# Session lifecycle
# --------------------------------------------------------------------------

def test_logout_revokes_the_bearer_token():
    session = SessionLocal()
    try:
        user = make_user(session, 5150)
        user_id = user.id
        phone = user.phone_number
    finally:
        session.close()

    login = client.post(
        "/api/v1/auth/login",
        json={"phone_number": phone, "pin": "1234"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert logout.json()["token_revoked"] is True

    # The credential must be dead immediately, not merely hidden by the client.
    after = client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401, "token still usable after logout"


def test_login_records_a_revocable_session():
    session = SessionLocal()
    try:
        user = make_user(session, 5252)
        user_id, phone = user.id, user.phone_number
    finally:
        session.close()

    login = client.post("/api/v1/auth/login", json={"phone_number": phone, "pin": "1234"})
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]

    session = SessionLocal()
    try:
        assert session.query(UserSession).filter(UserSession.user_id == user_id).count() == 1
        stored = session.query(UserSession).filter(UserSession.user_id == user_id).first()
        assert stored.revoked_at is None
    finally:
        session.close()
    assert token


def test_legacy_token_without_a_session_still_works():
    """Tokens issued before session tracking existed must not all break."""
    session = SessionLocal()
    try:
        user = make_user(session, 5353)
        user_id = user.id
    finally:
        session.close()
    response = client.get("/api/v1/auth/me", headers=auth(_reload(user_id)))
    assert response.status_code == 200


# --------------------------------------------------------------------------
# Farmer ID allocation
# --------------------------------------------------------------------------

def test_farmer_id_allocation_is_monotonic_and_ignores_other_formats():
    from app.utils.auth import generate_farmer_id
    session = SessionLocal()
    try:
        for farmer_id in ("FA-AS-00000003", "FA-AS-00000009", "LEGACY-0001"):
            session.add(User(
                farmer_id=farmer_id, full_name="x", phone_number="9" + farmer_id[-8:].ljust(8, "0")[:8],
                password_hash="x",
            ))
        session.flush()
        assert generate_farmer_id(session) == "FA-AS-00000010"
    finally:
        session.rollback()
        session.close()


def test_farmer_id_uses_numeric_not_lexicographic_ordering():
    """'FA-AS-100000000' must sort above 'FA-AS-99999999' numerically."""
    from app.utils.auth import generate_farmer_id
    session = SessionLocal()
    try:
        session.add(User(farmer_id="FA-AS-09999999", full_name="x", phone_number="9700000001", password_hash="x"))
        session.add(User(farmer_id="FA-AS-100000000", full_name="x", phone_number="9700000002", password_hash="x"))
        session.flush()
        assert generate_farmer_id(session) == "FA-AS-100000001"
    finally:
        session.rollback()
        session.close()
