import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./scratch_input_store.db")
from app.database.connection import Base, SessionLocal, engine
from app.models.user import User
from app.utils.auth import hash_password
Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    if not db.query(User).first():
        db.add(User(farmer_id="FA-DEMO-1", full_name="Farm Assist Demo", phone_number="9000000000",
                    email="demo@farmassist.test", password_hash=hash_password("demo123"),
                    role="farmer", is_active=True, is_demo=True))
        db.commit()
        print("demo user created")
finally:
    db.close()
from app.database.seed_input_store import seed
db = SessionLocal()
try:
    result = seed(db)
    print("Products:", result["products"], "Categories:", result["categories"])
    for slug, count in result["per_category"].items():
        print(f"  {slug:>20}: {count}")
finally:
    db.close()
