"""Seed agricultural Workers catalogue (Workers page).

Adds realistic worker profiles so the Workers page never shows an empty
catalogue. Idempotent: only inserts until the workers table reaches at
least MIN_WORKERS rows.
"""

import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.database.connection import SessionLocal, engine, Base
from app.models.worker import Worker
from app.models.farm import Farm
from app.utils.auth import generate_id

MIN_WORKERS = 90

FIRST_NAMES = [
    "Ramesh", "Suresh", "Mahesh", "Rajesh", "Vijay", "Arjun", "Dinesh", "Sanjay",
    "Manoj", "Sunil", "Prakash", "Anil", "Naresh", "Karthik", "Ganesh", "Mohan",
    "Devraj", "Ravi", "Shankar", "Laxman", "Bhaskar", "Umesh", "Kiran", "Rajkumar",
    "Srinivas", "Venkatesh", "Harish", "Nagaraj", "Basavaraj", "Guruprasad",
    "Subhash", "Deepak", "Pramod", "Anand", "Krishna", "Murugan", "Selvam",
    "Arumugam", "Rajaraman", "Velayudham", "Bhupinder", "Gurpreet", "Harpreet",
    "Jaspreet", "Balwinder", "Raghunath", "Surya", "Tejas", "Yash", "Aakash",
]
LAST_NAMES = [
    "Kumar", "Patel", "Yadav", "Singh", "Reddy", "Naik", "Choudhary", "Gupta",
    "Gowda", "Patil", "Deshmukh", "Kulkarni", "Krishnan", "Iyer", "Menon", "Pillai",
    "Thakur", "Jha", "Mishra", "Pandey", "Sahu", "Rathod", "Solanki", "Bhandari",
    "Raut", "Gaikwad", "Sawant", "Kadam", "Zade", "Chavan", "Jadhav", "More",
    "Shelke", "Gavali", "Shinde", "Mali", "Nikam", "Pawar", "Tamboli", "Maratha",
    "Randhawa", "Saini", "Gill", "Duggal", "Verma", "Bose", "Das", "Mondal",
]
WOMEN_FIRST = [
    "Anitha", "Lakshmi", "Sunita", "Geetha", "Pooja", "Rekha", "Savita", "Meena",
    "Kavita", "Deepa", "Shalini", "Radhika", "Mangala", "Kamala", "Saraswati",
    "Shanti", "Rani", "Leela", "Janaki", "Uma",
]
WOMEN_LAST = [
    "Ramesh", "Devi", "Kamble", "Rao", "Kumari", "Patil", "Jadhav", "Sharma",
    "Nair", "Pawar", "Gaikwad", "Shetty", "Kulkarni", "Mishra", "Bose",
]

SKILL_POOL = [
    "Harvesting", "Threshing", "Sowing", "Seed Drilling", "Plowing",
    "Tractor Driving", "Tilling", "Rotavating", "Weeding", "Hoeing",
    "Mulching", "Irrigation", "Drip Irrigation Setup", "Sprinkler Installation",
    "Water Management", "Pesticide Spraying", "Fertilizer Application",
    "Fencing", "Cattle Care", "General Farm Work", "Orchard Maintenance",
    "Greenhouse Management", "Mango Harvesting", "Vineyard Care",
]

SKILL_WORK_GROUPS = [
    ["Harvesting", "Threshing", "General Farm Work"],
    ["Sowing", "Seed Drilling", "Weeding"],
    ["Plowing", "Tractor Driving", "Tilling", "Rotavating"],
    ["Irrigation", "Drip Irrigation Setup", "Sprinkler Installation", "Water Management"],
    ["Pesticide Spraying", "Fertilizer Application", "Weeding"],
    ["Fencing", "Cattle Care", "General Farm Work"],
    ["Orchard Maintenance", "Mango Harvesting", "Harvesting"],
    ["Greenhouse Management", "Irrigation", "Fertilizer Application"],
    ["Vineyard Care", "Weeding", "Pesticide Spraying"],
]

BIOS = [
    "Hardworking farm hand with years of field experience across crops. Reliable and available on call.",
    "Skilled in modern farming techniques, comfortable operating tractors and tillers for small and large fields.",
    "Specialised in irrigation systems including drip and sprinkler setup for water-efficient farming.",
    "Experienced in quick, careful harvesting and post-harvest handling to protect crop quality.",
    "Trusted local worker offering sowing, weeding and general farm maintenance throughout the season.",
    "Motivated worker focused on pesticide and fertiliser application with proper safety measures.",
    "Multi-skilled farm worker for fencing, livestock care and daily farm chores.",
    "Detail-oriented orchard and vineyard specialist with pruning and picking experience.",
]


def _pick(pool, seed):
    return pool[seed % len(pool)]


def seed_workers(db, min_workers=MIN_WORKERS):
    existing = db.query(Worker).count()
    if existing >= min_workers:
        return {"workers_seeded": 0, "total_workers": existing}

    locations = db.query(Farm.village, Farm.district, Farm.state).filter(
        Farm.is_active == True
    ).distinct().all()
    loc_pool = [(v or "", d or "", s or "") for v, d, s in locations]
    if not loc_pool:
        loc_pool = [("Kothur", "Rangareddy", "Telangana")]

    all_names = (
        [f + " " + l for f in FIRST_NAMES for l in sorted(LAST_NAMES)]
        + [f + " " + l for f in WOMEN_FIRST for l in sorted(WOMEN_LAST)]
    )

    worker_id_base = db.query(Worker).count() + 1
    added = 0
    while db.query(Worker).count() < min_workers:
        name = all_names[(worker_id_base + added) % len(all_names)]
        wm = _pick(WOMEN_FIRST, added) if added % 5 == 4 else None
        if wm:
            name = wm + " " + _pick(WOMEN_LAST, added)
        skills = sorted(SKILL_WORK_GROUPS[added % len(SKILL_WORK_GROUPS)] + [SKILL_POOL[(added * 3) % len(SKILL_POOL)]])
        village, district, state = loc_pool[added % len(loc_pool)]
        w = Worker(
            worker_id=generate_id("FA-WRK", db, Worker),
            full_name=name,
            phone_number=f"9{100000000 + (worker_id_base + added) * 999983 % 9000000000}",
            village=village or _pick(FIRST_NAMES, added) + "palli",
            district=district or _pick(LAST_NAMES, added),
            state=state or "Telangana",
            latitude=round(16.5 + (added % 10) * 0.7, 4),
            longitude=round(78.0 + (added % 9) * 0.5, 4),
            skills=skills,
            experience_years=float(1 + ((added * 7) % 22)),
            hourly_rate=float(60 + ((added * 5) % 80)),
            daily_rate=float(420 + ((added * 37) % 700)),
            rating=round(3.6 + ((added * 13) % 15) / 10.0, 1),
            total_reviews=int((added * 7) % 41),
            is_verified=added % 4 != 0,
            is_available=added % 7 != 3,
            bio=BIOS[added % len(BIOS)],
        )
        db.add(w)
        db.flush()
        added += 1

    db.commit()
    return {"workers_seeded": added, "total_workers": db.query(Worker).count()}


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        res = seed_workers(db)
        print("Workers seed complete:")
        print(f"  Workers added: {res['workers_seeded']}")
        print(f"  Total workers: {res['total_workers']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()