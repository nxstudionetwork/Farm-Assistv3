"""Seed 100+ development Shorts (+ posts, stories, interactions) for FarmBuzz.

Usage:
    cd backend
    python seed_farmbuzz.py [--count 104] [--reset-farmbuzz]

- Uses the SAME SQLAlchemy models and relationships as real users.
- Media: real photographic farm assets served from uploads/farmbuzz/seed/
  (farm_01.jpg .. farm_12.jpg, valid JPEGs served through the existing
  /media endpoint) + a few text-only posts. Every short references a real
  photo so the Shorts feed and player never show placeholder tiles.
  If the photo assets are missing, lightweight SVG assets are generated
  as a last resort (no broken refs, no external fake URLs).
- Idempotent: skips when 100+ active shorts already exist (unless --reset-farmbuzz).
"""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.database.connection import SessionLocal, engine, Base
from app.models import (
    User, FarmerProfile, FarmBuzzPost, FarmBuzzComment, FarmBuzzLike,
    FarmBuzzSave, FarmBuzzShare, FarmBuzzFollow, FarmBuzzHashtag,
    FarmBuzzStory, FarmBuzzView, FarmBuzzInteraction,
)
from app.utils.auth import hash_password, generate_id

random.seed(20260905)

SEED_DIR = os.path.join(settings.STORAGE_LOCAL_PATH, "farmbuzz", "seed")

PALETTES = [
    ("#0F2E1E", "#2D8659"), ("#1B5E3F", "#52B788"), ("#1565C0", "#52B788"),
    ("#7c3aed", "#52B788"), ("#d97706", "#1B5E3F"), ("#B23A48", "#E9B640"),
    ("#0F2E1E", "#E9B640"), ("#2D8659", "#E9B640"), ("#40916C", "#0F2E1E"),
    ("#1B5E3F", "#74b9ff"), ("#5b3a1e", "#52B788"), ("#173423", "#74c69d"),
]

ICONS = ["\U0001f33e", "\U0001f69c", "\U0001f4a7", "\U0001f42e", "\U0001f514", "\u2696\ufe0f"]


def make_seed_media(n=12):
    os.makedirs(SEED_DIR, exist_ok=True)
    urls = []
    for i in range(n):
        name = f"farm_{i + 1:02d}.jpg"
        real = os.path.join(SEED_DIR, name)
        if os.path.isfile(real) and os.path.getsize(real) > 2000:
            urls.append(f"/api/v1/farmbuzz/media/farmbuzz/seed/{name}")
            continue
        c1, c2 = PALETTES[i % len(PALETTES)]
        icon = ICONS[i % len(ICONS)]
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="540" height="960">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/>'
            "</linearGradient></defs>"
            '<rect width="540" height="960" fill="url(#g)"/>'
            f'<text x="270" y="440" font-size="120" text-anchor="middle">{icon}</text>'
            f'<text x="270" y="560" font-size="34" font-family="sans-serif" font-weight="bold" '
            'fill="white" text-anchor="middle">FarmBuzz</text>'
            f'<text x="270" y="610" font-size="24" font-family="sans-serif" '
            'fill="white" text-anchor="middle" opacity="0.85">Agri Short</text>'
            "</svg>"
        )
        with open(os.path.join(SEED_DIR, f"seed_{i + 1:02d}.svg"), "w", encoding="utf-8") as f:
            f.write(svg)
        urls.append(f"/api/v1/farmbuzz/media/farmbuzz/seed/seed_{i + 1:02d}.svg")
    return urls


TOPICS = [
    # (category, crop, title, caption, hashtags)
    ("Farming", "Paddy", "Paddy nursery in 12 days", "Healthy paddy nursery with raised beds and timely watering gives uniform seedlings.", ["paddy", "nursery", "kharif"]),
    ("Crop", "Rice", "Sona Masuri tillering tips", "Keep 2-3 cm water during tillering and apply first N split for more tillers.", ["rice", "tillering", "fertilizer"]),
    ("Crop", "Cotton", "Bt cotton spacing guide", "90x60 cm spacing with drip gives better boll setting and easier picking.", ["cotton", "spacing", "drip"]),
    ("Crop", "Chilli", "Guntur chilli nursery care", "Shade nets for first 10 days prevent damping-off in chilli nurseries.", ["chilli", "nursery", "spices"]),
    ("Crop", "Groundnut", "Groundnut pegging stage", "Light earthing-up at pegging improves pod formation in sandy loams.", ["groundnut", "oilseed", "kharif"]),
    ("Crop", "Maize", "Hybrid maize plant population", "65,000 plants per hectare is the sweet spot for most hybrids.", ["maize", "hybrid", "yield"]),
    ("Crop", "Sugarcane", "Trash mulching in cane", "Trash mulching saves one irrigation and adds organic matter.", ["sugarcane", "mulch", "water"]),
    ("Crop", "Banana", "Banana propping before winds", "Prop bunches before monsoon winds to avoid lodging losses.", ["banana", "horticulture", "monsoon"]),
    ("Crop", "Tomato", "Tomato staking in rains", "Staking + pruning keeps foliage dry and cuts blight pressure.", ["tomato", "vegetables", "kharif"]),
    ("Crop", "Onion", "Onion curing after harvest", "Cure bulbs 7 days in shade for longer storage life.", ["onion", "storage", "postharvest"]),
    ("Crop", "Vegetables", "Brinjal shoot borer trap", "Pheromone traps at 5 per acre catch borer moths early.", ["vegetables", "pest", "ipm"]),
    ("Horticulture", "Mango", "Mango flowering nutrition", "0.5% zinc + boron spray at flowering improves fruit set.", ["mango", "orchard", "nutrition"]),
    ("Soil", "Paddy", "Soil sampling done right", "Take 8-10 cores per acre at 15 cm depth for a true sample.", ["soil", "testing", "fertility"]),
    ("Soil", "Cotton", "pH correction with gypsum", "Gypsum at 200 kg per acre reclaims sodic patches gradually.", ["soil", "gypsum", "reclamation"]),
    ("Irrigation", "Tomato", "Drip scheduling for tomato", "30-minute cycles morning and evening beat one long run.", ["irrigation", "drip", "water"]),
    ("Irrigation", "Cotton", "Drip saves 40% water", "Low-cost drip with mulch cut our borewell hours in half.", ["drip", "water", "savings"]),
    ("Organic Farming", "Vegetables", "Jeevamrit every 15 days", "200 litres per acre jeevamrit keeps soil biology active.", ["organic", "jeevamrit", "natural"]),
    ("Organic Farming", "Paddy", "Green manure before paddy", "Dhaincha at 45 days adds 60 kg nitrogen per hectare.", ["greenmanure", "paddy", "soil"]),
    ("Tip", "Cotton", "Pink bollworm scouting", "Check 20 bolls per acre; spray only above threshold.", ["cotton", "pest", "ipm"]),
    ("Tip", "Rice", "Stem borer pheromone traps", "8 traps per acre give early warning of borer flights.", ["rice", "pest", "traps"]),
    ("Tip", "Chilli", "Thrips control without burn", "Blue sticky traps + neemazal rotate well against thrips.", ["chilli", "pest", "organic"]),
    ("Tip", "Maize", "Fall armyworm whorl test", "Pinch of sand + neem in the whorl kills young larvae.", ["maize", "pest", "ipm"]),
    ("Farming", "Wheat", "Zero-till wheat sowing", "Zero-till saved diesel and gave 20% cost saving this rabi.", ["wheat", "zerotill", "rabi"]),
    ("Machinery", None, "Tractor tyre pressure", "Rear 14 psi and front 22 psi reduce compaction in wet fields.", ["tractor", "machinery", "tips"]),
    ("Machinery", None, "Sprayer calibration 101", "500 ml per minute nozzle output suits most contact sprays.", ["sprayer", "machinery", "safety"]),
    ("Market", "Cotton", "eNAM selling this week", "eNAM bids beat village trader by Rs 180 per quintal today.", ["market", "enam", "price"]),
    ("Market", "Onion", "Reading mandi arrivals", "Falling arrivals for 3 days usually lift prices — time sales.", ["market", "mandi", "price"]),
    ("Government", None, "PM-KISAN installment alert", "Check beneficiary status before the next installment window.", ["pmkisan", "scheme", "support"]),
    ("Government", None, "PMFBY enrolment window", "Enrol Kharif crops before the cutoff to stay insured.", ["pmfby", "insurance", "kharif"]),
    ("Finance", None, "KCC renewal checklist", "Land records + crop sown certificate speed up KCC renewal.", ["kcc", "credit", "finance"]),
    ("Livestock", "Dairy", "Deworming dairy cows", "Deworm every 3 months and repeat mineral mixture daily.", ["dairy", "livestock", "health"]),
    ("Dairy", "Dairy", "Clean milk production", "Wash udder, dry, then milk — keeps MBR time high.", ["dairy", "milk", "hygiene"]),
    ("Poultry", "Poultry", "Brooding temperature chart", "32°C week one, minus 3 each week for desi chicks.", ["poultry", "brooding", "tips"]),
    ("Livestock", "Goat", "Goat kid care first week", "Colostrum within 2 hours decides kid survival.", ["goat", "livestock", "care"]),
    ("Weather", "Paddy", "Monsoon sowing window", "Sow within 5 days of 50 mm soaking rain for best stand.", ["weather", "monsoon", "sowing"]),
    ("Weather", None, "Hailstorm preparedness", "Keep tarpaulins ready when orange alerts mention hail.", ["weather", "alert", "safety"]),
    ("Technology", None, "Drone spraying math", "Shared drone at Rs 300 per acre beats manual labour cost.", ["drone", "technology", "spray"]),
    ("Technology", "Cotton", "Soil moisture sensor", "Irrigate at 30 centibars for cotton in black soils.", ["sensors", "irrigation", "smart"]),
    ("Success Stories", "Banana", "One-acre banana profit", "Tissue-culture banana netted Rs 1.2 lakh in 11 months.", ["success", "banana", "income"]),
    ("Success Story", "Dairy", "Five-cow dairy model", "Five HF cows + fodder plot pay Rs 35,000 monthly.", ["success", "dairy", "income"]),
    ("Community", None, "Shared harvester group", "Our 6-farmer group books one harvester, halves cost.", ["community", "machinery", "sharing"]),
    ("Question", "Tomato", "Leaf curl — virus or mites?", "Yellow curling upward with stunting points to virus; rogue plants.", ["tomato", "disease", "help"]),
    ("Tip", "Sugarcane", "Sett treatment that works", "Dip setts in Trichoderma slurry for 20 minutes before planting.", ["sugarcane", "sett", "disease"]),
    ("Educational", "Rice", "Panicle initiation check", "Split a tiller — a 2 mm panicle means PI has begun.", ["rice", "growth", "knowledge"]),
    ("Quick Knowledge", "Wheat", "Flag leaf matters most", "Protect the flag leaf; it fills 45% of grain weight.", ["wheat", "knowledge", "yield"]),
    ("Farmer Techniques", "Cotton", "Topping cotton at 90 days", "Nipping the top bud pushes sympodial branching.", ["cotton", "techniques", "yield"]),
    ("Farmer Tricks", "Chilli", "Chilli picking baskets", "Wide shallow baskets bruise less than deep sacks.", ["chilli", "harvest", "tricks"]),
    ("Farming Scenes", "Paddy", "Sunrise transplanting", "Morning transplanting reduces seedling shock in July heat.", ["paddy", "scenes", "kharif"]),
    ("Farmer Life", None, "Night irrigation routine", "Head torch + whistle: our night-watch rota for canal turns.", ["farmerlife", "irrigation", "community"]),
    ("Farming Comedy", None, "When the tractor won't start", "Three farmers, one crank, zero patience — sound on.", ["comedy", "tractor", "fun"]),
    ("Expert Shorts", "Cotton", "Agronomist on sucking pests", "Jassids above 2 per leaf need action — start with neem.", ["expert", "cotton", "pest"]),
    ("Organic Farming", "Turmeric", "Turmeric boiling time", "Boil fingers till they snap clean — about 45 minutes.", ["turmeric", "processing", "organic"]),
    ("Sustainable Farming", None, "Farm pond sizing", "300 cubic metres per acre buffers a 20-day dry spell.", ["pond", "water", "sustainable"]),
    ("Horticulture", "Guava", "Guava bahar regulation", "Withhold water in June for a heavy winter bahar.", ["guava", "orchard", "pruning"]),
    ("Crop", "Soybean", "Soybean nodulation check", "Pink nodules mean active fixation — no extra urea needed.", ["soybean", "nitrogen", "kharif"]),
    ("Crop", "Sunflower", "Bee hives boost seed set", "Two hives per hectare lift sunflower filling visibly.", ["sunflower", "pollination", "yield"]),
    ("Irrigation", None, "Rainwater harvesting pit", "One recharge pit per borewell revived our summer yield.", ["rainwater", "recharge", "water"]),
    ("Soil", None, "Vermibed in 45 days", "8x4 ft bed with 5 kg worms gives a quintal of compost.", ["vermicompost", "soil", "organic"]),
    ("Market", "Maize", "Stagger maize sales", "Sell half at harvest, half after 60 days — spreads risk.", ["maize", "market", "storage"]),
    ("Technology", None, "WhatsApp crop calendar", "Our group shares spray dates so pests don't hop farms.", ["technology", "community", "planning"]),
    ("Livestock", "Sheep", "Sheep shearing season", "Shear before summer rains to cut tick load.", ["sheep", "livestock", "care"]),
    ("Dairy", "Fodder", "Azolla as feed top-up", "500 g azolla per cow daily trims concentrate cost.", ["azolla", "fodder", "dairy"]),
    ("Weather", "Cotton", "Windbreaks that work", "Subabul rows on the west cut boll shedding in storms.", ["windbreak", "cotton", "weather"]),
    ("Government", None, "Soil health card camp", "Free testing camp at the mandal office this Friday.", ["soilcard", "scheme", "testing"]),
    ("Finance", "Paddy", "Crop loan interest math", "4% effective KCC rate beats any input dealer credit.", ["finance", "kcc", "planning"]),
    ("Success Stories", "Poultry", "Backyard poultry income", "50 desi birds pay school fees every single month.", ["poultry", "income", "success"]),
    ("Community", "Paddy", "Custom hiring centre", "CHC rotavator at Rs 900 per hour — book a day early.", ["machinery", "community", "services"]),
    ("Tip", "Banana", "Sigatoka leaf spotting", "Remove worst leaves first, then mancozeb at 2.5 g per litre.", ["banana", "disease", "spray"]),
    ("Educational", "Soil", "Reading NPK ratio bags", "10-26-26 means 10% N, 26% P and K per 100 kg bag.", ["fertilizer", "knowledge", "basics"]),
    ("Quick Knowledge", "Onion", "Seed rate for onion", "8 kg seed per hectare for rabi onion nurseries.", ["onion", "seed", "rabi"]),
    ("Farmer Techniques", "Sugarcane", "Paired-row cane planting", "120 cm paired rows fit drip laterals perfectly.", ["sugarcane", "planting", "drip"]),
    ("Farmer Tricks", "Tomato", "Ripening without chemicals", "Straw-lined crates ripen tomatoes evenly in 3 days.", ["tomato", "postharvest", "tricks"]),
    ("Farming Scenes", "Wheat", "Combine at golden hour", "Evening harvest cuts shattering in dry wheat.", ["wheat", "harvest", "scenes"]),
    ("Farmer Life", None, "Mandi night halt tips", "Carry tarpaulin, torch and tiffin — auctions start at 4 am.", ["mandi", "life", "tips"]),
    ("Farming Comedy", None, "Goat vs vegetable plot", "Fence first, laugh later — goat edition.", ["comedy", "goat", "fun"]),
    ("Expert Shorts", "Paddy", "Pathologist on blast", "Leaf blast lesions with grey centres need tricyclazole.", ["expert", "paddy", "disease"]),
    ("Crop", "Redgram", "Redgram wilt watch", "Uproot and burn wilted plants; rotate with sorghum.", ["redgram", "disease", "pulses"]),
    ("Crop", "Castor", "Castor picking rounds", "Pick every 10 days; don't wait for all spikes to dry.", ["castor", "harvest", "oilseed"]),
    ("Horticulture", "Papaya", "Papaya ringspot roguing", "Rogue early-infected plants to slow spread.", ["papaya", "virus", "orchard"]),
    ("Irrigation", "Banana", "Basin vs drip for banana", "Drip + mulch uses half the water of basins.", ["banana", "drip", "water"]),
    ("Soil", "Groundnut", "Gypsum at pegging", "250 kg gypsum per hectare fills groundnut pods better.", ["groundnut", "gypsum", "yield"]),
    ("Market", "Chilli", "Chilli drying yard", "Concrete yard + shade nets keep colour grade high.", ["chilli", "drying", "quality"]),
    ("Technology", "Paddy", "Direct seeding vs transplant", "DSR saves 30% water where labour is scarce.", ["dsr", "paddy", "water"]),
    ("Sustainable Farming", "Cotton", "Refuge crop for Bt", "5 rows of non-Bt cotton keep resistance low.", ["btcotton", "resistance", "ipm"]),
    ("Organic Farming", "Coconut", "Coconut basin mulching", "Husk burial in basins holds moisture for months.", ["coconut", "mulch", "water"]),
    ("Livestock", "Buffalo", "Heat detection in buffalo", "Evening mounting + mucus means inseminate next morning.", ["buffalo", "breeding", "dairy"]),
    ("Weather", None, "Reading IMD alerts", "Orange means be prepared; red means act now.", ["imd", "alert", "safety"]),
    ("Government", None, "Farm pond subsidy", "50% subsidy on farm ponds up to 2 acres command.", ["subsidy", "pond", "scheme"]),
    ("Finance", None, "Dairy loan EMI planning", "One cow's milk should cover its own EMI + feed.", ["dairy", "loan", "planning"]),
    ("Success Story", "Turmeric", "Polished turmeric premium", "Boiled + polished fingers fetch Rs 800 more per quintal.", ["turmeric", "value", "income"]),
    ("Community", None, "Seed exchange mela", "Bring 2 kg desi seed, take 2 kg home — Sunday shandy.", ["seeds", "community", "exchange"]),
    ("Question", "Cotton", "Whitefly honeydew sticky?", "Sticky leaves + sooty mould confirm whitefly — spray diafenthiuron.", ["cotton", "pest", "help"]),
    ("Tip", "Paddy", "Last N split timing", "Final urea at panicle initiation, not after flowering.", ["paddy", "fertilizer", "yield"]),
    ("Educational", "Maize", "Silk drying = done pollinating", "Brown dry silks mean kernels are set — stop worrying.", ["maize", "growth", "knowledge"]),
    ("Quick Knowledge", "Sugarcane", "Trash shredder value", "Shredded trash returns 30 kg potassium per acre.", ["sugarcane", "trash", "soil"]),
    ("Farmer Techniques", "Onion", "Rope curing method", "Braid tops and hang — airflow beats heap storage.", ["onion", "storage", "techniques"]),
    ("Farmer Tricks", "Banana", "De-suckering rhythm", "Keep mother + one follower + one sucker, nothing more.", ["banana", "pruning", "tricks"]),
    ("Farming Scenes", "Cotton", "First picking morning", "Pick dry kapas after dew lifts for clean lint.", ["cotton", "harvest", "scenes"]),
    ("Expert Shorts", "Soil", "Micronutrient shortcuts", "Zinc sulphate 25 kg per hectare fixes most kharif deficits.", ["expert", "soil", "micronutrient"]),
]

POST_TOPICS = [
    ("Farming", "Paddy", "Kharif progress update", "Transplanting finished on 4 acres. Water holding well after bund repair.", ["kharif", "paddy"]),
    ("Tip", None, "Neemastra in 3 days", "Crush 5 kg neem leaves + 5 litres cow urine + 100 litres water. Ready in 72 hours.", ["neem", "organic", "pest"]),
    ("Market", "Cotton", "Mandi rates today", "Kapas touched Rs 6,540 at our mandi. Holding 5 quintals for next week.", ["mandi", "cotton", "price"]),
    ("Success Story", "Vegetables", "Polyhouse capsicum win", "First capsicum cut gave 2.1 tonnes from 1000 sqm. Buyers want weekly supply.", ["polyhouse", "income", "success"]),
    ("Question", "Tomato", "Yellow leaves after rain?", "Lower leaves yellowing after 3 days of rain. Drainage is okay. Deficiency or blight?", ["tomato", "help", "disease"]),
    ("Community", None, "Labour sharing this week", "Need 6 hands for transplanting Thursday. Our group rotates — who's free?", ["labour", "community", "help"]),
    ("Machinery", None, "Rotavator booking open", "CHC rotavator free Saturday. Rs 900 per hour with driver.", ["machinery", "services"]),
    ("Government", None, "Drip subsidy approved", "My drip application got approved — 55% subsidy. Process took 3 weeks.", ["subsidy", "drip", "scheme"]),
    ("Crop", "Maize", "Armyworm under control", "Pheromone traps + one emamectin spray stopped the spread. Scout whorls daily.", ["maize", "pest", "ipm"]),
    ("Tip", None, "Seed storage with neem", "Mix 200 g neem leaf powder per 10 kg seed. Zero weevils last season.", ["seeds", "storage", "organic"]),
    ("Farming", "Sugarcane", "Ratoon management", "Stubble shaving + trash mulching gave even sprouting in 12 days.", ["sugarcane", "ratoon"]),
    ("Weather", None, "Cyclone watch prep", "Tied banana bunches and moved harvested paddy under cover before the alert.", ["weather", "safety"]),
]

COMMENT_POOL = [
    "Very useful, trying this on my field this week.",
    "Worked well for us last season too.",
    "What dosage did you use per acre?",
    "Thanks for sharing such a clear explanation.",
    "Our FPO discussed this in yesterday's meeting.",
    "Adding this to my kharif plan.",
    "Can you share the cost breakup?",
    "Good timing — pest pressure is rising here.",
]

DEMO_FARMERS = [
    ("Lakshmi Narayana", "9000000001", "Paddy,Cotton", "Nalgonda, Telangana"),
    ("Venkatesh Goud", "9000000002", "Chilli,Tomato", "Warangal, Telangana"),
    ("Anitha Reddy", "9000000003", "Dairy,Vegetables", "Karimnagar, Telangana"),
    ("Srinivas Rao", "9000000004", "Cotton,Maize", "Khammam, Telangana"),
    ("Kavitha Sharma", "9000000005", "Organic Farming,Vegetables", "Hyderabad, Telangana"),
    ("Ravi Teja", "9000000006", "Banana,Sugarcane", "Nizamabad, Telangana"),
    ("Mohan Reddy", "9000000007", "Groundnut,Onion", "Mahabubnagar, Telangana"),
    ("Divya Sri", "9000000008", "Poultry,Dairy", "Medak, Telangana"),
]


def get_or_create_farmers(db):
    farmers = []
    for name, phone, crops, loc in DEMO_FARMERS:
        u = db.query(User).filter(User.phone_number == phone).first()
        if not u:
            u = User(
                full_name=name, phone_number=phone,
                email=f"demo{phone}@farmassist.local",
                password_hash=hash_password("1234"),
                preferred_language="en", role="farmer",
                is_verified=True, is_active=True,
            )
            db.add(u)
            db.flush()
            from app.utils.auth import generate_farmer_id
            u.farmer_id = generate_farmer_id(db)
            db.add(FarmerProfile(
                user_id=u.id, farmer_id=u.farmer_id,
                preferred_crops=crops, farm_location=loc,
                farming_type="Crop Farmer",
                bio=f"{name} grows {crops} near {loc}.",
            ))
            db.flush()
        farmers.append(u)
    db.commit()
    return farmers


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=104)
    ap.add_argument("--reset-farmbuzz", action="store_true")
    args = ap.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.reset_farmbuzz:
            for m in (FarmBuzzInteraction, FarmBuzzView, FarmBuzzShare,
                      FarmBuzzSave, FarmBuzzLike, FarmBuzzComment,
                      FarmBuzzStory, FarmBuzzPost):
                db.query(m).delete()
            db.commit()
            print("Cleared FarmBuzz tables.")

        existing_shorts = db.query(FarmBuzzPost).filter(
            FarmBuzzPost.content_type == "short",
            FarmBuzzPost.is_active == True,
        ).all()
        if len(existing_shorts) >= 100:
            created_posts = existing_shorts
            print(f"Already have {len(existing_shorts)} shorts — topping up interactions only.")
            seed_interactions_only = True
        else:
            seed_interactions_only = False

        media_urls = make_seed_media(12)
        farmers = get_or_create_farmers(db)
        # refresh ids
        for f in farmers:
            db.refresh(f)

        now = datetime.utcnow()
        if seed_interactions_only:
            created_posts = existing_shorts
        else:
            need = max(args.count, 100) - len(existing_shorts)
            topics = (TOPICS * ((need // len(TOPICS)) + 1))[:need]
            created_posts = []
        if not seed_interactions_only:
            for i, (cat, crop, title, caption, tags) in enumerate(topics):
                author = farmers[i % len(farmers)]
                days_ago = (i * 37) % 30
                hours_ago = (i * 13) % 24
                created = now - timedelta(days=days_ago, hours=hours_ago)
                use_image = (i % 3 != 2)  # 2/3 image, 1/3 text-only
                media_url = media_urls[i % len(media_urls)] if use_image else None
                media_type = "image" if use_image else "text"
                post = FarmBuzzPost(
                    post_id=generate_id("FA-BZ", db, FarmBuzzPost),
                    user_id=author.id,
                    content_type="short",
                    title=title,
                    caption=caption,
                    media_url=media_url,
                    media_type=media_type,
                    thumbnail_url=media_url,
                    location=random.choice([
                        "Nalgonda, Telangana", "Warangal, Telangana",
                        "Karimnagar, Telangana", "Krishna, AP", "Guntur, AP",
                    ]),
                    crop=crop,
                    category=cat,
                    hashtags=sorted({t.lower() for t in tags}),
                    visibility="public",
                    is_active=True,
                    created_at=created,
                    updated_at=created,
                )
                db.add(post)
                db.flush()
                for t in tags:
                    tag = t.lower()
                    row = db.query(FarmBuzzHashtag).filter(FarmBuzzHashtag.tag == tag).first()
                    if row:
                        row.post_count = (row.post_count or 0) + 1
                    else:
                        db.add(FarmBuzzHashtag(tag=tag, post_count=1))
                created_posts.append(post)
            db.commit()

        # Interactions: likes / saves / views / comments / shares / follows.
        # Preload existing pairs so re-runs and in-batch repeats never hit
        # UNIQUE constraints (the session can't see unflushed pending rows).
        seen_likes = {(r.post_id, r.user_id) for r in db.query(
            FarmBuzzLike.post_id, FarmBuzzLike.user_id).all()}
        seen_saves = {(r.post_id, r.user_id) for r in db.query(
            FarmBuzzSave.post_id, FarmBuzzSave.user_id).all()}
        seen_views = {(r.post_id, r.user_id) for r in db.query(
            FarmBuzzView.post_id, FarmBuzzView.user_id).all()}
        seen_follows = {(r.follower_id, r.following_id) for r in db.query(
            FarmBuzzFollow.follower_id, FarmBuzzFollow.following_id).all()}
        for idx, post in enumerate(created_posts):
            # Skip posts that already have seeded engagement (re-run safety).
            if (db.query(FarmBuzzLike).filter(FarmBuzzLike.post_id == post.id).count()
                    + db.query(FarmBuzzComment).filter(FarmBuzzComment.post_id == post.id).count()
                    + db.query(FarmBuzzView).filter(FarmBuzzView.post_id == post.id).count()) >= 3:
                continue
            others = [f for f in farmers if f.id != post.user_id]
            n_like = random.randint(0, min(14, len(others) + 6))
            likers = random.sample(farmers, min(len(farmers) - 1, n_like))
            for u in [x for x in likers if x.id != post.user_id][:10]:
                if (post.id, u.id) not in seen_likes:
                    seen_likes.add((post.id, u.id))
                    db.add(FarmBuzzLike(post_id=post.id, user_id=u.id))
            n_save = random.randint(0, 5)
            for u in random.sample(others, min(len(others), n_save)):
                if (post.id, u.id) not in seen_saves:
                    seen_saves.add((post.id, u.id))
                    db.add(FarmBuzzSave(post_id=post.id, user_id=u.id))
            n_view = random.randint(3, 12)
            for u in random.sample(farmers, min(len(farmers), n_view)):
                if u.id == post.user_id:
                    continue
                if (post.id, u.id) not in seen_views:
                    seen_views.add((post.id, u.id))
                    db.add(FarmBuzzView(post_id=post.id, user_id=u.id))
            n_comment = random.randint(0, 3)
            for u in random.sample(others, min(len(others), n_comment)):
                db.add(FarmBuzzComment(
                    post_id=post.id, user_id=u.id,
                    content=random.choice(COMMENT_POOL),
                ))
            if idx % 9 == 0 and others:
                u = random.choice(others)
                db.add(FarmBuzzShare(post_id=post.id, user_id=u.id))
            # behaviour events for recommender variety
            for u in random.sample(farmers, min(len(farmers), random.randint(1, 4))):
                if u.id == post.user_id:
                    continue
                et = random.choice(["watch", "watch", "complete", "complete", "skip", "replay", "qualified_view"])
                db.add(FarmBuzzInteraction(
                    post_id=post.id, user_id=u.id, event_type=et,
                    watch_duration_ms=random.randint(1500, 30000),
                    completion_pct=random.randint(10, 100) if et != "skip" else random.randint(1, 15),
                ))
            # a couple of follows to build the social graph
            if idx % 12 == 0 and others:
                a, b = random.choice(others), post.user_id
                if (a.id, b) not in seen_follows:
                    seen_follows.add((a.id, b))
                    db.add(FarmBuzzFollow(follower_id=a.id, following_id=b))
            if idx % 20 == 0:
                db.commit()
        db.commit()

        # Recompute denormalized counts from truth tables
        for post in created_posts:
            post.likes_count = db.query(FarmBuzzLike).filter(FarmBuzzLike.post_id == post.id).count()
            post.saves_count = db.query(FarmBuzzSave).filter(FarmBuzzSave.post_id == post.id).count()
            post.comments_count = db.query(FarmBuzzComment).filter(FarmBuzzComment.post_id == post.id).count()
            post.shares_count = db.query(FarmBuzzShare).filter(FarmBuzzShare.post_id == post.id).count()
            post.views_count = db.query(FarmBuzzView).filter(FarmBuzzView.post_id == post.id).count()
            # anonymous views add a little organic reach without breaking dedup logic
            post.views_count = (post.views_count or 0) + random.randint(0, 20)
        db.commit()

        # Seed posts (only if the DB has almost none — keeps re-runs idempotent)
        existing_posts = db.query(FarmBuzzPost).filter(
            FarmBuzzPost.content_type == "post", FarmBuzzPost.is_active == True).count()
        post_topics = [] if existing_posts >= 10 else POST_TOPICS
        for i, (cat, crop, title, caption, tags) in enumerate(post_topics):
            author = farmers[(i + 2) % len(farmers)]
            created = now - timedelta(days=(i * 3) % 20, hours=(i * 5) % 24)
            use_image = (i % 2 == 0)
            media_url = media_urls[(i + 3) % len(media_urls)] if use_image else None
            post = FarmBuzzPost(
                post_id=generate_id("FA-BZ", db, FarmBuzzPost),
                user_id=author.id,
                content_type="post",
                title=title,
                caption=caption,
                media_url=media_url,
                media_type="image" if use_image else "text",
                thumbnail_url=media_url,
                crop=crop, category=cat,
                hashtags=sorted({t.lower() for t in tags}),
                visibility="public", is_active=True,
                created_at=created, updated_at=created,
            )
            db.add(post)
            db.flush()
        db.commit()

        # Seed stories (active; top up only when fewer than 4 are live)
        live_stories = db.query(FarmBuzzStory).filter(
            FarmBuzzStory.is_active == True,
            FarmBuzzStory.expires_at > now).count()
        for i in range(0 if live_stories >= 4 else 6):
            author = farmers[i % len(farmers)]
            use_media = (i % 2 == 0)
            story = FarmBuzzStory(
                story_id=generate_id("FA-ST", db, FarmBuzzStory),
                user_id=author.id,
                media_url=media_urls[i % len(media_urls)] if use_media else None,
                media_type="image" if use_media else "text",
                caption=random.choice([
                    "Morning field round done — crop looking strong.",
                    "New drip line installed today.",
                    "Market day! Taking tomatoes to the mandi.",
                    "Soil testing camp tomorrow, don't miss it.",
                    "Calf born this morning, healthy and active.",
                    "Evening irrigation complete.",
                ]),
                is_active=True,
                expires_at=now + timedelta(hours=23),
                created_at=now - timedelta(hours=i * 2),
            )
            db.add(story)
            db.flush()
        db.commit()

        # Auto-heal: pre-existing shorts with invalid media (old test data)
        # become valid text shorts so the playable feed never has broken refs.
        repaired = 0
        for p in db.query(FarmBuzzPost).filter(
                FarmBuzzPost.content_type == "short", FarmBuzzPost.is_active == True).all():
            broken = (
                (p.media_type == "video" and not p.media_url)
                or (p.media_url or "").startswith(("http://", "https://"))
            )
            if p.media_url and p.media_url.startswith("/api/v1/farmbuzz/media/"):
                rel = p.media_url.replace("/api/v1/farmbuzz/media/", "")
                if not os.path.exists(os.path.join(settings.STORAGE_LOCAL_PATH, rel)):
                    broken = True
            if broken:
                p.media_type = "text"
                p.media_url = None
                p.thumbnail_url = None
                repaired += 1
        if repaired:
            db.commit()
            print(f"Auto-healed {repaired} broken short media refs.")

        # ---- verification ----
        n_shorts = db.query(FarmBuzzPost).filter(
            FarmBuzzPost.content_type == "short", FarmBuzzPost.is_active == True).count()
        n_posts = db.query(FarmBuzzPost).filter(
            FarmBuzzPost.content_type == "post", FarmBuzzPost.is_active == True).count()
        n_stories = db.query(FarmBuzzStory).filter(FarmBuzzStory.is_active == True).count()
        # every playable short must have valid media or be text-only
        bad = 0
        q = db.query(FarmBuzzPost).filter(
            FarmBuzzPost.content_type == "short", FarmBuzzPost.is_active == True).all()
        for p in q:
            if p.media_type == "video" and not p.media_url:
                bad += 1
            if p.media_url and p.media_url.startswith("/api/v1/farmbuzz/media/"):
                rel = p.media_url.replace("/api/v1/farmbuzz/media/", "")
                if not os.path.exists(os.path.join(settings.STORAGE_LOCAL_PATH, rel)):
                    bad += 1
            if p.media_url and p.media_url.startswith("http"):
                bad += 1
        print(f"Shorts: {n_shorts}, Posts: {n_posts}, Stories: {n_stories}")
        print(f"Seed media files: {len(media_urls)} in {SEED_DIR}")
        print(f"Broken media refs: {bad}")
        assert n_shorts >= 100, f"Expected 100+ shorts, got {n_shorts}"
        assert bad == 0, f"{bad} broken media references"
        print("FarmBuzz seed OK — recommendation pool ready.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
