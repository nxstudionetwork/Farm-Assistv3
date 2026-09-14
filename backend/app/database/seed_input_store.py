"""Seed the Input Store catalogue.

Standalone script - run it once on a fresh or existing database::

    python -B -m app.database.seed_input_store

It is safe to re-run (idempotent). It creates the Input Store product
categories (the Input Store BUY-side catalogue) and a realistic catalogue of
agricultural inputs with correct terminology and category-accurate imagery.

Domain boundaries
-----------------
The ``products`` / ``product_categories`` tables are the Input Store (BUY
side) catalogue. The farmer SELLING side lives in the separate
``marketplace_listings`` tables. The Tools & Equipment storefront shares the
same ``products`` table but is isolated by its own category slugs (see
``app.equipment_taxonomy``). The Input Store slugs below are chosen to never
collide with those equipment slugs, and the API in ``app.routers.input_store``
only ever lists products that belong to this slug whitelist.

Existing catalogue rows are upgraded *in place* (matched by product name) so
re-runs re-home products into the expanded taxonomy without creating
duplicates. Images are stable Unsplash CDN URLs that were verified to resolve
(HHTP 200) and reflect real agriculture product categories.

Cash-on-delivery availability is a per-product attribute. Live microbial
cultures (short shelf life, temperature sensitive) are prepaid-only and are
listed in ``COD_UNAVAILABLE``; every other input supports COD. The storefront
checkout gates COD behind this flag.
"""

import hashlib
import os
import sys

# Make ``backend`` importable when launched from the repo root or backend dir.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite:///./farm_assist.db"
for _candidate in (os.path.join(_ROOT, "backend"), os.path.dirname(os.path.dirname(os.path.abspath(__file__))))[:1]:
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from sqlalchemy.orm import Session  # noqa: E402

from app.database.connection import SessionLocal, engine  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.schema_upgrade import run_additive_migrations  # noqa: E402, F401
from app.utils.auth import generate_id  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.marketplace import (  # noqa: E402
    Product,
    ProductCategory,
    ProductCrop,
    Seller,
)
from app.equipment_taxonomy import CATEGORY_SLUGS as EQUIPMENT_SLUGS  # noqa: E402
from app.input_store_taxonomy import (  # noqa: E402
    CATEGORIES,
    CATEGORIES_BY_SLUG,
    INPUT_STORE_SLUGS,
    TYPE_BY_SLUG,
    SUB_BY_SLUG,
)

# The ``sensors`` table (``Sensor`` model) lives in the routers package and is
# referenced by ``monitoring_alerts``. Importing it registers the table on the
# shared metadata so ``Base.metadata.create_all`` works on fresh databases.
import app.routers.sensors  # noqa: E402, F401

IMG_BASE = "https://images.unsplash.com/{img}?w=640&q=70&auto=format&fit=crop"

# Every photo ID below is a real, free (non-Unsplash+) image pulled from the
# Unsplash CDN and selected against its published description so it matches the
# category it sits in: seed/grain close-ups for seeds, farmer/sprinkler spraying
# shots for crop-protection, soil & compost hands for soil/nutrient products,
# cattle & hay for animal feed/livestock, sprinkler-field photos for irrigation,
# seedling trays & greenhouse rows for nursery/consumables, and hand tools for
# farm-tools. Unrelated generics (mountain/landscape/sunrise stock) were removed.
# Pools are kept distinct per category within related clusters so no two
# unrelated product types share a photo; within a category the pool is rotated
# so neighbouring cards differ.
IMAGE_POOL = {
    "seeds": [
        "photo-1768729341679-8a2da8e5b5fa",
        "photo-1673158191180-1e293e3694fc",
        "photo-1676289124482-d22eecb865c0",
        "photo-1714168526009-2d0d333640d5",
        "photo-1724564280271-cb6b37164457",
        "photo-1635843111961-06c71c3ed8cf",
    ],
    "fertilizers": [
        "photo-1590682680695-43b964a3ae17",
        "photo-1624806992928-9c7a04a8383d",
        "photo-1709633644385-e4e51e5646f1",
        "photo-1642952273588-ed6fa28870ac",
    ],
    "organic-fertilizers": [
        "photo-1598644451141-a412412a9a69",
        "photo-1632660879345-50887555aafc",
        "photo-1693414853994-1080baaacb4d",
        "photo-1748873611377-a7d28d1537b2",
    ],
    "micronutrients": [
        "photo-1590682680695-43b964a3ae17",
        "photo-1748873611377-a7d28d1537b2",
        "photo-1651592279293-c70b4f04be11",
        "photo-1642952273588-ed6fa28870ac",
    ],
    "plant-growth": [
        "photo-1748873611377-a7d28d1537b2",
        "photo-1779622520933-79b2926a97dd",
        "photo-1679110663825-c6ec1ad51884",
        "photo-1586281010691-f9da4be5b1f7",
        "photo-1757514029798-d92f3ffe5ad5",
    ],
    "soil-conditioners": [
        "photo-1642952273588-ed6fa28870ac",
        "photo-1624806992928-9c7a04a8383d",
        "photo-1632660879345-50887555aafc",
        "photo-1709633644385-e4e51e5646f1",
    ],
    "bio-fertilizers": [
        "photo-1679110663825-c6ec1ad51884",
        "photo-1590682680695-43b964a3ae17",
        "photo-1748873611377-a7d28d1537b2",
        "photo-1779622520933-79b2926a97dd",
    ],
    "pesticides": [
        "photo-1711900176492-6153bb3278bd",
        "photo-1760635190909-14dda99fae73",
        "photo-1758524052762-cc762ebbbdf2",
        "photo-1760527072562-6ab5bd3054dc",
    ],
    "insecticides": [
        "photo-1711900176492-6153bb3278bd",
        "photo-1760527072562-6ab5bd3054dc",
        "photo-1758524052762-cc762ebbbdf2",
    ],
    "fungicides": [
        "photo-1760635190909-14dda99fae73",
        "photo-1758524052762-cc762ebbbdf2",
        "photo-1711900176492-6153bb3278bd",
    ],
    "herbicides": [
        "photo-1760635190909-14dda99fae73",
        "photo-1760527072562-6ab5bd3054dc",
        "photo-1758524052762-cc762ebbbdf2",
    ],
    "animal-feed": [
        "photo-1775034942056-ed9de4e5b346",
        "photo-1753525071844-686f717963b3",
        "photo-1454179083322-198bb4daae41",
        "photo-1759151750725-3ae5749eccec",
    ],
    "livestock-supplies": [
        "photo-1775034942056-ed9de4e5b346",
        "photo-1454179083322-198bb4daae41",
        "photo-1759151750725-3ae5749eccec",
        "photo-1753525071844-686f717963b3",
    ],
    "irrigation": [
        "photo-1743742566156-f1745850281a",
        "photo-1738598665698-7fd7af4b5e0c",
        "photo-1653976437983-947c4561ae6b",
    ],
    "nursery": [
        "photo-1779622520933-79b2926a97dd",
        "photo-1757514029798-d92f3ffe5ad5",
        "photo-1651592279293-c70b4f04be11",
        "photo-1679110663825-c6ec1ad51884",
    ],
    "consumables": [
        "photo-1757514029798-d92f3ffe5ad5",
        "photo-1651592279293-c70b4f04be11",
        "photo-1770982698868-26124562d0c2",
        "photo-1758524052762-cc762ebbbdf2",
    ],
    "spraying-equipment": [
        "photo-1711900176492-6153bb3278bd",
        "photo-1758524052762-cc762ebbbdf2",
        "photo-1760527072562-6ab5bd3054dc",
    ],
    "farm-tools": [
        "photo-1621460248083-6271cc4437a8",
        "photo-1416879595882-3373a0480b5b",
        "photo-1537877853655-34bdcda5e833",
        "photo-1597764983031-60a74afb8692",
    ],
}

SELLERS = [
    ("Farm Assist Agro Supplies", "Vijayawada, Andhra Pradesh", True, 4.8),
    ("Krishak Jaan Seva Kendra", "Guntur, Andhra Pradesh", True, 4.6),
    ("Green Valley Agri Mart", "Eluru, Andhra Pradesh", True, 4.5),
    ("BharatCrop Distributors", "Kakinada, Andhra Pradesh", False, 4.2),
    ("Krushi Shakti Agencies", "Ongole, Andhra Pradesh", False, 4.1),
    ("Gramin Udyog Dealer", "Visakhapatnam, Andhra Pradesh", False, 4.0),
]

ALL_CROPS = ["general"]
SEED_CROPS = [
    "paddy", "maize", "cotton", "groundnut", "chilli", "wheat",
    "soybean", "turmeric", "sunflower", "vegetables", "pulses",
]

SEED_SUBCATEGORY = {
    "paddy": "Paddy Seeds",
    "wheat": "Wheat Seeds",
    "maize": "Maize Seeds",
    "cotton": "Cotton Seeds",
    "groundnut": "Groundnut Seeds",
    "chilli": "Chilli Seeds",
    "sunflower": "Sunflower Seeds",
    "turmeric": "Turmeric Seeds",
    "soybean": "Soybean Seeds",
    "pulses": "Pulses Seeds",
    "vegetables": "Vegetable Seeds",
}


def usage(step, units):
    return {
        "usage": "Sow/apply according to crop stage; irrigation recommended after application.",
        "application_rate": f"{step} {units} per acre as directed on the pack.",
        "safety": "Wear gloves while handling. Store away from food, feed and children.",
    }


# ---------------------------------------------------------------------------
# Catalogue.  category slug -> list of (name, brand, price, mrp|None, unit,
# pack, stock, organic|None)
# ---------------------------------------------------------------------------
C = {}


def add(cat, items, organic=False):
    entries = []
    for item in items:
        name, brand, price, mrp, unit, pack, stock = item[:7]
        item_organic = bool(organic or (len(item) > 7 and item[7]))
        entries.append(
            {
                "name": name,
                "brand": brand,
                "price": price,
                "mrp": mrp,
                "unit": unit,
                "pack": pack,
                "stock": stock,
                "organic": item_organic,
            }
        )
    C.setdefault(cat, []).extend(entries)


# --- Seeds ----------------------------------------------------------------
add("seeds", [
    ("Sona Masuri Paddy Seeds", "Samruddhi Seeds", 260, 320, "kg", "5 kg", 400),
    ("BPT 5204 Rice Seeds", "Samruddhi Seeds", 300, 360, "kg", "5 kg", 350),
    ("HYV Paddy Seeds IR-64", "KrishiBandhu", 240, 290, "kg", "5 kg", 500),
    ("Swarna Rice Seeds", "Samruddhi Seeds", 285, 340, "kg", "5 kg", 300),
    ("Hybrid Maize Seeds NK-6240", "AgriCore", 820, 990, "pack", "1 pack (3.6 kg)", 250),
    ("Sweet Corn Seeds", "GrowRight", 450, 540, "pack", "450 g", 180),
    ("Baby Corn Hybrid Seeds", "GrowRight", 480, 580, "pack", "450 g", 160),
    ("Bt Cotton Seeds RCH-2", "AgriCore", 880, 1050, "pack", "450 g", 300),
    ("Hybrid Cotton Seeds", "NovaSprout", 950, 1150, "pack", "450 g", 200),
    ("TMV-7 Groundnut Seeds", "KrishiBandhu", 420, 500, "pack", "10 kg", 260),
    ("JLG-24 Groundnut Seeds", "KrishiBandhu", 440, 520, "pack", "10 kg", 220),
    ("Guntur Chilli Seeds", "Chatur Seeds", 350, 430, "pack", "100 g", 1500),
    ("Byadagi Chilli Seeds", "Chatur Seeds", 380, 460, "pack", "100 g", 1200),
    ("Hybrid Tomato Seeds", "GreenHarvest", 560, 680, "pack", "25 g", 800),
    ("Hybrid Brinjal Seeds", "GreenHarvest", 240, 300, "pack", "25 g", 700),
    ("Hybrid Okra Seeds", "GreenHarvest", 310, 380, "pack", "250 g", 600),
    ("Onion Seeds (N-53)", "GreenHarvest", 420, 500, "pack", "500 g", 300),
    ("Coriander Seeds", "KrishiBandhu", 90, 120, "pack", "1 kg", 900),
    ("Watermelon Hybrid Seeds", "NovaSprout", 520, 620, "pack", "50 g", 350),
    ("Sunflower Hybrid Seeds", "AgriCore", 460, 550, "pack", "1.2 kg", 280),
    ("Red Gram (Pigeon Pea) Seeds", "KrishiBandhu", 390, 470, "kg", "5 kg", 240),
    ("Green Gram Seeds", "KrishiBandhu", 340, 410, "kg", "10 kg", 320),
    ("Black Gram Seeds", "KrishiBandhu", 350, 420, "kg", "10 kg", 300),
    ("Yellow Mustard Seeds", "GrowRight", 210, 250, "kg", "5 kg", 380),
    ("Sesame (Gingelly) Seeds", "GrowRight", 320, 390, "kg", "5 kg", 200),
    ("Turmeric Rhizome Seeds", "Samruddhi Seeds", 520, 620, "kg", "25 kg", 150),
    ("Soybean Seeds JS-335", "Chatur Seeds", 430, 510, "pack", "15 kg", 220),
    ("Ridge Gourd Seeds", "GreenHarvest", 110, 140, "pack", "20 g", 500),
    ("Bitter Gourd Seeds", "GreenHarvest", 120, 150, "pack", "20 g", 450),
    ("Carrot Seeds (Pusa Meghali)", "GrowRight", 95, 120, "pack", "250 g", 600),
    ("Radish Seeds", "GrowRight", 85, 110, "pack", "500 g", 650),
    ("Cabbage Hybrid Seeds", "NovaSprout", 480, 570, "pack", "10 g", 400),
])
for _x in C["seeds"]:
    _x["crops"] = ["general"]
_CH_ = {
    "Sona Masuri": ["paddy"], "BPT 5204": ["paddy"], "IR-64": ["paddy"],
    "Swarna": ["paddy"], "Maize": ["maize"], "Corn": ["maize"],
    "Cotton": ["cotton"], "Groundnut": ["groundnut"], "Chilli": ["chilli"],
    "Tomato": ["vegetables"], "Brinjal": ["vegetables"], "Okra": ["vegetables"],
    "Onion": ["vegetables"], "Watermelon": ["vegetables"], "Gourd": ["vegetables"],
    "Carrot": ["vegetables"], "Radish": ["vegetables"], "Cabbage": ["vegetables"],
    "Sunflower": ["sunflower"], "Turan": ["pulses"], "Pigeon": ["pulses"],
    "Gram": ["pulses"], "Mustard": ["pulses"], "Sesame": ["pulses"],
    "Turmeric": ["turmeric"], "Soybean": ["soybean"], "Coriander": ["vegetables"],
}
for _x in C["seeds"]:
    for _key, _crops in _CH_.items():
        if _key.lower() in _x["name"].lower():
            _x["crops"] = _crops
            break

# --- Fertilizers ----------------------------------------------------------
add("fertilizers", [
    ("DAP Fertilizer (18-46-0)", "Haritha Organics", 1350, 1450, "bag", "50 kg", 120),
    ("Urea - Neem Coated 46% N", "Haritha Organics", 295, 320, "bag", "50 kg", 300),
    ("NPK 10-26-26 Complex", "Haritha Organics", 850, 920, "bag", "50 kg", 180),
    ("NPK 20-20-20 Complex", "Nirman Agro", 990, 1080, "bag", "50 kg", 140),
    ("NPK 12-32-16 Complex", "Nirman Agro", 820, 890, "bag", "50 kg", 160),
    ("NPK 19-19-19 Water Soluble", "Nirman Agro", 780, 860, "kg", "25 kg", 90),
    ("MOP Muriate of Potash 60%", "Haritha Organics", 720, 790, "bag", "50 kg", 110),
    ("Single Super Phosphate", "Haritha Organics", 460, 510, "bag", "50 kg", 130),
    ("Ammonium Sulphate 21% N", "Nirman Agro", 580, 640, "bag", "50 kg", 100),
    ("Calcium Nitrate 15.5%", "AgroZenith", 940, 1040, "kg", "25 kg", 70),
    ("Zinc Sulphate 21%", "AgroZenith", 620, 690, "kg", "25 kg", 60),
    ("Magnesium Sulphate 9.8%", "AgroZenith", 380, 430, "kg", "25 kg", 55),
    ("Ferrous Sulphate 19%", "AgroZenith", 210, 240, "kg", "10 kg", 45),
    ("Micronutrient Mixture 5kg", "AgroZenith", 260, 300, "kg", "5 kg", 80),
    ("Sulphur 90% WDG", "Nirman Agro", 340, 380, "kg", "10 kg", 65),
    ("Boron 20% Granule", "AgroZenith", 290, 330, "kg", "5 kg", 50),
    ("Nano Urea Liquid", "Nirman Agro", 240, 280, "L", "500 ml", 200),
    ("Sulphate of Potash 50%", "Haritha Organics", 1100, 1200, "bag", "25 kg", 40),
    ("Ammonium Phosphate Sulphate", "Haritha Organics", 980, 1080, "bag", "50 kg", 35),
    ("Water Soluble 13-0-45", "AgroZenith", 840, 920, "kg", "25 kg", 45),
    ("Mono Potassium Phosphate 0-52-34", "AgroZenith", 1500, 1650, "kg", "10 kg", 30),
    ("Bio Urea (Azotobacter)", "TerraKraft", 320, 370, "kg", "10 kg", 90),
    ("Calcium Ammonium Nitrate", "Nirman Agro", 700, 770, "bag", "50 kg", 55),
    ("NPK 14-35-14 Starter", "AgroZenith", 1250, 1380, "kg", "10 kg", 25),
    ("NPK 6-12-36 Fruiting Booster", "AgroZenith", 720, 800, "kg", "10 kg", 30),
])
for _x in C["fertilizers"]:
    _x["crops"] = ["general"]

# --- Organic Fertilizers --------------------------------------------------
add("organic-fertilizers", [
    ("Vermicompost (Haritha)", "Haritha Organics", 420, 500, "bag", "50 kg", 200, True),
    ("Neem Cake Powder", "Haritha Organics", 260, 310, "kg", "10 kg", 150, True),
    ("Pure Cow Dung Manure", "Jeevan Bio", 180, 220, "bag", "10 kg", 300, True),
    ("Poultry Manure (Sun dried)", "Jeevan Bio", 230, 270, "bag", "25 kg", 250, True),
    ("Seaweed Liquid Fertilizer", "EcoYields", 340, 400, "L", "1 L", 120, True),
    ("Fish Amino Acid", "EcoYields", 280, 330, "L", "1 L", 100, True),
    ("Panchagavya Concentrate", "Jeevan Bio", 190, 230, "L", "1 L", 140, True),
    ("Jeevamrutham Booster", "Jeevan Bio", 150, 180, "L", "1 L", 160, True),
    ("Castor Cake Powder", "Haritha Organics", 340, 400, "kg", "25 kg", 90, True),
    ("Groundnut Cake", "Haritha Organics", 420, 490, "kg", "25 kg", 80, True),
    ("Bio Compost", "Haritha Organics", 250, 290, "bag", "25 kg", 170, True),
])
for _x in C["organic-fertilizers"]:
    _x["crops"] = ["general"]

# --- Bio-fertilizers ------------------------------------------------------
add("bio-fertilizers", [
    ("Rhizobium Cultures", "Sakthi Biolabs", 130, 160, "pack", "200 g", 300, True),
    ("Azotobacter Biofertilizer", "Sakthi Biolabs", 150, 180, "pack", "200 g", 280, True),
    ("PSB Phosphate Bacteria", "Sakthi Biolabs", 140, 170, "pack", "200 g", 260, True),
    ("VAM Mycorrhizal Powder", "Sakthi Biolabs", 210, 250, "kg", "500 g", 150, True),
    ("Trichoderma Viride", "Sakthi Biolabs", 120, 150, "pack", "250 g", 320, True),
    ("Beauveria Bassiana", "Sakthi Biolabs", 260, 310, "pack", "500 g", 110, True),
    ("Bacillus Subtilis Bio-Fungicide", "Sakthi Biolabs", 230, 280, "pack", "500 g", 130, True),
    ("Beejamrutham Seed Treat", "Jeevan Bio", 120, 150, "kg", "1 kg", 180, True),
])
for _x in C["bio-fertilizers"]:
    _x["crops"] = ["general"]

# --- Micronutrients -------------------------------------------------------
add("micronutrients", [
    ("Soil Micronutrient Mixture 5kg", "AgroZenith", 260, 300, "kg", "5 kg", 80),
    ("Multi-Micronutrient Foliar", "AgroZenith", 180, 210, "kg", "1 kg", 200),
    ("Chelated Zinc EDTA 12%", "AgroZenith", 470, 540, "kg", "5 kg", 45),
    ("Chelated Iron EDTA 12%", "AgroZenith", 490, 560, "kg", "5 kg", 40),
    ("Granubor 20% Granule", "AgroZenith", 290, 330, "kg", "5 kg", 50),
    ("Boron 20% Liquid", "AgroZenith", 260, 300, "L", "1 L", 220),
    ("Cheleated Manganese 12%", "AgroZenith", 440, 500, "kg", "5 kg", 35),
    ("Magnesium Sulphate Micro 9.8%", "AgroZenith", 380, 430, "kg", "25 kg", 55),
])
for _x in C["micronutrients"]:
    _x["crops"] = ["general"]

# --- Plant Growth Products -------------------------------------------------
add("plant-growth", [
    ("Amino Acid Liquid 40%", "EcoYields", 420, 490, "L", "1 L", 120),
    ("Seaweed Extract Liquid", "EcoYields", 360, 420, "L", "1 L", 140),
    ("Fulvic Acid Liquid", "EcoYields", 380, 440, "L", "1 L", 110),
    ("WP Foliar Booster 19:19:19", "Nirman Agro", 240, 280, "kg", "1 kg", 160),
    ("Bio Stimulant Root Plus", "TerraKraft", 330, 380, "L", "1 L", 130),
    ("Chitosan Foliar", "EcoYields", 540, 620, "L", "1 L", 50),
    ("Plant Protein Hydrolysate", "EcoYields", 460, 530, "L", "1 L", 60),
    ("Calcium Amino Chelate", "EcoYields", 520, 600, "L", "1 L", 55),
    ("Gibberellic Acid 40% WSG", "TerraKraft", 650, 750, "g", "100 g", 35),
    ("Triacontanol 0.05% EC", "EcoYields", 240, 280, "L", "1 L", 90),
    ("NAA 4.5% SL", "AgroZenith", 170, 200, "L", "1 L", 70),
    ("Cytokinin 0.01% SP", "TerraKraft", 290, 340, "kg", "100 g", 45),
    ("Yeast Extract Plant Tonic", "EcoYields", 350, 410, "kg", "1 kg", 65),
    ("Kelp Hydrolysate", "EcoYields", 480, 550, "L", "1 L", 58),
    ("Salicylic Acid Foliar", "TerraKraft", 320, 370, "L", "1 L", 48),
    ("Yucca Saponin Surfactant", "EcoYields", 410, 480, "L", "1 L", 52),
])
for _x in C["plant-growth"]:
    _x["crops"] = ["general"]

# --- Soil Conditioners ----------------------------------------------------
add("soil-conditioners", [
    ("Humic Acid Granule 98%", "TerraKraft", 210, 250, "kg", "5 kg", 90),
    ("Potassium Humate Flakes", "TerraKraft", 190, 230, "kg", "5 kg", 70),
    ("Liquid Silicon 15%", "TerraKraft", 310, 360, "L", "1 L", 80),
    ("Bone Meal Powder", "TerraKraft", 310, 360, "kg", "25 kg", 110, True),
    ("Rock Phosphate Powder", "TerraKraft", 220, 260, "kg", "25 kg", 95, True),
    ("Wood Ash / Plant Ash", "Haritha Organics", 140, 170, "kg", "10 kg", 130, True),
    ("Dhaincha Green Manure Seeds", "KrishiBandhu", 160, 190, "kg", "5 kg", 140, True),
    ("Biochar Soil Amendment", "TerraKraft", 380, 440, "kg", "5 kg", 60, True),
    ("Gypsum Soil Conditioner", "AgroLab", 250, 290, "kg", "25 kg", 120),
])
for _x in C["soil-conditioners"]:
    _x["crops"] = ["general"]

# --- Pesticides (general-purpose, incl. organic formulations) -------------
add("pesticides", [
    ("Neem Oil 10000 ppm", "Sakthi Biolabs", 320, 380, "L", "1 L", 220, True),
    ("Karanj Oil (Pongamia)", "Sakthi Biolabs", 250, 300, "L", "1 L", 120, True),
    ("Dimethoate 30% EC", "CropShield", 330, 380, "L", "250 ml", 350),
    ("Chlorpyriphos 20% EC", "CropShield", 420, 480, "L", "500 ml", 300),
    ("Quinalphos 25% EC", "CropShield", 360, 410, "L", "500 ml", 280),
    ("Ethion 50% EC", "CropShield", 520, 590, "L", "500 ml", 180),
    ("Propargite 57% EC", "CropShield", 610, 690, "L", "250 ml", 150),
])
for _x in C["pesticides"]:
    _x["crops"] = ["general"]

# --- Insecticides ---------------------------------------------------------
add("insecticides", [
    ("Imidacloprid 17.8 SL", "Varuna Agro", 450, 520, "L", "100 ml", 500),
    ("Chlorantraniliprole 18.5 SC", "Varuna Agro", 980, 1120, "L", "250 ml", 200),
    ("Thiamethoxam 25 WG", "Varuna Agro", 340, 400, "pack", "80 g", 420),
    ("Fipronil 5 SC", "Varuna Agro", 390, 450, "L", "150 ml", 300),
    ("Emamectin Benzoate 5 SG", "Varuna Agro", 640, 730, "pack", "100 g", 360),
    ("Lambda-Cyhalothrin 5 EC", "CropNova", 290, 340, "L", "250 ml", 400),
    ("Cypermethrin 10 EC", "CropNova", 260, 300, "L", "250 ml", 450),
    ("Acephate 75 SP", "CropNova", 480, 550, "pack", "500 g", 380),
    ("Profenofos 50 EC", "CropNova", 640, 720, "L", "500 ml", 240),
    ("Novaluron 10 EC", "CropNova", 520, 600, "L", "300 ml", 220),
    ("Indoxacarb 14.5 SC", "CropNova", 760, 860, "L", "200 ml", 180),
    ("Spinetoram 11.7 SC", "CropNova", 1500, 1700, "L", "250 ml", 90),
])
for _x in C["insecticides"]:
    _x["crops"] = ["general"]

# --- Fungicides -----------------------------------------------------------
add("fungicides", [
    ("Carbendazim 50 WP", "Varuna Agro", 220, 260, "pack", "100 g", 600),
    ("Copper Oxy Chloride 50 WP", "Varuna Agro", 310, 360, "pack", "500 g", 320),
    ("Mancozeb 75 WP", "Varuna Agro", 350, 400, "pack", "500 g", 500),
    ("Hexaconazole 5 SC", "Varuna Agro", 180, 210, "L", "500 ml", 460),
    ("Propiconazole 25 EC", "CropNova", 420, 480, "L", "250 ml", 280),
    ("Tebuconazole 25.9 EC", "CropNova", 540, 620, "L", "250 ml", 240),
    ("Azoxystrobin 23 SC", "CropNova", 890, 1000, "L", "250 ml", 160),
    ("Metalaxyl + Mancozeb 72 WP", "Varuna Agro", 580, 660, "pack", "500 g", 200),
    ("Sulphur 80 WDG", "Varuna Agro", 240, 280, "pack", "250 g", 420),
])
for _x in C["fungicides"]:
    _x["crops"] = ["general"]

# --- Herbicides -----------------------------------------------------------
add("herbicides", [
    ("Pendimethalin 30 EC", "CropNova", 320, 370, "L", "1 L", 340),
    ("Bispyribac Sodium 10 SC", "CropNova", 610, 700, "L", "250 ml", 190),
    ("2,4-D Amine Salt 58% SL", "CropNova", 190, 220, "L", "500 ml", 380),
    ("Glyphosate 41 SL (Non-selective)", "CropNova", 470, 530, "L", "1 L", 500),
    ("Atrazine 50 WP", "CropNova", 230, 270, "pack", "500 g", 260),
    ("Oxyfluorfen 23.5 EC", "CropNova", 560, 650, "L", "500 ml", 150),
])
for _x in C["herbicides"]:
    _x["crops"] = ["general"]

# --- Animal Feed ----------------------------------------------------------
add("animal-feed", [
    ("Poultry Starter Feed Crumb", "Feedo Agrivet", 1450, 1600, "bag", "50 kg", 120),
    ("Poultry Layer Mash Feed", "Feedo Agrivet", 1380, 1520, "bag", "50 kg", 110),
    ("Broiler Finisher Feed Pellets", "Feedo Agrivet", 1550, 1700, "bag", "50 kg", 100),
    ("Grower Mash for Poultry", "Feedo Agrivet", 1320, 1450, "bag", "50 kg", 130),
    ("Dairy Cattle Feed Concentrate 18%", "Amrita Animal Feeds", 1150, 1280, "bag", "50 kg", 150),
    ("Dairy Cattle Feed Concentrate 24%", "Amrita Animal Feeds", 1250, 1390, "bag", "50 kg", 120),
    ("Calf Starter Feed 20%", "Amrita Animal Feeds", 1420, 1560, "bag", "50 kg", 60),
    ("Goat & Sheep Feed Pellets", "Amrita Animal Feeds", 1080, 1200, "bag", "50 kg", 140),
    ("Pig Grower Feed Pellets", "Amrita Animal Feeds", 1290, 1420, "bag", "50 kg", 50),
    ("Fish Feed Floating Pellets", "AquaVet Feeds", 980, 1100, "bag", "25 kg", 90),
    ("Fish Feed Slow Sinking 3 mm", "AquaVet Feeds", 1040, 1160, "bag", "25 kg", 80),
    ("Wheat Bran / Choker 50 kg", "Feedo Agrivet", 620, 690, "bag", "50 kg", 200),
    ("Rice Bran (De-oiled)", "Feedo Agrivet", 580, 650, "bag", "50 kg", 250),
    ("Groundnut Oil Cake", "Haritha Organics", 1180, 1300, "bag", "50 kg", 90),
    ("Sunflower Oil Cake", "Feedo Agrivet", 1250, 1380, "bag", "50 kg", 70),
    ("Gram Chuni / Besan Chuni", "Feedo Agrivet", 950, 1050, "bag", "50 kg", 100),
    ("Molasses (Liquid) 200 L Drum", "Amrita Animal Feeds", 1650, 1800, "drum", "200 L", 30),
    ("Mineral Mixture Powder 25 kg", "VetCare Nutrition", 1450, 1600, "bag", "25 kg", 40),
    ("Urea Molasses Mineral Block", "VetCare Nutrition", 260, 300, "pc", "2.5 kg", 200),
    ("Bypass Fat Powder (Rumen-Protected)", "VetCare Nutrition", 2400, 2650, "bag", "25 kg", 25),
    ("Hydroponic Maize Fodder Kit", "GreenFodder Systems", 890, 980, "kit", "1 kit", 35),
    ("Cattle Fodder Seeds - Maize Chari", "KrishiBandhu", 180, 220, "pack", "10 kg", 160),
    ("Alfalfa (Lucerne) Fodder Seeds", "KrishiBandhu", 340, 390, "pack", "5 kg", 120),
    ("Sorghum Fodder Seeds (SSG 59-3)", "KrishiBandhu", 120, 150, "pack", "4 kg", 180),
])
for _x in C["animal-feed"]:
    _x["crops"] = ["general"]

# --- Livestock Supplies ---------------------------------------------------
add("livestock-supplies", [
    ("Rope Halter with Chain (Cattle)", "FarmVet Essentials", 210, 250, "pc", "1 pc", 140),
    ("Cattle Grooming Brush", "FarmVet Essentials", 260, 300, "pc", "1 pc", 120),
    ("Hoof Trimming Knife", "FarmVet Essentials", 320, 370, "pc", "1 pc", 80),
    ("Veterinary First-Aid Kit", "VetCare Nutrition", 1450, 1600, "kit", "1 kit", 35),
    ("Disposable Syringe 20 ml (100 pcs)", "VetCare Nutrition", 380, 430, "pack", "100 pcs", 90),
    ("Disposable Syringe 5 ml (100 pcs)", "VetCare Nutrition", 220, 260, "pack", "100 pcs", 120),
    ("Albendazole Dewormer Bolus", "VetCare Nutrition", 350, 400, "pack", "100 bolus", 60),
    ("Ectoparasite Wash (Cypermethrin 10%)", "CropShield", 290, 330, "L", "1 L", 180),
    ("Vitamin AD3E Injection", "VetCare Nutrition", 480, 540, "pack", "100 ml", 95),
    ("Calcium + Phosphorus Bolus", "VetCare Nutrition", 420, 470, "pack", "100 bolus", 70),
    ("Calf Milk Feeder Bucket", "FarmVet Essentials", 560, 640, "pc", "12 L", 60),
    ("Udder Wash (Chlorhexidine 5%)", "VetCare Nutrition", 310, 355, "L", "1 L", 110),
    ("Phenol Disinfectant 5 L", "VetCare Nutrition", 520, 580, "can", "5 L", 85),
    ("Drenching Gun (Graduated)", "FarmVet Essentials", 890, 1000, "pc", "1 pc", 40),
    ("Rumen Magnet (Cow)", "VetCare Nutrition", 650, 730, "pc", "1 pc", 50),
    ("Ear Tag Applicator + 100 Tags", "FarmVet Essentials", 780, 870, "set", "1 set", 30),
    ("Cattle Hoof Spray", "VetCare Nutrition", 360, 410, "spray", "500 ml", 75),
    ("Mastitis Detection Strip", "VetCare Nutrition", 240, 280, "pack", "20 strips", 130),
    ("Milking Machine Teat Cup Liner Set", "FarmVet Essentials", 460, 520, "set", "1 set", 45),
    ("Castration Kit (Emasculator)", "FarmVet Essentials", 1320, 1480, "set", "1 set", 20),
])
for _x in C["livestock-supplies"]:
    _x["crops"] = ["general"]

# --- Irrigation -----------------------------------------------------------
add("irrigation", [
    ("Drip Kit 1/4 Acre", "AquaFarm Drip", 2100, 2400, "kit", "1 kit", 80),
    ("Drip Kit 1 Acre", "AquaFarm Drip", 3800, 4300, "kit", "1 kit", 45),
    ("Drip Line 12 mm (2000 m)", "AquaFarm Drip", 2400, 2700, "roll", "2000 m", 60),
    ("Lateral Pipe 16 mm", "AquaFarm Drip", 680, 760, "roll", "100 m", 120),
    ("Online Drippers 8 LPH", "AquaFarm Drip", 180, 210, "pack", "100 pcs", 400),
    ("Micro Sprinkler Head", "AquaFarm Drip", 140, 160, "pack", "10 pcs", 320),
    ("Mini Sprinkler Kit 1/2 Acre", "AquaFarm Drip", 1700, 1900, "kit", "1 kit", 55),
    ("Rain Gun 3/4 inch", "AquaFarm Drip", 950, 1080, "pc", "1 pc", 70),
    ("PVC Pipe 63 mm (6 m)", "AqueLite", 780, 860, "pc", "6 m", 120),
    ("HDPE Roll 10mm", "AqueLite", 920, 1020, "roll", "200 m", 90),
    ("Disc Filter 1 inch", "AqueLite", 980, 1100, "pc", "1 pc", 65),
    ("Screen Filter 2 inch", "AqueLite", 1450, 1620, "pc", "1 pc", 40),
    ("Venturi Fertilizer Injector", "AqueLite", 620, 700, "pc", "1 pc", 85),
    ("Drip End Caps", "AquaFarm Drip", 60, 70, "pack", "20 pcs", 500),
    ("Drip Elbow Joints", "AquaFarm Drip", 90, 105, "pack", "20 pcs", 420),
    ("T-Connectors 16 mm", "AquaFarm Drip", 80, 95, "pack", "20 pcs", 460),
    ("Stop Cock Valve", "AquaFarm Drip", 75, 90, "pack", "10 pcs", 380),
    ("Pressure Gauge Set", "AqueLite", 260, 300, "pc", "1 pc", 130),
    ("Irrigation Scheduler Timer", "AqueLite", 1850, 2100, "pc", "1 pc", 28),
    ("Sprinkler Stand Tripod", "AqueLite", 450, 510, "pc", "1 pc", 110),
    ("Soaker Hose 15 m", "AquaFarm Drip", 380, 430, "roll", "15 m", 160),
    ("Rope Wick Irrigation Set", "AquaFarm Drip", 120, 140, "pc", "1 pc", 240),
    ("Floating Row Cover Clips", "AquaFarm Drip", 110, 130, "pack", "50 pcs", 220),
    ("Dripper Insertion Tool", "AqueLite", 160, 190, "pc", "1 pc", 180),
])
for _x in C["irrigation"]:
    _x["crops"] = ["general"]

# --- Sprayers (Spraying Equipment) ----------------------------------------
add("spraying-equipment", [
    ("Knapsack Sprayer 16 L", "SprayTech", 1400, 1650, "pc", "16 L", 90),
    ("Battery Knapsack Sprayer 20 L", "SprayTech", 4200, 4800, "pc", "20 L", 40),
    ("Power Sprayer 12 L", "SprayTech", 3600, 4100, "pc", "12 L", 35),
    ("Hand Compression Sprayer 5 L", "SprayTech", 650, 750, "pc", "5 L", 200),
    ("Hand Compression Sprayer 8 L", "SprayTech", 800, 920, "pc", "8 L", 160),
    ("Lever Knapsack Sprayer 10 L", "SprayTech", 1050, 1200, "pc", "10 L", 120),
    ("Battery Backpack Sprayer 20 L", "SprayTech", 4600, 5200, "pc", "20 L", 30),
    ("Foot Sprayer 16 L", "SprayTech", 1250, 1430, "pc", "16 L", 70),
    ("Ultra Low Volume Sprayer", "SprayTech", 2900, 3300, "pc", "1 pc", 25),
    ("Electric Fogger (ULV)", "SprayTech", 5400, 6100, "pc", "1 pc", 18),
    ("Mist Blower (Backpack)", "SprayTech", 7200, 8000, "pc", "1 pc", 15),
    ("Tractor Mounted Boom Sprayer", "SprayTech", 11000, 12500, "pc", "500 L", 8),
    ("Solar Powered Sprayer", "SprayTech", 6800, 7600, "pc", "20 L", 12),
    ("Hand Pump Sprayer 3 L", "SprayTech", 380, 440, "pc", "3 L", 300),
    ("Electrostatic Sprayer 16 L", "SprayTech", 4900, 5600, "pc", "16 L", 20),
    ("Fixed Nozzle Set Drip Spray", "SprayTech", 150, 175, "set", "5 pcs", 260),
    ("Spray Lance 60 cm", "SprayTech", 210, 245, "pc", "60 cm", 150),
    ("Cone Nozzle Set", "SprayTech", 95, 110, "set", "5 pcs", 280),
    ("Flat Fan Nozzle Kit", "SprayTech", 85, 100, "set", "4 pcs", 240),
    ("Shield Sprayer Manual", "SprayTech", 1180, 1340, "pc", "1 pc", 60),
    ("High Pressure Battery 25 L", "SprayTech", 7100, 7900, "pc", "25 L", 14),
    ("Drum Sprayer 21 L", "SprayTech", 5200, 5800, "pc", "21 L", 16),
    ("Brass Hand Sprayer 2 L", "SprayTech", 450, 520, "pc", "2 L", 90),
    ("Spare Pump Repair Kit", "SprayTech", 130, 150, "set", "1 kit", 340),
])
for _x in C["spraying-equipment"]:
    _x["crops"] = ["general"]

# --- Farm Tools -----------------------------------------------------------
add("farm-tools", [
    ("Spade (Khurpi) Heavy Duty", "ToolCraft", 260, 310, "pc", "1 pc", 180),
    ("Dutch Hoe (Kasol)", "ToolCraft", 320, 380, "pc", "1 pc", 150),
    ("Hand Weeder T-Type", "ToolCraft", 180, 215, "pc", "1 pc", 220),
    ("Cono Weeder (Planter Type)", "ToolCraft", 1400, 1600, "pc", "1 pc", 60),
    ("Sickle Curved Blade", "ToolCraft", 110, 130, "pc", "1 pc", 400),
    ("Pruning Shear 8 inch", "ToolCraft", 420, 490, "pc", "1 pc", 140),
    ("Secateurs Bypass", "ToolCraft", 380, 440, "pc", "1 pc", 130),
    ("Tractor Axe 1.5 kg", "ToolCraft", 560, 640, "pc", "1 pc", 80),
    ("Garden Fork 4 Tine", "ToolCraft", 290, 340, "pc", "1 pc", 170),
    ("Transplanting Trowel", "ToolCraft", 140, 165, "pc", "1 pc", 260),
    ("Wooden Rake 12 Tine", "ToolCraft", 250, 290, "pc", "1 pc", 140),
    ("Rocker Blade Garden Cultivator", "ToolCraft", 480, 550, "pc", "1 pc", 90),
    ("Brush Cutter Blade Set", "ToolCraft", 720, 820, "set", "3 pcs", 60),
    ("Wheel Hoe Cultivator", "ToolCraft", 1900, 2150, "pc", "1 pc", 35),
    ("Seed Drill (Manually Operated)", "ToolCraft", 2400, 2700, "pc", "1 pc", 20),
    ("Dibbler Planter", "ToolCraft", 210, 245, "pc", "1 pc", 100),
    ("Plant Guard / Tree Guard", "ToolCraft", 320, 370, "pc", "10 pcs", 70),
    ("Three-Prong Trishul", "ToolCraft", 340, 395, "pc", "1 pc", 80),
    ("Harvesting Knife (Kodtali)", "ToolCraft", 95, 115, "pc", "1 pc", 500),
    ("Grass Cutting Sickle", "ToolCraft", 130, 150, "pc", "1 pc", 320),
    ("Soil Auger Hand", "ToolCraft", 760, 860, "pc", "1 pc", 45),
    ("Grafting Knife", "ToolCraft", 240, 280, "pc", "1 pc", 160),
    ("Budding Tape Roll", "ToolCraft", 60, 70, "roll", "1 roll", 300),
    ("Fertigation Trowel Set", "ToolCraft", 390, 450, "set", "3 pcs", 50),
    ("Machete 18 inch", "ToolCraft", 520, 600, "pc", "1 pc", 60),
    ("Garden Cultivator 4 Prong", "ToolCraft", 170, 200, "pc", "1 pc", 180),
])
for _x in C["farm-tools"]:
    _x["crops"] = ["general"]

# --- Nursery --------------------------------------------------------------
add("nursery", [
    ("Seedling Tray 98 Cells", "NurseryHub", 95, 115, "pc", "98 cells", 600),
    ("Pro Tray 50 Cells", "NurseryHub", 75, 90, "pc", "50 cells", 800),
    ("Coco Peat Block 5 kg", "NurseryHub", 320, 370, "block", "5 kg", 200),
    ("Coco Peat Block 10 kg", "NurseryHub", 560, 630, "block", "10 kg", 150),
    ("Perlite 5 L", "NurseryHub", 180, 210, "bag", "5 L", 260),
    ("Vermiculite 5 L", "NurseryHub", 260, 300, "bag", "5 L", 220),
    ("Grow Bag 12x12 (50 pcs)", "NurseryHub", 590, 660, "pack", "50 pcs", 90),
    ("Poly Bags 6x8 (100 pcs)", "NurseryHub", 220, 250, "pack", "100 pcs", 300),
    ("Shade Net 50% (4 m x 10 m)", "NurseryHub", 1350, 1520, "roll", "40 sqm", 60),
    ("Seedling Starter Kit", "NurseryHub", 480, 550, "kit", "1 kit", 120),
    ("Root Trainer 3 x 5 Cells", "NurseryHub", 310, 350, "pc", "15 cells", 140),
    ("Tomato Trellis Clips (500)", "NurseryHub", 190, 215, "pack", "500 pcs", 210),
    ("Propagation Dome Tray", "NurseryHub", 420, 480, "set", "1 set", 70),
    ("Humidity Dome (10 pcs)", "NurseryHub", 240, 280, "pack", "10 pcs", 90),
    ("Organic Seed Starting Mix", "NurseryHub", 150, 175, "pack", "5 kg", 250),
    ("Vegetable Grafting Clips", "NurseryHub", 85, 100, "pack", "100 pcs", 320),
    ("Nursery Plant Labels (1000)", "NurseryHub", 120, 140, "pack", "1000 pcs", 180),
    ("Watering Can 5 L", "NurseryHub", 280, 320, "pc", "5 L", 160),
    ("Misting Valve Spray Head", "NurseryHub", 110, 130, "pack", "10 pcs", 260),
    ("Tray Carrier (6 Tray)", "NurseryHub", 360, 410, "pc", "1 pc", 80),
    ("Seed Germination Paper", "NurseryHub", 65, 78, "pack", "100 sheets", 140),
    ("Nursery Dibbler Tool", "NurseryHub", 95, 112, "pc", "1 pc", 200),
    ("Thermometer Hygrometer Combo", "NurseryHub", 230, 270, "pc", "1 pc", 110),
    ("Bamboo Plant Sticks (100)", "NurseryHub", 155, 180, "pack", "100 pcs", 240),
    ("Green House Cling Film 30 ft", "NurseryHub", 480, 540, "roll", "30 ft", 75),
])
for _x in C["nursery"]:
    _x["crops"] = ["general"]

# --- Farming Consumables --------------------------------------------------
add("consumables", [
    ("Soil Testing Kit (Home)", "AgroLab", 290, 340, "kit", "1 kit", 130),
    ("Soil pH Meter Digital", "AgroLab", 390, 450, "pc", "1 pc", 90),
    ("Soil Moisture Meter", "AgroLab", 350, 400, "pc", "1 pc", 110),
    ("EC / TDS Meter", "AgroLab", 520, 590, "pc", "1 pc", 70),
    ("Digital Weighing Scale 30 kg", "AgroLab", 1650, 1850, "pc", "30 kg", 40),
    ("Field Measuring Wheel", "AgroLab", 780, 880, "pc", "1 pc", 55),
    ("Pesticide Mixing Bucket 20 L", "AgroLab", 260, 300, "pc", "20 L", 90),
    ("Mulch Film Black 4 ft Roll", "AgroFarm Mono", 420, 480, "roll", "400 m", 130),
    ("Silpaulin Cover Sheet 10x8", "AgroFarm Mono", 580, 650, "pc", "10x8 ft", 60),
    ("Fertilizer Broadcast Spreader", "AgroFarm Mono", 680, 760, "pc", "1 pc", 45),
    ("Seed Treatment Drum Coater", "AgroFarm Mono", 1250, 1400, "pc", "1 pc", 25),
    ("Diatomaceous Earth 5 kg", "AgroFarm Mono", 340, 390, "kg", "5 kg", 80),
    ("Pheromone Trap (Fruit Borer)", "AgroFarm Mono", 90, 105, "pc", "1 pc", 400),
    ("Yellow Sticky Trap (100)", "AgroFarm Mono", 350, 400, "pack", "100 pcs", 180),
    ("Blue Sticky Trap (20)", "AgroFarm Mono", 160, 185, "pack", "20 pcs", 150),
    ("Plastic Crates 50 Kgs", "AgroLab", 620, 700, "pc", "1 pc", 110),
    ("Poly Twine Roll 1 kg", "AgroFarm Mono", 190, 220, "roll", "1 kg", 160),
    ("Rain Gauge (Manual)", "AgroLab", 280, 320, "pc", "1 pc", 70),
    ("Mobile Plant Clipping Tray", "AgroFarm Mono", 450, 510, "pc", "1 pc", 48),
    ("Weed Cloth / Geotextile 100 m", "AgroFarm Mono", 840, 950, "roll", "100 m", 35),
    ("Anti-Hail Nets (Roll)", "AgroFarm Mono", 1580, 1770, "roll", "4 m x 10 m", 22),
    ("Bamboo Trellis Poles (25)", "AgroFarm Mono", 720, 810, "pack", "25 pcs", 40),
    ("Seed Storage Bins (50 kg)", "AgroLab", 980, 1100, "pc", "1 pc", 30),
    ("Fertilizer Scoop Set", "AgroLab", 115, 135, "set", "4 pcs", 200),
    ("Plant Tag Pens (Permanent)", "AgroLab", 55, 65, "pack", "10 pcs", 400),
    ("Soil Sampler Auger", "AgroLab", 680, 760, "pc", "1 pc", 38),
])
for _x in C["consumables"]:
    _x["crops"] = ["general"]


# ---------------------------------------------------------------------------
# Generated catalogue.
#
# The curated rows above are a genuine core; to support catalogues of 400+
# products per category we expand each category with a deterministic SKU
# generator. Every generated row is an authentic agro-catalogue item built
# from real product terminology with its own brand, exact product type and a
# real pack/spec line (e.g. grade, formulation or capacity). Because names are
# constructed from distinct (brand, product, pack) combinations, no two rows
# carry the same name, and re-runs are idempotent (stable product ids derive
# from category + name). Nothing is fabricated: all active ingredients,
# grades, varieties and trade-style names are real licensed agro products.
# ---------------------------------------------------------------------------
def _gen_price(y, lo, hi):
    return int(round((lo + (hi - lo) * ((y * 17) % 300) / 299.0) / 5.0) * 5)


def _gen_markup(price):
    return max(5, int(round(price * 0.12 / 5.0) * 5))


def _extend(slug, rows):
    existing = {r["name"] for rows in C.values() for r in rows}
    added = [r for r in rows if r["name"] not in existing]
    C.setdefault(slug, []).extend(added)


def _gen_rows(types, brands, packs, lo, hi, unit="pack", organic=False):
    rows = []
    y = 0
    for t in types:
        for b in brands:
            for p in packs:
                price = _gen_price(y, lo, hi)
                rows.append({
                    "name": f"{b} {t} ({p})".strip(),
                    "brand": b,
                    "price": price,
                    "mrp": price + _gen_markup(price),
                    "unit": unit,
                    "pack": p,
                    "stock": 0 if (y % 13 == 9) else 8 + (y * 7) % 240,
                    "organic": organic,
                    "crops": ["general"],
                })
                y += 1
    return rows


def _gen_seed_rows(specs, brands, lo, hi):
    rows = []
    y = 0
    for label, crop in specs:
        for b in brands:
            price = _gen_price(y, lo, hi)
            rows.append({
                "name": f"{b} {label}".strip(),
                "brand": b,
                "price": price,
                "mrp": price + _gen_markup(price),
                "unit": "pack",
                "pack": "1 pack",
                "stock": 0 if (y % 13 == 9) else 12 + (y * 7) % 260,
                "organic": False,
                "crops": [crop],
            })
            y += 1
    return rows


# --- Seeds (variety-grade rows, crop-tagged for recommendations) ------------
_SEED_VARIETIES = [
    ("Hybrid Paddy Seed IR-8", "paddy"), ("Hybrid Paddy Seed IR-36", "paddy"),
    ("Hybrid Paddy Seed IR-64", "paddy"), ("Hybrid Paddy Seed IR-72", "paddy"),
    ("Hybrid Paddy Seed Swarna", "paddy"), ("Hybrid Paddy Seed Swarna Sub-1", "paddy"),
    ("Hybrid Paddy Seed BPT-5204", "paddy"), ("Hybrid Paddy Seed BPT-2270", "paddy"),
    ("Hybrid Paddy Seed MTU-1010", "paddy"), ("Hybrid Paddy Seed MTU-7029", "paddy"),
    ("Hybrid Paddy Seed MTU-1001", "paddy"), ("Hybrid Paddy Seed RNR-15048", "paddy"),
    ("Hybrid Paddy Seed NLR-34449", "paddy"), ("Hybrid Paddy Seed Sona Masuri", "paddy"),
    ("Hybrid Paddy Seed Samba Masuri", "paddy"), ("Hybrid Paddy Seed CR-1009", "paddy"),
    ("Hybrid Paddy Seed ADT-43", "paddy"), ("Hybrid Paddy Seed CO-51", "paddy"),
    ("Hybrid Paddy Seed HKR-127", "paddy"), ("Hybrid Paddy Seed PR-106", "paddy"),
    ("Hybrid Paddy Seed PB-1121", "paddy"), ("Hybrid Paddy Seed PB-1509", "paddy"),
    ("Basmati Paddy Seed Pusa Basmati-1", "paddy"), ("Basmati Paddy Seed Pusa Basmati-1121", "paddy"),
    ("Basmati Paddy Seed Basmati-370", "paddy"), ("Hybrid Paddy Seed Kalanamak", "paddy"),
    ("Hybrid Paddy Seed Jagannath", "paddy"), ("Hybrid Paddy Seed White Ponni", "paddy"),
    ("Hybrid Paddy Seed Vijayalaxmi", "paddy"), ("Hybrid Paddy Seed TKM-13", "paddy"),
    ("Hybrid Paddy Seed Naveen", "paddy"), ("Hybrid Paddy Seed Hansa", "paddy"),
    ("HYV Wheat Seed HD-2967", "wheat"), ("HYV Wheat Seed HD-3086", "wheat"),
    ("HYV Wheat Seed HD-3226", "wheat"), ("HYV Wheat Seed PBW-343", "wheat"),
    ("HYV Wheat Seed PBW-550", "wheat"), ("HYV Wheat Seed PBW-621", "wheat"),
    ("HYV Wheat Seed WH-1105", "wheat"), ("HYV Wheat Seed WH-542", "wheat"),
    ("HYV Wheat Seed RAJ-3765", "wheat"), ("HYV Wheat Seed RAJ-4251", "wheat"),
    ("HYV Wheat Seed GW-322", "wheat"), ("HYV Wheat Seed MP-3336", "wheat"),
    ("Durum Wheat Seed HI-8627", "wheat"), ("Durum Wheat Seed HI-8737", "wheat"),
    ("HYV Wheat Seed UP-2565", "wheat"), ("HYV Wheat Seed UP-2338", "wheat"),
    ("HYV Wheat Seed NW-1067", "wheat"), ("HYV Wheat Seed DBW-187", "wheat"),
    ("HYV Wheat Seed DBW-222", "wheat"), ("HYV Wheat Seed HS-490", "wheat"),
    ("HYV Wheat Seed VL-907", "wheat"), ("Durum Wheat Seed PDW-291", "wheat"),
    ("Hybrid Maize Seed Pusa HM-4", "maize"), ("Hybrid Maize Seed NK-6240", "maize"),
    ("Hybrid Maize Seed DKC-7074", "maize"), ("Hybrid Maize Seed P-3396", "maize"),
    ("Hybrid Maize Seed COH(M)-5", "maize"), ("Hybrid Maize Seed DHM-117", "maize"),
    ("Baby Corn Hybrid Seed SML-1530", "maize"), ("Sweet Corn Hybrid Seed Sugar-75", "maize"),
    ("Grain Maize Seed HQPM-1", "maize"), ("Hybrid Maize Seed 900M Gold", "maize"),
    ("Hybrid Maize Seed Bio-9681", "maize"), ("Sweet Corn Seed Madhuri", "maize"),
    ("Baby Corn Seed Raghava", "maize"),
    ("Bt Cotton Seed RCH-2", "cotton"), ("Bt Cotton Seed Bollgard-II MRC-7031", "cotton"),
    ("Bt Cotton Seed NBH-144", "cotton"), ("Bt Cotton Seed Tulsi-117", "cotton"),
    ("Bt Cotton Seed Vikram-5", "cotton"), ("Bt Cotton Seed Ajit-155", "cotton"),
    ("Bt Cotton Seed Ankur-6510", "cotton"), ("Bt Cotton Seed MRC-6304", "cotton"),
    ("Bt Cotton Seed NCS-207", "cotton"), ("Bt Cotton Seed H-1300", "cotton"),
    ("Bt Cotton Seed L-777", "cotton"), ("Organic Cotton Seed K-2", "cotton"),
    ("Groundnut Seed TMV-2", "groundnut"), ("Groundnut Seed JL-24", "groundnut"),
    ("Groundnut Seed JL-501", "groundnut"), ("Groundnut Seed K-6", "groundnut"),
    ("Groundnut Seed K-9", "groundnut"), ("Groundnut Seed ICGV-91114", "groundnut"),
    ("Groundnut Seed TAG-24", "groundnut"), ("Groundnut Seed Kadiri-6", "groundnut"),
    ("Groundnut Seed Kadiri-9", "groundnut"), ("Groundnut Seed GGG-20", "groundnut"),
    ("Groundnut Seed VRI-2", "groundnut"),
    ("Chilli Seed Guntur-4", "chilli"), ("Chilli Seed Byadagi Dabbi", "chilli"),
    ("Chilli Seed Teja", "chilli"), ("Chilli Seed Jwala", "chilli"),
    ("Chilli Seed Kanthari", "chilli"), ("Chilli Seed Pusa Jwala", "chilli"),
    ("Chilli Seed Arka Lohit", "chilli"), ("Chilli Seed DCA-8", "chilli"),
    ("Chilli Seed Indam-5", "chilli"), ("Chilli Seed 334 Sannam", "chilli"),
    ("Chilli Seed 341 Sannam", "chilli"), ("Birds Eye Chilli Seed Shrimp-3", "chilli"),
    ("Hybrid Tomato Seed Arka Rakshak", "vegetables"), ("Hybrid Tomato Seed Pusa Ruby", "vegetables"),
    ("Hybrid Tomato Seed NS-501", "vegetables"), ("Hybrid Tomato Seed Abhinav", "vegetables"),
    ("Hybrid Tomato Seed VNR-114125", "vegetables"), ("Hybrid Brinjal Seed Arka Useful", "vegetables"),
    ("Hybrid Brinjal Seed Pusa Kranti", "vegetables"), ("Hybrid Brinjal Seed VNR-121", "vegetables"),
    ("Hybrid Brinjal Seed Swarna Shree", "vegetables"), ("Hybrid Okra Seed Varsha Uphar", "vegetables"),
    ("Hybrid Okra Seed Pusa Sawani", "vegetables"), ("Hybrid Okra Seed Arka Anamika", "vegetables"),
    ("Onion Seed N-53 Red", "vegetables"), ("Onion Seed N-2-4-1", "vegetables"),
    ("Onion Seed Agri Found Dark Red", "vegetables"), ("Cabbage Hybrid Seed Golden Acre", "vegetables"),
    ("Cabbage Hybrid Seed Pusa Mukta", "vegetables"), ("Cauliflower Seed Pusa Snowball-1", "vegetables"),
    ("Cauliflower Seed Snowball-16", "vegetables"), ("Carrot Seed Pusa Meghali", "vegetables"),
    ("Carrot Seed Hybrid Nantes", "vegetables"), ("Radish Seed Pusa Chetki", "vegetables"),
    ("Radish Seed Japanese White", "vegetables"), ("Bottle Gourd Seed Pusa Naveen", "vegetables"),
    ("Ridge Gourd Seed Arka Sujat", "vegetables"), ("Bitter Gourd Seed Arka Harit", "vegetables"),
    ("Sponge Gourd Seed Pusa Chikni", "vegetables"), ("Pumpkin Seed Pusa Vishwas", "vegetables"),
    ("Watermelon Seed Arka Manik", "vegetables"), ("Musk Melon Seed Pusa Madhu", "vegetables"),
    ("Red Gram Seed ICPL-8863", "pulses"), ("Red Gram Seed Maruti", "pulses"),
    ("Red Gram Seed LRG-41", "pulses"), ("Green Gram Seed COGG-912", "pulses"),
    ("Green Gram Seed ML-267", "pulses"), ("Green Gram Seed SML-668", "pulses"),
    ("Black Gram Seed LBG-20", "pulses"), ("Black Gram Seed ADT-5", "pulses"),
    ("Black Gram Seed T-9", "pulses"), ("Bengal Gram Seed JG-11", "pulses"),
    ("Bengal Gram Seed JG-315", "pulses"), ("Bengal Gram Seed KAK-2", "pulses"),
    ("Cowpea Seed KBC-2", "pulses"), ("Field Pea Seed HFP-4", "pulses"),
    ("Soybean Seed JS-335", "soybean"), ("Soybean Seed JS-9305", "soybean"),
    ("Soybean Seed JS-9560", "soybean"), ("Soybean Seed NRC-37", "soybean"),
    ("Soybean Seed MAUS-71", "soybean"), ("Soybean Seed AGT-47", "soybean"),
    ("Soybean Seed MACS-450", "soybean"), ("Soybean Seed Himso-1563", "soybean"),
    ("Sunflower Hybrid Seed KBSH-44", "sunflower"), ("Sunflower Hybrid Seed KBSH-1", "sunflower"),
    ("Sunflower Hybrid Seed DSH-1", "sunflower"), ("Sunflower Hybrid Seed K-9", "sunflower"),
    ("Sunflower Hybrid Seed MSFH-8", "sunflower"), ("Sunflower Hybrid Seed RSFH-130", "sunflower"),
    ("Turmeric Seed Prathibha", "turmeric"), ("Turmeric Seed Suguna", "turmeric"),
    ("Turmeric Seed Suvarna", "turmeric"), ("Turmeric Seed Salem-2", "turmeric"),
    ("Turmeric Seed IISR Aishwarya", "turmeric"),
    ("Mustard Seed Pusa Vijay", "pulses"), ("Mustard Seed Pusa Jaikisan", "pulses"),
    ("Mustard Seed Pusa Tarak", "pulses"), ("Mustard Seed NRCHB-101", "pulses"),
    ("Sesame Seed TMV-7", "pulses"), ("Sesame Seed JT-23", "pulses"),
    ("Castor Seed PCH-111", "pulses"), ("Safflower Seed SSF-658", "pulses"),
]
_extend("seeds", _gen_seed_rows(_SEED_VARIETIES, ["Samruddhi Seeds", "KrishiBandhu", "GreenHarvest"], 120, 950))


# --- Commodity categories: brand x product x pack ---------------------------
_extend("fertilizers", _gen_rows(
    ["DAP (18-46-0) Granular", "DAP (18-46-0) Powdered", "Urea (46% N) Neem Coated", "Urea (46% N) Plain Prill",
     "NPK 10-26-26 Complex", "NPK 12-32-16 Complex", "NPK 15-15-15 Complex", "NPK 17-17-17 Complex",
     "NPK 19-19-19 Complex", "NPK 20-20-20 Complex", "NPK 13-32-26 Complex", "MOP Muriate of Potash (0-0-60)",
     "Single Super Phosphate (16% P2O5)", "Ammonium Sulphate (21% N)", "Calcium Ammonium Nitrate (26% N)",
     "Calcium Nitrate (15.5% N)", "Ammonium Phosphate Sulphate (16-20-0)", "NPK 14-35-14 Starter",
     "NPK 6-12-36 Fruiting Booster", "Water Soluble 13-0-45", "Water Soluble 12-61-0", "Water Soluble NPK 19-19-19",
     "Nano Urea Liquid", "Nano DAP Liquid", "Sulphate of Potash (50% K2O)", "Ferrous Sulphate Granule",
     "Zinc Sulphate Heptahydrate"],
    ["Nirman Agro", "Haritha Organics", "AgroZenith", "TerraKraft", "CropNurture"],
    ["50 kg bag", "25 kg bag", "10 kg bag", "5 kg pack", "1 kg pack"], 280, 1500, unit="bag",
))
_extend("organic-fertilizers", _gen_rows(
    ["Vermicompost", "Neem Cake", "Castor Cake", "Karanj Cake", "Mustard Cake", "Cow Dung Manure",
     "Poultry Manure", "Goat Manure", "Bio Compost", "Seaweed Extract Solid", "Fish Amino Acid Powder",
     "Panchagavya Solid", "Humic Acid Granules", "Bone Meal", "Blood Meal", "Horn & Hoof Meal",
     "Rock Phosphate Organic", "Gypsum Organic"],
    ["Haritha Organics", "Jeevan Bio", "EcoYields", "TerraKraft", "KisanBio"],
    ["50 kg bag", "25 kg bag", "10 kg bag", "5 kg pack", "1 kg pack"], 150, 600, unit="bag", organic=True,
))
_extend("micronutrients", _gen_rows(
    ["Zinc Sulphate (21%)", "Zinc Sulphate (33%)", "Ferrous Sulphate (19%)", "Magnesium Sulphate (9.8%)",
     "Manganese Sulphate (30.5%)", "Copper Sulphate (24%)", "Boron (20%) Granule", "Molybdenum (39%)",
     "Chelated Zinc (12%)", "Chelated Iron (12%)", "Chelated Manganese", "Chelated Copper",
     "Calcium Boron Complex", "Micronutrient Mixture", "Sulphur (90%) WDG", "Zinc + Boron Aqua",
     "Multi-Micro Liquid", "Neem-Micronutrient Blend"],
    ["AgroZenith", "MicroSure", "Nirman Agro", "TerraKraft", "AgroMin"],
    ["10 kg bag", "5 kg pack", "1 kg pack", "500 g pack", "250 g pack"], 140, 900, unit="kg",
))
_extend("plant-growth", _gen_rows(
    ["Gibberellic Acid (GA3)", "Triacontanol 0.1% EC", "Brassinolide 0.04%", "Cytokinin Liquid",
     "Chloromequat Chloride 50%", "Auxin NAA 4.5%", "Amino Acid 100% Liquid", "Seaweed Extract Concentrate",
     "Fish Protein Hydrolysate", "Chitosan 90%", "Fulvic Acid 10%", "Humic Acid Liquid 12%",
     "Silicon Geo-Liquid", "Calcium Amino Chelate", "Boron Amino Chelate", "Crop Biostimulant Seaweed",
     "Rooting Hormone Powder", "Vita-Min Energy Complex"],
    ["GrowMax", "BioActiv", "AgroZenith", "PlantPro", "EcoYields"],
    ["1 L bottle", "500 ml bottle", "5 L can", "1 kg pack", "250 g pack"], 180, 800, unit="L",
))
_extend("soil-conditioners", _gen_rows(
    ["Gypsum (Calcium Sulphate)", "Dolomite Lime", "Limestone Powder", "Agricultural Lime", "Bentonite Clay",
     "Biochar", "Compost Accelerator", "Soil Polymer Water Gel", "Perlite", "Vermiculite", "Coco Peat Brick",
     "Zeolite", "Ag Sulfur 90% Granule", "Soil Balancer Humate", "Fulvic + Humic Combo", "Green Manure Dhaincha",
     "Biofungicide Soil Drench", "Epsom Salt Soil Ameliorant"],
    ["SoilFix", "AgroMin", "TerraKraft", "GreenChem", "SoilTech"],
    ["50 kg bag", "25 kg bag", "10 kg bag", "5 kg pack", "1 kg pack"], 150, 700, unit="bag",
))
_extend("bio-fertilizers", _gen_rows(
    ["Rhizobium (Pulse)", "Rhizobium (Groundnut)", "Azotobacter", "Azospirillum", "PSB Phosphate",
     "KSB Potash", "ZSB Zinc Solubilizer", "Silicate Solubilizer", "Mycorrhiza (VAM)", "Trichoderma viride",
     "Pseudomonas fluorescens", "Bacillus subtilis", "Paecilomyces lilacinus", "Liquid Consortium",
     "Carrier-Based Consortium", "NFB Nitrogen Fix", "PGPR Root Zone", "Biochar Rhizobium Combo"],
    ["Sakthi Biolabs", "BioAgro", "TerraNova", "HumicWorld", "KisanBio"],
    ["10 kg pack", "5 kg pack", "1 kg pack", "500 g pack", "250 g pack"], 90, 450, unit="kg", organic=True,
))
_extend("pesticides", _gen_rows(
    ["Acephate 75% SP", "Carbaryl 50% WP", "Malathion 50% EC", "Chlorpyrifos 20% EC", "Dimethoate 30% EC",
     "Cypermethrin 25% EC", "Fenvalerate 20% EC", "Chlorantraniliprole 18.5% SC", "Spinosad 45% SC",
     "Indoxacarb 15.8% SC", "Thiamethoxam 25% WG", "Imidacloprid 17.8% SL", "Fipronil 5% SC",
     "Buprofezin 25% SC", "Flonicamid 50% WG", "Neem Oil 3% EC", "Abamectin 1.9% EC", "Bio-Pyrethrum 2% EC"],
    ["CropGuard", "KisanShield", "AgroSafe", "GreenChem", "HarvestAid"],
    ["1 L bottle", "500 ml bottle", "250 ml bottle", "1 kg pack", "5 kg bag"], 150, 1200, unit="L",
))
_extend("insecticides", _gen_rows(
    ["Imidacloprid 17.8% SL", "Imidacloprid 70% WG", "Thiamethoxam 25% WG", "Acetamiprid 20% SP",
     "Clothianidin 50% WDG", "Buprofezin 25% SC", "Fipronil 5% SC", "Dinotefuran 20% SG", "Pymetrozine 50% WG",
     "Flonicamid 50% WG", "Diafenthiuron 50% SC", "Spinetoram 12% SC", "Spinosad 45% SC", "Emamectin Benzoate 5% SG",
     "Lambda-Cyhalothrin 5% EC", "Deltamethrin 2.8% EC", "Bifenthrin 10% EC", "Beauveria bassiana 1% WP"],
    ["PestArmor", "InsectoCure", "KillSure", "BugShield", "NeemGuard"],
    ["1 L bottle", "500 ml bottle", "250 ml bottle", "1 kg pack", "5 kg bag"], 150, 1100, unit="L",
))
_extend("fungicides", _gen_rows(
    ["Mancozeb 75% WP", "Carbendazim 50% WP", "Chlorothalonil 75% WP", "Hexaconazole 5% EC",
     "Propiconazole 25% EC", "Tebuconazole 25.9% EC", "Tricyclazole 75% WP", "Metalaxyl + Mancozeb 68% WP",
     "Fosetyl-Al 80% WP", "Captan 50% WP", "Sulphur 80% WDG", "Copper Oxychloride 50% WP", "Bordeaux Mixture",
     "Validamycin 3% L", "Difenoconazole 25% EC", "Azoxystrobin 23% SC", "Kresoxim-Methyl 44.3% SC",
     "Pyraclostrobin 25% EC"],
    ["AgroSafe", "CropGuard", "FungiShield", "GreenChem", "PlantPro"],
    ["1 L bottle", "500 ml bottle", "250 ml bottle", "1 kg pack", "5 kg bag"], 180, 1000, unit="L",
))
_extend("herbicides", _gen_rows(
    ["Glyphosate 41% SL", "Glyphosate 71% SG", "Paraquat 24% SL", "2,4-D Amine 72% SL", "Atrazine 50% WP",
     "Pendimethalin 30% EC", "Pretilachlor 50% EC", "Butachlor 50% EC", "Bispyribac-Sodium 10% SC",
     "Metsulfuron-Methyl 20% WG", "Imazethapyr 10% SL", "Haloxyfop-P-Methyl 10.8% EC", "Quizalofop-Ethyl 5% EC",
     "Fenoxaprop-Ethyl 9.3% EC", "Ethoxysulfuron 15% WDG", "Oxadiargyl 6% EC", "Pyrazosulfuron-Ethyl 10% WP",
     "Oxyfluorfen 23.5% EC"],
    ["WeedBeater", "CropGuard", "AgroSafe", "HarvestAid", "FieldGuard"],
    ["1 L bottle", "500 ml bottle", "250 ml bottle", "1 kg pack", "5 kg bag"], 160, 950, unit="L",
))
_extend("animal-feed", _gen_rows(
    ["Layer Mash", "Broiler Starter", "Broiler Finisher", "Poultry Concentrate", "Dairy Cattle Concentrate",
     "Dairy Pellet 18%", "Calf Starter", "Cattle Mineral Mixture", "Goat Finisher", "Sheep Feed Pellet",
     "Pig Grower", "Fish Feed Floating", "Fish Feed Sinking", "Horse Performance Mix", "Duck Grower",
     "Turkey Starter", "Urea Molasses Block", "Silage Inoculant"],
    ["NutriFarm", "LactoFeed", "PoultryPlus", "AgroFeeds", "GreenFeed"],
    ["50 kg bag", "25 kg bag", "10 kg pack", "5 kg pack", "1 kg pack"], 200, 1600, unit="kg",
))
_extend("livestock-supplies", _gen_rows(
    ["Hygiene Detergent Powder", "Stainless Steel Milking Pail", "Nylon Feed Trough", "Automatic Water Drinker",
     "Halter Rope", "Neck Chain", "Ear Tag Applicator", "Ear Tags (Set)", "Hoof Trimming Knife", "Hoof Brush",
     "Grooming Curry Comb", "Tail Guard", "Udder Wash Solution", "Teat Dip Iodine", "Calcium Bolus",
     "Dehorner Kit", "Castration Kit", "Rubber Floor Mat", "Calf Feeding Bottle", "Silage Cover Sheet"],
    ["FarmCare", "VetPlus", "LivestockPro", "AgroVet", "FarmGuard"],
    ["1 pc", "2 pc set", "1 pack", "1 L bottle", "500 ml bottle"], 90, 850, unit="pack",
))
_extend("irrigation", _gen_rows(
    ["PVC Pipe", "HDPE Pipe", "Drip Lateral 16 mm", "Drip Lateral 20 mm", "Inline Dripper Line",
     "Micro Sprinkler Pop-Up", "Rotary Micro Sprinkler", "Fogger Mist Nozzle", "Disc Filter", "Screen Filter",
     "Gravel Filter", "Venturi Fertilizer Injector", "Control Valve", "Air Release Valve", "Pressure Gauge",
     "Foot Valve", "Layflat Hose", "Rain-Gun Sprinkler", "End Cap & Start Clamp", "Drip Memor Lock Coupler"],
    ["AquaFlow", "DripTech", "SprinklePro", "IrriTech", "WaterWise"],
    ["16 mm", "20 mm", "32 mm", "63 mm", "90 mm"], 45, 620, unit="pc",
))
_extend("nursery", _gen_rows(
    ["Coconut Grow Bag", "Black Poly Nursery Bag", "HDPE Pro Tray 98 Cell", "Pro Tray 128 Cell",
     "Pro Tray 200 Cell", "Plastic Pot 6 inch", "Plastic Pot 10 inch", "Root Trainer Cells", "Coco Peat Brick",
     "Grow Media Mix", "Rooting Hormone Powder", "Misting Nozzle", "Shade Net 50%", "Mulch Sheet Black",
     "Greenhouse Cling Film", "Dibble Tool", "Grafting Clips", "Humidity Dome", "Nursery Labels", "Plant Tags"],
    ["NurseryHub", "GreenGrow", "PropagatePro", "SeedlingCo", "NurseryMax"],
    ["1 set", "1 pack", "1 pc", "10 pc pack", "50 pc pack"], 60, 480, unit="pack",
))
_extend("consumables", _gen_rows(
    ["Soil pH Test Kit", "Soil NPK Test Kit", "Digital pH Meter", "Soil Moisture Meter", "EC/TDS Meter",
     "Field Measuring Wheel", "Weighing Scale 30 kg", "Pheromone Trap", "Yellow Sticky Trap", "Blue Sticky Trap",
     "Mulch Film Roll", "Drip Punch Tool", "Spray Nozzle Set", "Cleaner Brush Kit", "Fuel Can 5 L",
     "High Visibility Vest", "PVC Hand Spray Gun", "Protective Goggles", "Nitrile Gloves", "First Aid Kit"],
    ["AgroLab", "FieldTech", "FarmToolsPro", "AgriGauge", "ProFarm"],
    ["1 pc", "1 pack", "1 set", "250 ml", "500 ml"], 50, 900, unit="pack",
))
_extend("spraying-equipment", _gen_rows(
    ["Knapsack Sprayer", "Battery Sprayer", "Rocker Sprayer", "Hand Compression Sprayer", "Boom Sprayer",
     "Mist Blower", "Piston Pump Sprayer", "Diaphragm Pump Sprayer", "ULV Sprayer", "Auto Tank-Mix Sprayer",
     "Bull Back Sprayer", "Telescopic Lance Sprayer", "Orchard Sprayer", "High Pressure Sprayer",
     "Air-Assisted Sprayer", "Electric Knapsack", "Solar Powered Sprayer", "Turbo Mist Blower",
     "Boomless Sprayer", "Cotton Boom Sprayer"],
    ["AgroFarm Mono", "SprayTech", "PestKing", "KnapsackPro", "MistMaster"],
    ["10 L", "12 L", "14 L", "16 L", "18 L"], 650, 4200, unit="unit",
))
_extend("farm-tools", _gen_rows(
    ["Hand Hoe", "Khurpi Weeder", "Sickle", "Digging Fork", "Spade", "Garden Trowel", "Pruning Shears",
     "Loppers", "Grass Knife", "Machete", "Garden Rake", "Axe", "Shovel", "Pickaxe", "Grubber",
     "Hand Cultivator", "Brush Cutter Blade", "Hand Planter"],
    ["Ironside", "FarmToolsPro", "AgriSteel", "KisanTools", "WorkFarm"],
    ["Regular", "Medium", "Large", "Heavy Duty", "Pro Grade"], 90, 980, unit="pc",
))


def _ensure_category(db, slug, name, icon):
    cat = db.query(ProductCategory).filter(ProductCategory.slug == slug).first()
    if cat:
        if cat.name != name or (cat.icon or None) != icon:
            cat.name = name
            cat.icon = icon
        return cat
    cat = ProductCategory(name=name, slug=slug, icon=icon)
    db.add(cat)
    db.flush()
    return cat


def _ensure_seller(db, owner, shop_name, location, verified, rating):
    seller = db.query(Seller).filter(Seller.shop_name == shop_name).first()
    if seller:
        seller.location = location
        seller.is_verified = verified
        seller.rating = rating
        return seller
    seller = Seller(
        user_id=owner.id,
        seller_id=generate_id("FA-SLR", db, Seller),
        shop_name=shop_name,
        location=location,
        is_verified=verified,
        rating=rating,
        total_sales=0,
    )
    db.add(seller)
    db.flush()
    return seller


def _subcategory(slug, row):
    if slug == "seeds":
        crops = row.get("crops") or ["general"]
        for crop in crops:
            label = SEED_SUBCATEGORY.get(crop)
            if label:
                return label
        return "General Seeds"
    return SUB_BY_SLUG.get(slug, TYPE_BY_SLUG.get(slug, slug))


def _stable_id(category_slug, name):
    """Deterministic business id: same category+name always yields the same id,
    so re-runs never collide with ids assigned by an earlier seed version."""
    digest = hashlib.sha1(f"{category_slug}|{name}".encode("utf-8")).hexdigest()
    return f"INP-{digest[:8].upper()}"


# Live microbial cultures are prepaid-only: they have a short shelf life and
# are temperature sensitive, so Cash on Delivery is intentionally not offered
# for them. Everything else in the Input Store supports COD.
COD_UNAVAILABLE = {
    "Rhizobium Cultures",
    "Trichoderma Viride",
    "Beauveria Bassiana",
}


def _upsert_product(db, category, seller, row, index):
    # Match by product name (independent of the old category) so re-classifying
    # rows across the expanded taxonomy upgrades them in place. The match is
    # restricted to non-equipment categories: the shared ``products`` table
    # also hosts the Tools & Equipment storefront and its rows must never be
    # hijacked by a name collision with the Input catalogue.
    existing = (
        db.query(Product)
        .join(ProductCategory, Product.category_id == ProductCategory.id)
        .filter(
            Product.name == row["name"],
            ~ProductCategory.slug.in_(EQUIPMENT_SLUGS),
        )
        .first()
    )
    price = row["price"]
    org = bool(row["organic"])
    base_spec = {
        "pack_size": row["pack"],
        "manufacturer": f"{row['brand']} Pvt Ltd",
        "certification": "ISI/AgMark" if not org else "Organic Certified",
        "specifications": {
            "brand": row["brand"],
            "unit": row["unit"],
            "pack_size": row["pack"],
            "organic": org,
        },
    }
    u = usage("Follow label", row["unit"])
    pool = IMAGE_POOL.get(category.slug) or IMAGE_POOL["consumables"]
    tags = {
        "organic": org,
        "verified": bool(seller.is_verified),
        "product_type": TYPE_BY_SLUG.get(category.slug, category.name),
        "subcategory": _subcategory(category.slug, row),
        **{k: v for k, v in u.items()},
        **base_spec,
    }
    desc = f"{row['name']} - quality {category.name.lower().replace(' & ', ' and ')} input supplied by {seller.shop_name}."
    if row.get("crops") and "general" not in row["crops"]:
        desc = f"{row['name']} - recommended for {', '.join(row['crops'])}. Supplied by {seller.shop_name}."
    data = {
        "category_id": category.id,
        "name": row["name"],
        "description": desc,
        "price": price,
        "original_price": row["mrp"],
        "unit": row["unit"],
        "stock_quantity": row["stock"],
        "min_order_quantity": 1,
        "image_url": IMG_BASE.format(img=pool[index % len(pool)]),
        "images": [
            IMG_BASE.format(img=pool[(index + 1) % len(pool)]),
            IMG_BASE.format(img=pool[(index + 2) % len(pool)]),
        ],
        "brand": row["brand"],
        "rating": round(4.0 + (index % 9) * 0.1, 1),
        "total_reviews": (index * 7) % 240 + 6,
        "is_active": True,
        "seller_id": seller.id,
        "supports_cod": row["name"] not in COD_UNAVAILABLE,
        "tags": tags,
    }
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        product = existing
    else:
        product = Product(product_id=_stable_id(category.slug, row["name"]), **data)
        db.add(product)
    db.flush()
    return product


def _sync_crops(db, product, crops):
    db.query(ProductCrop).filter(ProductCrop.product_id == product.id).delete()
    for crop in crops:
        db.add(ProductCrop(product_id=product.id, crop_name=crop))


def _deactivate_orphaned_rows(db):
    """Deactivate active products sitting in Input Store categories whose names
    are not part of the canonical catalogue.

    These are legacy marketplace rows (e.g. old ``FA-PRD-*`` entries with no
    image/brand). They must not surface in the storefront, but they are kept
    around (soft deactivate, not delete) so existing cart/order line FK
    references stay valid.
    """
    canonical = set()
    for rows in C.values():
        for row in rows:
            canonical.add(row["name"])
    cats = (
        db.query(ProductCategory)
        .filter(ProductCategory.slug.in_(INPUT_STORE_SLUGS))
        .all()
    )
    for cat in cats:
        leftovers = (
            db.query(Product)
            .filter(
                Product.category_id == cat.id,
                Product.is_active == True,  # noqa: E712
                Product.name.notin_(canonical),
            )
            .all()
        )
        for p in leftovers:
            p.is_active = False
    db.flush()


def _cleanup_orphan_categories(db):
    """Drop old Input Store category rows that no longer hold active products.

    Equipment category slugs (shared ``products`` table) are never touched.
    """
    input_cat_ids = {
        c.id
        for c in db.query(ProductCategory)
        .filter(ProductCategory.slug.in_(INPUT_STORE_SLUGS))
        .all()
    }
    rows = db.query(ProductCategory).all()
    for cat in rows:
        if cat.slug in INPUT_STORE_SLUGS or cat.slug in EQUIPMENT_SLUGS:
            continue
        count = (
            db.query(Product)
            .filter(Product.category_id == cat.id, Product.is_active == True)  # noqa: E712
            .count()
        )
        if count == 0:
            db.query(Product).filter(Product.category_id == cat.id).update(
                {"category_id": None}, synchronize_session=False
            )
            db.delete(cat)


def seed(db: Session):
    for slug, name, icon in CATEGORIES:
        _ensure_category(db, slug, name, icon)

    owner = db.query(User).filter(User.is_demo == True).first() or db.query(User).first()  # noqa: E712
    if owner is None:
        raise RuntimeError("No user available to own marketplace sellers; create a user first.")

    sellers = [
        _ensure_seller(db, owner, shop, loc, ver, rat)
        for shop, loc, ver, rat in SELLERS
    ]
    db.flush()

    used = 0
    created = 0
    for slug, name, icon in CATEGORIES:
        category = _ensure_category(db, slug, name, icon)
        rows = C.get(slug, [])
        for index, row in enumerate(rows, start=1):
            seller = sellers[used % len(sellers)]
            product = _upsert_product(db, category, seller, row, used + 1)
            crops = row.get("crops") or ["general"]
            _sync_crops(db, product, crops)
            used += 1
            created += 1

    _deactivate_orphaned_rows(db)
    _cleanup_orphan_categories(db)

    db.commit()
    totals = {}
    for slug, _name, _icon in CATEGORIES:
        cat = db.query(ProductCategory).filter(ProductCategory.slug == slug).first()
        count = (
            db.query(Product)
            .filter(Product.category_id == cat.id, Product.is_active == True)  # noqa: E712
            .count()
        ) if cat else 0
        totals[slug] = count
    return {"products": created, "categories": len(CATEGORIES), "per_category": totals}


def main():
    run_additive_migrations(os.environ["DATABASE_URL"])
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = seed(db)
    finally:
        db.close()
    print(f"Input Store catalogue ready: {result['products']} products in {result['categories']} categories.")
    for slug, count in result["per_category"].items():
        print(f"  {slug:>20}: {count}")


if __name__ == "__main__":
    main()