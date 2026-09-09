"""
Seeder for the Experts Hub catalog.

These are standing agriculture experts a farmer can discover and book on the
Experts Hub page. They are reference/demo profile data stored through the exact
same database model and API as any real expert -- never hardcoded in the
frontend. Ratings and consultation counts are seed-level values only; live
bookings and reviews recompute them through the normal backend flow.

Idempotent: an expert is inserted only when their FA-EXPT identifier is not
already present, and bio/languages are backfilled only when empty, so upgrading
an existing install never duplicates or overwrites existing experts.

Run standalone:  python -m app.database.seed_experts
"""

from sqlalchemy.orm import Session

from app.models.community import Expert

# (expert_id, full_name, speciality, qualification, experience_years, location,
#  consultation_fee, rating, total_consultations, is_available, languages, bio)
EXPERT_CATALOG = [
    ("FA-EXPT-000001", "Dr. Lakshmi Devi", "Crop Science", "PhD Agriculture", 15,
     "Hyderabad", 500, 4.8, 245, True, ["Telugu", "English"],
     "Agronomist specialising in high-yield paddy, maize and pulses for Telangana and Andhra farmers."),
    ("FA-EXPT-000002", "Dr. Venkateshwar Rao", "Soil Science", "PhD Soil Science", 20,
     "Warangal", 400, 4.6, 189, True, ["Telugu", "Hindi", "English"],
     "Soil scientist helping farmers test, amend and manage soil health for sustained yields."),
    ("FA-EXPT-000003", "Dr. Anitha Reddy", "Plant Protection", "PhD Entomology", 12,
     "Nalgonda", 600, 4.7, 312, True, ["Telugu", "English"],
     "Entomologist guiding integrated pest management for cotton, chilli and vegetables."),
    ("FA-EXPT-000004", "Prof. Srinivasa Rao", "Water Management", "PhD Irrigation Engineering", 18,
     "Karimnagar", 450, 4.5, 156, True, ["Telugu", "English"],
     "Irrigation specialist for drip, sprinkler and canal water scheduling under scarce water."),
    ("FA-EXPT-000005", "Dr. Kavitha Sharma", "Organic Farming", "MSc Organic Agriculture", 10,
     "Hyderabad", 350, 4.4, 203, True, ["Telugu", "Hindi", "English"],
     "Organic and natural farming practitioner supporting input-free, certified organic production."),
    ("FA-EXPT-000006", "Dr. Ramesh Kumar", "Agronomy", "MSc Agronomy", 14,
     "Kadapa", 450, 4.6, 178, True, ["Telugu", "English"],
     "Field agronomist advising on sowing windows, variety selection and nutrient scheduling."),
    ("FA-EXPT-000007", "Dr. Neelima Rao", "Plant Pathology", "PhD Plant Pathology", 16,
     "Hyderabad", 550, 4.7, 231, True, ["Telugu", "English"],
     "Plant pathologist diagnosing fungal, bacterial and viral diseases in field and horticultural crops."),
    ("FA-EXPT-000008", "Dr. Sudhakar Reddy", "Horticulture", "PhD Horticulture", 13,
     "Kurnool", 480, 4.5, 164, True, ["Telugu", "English"],
     "Horticulture expert for fruits, vegetables, spices and orchard management."),
    ("FA-EXPT-000009", "Dr. Jyothi Prasad", "Entomology", "PhD Entomology", 11,
     "Guntur", 500, 4.4, 142, True, ["Telugu", "English"],
     "Integrated pest management specialist with focus on cotton, vegetables and pulse crops."),
    ("FA-EXPT-000010", "Dr. Kiranmayi Rani", "Fertilizer & Plant Nutrition", "PhD Soil Chemistry", 15,
     "Vijayawada", 420, 4.6, 197, True, ["Telugu", "English"],
     "Plant nutrition advisor for balanced fertilisation, micronutrients and soil test-based dosing."),
    ("FA-EXPT-000011", "Dr. Naresh Goud", "Livestock Science", "MVSc Animal Science", 17,
     "Mahbubnagar", 550, 4.7, 214, True, ["Telugu", "Hindi", "English"],
     "Animal husbandry specialist covering cattle health, feeding, breeding and disease control."),
    ("FA-EXPT-000012", "Dr. Bharathi Devi", "Dairy Science", "MVSc Dairy Science", 12,
     "Nizamabad", 480, 4.5, 158, True, ["Telugu", "English"],
     "Dairy scientist helping improve milk yield, herd health and dairy farm economics."),
    ("FA-EXPT-000013", "Prof. Anil Deshmukh", "Agricultural Engineering", "MTech Agricultural Engineering", 16,
     "Hyderabad", 500, 4.6, 186, True, ["Hindi", "English"],
     "Farm machinery and engineering consultant for mechanisation, precision tools and ergonomics."),
    ("FA-EXPT-000014", "Dr. Sandeep Varma", "Farm Management", "MBA Agri Business", 12,
     "Warangal", 380, 4.4, 121, True, ["Telugu", "English"],
     "Farm manager helping plan cropping systems, budgets and profitable resource allocation."),
    ("FA-EXPT-000015", "Dr. Pradeep Sharma", "Agri Business & Marketing", "MBA Agri Marketing", 14,
     "Hyderabad", 420, 4.5, 167, True, ["Hindi", "English"],
     "Market linkage and agri-business advisor for FPOs, direct sales and value addition."),
    ("FA-EXPT-000016", "Dr. Meena Joshi", "Market & Pricing", "MSc Agricultural Economics", 11,
     "Vijayawada", 350, 4.3, 109, True, ["Telugu", "Hindi", "English"],
     "Agricultural economist tracking mandi prices, price trends and better selling timing."),
    ("FA-EXPT-000017", "Dr. Gopalakrishna", "Government Schemes & Policy", "PhD Agricultural Policy", 10,
     "Hyderabad", 300, 4.4, 133, True, ["Telugu", "English"],
     "Policy advisor on subsidy schemes, KCC, crop insurance and scheme documentation."),
    ("FA-EXPT-000018", "Dr. Uma Devi", "Organic Farming & Certification", "PhD Organic Agriculture", 9,
     "Medak", 380, 4.3, 98, True, ["Telugu", "English"],
     "Organic certification consultant guiding farmers through conversion and record keeping."),
    ("FA-EXPT-000019", "Dr. Venkat Nandan", "Crop Science & Seed Technology", "PhD Seed Science", 13,
     "Rajahmundry", 460, 4.5, 149, True, ["Telugu", "English"],
     "Seed technologist advising on certified seed, treatment, storage and replacement rates."),
    ("FA-EXPT-000020", "Dr. Lalitha Kumari", "Plant Breeding", "PhD Plant Breeding", 15,
     "Hyderabad", 500, 4.6, 175, True, ["Telugu", "English"],
     "Plant breeder supporting variety evaluation and seed selection for local conditions."),
    ("FA-EXPT-000021", "Dr. Murali Mohan", "Irrigation Engineering", "MTech Irrigation Engineering", 14,
     "Sangareddy", 440, 4.5, 116, False, ["Telugu", "English"],
     "Water infrastructure planner for canals, micro-irrigation and farm ponds. Currently on leave."),
    ("FA-EXPT-000022", "Dr. Swapna Reddy", "Soil Health & Microbes", "PhD Soil Microbiology", 12,
     "Karimnagar", 430, 4.4, 124, True, ["Telugu", "English"],
     "Soil microbiologist focused on biofertilizers, microbial consortia and soil rejuvenation."),
    ("FA-EXPT-000023", "Prof. Shravani Rao", "Agricultural Meteorology", "PhD Agricultural Meteorology", 12,
     "Hyderabad", 360, 4.2, 87, True, ["Telugu", "English"],
     "Agri-meteorologist helping plan sowing, spraying and harvest around seasonal forecasts."),
    ("FA-EXPT-000024", "Dr. Bhaskar Rao", "Apiculture & Bee Keeping", "PhD Entomology", 9,
     "Sangareddy", 0, 4.1, 73, True, ["Telugu", "Hindi", "English"],
     "Beekeeping and pollination specialist supporting apiary income and crop pollination."),
]


def seed_experts(db: Session) -> int:
    """Create expert catalog entries that are not already present.

    Backfills bio/languages on older rows but never overwrites newer values.
    Returns the number of rows added.
    """
    ids = [e[0] for e in EXPERT_CATALOG]
    existing = {ex.expert_id: ex for ex in db.query(Expert).filter(Expert.expert_id.in_(ids)).all()}

    added = 0
    changed = False
    for entry in EXPERT_CATALOG:
        (
            expert_id, full_name, speciality, qualification, experience_years, location,
            consultation_fee, rating, total_consultations, is_available, languages, bio,
        ) = entry
        ex = existing.get(expert_id)
        if ex is None:
            db.add(Expert(
                expert_id=expert_id,
                full_name=full_name,
                speciality=speciality,
                qualification=qualification,
                experience_years=experience_years,
                location=location,
                consultation_fee=consultation_fee,
                rating=rating,
                total_consultations=total_consultations,
                is_available=is_available,
                languages=languages,
                bio=bio,
            ))
            added += 1
            changed = True
            continue
        if not ex.bio:
            ex.bio = bio
            changed = True
        if not ex.languages:
            ex.languages = languages
            changed = True

    if changed:
        db.commit()
    return added


if __name__ == "__main__":
    import sys
    from json import dumps as _dumps
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.database.connection import SessionLocal

    session = SessionLocal()
    try:
        print(f"seed_experts: {seed_experts(session)} experts created")
        print("experts now:", session.query(Expert).count())
        print("languages sample:", _dumps(session.query(Expert.languages).first()[0]))
    finally:
        session.close()