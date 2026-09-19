"""
Database Seeder for the Crop Catalogue.

Seeds the shared crop catalog (Rice, Wheat, Maize, etc.) used by the My Farm
page's "Add Crop" flow and the crop-cycles API. The seeder is idempotent and
additive: existing crops are left untouched (so live crop-cycles keep their
foreign keys), only missing catalogue entries are inserted.
"""

from sqlalchemy.orm import Session
from app.models.crop import Crop

# (crop_id, name, variety, category, season, growth_duration_days)
CATALOG = [
    ("CROP-001", "Paddy (Rice)", "BPT 5204", "Cereal", "Kharif", 120),
    ("CROP-002", "Wheat", "HD 3086", "Cereal", "Rabi", 115),
    ("CROP-003", "Maize", "NK 6240", "Cereal", "Kharif", 90),
    ("CROP-004", "Cotton", "Bt Hybrid", "Cash Crop", "Kharif", 160),
    ("CROP-005", "Sugarcane", "Co 86032", "Cash Crop", "Kharif", 360),
    ("CROP-006", "Groundnut", "K-6", "Oilseed", "Kharif", 105),
    ("CROP-007", "Soybean", "JS 9560", "Oilseed", "Kharif", 100),
    ("CROP-008", "Chickpea", "Desi JG 11", "Pulse", "Rabi", 100),
    ("CROP-009", "Green Gram", "IPM 02-03", "Pulse", "Kharif", 65),
    ("CROP-010", "Tomato", "Hybrid 70", "Vegetable", "Rabi", 75),
    ("CROP-011", "Chilli", "Teja", "Vegetable", "Kharif", 90),
    ("CROP-012", "Onion", "Nasik Red", "Vegetable", "Rabi", 110),
    ("CROP-013", "Potato", "Kufri Bahar", "Vegetable", "Rabi", 90),
    ("CROP-014", "Brinjal", "Arka Kusumakar", "Vegetable", "Kharif", 80),
    ("CROP-015", "Okra (Ladies Finger)", "Arka Anamika", "Vegetable", "Kharif", 60),
    ("CROP-016", "Cabbage", "Golden Acre", "Vegetable", "Rabi", 90),
    ("CROP-017", "Sunflower", "KBSH-44", "Oilseed", "Kharif", 90),
    ("CROP-018", "Mustard", "Pusa Bold", "Oilseed", "Rabi", 100),
]


def seed_crops(db: Session):
    added = 0
    for crop_id, name, variety, category, season, duration in CATALOG:
        existing = db.query(Crop).filter(Crop.crop_id == crop_id).first()
        if existing:
            continue
        db.add(Crop(
            crop_id=crop_id,
            name=name,
            variety=variety,
            category=category,
            season=season,
            growth_duration_days=duration,
        ))
        added += 1
    if added:
        db.commit()
        print(f"Crop catalogue seeded: {added} crops added (total {db.query(Crop).count()}).")
    return added


if __name__ == "__main__":
    import app.models  # noqa: F401  (register all ORM models)
    from app.routers.sensors import Sensor, SensorReading  # noqa: F401
    from app.database.connection import SessionLocal

    db = SessionLocal()
    try:
        res = seed_crops(db)
        print(f"Seeded crops: {res} new (total {db.query(Crop).count()}).")
    finally:
        db.close()