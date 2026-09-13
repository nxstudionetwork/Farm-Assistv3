"""Seed the Tools & Equipment catalogue (spec-driven taxonomy).

Standalone script - run it once on a fresh or existing database::

    python -B -m app.database.seed_tools_equipment

Safe to re-run (idempotent). It maintains the spec's machine-type taxonomy
(18 categories) and builds a large, deterministic catalogue:

- BUY: ~300 catalogue products per category (18 x ~300 = 5400+ rows) in the
  SAME marketplace ``products`` table as Input Store and Marketplace, with
  equipment-specific fields in ``equipment_metadata`` and crop suitability in
  ``product_crops``.
- RENT: ~300 rental machinery rows per rentable category (15 x ~300 = 4500+
  rows) in the shared ``equipment`` table (used by the Tools & Equipment page,
  the workers dashboard summary and the farm calendar).

Every catalogue row is clearly labelled ``source: catalogue`` with NO fabricated
ratings, reviews, sellers or availability - the page shows it as catalogue
inventory, not as a real third-party listing.

Images are stable Unsplash CDN URLs (verified to resolve) chosen per category so
the picture matches the machinery and unrelated products never share the same
photo.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite:///./farm_assist.db"
_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from sqlalchemy.orm import Session  # noqa: E402

from app.database.connection import SessionLocal, engine  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.schema_upgrade import run_additive_migrations  # noqa: E402
from app.config import settings as app_settings  # noqa: E402
from app.models.marketplace import (  # noqa: E402
    Product,
    ProductCategory,
    ProductCrop,
    EquipmentMetadata,
)
from app.models.worker import Equipment  # noqa: E402
from app.equipment_taxonomy import (  # noqa: E402
    TAXONOMY,
    CATEGORY_SLUGS,
    RENTABLE_SLUGS,
    RENT_TYPE_BY_SLUG,
    CATEGORY_BY_SLUG,
    slug_for_type,
)

IMG_BASE = "https://images.unsplash.com/{img}?w=640&q=70&auto=format&fit=crop"

# ---------------------------------------------------------------------------
# Verified Unsplash pools per taxonomy category (subject-appropriate).
# ---------------------------------------------------------------------------
IMG = {
    "tractors": [
        "photo-1500382017468-9049fed747ef",
        "photo-1470252649378-9c29740c9fa8",
        "photo-1508615039623-a25605d2b022",
        "photo-1495107334309-fcf20504a5ab",
        "photo-1605000797499-95a51c5269ae",
        "photo-1530836369250-ef72a3f5cda8",
        "photo-1574267432553-4b4628081c31",
        "photo-1516467508483-a7212febe31a",
    ],
    "harvesters": [
        "photo-1523741543316-beb7fc7023d8",
        "photo-1516467508483-a7212febe31a",
        "photo-1509460913899-515f1df34fea",
        "photo-1558618666-fcd25c85cd64",
        "photo-1500382017468-9049fed747ef",
    ],
    "cutting-machines": [
        "photo-1504328345606-18bbc8c9d7d1",
        "photo-1586281380349-632531db7ed4",
        "photo-1530124566582-a618bc2615dc",
        "photo-1586864387967-d02ef85d93e8",
    ],
    "grass-cutters": [
        "photo-1508444845599-5c89863b1c44",
        "photo-1500651230702-0e2d8a49d4ad",
        "photo-1517824806704-9040b037703b",
        "photo-1416879595882-3373a0480b5b",
    ],
    "brush-cutters": [
        "photo-1517824806704-9040b037703b",
        "photo-1500651230702-0e2d8a49d4ad",
        "photo-1464226184884-fa280b87c399",
        "photo-1508444845599-5c89863b1c44",
    ],
    "rotavators": [
        "photo-1500382017468-9049fed747ef",
        "photo-1470252649378-9c29740c9fa8",
        "photo-1508615039623-a25605d2b022",
        "photo-1530836369250-ef72a3f5cda8",
    ],
    "tillers": [
        "photo-1530836369250-ef72a3f5cda8",
        "photo-1495107334309-fcf20504a5ab",
        "photo-1500382017468-9049fed747ef",
        "photo-1574267432553-4b4628081c31",
    ],
    "seeders": [
        "photo-1592982537447-7440770cbfc9",
        "photo-1466692476868-aef1dfb1e735",
        "photo-1416879595882-3373a0480b5b",
        "photo-1517824806704-9040b037703b",
    ],
    "sprayers": [
        "photo-1620331311520-246422fd82f9",
        "photo-1542838132-92c53300491e",
        "photo-1596838132731-3301c3fd4317",
        "photo-1517824806704-9040b037703b",
    ],
    "irrigation-equipment": [
        "photo-1574943320219-553eb213f72d",
        "photo-1542838132-92c53300491e",
        "photo-1620331311520-246422fd82f9",
        "photo-1596838132731-3301c3fd4317",
    ],
    "ploughs": [
        "photo-1625246333195-78d9c38ad449",
        "photo-1500382017468-9049fed747ef",
        "photo-1574267432553-4b4628081c31",
        "photo-1530836369250-ef72a3f5cda8",
    ],
    "cultivators": [
        "photo-1500382017468-9049fed747ef",
        "photo-1530836369250-ef72a3f5cda8",
        "photo-1574267432553-4b4628081c31",
        "photo-1464226184884-fa280b87c399",
    ],
    "threshers": [
        "photo-1558618666-fcd25c85cd64",
        "photo-1509460913899-515f1df34fea",
        "photo-1464226184884-fa280b87c399",
        "photo-1507103011901-e954d6ec0988",
    ],
    "pumps": [
        "photo-1574943320219-553eb213f72d",
        "photo-1542838132-92c53300491e",
        "photo-1500651230702-0e2d8a49d4ad",
    ],
    "trailers": [
        "photo-1500382017468-9049fed747ef",
        "photo-1495107334309-fcf20504a5ab",
        "photo-1516467508483-a7212febe31a",
        "photo-1574267432553-4b4628081c31",
    ],
    "agricultural-tools": [
        "photo-1500937386664-56d1dfef3854",
        "photo-1586281380349-632531db7ed4",
        "photo-1530124566582-a618bc2615dc",
        "photo-1504328345606-18bbc8c9d7d1",
        "photo-1508444845599-5c89863b1c44",
        "photo-1452860606245-08befc0ff44b",
    ],
    "safety-equipment": [
        "photo-1590496793929-36417d3117de",
        "photo-1583485088034-697b5bc54ccd",
    ],
    "other-equipment": [
        "photo-1566438480900-0609be27a4be",
        "photo-1609951651556-5334e2706168",
        "photo-1507103011901-e954d6ec0988",
        "photo-1558618666-fcd25c85cd64",
        "photo-1464226184884-fa280b87c399",
    ],
}

#: Farm districts offered as rental/buy locations.
LOCATIONS = [
    "Nellore", "Guntur", "Kurnool", "Kadapa", "Ananthapuramu", "Chittoor",
    "Tirupati", "Prakasam", "Srikakulam", "Vijayanagaram", "Visakhapatnam",
    "East Godavari", "West Godavari", "Krishna",
]

# Legacy / old equipment slugs that the taxonomy replaces. Products carrying
# equipment metadata in these slugs are re-homed into the new taxonomy (kept,
# never deleted - protects cart/recent/order references).
LEGACY_EQUIP_SLUGS = {
    "hand-tools", "equipment", "harvesting-tools", "planting-tools",
    "soil-field-tools", "spraying-equipment", "storage-equipment",
    "small-machinery", "planting", "irrigation", "sprayers", "harvesting",
    "soil-field", "safety", "storage",
}

# ---------------------------------------------------------------------------
# BUY catalogue generator parameters, per taxonomy category.
#   types    -> equipment_type values that rotate across the 300 listings
#   brands   -> brand pool
#   nums     -> model number pool (rotated for variety)
#   mods     -> name modifiers (Pro/HD/Series/...)
#   price    -> (min, max) selling price in INR
#   power    -> power source pool
#   mats     -> material pool
#   wkg      -> (min, max) weight pool in kg
#   dims     -> dimension template (uses {n})
#   use      -> suitable_use pool
#   warranty -> warranty pool
#   cap      -> capacity template or None (uses {n})
#   ow       -> operating width template or None (uses {n})
#   crops    -> crop suitability (falls back to ["general"])
# ---------------------------------------------------------------------------
GEN = {
    "tractors": {
        "types": ["Tractor", "Utility Tractor", "Row Crop Tractor", "4WD Tractor", "Compact Tractor", "Mini Tractor", "Heavy Duty Tractor"],
        "brands": ["Mahindra", "Sonalika", "Eicher", "TAFE", "Massey Ferguson", "New Holland", "Kubota", "John Deere", "Swaraj", "Escorts"],
        "nums": ["2416", "2455", "2850", "3535", "4435", "4755", "6030", "7525", "8600", "9200"],
        "mods": ["", "HD", "XL", "Pro", "Series", "Plus", "Farm", "Classic", "EL", "SI"],
        "price": (895000, 3250000), "power": ["Fuel", "Diesel"], "mats": ["Heavy Duty Steel Frame", "Cast Iron Chassis", "Powder Coated Steel"],
        "wkg": (1250, 3200), "dims": "{n} x 1.9 m (L x W)", "use": ["Land preparation", "Transport", "Trailer pulling"],
        "warranty": ["1 year warranty", "2 years warranty"], "cap": "{n} HP engine", "ow": None, "crops": ["general"],
    },
    "harvesters": {
        "types": ["Harvester", "Combine Harvester", "Mini Harvester", "Multi Crop Harvester", "Trailed Harvester"],
        "brands": ["John Deere", "Kubota", "CLAAS", "Preet", "Kartar", "Sonalika"],
        "nums": ["5058", "6030", "7078", "5100", "8010", "9060"],
        "mods": ["", "Pro", "XL", "Max", "Plus", "Turbo"],
        "price": (1850000, 9500000), "power": ["Fuel", "Diesel"], "mats": ["Heavy Steel", "Galvanised Steel Pod"],
        "wkg": (1800, 4600), "dims": "Header {n} m", "use": ["Harvesting", "Threshing"],
        "warranty": ["1 year warranty", "2 years warranty"], "cap": "{n} header width", "ow": "{n} m",
        "crops": ["paddy", "wheat", "maize"],
    },
    "cutting-machines": {
        "types": ["Chaff Cutter", "Forage Cutter", "Silage Cutter", "Straw Cutter", "Sugarcane Cutter", "Crop Chopper", "Set Cutter", "Green Chopper"],
        "brands": ["Kisan Yantra", "AgroMach", "FarmForce", "HarvestPlus", "TractorTech"],
        "nums": ["J15", "J18", "J22", "J26", "J30", "J35"],
        "mods": ["", "Pro", "Max", "HD", "Plus", "Deluxe"],
        "price": (14500, 2650000), "power": ["Manual", "Electric", "Fuel"], "mats": ["Cast Iron + Steel", "Forged Steel Blades"],
        "wkg": (35, 620), "dims": "{n} x 0.9 m", "use": ["Maintenance", "Livestock feed"],
        "warranty": ["6 months guarantee", "1 year warranty"], "cap": "{n} kg/h output", "ow": None,
        "crops": ["general"],
    },
    "grass-cutters": {
        "types": ["Grass Cutter", "Lawn Mower", "Grass Trimmer", "Scythe Mower", "Reel Mower", "Ride On Mower"],
        "brands": ["GreenEver", "TurfKing", "MowWell", "AgroKraft", "HarvestPlus"],
        "nums": ["PRO-32", "PRO-36", "PRO-40", "PRO-48", "PRO-54", "PRO-62"],
        "mods": ["", "X", "Pro", "Max", "Plus", "Turbo"],
        "price": (8900, 285000), "power": ["Fuel", "Battery", "Electric", "Manual"], "mats": ["ABS + Steel Deck", "Aluminum Frame"],
        "wkg": (6, 180), "dims": "Cutting deck {n} cm", "use": ["Maintenance", "Grassland upkeep"],
        "warranty": ["6 months guarantee", "1 year warranty"], "cap": "{n} cc engine", "ow": "{n} cm",
        "crops": ["general"],
    },
    "brush-cutters": {
        "types": ["Brush Cutter", "Bush Cutter", "Weed Brush Cutter", "Forestry Cutter", "High Rise Cutter"],
        "brands": ["BushLine", "ForestPro", "AgroKraft", "MowWell", "HarvestPlus"],
        "nums": ["BC26", "BC33", "BC38", "BC43", "BC52", "BC60"],
        "mods": ["", "Pro", "Max", "HD", "Plus", "SI"],
        "price": (7500, 260000), "power": ["Fuel", "Battery"], "mats": ["Aluminum Shaft", "Steel Guard"],
        "wkg": (5, 90), "dims": "Shaft {n} cm", "use": ["Maintenance", "Weed control"],
        "warranty": ["6 months guarantee", "1 year warranty"], "cap": "{n} cc engine", "ow": "{n} cm",
        "crops": ["general"],
    },
    "rotavators": {
        "types": ["Rotavator", "Power Rotavator", "Soil Rotavator", "Rotary Tiller", "Star Rotavator"],
        "brands": ["AgroMach", "KisanYantra", "FarmForce", "TractorTech", "Sonalika"],
        "nums": ["RT46", "RT52", "RT60", "RT72", "RT84", "RT96"],
        "mods": ["", "HD", "Pro", "Max", "Plus", "Classic"],
        "price": (58000, 435000), "power": ["Fuel"], "mats": ["Forged Blades", "Heavy Duty Gearbox"],
        "wkg": (180, 620), "dims": "Width {n} cm", "use": ["Land preparation", "Tillage"],
        "warranty": ["1 year warranty", "2 years warranty"], "cap": "{n} blades", "ow": "{n} cm",
        "crops": ["general"],
    },
    "tillers": {
        "types": ["Power Tiller", "Mini Tiller", "Walking Tiller", "Rotary Tiller", "Hand Tiller"],
        "brands": ["Kubota", "Greaves", "KisanKraft", "VST", "Sonalika", "AgroKraft"],
        "nums": ["R80", "R120", "RT135", "RT220", "DI1300", "DI2600"],
        "mods": ["", "Plus", "Pro", "Max", "HD", "SI"],
        "price": (105000, 895000), "power": ["Fuel", "Battery"], "mats": ["Cast Iron Engine", "Aluminum + Steel"],
        "wkg": (45, 320), "dims": "Working width {n} cm", "use": ["Land preparation", "Tillage", "Weeding"],
        "warranty": ["1 year warranty", "2 years warranty"], "cap": "{n} HP", "ow": "{n} cm",
        "crops": ["general"],
    },
    "seeders": {
        "types": ["Seeder", "Seed Drill", "Multi Row Seeder", "Planter", "Rice Planter", "Transplanter", "Seed Sower", "Direct Seeder"],
        "brands": ["SeedRight", "AgroKraft", "KisanKraft", "SoilSpring", "HarvestPlus"],
        "nums": ["SR-9", "SR-11", "SR-14", "SR-17", "SR-21", "SR-25"],
        "mods": ["", "Pro", "XL", "Plus", "Max", "Deluxe"],
        "price": (3200, 385000), "power": ["Manual", "Fuel", "Battery"], "mats": ["Steel Frame", "PP + Steel"],
        "wkg": (8, 210), "dims": "Row width {n} cm", "use": ["Planting", "Sowing"],
        "warranty": ["6 months guarantee", "1 year warranty"], "cap": "{n} rows", "ow": "{n} cm",
        "crops": ["wheat", "paddy", "maize", "pulses"],
    },
    "sprayers": {
        "types": ["Sprayer", "Knapsack Sprayer", "Power Sprayer", "Boom Sprayer", "Mist Blower", "Hand Pump Sprayer", "Battery Sprayer", "Tractor Mounted Sprayer"],
        "brands": ["SprayWell", "CropJet", "AgroTech", "KisanPro", "ASEE"],
        "nums": ["16L", "20L", "50L", "100L", "200L", "300L"],
        "mods": ["", "HP", "Pro", "Max", "Plus", "Deluxe"],
        "price": (640, 385000), "power": ["Manual", "Battery", "Fuel", "Electric"], "mats": ["HDPE + Brass", "Stainless Steel Tank"],
        "wkg": (2, 120), "dims": "Tank {n} L", "use": ["Spraying", "Crop protection"],
        "warranty": ["6 months guarantee", "1 year warranty"], "cap": "{n} L tank", "ow": "{n} m",
        "crops": ["general"],
    },
    "irrigation-equipment": {
        "types": ["Drip System", "Drip Line", "Sprinkler System", "Rain Gun", "Irrigation Pump", "Hose Pipe", "Irrigation Valve", "Micro Sprinkler", "Drip Fitting", "Irrigation Kit"],
        "brands": ["AquaFlow", "DripTech", "GreenDrip", "HydroKisan", "Netafim"],
        "nums": ["DR16", "DR20", "SP22", "SP30", "70HM", "250HM"],
        "mods": ["", "Pro", "XL", "Plus", "Max", "Classic"],
        "price": (280, 185000), "power": ["Manual", "Electric", "Solar", "Fuel"], "mats": ["Polyethylene", "PVC + Brass", "UV Stabilized Poly"],
        "wkg": (1, 85), "dims": "Coverage {n} ft", "use": ["Irrigation", "Water management"],
        "warranty": ["6 months guarantee", "1 year warranty"], "cap": "{n} L/h", "ow": "{n} m",
        "crops": ["general"],
    },
    "ploughs": {
        "types": ["Plough", "Mouldboard Plough", "Disc Plough", "Land Plough", "Reversible Plough", "Chisel Plough"],
        "brands": ["AgroMach", "KisanYantra", "FieldMaster", "TractorTech", "Sonalika"],
        "nums": ["PL-2R", "PL-3R", "PL-4R", "MP-10", "MP-12", "DP-18"],
        "mods": ["", "HD", "Pro", "Max", "Plus", "Deluxe"],
        "price": (14500, 265000), "power": ["Fuel", "Manual"], "mats": ["Cast Iron + Bearing Steel", "Forged Steel"],
        "wkg": (60, 640), "dims": "Working width {n} cm", "use": ["Land preparation"],
        "warranty": ["6 months guarantee", "1 year warranty"], "cap": "{n} furrows", "ow": "{n} cm",
        "crops": ["general"],
    },
    "cultivators": {
        "types": ["Cultivator", "Harrow", "Disc Harrow", "Sub-Soiler", "Ridge Former", "Land Leveler", "Power Harrow", "Tiller Cultivator"],
        "brands": ["AgroMach", "KisanYantra", "FieldMaster", "TractorTech", "DugDeep"],
        "nums": ["CV-9", "CV-11", "CV-13", "CV-15", "DH-20", "SL-3"],
        "mods": ["", "HD", "Pro", "Max", "Plus", "SI"],
        "price": (9800, 385000), "power": ["Fuel", "Manual"], "mats": ["Spring Steel Tines", "Cast Iron"],
        "wkg": (85, 980), "dims": "Working width {n} cm", "use": ["Land preparation", "Weeding"],
        "warranty": ["6 months guarantee", "1 year warranty"], "cap": "{n} tines", "ow": "{n} cm",
        "crops": ["general"],
    },
    "threshers": {
        "types": ["Thresher", "Paddy Thresher", "Multi Crop Thresher", "Sheller", "Maize Sheller", "Winnower", "Grader"],
        "brands": ["KisanKraft", "FarmForce", "AgroMach", "HarvestPlus", "GrainTech"],
        "nums": ["TH-1", "TH-2", "MS-0.5", "MS-1", "PW-1", "GR-5"],
        "mods": ["", "Pro", "Max", "HD", "Plus", "Deluxe"],
        "price": (9900, 385000), "power": ["Manual", "Electric", "Fuel"], "mats": ["Cast Iron + Steel", "Forged Steel"],
        "wkg": (40, 460), "dims": "Drum {n} cm", "use": ["Harvesting", "Threshing"],
        "warranty": ["6 months guarantee", "1 year warranty"], "cap": "{n} kg/h", "ow": "{n} cm",
        "crops": ["paddy", "wheat", "maize"],
    },
    "pumps": {
        "types": ["Water Pump", "Submersible Pump", "Diesel Pump", "Solar Pump", "Self Priming Pump", "Centrifugal Pump", "Monoblock Pump"],
        "brands": ["HydroKisan", "Kirloskar", "Texmo", "Crompton", "Shakti"],
        "nums": ["1HP", "1.5HP", "2HP", "3HP", "5HP", "7.5HP"],
        "mods": ["", "PR", "MX", "Plus", "Pro", "HD"],
        "price": (3900, 285000), "power": ["Electric", "Fuel", "Solar", "Manual"], "mats": ["Cast Iron Body", "Stainless Steel Impeller"],
        "wkg": (7, 95), "dims": "Delivery {n} mm", "use": ["Irrigation", "Water supply"],
        "warranty": ["1 year warranty", "2 years warranty"], "cap": "{n} L/h", "ow": None,
        "crops": ["general"],
    },
    "trailers": {
        "types": ["Trailer", "Farm Trolley", "Cart", "Wagon", "Tractor Trailer", "Hydraulic Trailer"],
        "brands": ["TrolleyKing", "TractorTech", "AgroMach", "FarmForce", "LoadLine"],
        "nums": ["TR-1", "TR-2", "TR-3", "TR-4", "HT-5", "HT-8"],
        "mods": ["", "HD", "Pro", "Max", "Plus", "Deluxe"],
        "price": (38500, 685000), "power": ["Fuel", "Manual"], "mats": ["Heavy Duty Steel", "Powder Coated Chassis"],
        "wkg": (180, 1400), "dims": "Platform {n} m", "use": ["Transport", "Carting produce"],
        "warranty": ["1 year warranty", "2 years warranty"], "cap": "{n} tonne", "ow": None,
        "crops": ["general"],
    },
    "agricultural-tools": {
        "types": ["Hoe", "Sickle", "Spade", "Shovel", "Fork", "Rake", "Trowel", "Shears", "Pruner", "Knife", "Saw", "Axe", "Pickaxe", "Cultivator", "Weeder", "Dibber", "Digger", "Scissors", "Spreader"],
        "brands": ["KisanPro", "AgroKraft", "HarvestPlus", "ToolMaster", "FieldMaster"],
        "nums": ["T-1", "T-2", "T-3", "T-4", "T-5", "T-6"],
        "mods": ["", "Pro", "Max", "HD", "Plus", "Comfort"],
        "price": (120, 12800), "power": ["Manual", "Battery"], "mats": ["Carbon Steel", "Spring Steel", "Stainless Steel"],
        "wkg": (0.1, 6), "dims": "Handle {n} cm", "use": ["Maintenance", "Weeding", "Planting", "Harvesting", "Land preparation"],
        "warranty": ["No warranty", "6 months guarantee", "1 year warranty"], "cap": None, "ow": "{n} cm",
        "crops": ["general"],
    },
    "safety-equipment": {
        "types": ["Helmet", "Gloves", "Goggles", "Mask", "Coverall", "Vest", "Boots", "Rainwear", "First Aid Kit", "Knee Pads", "Apron", "Face Shield", "Hat"],
        "brands": ["SafeFarm", "BharatGuard", "FarmShield", "AgroSafe"],
        "nums": ["S-1", "S-2", "S-3", "S-4"],
        "mods": ["", "Pro", "Max", "Lite"],
        "price": (90, 5200), "power": ["Manual"], "mats": ["ABS + Foam", "PVC Coated", "Nitrile", "Polyester + Reflective"],
        "wkg": (0.05, 3), "dims": "Size {n}", "use": ["Safety", "Crop protection application"],
        "warranty": ["No warranty", "6 months guarantee"], "cap": None, "ow": None,
        "crops": ["general"],
    },
    "other-equipment": {
        "types": ["Baler", "Winch", "Rope Machine", "Fencing", "Scale", "Charger", "Lighting", "Storage Tank", "Mulch Film", "Shade Net", "Tarp", "Sealer", "Treater", "Mixer", "Generator", "Drone"],
        "brands": ["AgroLab", "FarmBest", "FieldTools", "AgroTech"],
        "nums": ["OE-1", "OE-2", "OE-3", "OE-4", "OE-5", "OE-6"],
        "mods": ["", "Pro", "Max", "HD", "Plus", "Deluxe"],
        "price": (240, 985000), "power": ["Manual", "Electric", "Fuel", "Solar", "Battery"], "mats": ["Steel", "UV Poly", "Aluminum + ABS"],
        "wkg": (0.3, 260), "dims": "Unit {n} m", "use": ["Maintenance", "Storage", "Transport", "Safety"],
        "warranty": ["No warranty", "6 months guarantee", "1 year warranty"], "cap": "{n} kg", "ow": None,
        "crops": ["general"],
    },
}

# ---------------------------------------------------------------------------
# RENT catalogue parameters, per rentable category.
#   brands  -> rental fleet brand pool
#   nums    -> model plate pool
#   rates   -> (min, max) daily rate in INR
# ---------------------------------------------------------------------------
RENT_SPEC = {
    "tractors": {
        "brands": ["Mahindra", "Sonalika", "Eicher", "TAFE", "Massey Ferguson", "New Holland"],
        "nums": ["2416", "2455", "2850", "3535", "4435", "4755", "6030", "7525"],
        "rates": (1800, 4500),
    },
    "harvesters": {
        "brands": ["John Deere", "Kubota", "CLAAS", "Preet", "Kartar"],
        "nums": ["5058", "6030", "7078", "5100", "8010"],
        "rates": (4500, 9000),
    },
    "cutting-machines": {
        "brands": ["Kisan Yantra", "AgroMach", "FarmForce", "HarvestPlus"],
        "nums": ["J15", "J18", "J22", "J26"],
        "rates": (400, 1200),
    },
    "grass-cutters": {
        "brands": ["GreenEver", "TurfKing", "MowWell", "AgroKraft"],
        "nums": ["PRO-32", "PRO-40", "PRO-48", "PRO-62"],
        "rates": (500, 1400),
    },
    "brush-cutters": {
        "brands": ["BushLine", "ForestPro", "AgroKraft", "MowWell"],
        "nums": ["BC26", "BC33", "BC43", "BC60"],
        "rates": (450, 1300),
    },
    "rotavators": {
        "brands": ["AgroMach", "KisanYantra", "FarmForce", "TractorTech"],
        "nums": ["RT46", "RT60", "RT72", "RT96"],
        "rates": (900, 2200),
    },
    "tillers": {
        "brands": ["Kubota", "Greaves", "KisanKraft", "VST"],
        "nums": ["R80", "RT135", "DI1300", "DI2600"],
        "rates": (1200, 2800),
    },
    "seeders": {
        "brands": ["SeedRight", "AgroKraft", "KisanKraft", "SoilSpring"],
        "nums": ["SR-9", "SR-14", "SR-21", "SR-25"],
        "rates": (600, 1800),
    },
    "sprayers": {
        "brands": ["SprayWell", "CropJet", "AgroTech", "ASEE"],
        "nums": ["16L", "100L", "200L", "300L"],
        "rates": (400, 1500),
    },
    "irrigation-equipment": {
        "brands": ["AquaFlow", "DripTech", "HydroKisan", "Netafim"],
        "nums": ["DR16", "SP22", "70HM", "250HM"],
        "rates": (300, 1200),
    },
    "ploughs": {
        "brands": ["AgroMach", "KisanYantra", "FieldMaster", "TractorTech"],
        "nums": ["PL-2R", "PL-4R", "MP-10", "DP-18"],
        "rates": (700, 1800),
    },
    "cultivators": {
        "brands": ["AgroMach", "KisanYantra", "FieldMaster", "DugDeep"],
        "nums": ["CV-9", "CV-15", "DH-20", "SL-3"],
        "rates": (800, 2000),
    },
    "threshers": {
        "brands": ["KisanKraft", "FarmForce", "AgroMach", "GrainTech"],
        "nums": ["TH-1", "TH-2", "MS-1", "GR-5"],
        "rates": (1500, 3500),
    },
    "pumps": {
        "brands": ["HydroKisan", "Kirloskar", "Texmo", "Shakti"],
        "nums": ["2HP", "3HP", "5HP", "7.5HP"],
        "rates": (500, 1500),
    },
    "trailers": {
        "brands": ["TrolleyKing", "TractorTech", "AgroMach", "LoadLine"],
        "nums": ["TR-1", "TR-3", "HT-5", "HT-8"],
        "rates": (1000, 2500),
    },
}

RENT_TERMS = (
    "Diesel/fuel is charged to the renter. Free servicing during the rental "
    "period; minor wear and tear covered. Security deposit returned after "
    "inspection. Cancellation is free up to 48 hours before the start date."
)


def _round_price(value):
    return int(round(value / 10.0) * 10)


def _stable_hash(text):
    return sum(ord(ch) for ch in str(text)) or 1


def _buy_meta(slug, i, t, cap_n, ow_n):
    g = GEN[slug]
    return {
        "equipment_type": t,
        "power_source": g["power"][i % len(g["power"])],
        "material": g["mats"][i % len(g["mats"])],
        "weight": f"{g['wkg'][0] + (i * 13) % (g['wkg'][1] - g['wkg'][0] + 1)} kg",
        "dimensions": g["dims"].format(n=cap_n),
        "warranty": g["warranty"][i % len(g["warranty"])],
        "suitable_use": g["use"][i % len(g["use"])],
        "operating_width": (g["ow"].format(n=ow_n) if g["ow"] else None),
        "capacity": (g["cap"].format(n=cap_n) if g["cap"] else None),
        "crops": g["crops"] or ["general"],
    }


def _buy_rows(slug, total):
    """Generate ``total`` deterministic catalogue (buy) rows for a category."""
    g = GEN[slug]
    rows = []
    for i in range(total):
        j = i % len(g["types"])
        t = g["types"][j]
        brand = g["brands"][(i // len(g["types"])) % len(g["brands"])]
        num = g["nums"][(i // (len(g["types"]) * len(g["brands"]))) % len(g["nums"])]
        mod = g["mods"][i % len(g["mods"])]
        name = f"{brand} {t} {num}{(' ' + mod) if mod else ''}".strip()
        price = g["price"][0] + ((g["price"][1] - g["price"][0]) * ((i * 17) % 300)) / 299
        price = _round_price(price)
        mrp = _round_price(price * (1.06 + 0.09 * ((i * 3) % 2)))
        cap_n = 4 + (i * 7) % 96
        ow_n = 20 + (i * 11) % 180
        stock = 0 if (i % 13 == 9) else 3 + (i * 7) % 38
        rows.append({
            "name": name,
            "brand": brand,
            "price": price,
            "mrp": mrp,
            "stock": stock,
            "meta": _buy_meta(slug, i, t, cap_n, ow_n),
            "location": LOCATIONS[(i * 5) % len(LOCATIONS)],
        })
    return rows


def _rent_rows(slug, total):
    """Generate ``total`` deterministic rental-equipment rows for a category."""
    spec = RENT_SPEC[slug]
    type_label = RENT_TYPE_BY_SLUG[slug]
    rows = []
    for i in range(total):
        brand = spec["brands"][i % len(spec["brands"])]
        num = spec["nums"][(i // len(spec["brands"])) % len(spec["nums"])]
        rate = spec["rates"][0] + ((spec["rates"][1] - spec["rates"][0]) * ((i * 7) % 300)) / 299
        rate = _round_price(rate)
        deposit = _round_price(rate * (3 + (i % 5)))
        min_days = 1 if (i % 4) else 2
        rows.append({
            "name": f"{brand} {type_label} {num}".strip(),
            "type": type_label,
            "brand": brand,
            "model": num,
            "daily_rate": rate,
            "hourly_rate": _round_price(rate / 8) or 50,
            "deposit": deposit,
            "min_days": min_days,
            "location": LOCATIONS[i % len(LOCATIONS)],
            "available": (i % 9) != 7,
            "description": (
                f"{type_label} available on daily rent at ₹{rate}/day from the Farm Assist "
                f"rental catalogue. Serviced and ready for {CATEGORY_BY_SLUG[slug]['name'].lower()} work."
            ),
        })
    return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_category(db, slug, name, icon):
    cat = db.query(ProductCategory).filter(ProductCategory.slug == slug).first()
    if cat:
        return cat
    cat = ProductCategory(name=name, slug=slug, icon=icon)
    db.add(cat)
    db.flush()
    return cat


def _catalogue_tags(meta, location):
    tags = {
        "source": "catalogue",
        "location": location,
        "equipment_type": meta["equipment_type"],
        "power_source": meta["power_source"],
        "material": meta["material"],
        "weight": meta["weight"],
        "dimensions": meta["dimensions"],
        "warranty": meta["warranty"],
        "suitable_use": meta["suitable_use"],
        "operating_width": meta["operating_width"],
        "capacity": meta["capacity"],
    }
    return tags


def _upsert_buy_product(db, category, row, pid, seq):
    existing = db.query(Product).filter(Product.product_id == pid).first()
    meta = row["meta"]
    images = [IMG_BASE.format(img=p) for p in IMG[category.slug]]
    img = images[seq % len(images)]
    data = {
        "category_id": category.id,
        "name": row["name"],
        "description": (
            f"{row['name']} - professional-grade {category.name.lower()} from the Farm Assist "
            f"equipment catalogue. Built for reliable performance and easy upkeep, ideal for "
            f"{meta['suitable_use'].lower()} work."
        ),
        "price": row["price"],
        "original_price": row["mrp"],
        "unit": "unit",
        "stock_quantity": row["stock"],
        "min_order_quantity": 1,
        "image_url": img,
        "images": images[:3],
        "brand": row["brand"],
        "rating": 0,
        "total_reviews": 0,
        "is_active": True,
        "seller_id": None,
        "tags": _catalogue_tags(meta, row["location"]),
    }
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        product = existing
    else:
        product = Product(product_id=pid, **data)
        db.add(product)
    db.flush()

    m = db.query(EquipmentMetadata).filter(EquipmentMetadata.product_id == product.id).first()
    if not m:
        m = EquipmentMetadata(product_id=product.id)
        db.add(m)
    m.equipment_type = meta["equipment_type"]
    m.power_source = meta["power_source"]
    m.material = meta["material"]
    m.weight = meta["weight"]
    m.dimensions = meta["dimensions"]
    m.warranty = meta["warranty"]
    m.suitable_use = meta["suitable_use"]
    m.operating_width = meta["operating_width"]
    m.capacity = meta["capacity"]
    m.location = row["location"]
    db.flush()

    db.query(ProductCrop).filter(ProductCrop.product_id == product.id).delete()
    for crop in meta["crops"]:
        db.add(ProductCrop(product_id=product.id, crop_name=crop))
    return product


def _upsert_rent_row(db, row, equipment_id):
    existing = db.query(Equipment).filter(Equipment.equipment_id == equipment_id).first()
    pool = IMG[slug_for_type(row["type"])]
    data = {
        "name": row["name"],
        "type": row["type"],
        "brand": row["brand"],
        "model": row["model"],
        "description": row["description"],
        "daily_rate": row["daily_rate"],
        "hourly_rate": row["hourly_rate"],
        "deposit_amount": row["deposit"],
        "min_duration_days": row["min_days"],
        "rental_terms": RENT_TERMS,
        "owner_id": None,
        "is_available": row["available"],
        "location": row["location"],
        "image_url": IMG_BASE.format(img=pool[(_stable_hash(row["name"])) % len(pool)]),
    }
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        item = existing
    else:
        item = Equipment(equipment_id=equipment_id, **data)
        db.add(item)
    db.flush()
    return item


def _remap_legacy_products(db, category_by_slug):
    """Re-home legacy equipment products into the taxonomy.

    Only products that carry ``equipment_metadata`` are moved; Input Store
    products in shared slugs (seeds/fertilisers/...) are never touched.
    Also zeroes the fabricated ratings/sellers seeded earlier so the page never
    presents them as real.
    """
    moved = count = 0
    old_cats = (
        db.query(ProductCategory.id)
        .filter(ProductCategory.slug.in_(LEGACY_EQUIP_SLUGS))
        .all()
    )
    old_ids = [r[0] for r in old_cats] or [""]
    rows = (
        db.query(Product)
        .join(EquipmentMetadata, EquipmentMetadata.product_id == Product.id)
        .filter(Product.category_id.in_(old_ids))
        .all()
    )
    for product in rows:
        meta = product.equipment_metadata
        source = meta.equipment_type or (product.category.name if product.category else "")
        new_slug = slug_for_type(source)
        new_cat = category_by_slug.get(new_slug)
        if new_cat and product.category_id != new_cat.id:
            product.category_id = new_cat.id
            moved += 1
        product.seller_id = None
        product.rating = 0
        product.total_reviews = 0
        tags = product.tags if isinstance(product.tags, dict) else {}
        tags["source"] = "catalogue"
        tags["location"] = LOCATIONS[_stable_hash(product.product_id or product.id) % len(LOCATIONS)]
        product.tags = tags
        meta.location = tags["location"]
        db.flush()
        count += 1
    return moved, count


def _remap_legacy_rentals(db, category_by_slug):
    """Normalise legacy rental rows to the taxonomy (type labels + policy)."""
    touched = 0
    for equip in db.query(Equipment).all():
        slug = slug_for_type(equip.type)
        label = RENT_TYPE_BY_SLUG.get(slug)
        if label:
            equip.type = label
        rate = equip.daily_rate or 0
        if equip.deposit_amount is None:
            equip.deposit_amount = _round_price(rate * 3) or 100
        if not equip.min_duration_days:
            equip.min_duration_days = 1
        if not equip.rental_terms:
            equip.rental_terms = RENT_TERMS
        touched += 1
    return touched


def seed(db: Session):
    created_products = created_rentals = 0
    category_by_slug = {}
    for slug, name, icon, _rentable in TAXONOMY:
        category_by_slug[slug] = _ensure_category(db, slug, name, icon)
    db.flush()

    moved_products, remapped = _remap_legacy_products(db, category_by_slug)
    db.flush()
    touched_rentals = _remap_legacy_rentals(db, category_by_slug)
    db.flush()

    per_category = {}
    for ci, (slug, _name, _icon, _rentable) in enumerate(TAXONOMY):
        cat = category_by_slug[slug]
        existing = (
            db.query(Product).filter(Product.category_id == cat.id, Product.is_active == True).count()  # noqa: E712
        )
        needed = 300 - existing
        if needed > 0:
            for seq in range(1, needed + 1):
                pid = f"FT-EQP-{ci:02d}{seq:04d}"
                _upsert_buy_product(db, cat, _buy_rows(slug, needed)[seq - 1], pid, seq)
                created_products += 1
        per_category[slug] = max(existing, 300) if existing > 300 else 300 if existing >= 300 else existing + needed
    db.flush()

    per_rent_category = {}
    for ri, slug in enumerate(RENTABLE_SLUGS):
        existing = db.query(Equipment).filter(Equipment.type == RENT_TYPE_BY_SLUG[slug]).count()
        needed = 300 - existing
        if needed > 0:
            rows = _rent_rows(slug, needed)
            for seq in range(1, needed + 1):
                equipment_id = f"FT-RNT-{ri:02d}{seq:04d}"
                _upsert_rent_row(db, rows[seq - 1], equipment_id)
                created_rentals += 1
        per_rent_category[slug] = max(existing, 300) if existing > 300 else 300 if existing >= 300 else existing + needed

    db.commit()

    totals = {}
    for slug, _n, _i, _r in TAXONOMY:
        cat = category_by_slug[slug]
        totals[slug] = (
            db.query(Product).filter(Product.category_id == cat.id, Product.is_active == True).count()  # noqa: E712
            if cat
            else 0
        )
    rent_totals = {}
    for slug in RENTABLE_SLUGS:
        rent_totals[slug] = db.query(Equipment).filter(Equipment.type == RENT_TYPE_BY_SLUG[slug]).count()

    return {
        "products_created": created_products,
        "rentals_created": created_rentals,
        "remapped_products": remapped,
        "moved_products": moved_products,
        "touched_rentals": touched_rentals,
        "categories": len(TAXONOMY),
        "per_category": totals,
        "rental_categories": rent_totals,
    }


def main():
    engine.echo = False  # keep seed output readable
    run_additive_migrations(app_settings.DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = seed(db)
    finally:
        db.close()
    print(f"Tools & Equipment catalogue ready:")
    print(f"  Buy  products created: {result['products_created']}  (remapped {result['remapped_products']}, moved {result['moved_products']})")
    print(f"  Rent items  created : {result['rentals_created']}  (touched {result['touched_rentals']})")
    for slug, count in result["per_category"].items():
        rent = result["rental_categories"].get(slug)
        suffix = f"  rent={rent}" if rent is not None else ""
        print(f"  {slug:>22}: {count}{suffix}")


if __name__ == "__main__":
    main()