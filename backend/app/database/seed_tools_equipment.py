"""Seed the Tools & Equipment catalogue.

Standalone script - run it once on a fresh or existing database::

    python -B -m app.database.seed_tools_equipment

Safe to re-run (idempotent). It creates the equipment categories and a
realistic catalogue of 300+ farm tools & equipment. Every row lands in the
SAME marketplace ``products`` table as Input Store and Marketplace, with
equipment-specific fields in ``equipment_metadata`` and crop suitability in
``product_crops`` - so a product shows the same image and data on every page.

Images are the same stable Unsplash CDN URLs used by the Input Store seeder
(per category), so product photographs are consistent and reproducible.
"""

import os
import sys

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
    EquipmentMetadata,
    Seller,
)

IMG_BASE = "https://images.unsplash.com/{img}?w=640&q=70&auto=format&fit=crop"

EQUIP_IMG = {
    "hand-tools": [
        "photo-1500937386664-56d1dfef3854",
        "photo-1416879595882-3373a0480b5b",
        "photo-1466692476868-aef1dfb1e735",
    ],
    "equipment": [
        "photo-1500382017468-9049fed747ef",
        "photo-1523741543316-beb7fc7023d8",
        "photo-1470252649378-9c29740c9fa8",
    ],
    "irrigation-equipment": [
        "photo-1574943320219-553eb213f72d",
        "photo-1542838132-92c53300491e",
        "photo-1625246333195-78d9c38ad449",
    ],
    "harvesting-tools": [
        "photo-1523741543316-beb7fc7023d8",
        "photo-1500382017468-9049fed747ef",
        "photo-1416879595882-3373a0480b5b",
    ],
    "planting-tools": [
        "photo-1592982537447-7440770cbfc9",
        "photo-1466692476868-aef1dfb1e735",
        "photo-1416879595882-3373a0480b5b",
    ],
    "soil-field-tools": [
        "photo-1508615039623-a25605d2b022",
        "photo-1500382017468-9049fed747ef",
    ],
    "spraying-equipment": [
        "photo-1470252649378-9c29740c9fa8",
        "photo-1523741543316-beb7fc7023d8",
        "photo-1500382017468-9049fed747ef",
    ],
    "safety-equipment": [
        "photo-1500937386664-56d1dfef3854",
        "photo-1508615039623-a25605d2b022",
    ],
    "storage-equipment": [
        "photo-1566438480900-0609be27a4be",
        "photo-1609951651556-5334e2706168",
    ],
    "small-machinery": [
        "photo-1500382017468-9049fed747ef",
        "photo-1500937386664-56d1dfef3854",
    ],
    "other-equipment": [
        "photo-1586281380349-632531db7ed4",
        "photo-1495107334309-fcf20504a5ab",
        "photo-1508615039623-a25605d2b022",
    ],
}

CATEGORIES = [
    ("hand-tools", "Hand Tools", "fa-hand"),
    ("equipment", "Farm Equipment", "fa-tractor"),
    ("irrigation-equipment", "Irrigation Equipment", "fa-droplet"),
    ("harvesting-tools", "Harvesting Tools", "fa-wheat-awn"),
    ("planting-tools", "Planting Tools", "fa-seedling"),
    ("soil-field-tools", "Soil & Field Tools", "fa-mound"),
    ("spraying-equipment", "Spraying Equipment", "fa-spray-can"),
    ("safety-equipment", "Safety Equipment", "fa-helmet-safety"),
    ("storage-equipment", "Storage Equipment", "fa-warehouse"),
    ("small-machinery", "Small Farm Machinery", "fa-gears"),
    ("other-equipment", "Other Equipment", "fa-box-open"),
]

SELLERS = [
    ("Krishi Yantra Agencies", "Ludhiana, Punjab", True, 4.7),
    ("AgroMach Distributors", "Rajkot, Gujarat", True, 4.5),
    ("Kisan Tools N More", "Hisar, Haryana", True, 4.4),
    ("FarmTech Implements", "Coimbatore, Tamil Nadu", False, 4.2),
    ("GreenField Equipment", "Pune, Maharashtra", False, 4.1),
    ("Harvest House Traders", "Nashik, Maharashtra", False, 4.0),
]

ALL_CROPS = ["general"]
EQUIPMENT_CROPS = [
    "paddy", "maize", "cotton", "groundnut", "chilli", "wheat",
    "soybean", "vegetables", "pulses", "sunflower",
]

# Legacy equipment category slugs created by earlier seeders. Equipment
# products currently sitting in these slugs are migrated into the new
# taxonomy so the Tools & Equipment page owns them and Input Store's shared
# categories (irrigation/sprayers/...) are never polluted.
LEGACY_SLUG_MAP = {
    "planting": "planting-tools",
    "irrigation": "irrigation-equipment",
    "sprayers": "spraying-equipment",
    "harvesting": "harvesting-tools",
    "soil-field": "soil-field-tools",
    "safety": "safety-equipment",
    "storage": "storage-equipment",
}

# ---------------------------------------------------------------------------
# Catalogue.  category -> list of:
#   (name, brand, price, mrp|None, stock,
#    equipment_type, power_source, material, weight, dimensions, warranty,
#    suitable_use, capacity|None, operating_width|None, crops|None)
# ---------------------------------------------------------------------------
C = {}


def et(equip_type, power, mat, weight, dims, warranty, use, cap=None, ow=None, crops=None):
    return {
        "equipment_type": equip_type, "power_source": power, "material": mat,
        "weight": weight, "dimensions": dims, "warranty": warranty,
        "suitable_use": use, "capacity": cap, "operating_width": ow,
        "crops": crops or ["general"],
    }


# --- Hand Tools ------------------------------------------------------------
C["hand-tools"] = []
_T = [
    ("Garden Anvil Pruner", 349, 420, 120, et("Pruner", "Manual", "Carbon Steel", "0.35 kg", "18 cm", "6 months guarantee", "Maintenance", ow="2 cm")),
    ("Bypass Secateurs 8\"", 429, 520, 88, et("Pruner", "Manual", "High Carbon Steel", "0.4 kg", "20 cm", "1 year warranty", "Maintenance", ow="2.5 cm")),
    ("Lopping Shears (43 cm)", 679, 810, 64, et("Pruner", "Manual", "Carbon Steel", "1.1 kg", "43 cm", "6 months guarantee", "Maintenance", ow="4.5 cm")),
    ("Heavy Duty Garden Hand Hoe", 289, 350, 140, et("Hoe", "Manual", "Manganese Steel", "0.8 kg", "28 cm handle", "6 months guarantee", "Weeding", ow="8 cm")),
    ("Crowbar Hoe (Country Hoe)", 359, 430, 95, et("Hoe", "Manual", "Carbon Steel", "1.6 kg", "110 cm", "6 months guarantee", "Weeding", ow="15 cm")),
    ("Hand Trowel (Stainless)", 185, 230, 160, et("Trowel", "Manual", "Stainless Steel", "0.2 kg", "31 cm", "No warranty", "Maintenance")),
    ("Transplant Trowel", 210, 260, 130, et("Trowel", "Manual", "Stainless Steel", "0.25 kg", "33 cm", "No warranty", "Maintenance")),
    ("Mini Weeder Hand Fork", 165, 200, 170, et("Fork", "Manual", "Spring Steel", "0.18 kg", "24 cm", "6 months guarantee", "Weeding", ow="6 cm")),
    ("Three Tine Cultivator Hand Tool", 275, 330, 110, et("Cultivator", "Manual", "Cast Iron", "0.7 kg", "35 cm", "1 year warranty", "Weeding", ow="12 cm")),
    ("Stainless Steel Manure Fork", 545, 650, 75, et("Fork", "Manual", "Stainless Steel", "1.5 kg", "120 cm", "1 year warranty", "Transport")),
    ("Garlic Peeling Hammer", 199, 240, 90, et("Hammer", "Manual", "Cast Iron", "0.5 kg", "20 cm", "No warranty", "Maintenance")),
    ("Sickle - Heavy Grade (Jasike)", 159, 195, 220, et("Sickle", "Manual", "Carbon Steel", "0.3 kg", "35 cm", "No warranty", "Harvesting", ow="12 cm")),
    ("Sickle - Serrated PVC Grip", 179, 220, 190, et("Sickle", "Manual", "High Carbon Steel", "0.28 kg", "33 cm", "No warranty", "Harvesting", ow="11 cm")),
    ("Wooden Garden Rake 14 Tine", 385, 460, 85, et("Rake", "Manual", "Steel + Wood", "0.9 kg", "135 cm", "6 months guarantee", "Land preparation", ow="35 cm")),
    ("Steel Garden Rake (Adjustable)", 415, 500, 70, et("Rake", "Manual", "Carbon Steel", "1 kg", "130 cm", "6 months guarantee", "Land preparation", ow="38 cm")),
    ("Dibber Planting Stick", 145, 175, 140, et("Dibber", "Manual", "Hardwood", "0.35 kg", "35 cm", "No warranty", "Planting")),
    ("Garden Scissors (Utility)", 149, 180, 150, et("Scissors", "Manual", "Stainless Steel", "0.12 kg", "17 cm", "No warranty", "Maintenance")),
    ("Hedge Shears 20\"", 685, 820, 55, et("Shears", "Manual", "Carbon Steel", "1.8 kg", "61 cm", "1 year warranty", "Maintenance", ow="20 cm")),
    ("Bamboo Garden Cane Cutter", 265, 320, 60, et("Cutter", "Manual", "Steel", "0.6 kg", "40 cm", "No warranty", "Maintenance")),
    ("Root Slayer Garden Axe", 745, 890, 40, et("Axe", "Manual", "Forged Steel", "1.2 kg", "51 cm", "1 year warranty", "Maintenance")),
    ("Hand Cultivator 3 Prong", 205, 250, 120, et("Cultivator", "Manual", "Carbon Steel", "0.5 kg", "33 cm", "6 months guarantee", "Weeding", ow="10 cm")),
    ("Long Handle Weeder (Standing)", 395, 470, 65, et("Hoe", "Manual", "Stainless Steel", "1 kg", "125 cm", "1 year warranty", "Weeding", ow="9 cm")),
    ("Stainless Steel Hand Shovel", 255, 310, 100, et("Shovel", "Manual", "Stainless Steel", "0.45 kg", "34 cm", "6 months guarantee", "Maintenance")),
    ("Transplanting Hand Fork", 175, 215, 130, et("Fork", "Manual", "Stainless Steel", "0.2 kg", "26 cm", "No warranty", "Planting")),
    ("Battery Powered Hedge Trimmer Kit", 1890, 2190, 25, et("Hedge Trimmer", "Battery", "Steel + ABS", "2.4 kg", "68 cm", "2 years warranty", "Maintenance", ow="45 cm")),
    ("ProGard Ultra Multi Cutter", 485, 580, 45, et("Cutter", "Manual", "Spring Steel", "0.55 kg", "32 cm", "6 months guarantee", "Maintenance")),
    ("Sapphire Bypass Loppers (Heavy)", 890, 1065, 35, et("Pruner", "Manual", "Forged Steel", "1.5 kg", "64 cm", "1 year warranty", "Maintenance", ow="5.5 cm")),
    ("Soil Cultivator Hand Tool Combo", 465, 560, 58, et("Cultivator", "Manual", "Carbon Steel", "0.85 kg", "95 cm", "6 months guarantee", "Weeding", ow="14 cm")),
]
for _r in _T:
    C["hand-tools"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Farm Equipment --------------------------------------------------------
C["equipment"] = []
_T = [
    ("Manual Seed Cum Fertilizer Drill", 3490, 3990, 18, et("Seed Drill", "Manual", "Carbon Steel + PVC", "18 kg", "125 x 45 x 60 cm", "1 year warranty", "Planting", cap="5 rows", ow="90 cm", crops=["wheat", "paddy", "maize"])),
    ("Tractor Drawn Mouldboard Plough", 18500, 21000, 6, et("Plough", "Fuel Powered", "Cast Iron + Bearing Steel", "285 kg", "175 x 120 x 95 cm", "1 year warranty", "Land preparation", ow="105 cm")),
    ("Animal Drawn Wooden Plough", 2450, 2850, 12, et("Plough", "Manual", "Teak Wood + Steel", "9 kg", "150 cm", "6 months guarantee", "Land preparation", ow="55 cm")),
    ("Harrow 8 ft (Tractor)", 16300, 18500, 5, et("Harrow", "Fuel Powered", "Spring Steel Tines", "310 kg", "245 cm", "1 year warranty", "Land preparation", ow="245 cm")),
    ("Cultivator 7 Tine (Tractor)", 12800, 14600, 7, et("Cultivator", "Fuel Powered", "Cast Iron", "190 kg", "180 cm", "1 year warranty", "Land preparation", ow="180 cm")),
    ("Rotavator 5 ft", 23800, 26900, 4, et("Rotavator", "Fuel Powered", "Forged Blades", "410 kg", "150 cm", "1 year warranty", "Land preparation", ow="150 cm")),
    ("Laser Land Leveler (6 m)", 198000, 225000, 2, et("Land Leveler", "Fuel Powered", "Heavy Duty Steel", "1850 kg", "600 cm", "2 years warranty", "Land preparation", ow="600 cm")),
    ("Rice Transplanter (Walk Behind)", 78000, 87500, 3, et("Transplanter", "Fuel Powered", "Steel + Aluminum", "128 kg", "210 cm", "1 year warranty", "Planting", cap="4 rows", ow="120 cm", crops=["paddy"])),
    ("Roti Weeder (Manual Paddy)", 1150, 1350, 28, et("Weeder", "Manual", "Carbon Steel", "2.2 kg", "85 cm", "6 months guarantee", "Weeding", ow="16 cm", crops=["paddy", "rice"])),
    ("Jute / Disc Spreader", 3250, 3750, 14, et("Spreader", "Manual", "Steel + Plastic", "7.5 kg", "110 x 40 cm", "1 year warranty", "Planting", cap="12 kg", ow="60 cm")),
    ("Seed Spreader Fertilizer Distributor", 2850, 3300, 16, et("Spreader", "Manual", "Steel + ABS", "5.8 kg", "95 cm", "6 months guarantee", "Planting", cap="15 kg", ow="55 cm")),
    ("Earth Auger (Hand Operated)", 1390, 1600, 22, et("Auger", "Manual", "Carbon Steel", "3.4 kg", "110 cm", "6 months guarantee", "Planting", cap="15 cm bit")),
    ("Garden Cart / Utility Cart", 4650, 5300, 9, et("Cart", "Manual", "Steel Mesh + Wheels", "16 kg", "100 x 55 x 62 cm", "1 year warranty", "Transport", cap="150 kg")),
    ("Farm Trolley (Tractor Mounted)", 26800, 30500, 5, et("Trolley", "Fuel Powered", "Heavy Duty Steel", "620 kg", "300 x 150 cm", "1 year warranty", "Transport", cap="2000 kg")),
    ("Capstan Winch (5 HP)", 8900, 9900, 8, et("Winch", "Electric", "Cast Iron + Steel", "45 kg", "60 x 55 x 40 cm", "1 year warranty", "Transport", cap="1000 kg")),
    ("Groundnut Decorticator (Manual)", 2250, 2600, 15, et("Decorticator", "Manual", "Cast Iron", "11 kg", "75 x 45 x 100 cm", "6 months guarantee", "Harvesting", cap="80 kg/h", crops=["groundnut"])),
    ("Chaff Cutter (Cattle Feed)", 6500, 7400, 10, et("Chaff Cutter", "Manual", "Cast Iron + Steel", "58 kg", "120 x 70 x 110 cm", "1 year warranty", "Maintenance")),
    ("Multipurpose Seed Cleaner", 4200, 4800, 11, et("Seed Cleaner", "Electric", "Steel", "27 kg", "95 x 60 x 70 cm", "1 year warranty", "Maintenance", cap="300 kg/h")),
    ("Farm Gate Lock Kit (Heavy)", 650, 780, 40, et("Hardware", "Manual", "Galvanized Steel", "1.2 kg", "Set", "6 months guarantee", "Maintenance")),
    ("Windrower Attachable Rake", 15200, 17200, 4, et("Rake Attachment", "Fuel Powered", "Spring Steel", "260 kg", "220 cm", "1 year warranty", "Harvesting", ow="220 cm")),
    ("Baler (Mini Fixed Chamber)", 890000, 940000, 1, et("Baler", "Fuel Powered", "Heavy Steel", "1450 kg", "400 cm", "1 year warranty", "Harvesting", ow="90 cm")),
    ("Disc Harrow Tandem 10 ft", 32500, 36500, 3, et("Harrow", "Fuel Powered", "Disc Steel", "480 kg", "300 cm", "1 year warranty", "Land preparation", ow="300 cm")),
    ("Sub-Soiler (Tractor Mounted)", 22800, 25800, 4, et("Sub-Soiler", "Fuel Powered", "Forged Steel", "360 kg", "180 cm", "1 year warranty", "Land preparation", ow="180 cm")),
    ("Furrow Maker (Ridge Former)", 9800, 11200, 6, et("Ridge Former", "Fuel Powered", "Cast Iron + Steel", "120 kg", "150 cm", "1 year warranty", "Land preparation", ow="150 cm")),
    ("Tractor Mounted Sprayer Boom 12 m", 98500, 109000, 2, et("Boom Sprayer", "Fuel Powered", "SS Tank + Steel Boom", "460 kg", "12 m", "1 year warranty", "Spraying", cap="1500 L", ow="1200 cm")),
    ("Pedal Operated Paddy Thresher", 11200, 12900, 7, et("Thresher", "Manual", "Cast Iron + Steel", "95 kg", "160 x 120 cm", "1 year warranty", "Harvesting", cap="300 kg/day", crops=["paddy", "rice"])),
    ("Groundnut Shelling Machine (Power)", 48500, 54500, 3, et("Sheller", "Electric", "Cast Iron", "150 kg", "130 x 90 x 120 cm", "1 year warranty", "Harvesting", cap="350 kg/h", crops=["groundnut"])),
    ("Power Tiller Attachable Weeder", 7800, 8900, 9, et("Weeder", "Fuel Powered", "Spring Steel", "42 kg", "95 cm", "1 year warranty", "Weeding", ow="95 cm")),
]
for _r in _T:
    C["equipment"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Irrigation Equipment --------------------------------------------------
C["irrigation-equipment"] = []
_T = [
    ("Drip Irrigation Kit (1/4 Acre)", 2100, 2400, 22, et("Drip System", "Manual", "PVC + Polyethylene", "9 kg", "Kit", "1 year warranty", "Irrigation", cap="1/4 acre")),
    ("Drip Irrigation Kit (1 Acre)", 6800, 7600, 14, et("Drip System", "Manual", "PVC + Polyethylene", "28 kg", "Kit", "1 year warranty", "Irrigation", cap="1 acre")),
    ("Inline Drip Line 16 mm (200 m)", 1850, 2100, 60, et("Drip System", "Manual", "Polyethylene", "12 kg", "200 m roll", "6 months guarantee", "Irrigation")),
    ("Punching Tool for Drip Line", 240, 290, 80, et("Drip Fitting", "Manual", "Stainless Steel", "0.3 kg", "12 cm", "No warranty", "Irrigation")),
    ("Drip Emitters (4 LPH, 50 pc)", 310, 380, 70, et("Drip Emitter", "Manual", "Polypropylene", "0.4 kg", "pack of 50", "No warranty", "Irrigation")),
    ("Garden Sprinkler Tripod 4 in 1", 1650, 1900, 30, et("Sprinkler", "Manual", "ABS Plastic + Brass", "3.2 kg", "72 cm tripod", "1 year warranty", "Irrigation", ow="15 m")),
    ("Impact Sprinkler Head (1/2\")", 420, 500, 65, et("Sprinkler", "Manual", "Brass Nozzle + ABS", "0.8 kg", "14 cm", "6 months guarantee", "Irrigation", ow="12 m")),
    ("Rotary Lawn Sprinkler (Plastic)", 350, 420, 90, et("Sprinkler", "Manual", "ABS", "0.22 kg", "16 cm", "6 months guarantee", "Irrigation", ow="10 m")),
    ("Self Priming Water Pump 1 HP", 4900, 5600, 12, et("Water Pump", "Electric", "Cast Iron Body", "18 kg", "35 x 30 x 40 cm", "1 year warranty", "Irrigation", cap="3000 L/h")),
    ("Submersible Pump 1.5 HP", 7600, 8600, 9, et("Water Pump", "Electric", "Stainless Steel", "26 kg", "110 x 90 cm", "1 year warranty", "Irrigation", cap="5000 L/h")),
    ("Diesel Water Pump 5 HP", 12500, 14200, 6, et("Water Pump", "Fuel", "Aluminum + Cast Iron", "58 kg", "60 x 50 x 55 cm", "1 year warranty", "Irrigation", cap="18000 L/h")),
    ("Solar Water Pump 1 HP (With Panel)", 38500, 42500, 3, et("Water Pump", "Solar", "SS Impeller + Poly", "90 kg", "Kit", "2 years warranty", "Irrigation", cap="12000 L/day")),
    ("HDPE Garden Hose Pipe 25 mm (50 m)", 1550, 1780, 55, et("Hose", "Manual", "HDPE", "7 kg", "50 m", "6 months guarantee", "Irrigation")),
    ("PVC Flexible Layflat Hose 3\" (90 m)", 3450, 3900, 25, et("Hose", "Manual", "PVC", "16 kg", "90 m", "6 months guarantee", "Irrigation")),
    ("Hose Reel Cart 30 m", 2900, 3300, 18, et("Hose Reel", "Manual", "Steel + ABS", "5.4 kg", "95 x 40 x 80 cm", "1 year warranty", "Irrigation")),
    ("Garden Hose Connector Kit (12 pc)", 380, 460, 85, et("Hose Fitting", "Manual", "Brass + ABS", "0.6 kg", "Kit", "No warranty", "Irrigation")),
    ("4-Way Garden Hose Splitter", 320, 390, 75, et("Hose Fitting", "Manual", "Brass", "0.5 kg", "13 cm", "No warranty", "Irrigation")),
    ("Mini Spray Pump Bottle 1L", 280, 340, 65, et("Spray Pump", "Manual", "PP + HDPE", "0.55 kg", "28 cm", "6 months guarantee", "Irrigation", cap="1 L")),
    ("Watering Jug / Water Can 5L", 290, 350, 80, et("Watering Can", "Manual", "HDPE", "0.7 kg", "42 x 18 cm", "No warranty", "Irrigation", cap="5 L")),
    ("Rain Gun Sprinkler (Heavy Duty)", 890, 1050, 30, et("Sprinkler", "Manual", "Aluminum + Brass", "1.6 kg", "32 cm", "1 year warranty", "Irrigation", ow="25 m")),
    ("Venturi Fertilizer Injector", 720, 850, 28, et("Injector", "Manual", "ABS + NS", "0.4 kg", "18 cm", "6 months guarantee", "Irrigation", cap="16 L/min")),
    ("Flow Control Valve (Drip, 20 pc)", 260, 315, 95, et("Drip Fitting", "Manual", "PP", "0.35 kg", "pack of 20", "No warranty", "Irrigation")),
    ("Foot Operated Water Pump", 1450, 1700, 20, et("Water Pump", "Manual", "Cast Iron", "9 kg", "60 x 30 cm", "6 months guarantee", "Irrigation", cap="1000 L/h")),
    ("Sump Tank 500 Litre (UV)", 6400, 7200, 8, et("Storage Tank", "Manual", "UV Stabilized Poly", "22 kg", "105 x 120 cm", "1 year warranty", "Irrigation", cap="500 L")),
    ("Overhead Water Tank 1000 L", 9800, 11000, 5, et("Storage Tank", "Manual", "UV Stabilized Poly", "35 kg", "135 x 150 cm", "1 year warranty", "Irrigation", cap="1000 L")),
    ("Telescopic Spray Lance", 420, 500, 40, et("Spray Lance", "Manual", "Aluminum", "0.65 kg", "95-180 cm", "6 months guarantee", "Irrigation")),
    ("Micro Sprinkler Kit (100 pc)", 1250, 1450, 35, et("Sprinkler", "Manual", "PP + PE", "4.5 kg", "Kit", "6 months guarantee", "Irrigation", cap="1/2 acre")),
    ("PVC Ball Valve 1\" (Set of 5)", 460, 550, 60, et("Valve", "Manual", "PVC + MS", "1.9 kg", "Set", "6 months guarantee", "Irrigation")),
]
for _r in _T:
    C["irrigation-equipment"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Harvesting Tools ------------------------------------------------------
C["harvesting-tools"] = []
_T = [
    ("Serrated Harvesting Sickle", 185, 225, 120, et("Sickle", "Manual", "Carbon Steel", "0.32 kg", "34 cm", "No warranty", "Harvesting", ow="12 cm", crops=["paddy", "wheat"])),
    ("Heavy Duty Paddy Cutter", 245, 295, 95, et("Sickle", "Manual", "Forge Steel", "0.45 kg", "38 cm", "No warranty", "Harvesting", ow="14 cm", crops=["paddy", "rice"])),
    ("Fruit Picking Net Basket", 420, 500, 70, et("Picker", "Manual", "Steel + Poly Mesh", "1.3 kg", "135 cm pole", "6 months guarantee", "Harvesting", cap="20 kg", crops=["vegetables"])),
    ("Mango Picking Cutter Pole", 560, 660, 45, et("Picker", "Manual", "Aluminum + Steel", "0.9 kg", "180 cm", "6 months guarantee", "Harvesting", crops=["vegetables"])),
    ("Folding Fruit Picker Bag", 380, 450, 55, et("Picker", "Manual", "Canvas + Steel", "0.8 kg", "120 cm", "6 months guarantee", "Harvesting")),
    ("Harvest Basket (Rattan)", 320, 380, 60, et("Basket", "Manual", "Rattan", "1.1 kg", "45 x 30 cm", "No warranty", "Harvesting", cap="15 kg")),
    ("Groundnut Digging Fork", 340, 410, 65, et("Fork", "Manual", "Carbon Steel", "1.4 kg", "95 cm", "6 months guarantee", "Harvesting", ow="15 cm", crops=["groundnut"])),
    ("Potato Spade Digger", 360, 430, 55, et("Spade", "Manual", "Stainless Steel", "1.2 kg", "100 cm", "6 months guarantee", "Harvesting", ow="18 cm", crops=["vegetables"])),
    ("Root Crop Harvesting Claw", 260, 315, 60, et("Claw", "Manual", "Cast Iron", "0.9 kg", "75 cm", "No warranty", "Harvesting", crops=["vegetables", "groundnut"])),
    ("Onion Storage Rack Net", 190, 230, 80, et("Net Rack", "Manual", "Poly Mesh", "0.5 kg", "60 x 40 cm", "No warranty", "Harvesting", cap="25 kg")),
    ("Paddy Reaping Sickle (Kammu)", 155, 190, 130, et("Sickle", "Manual", "Spring Steel", "0.3 kg", "32 cm", "No warranty", "Harvesting", ow="11 cm", crops=["paddy", "rice"])),
    ("Banana Bunch Cutter (Curved)", 890, 1050, 25, et("Cutter", "Manual", "Stainless Steel", "1.8 kg", "150 cm", "6 months guarantee", "Harvesting", ow="20 cm", crops=["vegetables"])),
    ("Palm Srash / Weeding Blade", 210, 255, 70, et("Blade", "Manual", "High Carbon Steel", "0.65 kg", "28 cm", "No warranty", "Harvesting")),
    ("Harvest Trolley Bag (Loader)", 1450, 1680, 20, et("Trolley", "Manual", "Steel Frame + Fabric", "6 kg", "Foldable", "6 months guarantee", "Harvesting", cap="80 kg")),
    ("Sugarcane Cutter (Bite)", 480, 575, 40, et("Cutter", "Manual", "Forged Steel", "0.85 kg", "32 cm", "6 months guarantee", "Harvesting", ow="6 cm")),
    ("Cotton Picking Bag (Dual Hand)", 380, 450, 45, et("Picker", "Manual", "Cotton Canvas", "0.4 kg", "50 x 35 cm", "No warranty", "Harvesting", cap="12 kg", crops=["cotton"])),
    ("Harvesting Gloves (Cut Proof)", 290, 350, 60, et("Gloves", "Manual", "Kevlar Blend", "0.15 kg", "Universal", "No warranty", "Harvesting")),
    ("Paddy Bundling Hook", 230, 280, 50, et("Hook", "Manual", "Carbon Steel", "0.5 kg", "25 cm", "No warranty", "Harvesting", crops=["paddy"])),
    ("Comfort Grip Harvesting Knife", 175, 210, 85, et("Knife", "Manual", "Stainless Steel", "0.22 kg", "22 cm", "No warranty", "Harvesting")),
    ("Corn Husk Remover Tool", 250, 300, 45, et("Peeler", "Manual", "ABS + Steel", "0.3 kg", "18 cm", "No warranty", "Harvesting", crops=["maize"])),
    ("Threshing Mat / Tarp 10x10", 990, 1150, 30, et("Tarp", "Manual", "Laminated HDPE", "4.2 kg", "10 x 10 m", "6 months guarantee", "Harvesting")),
    ("Grain Scoop (Aluminum)", 320, 385, 70, et("Scoop", "Manual", "Aluminum", "0.6 kg", "35 cm", "No warranty", "Harvesting", cap="3 kg")),
    ("Wagon Wheel Hand Cart (Farm)", 2850, 3250, 10, et("Cart", "Manual", "Steel + Pneumatic", "14 kg", "110 x 60 cm", "1 year warranty", "Transport", cap="200 kg")),
    ("Harvest Ladder (4 Step, Foldable)", 2650, 3050, 12, et("Ladder", "Manual", "Aluminum", "6.5 kg", "115 cm", "1 year warranty", "Harvesting")),
    ("Sugarcane Loader Cane Holder", 760, 890, 18, et("Holder", "Manual", "Spring Steel", "2.1 kg", "45 cm", "6 months guarantee", "Transport")),
    ("Sickle Sharpening Stone Set", 180, 220, 90, et("Sharpener", "Manual", "Carborundum", "0.4 kg", "18 cm", "No warranty", "Maintenance")),
    ("Paddy Binder Twine (1 kg)", 245, 295, 65, et("Twine", "Manual", "Jute + PP", "1 kg", "spool", "No warranty", "Harvesting", crops=["paddy"])),
    ("Multi-Purpose Harvest Saw", 520, 620, 30, et("Saw", "Manual", "Hardened Steel", "0.7 kg", "45 cm", "6 months guarantee", "Harvesting", ow="35 cm")),
]
for _r in _T:
    C["harvesting-tools"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Planting Tools --------------------------------------------------------
C["planting-tools"] = []
_T = [
    ("Two Row Manual Seed Planter", 1850, 2120, 15, et("Planter", "Manual", "Steel + PP", "6.8 kg", "105 x 40 cm", "1 year warranty", "Planting", ow="30 cm", crops=["maize", "groundnut", "paddy"])),
    ("Single Row Garden Seed Drill", 1250, 1450, 22, et("Planter", "Manual", "Steel + ABS", "4.5 kg", "95 cm", "6 months guarantee", "Planting", ow="25 cm", crops=["wheat", "pulses"])),
    ("Hand Operated Transplanter", 1450, 1680, 18, et("Transplanter", "Manual", "Stainless Steel", "2.8 kg", "85 cm", "6 months guarantee", "Planting", cap="2 rows", ow="40 cm", crops=["paddy"])),
    ("Garden Planter Seeder (Single)", 890, 1040, 25, et("Planter", "Manual", "Zinc Coated Steel", "3 kg", "70 cm", "6 months guarantee", "Planting", ow="20 cm")),
    ("Corn Planter (Push Type)", 2350, 2700, 10, et("Planter", "Manual", "Steel Frame", "12 kg", "120 cm", "1 year warranty", "Planting", cap="2 rows", ow="60 cm", crops=["maize"])),
    ("Battery Operated Seed Sower", 3450, 3950, 8, et("Planter", "Battery", "ABS + Steel", "6.2 kg", "98 cm", "1 year warranty", "Planting", cap="8 seeds/hole")),
    ("Planting Board / Setter Board", 310, 375, 40, et("Board", "Manual", "Marine Plywood", "0.9 kg", "50 cm", "No warranty", "Planting")),
    ("Seed Sowing Funnel (Bag Mount)", 260, 315, 45, et("Funnel", "Manual", "PP", "0.35 kg", "22 cm", "No warranty", "Planting")),
    ("Protective Planting Gloves (Pair)", 340, 410, 55, et("Gloves", "Manual", "Nitrile Coated", "0.18 kg", "Pair (L)", "No warranty", "Planting")),
    ("Soil Block Maker (Cubical)", 620, 745, 30, et("Block Maker", "Manual", "Aluminum", "1.1 kg", "16 cm", "6 months guarantee", "Planting", cap="6 blocks")),
    ("Potting Tray 50 Cell (Set of 5)", 540, 650, 60, et("Tray", "Manual", "PP", "1.4 kg", "52 x 26 cm", "6 months guarantee", "Planting", cap="50 cells")),
    ("Potting Tray 104 Cell (Set of 3)", 520, 625, 55, et("Tray", "Manual", "PP", "1.2 kg", "52 x 26 cm", "6 months guarantee", "Planting", cap="104 cells")),
    ("Hand Spray Watering Wand for Nursery", 380, 455, 40, et("Wand", "Manual", "ABS", "0.55 kg", "80 cm", "6 months guarantee", "Irrigation")),
    ("Bamboo Plant Support Poles (Set 50)", 780, 920, 35, et("Support", "Manual", "Bamboo", "8 kg", "180 cm x 50", "No warranty", "Planting", crops=["vegetables", "chilli"])),
    ("Tree Guard Net (Set of 10)", 460, 550, 42, et("Guard", "Manual", "PP Mesh", "2.2 kg", "Set", "6 months guarantee", "Planting")),
    ("Ridger / Ridge Maker (Manual)", 1690, 1950, 14, et("Ridger", "Manual", "Steel", "7.5 kg", "110 cm", "1 year warranty", "Land preparation", ow="45 cm")),
    ("Perimeter Garden Marker Rope", 190, 230, 50, et("Marker", "Manual", "Nylon + Pins", "0.5 kg", "25 m", "No warranty", "Planting")),
    ("Bulb Hole Digger (Lifter)", 350, 420, 38, et("Digger", "Manual", "Cast Iron", "1 kg", "80 cm", "6 months guarantee", "Planting", cap="10 cm")),
    ("Wheel Hoe Planter Assembly", 2150, 2450, 12, et("Hoe-Wheel", "Manual", "Steel + Cast Iron", "9 kg", "130 cm", "1 year warranty", "Weeding", ow="20 cm")),
    ("Nursery Polybags 6x8 (500 pc)", 1250, 1450, 40, et("Polybag", "Manual", "PP", "6 kg", "pack of 500", "No warranty", "Planting")),
    ("Coconut Pit Digging Tool", 640, 770, 28, et("Digger", "Manual", "Forged Steel", "2.4 kg", "115 cm", "6 months guarantee", "Planting", cap="35 cm")),
    ("Grafting Tools Kit (2 in 1)", 520, 625, 30, et("Grafting Kit", "Manual", "Stainless Steel", "0.45 kg", "Kit", "6 months guarantee", "Maintenance")),
    ("Budding Tape Roll (100 m)", 240, 290, 35, et("Tape", "Manual", "PE Exhalable", "0.2 kg", "100 m", "No warranty", "Planting")),
    ("Tractor Mounted Ridger (2 Row)", 11800, 13400, 5, et("Ridger", "Fuel Powered", "Heavy Steel", "140 kg", "160 cm", "1 year warranty", "Land preparation", ow="160 cm")),
    ("Vegetable Transplanter (Walk)", 6900, 7900, 6, et("Transplanter", "Manual", "Steel + PP", "23 kg", "150 cm", "1 year warranty", "Planting", cap="2 rows", crops=["vegetables", "chilli"])),
    ("Seed Treatment Drum", 850, 1000, 20, et("Drum", "Manual", "HDPE", "3.5 kg", "60 cm", "6 months guarantee", "Planting", cap="25 kg")),
    ("Marker Wheels Kit (Planter)", 430, 515, 22, et("Marker", "Manual", "Steel", "1.8 kg", "Set", "6 months guarantee", "Planting")),
    ("Perforated Seed Germination Tray", 380, 460, 45, et("Tray", "Manual", "PP", "0.9 kg", "54 x 28 cm", "No warranty", "Planting")),
]
for _r in _T:
    C["planting-tools"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Soil & Field Tools ----------------------------------------------------
C["soil-field-tools"] = []
_T = [
    ("Round Point Shovel (D - Handle)", 520, 620, 50, et("Shovel", "Manual", "Carbon Steel", "2 kg", "75 cm", "1 year warranty", "Land preparation")),
    ("Square Mouth Spade", 545, 655, 45, et("Spade", "Manual", "Stainless Steel", "2.2 kg", "80 cm", "1 year warranty", "Land preparation", ow="21 cm")),
    ("Digging Fork 4 Prong", 560, 670, 40, et("Fork", "Manual", "Forged Steel", "1.9 kg", "105 cm", "6 months guarantee", "Land preparation")),
    ("Garden Spade (Treaded)", 490, 590, 48, et("Spade", "Manual", "Carbon Steel", "1.8 kg", "90 cm", "6 months guarantee", "Land preparation")),
    ("Fiber Handle Shovel", 460, 550, 55, et("Shovel", "Manual", "Steel + Fiber", "1.7 kg", "95 cm", "6 months guarantee", "Land preparation")),
    ("Soil Sieve / Sifter 40 cm", 580, 690, 32, et("Sieve", "Manual", "Galvanized + Wood", "2.5 kg", "40 cm", "6 months guarantee", "Land preparation")),
    ("Compost Turner Fork", 620, 745, 30, et("Fork", "Manual", "Carbon Steel", "2.8 kg", "110 cm", "1 year warranty", "Maintenance")),
    ("Mattock / Pickaxe (Heavy)", 780, 920, 35, et("Pickaxe", "Manual", "Forged Steel", "3.6 kg", "105 cm", "1 year warranty", "Land preparation")),
    ("Clay Cutter Blade Tool", 340, 410, 30, et("Cutter", "Manual", "Carbon Steel", "1.2 kg", "65 cm", "6 months guarantee", "Land preparation")),
    ("Field Shovel (Power Grip)", 500, 600, 40, et("Shovel", "Manual", "Carbon Steel", "2 kg", "90 cm", "6 months guarantee", "Land preparation")),
    ("Soil Thermometer (Long Stem)", 390, 470, 25, et("Probe", "Manual", "Stainless Steel", "0.3 kg", "50 cm", "No warranty", "Maintenance")),
    ("Soil pH Tester (3 in 1)", 480, 575, 28, et("Tester", "Battery", "ABS + Probe", "0.25 kg", "30 cm", "6 months guarantee", "Maintenance")),
    ("Soil Moisture Meter", 330, 400, 45, et("Tester", "Manual", "ABS + Probe", "0.2 kg", "28 cm", "No warranty", "Irrigation")),
    ("Earth Clod Crusher", 720, 860, 22, et("Crusher", "Manual", "Cast Iron", "4.5 kg", "70 cm", "6 months guarantee", "Land preparation")),
    ("Soil Compactor (Hand Tamp)", 450, 540, 26, et("Compactor", "Manual", "Cast Iron", "3.4 kg", "100 cm", "6 months guarantee", "Land preparation")),
    ("Transplanting Hoe (Wide)", 520, 625, 34, et("Hoe", "Manual", "Carbon Steel", "1.5 kg", "90 cm", "6 months guarantee", "Weeding", ow="17 cm")),
    ("Grub Hoe / Wing Hoe", 560, 670, 30, et("Hoe", "Manual", "Forged Steel", "1.9 kg", "100 cm", "6 months guarantee", "Weeding", ow="15 cm")),
    ("Carbon Steel Spade 12\"", 610, 735, 28, et("Spade", "Manual", "Carbon Steel", "2.3 kg", "100 cm", "1 year warranty", "Land preparation", ow="30 cm")),
    ("Field Rake (Steel 24 Tine)", 680, 815, 24, et("Rake", "Manual", "Spring Steel", "2.6 kg", "120 cm", "6 months guarantee", "Land preparation", ow="45 cm")),
    ("Soil Bag Spreader (Wheel)", 990, 1180, 18, et("Spreader", "Manual", "Steel + PP", "5.5 kg", "95 cm", "1 year warranty", "Land preparation", cap="15 kg")),
    ("Hand Auger Soil Sampling 35 cm", 425, 510, 26, et("Auger", "Manual", "Carbon Steel", "1.3 kg", "50 cm", "6 months guarantee", "Maintenance", cap="5 cm")),
    ("Leveler / Ladder Scraper", 620, 745, 20, et("Leveler", "Manual", "Steel", "3 kg", "60 cm", "6 months guarantee", "Land preparation", ow="60 cm")),
    ("Bulb Planter Soil Corer", 370, 445, 30, et("Corer", "Manual", "Stainless Steel", "0.6 kg", "34 cm", "No warranty", "Planting", cap="8 cm")),
    ("Asbestos Grid Tripod Rack", 850, 1000, 15, et("Rack", "Manual", "Steel", "4 kg", "120 cm", "6 months guarantee", "Storage")),
    ("Jungle Cleaver (Heavy)", 690, 825, 25, et("Cleaver", "Manual", "Forged Steel", "1.4 kg", "45 cm", "1 year warranty", "Maintenance")),
    ("Weed Cutter Sickle (Surti)", 310, 375, 40, et("Sickle", "Manual", "High Carbon Steel", "0.5 kg", "36 cm", "6 months guarantee", "Weeding", ow="13 cm")),
    ("Double Sided Hoe Blade", 430, 515, 30, et("Hoe", "Manual", "Carbon Steel", "0.95 kg", "75 cm", "6 months guarantee", "Weeding", ow="14 cm")),
    ("Cultivator Spikes Pack (5 pc)", 350, 420, 25, et("Cultivator", "Manual", "Spring Steel", "1.6 kg", "Set", "6 months guarantee", "Land preparation")),
]
for _r in _T:
    C["soil-field-tools"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Spraying Equipment ----------------------------------------------------
C["spraying-equipment"] = []
_T = [
    ("Knapsack Sprayer 16L (Manual)", 1450, 1680, 40, et("Knapsack Sprayer", "Manual", "HDPE + Brass", "6.5 kg", "54 x 42 x 18 cm", "1 year warranty", "Spraying", cap="16 L")),
    ("Knapsack Sprayer 20L (High Pressure)", 1850, 2150, 32, et("Knapsack Sprayer", "Manual", "PP + SS", "7.8 kg", "58 x 45 x 20 cm", "1 year warranty", "Spraying", cap="20 L")),
    ("Battery Operated Knapsack Sprayer 16L", 3850, 4400, 25, et("Knapsack Sprayer", "Battery", "PP + ABS", "9.5 kg", "55 x 46 cm", "1 year warranty", "Spraying", cap="16 L")),
    ("Power Sprayer 260 L (Petrol)", 16550, 18500, 8, et("Power Sprayer", "Fuel", "SS Tank + Brass Pump", "48 kg", "120 x 60 x 70 cm", "1 year warranty", "Spraying", cap="260 L")),
    ("Power Sprayer 300 L (Diesel)", 19800, 22000, 6, et("Power Sprayer", "Fuel", "Stainless Steel", "55 kg", "130 x 65 x 75 cm", "1 year warranty", "Spraying", cap="300 L")),
    ("Electric Sprayer 12 L (Rechargeable)", 2250, 2600, 30, et("Sprayer", "Electric", "ABS + HDPE", "5.2 kg", "45 x 38 x 22 cm", "1 year warranty", "Spraying", cap="12 L")),
    ("Foot Operated Sprayer 10L", 890, 1040, 35, et("Sprayer", "Manual", "PP + Brass", "3.8 kg", "62 x 30 cm", "6 months guarantee", "Spraying", cap="10 L")),
    ("Hand Pump Sprayer 2L (Garden)", 240, 290, 60, et("Sprayer", "Manual", "PP", "0.5 kg", "38 cm", "6 months guarantee", "Spraying", cap="2 L")),
    ("Pressure Sprayer 5L", 520, 620, 45, et("Sprayer", "Manual", "HDPE", "1.6 kg", "45 x 20 cm", "6 months guarantee", "Spraying", cap="5 L")),
    ("Pesticide Mixing Bucket 20L", 340, 410, 40, et("Bucket", "Manual", "HDPE", "1 kg", "38 x 30 cm", "No warranty", "Spraying", cap="20 L")),
    ("Nozzle Set (Ceramic + Brass, 10 pc)", 420, 505, 50, et("Nozzle", "Manual", "Ceramic + Brass", "0.5 kg", "Set", "6 months guarantee", "Spraying")),
    ("Spray Gun with Lance (Trigger)", 480, 575, 42, et("Spray Gun", "Manual", "Brass + ABS", "0.7 kg", "60 cm", "6 months guarantee", "Spraying")),
    ("Telescopic Spray Boom (3 m)", 1250, 1460, 18, et("Boom", "Manual", "Aluminum + SS", "4.2 kg", "3 m", "6 months guarantee", "Spraying", ow="300 cm")),
    ("Spray Hose 10 mm (50 m)", 520, 625, 35, et("Hose", "Manual", "EPDM Rubber", "4.5 kg", "50 m", "6 months guarantee", "Spraying")),
    ("Sulfur Dusting Machine", 1680, 1950, 14, et("Duster", "Manual", "PP + Steel", "3.6 kg", "70 cm", "1 year warranty", "Spraying", cap="8 L")),
    ("Flaming Weeder (Safety)", 890, 1050, 16, et("Weeder", "Fuel", "Steel + Brass", "2.8 kg", "80 cm", "6 months guarantee", "Weeding")),
    ("Pressure Gauge Set for Sprayer", 380, 455, 30, et("Gauge", "Manual", "Brass + Steel", "0.4 kg", "Set", "6 months guarantee", "Spraying")),
    ("Anti-Drift Spray Shield", 560, 670, 24, et("Shield", "Manual", "PVC + Steel", "1.2 kg", "40 cm", "6 months guarantee", "Spraying")),
    ("Stirring Stick SS (Chemical)", 250, 300, 40, et("Stirrer", "Manual", "Stainless Steel", "0.4 kg", "60 cm", "No warranty", "Spraying")),
    ("Measuring Cup Set (Chemical)", 310, 375, 35, et("Measure Cup", "Manual", "PP", "0.3 kg", "Set of 3", "No warranty", "Spraying")),
    ("Funnel Set for Spray Filling", 190, 230, 45, et("Funnel", "Manual", "HDPE", "0.2 kg", "Set", "No warranty", "Spraying")),
    ("Universal Coupler Sprayer Kit", 450, 540, 28, et("Coupler", "Manual", "Brass", "0.6 kg", "Kit", "6 months guarantee", "Spraying")),
    ("Sprayer Shoulder Strap (Comfort)", 220, 265, 50, et("Strap", "Manual", "Nylon + Foam", "0.25 kg", "Adjustable", "No warranty", "Spraying")),
    ("Pesticide PPE Kit (Mask + Goggles)", 690, 820, 26, et("PPE Kit", "Manual", "PP + Rubber", "0.6 kg", "Kit", "No warranty", "Spraying", crops=["general"])),
    ("Trolley Wheel Power Sprayer Frame", 1390, 1600, 15, et("Trolley", "Manual", "Steel", "7 kg", "90 cm", "1 year warranty", "Spraying", cap="50 L")),
    ("Mist Blower (Battery)", 4450, 5100, 10, et("Mist Blower", "Battery", "ABS + Steel", "10.5 kg", "70 x 45 cm", "1 year warranty", "Spraying", cap="20 L")),
    ("Banana Gun Sprayer (Knapsack 20L)", 4900, 5600, 12, et("Banana Gun", "Battery", "PP + Brass", "11 kg", "60 cm", "1 year warranty", "Spraying", cap="20 L")),
    ("Spill Proof Chemical Carrier", 620, 745, 20, et("Carrier", "Manual", "HDPE", "3.2 kg", "60 x 40 cm", "6 months guarantee", "Spraying", cap="25 L")),
]
for _r in _T:
    C["spraying-equipment"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Safety Equipment ------------------------------------------------------
C["safety-equipment"] = []
_T = [
    ("Tractor Driver Helmet (R)-Approved)", 480, 575, 25, et("Helmet", "Manual", "ABS + Foam", "0.7 kg", "Universal", "1 year warranty", "Safety", crops=["general"])),
    ("Farm Work Gloves (Nitrile Grip)", 290, 350, 55, et("Gloves", "Manual", "Nitrile Coated", "0.2 kg", "Pair", "No warranty", "Safety")),
    ("Cut Resistant Gloves (Level 5)", 420, 505, 40, et("Gloves", "Manual", "Kevlar Blend", "0.25 kg", "Pair", "No warranty", "Safety")),
    ("Safety Goggles (Anti Fog)", 260, 315, 45, et("Goggles", "Manual", "PC Lens", "0.12 kg", "Universal", "No warranty", "Safety")),
    ("Full Face Chemical Mask", 550, 660, 30, et("Mask", "Manual", "Silicone + PP", "0.4 kg", "Universal", "6 months guarantee", "Safety")),
    ("N95 Farm Dust Mask (Pack 20)", 640, 770, 50, et("Mask", "Manual", "PP Non-Woven", "0.5 kg", "pack of 20", "No warranty", "Safety")),
    ("Spray Suit / Coverall (Chemical)", 990, 1180, 22, et("Coverall", "Manual", "PE-Coated", "1.2 kg", "M - XXL", "No warranty", "Safety")),
    ("Reflective High Visibility Vest", 280, 335, 40, et("Vest", "Manual", "Polyester + Reflective", "0.2 kg", "Universal", "No warranty", "Safety")),
    ("Knee Pads (Outdoor, Set of 2)", 360, 430, 35, et("Knee Pads", "Manual", "EVA + Nylon", "0.5 kg", "Set", "No warranty", "Safety")),
    ("Steel Toe Farm Boots", 1150, 1350, 25, et("Boots", "Manual", "PU + Steel Toe", "1.4 kg", "8 - 11 UK", "6 months guarantee", "Safety")),
    ("Raincoat Farmers 2 Piece", 590, 710, 20, et("Rainwear", "Manual", "PVC Coated", "0.9 kg", "M - XXL", "No warranty", "Safety")),
    ("First Aid Kit (Farm 30 pcs)", 720, 860, 30, et("First Aid", "Manual", "ABS Case", "1.3 kg", "Kit", "No warranty", "Safety")),
    ("Ear Protector (Muff)", 380, 455, 25, et("Ear Protection", "Manual", "ABS + Foam", "0.28 kg", "Universal", "No warranty", "Safety")),
    ("Work Helmet with Chin Strap", 320, 385, 30, et("Helmet", "Manual", "HDPE", "0.45 kg", "Universal", "No warranty", "Safety")),
    ("Sunscreen Worker Hat (Wide Brim)", 310, 375, 30, et("Hat", "Manual", "Polypropylene", "0.3 kg", "Universal", "No warranty", "Safety")),
    ("Sprayer Back Shield Guard", 340, 410, 18, et("Back Shield", "Manual", "PVC", "0.7 kg", "50 cm", "No warranty", "Safety")),
    ("Dust Respirator N90 (Pack 10)", 420, 505, 35, et("Mask", "Manual", "PP Non-Woven", "0.35 kg", "pack of 10", "No warranty", "Safety")),
    ("Gardening Apron (Waterproof)", 260, 315, 25, et("Apron", "Manual", "PVC", "0.4 kg", "Universal", "No warranty", "Safety")),
    ("Rayon Chemical Gloves", 230, 280, 30, et("Gloves", "Manual", "Rubber Coated", "0.2 kg", "Pair", "No warranty", "Safety")),
    ("Fall-Off Handle Lanyard (Tool)", 210, 255, 25, et("Lanyard", "Manual", "Nylon + Carabiner", "0.3 kg", "45 cm", "No warranty", "Safety")),
    ("Head Lamp (Rechargeable)", 390, 470, 30, et("Lamp", "Battery", "ABS + LED", "0.15 kg", "Universal", "6 months guarantee", "Safety")),
    ("Splash Shield Face Guard", 450, 540, 15, et("Face Shield", "Manual", "PC + PP", "0.35 kg", "Universal", "No warranty", "Safety")),
    ("Warning Road Cone (Set of 4)", 830, 980, 12, et("Cone", "Manual", "PVC", "4.5 kg", "60 cm", "No warranty", "Safety")),
    ("Safety Ladder Anchor", 620, 745, 15, et("Anchor", "Manual", "Galvanized Steel", "2 kg", "Set", "6 months guarantee", "Safety")),
    ("Bug Bite Shield Net (Hat)", 250, 300, 25, et("Net", "Manual", "Poly Mesh", "0.2 kg", "Universal", "No warranty", "Safety")),
    ("Heavy Work Belt (Support)", 760, 890, 18, et("Belt", "Manual", "Nylon + Foam", "0.6 kg", "S - XL", "No warranty", "Safety")),
    ("Hand Sanitizer Dispenser Kit (Farm)", 210, 255, 30, et("Sanitizer Kit", "Manual", "PP", "0.4 kg", "Kit", "No warranty", "Safety")),
    ("Emergency Whistle + Flare Set", 240, 290, 20, et("Signal Kit", "Manual", "ABS", "0.2 kg", "Set", "No warranty", "Safety")),
]
for _r in _T:
    C["safety-equipment"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Storage Equipment -----------------------------------------------------
C["storage-equipment"] = []
_T = [
    ("Grain Storage Bag (PP, 50 kg)", 180, 220, 120, et("Storage Bag", "Manual", "Polypropylene", "0.3 kg", "90 x 55 cm", "No warranty", "Storage", cap="50 kg")),
    ("Hermetic Grain Bag (60 kg)", 420, 505, 70, et("Hermetic Bag", "Manual", "Multi-Layer Poly", "0.7 kg", "100 x 60 cm", "6 months guarantee", "Storage", cap="60 kg")),
    ("Fumigation Cover Tarp", 1100, 1280, 25, et("Tarp", "Manual", "Laminated HDPE", "6 kg", "8 x 10 m", "6 months guarantee", "Storage")),
    ("Plastic Grain Bin 500 L (UV)", 6800, 7700, 12, et("Grain Bin", "Manual", "UV Poly", "24 kg", "110 x 120 cm", "1 year warranty", "Storage", cap="500 L")),
    ("Grain Silo Bag 1 Tonne", 14500, 16200, 6, et("Silo Bag", "Manual", "UV Poly", "42 kg", "1 tonne", "1 year warranty", "Storage", cap="1000 kg")),
    ("Seed Storage Rack Metal (4 Ply)", 8200, 9300, 8, et("Rack", "Manual", "Powder Coated Steel", "38 kg", "180 x 60 x 90 cm", "1 year warranty", "Storage")),
    ("Mesh Storage Crate (Stackable)", 590, 710, 40, et("Crate", "Manual", "Steel Wire", "2.1 kg", "60 x 40 x 32 cm", "6 months guarantee", "Storage", cap="20 kg")),
    ("Plastic Harvest Crate 60L", 420, 505, 55, et("Crate", "Manual", "PP", "1.8 kg", "58 x 40 x 30 cm", "No warranty", "Storage", cap="60 L")),
    ("Seed Pouch Sealer Machine (Hand)", 560, 670, 30, et("Sealer", "Electric", "ABS + Steel", "0.5 kg", "20 cm", "6 months guarantee", "Storage")),
    ("Grain Moisture Meter (Digital)", 1450, 1680, 20, et("Meter", "Battery", "ABS + Probes", "0.3 kg", "18 cm", "1 year warranty", "Storage")),
    ("Storage Fumigation Tablets (500 g)", 350, 420, 45, et("Fumigant", "Manual", "Aluminum Phosphide", "0.5 kg", "tin", "No warranty", "Storage")),
    ("Neem Bitter Amrit Pellets (1 kg)", 240, 290, 60, et("Grain Protector", "Manual", "Neem Extract", "1 kg", "pack", "No warranty", "Storage")),
    ("Food Grade Grain Scoop (20L)", 310, 375, 40, et("Scoop", "Manual", "PP Food Grade", "0.6 kg", "38 cm", "No warranty", "Storage", cap="20 L")),
    ("Vermin Proof Shed Lining Cloth", 890, 1040, 15, et("Lining", "Manual", "HDPE Woven", "8 kg", "10 x 20 m", "6 months guarantee", "Storage")),
    ("Sack Lifter / Webbing Hoist", 980, 1150, 18, et("Lifter", "Manual", "Nylon + Steel Hook", "3 kg", "3 m", "1 year warranty", "Storage", cap="120 kg")),
    ("Portable Threshing Shed Tent", 3500, 4000, 10, et("Shed", "Manual", "Laminated HDPE", "18 kg", "6 x 4 m", "6 months guarantee", "Storage")),
    ("Stackable Feed Bin 100 L", 1950, 2250, 22, et("Feed Bin", "Manual", "HD-PE", "8 kg", "60 x 75 cm", "1 year warranty", "Storage", cap="100 L")),
    ("Rat Repellent Bait Box (Set 5)", 480, 575, 35, et("Bait Box", "Manual", "PP", "2 kg", "Set", "No warranty", "Storage")),
    ("Grain Weighing Scale 100 kg", 1850, 2150, 15, et("Scale", "Manual", "Steel + Cast Iron", "9 kg", "60 cm", "1 year warranty", "Storage", cap="100 kg")),
    ("Camphor Storage Block (1 kg)", 260, 315, 50, et("Protector", "Manual", "Camphor", "1 kg", "pack", "No warranty", "Storage")),
    ("Insect Pheromone Trap (Set 10)", 620, 745, 25, et("Trap", "Manual", "PP + Sticky Board", "1.5 kg", "Set", "6 months guarantee", "Storage")),
    ("Grain Bin Aeration Pipe Set", 340, 410, 20, et("Pipe Set", "Manual", "PVC", "2.4 kg", "Set", "6 months guarantee", "Storage")),
    ("Waterproof Storage Drum 50 L", 760, 890, 28, et("Drum", "Manual", "HDPE", "3.5 kg", "60 x 80 cm", "6 months guarantee", "Storage", cap="50 L")),
    ("Farm Lockable Tool Kit Box", 890, 1065, 18, et("Tool Box", "Manual", "Steel", "6.5 kg", "50 x 25 x 22 cm", "6 months guarantee", "Storage")),
    ("Seed Inventory Log Book + Tags", 220, 265, 50, et("Records", "Manual", "Paper", "0.4 kg", "A4", "No warranty", "Storage")),
    ("Collapsible Grain Carton (Set 10)", 520, 625, 30, et("Carton", "Manual", "Corrugated PP", "3 kg", "Set", "No warranty", "Storage")),
    ("Dust Proof Shed Tarp Clips (50)", 260, 315, 40, et("Clips", "Manual", "Galvanized Steel", "1.2 kg", "Set of 50", "No warranty", "Storage")),
    ("Grain Dusting Duster (Hand Crank)", 540, 650, 15, et("Duster", "Manual", "Steel + Wood", "2.4 kg", "55 cm", "6 months guarantee", "Storage")),
]
for _r in _T:
    C["storage-equipment"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Small Farm Machinery --------------------------------------------------
C["small-machinery"] = []
_T = [
    ("Power Tiller 8 HP (Diesel)", 125000, 138000, 3, et("Power Tiller", "Fuel", "Cast Iron Engine", "285 kg", "185 x 80 x 115 cm", "1 year warranty", "Land preparation", cap="8 HP")),
    ("Petrol Engine Cultivator 5 HP", 42500, 47500, 4, et("Tiller", "Fuel", "Aluminum + Steel", "78 kg", "130 x 60 cm", "1 year warranty", "Land preparation", cap="5 HP")),
    ("Manual Rice Transplanter (Battery)", 34000, 38000, 5, et("Transplanter", "Battery", "Aluminum + ABS", "42 kg", "180 cm", "1 year warranty", "Planting", cap="2 rows", crops=["paddy"])),
    ("Walk Behind Brush Cutter 1.3 HP", 11500, 12900, 12, et("Brush Cutter", "Fuel", "Aluminum Shaft", "9 kg", "180 cm", "1 year warranty", "Maintenance", cap="1.3 HP")),
    ("Battery Brush Cutter 40V", 9800, 11200, 14, et("Brush Cutter", "Battery", "ABS + Steel", "6.5 kg", "170 cm", "1 year warranty", "Maintenance", cap="40 V")),
    ("Power Weeder 3 HP (Engine)", 15800, 17800, 8, et("Power Weeder", "Fuel", "Cast Iron", "35 kg", "120 x 55 cm", "1 year warranty", "Weeding", ow="50 cm")),
    ("Mini Combine Harvester (Rice)", 485000, 525000, 2, et("Harvester", "Fuel", "Heavy Steel", "1800 kg", "380 cm", "1 year warranty", "Harvesting", crops=["paddy", "wheat"])),
    ("Thresher Machine 3 HP (Engine)", 68000, 76000, 3, et("Thresher", "Fuel", "Cast Iron + Steel", "210 kg", "170 x 140 cm", "1 year warranty", "Harvesting", cap="500 kg/h", crops=["wheat", "paddy"])),
    ("Chaff Cutter Power 2 HP", 24500, 27500, 4, et("Chaff Cutter", "Electric", "Cast Iron", "120 kg", "140 x 90 cm", "1 year warranty", "Maintenance", cap="500 kg/h")),
    ("Grain Cleaner / Gravity Separator", 38500, 43000, 3, et("Cleaner", "Electric", "Steel", "95 kg", "150 x 90 cm", "1 year warranty", "Storage", cap="800 kg/h")),
    ("Sugarcane Crusher (Mini, 5 HP)", 52000, 58000, 3, et("Crusher", "Electric", "Cast Iron Rollers", "180 kg", "160 x 90 x 120 cm", "1 year warranty", "Maintenance", cap="250 kg/h")),
    ("Oil Engine 5 HP (Water Pump Set)", 18500, 20800, 5, et("Engine", "Fuel", "Cast Iron Block", "95 kg", "70 x 60 x 70 cm", "1 year warranty", "Irrigation", cap="5 HP")),
    ("Diesel Engine 8 HP", 29800, 33000, 3, et("Engine", "Fuel", "Cast Iron Block", "135 kg", "80 x 65 x 75 cm", "1 year warranty", "Irrigation", cap="8 HP")),
    ("Electric Motor 2 HP (Dual)", 7200, 8200, 10, et("Motor", "Electric", "Cast Iron + Copper", "22 kg", "38 x 30 x 32 cm", "1 year warranty", "Irrigation", cap="2 HP")),
    ("Solar Fencing Energizer (12V)", 2450, 2850, 20, et("Energizer", "Solar", "ABS + PCB", "3.5 kg", "30 x 20 x 15 cm", "1 year warranty", "Safety", cap="1.5 J")),
    ("Goat / Cattle Feed Mixer (Hand)", 3800, 4300, 6, et("Mixer", "Manual", "Steel", "45 kg", "110 x 60 cm", "6 months guarantee", "Maintenance", cap="50 kg")),
    ("Bag Closer Sewing Machine (Electric)", 8900, 10000, 5, et("Bag Closer", "Electric", "Steel", "5 kg", "45 x 20 cm", "1 year warranty", "Storage", cap="12 m/min")),
    ("Rope Making Machine (Manual)", 2900, 3300, 8, et("Rope Machine", "Manual", "Cast Iron", "18 kg", "70 x 60 cm", "6 months guarantee", "Maintenance")),
    ("Animal Feed Pelletizer (Mini)", 16800, 18900, 3, et("Pelletizer", "Electric", "Steel", "85 kg", "90 x 60 x 100 cm", "1 year warranty", "Maintenance", cap="120 kg/h")),
    ("Maize Sheller Machine (Power)", 6800, 7800, 6, et("Sheller", "Electric", "Cast Iron + Steel", "30 kg", "80 x 70 x 90 cm", "1 year warranty", "Harvesting", cap="300 kg/h", crops=["maize"])),
    ("Groundnut Decorticator (Power)", 12400, 14100, 4, et("Decorticator", "Electric", "Cast Iron", "70 kg", "100 x 80 x 110 cm", "1 year warranty", "Harvesting", cap="250 kg/h", crops=["groundnut"])),
    ("Sugarcane Set Cutter Machine", 8900, 10000, 4, et("Set Cutter", "Electric", "Steel Blades", "48 kg", "105 x 70 cm", "1 year warranty", "Planting", cap="600 sets/h")),
    ("Fencing Post Driver (Manual)", 2150, 2450, 15, et("Post Driver", "Manual", "Carbon Steel", "9 kg", "110 cm", "6 months guarantee", "Safety")),
    ("Spray Pump Cart (Engine Mounted)", 14200, 16000, 6, et("Spray Cart", "Fuel", "Steel + SS Tank", "65 kg", "150 x 80 cm", "1 year warranty", "Spraying", cap="200 L")),
    ("Seed Treatment Machine (Tetra)", 5600, 6400, 5, et("Seed Treater", "Electric", "Steel", "38 kg", "90 x 70 x 100 cm", "1 year warranty", "Planting", cap="150 kg/h")),
    ("Greenhouse Vent Fan Motor", 3800, 4300, 10, et("Vent Fan", "Electric", "Aluminum + ABS", "9 kg", "60 cm", "1 year warranty", "Maintenance")),
    ("Mini Chaff / Crop Chopper", 7900, 8900, 5, et("Chopper", "Electric", "Steel", "40 kg", "95 x 65 cm", "1 year warranty", "Maintenance", cap="300 kg/h")),
    ("Egg Incubator (96 Eggs)", 6800, 7800, 9, et("Incubator", "Electric", "HDPE + Plastic", "16 kg", "70 x 50 x 55 cm", "1 year warranty", "Maintenance", cap="96 eggs")),
]
for _r in _T:
    C["small-machinery"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Other Equipment -------------------------------------------------------
C["other-equipment"] = []
_T = [
    ("Digital Farm Weighing Scale 300 kg", 4200, 4800, 12, et("Scale", "Battery", "Steel Platform", "12 kg", "50 x 50 cm", "1 year warranty", "Storage", cap="300 kg")),
    ("Hanging Scale 50 kg (Spring)", 480, 575, 30, et("Scale", "Manual", "Steel + Zinc", "0.9 kg", "40 cm", "6 months guarantee", "Storage", cap="50 kg")),
    ("Digital Vernier Caliper", 520, 625, 25, et("Gauge", "Battery", "Stainless Steel", "0.3 kg", "15 cm", "6 months guarantee", "Maintenance")),
    ("Milling Machine Bit Set (Agri)", 990, 1180, 14, et("Bit Set", "Manual", "HSS", "0.8 kg", "Set", "6 months guarantee", "Maintenance")),
    ("Fencing Wire Roll (Barbed 50 kg)", 3800, 4300, 8, et("Fencing", "Manual", "Galvanized Steel", "50 kg", "roll", "No warranty", "Safety")),
    ("GI Fence Poles (Set of 10)", 1450, 1680, 12, et("Fencing", "Manual", "Galvanized Steel", "24 kg", "400 cm", "6 months guarantee", "Safety")),
    ("Rope Winder (Manual)", 780, 920, 15, et("Winder", "Manual", "Cast Iron", "6 kg", "55 cm", "6 months guarantee", "Maintenance")),
    ("Water Level Controller (Float)", 890, 1040, 20, et("Controller", "Electric", "ABS + SS", "1.1 kg", "Set", "1 year warranty", "Irrigation")),
    ("Digital TDS / EC Meter", 780, 920, 18, et("Meter", "Battery", "ABS + Probes", "0.2 kg", "15 cm", "6 months guarantee", "Irrigation")),
    ("Solar Fence Panel 50W", 3200, 3650, 10, et("Solar Panel", "Solar", "Monocrystalline", "4.5 kg", "67 x 55 cm", "1 year warranty", "Safety", cap="50 W")),
    ("Engine Oil 5L (Agri Grade)", 1750, 2000, 40, et("Lubricant", "Manual", "Mineral Oil", "4.6 kg", "5 L", "No warranty", "Maintenance")),
    ("Grease Gun Set (Heavy)", 690, 825, 18, et("Grease Gun", "Manual", "Steel Body", "1.4 kg", "Set", "6 months guarantee", "Maintenance")),
    ("Air Filter Kit for Tractor", 920, 1080, 14, et("Filter Kit", "Manual", "Paper + Urethane", "1.5 kg", "Kit", "6 months guarantee", "Maintenance")),
    ("Tractor Battery 12V 135Ah", 8900, 10000, 6, et("Battery", "Battery", "Lead Acid", "32 kg", "52 x 25 x 22 cm", "1 year warranty", "Maintenance", cap="135 Ah")),
    ("Battery Charger 12V (Smart)", 2450, 2800, 10, et("Charger", "Electric", "ABS + Copper", "3.2 kg", "25 x 18 x 12 cm", "1 year warranty", "Maintenance")),
    ("Headlight Kit for Tractor", 950, 1100, 12, et("Lighting", "Electric", "Aluminum + LED", "1.8 kg", "Set of 2", "6 months guarantee", "Safety")),
    ("Horn + Indicator Kit (Agri)", 560, 670, 15, et("Electrical Kit", "Electric", "ABS + Wiring", "1.2 kg", "Kit", "6 months guarantee", "Safety")),
    ("Hydraulic Jack 10 Ton", 2150, 2450, 10, et("Jack", "Manual", "Cast Iron + Steel", "28 kg", "45 x 30 x 20 cm", "1 year warranty", "Maintenance", cap="10 T")),
    ("Tow Rope / Towing Strap 8 m", 780, 920, 16, et("Tow Strap", "Manual", "Polyester Webbing", "3 kg", "8 m", "6 months guarantee", "Transport", cap="5 T")),
    ("Wheel Chocks Set (Tractor)", 480, 575, 12, et("Chock", "Manual", "Rubber + Steel", "4 kg", "Set", "No warranty", "Safety")),
    ("Canopy / Shade Net 90% (50 m)", 2800, 3200, 8, et("Shade Net", "Manual", "HDPE", "12 kg", "50 m roll", "6 months guarantee", "Maintenance")),
    ("Mulch Roll 1 m x 200 m", 1850, 2150, 10, et("Mulch Film", "Manual", "LDPE", "14 kg", "200 m", "No warranty", "Irrigation", crops=["vegetables", "chilli"])),
    ("Dripline End Caps & Fittings Kit", 320, 385, 30, et("Fittings", "Manual", "PP", "0.6 kg", "Kit", "No warranty", "Irrigation")),
    ("Grafting Heat Pad", 680, 815, 12, et("Heat Pad", "Electric", "Silicone", "0.9 kg", "52 x 28 cm", "6 months guarantee", "Maintenance")),
    ("Laboratory Soil Test Mini Kit", 1450, 1680, 15, et("Test Kit", "Manual", "PP Reagents", "1.6 kg", "Kit", "6 months guarantee", "Maintenance")),
    ("Field Notebook Kit (Year)", 310, 375, 30, et("Records", "Manual", "Paper", "0.5 kg", "A5 + Pen", "No warranty", "Maintenance")),
    ("Bamboo Process Kit (Splitter)", 1150, 1350, 8, et("Splitter", "Manual", "Forged Steel", "7 kg", "75 cm", "6 months guarantee", "Maintenance")),
    ("Farm Umbrella Canopy Stand", 890, 1050, 14, et("Stand", "Manual", "Steel + UV Fabric", "3.6 kg", "230 cm", "6 months guarantee", "Safety")),
]
for _r in _T:
    C["other-equipment"].append((_r[0], _r[1], _r[2], _r[3], _r[4]))

# --- Brand rotation + defaults ---------------------------------------------
BRANDS = {
    "hand-tools": ["KisanPro", "AgroKraft", "HarvestPlus", "ToolMaster"],
    "equipment": ["AgroMach", "KisanYantra", "FarmTech", "GreenField"],
    "irrigation-equipment": ["AquaFlow", "DripTech", "GreenDrip", "HydroKisan"],
    "harvesting-tools": ["HarvestPlus", "KisanPro", "AgroKraft", "SickleMax"],
    "planting-tools": ["SoilSpring", "PlantRight", "AgroKraft", "KisanPro"],
    "soil-field-tools": ["FieldMaster", "AgroKraft", "KisanPro", "DugDeep"],
    "spraying-equipment": ["SprayWell", "AgroTech", "CropJet", "KisanPro"],
    "safety-equipment": ["SafeFarm", "BharatGuard", "KisanPro", "FarmShield"],
    "storage-equipment": ["StoreGrain", "HarvestLock", "KisanPro", "AgroBin"],
    "small-machinery": ["KisanYantra", "TractorTech", "AgroMach", "FarmForce"],
    "other-equipment": ["AgroLab", "KisanPro", "FieldTools", "FarmBest"],
}

DESC_TEMPLATE = (
    "{name} - reliable {category} for everyday farm work. "
    "Engineered for durability, easy to operate and backed by {seller}. "
    "Ideal for {use} on your farm."
)


def _ensure_category(db, slug, name, icon):
    cat = db.query(ProductCategory).filter(ProductCategory.slug == slug).first()
    if cat:
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


def _upsert_product(db, category, seller, row, index):
    # Existing products are upgraded in place (matched by name + category).
    existing = db.query(Product).filter(Product.category_id == category.id, Product.name == row["name"]).first()

    meta = row["meta"]
    data = {
        "category_id": category.id,
        "name": row["name"],
        "description": DESC_TEMPLATE.format(
            name=row["name"], category=category.name.lower(), seller=seller.shop_name, use=meta["suitable_use"].lower()
        ),
        "price": row["price"],
        "original_price": row["mrp"],
        "unit": "unit",
        "stock_quantity": row["stock"],
        "min_order_quantity": 1,
        "image_url": IMG_BASE.format(img=EQUIP_IMG[category.slug][index % len(EQUIP_IMG[category.slug])]),
        "images": [
            IMG_BASE.format(img=EQUIP_IMG[category.slug][(index + 1) % len(EQUIP_IMG[category.slug])]),
            IMG_BASE.format(img=EQUIP_IMG[category.slug][(index + 2) % len(EQUIP_IMG[category.slug])]),
        ],
        "brand": row["brand"],
        "rating": round(3.8 + (index % 12) * 0.1, 1),
        "total_reviews": (index * 7) % 90 + 3,
        "is_active": True,
        "seller_id": seller.id,
        "tags": {
            "verified": seller.is_verified,
            "equipment_type": meta["equipment_type"],
            "power_source": meta["power_source"],
            "material": meta["material"],
            "weight": meta["weight"],
            "dimensions": meta["dimensions"],
            "warranty": meta["warranty"],
            "suitable_use": meta["suitable_use"],
            "operating_width": meta["operating_width"],
            "capacity": meta["capacity"],
        },
    }

    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        product = existing
    else:
        product = Product(product_id=f"EQP-{index:06d}", **data)
        db.add(product)
    db.flush()

    # Equipment metadata (upsert)
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
    db.flush()

    # Crop mappings (upsert)
    db.query(ProductCrop).filter(ProductCrop.product_id == product.id).delete()
    for crop in meta["crops"]:
        db.add(ProductCrop(product_id=product.id, crop_name=crop))

    return product


def _next_product_index(db, total):
    rows = [
        int(r[0].split("-")[-1])
        for r in db.query(Product.product_id).filter(Product.product_id.like("EQP-%")).all()
        if r[0] and r[0].split("-")[-1].isdigit()
    ]
    return max(rows) + 1 if rows else 1


def _migrate_legacy_equipment(db, category_by_slug):
    """Move previously-seeded equipment products into the new taxonomy.

    Products that carry ``equipment_metadata`` but still live in the old
    shared slug (planting/irrigation/sprayers/harvesting/soil-field/safety/
    storage) are re-homed into the matching new equipment category. Non-
    equipment products in those categories are left untouched.
    """
    moved = 0
    legacy_cats = db.query(ProductCategory).filter(
        ProductCategory.slug.in_(list(LEGACY_SLUG_MAP))
    ).all()
    for cat in legacy_cats:
        new_slug = LEGACY_SLUG_MAP[cat.slug]
        new_cat = category_by_slug.get(new_slug)
        if not new_cat:
            continue
        ids = [
            r[0]
            for r in db.query(Product.id)
            .join(EquipmentMetadata, EquipmentMetadata.product_id == Product.id)
            .filter(Product.category_id == cat.id)
            .all()
        ]
        if not ids:
            continue
        moved += db.query(Product).filter(Product.id.in_(ids)).update(
            {Product.category_id: new_cat.id}, synchronize_session=False
        )
    return moved


def seed(db: Session):
    created = 0
    owner = db.query(User).filter(User.is_demo == True).first() or db.query(User).first()  # noqa: E712
    if owner is None:
        raise RuntimeError("No user available to own equipment sellers; create a user first.")

    sellers = [
        _ensure_seller(db, owner, shop, loc, ver, rat)
        for shop, loc, ver, rat in SELLERS
    ]
    db.flush()

    category_by_slug = {}
    for slug, name, icon in CATEGORIES:
        category_by_slug[slug] = _ensure_category(db, slug, name, icon)
    db.flush()

    migrated = _migrate_legacy_equipment(db, category_by_slug)
    db.flush()

    total_planned = sum(len(C[slug]) for slug, _n, _i in CATEGORIES)
    index = _next_product_index(db, total_planned)

    used = 0
    for slug, name, icon in CATEGORIES:
        category = category_by_slug[slug]
        for row in C.get(slug, []):
            seller = sellers[used % len(sellers)]
            brand = BRANDS[slug][used % len(BRANDS[slug])]
            name_, price, mrp, stock, meta = row
            product = _upsert_product(
                db, category, seller,
                {"name": name_, "brand": brand, "price": price, "mrp": mrp, "stock": stock, "meta": meta},
                index=index,
            )
            used += 1
            index += 1
            created += 1

    db.commit()

    totals = {}
    for slug, _n, _i in CATEGORIES:
        cat = db.query(ProductCategory).filter(ProductCategory.slug == slug).first()
        totals[slug] = (
            db.query(Product).filter(Product.category_id == cat.id, Product.is_active == True).count()  # noqa: E712
            if cat
            else 0
        )
    return {"products": created, "migrated": migrated, "categories": len(CATEGORIES), "per_category": totals}


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = seed(db)
    finally:
        db.close()
    print(f"Tools & Equipment catalogue ready: {result['products']} products in {result['categories']} categories.")
    if result["migrated"]:
        print(f"  Migrated {result['migrated']} legacy equipment products into the new taxonomy.")
    for slug, count in result["per_category"].items():
        print(f"  {slug:>22}: {count}")


if __name__ == "__main__":
    main()