"""
Seeder for the topic-based Community catalog (community_groups).

These are the standing discussion communities a farmer can join (Rice Farmers,
Dairy Farmers, ...). They are reference catalog data in the same spirit as
seed_services / seed_techniques -- not user-generated content. No sample users,
posts, comments, likes or answers are created here; the community feed starts
empty and is populated only by real authenticated farmers (plus the explicit
demo seed in seed_community_demo, which is clearly flagged as demo data).

Idempotent: each catalog entry is added only if a group with that name does not
already exist, so upgrading an existing install adds only the new entries.

Run standalone:  python -m app.database.seed_communities
"""

from sqlalchemy.orm import Session

from app.models.community import CommunityGroup

# (name, description, category, icon, color)
COMMUNITY_CATALOG = [
    ("Rice Farmers", "Discuss rice cultivation, water management and paddy varieties with fellow growers.", "Crops", "fa-wheat-awn", "#2E7D32"),
    ("Wheat Farmers", "Wheat sowing, irrigation schedules, variety selection and harvest advice.", "Crops", "fa-wheat-awn", "#8B6F47"),
    ("Cotton Cultivation", "Cotton crop management, pest control and fibre quality discussions.", "Crops", "fa-leaf", "#B7791F"),
    ("Sugarcane Farmers", "Sugarcane planting, ratooning, harvesting and mill supply guidance.", "Crops", "fa-seedling", "#558B2F"),
    ("Pulses & Oilseeds", "Grow pulses, groundnut, soybean and sunflower with proven field practices.", "Crops", "fa-seedling", "#6A1B9A"),
    ("Seed Bank & Nursery", "Quality seeds, saplings, grafting and nursery management tips.", "Crops", "fa-seedling", "#D81B60"),
    ("Vegetable Growers", "Everything about vegetable cultivation, from nursery to market.", "Vegetables", "fa-carrot", "#F57C00"),
    ("Potato Growers", "Potato seed, sowing, disease control and storage best practices.", "Vegetables", "fa-seedling", "#8B6F47"),
    ("Greenhouse Farming", "Polyhouse and greenhouse cultivation, climate control and protected farming.", "Vegetables", "fa-house-chimney", "#00695C"),
    ("Horticulture Farmers", "Fruits, flowers, spices and plantation crops knowledge hub.", "Horticulture", "fa-apple-whole", "#D81B60"),
    ("Mango & Orchards", "Mango, chikoo and orchard management - flowering, nutrition and harvesting.", "Horticulture", "fa-apple-whole", "#F57C00"),
    ("Banana Planters", "Banana cultivation, tissue culture planting and bunch management.", "Horticulture", "fa-seedling", "#6A1B9A"),
    ("Spices & Condiments", "Chilli, turmeric, ginger, garlic and coriander growing discussions.", "Horticulture", "fa-seedling", "#C62828"),
    ("Flower Cultivation", "Marigold, jasmine, roses and cut flower production for market.", "Horticulture", "fa-seedling", "#D81B60"),
    ("Soil Health", "Soil testing, fertility and organic matter for better yields.", "Soil", "fa-mountain", "#8B6F47"),
    ("Fertilizer & Nutrition", "Macro and micronutrient management, DAP, urea and biofertilizers.", "Soil", "fa-flask", "#1565C0"),
    ("Organic Farmers", "Share organic farming techniques, inputs and certification advice.", "Organic Farming", "fa-leaf", "#558B2F"),
    ("Natural Farming", "Zero-budget and zero-chemical natural farming practices.", "Organic Farming", "fa-leaf", "#2E7D32"),
    ("Organic Certification", "Steps, records and agencies for becoming an organic-certified farm.", "Organic Farming", "fa-file-certificate", "#4A148C"),
    ("Irrigation Experts", "Water management, drip and sprinkler systems best practices.", "Irrigation", "fa-droplet", "#1565C0"),
    ("Water Management", "Water saving methods, rainwater harvesting and canal scheduling.", "Irrigation", "fa-water", "#00695C"),
    ("Pest & Disease Control", "Identify and manage pests and crop diseases together.", "Pest & Disease", "fa-bug", "#C62828"),
    ("Crop Protection", "Safe spraying, IPM and biological control of crop enemies.", "Pest & Disease", "fa-shield-halved", "#B7791F"),
    ("Livestock Farmers", "Cattle, buffalo and mixed farming management discussions.", "Livestock", "fa-cow", "#6A1B9A"),
    ("Dairy Farmers", "Milk production, cattle feed, healthcare and dairy income.", "Livestock", "fa-cow", "#2E7D32"),
    ("Poultry Farmers", "Broiler and layer farming, feed, vaccination and biosecurity.", "Livestock", "fa-egg", "#C62828"),
    ("Fodder & Cattle Feed", "Green fodder, silage and balanced cattle rations.", "Livestock", "fa-wheat-awn", "#8B6F47"),
    ("Young Farmers", "A space for new and young farmers to connect and learn.", "General", "fa-seedling", "#00695C"),
    ("Women Farmers", "A supportive community for women in farming to share and grow.", "General", "fa-people-roof", "#D81B60"),
    ("Farm Labor & Workers", "Finding workers, labour rates and worker welfare discussions.", "General", "fa-people-group", "#6A1B9A"),
    ("Cooperative & FPO", "Farmer producer organisations, cooperatives and group marketing.", "General", "fa-users", "#B7791F"),
    ("Farmer Success Stories", "Real wins, learnings and inspiration from fellow farmers.", "General", "fa-trophy", "#2E7D32"),
    ("Mushroom Farming", "Button, oyster and paddy straw mushroom growing and marketing.", "General", "fa-seedling", "#8B6F47"),
    ("Beekeeping & Apiary", "Honeybee rearing, hive management and pollination income.", "General", "fa-bee", "#F57C00"),
    ("Agri Finance & Loans", "Kisan credit cards, crop loans and MSME finance guidance.", "Government Schemes", "fa-hand-holding-dollar", "#4A148C"),
    ("Government Schemes", "Updates and guidance on subsidies and farmer schemes.", "Government Schemes", "fa-landmark", "#4A148C"),
    ("Farm Insurance", "PMFBY crop insurance, claims and premium support help.", "Government Schemes", "fa-umbrella", "#1565C0"),
    ("Farm Machinery", "Tractors, tillers, harvesters and cost-saving equipment use.", "Farm Machinery", "fa-tractor", "#8B6F47"),
    ("Drone Technology", "Agri-drones for spraying, mapping and crop scouting.", "Technology", "fa-microchip", "#7c3aed"),
    ("Smart Farming", "IoT sensors, automation and app-based farm monitoring.", "Technology", "fa-microchip", "#7c3aed"),
    ("Agri Technology", "New tools, apps and scientific methods to boost yields.", "Technology", "fa-satellite-dish", "#00695C"),
    ("Precision Agriculture", "Data-driven decisions for seeds, sowing and inputs.", "Technology", "fa-microchip", "#1565C0"),
    ("Hydroponics & Protected", "Soilless growing, hydroponics and vertical farming.", "Technology", "fa-seedling", "#558B2F"),
    ("Market & Trading", "Mandi prices, market links and selling strategies.", "Markets", "fa-chart-line", "#B7791F"),
    ("Mandi Price Watch", "Daily mandi and APMC price updates from the ground.", "Markets", "fa-sack-dollar", "#F57C00"),
    ("Export & Premium Produce", "Export standards, premium varieties and quality grading.", "Markets", "fa-truck", "#C62828"),
    ("Cold Storage & Logistics", "Storage, transportation and reducing post-harvest loss.", "Markets", "fa-warehouse", "#00695C"),
    ("Weather & Climate Watch", "Seasonal forecasts, rainfall and climate planning.", "Weather", "fa-cloud-sun", "#1565C0"),
    ("Sustainability & Eco Farming", "Sustainable, climate-resilient and eco-friendly farming.", "Sustainability", "fa-recycle", "#2E7D32"),
    ("Agroforestry", "Trees on farms, silvipasture and green cover income.", "Sustainability", "fa-tree", "#558B2F"),
]

CATALOG_BY_CATEGORY = {}
for _entry in COMMUNITY_CATALOG:
    CATALOG_BY_CATEGORY.setdefault(_entry[2], []).append(_entry[0])


def seed_communities(db: Session) -> int:
    """Create the community catalog entries that are not already present.

    Returns the number of rows added.
    """
    added = 0
    existing = {
        g.name for g in db.query(CommunityGroup.name).all()
    }

    # Continue the FA-GRP sequence after the highest number already in use so we
    # never collide with an existing group's community_id.
    seq = 0
    for cid, in db.query(CommunityGroup.community_id).filter(
        CommunityGroup.community_id.like("FA-GRP-%")
    ).all():
        try:
            seq = max(seq, int(str(cid).replace("FA-GRP-", "")))
        except (TypeError, ValueError):
            continue

    for (name, description, category, icon, color) in COMMUNITY_CATALOG:
        if name in existing:
            continue
        seq += 1
        db.add(CommunityGroup(
            community_id=f"FA-GRP-{seq:06d}",
            name=name,
            description=description,
            category=category,
            icon=icon,
            color=color,
            is_demo=False,
        ))
        added += 1
    if added:
        db.commit()
    return added


if __name__ == "__main__":
    from app.database.connection import SessionLocal

    session = SessionLocal()
    try:
        print(f"seed_communities: {seed_communities(session)} communities created")
    finally:
        session.close()