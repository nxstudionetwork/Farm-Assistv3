"""
Seeder for the topic-based Community catalog (community_groups).

These are the standing discussion communities a farmer can join (Rice Farmers,
Organic Farmers, ...). They are reference catalog data in the same spirit as
seed_services / seed_techniques -- not user-generated content. No sample users,
posts, comments, likes or answers are created here; the community feed starts
empty and is populated only by real authenticated farmers.

Idempotent: seeding is skipped as soon as any group exists.

Run standalone:  python -m app.database.seed_communities
"""

from sqlalchemy.orm import Session

from app.models.community import CommunityGroup

# (name, description, category, icon, color)
COMMUNITY_CATALOG = [
    ("Rice Farmers", "Discuss rice cultivation, water management and paddy varieties with fellow growers.", "Crops", "fa-plant-wilt", "#2E7D32"),
    ("Organic Farmers", "Share organic farming techniques, inputs and certification advice.", "Organic Farming", "fa-leaf", "#558B2F"),
    ("Vegetable Growers", "Everything about vegetable cultivation, from nursery to market.", "Vegetables", "fa-carrot", "#F57C00"),
    ("Horticulture", "Fruits, flowers, spices and plantation crops knowledge hub.", "Horticulture", "fa-apple-whole", "#D81B60"),
    ("Livestock & Dairy", "Cattle, buffalo, poultry and dairy management discussions.", "Livestock", "fa-cow", "#6A1B9A"),
    ("Young Farmers", "A space for new and young farmers to connect and learn.", "General", "fa-seedling", "#00695C"),
    ("Farm Technology", "Drones, sensors, AI and precision farming tools and tips.", "Technology", "fa-microchip", "#7c3aed"),
    ("Irrigation Experts", "Water management, drip and sprinkler systems best practices.", "Irrigation", "fa-droplet", "#1565C0"),
    ("Soil Health", "Soil testing, fertility and organic matter for better yields.", "Soil", "fa-mountain", "#8B6F47"),
    ("Market & Prices", "Mandi prices, market links and selling strategies.", "Markets", "fa-chart-line", "#B7791F"),
    ("Pest & Disease Control", "Identify and manage pests and crop diseases together.", "Pest & Disease", "fa-bug", "#C62828"),
    ("Government Schemes", "Updates and guidance on subsidies and farmer schemes.", "Government Schemes", "fa-landmark", "#4A148C"),
]


def seed_communities(db: Session) -> int:
    """Create the community catalog if the table is empty. Returns rows added."""
    if db.query(CommunityGroup).count() > 0:
        return 0

    for index, (name, description, category, icon, color) in enumerate(COMMUNITY_CATALOG, start=1):
        db.add(CommunityGroup(
            community_id=f"FA-GRP-{index:04d}",
            name=name,
            description=description,
            category=category,
            icon=icon,
            color=color,
        ))
    db.commit()
    return len(COMMUNITY_CATALOG)


if __name__ == "__main__":
    from app.database.connection import SessionLocal

    session = SessionLocal()
    try:
        print(f"seed_communities: {seed_communities(session)} communities created")
    finally:
        session.close()
