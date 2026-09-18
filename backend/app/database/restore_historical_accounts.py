"""Restore the original Farm Assist farmer accounts.

These are the accounts that existed in the very first database snapshot
(git commit ``8300455``) before the demo-seed suite was introduced. They are
real accounts (verified, non-demo) and are restored idempotently on every
startup by their ``farmer_id`` so they survive a fresh/provisioned database.

Every restored account logs in with PIN ``1234`` via ``/auth/login``
(phone, email or farmer_id).

Note: the account with farmer id ``FA-AS-00000004`` (Harsha Vardhan) is
canonically stored under the explicit user id ``"4"``.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user import User, FarmerProfile
from app.utils.auth import hash_password

RESTORE_PIN = "1234"

# (farmer_id, id, full_name, phone_number, email)
# id/email may be None; when id is None the row is reused by farmer_id.
HISTORICAL_ACCOUNTS = [
    {
        "farmer_id": "FA-AS-00000002",
        "id": "a2fa7efe-5c12-4ea2-adab-42f0eb8463ae",
        "full_name": "Rajesh Kumar",
        "phone_number": "+919876543210",
        "email": "rajesh@farmassist.com",
    },
    {
        "farmer_id": "FA-AS-00000003",
        "id": "b18033e1-ef34-4d8e-b328-b9dd95a73133",
        "full_name": "Sai Kumar",
        "phone_number": "9800652324",
        "email": None,
    },
    {
        "farmer_id": "FA-AS-00000004",
        "id": "4",
        "full_name": "Harsha Vardhan",
        "phone_number": "6301268629",
        "email": "harsha@ahaicoe.org",
    },
    {
        "farmer_id": "FA-AS-00000005",
        "id": "ca07e881-215d-4203-885b-daf9366ae3c6",
        "full_name": "Smoke Test Farmer",
        "phone_number": "9000000099",
        "email": "smoke99@example.com",
    },
    {
        "farmer_id": "FA-AS-00000006",
        "id": "c342944a-27ce-4d3a-a8da-5c166b2a786c",
        "full_name": "NX Studio",
        "phone_number": "6301238629",
        "email": "nx.studio.network@gmail.com",
    },
    {
        "farmer_id": "FA-AS-00000007",
        "id": "c3f37da4-34e6-47a1-83de-7b6151903a48",
        "full_name": "Hemanth",
        "phone_number": "9886894948",
        "email": "hemanth@farmassist.io",
    },
]


def ensure_historical_accounts(db: Session) -> dict:
    restored = []
    for acc in HISTORICAL_ACCOUNTS:
        user = db.query(User).filter(User.farmer_id == acc["farmer_id"]).first()

        if not user and acc["id"]:
            user = db.query(User).filter(User.id == acc["id"]).first()

        if user:
            # Refresh any drifted fields on an existing row.
            user.farmer_id = acc["farmer_id"]
            user.full_name = acc["full_name"]
            if user.email != acc["email"] and not _email_taken(db, acc["email"], user.id):
                user.email = acc["email"]
            user.phone_number = acc["phone_number"]
            if not user.password_hash:
                user.password_hash = hash_password(RESTORE_PIN)
            user.is_verified = True
            user.is_active = True
            user.is_demo = False
            status = "updated"
        else:
            user = User(
                id=acc["id"],
                farmer_id=acc["farmer_id"],
                full_name=acc["full_name"],
                phone_number=acc["phone_number"],
                email=acc["email"],
                password_hash=hash_password(RESTORE_PIN),
                preferred_language="en",
                role="farmer",
                is_verified=True,
                is_active=True,
                is_demo=False,
                created_at=datetime.utcnow(),
            )
            db.add(user)
            db.flush()
            status = "created"

        profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == user.id).first()
        if not profile:
            db.add(FarmerProfile(
                user_id=user.id,
                farmer_id=acc["farmer_id"],
                occupation="Farmer",
            ))
        elif not profile.farmer_id:
            profile.farmer_id = acc["farmer_id"]

        db.commit()
        restored.append({"farmer_id": acc["farmer_id"], "status": status, "user_id": user.id})

    return {"status": "success", "pin": RESTORE_PIN, "accounts": restored}


def _email_taken(db: Session, email, exclude_user_id) -> bool:
    if not email:
        return False
    return (
        db.query(User.id)
        .filter(User.email == email, User.id != exclude_user_id)
        .first()
        is not None
    )