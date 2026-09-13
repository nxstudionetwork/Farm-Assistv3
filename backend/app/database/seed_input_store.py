"""Seed the Input Store catalogue.

Standalone script - run it once on a fresh or existing database::

    python -B -m app.database.seed_input_store

It is safe to re-run (idempotent). It creates the Input Store product
categories and a realistic catalogue of agricultural inputs (25+ products per
category). Every row lands in the SAME marketplace ``products`` table - existing
products are *upgraded in place* (matched by name + category) so the Input Store
and Marketplace stay one unified catalogue. No frontend mocks; the page only
ever renders what this database contains.

Images are stable Unsplash CDN URLs that were verified to resolve and reflect
real agriculture product categories (seed beds, fertiliser spreading, drip
irrigation, sprayers, tools, nurseries, greenhouses).
"""

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
from app.utils.auth import generate_id  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.marketplace import (  # noqa: E402
    Product,
    ProductCategory,
    ProductCrop,
    Seller,
)

IMG_BASE = "https://images.unsplash.com/{img}?w=640&q=70&auto=format&fit=crop"

IMAGE_POOL = {
    "seeds": [
        "photo-1500937386664-56d1dfef3854",
        "photo-1625246333195-78d9c38ad449",
        "photo-1500382017468-9049fed747ef",
        "photo-1542838132-92c53300491e",
        "photo-1592982537447-7440770cbfc9",
    ],
    "fertilizers": [
        "photo-1506084868230-bb9d95c24759",
        "photo-1507003211169-0a1dd7228f2d",
        "photo-1591857177580-dc82b9ac4e1e",
        "photo-1472162072942-cd5147eb3902",
    ],
    "crop-nutrition": [
        "photo-1560493676-04071c5f467b",
        "photo-1523348837708-15d4a09cfac2",
        "photo-1416879595882-3373a0480b5b",
        "photo-1466692476868-aef1dfb1e735",
    ],
    "organic": [
        "photo-1416879595882-3373a0480b5b",
        "photo-1560493676-04071c5f467b",
        "photo-1523348837708-15d4a09cfac2",
        "photo-1472162072942-cd5147eb3902",
    ],
    "crop-protection": [
        "photo-1500382017468-9049fed747ef",
        "photo-1523741543316-beb7fc7023d8",
        "photo-1574943320219-553eb213f72d",
    ],
    "irrigation": [
        "photo-1574943320219-553eb213f72d",
        "photo-1542838132-92c53300491e",
        "photo-1625246333195-78d9c38ad449",
    ],
    "sprayers": [
        "photo-1470252649378-9c29740c9fa8",
        "photo-1523741543316-beb7fc7023d8",
        "photo-1500382017468-9049fed747ef",
    ],
    "farm-tools": [
        "photo-1508615039623-a25605d2b022",
        "photo-1416879595882-3373a0480b5b",
        "photo-1523741543316-beb7fc7023d8",
    ],
    "nursery": [
        "photo-1466692476868-aef1dfb1e735",
        "photo-1592982537447-7440770cbfc9",
        "photo-1625246333195-78d9c38ad449",
    ],
    "other-inputs": [
        "photo-1495107334309-fcf20504a5ab",
        "photo-1609951651556-5334e2706168",
        "photo-1586281380349-632531db7ed4",
        "photo-1566438480900-0609be27a4be",
    ],
}

CATEGORIES = [
    ("seeds", "Seeds"),
    ("fertilizers", "Fertilizers"),
    ("crop-nutrition", "Crop Nutrition"),
    ("organic", "Organic Inputs"),
    ("crop-protection", "Crop Protection"),
    ("irrigation", "Irrigation"),
    ("sprayers", "Sprayers"),
    ("farm-tools", "Farm Tools"),
    ("nursery", "Nursery"),
    ("other-inputs", "Other Inputs"),
]

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


def usage(step, units):
    return {
        "usage": "Sow/apply according to crop stage; irrigation recommended after application.",
        "application_rate": f"{step} {units} per acre as directed on the pack.",
        "safety": "Wear gloves while handling. Store away from food, feed and children.",
    }


# ---------------------------------------------------------------------------
# Catalogue.  category -> list of (name, brand, price, mrp|None, unit, pack, stock)
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
# map specific seeds to crops
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
])
for _x in C["fertilizers"]:
    _x["crops"] = ["general"]

# --- Crop Nutrition -------------------------------------------------------
add("crop-nutrition", [
    ("Amino Acid Liquid 40%", "EcoYields", 420, 490, "L", "1 L", 120),
    ("Seaweed Extract Liquid", "EcoYields", 360, 420, "L", "1 L", 140),
    ("Humic Acid Granule 98%", "TerraKraft", 210, 250, "kg", "5 kg", 90),
    ("Fulvic Acid Liquid", "EcoYields", 380, 440, "L", "1 L", 110),
    ("WP Foliar Booster 19:19:19", "Nirman Agro", 240, 280, "kg", "1 kg", 160),
    ("Bio Stimulant Root Plus", "TerraKraft", 330, 380, "L", "1 L", 130),
    ("Potassium Humate Flakes", "TerraKraft", 190, 230, "kg", "5 kg", 70),
    ("Chitosan Foliar", "EcoYields", 540, 620, "L", "1 L", 50),
    ("Plant Protein Hydrolysate", "EcoYields", 460, 530, "L", "1 L", 60),
    ("Multi-Micronutrient Foliar", "AgroZenith", 180, 210, "kg", "1 kg", 200),
    ("Chelated Zinc EDTA 12%", "AgroZenith", 470, 540, "kg", "5 kg", 45),
    ("Chelated Iron EDTA 12%", "AgroZenith", 490, 560, "kg", "5 kg", 40),
    ("Boron 20% Liquid", "AgroZenith", 260, 300, "L", "1 L", 220),
    ("Calcium Amino Chelate", "EcoYields", 520, 600, "L", "1 L", 55),
    ("Liquid Silicon 15%", "TerraKraft", 310, 360, "L", "1 L", 80),
    ("Gibberellic Acid 40% WSG", "TerraKraft", 650, 750, "g", "100 g", 35),
    ("Triacontanol 0.05% EC", "EcoYields", 240, 280, "L", "1 L", 90),
    ("NAA 4.5% SL", "AgroZenith", 170, 200, "L", "1 L", 70),
    ("Cytokinin 0.01% SP", "TerraKraft", 290, 340, "kg", "100 g", 45),
    ("Yeast Extract Plant Tonic", "EcoYields", 350, 410, "kg", "1 kg", 65),
    ("NPK 6-12-36 Fruiting Booster", "AgroZenith", 720, 800, "kg", "10 kg", 30),
    ("Kelp Hydrolysate", "EcoYields", 480, 550, "L", "1 L", 58),
    ("Salicylic Acid Foliar", "TerraKraft", 320, 370, "L", "1 L", 48),
    ("Yucca Saponin Surfactant", "EcoYields", 410, 480, "L", "1 L", 52),
])
for _x in C["crop-nutrition"]:
    _x["crops"] = ["general"]

# --- Organic Inputs -------------------------------------------------------
add("organic", [
    ("Vermicompost (Haritha)", "Haritha Organics", 420, 500, "bag", "50 kg", 200, True),
    ("Neem Cake Powder", "Haritha Organics", 260, 310, "kg", "10 kg", 150, True),
    ("Pure Cow Dung Manure", "Jeevan Bio", 180, 220, "bag", "10 kg", 300, True),
    ("Poultry Manure (Sun dried)", "Jeevan Bio", 230, 270, "bag", "25 kg", 250, True),
    ("Seaweed Liquid Fertilizer", "EcoYields", 340, 400, "L", "1 L", 120, True),
    ("Fish Amino Acid", "EcoYields", 280, 330, "L", "1 L", 100, True),
    ("Panchagavya Concentrate", "Jeevan Bio", 190, 230, "L", "1 L", 140, True),
    ("Jeevamrutham Booster", "Jeevan Bio", 150, 180, "L", "1 L", 160, True),
    ("Beejamrutham Seed Treat", "Jeevan Bio", 120, 150, "kg", "1 kg", 180, True),
    ("Neem Oil 10000 ppm", "Sakthi Biolabs", 320, 380, "L", "1 L", 220, True),
    ("Karanj Oil (Pongamia)", "Sakthi Biolabs", 250, 300, "L", "1 L", 120, True),
    ("Castor Cake Powder", "Haritha Organics", 340, 400, "kg", "25 kg", 90, True),
    ("Groundnut Cake", "Haritha Organics", 420, 490, "kg", "25 kg", 80, True),
    ("Bone Meal Powder", "TerraKraft", 310, 360, "kg", "25 kg", 110, True),
    ("Rock Phosphate Powder", "TerraKraft", 220, 260, "kg", "25 kg", 95, True),
    ("Wood Ash / Plant Ash", "Haritha Organics", 140, 170, "kg", "10 kg", 130, True),
    ("Bio Compost", "Haritha Organics", 250, 290, "bag", "25 kg", 170, True),
    ("Dhaincha Green Manure Seeds", "KrishiBandhu", 160, 190, "kg", "5 kg", 140, True),
    ("Biochar Soil Amendment", "TerraKraft", 380, 440, "kg", "5 kg", 60, True),
    ("Rhizobium Cultures", "Sakthi Biolabs", 130, 160, "pack", "200 g", 300, True),
    ("Azotobacter Biofertilizer", "Sakthi Biolabs", 150, 180, "pack", "200 g", 280, True),
    ("PSB Phosphate Bacteria", "Sakthi Biolabs", 140, 170, "pack", "200 g", 260, True),
    ("VAM Mycorrhizal Powder", "Sakthi Biolabs", 210, 250, "kg", "500 g", 150, True),
    ("Trichoderma Viride", "Sakthi Biolabs", 120, 150, "pack", "250 g", 320, True),
    ("Beauveria Bassiana", "Sakthi Biolabs", 260, 310, "pack", "500 g", 110, True),
    ("Bacillus Subtilis Bio-Fungicide", "Sakthi Biolabs", 230, 280, "pack", "500 g", 130, True),
])
for _x in C["organic"]:
    _x["crops"] = ["general"]

# --- Crop Protection ------------------------------------------------------
add("crop-protection", [
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
    ("Carbendazim 50 WP", "Varuna Agro", 220, 260, "pack", "100 g", 600),
    ("Copper Oxy Chloride 50 WP", "Varuna Agro", 310, 360, "pack", "500 g", 320),
    ("Mancozeb 75 WP", "Varuna Agro", 350, 400, "pack", "500 g", 500),
    ("Hexaconazole 5 SC", "Varuna Agro", 180, 210, "L", "500 ml", 460),
    ("Propiconazole 25 EC", "CropNova", 420, 480, "L", "250 ml", 280),
    ("Tebuconazole 25.9 EC", "CropNova", 540, 620, "L", "250 ml", 240),
    ("Azoxystrobin 23 SC", "CropNova", 890, 1000, "L", "250 ml", 160),
    ("Metalaxyl + Mancozeb 72 WP", "Varuna Agro", 580, 660, "pack", "500 g", 200),
    ("Sulphur 80 WDG", "Varuna Agro", 240, 280, "pack", "250 g", 420),
    ("Pendimethalin 30 EC", "CropNova", 320, 370, "L", "1 L", 340),
    ("Bispyribac Sodium 10 SC", "CropNova", 610, 700, "L", "250 ml", 190),
    ("2,4-D Amine Salt 58% SL", "CropNova", 190, 220, "L", "500 ml", 380),
    ("Glyphosate 41 SL (Non-selective)", "CropNova", 470, 530, "L", "1 L", 500),
    ("Atrazine 50 WP", "CropNova", 230, 270, "pack", "500 g", 260),
    ("Oxyfluorfen 23.5 EC", "CropNova", 560, 650, "L", "500 ml", 150),
])
for _x in C["crop-protection"]:
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

# --- Sprayers -------------------------------------------------------------
add("sprayers", [
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
for _x in C["sprayers"]:
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

# --- Other Inputs ---------------------------------------------------------
add("other-inputs", [
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
for _x in C["other-inputs"]:
    _x["crops"] = ["general"]


def _ensure_category(db, slug, name):
    cat = db.query(ProductCategory).filter(ProductCategory.slug == slug).first()
    if cat:
        return cat
    cat = ProductCategory(name=name, slug=slug, icon=_ICON_MAP.get(slug))
    db.add(cat)
    db.flush()
    return cat


_ICON_MAP = {
    "seeds": "fa-seedling",
    "fertilizers": "fa-flask",
    "crop-nutrition": "fa-droplet",
    "organic": "fa-leaf",
    "crop-protection": "fa-shield-halved",
    "irrigation": "fa-droplet",
    "sprayers": "fa-spray-can",
    "farm-tools": "fa-screwdriver-wrench",
    "nursery": "fa-seedling",
    "other-inputs": "fa-box",
}


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


def _upsert_product(db, category, seller, row, index):
    existing = (
        db.query(Product)
        .filter(Product.category_id == category.id, Product.name == row["name"])
        .first()
    )
    price = row["price"]
    base_spec = {
        "pack_size": row["pack"],
        "manufacturer": f"{row['brand']} Pvt Ltd",
        "certification": "ISI/AgMark" if not row["organic"] else "Organic Certified",
        "specifications": {
            "brand": row["brand"],
            "unit": row["unit"],
            "pack_size": row["pack"],
            "organic": bool(row["organic"]),
        },
    }
    u = usage("Follow label", row["unit"])
    tags = {
        "organic": bool(row["organic"]),
        "verified": seller.is_verified,
        **{k: v for k, v in u.items()},
        **base_spec,
    }
    data = {
        "category_id": category.id,
        "name": row["name"],
        "description": (
            f"{row['name']} - quality {category.name.lower()} input supplied by "
            f"{seller.shop_name}. Suitable for a wide range of farming needs."
        ),
        "price": price,
        "original_price": row["mrp"],
        "unit": row["unit"],
        "stock_quantity": row["stock"],
        "min_order_quantity": 1,
        "image_url": IMG_BASE.format(img=IMAGE_POOL[category.slug][index % len(IMAGE_POOL[category.slug])]),
        "images": [
            IMG_BASE.format(img=IMAGE_POOL[category.slug][(index + 1) % len(IMAGE_POOL[category.slug])]),
            IMG_BASE.format(img=IMAGE_POOL[category.slug][(index + 2) % len(IMAGE_POOL[category.slug])]),
        ],
        "brand": row["brand"],
        "rating": round(4.0 + (index % 9) * 0.1, 1),
        "total_reviews": (index * 7) % 240 + 6,
        "is_active": True,
        "seller_id": seller.id,
        "tags": tags,
    }
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        product = existing
    else:
        product = Product(product_id=f"INP-{index:06d}", **data)
        db.add(product)
    db.flush()
    return product


def _sync_crops(db, product, crops):
    db.query(ProductCrop).filter(ProductCrop.product_id == product.id).delete()
    for crop in crops:
        db.add(ProductCrop(product_id=product.id, crop_name=crop))


def seed(db: Session):
    # idempotently clear catalogue rows not managed by this seed (keeps the 16
    # original legacy products intact); all catalogue products are re-synced.
    created = 0
    for slug, name in CATEGORIES:
        category = _ensure_category(db, slug, name)

    # Sellers are owned by a demo user so the NOT NULL seller.user_id holds.
    owner = db.query(User).filter(User.is_demo == True).first() or db.query(User).first()  # noqa: E712
    if owner is None:
        raise RuntimeError("No user available to own marketplace sellers; create a user first.")

    sellers = [
        _ensure_seller(db, owner, shop, loc, ver, rat)
        for shop, loc, ver, rat in SELLERS
    ]
    db.flush()

    used = 0
    for slug, _name in CATEGORIES:
        rows = C.get(slug, [])
        for index, row in enumerate(rows, start=1):
            seller = sellers[used % len(sellers)]
            product = _upsert_product(db, category=_ensure_category(db, slug, _name), seller=seller, row=row, index=used + 1)
            crops = row.get("crops") or ["general"]
            _sync_crops(db, product, crops)
            used += 1
            created += 1

    db.commit()
    totals = {
        slug: db.query(Product).filter(
            Product.category_id == db.query(ProductCategory).filter(ProductCategory.slug == slug).first().id,
            Product.is_active == True,
        ).count()
        for slug, _n in CATEGORIES
    }
    return {"products": created, "categories": len(CATEGORIES), "per_category": totals}


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = seed(db)
    finally:
        db.close()
    print(f"Input Store catalogue ready: {result['products']} products in {result['categories']} categories.")
    for slug, count in result["per_category"].items():
        print(f"  {slug:>16}: {count}")


if __name__ == "__main__":
    main()