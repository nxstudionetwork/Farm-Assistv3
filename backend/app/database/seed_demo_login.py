"""Guarantee the documented demo login account exists.

Idempotent: only creates the user when no active user with that phone exists.
This runs on every startup (local SQLite and hosted PostgreSQL) so the README
credentials always work even after a fresh database is provisioned.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user import User, FarmerProfile
from app.utils.auth import hash_password, generate_farmer_id, phone_lookup_candidates

DEMO_LOGIN_PHONE = "9876543210"
DEMO_LOGIN_PIN = "1234"
DEMO_LOGIN_NAME = "Rajesh Kumar"
DEMO_LOGIN_EMAIL = "rajesh@farmassist.com"


def ensure_demo_login_user(db: Session) -> dict:
    existing = (
        db.query(User)
        .filter(User.phone_number.in_(phone_lookup_candidates(DEMO_LOGIN_PHONE)))
        .first()
    )
    if existing:
        return {"status": "exists", "user_id": existing.id, "phone": existing.phone_number}

    farmer_id = generate_farmer_id(db)
    user = User(
        farmer_id=farmer_id,
        full_name=DEMO_LOGIN_NAME,
        phone_number=DEMO_LOGIN_PHONE,
        email=DEMO_LOGIN_EMAIL,
        password_hash=hash_password(DEMO_LOGIN_PIN),
        preferred_language="en",
        role="farmer",
        is_verified=True,
        is_active=True,
        is_demo=False,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()

    profile_exists = (
        db.query(FarmerProfile.id).filter(FarmerProfile.user_id == user.id).first()
    )
    if not profile_exists:
        db.add(FarmerProfile(
            user_id=user.id,
            farmer_id=farmer_id,
            occupation="Farmer",
            farming_experience="10+ years",
            preferred_crops="Rice,Wheat,Cotton,Chilli",
            farm_location="Nalgonda, Telangana",
        ))
    db.commit()
    return {
        "status": "created",
        "user_id": user.id,
        "farmer_id": farmer_id,
        "phone": user.phone_number,
        "pin": DEMO_LOGIN_PIN,
    }