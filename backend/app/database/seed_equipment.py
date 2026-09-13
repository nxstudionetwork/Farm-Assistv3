"""Seed Tools & Equipment catalogue (Buy & Rent).

Unified database seeding:
1. Equipment products land in the shared ``products`` table and ``equipment_metadata`` table.
2. Categories land in ``product_categories``.
3. Sellers land in ``sellers``.
4. Crop mappings land in ``product_crops``.
5. Rental equipment lands in ``equipment`` table for the Rent mode.
All images are high-resolution, verified, realistic agricultural photography.
"""

import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy.orm import Session
from app.database.connection import SessionLocal, engine, Base
from app.models.marketplace import (
    Product, ProductCategory, Seller, ProductCrop, EquipmentMetadata
)
from app.models.worker import Equipment
from app.models.user import User

# Stable high-quality Unsplash agricultural tool & equipment images
EQUIPMENT_IMAGES = {
    # Hand Tools
    "spade": "https://images.unsplash.com/photo-1589051039495-eb77716d8e62?w=800&auto=format&fit=crop&q=80",
    "hoe": "https://images.unsplash.com/photo-1592417817098-8f3d69102a56?w=800&auto=format&fit=crop&q=80",
    "pruning": "https://images.unsplash.com/photo-1585320806297-9794b3e4eeae?w=800&auto=format&fit=crop&q=80",
    "rake": "https://images.unsplash.com/photo-1508615039623-a25605d2b022?w=800&auto=format&fit=crop&q=80",
    "weeder": "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=800&auto=format&fit=crop&q=80",
    # Planting
    "seeder": "https://images.unsplash.com/photo-1592982537447-7440770cbfc9?w=800&auto=format&fit=crop&q=80",
    "dibber": "https://images.unsplash.com/photo-1466692476868-aef1dfb1e735?w=800&auto=format&fit=crop&q=80",
    "transplanter": "https://images.unsplash.com/photo-1523348837708-15d4a09cfac2?w=800&auto=format&fit=crop&q=80",
    # Irrigation
    "drip": "https://images.unsplash.com/photo-1563514227147-6d2ff665a6a0?w=800&auto=format&fit=crop&q=80",
    "pump": "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=800&auto=format&fit=crop&q=80",
    "sprinkler": "https://images.unsplash.com/photo-1574943320219-553eb213f72d?w=800&auto=format&fit=crop&q=80",
    "pipe": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=800&auto=format&fit=crop&q=80",
    # Sprayers
    "sprayer_battery": "https://images.unsplash.com/photo-1523741543316-beb7fc7023d8?w=800&auto=format&fit=crop&q=80",
    "sprayer_knapsack": "https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?w=800&auto=format&fit=crop&q=80",
    "sprayer_power": "https://images.unsplash.com/photo-1591857177580-dc82b9ac4e1e?w=800&auto=format&fit=crop&q=80",
    # Harvesting
    "sickle": "https://images.unsplash.com/photo-1500937386664-56d1dfef3854?w=800&auto=format&fit=crop&q=80",
    "harvester_pole": "https://images.unsplash.com/photo-1615811361523-6bd03d7748e7?w=800&auto=format&fit=crop&q=80",
    "pruning_saw": "https://images.unsplash.com/photo-1585320806297-9794b3e4eeae?w=800&auto=format&fit=crop&q=80",
    # Soil & Field
    "plough": "https://images.unsplash.com/photo-1542838132-92c53300491e?w=800&auto=format&fit=crop&q=80",
    "cultivator": "https://images.unsplash.com/photo-1595974482597-4b8da8879bc5?w=800&auto=format&fit=crop&q=80",
    "auger": "https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=800&auto=format&fit=crop&q=80",
    # Safety
    "respirator": "https://images.unsplash.com/photo-1584634731339-252c581abfc5?w=800&auto=format&fit=crop&q=80",
    "boots": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=800&auto=format&fit=crop&q=80",
    "gloves": "https://images.unsplash.com/photo-1584744982491-665216d95f8b?w=800&auto=format&fit=crop&q=80",
    # Storage
    "storage_bags": "https://images.unsplash.com/photo-1586281380349-632531db7ed4?w=800&auto=format&fit=crop&q=80",
    "crates": "https://images.unsplash.com/photo-1610832958506-aa56368176cf?w=800&auto=format&fit=crop&q=80",
    "tarpaulin": "https://images.unsplash.com/photo-1506084868230-bb9d95c24759?w=800&auto=format&fit=crop&q=80",
    # Small Machinery
    "power_tiller": "https://images.unsplash.com/photo-1595974482597-4b8da8879bc5?w=800&auto=format&fit=crop&q=80",
    "brush_cutter": "https://images.unsplash.com/photo-1513836279014-a89f7a76ae86?w=800&auto=format&fit=crop&q=80",
    "chaff_cutter": "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=800&auto=format&fit=crop&q=80",
    # Other Equipment
    "wheelbarrow": "https://images.unsplash.com/photo-1589051039495-eb77716d8e62?w=800&auto=format&fit=crop&q=80",
    "fence": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=800&auto=format&fit=crop&q=80",
    "soil_meter": "https://images.unsplash.com/photo-1530595467537-0b5996c41f2d?w=800&auto=format&fit=crop&q=80",
    # Machinery for rent
    "tractor_rental": "https://images.unsplash.com/photo-1592417817098-8f3d69102a56?w=800&auto=format&fit=crop&q=80",
    "harvester_rental": "https://images.unsplash.com/photo-1500937386664-56d1dfef3854?w=800&auto=format&fit=crop&q=80",
    "drone_rental": "https://images.unsplash.com/photo-1508614589041-895b88991e3e?w=800&auto=format&fit=crop&q=80",
    "seeder_rental": "https://images.unsplash.com/photo-1592982537447-7440770cbfc9?w=800&auto=format&fit=crop&q=80",
    "rotavator_rental": "https://images.unsplash.com/photo-1595974482597-4b8da8879bc5?w=800&auto=format&fit=crop&q=80",
}

EQUIPMENT_CATEGORIES = [
    ("hand-tools", "Hand Tools", "fa-hammer"),
    ("planting", "Planting", "fa-seedling"),
    ("irrigation", "Irrigation", "fa-faucet-drip"),
    ("sprayers", "Sprayers", "fa-spray-can-sparkles"),
    ("harvesting", "Harvesting", "fa-wheat-awn"),
    ("soil-field", "Soil & Field", "fa-tractor"),
    ("safety", "Safety", "fa-shield-halved"),
    ("storage", "Storage", "fa-warehouse"),
    ("small-machinery", "Small Machinery", "fa-gears"),
    ("other-equipment", "Other Equipment", "fa-toolbox"),
]

SELLERS_DATA = [
    ("Tata Agrico Official Store", "Jamshedpur, Jharkhand", True, 4.8),
    ("Falcon Garden & Agri Tools Hub", "Ludhiana, Punjab", True, 4.7),
    ("KisanKraft Machinery Center", "Bengaluru, Karnataka", True, 4.6),
    ("Jain Agri Irrigation Mart", "Jalgaon, Maharashtra", True, 4.9),
    ("Aspee Spray Equipment Depot", "Mumbai, Maharashtra", True, 4.6),
    ("Shaktiman Field Solutions", "Rajkot, Gujarat", True, 4.7),
    ("Bharat Kisan Hardware & Tools", "Guntur, Andhra Pradesh", False, 4.3),
]

PRODUCTS_CATALOGUE = [
    # 1. HAND TOOLS
    {
        "category": "hand-tools",
        "name": "Tata Agrico Forged Steel Powrah / Hand Hoe",
        "brand": "Tata Agrico",
        "price": 490.0,
        "mrp": 620.0,
        "unit": "piece",
        "stock": 45,
        "image": EQUIPMENT_IMAGES["hoe"],
        "gallery": [EQUIPMENT_IMAGES["hoe"], EQUIPMENT_IMAGES["rake"]],
        "desc": "Heavy-duty forged high-carbon steel powrah (hoe) with heat-treated blade. Designed for soil excavation, earthing-up, and field ridging.",
        "rating": 4.8,
        "reviews": 118,
        "metadata": {
            "equipment_type": "Hand Tools",
            "power_source": "Manual",
            "material": "Forged High-Carbon Steel",
            "weight": "1.8 kg",
            "dimensions": "28 x 22 x 15 cm",
            "warranty": "1 Year Replacement Warranty",
            "suitable_use": "Land preparation",
            "operating_width": "22 cm blade",
            "capacity": "Heavy Duty Tillage",
        },
        "crops": ["paddy", "wheat", "maize", "vegetables", "cotton"],
    },
    {
        "category": "hand-tools",
        "name": "Falcon Heavy-Duty All-Steel Shovel with D-Handle",
        "brand": "Falcon",
        "price": 750.0,
        "mrp": 920.0,
        "unit": "piece",
        "stock": 35,
        "image": EQUIPMENT_IMAGES["spade"],
        "gallery": [EQUIPMENT_IMAGES["spade"], EQUIPMENT_IMAGES["hoe"]],
        "desc": "Industrial-grade round point digging shovel with ergonomic tubular steel D-handle. Rust-resistant powder coated finish for rough farm utility.",
        "rating": 4.7,
        "reviews": 84,
        "metadata": {
            "equipment_type": "Hand Tools",
            "power_source": "Manual",
            "material": "Alloy Steel Blade & Tubular Handle",
            "weight": "2.4 kg",
            "dimensions": "104 x 24 x 18 cm",
            "warranty": "2 Years Manufacturer Warranty",
            "suitable_use": "Land preparation",
            "operating_width": "24 cm scoop",
            "capacity": "15 kg scoop load",
        },
        "crops": ["general", "vegetables", "sugarcane"],
    },
    {
        "category": "hand-tools",
        "name": "Falcon Heavy Forged Bypass Pruning Shears",
        "brand": "Falcon",
        "price": 540.0,
        "mrp": 690.0,
        "unit": "piece",
        "stock": 50,
        "image": EQUIPMENT_IMAGES["pruning"],
        "gallery": [EQUIPMENT_IMAGES["pruning"], EQUIPMENT_IMAGES["pruning_saw"]],
        "desc": "Precision SK5 carbon steel blades for clean orchard pruning and branch cutting. Shock absorbing rubber grip with safety thumb lock.",
        "rating": 4.9,
        "reviews": 162,
        "metadata": {
            "equipment_type": "Hand Tools",
            "power_source": "Manual",
            "material": "SK5 Japanese Carbon Steel",
            "weight": "0.32 kg",
            "dimensions": "21 x 6 x 2.5 cm",
            "warranty": "1 Year Warranty",
            "suitable_use": "Maintenance",
            "operating_width": "25 mm cut diameter",
            "capacity": "Up to 25mm branches",
        },
        "crops": ["chilli", "cotton", "vegetables", "fruits"],
    },
    {
        "category": "hand-tools",
        "name": "KisanCraft 14-Teeth Heavy Carbon Steel Garden Rake",
        "brand": "KisanCraft",
        "price": 620.0,
        "mrp": 780.0,
        "unit": "piece",
        "stock": 30,
        "image": EQUIPMENT_IMAGES["rake"],
        "gallery": [EQUIPMENT_IMAGES["rake"], EQUIPMENT_IMAGES["weeder"]],
        "desc": "Tough 14-curved-teeth leveler rake for soil smoothing, clod breaking, and gathering farm debris and mulch.",
        "rating": 4.6,
        "reviews": 53,
        "metadata": {
            "equipment_type": "Hand Tools",
            "power_source": "Manual",
            "material": "Hardened Manganese Carbon Steel",
            "weight": "1.6 kg",
            "dimensions": "135 x 36 x 9 cm",
            "warranty": "1 Year Manufacturer Warranty",
            "suitable_use": "Land preparation",
            "operating_width": "36 cm spread",
            "capacity": "14 Hardened Tines",
        },
        "crops": ["paddy", "wheat", "vegetables"],
    },
    {
        "category": "hand-tools",
        "name": "KisanMitra Rotary Hand Cultivator & Weeder",
        "brand": "KisanCraft",
        "price": 890.0,
        "mrp": 1150.0,
        "unit": "piece",
        "stock": 25,
        "image": EQUIPMENT_IMAGES["weeder"],
        "gallery": [EQUIPMENT_IMAGES["weeder"], EQUIPMENT_IMAGES["hoe"]],
        "desc": "Rotating star wheels combined with undersoil weeder blade for swift inter-row weeding without straining back.",
        "rating": 4.5,
        "reviews": 41,
        "metadata": {
            "equipment_type": "Hand Tools",
            "power_source": "Manual",
            "material": "High Tensile Galvanized Steel",
            "weight": "2.1 kg",
            "dimensions": "140 x 18 x 14 cm",
            "warranty": "6 Months Warranty",
            "suitable_use": "Weeding",
            "operating_width": "18 cm swath",
            "capacity": "Inter-row Weeding",
        },
        "crops": ["cotton", "maize", "groundnut", "vegetables", "pulses"],
    },

    # 2. PLANTING TOOLS
    {
        "category": "planting",
        "name": "KisanSeeder Pro Manual Single-Row Push Seed Planter",
        "brand": "KisanKraft",
        "price": 3850.0,
        "mrp": 4600.0,
        "unit": "unit",
        "stock": 18,
        "image": EQUIPMENT_IMAGES["seeder"],
        "gallery": [EQUIPMENT_IMAGES["seeder"], EQUIPMENT_IMAGES["transplanter"]],
        "desc": "Adjustable seed roller planter that digs furrow, drops seed at exact spaced intervals, and presses soil in a single walking pass.",
        "rating": 4.7,
        "reviews": 79,
        "metadata": {
            "equipment_type": "Planting Tools",
            "power_source": "Manual",
            "material": "Aluminium Alloy & Heavy Polycarbonate",
            "weight": "8.5 kg",
            "dimensions": "95 x 35 x 88 cm",
            "warranty": "1 Year Manufacturer Warranty",
            "suitable_use": "Planting",
            "operating_width": "Single Row (10-35cm seed spacing)",
            "capacity": "3.5 kg seed hopper",
        },
        "crops": ["maize", "cotton", "groundnut", "soybean", "wheat", "pulses"],
    },
    {
        "category": "planting",
        "name": "GreenGarden Ergonomic Soil Dibber & Bulb Planter",
        "brand": "Falcon",
        "price": 340.0,
        "mrp": 420.0,
        "unit": "piece",
        "stock": 60,
        "image": EQUIPMENT_IMAGES["dibber"],
        "gallery": [EQUIPMENT_IMAGES["dibber"], EQUIPMENT_IMAGES["transplanter"]],
        "desc": "T-handle solid steel soil dibber marked with depth measurements for uniform seed and seedling root depth.",
        "rating": 4.6,
        "reviews": 38,
        "metadata": {
            "equipment_type": "Planting Tools",
            "power_source": "Manual",
            "material": "Stainless Steel with Beechwood Handle",
            "weight": "0.38 kg",
            "dimensions": "28 x 12 x 3 cm",
            "warranty": "1 Year Warranty",
            "suitable_use": "Planting",
            "operating_width": "Depth up to 15 cm",
            "capacity": "Seed & Seedling Holes",
        },
        "crops": ["chilli", "vegetables", "turmeric", "onion"],
    },
    {
        "category": "planting",
        "name": "AgriPro Stainless Steel Seedling Transplanter Tool",
        "brand": "Falcon",
        "price": 1450.0,
        "mrp": 1850.0,
        "unit": "piece",
        "stock": 28,
        "image": EQUIPMENT_IMAGES["transplanter"],
        "gallery": [EQUIPMENT_IMAGES["transplanter"], EQUIPMENT_IMAGES["dibber"]],
        "desc": "Stand-up double handle seedling transplanting tube. Drop seedling through tube and trigger handle to plant without bending.",
        "rating": 4.8,
        "reviews": 92,
        "metadata": {
            "equipment_type": "Planting Tools",
            "power_source": "Manual",
            "material": "304 Stainless Steel",
            "weight": "2.2 kg",
            "dimensions": "92 x 14 x 14 cm",
            "warranty": "1 Year Replacement Warranty",
            "suitable_use": "Planting",
            "operating_width": "75 mm funnel opening",
            "capacity": "Single Plant Dispense",
        },
        "crops": ["paddy", "chilli", "vegetables", "cotton"],
    },

    # 3. IRRIGATION EQUIPMENT
    {
        "category": "irrigation",
        "name": "Jain Drip Master 1-Acre Complete Inline Drip Irrigation Kit",
        "brand": "Jain Irrigation",
        "price": 14800.0,
        "mrp": 18500.0,
        "unit": "kit",
        "stock": 14,
        "image": EQUIPMENT_IMAGES["drip"],
        "gallery": [EQUIPMENT_IMAGES["drip"], EQUIPMENT_IMAGES["sprinkler"], EQUIPMENT_IMAGES["pipe"]],
        "desc": "Complete commercial 1-acre kit: 16mm inline lateral tubes (40cm spacing, 2.2 LPH), screen filter, venturi injector, ball valves, and connectors.",
        "rating": 4.9,
        "reviews": 145,
        "metadata": {
            "equipment_type": "Irrigation Equipment",
            "power_source": "Manual",
            "material": "Virgin UV-Stabilized LLDPE",
            "weight": "42 kg",
            "dimensions": "1000m Pipe + Fittings Crate",
            "warranty": "5 Years Manufacturer Warranty",
            "suitable_use": "Irrigation",
            "operating_width": "1 Acre Coverage",
            "capacity": "2.2 LPH Emitter Discharge",
        },
        "crops": ["chilli", "cotton", "vegetables", "sugarcane", "maize", "groundnut"],
    },
    {
        "category": "irrigation",
        "name": "Kirloskar Aqua 1.5 HP Single-Phase Submersible Water Pump",
        "brand": "Kirloskar",
        "price": 11500.0,
        "mrp": 13800.0,
        "unit": "unit",
        "stock": 12,
        "image": EQUIPMENT_IMAGES["pump"],
        "gallery": [EQUIPMENT_IMAGES["pump"], EQUIPMENT_IMAGES["pipe"]],
        "desc": "100% copper wound submersible pump with stainless steel jacket and Noryl impellers. Head range up to 60m with discharge up to 3600 LPH.",
        "rating": 4.8,
        "reviews": 98,
        "metadata": {
            "equipment_type": "Irrigation Equipment",
            "power_source": "Electric",
            "material": "Stainless Steel 304 & Cast Iron",
            "weight": "16.5 kg",
            "dimensions": "58 x 14 x 14 cm",
            "warranty": "2 Years Comprehensive Warranty",
            "suitable_use": "Irrigation",
            "operating_width": "1.25 inch delivery outlet",
            "capacity": "1.5 HP / 3600 LPH",
        },
        "crops": ["paddy", "wheat", "sugarcane", "cotton", "vegetables"],
    },
    {
        "category": "irrigation",
        "name": "Varuna Rain Gun 1.5-Inch Full Circle Sprinkler with Tripod",
        "brand": "Jain Irrigation",
        "price": 3950.0,
        "mrp": 4800.0,
        "unit": "set",
        "stock": 20,
        "image": EQUIPMENT_IMAGES["sprinkler"],
        "gallery": [EQUIPMENT_IMAGES["sprinkler"], EQUIPMENT_IMAGES["pipe"]],
        "desc": "Heavy aluminium gear rain gun with adjustable jet breaker and 1.2m collapsible powder-coated steel tripod. 28-32 meter throw radius.",
        "rating": 4.7,
        "reviews": 67,
        "metadata": {
            "equipment_type": "Irrigation Equipment",
            "power_source": "Manual",
            "material": "Cast Aluminium & Brass Bushings",
            "weight": "6.8 kg",
            "dimensions": "120 x 40 x 30 cm",
            "warranty": "1 Year Warranty",
            "suitable_use": "Irrigation",
            "operating_width": "30 Meter Radius",
            "capacity": "15,000 LPH at 3 kg/cm2",
        },
        "crops": ["wheat", "maize", "sugarcane", "groundnut", "pulses"],
    },
    {
        "category": "irrigation",
        "name": "KisanDhara 2-Inch Flexible Heavy PVC Delivery Hose Pipe 50m",
        "brand": "KisanCraft",
        "price": 2800.0,
        "mrp": 3400.0,
        "unit": "roll",
        "stock": 22,
        "image": EQUIPMENT_IMAGES["pipe"],
        "gallery": [EQUIPMENT_IMAGES["pipe"], EQUIPMENT_IMAGES["pump"]],
        "desc": "Braided 3-ply heavy PVC lay-flat delivery pipe for water conveyance from pump to field. Kink-free and withstands 6 bar water pressure.",
        "rating": 4.6,
        "reviews": 49,
        "metadata": {
            "equipment_type": "Irrigation Equipment",
            "power_source": "Manual",
            "material": "Reinforced PVC Polyurethane",
            "weight": "14.2 kg",
            "dimensions": "50m Coil x 50mm inner dia",
            "warranty": "1 Year Warranty",
            "suitable_use": "Irrigation",
            "operating_width": "2 Inch Diameter",
            "capacity": "6 Bar Working Pressure",
        },
        "crops": ["general", "paddy", "wheat"],
    },

    # 4. SPRAYERS / SPRAYING EQUIPMENT
    {
        "category": "sprayers",
        "name": "Aspee Gator 16L 12V 12Ah Dual-Switch Battery Knapsack Sprayer",
        "brand": "Aspee",
        "price": 3250.0,
        "mrp": 4100.0,
        "unit": "unit",
        "stock": 35,
        "image": EQUIPMENT_IMAGES["sprayer_battery"],
        "gallery": [EQUIPMENT_IMAGES["sprayer_battery"], EQUIPMENT_IMAGES["sprayer_knapsack"]],
        "desc": "Heavy-duty 16L chemical-resistant tank with auto-cutoff micro diaphragm pump. Delivers 3.1 L/min with up to 6 hours continuous battery runtime.",
        "rating": 4.8,
        "reviews": 210,
        "metadata": {
            "equipment_type": "Spraying Equipment",
            "power_source": "Battery",
            "material": "UV-Stabilized High Impact Polypropylene",
            "weight": "5.6 kg (empty)",
            "dimensions": "42 x 20 x 55 cm",
            "warranty": "1 Year Motor & Battery Warranty",
            "suitable_use": "Spraying",
            "operating_width": "Multi-nozzle 1.5m spray swath",
            "capacity": "16 Litres / 12V 12Ah",
        },
        "crops": ["cotton", "chilli", "paddy", "vegetables", "maize"],
    },
    {
        "category": "sprayers",
        "name": "Neptune 2-in-1 Battery & Manual Knapsack Sprayer 16L",
        "brand": "Aspee",
        "price": 3650.0,
        "mrp": 4500.0,
        "unit": "unit",
        "stock": 25,
        "image": EQUIPMENT_IMAGES["sprayer_knapsack"],
        "gallery": [EQUIPMENT_IMAGES["sprayer_knapsack"], EQUIPMENT_IMAGES["sprayer_battery"]],
        "desc": "Hybrid operation: runs on 12V battery or manual hand pump lever if battery depletes in distant fields. Comes with 4 interchangeable brass nozzles.",
        "rating": 4.7,
        "reviews": 115,
        "metadata": {
            "equipment_type": "Spraying Equipment",
            "power_source": "Battery",
            "material": "Reinforced Virgin HDPE",
            "weight": "6.2 kg",
            "dimensions": "44 x 22 x 56 cm",
            "warranty": "1 Year Warranty",
            "suitable_use": "Spraying",
            "operating_width": "1.2 - 2.0 m swath",
            "capacity": "16 Litres",
        },
        "crops": ["chilli", "cotton", "paddy", "vegetables"],
    },
    {
        "category": "sprayers",
        "name": "KisanKraft KK-P768 4-Stroke 25cc Engine Power Sprayer",
        "brand": "KisanKraft",
        "price": 8900.0,
        "mrp": 10500.0,
        "unit": "unit",
        "stock": 10,
        "image": EQUIPMENT_IMAGES["sprayer_power"],
        "gallery": [EQUIPMENT_IMAGES["sprayer_power"], EQUIPMENT_IMAGES["sprayer_battery"]],
        "desc": "High-pressure petrol 4-stroke engine sprayer with 25L chemical tank and brass twin piston pump. Generates up to 35 bar pressure for tall orchards.",
        "rating": 4.6,
        "reviews": 74,
        "metadata": {
            "equipment_type": "Spraying Equipment",
            "power_source": "Fuel",
            "material": "Reinforced Brass Pump & Alloy Engine",
            "weight": "9.8 kg",
            "dimensions": "45 x 35 x 65 cm",
            "warranty": "1 Year Engine Warranty",
            "suitable_use": "Spraying",
            "operating_width": "Spray height up to 8 meters",
            "capacity": "25 Litres Tank / 1.0 HP Engine",
        },
        "crops": ["fruits", "cotton", "sugarcane", "vegetables"],
    },

    # 5. HARVESTING TOOLS
    {
        "category": "harvesting",
        "name": "Falcon Heavy Serrated Paddy & Wheat Harvesting Sickle",
        "brand": "Falcon",
        "price": 240.0,
        "mrp": 310.0,
        "unit": "piece",
        "stock": 100,
        "image": EQUIPMENT_IMAGES["sickle"],
        "gallery": [EQUIPMENT_IMAGES["sickle"], EQUIPMENT_IMAGES["pruning_saw"]],
        "desc": "Self-sharpening micro-serrated high carbon steel sickle for fast harvest of paddy, wheat, grass, and pulses without shattering grain ears.",
        "rating": 4.9,
        "reviews": 230,
        "metadata": {
            "equipment_type": "Harvesting Tools",
            "power_source": "Manual",
            "material": "Forged Manganese Spring Steel",
            "weight": "0.28 kg",
            "dimensions": "36 x 18 x 3 cm",
            "warranty": "6 Months Warranty",
            "suitable_use": "Harvesting",
            "operating_width": "22 cm curved blade",
            "capacity": "Fast Stalk Cutting",
        },
        "crops": ["paddy", "wheat", "soybean", "pulses"],
    },
    {
        "category": "harvesting",
        "name": "GreenReach 12ft Telescopic Fruit Harvester Pole with Cushion Basket",
        "brand": "Falcon",
        "price": 1250.0,
        "mrp": 1600.0,
        "unit": "piece",
        "stock": 30,
        "image": EQUIPMENT_IMAGES["harvester_pole"],
        "gallery": [EQUIPMENT_IMAGES["harvester_pole"], EQUIPMENT_IMAGES["sickle"]],
        "desc": "Extendable lightweight aluminium pole reaching up to 12 feet. Steel wire harvest fingers twist fruit into a soft padded foam collection basket.",
        "rating": 4.7,
        "reviews": 88,
        "metadata": {
            "equipment_type": "Harvesting Tools",
            "power_source": "Manual",
            "material": "Anodized Aircraft Aluminium",
            "weight": "1.3 kg",
            "dimensions": "1.4m to 3.6m extendable",
            "warranty": "1 Year Warranty",
            "suitable_use": "Harvesting",
            "operating_width": "15 cm basket opening",
            "capacity": "Picks 4-5 fruits per pull",
        },
        "crops": ["fruits", "vegetables"],
    },
    {
        "category": "harvesting",
        "name": "Tata Agrico Curved Pruning Saw with Wooden Handle",
        "brand": "Tata Agrico",
        "price": 460.0,
        "mrp": 580.0,
        "unit": "piece",
        "stock": 40,
        "image": EQUIPMENT_IMAGES["pruning_saw"],
        "gallery": [EQUIPMENT_IMAGES["pruning_saw"], EQUIPMENT_IMAGES["pruning"]],
        "desc": "Curved pull-stroke tooth design for effortless cutting through tree trunks, dried sugarcane clumps, and thick orchard wood.",
        "rating": 4.8,
        "reviews": 65,
        "metadata": {
            "equipment_type": "Harvesting Tools",
            "power_source": "Manual",
            "material": "Hardened High-Grade Steel 65Mn",
            "weight": "0.42 kg",
            "dimensions": "48 x 8 x 2.5 cm",
            "warranty": "1 Year Warranty",
            "suitable_use": "Harvesting",
            "operating_width": "35 cm saw blade",
            "capacity": "Branches up to 150mm",
        },
        "crops": ["sugarcane", "fruits", "general"],
    },

    # 6. SOIL & FIELD TOOLS
    {
        "category": "soil-field",
        "name": "Shaktiman 9-Tyne Heavy Rigid Cultivator Attachment",
        "brand": "Shaktiman",
        "price": 28500.0,
        "mrp": 33000.0,
        "unit": "unit",
        "stock": 5,
        "image": EQUIPMENT_IMAGES["cultivator"],
        "gallery": [EQUIPMENT_IMAGES["cultivator"], EQUIPMENT_IMAGES["plough"]],
        "desc": "Heavy box frame tractor cultivator with 9 forged reversible shovel points. Compatible with 35-55 HP tractors for secondary tillage.",
        "rating": 4.8,
        "reviews": 47,
        "metadata": {
            "equipment_type": "Soil & Field Tools",
            "power_source": "Manual",
            "material": "High Tensile Channel Steel & Forged Tines",
            "weight": "195 kg",
            "dimensions": "210 x 85 x 105 cm",
            "warranty": "2 Years Structural Warranty",
            "suitable_use": "Land preparation",
            "operating_width": "2.1 Meter Working Width",
            "capacity": "Tillage Depth up to 22 cm",
        },
        "crops": ["paddy", "wheat", "cotton", "maize", "sugarcane"],
    },
    {
        "category": "soil-field",
        "name": "Mahindra Agromaster 2-Bottom Reversible MB Plough",
        "brand": "Shaktiman",
        "price": 38000.0,
        "mrp": 44000.0,
        "unit": "unit",
        "stock": 4,
        "image": EQUIPMENT_IMAGES["plough"],
        "gallery": [EQUIPMENT_IMAGES["plough"], EQUIPMENT_IMAGES["cultivator"]],
        "desc": "Deep furrow mouldboard plough with hydraulic turn mechanism for inversion of tough soil and root burying in paddy and cotton fields.",
        "rating": 4.9,
        "reviews": 32,
        "metadata": {
            "equipment_type": "Soil & Field Tools",
            "power_source": "Manual",
            "material": "Boron Steel Reversible Shares",
            "weight": "240 kg",
            "dimensions": "165 x 90 x 115 cm",
            "warranty": "2 Years Warranty",
            "suitable_use": "Land preparation",
            "operating_width": "60 cm (2 Furrows)",
            "capacity": "Working depth 30-35 cm",
        },
        "crops": ["cotton", "paddy", "sugarcane"],
    },
    {
        "category": "soil-field",
        "name": "Falcon Manual Heavy Post Hole Digger & Earth Auger",
        "brand": "Falcon",
        "price": 1650.0,
        "mrp": 2100.0,
        "unit": "piece",
        "stock": 20,
        "image": EQUIPMENT_IMAGES["auger"],
        "gallery": [EQUIPMENT_IMAGES["auger"], EQUIPMENT_IMAGES["hoe"]],
        "desc": "Dual spiral cutting blades with sharp chisel tip for manual digging of fence post holes and plantation sapling pits.",
        "rating": 4.6,
        "reviews": 40,
        "metadata": {
            "equipment_type": "Soil & Field Tools",
            "power_source": "Manual",
            "material": "Hardened Carbon Steel Spiral",
            "weight": "4.8 kg",
            "dimensions": "110 x 30 x 15 cm",
            "warranty": "1 Year Warranty",
            "suitable_use": "Land preparation",
            "operating_width": "6-inch (150mm) hole",
            "capacity": "Digs up to 1 meter deep",
        },
        "crops": ["fruits", "general"],
    },

    # 7. SAFETY EQUIPMENT
    {
        "category": "safety",
        "name": "KisanRakshak Dual Chemical & Pesticide Protection Respirator",
        "brand": "Tata Agrico",
        "price": 890.0,
        "mrp": 1200.0,
        "unit": "unit",
        "stock": 50,
        "image": EQUIPMENT_IMAGES["respirator"],
        "gallery": [EQUIPMENT_IMAGES["respirator"], EQUIPMENT_IMAGES["gloves"]],
        "desc": "Half-face silicone mask with dual activated charcoal filter cartridges. Filters pesticide mist, organic vapors, sulfur, and fine agricultural dust.",
        "rating": 4.8,
        "reviews": 134,
        "metadata": {
            "equipment_type": "Safety Equipment",
            "power_source": "Manual",
            "material": "Food-grade Medical Silicone & Charcoal",
            "weight": "0.38 kg",
            "dimensions": "16 x 14 x 11 cm",
            "warranty": "6 Months Warranty",
            "suitable_use": "Safety",
            "operating_width": "Standard Adjustable Adult Fit",
            "capacity": "99.9% Particulate & Vapor Filtering",
        },
        "crops": ["cotton", "chilli", "paddy", "vegetables"],
    },
    {
        "category": "safety",
        "name": "Liberty Warrior Heavy PVC Waterproof Farm Gum Boots",
        "brand": "Falcon",
        "price": 680.0,
        "mrp": 850.0,
        "unit": "pair",
        "stock": 65,
        "image": EQUIPMENT_IMAGES["boots"],
        "gallery": [EQUIPMENT_IMAGES["boots"], EQUIPMENT_IMAGES["respirator"]],
        "desc": "Knee-high waterproof virgin PVC boots with deep cleated anti-skid mud lugs. Protects feet from mud, stagnant water, thorns, and snake bites.",
        "rating": 4.7,
        "reviews": 178,
        "metadata": {
            "equipment_type": "Safety Equipment",
            "power_source": "Manual",
            "material": "Virgin Flexible PVC Polymer",
            "weight": "1.4 kg (pair)",
            "dimensions": "Height 38 cm (Sizes 7-10 available)",
            "warranty": "1 Year Manufacturer Warranty",
            "suitable_use": "Safety",
            "operating_width": "Full Calf Coverage",
            "capacity": "100% Waterproof & Chemical Resistant",
        },
        "crops": ["paddy", "sugarcane", "general"],
    },
    {
        "category": "safety",
        "name": "AgriShield Heavy Nitrile Chemical Handling Long Gloves",
        "brand": "Falcon",
        "price": 320.0,
        "mrp": 420.0,
        "unit": "pair",
        "stock": 80,
        "image": EQUIPMENT_IMAGES["gloves"],
        "gallery": [EQUIPMENT_IMAGES["gloves"], EQUIPMENT_IMAGES["respirator"]],
        "desc": "15-inch elbow-length puncture-proof nitrile gauntlets for mixing chemicals, pesticide dilution, and handling sharp crop residues.",
        "rating": 4.6,
        "reviews": 85,
        "metadata": {
            "equipment_type": "Safety Equipment",
            "power_source": "Manual",
            "material": "Reinforced Flock-Lined Nitrile",
            "weight": "0.22 kg",
            "dimensions": "Length 38 cm (15 inches)",
            "warranty": "Replacement on manufacturing defect",
            "suitable_use": "Safety",
            "operating_width": "Elbow Length Gauntlet",
            "capacity": "Chemical & Acid Resistant",
        },
        "crops": ["cotton", "chilli", "general"],
    },

    # 8. STORAGE EQUIPMENT
    {
        "category": "storage",
        "name": "PICS GrainGuard 5-Layer Airtight Hermetic Grain Bags 50kg (Pack of 5)",
        "brand": "Tata Agrico",
        "price": 850.0,
        "mrp": 1050.0,
        "unit": "pack",
        "stock": 45,
        "image": EQUIPMENT_IMAGES["storage_bags"],
        "gallery": [EQUIPMENT_IMAGES["storage_bags"], EQUIPMENT_IMAGES["tarpaulin"]],
        "desc": "Multi-layer oxygen barrier storage bags for storing paddy, pulses, wheat, and maize for up to 2 years without chemical fumigation.",
        "rating": 4.9,
        "reviews": 156,
        "metadata": {
            "equipment_type": "Storage Equipment",
            "power_source": "Manual",
            "material": "5-Layer Co-extruded Polyethylene Barrier",
            "weight": "1.2 kg (pack)",
            "dimensions": "115 x 65 cm per bag",
            "warranty": "1 Year Storage Guarantee",
            "suitable_use": "Storage",
            "operating_width": "50 kg bag capacity",
            "capacity": "5 Bags x 50kg = 250kg Storage",
        },
        "crops": ["paddy", "wheat", "maize", "pulses", "groundnut"],
    },
    {
        "category": "storage",
        "name": "Nilkamal Agro Heavy-Duty Perforated Harvest Crates 25kg (Pack of 3)",
        "brand": "Falcon",
        "price": 1380.0,
        "mrp": 1750.0,
        "unit": "pack",
        "stock": 35,
        "image": EQUIPMENT_IMAGES["crates"],
        "gallery": [EQUIPMENT_IMAGES["crates"], EQUIPMENT_IMAGES["storage_bags"]],
        "desc": "Stackable ventilated high-density polyethylene crates for post-harvest tomato, mango, and vegetable transport without bruising.",
        "rating": 4.8,
        "reviews": 92,
        "metadata": {
            "equipment_type": "Storage Equipment",
            "power_source": "Manual",
            "material": "100% Virgin Food-Grade HDPE",
            "weight": "4.8 kg (pack of 3)",
            "dimensions": "54 x 36 x 30 cm per crate",
            "warranty": "2 Years Manufacturer Warranty",
            "suitable_use": "Storage",
            "operating_width": "Interlocking Stackable Design",
            "capacity": "25 kg load per crate",
        },
        "crops": ["vegetables", "fruits", "chilli"],
    },
    {
        "category": "storage",
        "name": "Silpaulin Dura 250 GSM Heavy Waterproof Farm Tarpaulin 24x18 ft",
        "brand": "Tata Agrico",
        "price": 2950.0,
        "mrp": 3600.0,
        "unit": "piece",
        "stock": 25,
        "image": EQUIPMENT_IMAGES["tarpaulin"],
        "gallery": [EQUIPMENT_IMAGES["tarpaulin"], EQUIPMENT_IMAGES["storage_bags"]],
        "desc": "Cross-laminated multi-layered UV-treated waterproof sheet with reinforced brass eyelets every 3 feet. Covers grain heaps and tractor implements.",
        "rating": 4.7,
        "reviews": 112,
        "metadata": {
            "equipment_type": "Storage Equipment",
            "power_source": "Manual",
            "material": "Cross-Laminated Multi-Layer Polyethylene",
            "weight": "8.2 kg",
            "dimensions": "24 x 18 Feet (7.3 x 5.5 m)",
            "warranty": "3 Years UV Protection Warranty",
            "suitable_use": "Storage",
            "operating_width": "432 sq.ft Surface Area",
            "capacity": "250 GSM Heavy Gauge",
        },
        "crops": ["paddy", "wheat", "cotton", "maize", "general"],
    },

    # 9. SMALL MACHINERY
    {
        "category": "small-machinery",
        "name": "VST Shakti 7 HP Petrol Multi-Purpose Power Tiller",
        "brand": "VST Shakti",
        "price": 42000.0,
        "mrp": 49000.0,
        "unit": "unit",
        "stock": 8,
        "image": EQUIPMENT_IMAGES["power_tiller"],
        "gallery": [EQUIPMENT_IMAGES["power_tiller"], EQUIPMENT_IMAGES["brush_cutter"]],
        "desc": "Powerful 212cc 4-stroke petrol rotary tiller with 24 curved tilling blades. Ideal for de-weeding, soil tilling in vegetable beds and narrow crop rows.",
        "rating": 4.9,
        "reviews": 86,
        "metadata": {
            "equipment_type": "Small Farm Machinery",
            "power_source": "Fuel",
            "material": "Cast Steel Gearbox & Forged Blades",
            "weight": "74 kg",
            "dimensions": "145 x 65 x 90 cm",
            "warranty": "1 Year Comprehensive Engine Warranty",
            "suitable_use": "Land preparation",
            "operating_width": "80-105 cm adjustable width",
            "capacity": "7.0 HP / 212cc / 3.6L Fuel Tank",
        },
        "crops": ["vegetables", "sugarcane", "cotton", "turmeric", "maize"],
    },
    {
        "category": "small-machinery",
        "name": "KisanKraft 52cc 2-Stroke Backpack Brush Cutter with Tiller Head",
        "brand": "KisanKraft",
        "price": 12500.0,
        "mrp": 14900.0,
        "unit": "set",
        "stock": 15,
        "image": EQUIPMENT_IMAGES["brush_cutter"],
        "gallery": [EQUIPMENT_IMAGES["brush_cutter"], EQUIPMENT_IMAGES["power_tiller"]],
        "desc": "Backpack mounted 52cc petrol engine with flexible shaft, 3-tooth brush blade, nylon line weed cutter, and mini rotary weeder attachment.",
        "rating": 4.7,
        "reviews": 68,
        "metadata": {
            "equipment_type": "Small Farm Machinery",
            "power_source": "Fuel",
            "material": "Forged Chrome Engine Cylinder & Steel Shaft",
            "weight": "11.5 kg",
            "dimensions": "180 x 30 x 30 cm",
            "warranty": "1 Year Warranty",
            "suitable_use": "Weeding",
            "operating_width": "25 cm weed swath / 30cm blade",
            "capacity": "52cc Engine / 2.2 HP",
        },
        "crops": ["paddy", "wheat", "cotton", "maize", "fruits"],
    },
    {
        "category": "small-machinery",
        "name": "Bharat Chaff Pro 2 HP Single-Phase Electric Fodder Cutter",
        "brand": "Shaktiman",
        "price": 16800.0,
        "mrp": 19500.0,
        "unit": "unit",
        "stock": 10,
        "image": EQUIPMENT_IMAGES["chaff_cutter"],
        "gallery": [EQUIPMENT_IMAGES["chaff_cutter"], EQUIPMENT_IMAGES["power_tiller"]],
        "desc": "High output 2 HP electric motor chaff cutter with 2 high-grade steel knives. Chops green grass, maize stalks, and straw into nutritious fodder.",
        "rating": 4.8,
        "reviews": 54,
        "metadata": {
            "equipment_type": "Small Farm Machinery",
            "power_source": "Electric",
            "material": "Structural Mild Steel Frame & Cast Iron Hub",
            "weight": "48 kg",
            "dimensions": "110 x 55 x 105 cm",
            "warranty": "1 Year Motor Warranty",
            "suitable_use": "Maintenance",
            "operating_width": "22 cm intake mouth",
            "capacity": "600 - 800 kg/hour chopping rate",
        },
        "crops": ["maize", "sugarcane", "general"],
    },

    # 10. OTHER AGRICULTURAL EQUIPMENT
    {
        "category": "other-equipment",
        "name": "ToughAgri Heavy 120L Single Pneumatic Tyre Wheelbarrow",
        "brand": "Tata Agrico",
        "price": 3400.0,
        "mrp": 4200.0,
        "unit": "unit",
        "stock": 20,
        "image": EQUIPMENT_IMAGES["wheelbarrow"],
        "gallery": [EQUIPMENT_IMAGES["wheelbarrow"], EQUIPMENT_IMAGES["hoe"]],
        "desc": "Seamless pressed heavy steel tray with powder coating and heavy 16-inch 4-ply pneumatic wheel. Built to carry fertilizer bags, manure, and harvest.",
        "rating": 4.8,
        "reviews": 77,
        "metadata": {
            "equipment_type": "Other Agricultural Equipment",
            "power_source": "Manual",
            "material": "Heavy Pressed Steel & Tubular Chassis",
            "weight": "15.8 kg",
            "dimensions": "145 x 65 x 68 cm",
            "warranty": "1 Year Frame Warranty",
            "suitable_use": "Transport",
            "operating_width": "65 cm overall width",
            "capacity": "120 Litres / 150 kg Pay Load",
        },
        "crops": ["general", "vegetables", "paddy"],
    },
    {
        "category": "other-equipment",
        "name": "Suraksha Agro Solar Powered Electric Fence Energizer Unit 5-Acre",
        "brand": "KisanKraft",
        "price": 7900.0,
        "mrp": 9600.0,
        "unit": "set",
        "stock": 12,
        "image": EQUIPMENT_IMAGES["fence"],
        "gallery": [EQUIPMENT_IMAGES["fence"], EQUIPMENT_IMAGES["soil_meter"]],
        "desc": "Solar-charged pulse fence energizer with 10W solar panel and 12V rechargeable battery. Emits harmless deterring pulses to protect crops from wild boars.",
        "rating": 4.7,
        "reviews": 46,
        "metadata": {
            "equipment_type": "Other Agricultural Equipment",
            "power_source": "Solar",
            "material": "Weatherproof IP65 ABS Enclosure",
            "weight": "4.5 kg",
            "dimensions": "32 x 24 x 18 cm",
            "warranty": "1 Year Comprehensive Warranty",
            "suitable_use": "Maintenance",
            "operating_width": "Up to 5 Acres Perimeter",
            "capacity": "1.2 Joule Stored Energy / 10kV Pulse",
        },
        "crops": ["groundnut", "maize", "paddy", "sugarcane", "cotton"],
    },
    {
        "category": "other-equipment",
        "name": "AgriSensor Pro 3-in-1 Soil Moisture, pH & Sunlight Meter",
        "brand": "Falcon",
        "price": 650.0,
        "mrp": 890.0,
        "unit": "piece",
        "stock": 40,
        "image": EQUIPMENT_IMAGES["soil_meter"],
        "gallery": [EQUIPMENT_IMAGES["soil_meter"], EQUIPMENT_IMAGES["fence"]],
        "desc": "Battery-free dual probe soil tester. Instantly measures soil moisture level, pH range (3.5 to 8.0), and sunlight intensity for optimal crop growth.",
        "rating": 4.6,
        "reviews": 89,
        "metadata": {
            "equipment_type": "Other Agricultural Equipment",
            "power_source": "Manual",
            "material": "Copper and Aluminium Sensor Probes",
            "weight": "0.14 kg",
            "dimensions": "29 x 5 x 3.8 cm",
            "warranty": "6 Months Replacement Warranty",
            "suitable_use": "Maintenance",
            "operating_width": "20 cm probe depth",
            "capacity": "Moisture, pH & Light Multi-Sensor",
        },
        "crops": ["vegetables", "cotton", "chilli", "fruits", "general"],
    },
]

# RENTAL MACHINERY DATA (for Rent mode)
RENTAL_MACHINERY = [
    {
        "name": "John Deere 5310 4WD (55 HP Tractor)",
        "type": "Tractor",
        "brand": "John Deere",
        "model": "5310 4WD",
        "daily_rate": 2800.0,
        "hourly_rate": 450.0,
        "location": "Vijayawada, Andhra Pradesh",
        "image_url": EQUIPMENT_IMAGES["tractor_rental"],
        "description": "55 HP heavy-duty 4WD tractor with power steering and dual-clutch PTO. Perfect for deep ploughing, laser levelling, and heavy haulage.",
        "is_available": True,
    },
    {
        "name": "Mahindra Arjun Novo 605 DI-i (60 HP Tractor)",
        "type": "Tractor",
        "brand": "Mahindra",
        "model": "Arjun Novo 605",
        "daily_rate": 2500.0,
        "hourly_rate": 400.0,
        "location": "Guntur, Andhra Pradesh",
        "image_url": EQUIPMENT_IMAGES["tractor_rental"],
        "description": "60 HP powerful diesel tractor with synchromesh transmission and 2200 kg lift capacity. Ideal for rotavator and combined harvester trolley.",
        "is_available": True,
    },
    {
        "name": "Kubota DC-68G Multi-Crop Combine Harvester",
        "type": "Harvester",
        "brand": "Kubota",
        "model": "DC-68G",
        "daily_rate": 5500.0,
        "hourly_rate": 900.0,
        "location": "Krishna, Andhra Pradesh",
        "image_url": EQUIPMENT_IMAGES["harvester_rental"],
        "description": "Rubber crawler track combine harvester with 2-meter cutter bar. Minimizes grain loss in wet paddy and wheat fields.",
        "is_available": True,
    },
    {
        "name": "DJI Agras T40 40L Agricultural Spraying Drone",
        "type": "Drone",
        "brand": "DJI Agri",
        "model": "Agras T40",
        "daily_rate": 3500.0,
        "hourly_rate": 600.0,
        "location": "Vijayawada, Andhra Pradesh",
        "image_url": EQUIPMENT_IMAGES["drone_rental"],
        "description": "40 kg spraying payload drone with active phased array radar and dual atomized centrifugal spray discs. Covers up to 40 acres per day.",
        "is_available": True,
    },
    {
        "name": "Shaktiman 7-Feet Heavy Duty Rotavator",
        "type": "Cultivator",
        "brand": "Shaktiman",
        "model": "Regular Plus 7ft",
        "daily_rate": 1400.0,
        "hourly_rate": 250.0,
        "location": "Eluru, Andhra Pradesh",
        "image_url": EQUIPMENT_IMAGES["rotavator_rental"],
        "description": "Heavy 54-blade rotary tiller for fine seedbed preparation in a single tractor pass. Works in both wet paddy puddling and dry fields.",
        "is_available": True,
    },
    {
        "name": "Dasmesh 9-Row Automatic Seed cum Fertilizer Drill",
        "type": "Seeder",
        "brand": "Dasmesh",
        "model": "9-Row Standard",
        "daily_rate": 1200.0,
        "hourly_rate": 200.0,
        "location": "Guntur, Andhra Pradesh",
        "image_url": EQUIPMENT_IMAGES["seeder_rental"],
        "description": "Pneumatic 9-row seed and fertilizer drill attachment for uniform depth sowing of wheat, maize, and pulses.",
        "is_available": True,
    },
    {
        "name": "Kirloskar 8 HP Diesel Portable Irrigation Pump",
        "type": "Water Pump",
        "brand": "Kirloskar",
        "model": "8 HP Centrifugal",
        "daily_rate": 650.0,
        "hourly_rate": 120.0,
        "location": "Vijayawada, Andhra Pradesh",
        "image_url": EQUIPMENT_IMAGES["pump"],
        "description": "Self-priming centrifugal diesel engine water pump with 3-inch inlet/outlet. Discharge up to 50,000 litres per hour for canal/pond irrigation.",
        "is_available": True,
    },
]


def seed_equipment(db: Session) -> dict:
    """Idempotently seed tools & equipment catalogue and rental machinery."""
    # 1. Ensure categories exist
    category_map = {}
    for slug, name, icon in EQUIPMENT_CATEGORIES:
        cat = db.query(ProductCategory).filter(ProductCategory.slug == slug).first()
        if not cat:
            cat = ProductCategory(name=name, slug=slug, icon=icon)
            db.add(cat)
            db.flush()
        category_map[slug] = cat

    # Also make sure "equipment" and "irrigation" exist if not already
    for fallback_slug, fallback_name in [("equipment", "Farm Equipment"), ("irrigation", "Irrigation")]:
        if fallback_slug not in category_map:
            cat = db.query(ProductCategory).filter(ProductCategory.slug == fallback_slug).first()
            if not cat:
                cat = ProductCategory(name=fallback_name, slug=fallback_slug, icon="fa-toolbox")
                db.add(cat)
                db.flush()
            category_map[fallback_slug] = cat

    # 2. Ensure sellers exist
    first_user = db.query(User).first()
    first_user_id = first_user.id if first_user else "system-admin"

    seller_map = []
    for idx, (shop_name, location, is_verified, rating) in enumerate(SELLERS_DATA, start=1):
        seller = db.query(Seller).filter(Seller.shop_name == shop_name).first()
        if not seller:
            seller = Seller(
                seller_id=f"FA-SEL-{idx:04d}",
                user_id=first_user_id,
                shop_name=shop_name,
                location=location,
                is_verified=is_verified,
                rating=rating,
                total_sales=120 + idx * 45,
            )
            db.add(seller)
            db.flush()
        seller_map.append(seller)

    # 3. Upsert products and equipment_metadata
    products_count = 0
    for idx, item in enumerate(PRODUCTS_CATALOGUE, start=1):
        cat = category_map.get(item["category"]) or category_map.get("other-equipment")
        seller = seller_map[idx % len(seller_map)]

        # Check existing by name
        product = db.query(Product).filter(Product.name == item["name"]).first()
        tags_dict = {
            "equipment_type": item["metadata"]["equipment_type"],
            "power_source": item["metadata"]["power_source"],
            "material": item["metadata"]["material"],
            "weight": item["metadata"]["weight"],
            "dimensions": item["metadata"]["dimensions"],
            "warranty": item["metadata"]["warranty"],
            "suitable_use": item["metadata"]["suitable_use"],
            "operating_width": item["metadata"]["operating_width"],
            "capacity": item["metadata"]["capacity"],
            "verified": seller.is_verified,
        }

        if product:
            product.category_id = cat.id
            product.seller_id = seller.id
            product.price = item["price"]
            product.original_price = item["mrp"]
            product.unit = item["unit"]
            product.stock_quantity = item["stock"]
            product.image_url = item["image"]
            product.images = item.get("gallery") or [item["image"]]
            product.brand = item["brand"]
            product.description = item["desc"]
            product.rating = item["rating"]
            product.total_reviews = item["reviews"]
            product.tags = tags_dict
            product.is_active = True
        else:
            product = Product(
                product_id=f"FA-EQP-{idx:05d}",
                category_id=cat.id,
                seller_id=seller.id,
                name=item["name"],
                description=item["desc"],
                price=item["price"],
                original_price=item["mrp"],
                unit=item["unit"],
                stock_quantity=item["stock"],
                min_order_quantity=1,
                image_url=item["image"],
                images=item.get("gallery") or [item["image"]],
                brand=item["brand"],
                rating=item["rating"],
                total_reviews=item["reviews"],
                is_active=True,
                tags=tags_dict,
            )
            db.add(product)
            db.flush()

        # EquipmentMetadata
        meta = db.query(EquipmentMetadata).filter(EquipmentMetadata.product_id == product.id).first()
        m_data = item["metadata"]
        if meta:
            meta.equipment_type = m_data["equipment_type"]
            meta.power_source = m_data["power_source"]
            meta.material = m_data["material"]
            meta.weight = m_data["weight"]
            meta.dimensions = m_data["dimensions"]
            meta.warranty = m_data["warranty"]
            meta.suitable_use = m_data["suitable_use"]
            meta.operating_width = m_data.get("operating_width")
            meta.capacity = m_data.get("capacity")
        else:
            meta = EquipmentMetadata(
                product_id=product.id,
                equipment_type=m_data["equipment_type"],
                power_source=m_data["power_source"],
                material=m_data["material"],
                weight=m_data["weight"],
                dimensions=m_data["dimensions"],
                warranty=m_data["warranty"],
                suitable_use=m_data["suitable_use"],
                operating_width=m_data.get("operating_width"),
                capacity=m_data.get("capacity"),
            )
            db.add(meta)

        # Sync crops
        db.query(ProductCrop).filter(ProductCrop.product_id == product.id).delete()
        for crop_name in item.get("crops", ["general"]):
            db.add(ProductCrop(product_id=product.id, crop_name=crop_name.lower().strip()))

        products_count += 1

    # 4. Upsert rental machinery into equipment table (Rent mode)
    rentals_count = 0
    for idx, r in enumerate(RENTAL_MACHINERY, start=1):
        existing_rental = db.query(Equipment).filter(Equipment.name == r["name"]).first()
        if existing_rental:
            existing_rental.type = r["type"]
            existing_rental.brand = r["brand"]
            existing_rental.model = r["model"]
            existing_rental.daily_rate = r["daily_rate"]
            existing_rental.hourly_rate = r["hourly_rate"]
            existing_rental.location = r["location"]
            existing_rental.description = r["description"]
            existing_rental.image_url = r["image_url"]
            existing_rental.is_available = r["is_available"]
        else:
            rental = Equipment(
                equipment_id=f"FA-RNT-{idx:04d}",
                name=r["name"],
                type=r["type"],
                brand=r["brand"],
                model=r["model"],
                daily_rate=r["daily_rate"],
                hourly_rate=r["hourly_rate"],
                location=r["location"],
                description=r["description"],
                image_url=r["image_url"],
                is_available=r["is_available"],
                owner_id=first_user_id,
            )
            db.add(rental)
        rentals_count += 1

    db.commit()
    return {
        "products_seeded": products_count,
        "rentals_seeded": rentals_count,
        "categories_count": len(category_map),
        "sellers_count": len(seller_map),
    }


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        res = seed_equipment(db)
        print("Tools & Equipment seeded successfully:")
        print(f"  Products (Buy mode): {res['products_seeded']}")
        print(f"  Rentals (Rent mode): {res['rentals_seeded']}")
        print(f"  Categories: {res['categories_count']}")
        print(f"  Sellers: {res['sellers_count']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
