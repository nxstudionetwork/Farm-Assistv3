"""Seeds the scalable crop catalog: taxonomy, cultivation methods, varieties.

The catalog is data, not logic. Everything a new crop needs lives in the tables
below, so adding a crop (or a whole agricultural domain) later means appending
rows here - never editing the seeding code and never touching the frontend.

Design notes
------------
* **Additive and idempotent.** Existing crops are classified, never rewritten or
  deleted, so live crop cycles keep their foreign keys.
* **Crop and variety are separate.** A crop row is shared reference data; each
  known variety is a ``crop_varieties`` row. This is what stops the catalog from
  growing "Tomato Field" / "Tomato Greenhouse" duplicates - the cultivation
  method is recorded on the cycle instead.
* **No mock farmer data.** Only reference catalog rows are inserted here; crops
  a farmer creates themselves are untouched.
"""

import logging
from collections import namedtuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.crop import (
    Crop,
    CropCategory,
    CropCycle,
    CropHealthCheck,
    CropVariety,
    CultivationMethod,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

#: (code, domain, category, subcategory, display_name, icon, sort_order)
#: ``code`` is the stable language-independent key used by the API and the UI.
CROP_TAXONOMY = [
    # --- Field crops -------------------------------------------------------
    ("field_crops.cereals",       "Field Crops", "Cereals",     None,        "Cereals",      "fa-solid fa-wheat-awn", 10),
    ("field_crops.pulses",        "Field Crops", "Pulses",      None,        "Pulses",       "fa-solid fa-peanut",     20),
    ("field_crops.oilseeds",      "Field Crops", "Oilseeds",    None,        "Oilseeds",     "fa-solid fa-seedling",   30),
    ("field_crops.fibres",        "Field Crops", "Fibre Crops", None,        "Fibre Crops",  "fa-solid fa-cotton-bolt", 40),
    ("field_crops.cash_crops",    "Field Crops", "Cash Crops",  None,        "Cash Crops",   "fa-solid fa-money-bill-wave", 50),
    ("field_crops.forage",        "Field Crops", "Forage",      None,        "Forage Crops", "fa-solid fa-cow",        60),
    # --- Horticulture ------------------------------------------------------
    ("horticulture.vegetables",   "Horticulture", "Vegetables",  None,        "Vegetables",   "fa-solid fa-carrot",     70),
    ("horticulture.leafy",        "Horticulture", "Vegetables",  "Leafy",      "Leafy Vegetables", "fa-solid fa-leaf",    75),
    ("horticulture.root_crops",   "Horticulture", "Vegetables",  "Root",       "Root Vegetables",  "fa-solid fa-arrow-down", 78),
    ("horticulture.tubers",       "Horticulture", "Vegetables",  "Tuber",      "Tuber Crops",  "fa-solid fa-circle-nodes", 80),
    ("horticulture.gourds",       "Horticulture", "Vegetables",  "Gourd",      "Gourds",       "fa-solid fa-circle",     82),
    ("horticulture.fruits",       "Horticulture", "Fruits",      None,        "Fruits",       "fa-solid fa-apple-whole", 90),
    ("horticulture.viticulture",  "Horticulture", "Fruits",  "Viticulture", "Grapes",      "fa-solid fa-wine-glass", 95),
    ("horticulture.flowers",      "Horticulture", "Flowers",     None,        "Flowers",      "fa-solid fa-fan",        100),
    ("horticulture.spices",       "Horticulture", "Spices",      None,        "Spices",       "fa-solid fa-mortar-pestle", 110),
    ("horticulture.medicinal",    "Horticulture", "Medicinal",   None,        "Medicinal Plants", "fa-solid fa-mortar-pestle", 120),
    ("horticulture.aromatic",     "Horticulture", "Aromatic",    None,        "Aromatic Plants",   "fa-solid fa-wind",    125),
    ("horticulture.ornamental",   "Horticulture", "Ornamental",  None,        "Ornamental",   "fa-solid fa-star",       130),
    ("horticulture.nursery",      "Horticulture", "Nursery",     None,        "Nursery",      "fa-solid fa-seedling",   140),
    # --- Plantation / forestry --------------------------------------------
    ("plantation.crops",          "Plantation",   "Plantation",  None,        "Plantation Crops", "fa-solid fa-tree",   150),
    ("forestry.tree_based",       "Forestry",     "Tree Crops",  None,        "Tree & Agroforestry", "fa-solid fa-tree", 160),
    ("forestry.silviculture",     "Forestry",     "Silviculture", None,       "Silviculture",  "fa-solid fa-tree",       170),
]

#: (code, name, is_soil_based, is_protected, description, sort_order)
#: The same Crop row is reused for every method, so protected cultivation and
#: hydroponics never need their own crop catalog.
CULTIVATION_METHODS = [
    ("open_field",  "Open Field",  True,  False, "Conventional field cultivation", 10),
    ("soil",        "Soil",        True,  False, "Soil based cultivation", 20),
    ("protected",   "Protected Cultivation", True, True,
     "Greenhouse, polyhouse, shade net or net house", 30),
    ("hydroponic",  "Hydroponic",  False, True, "Nutrient solution without soil", 40),
    ("orchard",     "Orchard",     True,  False, "Tree fruit plantation", 50),
    ("plantation",  "Plantation",  True,  False, "Long duration plantation crop", 60),
    ("nursery",     "Nursery",     True,  False, "Raised beds, polybags or pots", 70),
    ("vertical",    "Vertical / Soilless", False, True,
     "Vertical towers or soilless substrate", 80),
]

#: Ordered lifecycle stages per crop group. Task suggestions and Crop Health use
#: these instead of a single hardcoded lifecycle, so grapes get pruning and bud
#: break while rice gets seedling and grain filling.
LIFECYCLE_TEMPLATES = {
    "cereal": ["Seedling", "Vegetative", "Tillering", "Flowering", "Grain filling", "Maturity", "Harvest"],
    "pulse": ["Germination", "Vegetative", "Flowering", "Pod development", "Maturity", "Harvest"],
    "oilseed": ["Germination", "Vegetative", "Flowering", "Pod formation", "Seed filling", "Maturity", "Harvest"],
    "fibre": ["Germination", "Vegetative", "Squaring", "Flowering", "Boll development", "Maturity", "Harvest"],
    "vegetable_leafy": ["Nursery", "Germination", "Vegetative", "Harvest"],
    "vegetable_root": ["Germination", "Thinning", "Vegetative", "Root development", "Maturity", "Harvest"],
    "vegetable_tuber": ["Sprouting", "Vegetative", "Tuber initiation", "Tuber bulking", "Maturity", "Harvest"],
    "vegetable_fruit": ["Nursery", "Transplanting", "Vegetative", "Flowering", "Fruit development", "Maturity", "Harvest"],
    "vegetable_gourd": ["Nursery", "Transplanting", "Vegetative", "Flowering", "Fruit development", "Harvest"],
    "spice": ["Land preparation", "Planting", "Vegetative", "Flowering", "Rhizome / bulb development", "Harvest"],
    "viticulture": ["Dormancy", "Pruning", "Bud break", "Shoot growth", "Flowering", "Fruit set",
                    "Berry development", "Ripening", "Harvest", "Post-harvest"],
    "orchard": ["Dormancy", "Flowering", "Fruit set", "Fruit development", "Ripening", "Harvest"],
    "plantation": ["Establishment", "Vegetative growth", "Maintenance", "Flowering / bearing",
                   "Harvest", "Post-harvest"],
    "flower_cut": ["Establishment", "Vegetative", "Flower bud initiation", "Flowering", "Flower cutting", "Repeat cycle"],
    "flower_loose": ["Establishment", "Vegetative", "Flower bud initiation", "Flowering", "Loose flower harvest", "Repeat cycle"],
    "medicinal": ["Establishment", "Vegetative", "Harvest"],
    "forage": ["Establishment", "Vegetative", "First cutting", "Regrowth", "Repeat cutting"],
    "nursery": ["Sowing", "Germination", "Seedling", "Hardening", "Ready for transplant / dispatch"],
    "tree": ["Nursery", "Planting", "Establishment", "Juvenile growth", "Maturity", "Bearing", "Harvest"],
}

CropSpec = namedtuple(
    "CropSpec",
    "code name domain category subcategory scientific local_names life_cycle "
    "duration seasons climate soil water harvest_type unit market_type "
    "lifecycle varieties",
)
CropSpec.__new__.__defaults__ = (
    None, None, None, None,  # scientific, local_names, life_cycle, duration
    None, None, None, None,  # seasons, climate, soil, water
    None, None, None, None,  # harvest_type, unit, market_type, lifecycle
    (),                       # varieties
)


def _c(code, name, domain, category, subcategory=None, **kw):
    return CropSpec(code, name, domain, category, subcategory, **kw)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

CROP_CATALOG = [
_c("rice", "Rice", "Field Crops", "Cereals", scientific="Oryza sativa",
       local_names={"te": "అన్నం", "hi": "चावल"}, life_cycle="annual", duration=120,
       seasons="Kharif", climate="Warm humid", soil="Clay loam", water="High",
       harvest_type="Grain", unit="quintal", market_type="Grains",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"],
       varieties=["Sona Masuri", "BPT 5204", "IR 64", "MTU 7029", "Hara Masuri"]),
    _c("wheat", "Wheat", "Field Crops", "Cereals", scientific="Triticum aestivum",
       local_names={"te": "గోధుములు", "hi": "गेहूं"}, life_cycle="annual", duration=115,
       seasons="Rabi", climate="Cool temperate", soil="Well drained loam", water="Medium",
       harvest_type="Grain", unit="quintal", market_type="Grains",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"],
       varieties=["HD 3086", "HD 2967", "Sharbati", "Lokwan"]),
    _c("maize", "Maize", "Field Crops", "Cereals", scientific="Zea mays",
       local_names={"te": "మొక్కజొన్న", "hi": "मक्का"}, life_cycle="annual", duration=90,
       seasons="Kharif", climate="Warm temperate", soil="Well drained sandy loam", water="Medium",
       harvest_type="Grain", unit="quintal", market_type="Grains",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"],
       varieties=["NK 6240", "Hybrid 900", "Pioneer 3396", "Bio 9544"]),
    _c("sorghum", "Sorghum", "Field Crops", "Cereals", scientific="Sorghum bicolor",
       local_names={"te": "జొన్న", "hi": "ज्वार"}, life_cycle="annual", duration=100,
       seasons="Kharif", climate="Warm dry", soil="Black cotton soil", water="Low",
       harvest_type="Grain", unit="quintal", market_type="Grains",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"],
       varieties=["J 956014", "SPH 1", "Maldandi"]),
    _c("pearl_millet", "Pearl Millet", "Field Crops", "Cereals", scientific="Pennisetum glaucum",
       local_names={"te": "సజ్జి", "hi": "बाजरा"}, life_cycle="annual", duration=80,
       seasons="Kharif", climate="Hot dry", soil="Sandy loam", water="Low",
       harvest_type="Grain", unit="quintal", market_type="Grains",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"], varieties=["PC 238", "HGB 94", "PMH 3"]),
    _c("finger_millet", "Finger Millet", "Field Crops", "Cereals", scientific="Eleusine coracana",
       local_names={"te": "రాగి", "hi": "रागी"}, life_cycle="annual", duration=95,
       seasons="Kharif", climate="Warm temperate", soil="Red loam", water="Low",
       harvest_type="Grain", unit="quintal", market_type="Grains",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"], varieties=["PRM 2", "Godawari variety"]),
    _c("barley", "Barley", "Field Crops", "Cereals", scientific="Hordeum vulgare",
       local_names={"hi": "जौ"}, life_cycle="annual", duration=110,
       seasons="Rabi", climate="Cool", soil="Well drained loam", water="Medium",
       harvest_type="Grain", unit="quintal", market_type="Grains",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"], varieties=["JHB 150", "PL 172"]),
    _c("oats", "Oats", "Field Crops", "Cereals", scientific="Avena sativa",
       local_names={"hi": "जई"}, life_cycle="annual", duration=100,
       seasons="Rabi", climate="Cool", soil="Loam", water="Medium",
       harvest_type="Grain", unit="quintal", market_type="Grains",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"], varieties=["HFO 19", "JZO 1"]),
    _c("sweet_corn", "Sweet Corn", "Field Crops", "Cereals", scientific="Zea mays var. saccharata",
       local_names={"te": "మిఠాయి", "hi": "मक्का"}, life_cycle="annual", duration=75,
       seasons="Kharif / Rabi", climate="Warm", soil="Fertile loam", water="Medium",
       harvest_type="Cob", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_fruit"], varieties=["Ambrosia", "Pioneer 5058"]),

    # ---------------- Field crops: pulses ----------------------------------
    _c("chickpea", "Chickpea", "Field Crops", "Pulses", scientific="Cicer arietinum",
       local_names={"te": "సెన్నెగురు", "hi": "चना"}, life_cycle="annual", duration=100,
       seasons="Rabi", climate="Cool dry", soil="Well drained sandy loam", water="Low",
       harvest_type="Grain", unit="quintal", market_type="Pulses",
       lifecycle=LIFECYCLE_TEMPLATES["pulse"], varieties=["Desi JG 11", "JG 315", "Kabuli 105"]),
    _c("pigeon_pea", "Pigeon Pea", "Field Crops", "Pulses", scientific="Cajanus cajan",
       local_names={"te": "పప్పు", "hi": "अरहर"}, life_cycle="annual", duration=165,
       seasons="Kharif", climate="Warm", soil="Black or red loam", water="Low",
       harvest_type="Grain", unit="quintal", market_type="Pulses",
       lifecycle=LIFECYCLE_TEMPLATES["pulse"], varieties=["Maruti", "Jangar", "PRAGATI"]),
    _c("green_gram", "Green Gram", "Field Crops", "Pulses", scientific="Vigna radiata",
       local_names={"te": "పప్పు పెసరు", "hi": "मूंग"}, life_cycle="annual", duration=65,
       seasons="Kharif", climate="Warm humid", soil="Sandy loam", water="Low",
       harvest_type="Grain", unit="quintal", market_type="Pulses",
       lifecycle=LIFECYCLE_TEMPLATES["pulse"], varieties=["IPM 02-03", "MH 1142", "Sona"]),
    _c("black_gram", "Black Gram", "Field Crops", "Pulses", scientific="Vigna mungo",
       local_names={"te": "పప్పు నలుపు", "hi": "उड़द"}, life_cycle="annual", duration=75,
       seasons="Kharif", climate="Warm", soil="Loam", water="Low",
       harvest_type="Grain", unit="quintal", market_type="Pulses",
       lifecycle=LIFECYCLE_TEMPLATES["pulse"], varieties=["T 9", "VBG 4"]),
    _c("cowpea", "Cowpea", "Field Crops", "Pulses", scientific="Vigna unguiculata",
       local_names={"te": "అలువ", "hi": "लोबिया"}, life_cycle="annual", duration=80,
       seasons="Kharif", climate="Warm", soil="Sandy loam", water="Low",
       harvest_type="Grain", unit="quintal", market_type="Pulses",
       lifecycle=LIFECYCLE_TEMPLATES["pulse"], varieties=["Arka Swayam", "Pusa Dibar"]),

    # ---------------- Field crops: oilseeds --------------------------------
    _c("groundnut", "Groundnut", "Field Crops", "Oilseeds", scientific="Arachis hypogaea",
       local_names={"te": "పప్పు విత్తనాలు", "hi": "मूंगफली"}, life_cycle="annual", duration=105,
       seasons="Kharif", climate="Warm", soil="Sandy loam", water="Low",
       harvest_type="Pod", unit="quintal", market_type="Oilseeds",
       lifecycle=LIFECYCLE_TEMPLATES["oilseed"], varieties=["K-6", "TMV 7", "J 11", "TAG 24"]),
    _c("soybean", "Soybean", "Field Crops", "Oilseeds", scientific="Glycine max",
       local_names={"hi": "सोयाबीन"}, life_cycle="annual", duration=100,
       seasons="Kharif", climate="Warm humid", soil="Well drained black soil", water="Medium",
       harvest_type="Pod", unit="quintal", market_type="Oilseeds",
       lifecycle=LIFECYCLE_TEMPLATES["oilseed"], varieties=["JS 335", "JS 9560", "Phule Sangam"]),
    _c("sunflower", "Sunflower", "Field Crops", "Oilseeds", scientific="Helianthus annuus",
       local_names={"hi": "सूरजमुखी"}, life_cycle="annual", duration=90,
       seasons="Kharif", climate="Warm temperate", soil="Well drained black soil", water="Medium",
       harvest_type="Seed", unit="quintal", market_type="Oilseeds",
       lifecycle=LIFECYCLE_TEMPLATES["oilseed"], varieties=["KBSH 44", "KBSH 1", "Modern"]),
    _c("mustard", "Mustard", "Field Crops", "Oilseeds", scientific="Brassica juncea",
       local_names={"te": "పెసుగు", "hi": "सरसों"}, life_cycle="annual", duration=100,
       seasons="Rabi", climate="Cool", soil="Loam", water="Low",
       harvest_type="Seed", unit="quintal", market_type="Oilseeds",
       lifecycle=LIFECYCLE_TEMPLATES["oilseed"], varieties=["Pusa Bold", "Pusa Jaikisan", "Laxmi"]),
    _c("sesame", "Sesame", "Field Crops", "Oilseeds", scientific="Sesamum indicum",
       local_names={"te": "విత్తె", "hi": "तिल"}, life_cycle="annual", duration=85,
       seasons="Kharif", climate="Warm", soil="Well drained sandy loam", water="Low",
       harvest_type="Seed", unit="quintal", market_type="Oilseeds",
       lifecycle=LIFECYCLE_TEMPLATES["oilseed"], varieties=["B 71", "Pratilipi", "Yel 2"]),
    _c("linseed", "Linseed", "Field Crops", "Oilseeds", scientific="Linum usitatissimum",
       local_names={"hi": "अलसी"}, life_cycle="annual", duration=110,
       seasons="Rabi", climate="Cool", soil="Loam", water="Low",
       harvest_type="Seed", unit="quintal", market_type="Oilseeds",
       lifecycle=LIFECYCLE_TEMPLATES["oilseed"], varieties=["LC 209", "JLS 66"]),
    _c("castor", "Castor", "Field Crops", "Oilseeds", scientific="Ricinus communis",
       local_names={"te": "అముకు", "hi": "अरंडी"}, life_cycle="perennial", duration=150,
       seasons="Kharif", climate="Tropical", soil="Well drained red loam", water="Low",
       harvest_type="Seed", unit="quintal", market_type="Oilseeds",
       lifecycle=LIFECYCLE_TEMPLATES["oilseed"], varieties=["DCH 1", "Jw-1", "Aruna"]),

    # ---------------- Field crops: fibre & cash ---------------------------
    _c("cotton", "Cotton", "Field Crops", "Fibre Crops", scientific="Gossypium hirsutum",
       local_names={"te": "పత్తి", "hi": "कपास"}, life_cycle="annual", duration=160,
       seasons="Kharif", climate="Warm", soil="Black cotton soil", water="Medium",
       harvest_type="Boll", unit="quintal", market_type="Fibres",
       lifecycle=LIFECYCLE_TEMPLATES["fibre"], varieties=["Bt Hybrid", "Bt Cotton", "Nanded 44", "MCU 5"]),
    _c("jute", "Jute", "Field Crops", "Fibre Crops", scientific="Corchorus olitorius",
       local_names={"hi": "जूट"}, life_cycle="annual", duration=120,
       seasons="Kharif", climate="Warm humid", soil="Alluvial loam", water="High",
       harvest_type="Fibre", unit="quintal", market_type="Fibres",
       lifecycle=LIFECYCLE_TEMPLATES["fibre"], varieties=["JRO 2030", "JRO 108", "New Aref"]),
    _c("sugarcane", "Sugarcane", "Field Crops", "Cash Crops", scientific="Saccharum officinarum",
       local_names={"te": "చెరకు", "hi": "गन्ना"}, life_cycle="perennial", duration=360,
       seasons="Annual", climate="Warm tropical", soil="Deep rich loam", water="High",
       harvest_type="Cane", unit="tonne", market_type="Cash Crops",
       lifecycle=LIFECYCLE_TEMPLATES["plantation"], varieties=["Co 86032", "Co 0238", "Co 86010"]),
    _c("tobacco", "Tobacco", "Field Crops", "Cash Crops", scientific="Nicotiana tabacum",
       local_names={"hi": "तंबाकू"}, life_cycle="annual", duration=150,
       seasons="Kharif / Rabi", climate="Warm humid", soil="Well drained sandy loam", water="Medium",
       harvest_type="Leaf", unit="kg", market_type="Cash Crops",
       lifecycle=LIFECYCLE_TEMPLATES["oilseed"], varieties=["FCV TN 90", "Virginia", " flue cured"]),

    # ---------------- Vegetables ------------------------------------------
    _c("tomato", "Tomato", "Horticulture", "Vegetables", scientific="Solanum lycopersicum",
       local_names={"te": "టమాటా", "hi": "टमाटर"}, life_cycle="annual", duration=75,
       seasons="Rabi / Kharif", climate="Warm temperate", soil="Well drained loam", water="Medium",
       harvest_type="Fruit", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_fruit"],
       varieties=["Hybrid 70", "Arka Vikas", "Arka Megdoot", "Roma", "US 440"]),
    _c("potato", "Potato", "Horticulture", "Vegetables", "Tuber",
       scientific="Solanum tuberosum", local_names={"te": "బంగారం", "hi": "आलू"},
       life_cycle="annual", duration=90, seasons="Rabi", climate="Cool",
       soil="Well drained sandy loam", water="Medium", harvest_type="Tuber",
       unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_tuber"],
       varieties=["Kufri Bahar", "Kufri Jyoti", "Kufri Girimek", "Atlantic"]),
    _c("onion", "Onion", "Horticulture", "Vegetables", "Tuber",
       scientific="Allium cepa", local_names={"te": "ఉల్లిపిళ్లు", "hi": "प्याज"},
       life_cycle="biennial", duration=110, seasons="Rabi / Kharif", climate="Temperate",
       soil="Well drained loam", water="Medium", harvest_type="Bulb", unit="quintal",
       market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_tuber"],
       varieties=["Nasik Red", "Bangarapally", "Red Globe", "Pusa White"]),
    _c("garlic", "Garlic", "Horticulture", "Vegetables", "Tuber",
       scientific="Allium sativum", local_names={"te": "వెల్లురు", "hi": "लहसुन"},
       life_cycle="biennial", duration=120, seasons="Rabi", climate="Cool temperate",
       soil="Loam", water="Low", harvest_type="Bulb", unit="quintal",
       market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_tuber"],
       varieties=["Harihar", "Yeluri", "G 1-1"]),
    _c("carrot", "Carrot", "Horticulture", "Vegetables", "Root",
       scientific="Daucus carota", local_names={"hi": "गाजर"}, life_cycle="biennial",
       duration=90, seasons="Rabi", climate="Cool", soil="Deep sandy loam", water="Medium",
       harvest_type="Root", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_root"], varieties=["Pusa Kuber", "Nantes"]),
    _c("radish", "Radish", "Horticulture", "Vegetables", "Root",
       scientific="Raphanus sativus", local_names={"te": "ముల్లంగి", "hi": "मूला"},
       life_cycle="annual", duration=45, seasons="Rabi", climate="Cool",
       soil="Loam", water="Medium", harvest_type="Root", unit="quintal",
       market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_root"],
       varieties=["Pusa Jayanti", "French Breakfast"]),
    _c("beetroot", "Beetroot", "Horticulture", "Vegetables", "Root",
       scientific="Beta vulgaris", local_names={"hi": "चुकन्दर"}, life_cycle="biennial",
       duration=75, seasons="Rabi", climate="Cool", soil="Sandy loam", water="Medium",
       harvest_type="Root", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_root"], varieties=["Detroit Dark Red", "Crimson Globe"]),
    _c("cabbage", "Cabbage", "Horticulture", "Vegetables", scientific="Brassica oleracea var. capitata",
       local_names={"hi": "पत्ता गोभी"}, life_cycle="biennial", duration=90, seasons="Rabi",
       climate="Cool", soil="Well drained loam", water="Medium", harvest_type="Head",
       unit="quintal", market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_leafy"],
       varieties=["Golden Acre", "Copra", "Cross"]),
    _c("cauliflower", "Cauliflower", "Horticulture", "Vegetables", scientific="Brassica oleracea var. botrytis",
       local_names={"hi": "फूलगोभी"}, life_cycle="annual", duration=85, seasons="Rabi",
       climate="Cool", soil="Fertile loam", water="High", harvest_type="Curd",
       unit="quintal", market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_leafy"],
       varieties=["Pusa Sharbati", "Snowball 16"]),
    _c("broccoli", "Broccoli", "Horticulture", "Vegetables", scientific="Brassica oleracea var. italica",
       local_names={"hi": "ब्रोकली"}, life_cycle="annual", duration=80, seasons="Rabi",
       climate="Cool", soil="Fertile loam", water="High", harvest_type="Head",
       unit="quintal", market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_leafy"],
       varieties=["Green Courage", "Toria"]),
    _c("spinach", "Spinach", "Horticulture", "Vegetables", "Leafy",
       scientific="Spinacia oleracea", local_names={"hi": "पालक"}, life_cycle="annual",
       duration=45, seasons="Rabi", climate="Cool", soil="Fertile loam", water="Medium",
       harvest_type="Leaf", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_leafy"], varieties=["Pusa Green", "Fordhook Giant"]),
    _c("amaranthus", "Amaranthus", "Horticulture", "Vegetables", "Leafy",
       scientific="Amaranthus tricolor", local_names={"te": "ఆంధ్రకోకిల", "hi": "चौलाई"},
       life_cycle="annual", duration=45, seasons="All", climate="Warm humid",
       soil="Fertile loam", water="Medium", harvest_type="Leaf", unit="quintal",
       market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_leafy"],
       varieties=["Rama", "Krishna"]),
    _c("lettuce", "Lettuce", "Horticulture", "Vegetables", "Leafy",
       scientific="Lactuca sativa", local_names={"hi": "सलाद"}, life_cycle="annual",
       duration=60, seasons="Rabi", climate="Cool", soil="Well drained loam", water="High",
       harvest_type="Leaf", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_leafy"], varieties=["Great Lakes", "Pusa"]),
    _c("okra", "Okra", "Horticulture", "Vegetables", scientific="Abelmoschus esculentus",
       local_names={"te": "బండకాయ", "hi": "भिंडी"}, life_cycle="annual", duration=60,
       seasons="Kharif / Rabi", climate="Warm", soil="Well drained loam", water="Medium",
       harvest_type="Fruit", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_fruit"], varieties=["Arka Anamika", "Parbhani Kranti", "Arka Abhay"]),
    _c("brinjal", "Brinjal", "Horticulture", "Vegetables", scientific="Solanum melongena",
       local_names={"te": "బింగాకాయ", "hi": "बैंगन"}, life_cycle="annual", duration=80,
       seasons="Kharif / Rabi", climate="Warm", soil="Well drained loam", water="Medium",
       harvest_type="Fruit", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_fruit"], varieties=["Arka Kusumakar", "Arka Sheela", "Pusa Purple Long"]),
    _c("chilli", "Chilli", "Horticulture", "Vegetables", scientific="Capsicum annuum",
       local_names={"te": "మిర్చి", "hi": "मिर्च"}, life_cycle="annual", duration=90,
       seasons="Kharif", climate="Warm", soil="Well drained black soil", water="Medium",
       harvest_type="Fruit", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_fruit"], varieties=["Teja", "Guntur Special", "Byadgi", "Lca 334"]),
    _c("capsicum", "Capsicum", "Horticulture", "Vegetables", scientific="Capsicum annuum var. grossum",
       local_names={"te": "గ్రీన్ పెప్పర్", "hi": "शिमला मिर्च"}, life_cycle="annual", duration=90,
       seasons="Rabi", climate="Cool temperate", soil="Well drained loam", water="High",
       harvest_type="Fruit", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_fruit"], varieties=["California Wonder", "Yolo Wonder", "Solan Bharpur"]),
    _c("cucumber", "Cucumber", "Horticulture", "Vegetables", "Gourd",
       scientific="Cucumis sativus", local_names={"te": "పెగ్గుకాయ", "hi": "खीरा"},
       life_cycle="annual", duration=60, seasons="Rabi / Kharif", climate="Warm humid",
       soil="Fertile sandy loam", water="High", harvest_type="Fruit", unit="quintal",
       market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_gourd"],
       varieties=["Arka Udyan", "Arka Anamika", "Khira", "Himangi"]),
    _c("bottle_gourd", "Bottle Gourd", "Horticulture", "Vegetables", "Gourd",
       scientific="Lagenaria siceraria", local_names={"te": "అనపకాయ", "hi": "लौकी"},
       life_cycle="annual", duration=75, seasons="Rabi / Kharif", climate="Warm",
       soil="Fertile loam", water="High", harvest_type="Fruit", unit="quintal",
       market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_gourd"],
       varieties=["Arka Bahar", "Arka Chandan", "Pusa Naim"]),
    _c("bitter_gourd", "Bitter Gourd", "Horticulture", "Vegetables", "Gourd",
       scientific="Momordica charantia", local_names={"te": "కర్పాస", "hi": "करेला"},
       life_cycle="annual", duration=70, seasons="All", climate="Warm humid",
       soil="Fertile loam", water="Medium", harvest_type="Fruit", unit="quintal",
       market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_gourd"],
       varieties=["Arka Premier", "Priya", "Pusa Vishwa"]),
    _c("ridge_gourd", "Ridge Gourd", "Horticulture", "Vegetables", "Gourd",
       scientific="Luffa acutangula", local_names={"te": "నిమ్మకాయ", "hi": "तोरिया"},
       life_cycle="annual", duration=70, seasons="All", climate="Warm humid",
       soil="Fertile loam", water="Medium", harvest_type="Fruit", unit="quintal",
       market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_gourd"],
       varieties=["Arka Sujata", "Pusa Uday"]),
    _c("snake_gourd", "Snake Gourd", "Horticulture", "Vegetables", "Gourd",
       scientific="Trichosanthes dioica", local_names={"hi": "चिचौरा"},
       life_cycle="annual", duration=75, seasons="All", climate="Warm humid",
       soil="Fertile loam", water="Medium", harvest_type="Fruit", unit="quintal",
       market_type="Vegetables", lifecycle=LIFECYCLE_TEMPLATES["vegetable_gourd"],
       varieties=["Arka Mani", "Pusa Green"]),
    _c("pumpkin", "Pumpkin", "Horticulture", "Vegetables", "Gourd",
       scientific="Cucurbita pepo", local_names={"hi": "कद्दू"}, life_cycle="annual",
       duration=90, seasons="All", climate="Warm", soil="Fertile loam", water="Medium",
       harvest_type="Fruit", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_gourd"], varieties=["Arka Chandan", "Pusa Hybrid 1"]),
    _c("beans", "Beans", "Horticulture", "Vegetables", scientific="Phaseolus vulgaris",
       local_names={"te": "బింది", "hi": "सेमल"}, life_cycle="annual", duration=60,
       seasons="Rabi", climate="Cool warm", soil="Well drained loam", water="Medium",
       harvest_type="Pod", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_fruit"], varieties=["Arka Vikas", "Pusa Parvati"]),
    _c("peas", "Peas", "Horticulture", "Vegetables", scientific="Pisum sativum",
       local_names={"hi": "मटर"}, life_cycle="annual", duration=65, seasons="Rabi",
       climate="Cool", soil="Well drained loam", water="Medium", harvest_type="Pod",
       unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["vegetable_fruit"], varieties=["Arkel", "Azad P 1"]),
    _c("drumstick", "Drumstick", "Horticulture", "Vegetables", scientific="Moringa oleifera",
       local_names={"te": "మునగి", "hi": "सहजन"}, life_cycle="perennial", duration=180,
       seasons="All", climate="Tropical", soil="Well drained loam", water="Low",
       harvest_type="Pod / Leaf", unit="quintal", market_type="Vegetables",
       lifecycle=LIFECYCLE_TEMPLATES["orchard"], varieties=["PKM 1", "Local"]),

    # ---------------- Fruits ------------------------------------------------
    _c("mango", "Mango", "Horticulture", "Fruits", scientific="Mangifera indica",
       local_names={"te": "మామిడి", "hi": "आम"}, life_cycle="perennial", duration=3650,
       seasons="All", climate="Tropical subtropical", soil="Well drained alluvial", water="Medium",
       harvest_type="Fruit", unit="tonne", market_type="Fruits",
       lifecycle=LIFECYCLE_TEMPLATES["orchard"], varieties=["Alphonso", "Dasheri", "Banganapalli", "Totapuri", "Rani"]),
    _c("banana", "Banana", "Horticulture", "Fruits", scientific="Musa acuminata",
       local_names={"te": "అరవిద", "hi": "केला"}, life_cycle="perennial", duration=330,
       seasons="All", climate="Tropical humid", soil="Rich well drained loam", water="High",
       harvest_type="Bunch", unit="tonne", market_type="Fruits",
       lifecycle=LIFECYCLE_TEMPLATES["plantation"], varieties=["Grand Naine", "Robusta", "Red Lady", "Nendran"]),
    _c("papaya", "Papaya", "Horticulture", "Fruits", scientific="Carica papaya",
       local_names={"te": "బిరప్ప", "hi": "पपीता"}, life_cycle="perennial", duration=330,
       seasons="All", climate="Tropical", soil="Well drained sandy loam", water="Medium",
       harvest_type="Fruit", unit="tonne", market_type="Fruits",
       lifecycle=LIFECYCLE_TEMPLATES["plantation"], varieties=["Pusa Papaya", "Red Lady", "Solo"]),
    _c("guava", "Guava", "Horticulture", "Fruits", scientific="Psidium guajava",
       local_names={"te": "పసava", "hi": "अमरूद"}, life_cycle="perennial", duration=1460,
       seasons="All", climate="Tropical subtropical", soil="Well drained loam", water="Low",
       harvest_type="Fruit", unit="tonne", market_type="Fruits",
       lifecycle=LIFECYCLE_TEMPLATES["orchard"], varieties=["Allahabad Safed", "Lalitha", "Pink"]),
    _c("pomegranate", "Pomegranate", "Horticulture", "Fruits", scientific="Punica granatum",
       local_names={"te": "దాడిమ", "hi": "अनार"}, life_cycle="perennial", duration=1460,
       seasons="All", climate="Dry subtropical", soil="Well drained loam", water="Low",
       harvest_type="Fruit", unit="tonne", market_type="Fruits",
       lifecycle=LIFECYCLE_TEMPLATES["orchard"], varieties=["Bhagwa", "Ganesh", "Arakta"]),
    _c("orange", "Orange", "Horticulture", "Fruits", scientific="Citrus sinensis",
       local_names={"hi": "संतरा"}, life_cycle="perennial", duration=1460, seasons="All",
       climate="Subtropical", soil="Well drained loam", water="Medium", harvest_type="Fruit",
       unit="tonne", market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["Nagpur", "Sathgudi", "Valencia"]),
    _c("sweet_orange", "Sweet Orange", "Horticulture", "Fruits", scientific="Citrus sinensis", local_names={"te": "స్వీట్ ఆరెంజ్", "hi": "संतरा"},
       life_cycle="perennial", duration=1460, seasons="All", climate="Subtropical",
       soil="Well drained loam", water="Medium", harvest_type="Fruit", unit="tonne",
       market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["Mosambi", "Jaffa"]),
    _c("lemon", "Lemon", "Horticulture", "Fruits", scientific="Citrus limon",
       local_names={"te": "నిమ్మ", "hi": "नींबू"}, life_cycle="perennial", duration=1460,
       seasons="All", climate="Subtropical", soil="Well drained loam", water="Medium",
       harvest_type="Fruit", unit="tonne", market_type="Fruits",
       lifecycle=LIFECYCLE_TEMPLATES["orchard"], varieties=["Eureka", "Lisbon", "Pusa Viral"]),
    _c("lime", "Lime", "Horticulture", "Fruits", scientific="Citrus aurantifolia",
       local_names={"hi": "नींबू"}, life_cycle="perennial", duration=1460, seasons="All",
       climate="Tropical subtropical", soil="Well drained loam", water="Medium",
       harvest_type="Fruit", unit="tonne", market_type="Fruits",
       lifecycle=LIFECYCLE_TEMPLATES["orchard"], varieties=["Kagzi", "Tende"]),
    _c("watermelon", "Watermelon", "Horticulture", "Fruits", scientific="Citrullus lanatus",
       local_names={"te": "పుద్గ", "hi": "तरबूज"}, life_cycle="annual", duration=75,
       seasons="All", climate="Hot dry", soil="Sandy loam", water="Medium", harvest_type="Fruit",
       unit="tonne", market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["vegetable_gourd"],
       varieties=["Arka Manas", "Arka Jayanti", "Sugar Baby", "Charleston"]),
    _c("muskmelon", "Muskmelon", "Horticulture", "Fruits", scientific="Cucumis melo",
       local_names={"hi": "खरबूजा"}, life_cycle="annual", duration=75, seasons="Rabi",
       climate="Hot dry", soil="Sandy loam", water="Medium", harvest_type="Fruit",
       unit="tonne", market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["vegetable_gourd"],
       varieties=["Arka Madhu", "Arka Raja", "Hara Madu"]),
    _c("pineapple", "Pineapple", "Horticulture", "Fruits", scientific="Ananas comosus",
       local_names={"te": "అనాస", "hi": "अनानास"}, life_cycle="perennial", duration=540,
       seasons="All", climate="Tropical humid", soil="Acidic well drained", water="High",
       harvest_type="Fruit", unit="tonne", market_type="Fruits",
       lifecycle=LIFECYCLE_TEMPLATES["plantation"], varieties=["Queen", "MDU 1", "Smooth Cayenne"]),
    _c("jackfruit", "Jackfruit", "Horticulture", "Fruits", scientific="Artocarpus heterophyllus", local_names={"te": "జాక్‌ఫ్రూట్", "hi": "जकफल"},
       life_cycle="perennial", duration=1825, seasons="All", climate="Tropical humid",
       soil="Well drained laterite", water="Medium", harvest_type="Fruit", unit="tonne",
       market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"], varieties=["Local", "Hybrid"]),
    _c("sapota", "Sapota", "Horticulture", "Fruits", scientific="Manilkara zapota",
       local_names={"hi": "चिकू"}, life_cycle="perennial", duration=1825, seasons="All",
       climate="Tropical", soil="Well drained loam", water="Low", harvest_type="Fruit",
       unit="tonne", market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["Girikshma", "Khirni", "Common"]),
    _c("custard_apple", "Custard Apple", "Horticulture", "Fruits", scientific="Annona squamosa",
       local_names={"te": "సీతాపిడుకు", "hi": "सीता फल"}, life_cycle="perennial",
       duration=1825, seasons="All", climate="Tropical", soil="Well drained red loam",
       water="Low", harvest_type="Fruit", unit="tonne", market_type="Fruits",
       lifecycle=LIFECYCLE_TEMPLATES["orchard"], varieties=["Local", "Arka Nili"]),
    _c("apple", "Apple", "Horticulture", "Fruits", scientific="Malus domestica",
       local_names={"hi": "सेब"}, life_cycle="perennial", duration=1825, seasons="All",
       climate="Temperate", soil="Well drained loam", water="Medium", harvest_type="Fruit",
       unit="tonne", market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["Golden", "Red Delicious", "Royal Delicious", "Amber"]),
    _c("pear", "Pear", "Horticulture", "Fruits", scientific="Pyrus communis",
       local_names={"hi": "नाशपाती"}, life_cycle="perennial", duration=1825, seasons="All",
       climate="Temperate", soil="Well drained loam", water="Medium", harvest_type="Fruit",
       unit="tonne", market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["Bartlett", "Beurre Hardy"]),
    _c("peach", "Peach", "Horticulture", "Fruits", scientific="Prunus persica",
       local_names={"hi": "आड़ू"}, life_cycle="perennial", duration=1095, seasons="All",
       climate="Temperate", soil="Well drained loam", water="Medium", harvest_type="Fruit",
       unit="tonne", market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["Sharbati", "Red Gold", "Florida Red"]),
    _c("plum", "Plum", "Horticulture", "Fruits", scientific="Prunus domestica", local_names={"te": "ప్లమ్", "hi": "बेर"},
       life_cycle="perennial", duration=1095, seasons="All", climate="Temperate",
       soil="Well drained loam", water="Medium", harvest_type="Fruit", unit="tonne",
       market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["Santa Rosa", "B keynote"]),
    _c("strawberry", "Strawberry", "Horticulture", "Fruits", scientific="Fragaria ananassa", local_names={"te": "స్ట్రాబెరీ", "hi": "स्ट्रॉबेरी"},
       life_cycle="perennial", duration=120, seasons="Winter", climate="Cool temperate",
       soil="Acidic well drained", water="High", harvest_type="Fruit", unit="quintal",
       market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["vegetable_fruit"],
       varieties=["Chandler", "Sweetheart", "Festival"]),
    _c("dragon_fruit", "Dragon Fruit", "Horticulture", "Fruits", scientific="Hylocereus undatus", local_names={"te": "డ్రాగన్ ఫ్రూట్", "hi": "ड्रैगन फ्रूट"},
       life_cycle="perennial", duration=1095, seasons="All", climate="Tropical dry",
       soil="Well drained sandy", water="Low", harvest_type="Fruit", unit="tonne",
       market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["White flesh", "Red flesh"]),
    _c("avocado", "Avocado", "Horticulture", "Fruits", scientific="Persea americana", local_names={"te": "అవోకాడో", "hi": "एवोकाडो"},
       life_cycle="perennial", duration=1825, seasons="All", climate="Subtropical",
       soil="Well drained loam", water="Medium", harvest_type="Fruit", unit="tonne",
       market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["Hass", "Fuerte", "Purple"]),
    _c("coconut", "Coconut", "Plantation", "Plantation", scientific="Cocos nucifera",
       local_names={"te": "కొబ్బరి", "hi": "नारियल"}, life_cycle="perennial", duration=2920,
       seasons="All", climate="Tropical humid coastal", soil="Sandy laterite", water="High",
       harvest_type="Nut", unit="tonne", market_type="Plantation Produce",
       lifecycle=LIFECYCLE_TEMPLATES["plantation"], varieties=["West Coast", "East Coast", "Hybrid"]),
    _c("date_palm", "Date Palm", "Plantation", "Plantation", scientific="Phoenix dactylifera", local_names={"te": "ఖర్జూరం", "hi": "खजूर"},
       life_cycle="perennial", duration=3650, seasons="All", climate="Arid subtropical",
       soil="Sandy loam", water="Low", harvest_type="Fruit", unit="tonne",
       market_type="Plantation Produce", lifecycle=LIFECYCLE_TEMPLATES["plantation"],
       varieties=["Medjool", "Deglet Noor"]),
    _c("fig", "Fig", "Horticulture", "Fruits", scientific="Ficus carica", local_names={"te": "అత్తి పండు", "hi": "अंजीर"},
       life_cycle="perennial", duration=1825, seasons="All", climate="Subtropical",
       soil="Well drained loam", water="Low", harvest_type="Fruit", unit="tonne",
       market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"], varieties=["Common"]),
    _c("kiwi", "Kiwi", "Horticulture", "Fruits", scientific="Actinidia deliciosa", local_names={"te": "కివీ", "hi": "कीवी"},
       life_cycle="perennial", duration=1825, seasons="All", climate="Temperate",
       soil="Well drained loam", water="Medium", harvest_type="Fruit", unit="tonne",
       market_type="Fruits", lifecycle=LIFECYCLE_TEMPLATES["orchard"],
       varieties=["Hayward", "Zespri Green"]),

    # ---------------- Viticulture (grapes are a real category) -------------
    _c("grapes", "Grapes", "Horticulture", "Fruits", "Viticulture",
       scientific="Vitis vinifera", local_names={"te": "ద్రాక్షి", "hi": "अंगूर"},
       life_cycle="perennial", duration=730, seasons="Perennial",
       climate="Warm dry with sunny days", soil="Well drained sandy loam", water="Medium",
       harvest_type="Bunch", unit="tonne", market_type="Grapes",
       lifecycle=LIFECYCLE_TEMPLATES["viticulture"],
       varieties=["Thompson Seedless", "Sonaka", "Sharad Seedless", "Merlot", "Cabernet Sauvignon"]),

    # ---------------- Flowers ---------------------------------------------
    _c("rose", "Rose", "Horticulture", "Flowers", scientific="Rosa indica",
       local_names={"te": "రోజె", "hi": "गुलाब"}, life_cycle="perennial", duration=120,
       seasons="All", climate="Mild", soil="Well drained fertile loam", water="Medium",
       harvest_type="Cut flower", unit="kg", market_type="Flowers",
       lifecycle=LIFECYCLE_TEMPLATES["flower_cut"],
       varieties=["Kala Sharbati", "Mulligan", "Poornima", "Red Ramani"]),
    _c("jasmine", "Jasmine", "Horticulture", "Flowers", scientific="Jasminum sambac",
       local_names={"te": "మల్లి", "hi": "चमेली"}, life_cycle="perennial", duration=180,
       seasons="All", climate="Warm tropical", soil="Well drained fertile loam", water="Medium",
       harvest_type="Loose flower", unit="kg", market_type="Flowers",
       lifecycle=LIFECYCLE_TEMPLATES["flower_loose"], varieties=["Mullu", "Ooty", "Apartment"]),
    _c("marigold", "Marigold", "Horticulture", "Flowers", scientific="Tagetes erecta",
       local_names={"te": "పూలేపులు", "hi": "गेंदा"}, life_cycle="annual", duration=90,
       seasons="All", climate="Warm sunny", soil="Well drained sandy loam", water="Medium",
       harvest_type="Loose / cut flower", unit="kg", market_type="Flowers",
       lifecycle=LIFECYCLE_TEMPLATES["flower_cut"], varieties=["Pusa Narangi", "Pusa Karan", "African Gold"]),
    _c("chrysanthemum", "Chrysanthemum", "Horticulture", "Flowers", scientific="Chrysanthemum morifolium", local_names={"te": "మాలతీ", "hi": "गुलदाऊदी"},
       life_cycle="annual", duration=110, seasons="Rabi", climate="Cool",
       soil="Well drained fertile loam", water="High", harvest_type="Cut flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_cut"],
       varieties=["White, Yellow and Red", "Pusa Dushyant", "Indico"]),
    _c("gerbera", "Gerbera", "Horticulture", "Flowers", scientific="Gerbera jamesonii", local_names={"te": "జర్బెరా", "hi": "जरबेरा"},
       life_cycle="annual", duration=90, seasons="All", climate="Mild",
       soil="Well drained sandy loam", water="Medium", harvest_type="Cut flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_cut"],
       varieties=["Dana", "Kimberley", "Tropical"]),
    _c("tuberose", "Tuberose", "Horticulture", "Flowers", scientific="Polianthes tuberosa", local_names={"te": "ట్యూబరోజ్", "hi": "ट्यूबरोज़"},
       life_cycle="perennial", duration=120, seasons="Rabi", climate="Warm sunny",
       soil="Well drained loam", water="Medium", harvest_type="Cut flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_cut"],
       varieties=["Single", "Double", "Pearly"]),
    _c("carnation", "Carnation", "Horticulture", "Flowers", scientific="Dianthus caryophyllus", local_names={"te": "కార్నేషన్", "hi": "कार्नेशन"},
       life_cycle="perennial", duration=120, seasons="Winter", climate="Cool",
       soil="Well drained loam", water="Medium", harvest_type="Cut flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_cut"],
       varieties=["White", "Red", "Green"]),
    _c("orchid", "Orchid", "Horticulture", "Flowers", scientific="Dendrobium spp.", local_names={"te": "ఆర్కిడ్", "hi": "ऑर्किड"},
       life_cycle="perennial", duration=240, seasons="All", climate="Warm humid",
       soil="Growing media", water="High", harvest_type="Cut flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_cut"],
       varieties=["Dendrobium", "Phalaenopsis"]),
    _c("gladiolus", "Gladiolus", "Horticulture", "Flowers", scientific="Gladiolus hybrid", local_names={"te": "గ్లాడియోలస్", "hi": "ग्लैडिओलस"},
       life_cycle="perennial", duration=120, seasons="Winter", climate="Cool",
       soil="Well drained loam", water="Medium", harvest_type="Cut flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_cut"],
       varieties=["Red", "White", "Yellow", "Picotee"]),
    _c("lily", "Lily", "Horticulture", "Flowers", scientific="Lilium spp.", local_names={"te": "లిలీ", "hi": "लिली"},
       life_cycle="perennial", duration=120, seasons="Winter", climate="Cool",
       soil="Well drained loam", water="Medium", harvest_type="Cut flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_cut"],
       varieties=["Oriental", "Asiatic", "Cut flower"]),
    _c("lotus", "Lotus", "Horticulture", "Flowers", scientific="Nelumbo nucifera", local_names={"te": "పద్మం", "hi": "कमल"},
       life_cycle="perennial", duration=180, seasons="All", climate="Aquatic",
       soil="Pond bed", water="Very high", harvest_type="Loose flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_loose"],
       varieties=["Pink", "White"]),
    _c("crossandra", "Crossandra", "Horticulture", "Flowers", scientific="Crossandra infundibuliformis", local_names={"te": "క్రాస్‌ఆండ్రా", "hi": "क्रॉसएंड्रा"},
       life_cycle="perennial", duration=150, seasons="All", climate="Warm tropical",
       soil="Well drained loam", water="Medium", harvest_type="Loose flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_loose"],
       varieties=["Vampire", "Mandalay"]),
    _c("anthurium", "Anthurium", "Horticulture", "Flowers", scientific="Anthurium andraeanum", local_names={"te": "అన్థూరియం", "hi": "एंथोरियम"},
       life_cycle="perennial", duration=150, seasons="All", climate="Warm humid",
       soil="Growing media", water="High", harvest_type="Cut flower", unit="kg",
       market_type="Flowers", lifecycle=LIFECYCLE_TEMPLATES["flower_cut"],
       varieties=["Red", "Pink", "White"]),

    # ---------------- Plantation ------------------------------------------
    _c("arecanut", "Arecanut", "Plantation", "Plantation", scientific="Areca catechu",
       local_names={"te": "వెజ్జుమేను", "hi": "सुपारी"}, life_cycle="perennial", duration=1460,
       seasons="All", climate="Tropical humid", soil="Laterite", water="High",
       harvest_type="Nut", unit="tonne", market_type="Plantation Produce",
       lifecycle=LIFECYCLE_TEMPLATES["plantation"], varieties=["Mangalore", "Doddavail"]),
    _c("cashew", "Cashew", "Plantation", "Plantation", scientific="Anacardium occidentale", local_names={"te": "కాజూ పప్పు", "hi": "काजू"},
       life_cycle="perennial", duration=1460, seasons="All", climate="Tropical",
       soil="Laterite", water="Medium", harvest_type="Nut", unit="tonne",
       market_type="Plantation Produce", lifecycle=LIFECYCLE_TEMPLATES["plantation"],
       varieties=["H-4/273", "V 4", "Local"]),
    _c("rubber", "Rubber", "Plantation", "Plantation", scientific="Hevea brasiliensis", local_names={"te": "రబ్బర్ చెట్టు", "hi": "रबर"},
       life_cycle="perennial", duration=2555, seasons="All", climate="Tropical humid",
       soil="Well drained laterite", water="High", harvest_type="Latex", unit="kg",
       market_type="Plantation Produce", lifecycle=LIFECYCLE_TEMPLATES["plantation"],
       varieties=["RRIM 600", "GT 1", "PB 260"]),
    _c("tea", "Tea", "Plantation", "Plantation", scientific="Camellia sinensis", local_names={"te": "టీ", "hi": "चाय"},
       life_cycle="perennial", duration=1095, seasons="All", climate="Highland tropical",
       soil="Acidic well drained", water="High", harvest_type="Leaf", unit="kg",
       market_type="Plantation Produce", lifecycle=LIFECYCLE_TEMPLATES["plantation"],
       varieties=["Assam", "Darjeeling", "Nilgiri"]),
    _c("coffee", "Coffee", "Plantation", "Plantation", scientific="Coffea arabica", local_names={"te": "కాఫీ", "hi": "कॉफ़ी"},
       life_cycle="perennial", duration=1460, seasons="All", climate="Highland tropical",
       soil="Acidic well drained", water="High", harvest_type="Bean", unit="kg",
       market_type="Plantation Produce", lifecycle=LIFECYCLE_TEMPLATES["plantation"],
       varieties=["Arabica", "Robusta", "Chikmagalur"]),
    _c("cocoa", "Cocoa", "Plantation", "Plantation", scientific="Theobroma cacao", local_names={"te": "కాకో", "hi": "कोको"},
       life_cycle="perennial", duration=1460, seasons="All", climate="Tropical humid",
       soil="Well drained loam", water="High", harvest_type="Pod", unit="kg",
       market_type="Plantation Produce", lifecycle=LIFECYCLE_TEMPLATES["plantation"],
       varieties=["Forastero", "Trinitario", "Criollo"]),
    _c("oil_palm", "Oil Palm", "Plantation", "Plantation", scientific="Elaeis guineensis", local_names={"te": "ఆయిల్ తేగ", "hi": "तेल पाम"},
       life_cycle="perennial", duration=2920, seasons="All", climate="Tropical humid",
       soil="Sandy laterite", water="High", harvest_type="FFB", unit="tonne",
       market_type="Plantation Produce", lifecycle=LIFECYCLE_TEMPLATES["plantation"],
       varieties=["Durra", "Pisifera", "DxD"]),

    # ---------------- Spices ----------------------------------------------
    _c("black_pepper", "Black Pepper", "Horticulture", "Spices", scientific="Piper nigrum",
       local_names={"te": "కొప్ప మిర్రి", "hi": "काली मिर्च"}, life_cycle="perennial", duration=1095,
       seasons="All", climate="Tropical humid", soil="Well drained loam", water="High",
       harvest_type="Berry", unit="kg", market_type="Spices",
       lifecycle=LIFECYCLE_TEMPLATES["spice"], varieties=["Karimunda", "Panchavedam", "Malabar"]),
    _c("cardamom", "Cardamom", "Horticulture", "Spices", scientific="Elettaria cardamomum", local_names={"te": "ఏలక్ కర్దాము", "hi": "इलायची"},
       life_cycle="perennial", duration=1095, seasons="All", climate="Humid highland",
       soil="Acidic well drained", water="High", harvest_type="Pod", unit="kg",
       market_type="Spices", lifecycle=LIFECYCLE_TEMPLATES["spice"],
       varieties=["Malabar", "Mysore", "Bombei"]),
    _c("turmeric", "Turmeric", "Horticulture", "Spices", scientific="Curcuma longa",
       local_names={"te": "పసిపొడ్గు", "hi": "हल्दी"}, life_cycle="perennial", duration=240,
       seasons="Rabi", climate="Warm humid", soil="Well drained loam", water="High",
       harvest_type="Rhizome", unit="quintal", market_type="Spices",
       lifecycle=LIFECYCLE_TEMPLATES["spice"], varieties=["Erode", "Alleppey Finger", "Bhavani", "Prathibha"]),
    _c("ginger", "Ginger", "Horticulture", "Spices", scientific="Zingiber officinale",
       local_names={"te": "అలపము", "hi": "अदरक"}, life_cycle="perennial", duration=240,
       seasons="Rabi", climate="Warm humid", soil="Well drained sandy loam", water="High",
       harvest_type="Rhizome", unit="quintal", market_type="Spices",
       lifecycle=LIFECYCLE_TEMPLATES["spice"], varieties=["Rio de Janeiro", "Mysore", "Thingpui"]),
    _c("coriander", "Coriander", "Horticulture", "Spices", scientific="Coriandrum sativum", local_names={"te": "ధనియాలు", "hi": "धनिया"},
       life_cycle="annual", duration=60, seasons="Rabi", climate="Cool",
       soil="Well drained loam", water="Low", harvest_type="Seed / leaf", unit="kg",
       market_type="Spices", lifecycle=LIFECYCLE_TEMPLATES["spice"],
       varieties=["Rajendra", "GC 1", "Kharchia 65"]),
    _c("cumin", "Cumin", "Horticulture", "Spices", scientific="Cuminum cyminum", local_names={"te": "జీరకు", "hi": "जीरा"},
       life_cycle="annual", duration=90, seasons="Rabi", climate="Arid",
       soil="Sandy loam", water="Low", harvest_type="Seed", unit="kg",
       market_type="Spices", lifecycle=LIFECYCLE_TEMPLATES["spice"],
       varieties=["GC 1", "Pratap", "RS 1"]),
    _c("fenugreek", "Fenugreek", "Horticulture", "Spices", scientific="Trigonella foenum-graecum", local_names={"te": "మెంతు కూర", "hi": "मेथी"},
       life_cycle="annual", duration=80, seasons="Rabi", climate="Cool",
       soil="Well drained loam", water="Low", harvest_type="Seed", unit="kg",
       market_type="Spices", lifecycle=LIFECYCLE_TEMPLATES["spice"],
       varieties=["Methi", "Hissar", "Rajka"]),
    _c("clove", "Clove", "Horticulture", "Spices", scientific="Syzygium aromaticum", local_names={"te": "లవంగం", "hi": "लौंग"},
       life_cycle="perennial", duration=1460, seasons="All", climate="Tropical humid",
       soil="Laterite", water="High", harvest_type="Bud", unit="kg", market_type="Spices",
       lifecycle=LIFECYCLE_TEMPLATES["spice"], varieties=["Local", "TRI 1"]),
    _c("cinnamon", "Cinnamon", "Horticulture", "Spices", scientific="Cinnamomum verum", local_names={"te": "దాల్చిని", "hi": "दालचीनी"},
       life_cycle="perennial", duration=1460, seasons="All", climate="Tropical",
       soil="Well drained loam", water="High", harvest_type="Bark", unit="kg",
       market_type="Spices", lifecycle=LIFECYCLE_TEMPLATES["spice"], varieties=["Ceylon"]),
    _c("nutmeg", "Nutmeg", "Horticulture", "Spices", scientific="Myristica fragrans", local_names={"te": "వెనిముకు", "hi": "जायफल"},
       life_cycle="perennial", duration=1825, seasons="All", climate="Tropical humid",
       soil="Laterite", water="High", harvest_type="Seed", unit="kg", market_type="Spices",
       lifecycle=LIFECYCLE_TEMPLATES["spice"], varieties=["Local", "Th TKU"]),
    _c("saffron", "Saffron", "Horticulture", "Spices", scientific="Crocus sativus", local_names={"te": "కాశ్మరీ కుర్కుమె", "hi": "केसर"},
       life_cycle="perennial", duration=1095, seasons="Rabi", climate="Cold arid",
       soil="Well drained", water="Low", harvest_type="Stigma", unit="kg",
       market_type="Spices", lifecycle=LIFECYCLE_TEMPLATES["spice"],
       varieties=["Kashmir", "Konya", "Mangan"]),

    # ---------------- Medicinal & aromatic ---------------------------------
    _c("ashwagandha", "Ashwagandha", "Horticulture", "Medicinal", scientific="Withania somnifera", local_names={"te": "అశ్వగంధా", "hi": "अश्वगंधा"},
       life_cycle="annual", duration=150, seasons="Kharif", climate="Warm dry",
       soil="Well drained sandy loam", water="Low", harvest_type="Root", unit="kg",
       market_type="Medicinal Plants", lifecycle=LIFECYCLE_TEMPLATES["medicinal"],
       varieties=["Mysore", "Jawahar", "KSM-66"]),
    _c("aloe_vera", "Aloe Vera", "Horticulture", "Medicinal", scientific="Aloe barbadensis", local_names={"te": "అలోవెరా", "hi": "एलोवेरा"},
       life_cycle="perennial", duration=730, seasons="All", climate="Arid subtropical",
       soil="Sandy loam", water="Low", harvest_type="Leaf", unit="kg",
       market_type="Medicinal Plants", lifecycle=LIFECYCLE_TEMPLATES["medicinal"],
       varieties=["Local", "Dharwad", "Saguar"]),
    _c("tulsi", "Tulsi", "Horticulture", "Medicinal", scientific="Ocimum tenuiflorum", local_names={"te": "తులసి", "hi": "तुलसी"},
       life_cycle="perennial", duration=180, seasons="All", climate="Tropical",
       soil="Well drained loam", water="Medium", harvest_type="Herb", unit="kg",
       market_type="Medicinal Plants", lifecycle=LIFECYCLE_TEMPLATES["medicinal"],
       varieties=["Rama", "Krishna", "Vana"]),
    _c("lemongrass", "Lemongrass", "Horticulture", "Aromatic", scientific="Cymbopogon citratus", local_names={"te": "వచనగ్రాస్", "hi": "नींबू घास"},
       life_cycle="perennial", duration=365, seasons="All", climate="Tropical",
       soil="Well drained loam", water="Medium", harvest_type="Herb", unit="kg",
       market_type="Aromatic Plants", lifecycle=LIFECYCLE_TEMPLATES["medicinal"],
       varieties=["West Indian", "East Indian", "Citronella"]),
    _c("mint", "Mint", "Horticulture", "Aromatic", scientific="Mentha spp.", local_names={"te": "పుదినా", "hi": "पुदीना"},
       life_cycle="perennial", duration=120, seasons="Rabi", climate="Cool humid",
       soil="Moist loam", water="High", harvest_type="Herb", unit="kg",
       market_type="Aromatic Plants", lifecycle=LIFECYCLE_TEMPLATES["medicinal"],
       varieties=["Pudina", "Spearmint", "Mentha arvensis"]),
    _c("stevia", "Stevia", "Horticulture", "Aromatic", scientific="Stevia rebaudiana", local_names={"te": "స్టీవియా", "hi": "स्टीविया"},
       life_cycle="perennial", duration=365, seasons="All", climate="Subtropical",
       soil="Well drained loam", water="Medium", harvest_type="Leaf", unit="kg",
       market_type="Aromatic Plants", lifecycle=LIFECYCLE_TEMPLATES["medicinal"],
       varieties=["Eirete", "Criolla", "Morita"]),
    _c("vetiver", "Vetiver", "Horticulture", "Aromatic", scientific="Chrysopogon zizanioides", local_names={"te": "వెటివర్", "hi": "चिरेता"},
       life_cycle="perennial", duration=730, seasons="All", climate="Tropical",
       soil="Well drained loam", water="Medium", harvest_type="Root", unit="kg",
       market_type="Aromatic Plants", lifecycle=LIFECYCLE_TEMPLATES["medicinal"],
       varieties=["Local", "Hullu", "Vetiver I"]),

    # ---------------- Fodder / forage -------------------------------------
    _c("napier_grass", "Napier Grass", "Field Crops", "Forage", scientific="Pennisetum purpureum", local_names={"te": "నేపియర్ గడ్డి", "hi": "नैपियर घास"},
       life_cycle="perennial", duration=1095, seasons="All", climate="Tropical humid",
       soil="Well drained loam", water="High", harvest_type="Fodder", unit="tonne",
       market_type="Fodder", lifecycle=LIFECYCLE_TEMPLATES["forage"],
       varieties=["Napier 1", "Napier 2 (Banneru)", "NPM 2"]),
    _c("fodder_maize", "Fodder Maize", "Field Crops", "Forage", scientific="Zea mays", local_names={"te": "పశుమైస్", "hi": "चारे का मक्का"},
       life_cycle="annual", duration=75, seasons="All", climate="Warm", soil="Fertile loam",
       water="Medium", harvest_type="Fodder", unit="tonne", market_type="Fodder",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"], varieties=["Cow 1", "African Tall", "JTM 1"]),
    _c("fodder_sorghum", "Fodder Sorghum", "Field Crops", "Forage", scientific="Sorghum bicolor", local_names={"te": "పశు జొన్జోను", "hi": "चारे का ज्वार"},
       life_cycle="annual", duration=90, seasons="Kharif / Rabi", climate="Semi arid",
       soil="Loam", water="Low", harvest_type="Fodder", unit="tonne", market_type="Fodder",
       lifecycle=LIFECYCLE_TEMPLATES["cereal"], varieties=["Multi", "Sudan Grass", "J 401"]),
    _c("lucerne", "Lucerne", "Field Crops", "Forage", scientific="Medicago sativa",
       local_names={"te": "ఆల్ఫాల్ఫా", "hi": "लूसर्न"}, life_cycle="perennial", duration=1095,
       seasons="Rabi", climate="Cool temperate", soil="Well drained loam", water="Medium",
       harvest_type="Fodder", unit="tonne", market_type="Fodder",
       lifecycle=LIFECYCLE_TEMPLATES["forage"], varieties=["Luz 8", "Sirsa 1", "LL 9"]),

    # ---------------- Nursery ---------------------------------------------
    _c("fruit_seedlings", "Fruit Seedlings", "Horticulture", "Nursery",
       scientific="Various", local_names={"te": "పండ్ల మొక్కలు", "hi": "फलों के पौधे"}, life_cycle="perennial", duration=365, seasons="All",
       climate="Tropical subtropical", soil="Growing media", water="Medium",
       harvest_type="Seedling", unit="Nos", market_type="Nursery Plants",
       lifecycle=LIFECYCLE_TEMPLATES["nursery"],
       varieties=["Mango", "Guava", "Pomegranate", "Papaya", "Citrus"]),
    _c("vegetable_seedlings", "Vegetable Seedlings", "Horticulture", "Nursery",
       scientific="Various", local_names={"te": "కూరగాయల మొక్కలు", "hi": "सब्जी पौधे"},
       life_cycle="annual", duration=45, seasons="All", climate="Warm",
       soil="Growing media", water="High", harvest_type="Seedling", unit="Nos",
       market_type="Nursery Plants", lifecycle=LIFECYCLE_TEMPLATES["nursery"],
       varieties=["Tomato", "Chilli", "Brinjal", "Capsicum", "Cucumber"]),
    _c("flower_seedlings", "Flower Seedlings", "Horticulture", "Nursery",
       scientific="Various", local_names={"te": "పూల మొక్కలు", "hi": "फूल पौधे"},
       life_cycle="annual", duration=60, seasons="All", climate="Mild",
       soil="Growing media", water="Medium", harvest_type="Seedling", unit="Nos",
       market_type="Nursery Plants", lifecycle=LIFECYCLE_TEMPLATES["nursery"],
       varieties=["Marigold", "Rose", "Chrysanthemum", "Jasmine"]),
    _c("tree_saplings", "Tree Saplings", "Horticulture", "Nursery",
       scientific="Various", local_names={"te": "చెట్ల మొక్కలు", "hi": "नर्सरी पौधे"},
       life_cycle="perennial", duration=730, seasons="All", climate="Tropical",
       soil="Growing media", water="Medium", harvest_type="Sapling", unit="Nos",
       market_type="Nursery Plants", lifecycle=LIFECYCLE_TEMPLATES["nursery"],
       varieties=["Neem", "Jamun", "Mango", "Teak", "Bamboo"]),

    # ---------------- Forestry / agroforestry ------------------------------
    _c("teak", "Teak", "Forestry", "Silviculture", scientific="Tectona grandis", local_names={"te": "తేక", "hi": "सागौन"},
       life_cycle="perennial", duration=7300, seasons="Monsoon", climate="Tropical",
       soil="Well drained loam", water="Medium", harvest_type="Timber", unit="m3",
       market_type="Timber", lifecycle=LIFECYCLE_TEMPLATES["tree"],
       varieties=["Local", "Nilamiri", "Kanchan"]),
    _c("bamboo", "Bamboo", "Forestry", "Tree Crops", scientific="Bambusa vulgaris", local_names={"te": "చెమ్మ", "hi": "बाँस"},
       life_cycle="perennial", duration=1825, seasons="Monsoon", climate="Tropical humid",
       soil="Well drained loam", water="Medium", harvest_type="Culm", unit="tonne",
       market_type="Timber", lifecycle=LIFECYCLE_TEMPLATES["tree"],
       varieties=["Bambusa vulgaris", "Dendrocalamus"]),
    _c("neem", "Neem", "Forestry", "Tree Crops", scientific="Azadirachta indica",
       local_names={"te": "వేప", "hi": "नीम"}, life_cycle="perennial", duration=3650,
       seasons="Monsoon", climate="Tropical dry", soil="Well drained loam", water="Low",
       harvest_type="Leaf / seed", unit="kg", market_type="Timber",
       lifecycle=LIFECYCLE_TEMPLATES["tree"], varieties=["Local"]),
    _c("eucalyptus", "Eucalyptus", "Forestry", "Silviculture", scientific="Eucalyptus globulus", local_names={"te": "యూకేలిప్టస్", "hi": "नीलगिरी"},
       life_cycle="perennial", duration=3650, seasons="Monsoon", climate="Subtropical",
       soil="Well drained loam", water="Medium", harvest_type="Timber", unit="m3",
       market_type="Timber", lifecycle=LIFECYCLE_TEMPLATES["tree"],
       varieties=["Eucalyptus globulus", "Hybrid"]),
    _c("sandalwood", "Sandalwood", "Forestry", "Silviculture", scientific="Santalum album", local_names={"te": "చందనం", "hi": "चन्दन"},
       life_cycle="perennial", duration=7300, seasons="Monsoon", climate="Subtropical",
       soil="Well drained loam", water="Low", harvest_type="Timber", unit="m3",
       market_type="Timber", lifecycle=LIFECYCLE_TEMPLATES["tree"], varieties=["Local"]),
]

#: Nutrient-solution targets per crop, stored on the crop row as
#: ``Crop.hydroponic_targets`` so hydroponics reads them from the catalog.
#: Keys are catalog codes, so a soilless crop is never a second crop record.
#: ``group`` is the presentation grouping used by the hydroponics reference view.
#: pH values are solution pH; EC is in mS/cm.
#:
#: This is also the single definition of which crops support soilless
#: production: :data:`HYDROPONIC_FRIENDLY` is derived from it, so a crop cannot
#: be advertised as hydroponic without targets, and cannot have targets without
#: being advertised. Adding a soilless crop is a one-line change here.
HYDROPONIC_TARGETS = {
    "lettuce": {"ph": [5.5, 6.5], "ec": [0.8, 1.6], "days": 45, "group": "Leafy"},
    "spinach": {"ph": [5.5, 6.5], "ec": [1.2, 2.0], "days": 40, "group": "Leafy"},
    "tomato": {"ph": [5.5, 6.5], "ec": [2.0, 3.5], "days": 90, "group": "Fruiting"},
    "cucumber": {"ph": [5.5, 6.5], "ec": [1.8, 2.8], "days": 80, "group": "Fruiting"},
    "capsicum": {"ph": [5.5, 6.5], "ec": [1.8, 2.8], "days": 85, "group": "Fruiting"},
    "brinjal": {"ph": [5.5, 6.5], "ec": [1.8, 2.8], "days": 85, "group": "Fruiting"},
    "chilli": {"ph": [5.5, 6.5], "ec": [1.8, 2.8], "days": 85, "group": "Fruiting"},
}

#: Crops that intentionally support soilless / hydroponic production. The list
#: is metadata, not a second catalog: these rows are reused for hydroponics.
#: Derived from :data:`HYDROPONIC_TARGETS` so a crop can never claim soilless
#: support without targets to validate its readings against.
HYDROPONIC_FRIENDLY = set(HYDROPONIC_TARGETS)

#: (domain, category, subcategory) -> taxonomy code. Built from
#: :data:`CROP_TAXONOMY` so a catalog entry never invents a code that no node
#: declares, and so a parent node is inherited by its subcategories.
_TAXONOMY_INDEX = {
    (domain, category, subcategory): code
    for code, domain, category, subcategory, _display, _icon, _order in CROP_TAXONOMY
}


def _taxonomy_code(domain, category, subcategory):
    """Resolve the taxonomy node a catalog entry belongs to.

    Subcategories win over their parent node (Leafy Vegetables rather than plain
    Vegetables), and an unknown triple still yields a stable synthesised code
    instead of silently losing the crop's classification.
    """
    if subcategory:
        exact = _TAXONOMY_INDEX.get((domain, category, subcategory))
        if exact:
            return exact
    parent = _TAXONOMY_INDEX.get((domain, category, None))
    if parent:
        return parent
    key = "_".join(part for part in (domain, category, subcategory) if part)
    return key.lower().replace(" ", "_")


def seed_crop_taxonomy(db: Session) -> int:
    """Insert the taxonomy and cultivation-method reference rows.

    Idempotent: existing codes are updated in place, never duplicated.
    """
    added = 0
    for code, domain, category, subcategory, display, icon, order in CROP_TAXONOMY:
        node = db.query(CropCategory).filter(CropCategory.code == code).first()
        if node is None:
            node = CropCategory(code=code)
            added += 1
        node.domain = domain
        node.category = category
        node.subcategory = subcategory
        node.display_name = display
        node.icon = icon
        node.sort_order = order
        node.is_active = True
        db.add(node)

    for code, name, soil_based, protected, desc, order in CULTIVATION_METHODS:
        method = db.query(CultivationMethod).filter(CultivationMethod.code == code).first()
        if method is None:
            method = CultivationMethod(code=code)
            added += 1
        method.name = name
        method.is_soil_based = soil_based
        method.is_protected = protected
        method.description = desc
        method.sort_order = order
        method.is_active = True
        db.add(method)

    db.commit()
    return added


def _normalise(name):
    return " ".join((name or "").lower().replace("(", " ").replace(")", " ").split())


def _alias_key(name):
    """Collapse well-known synonyms so 'Paddy (Rice)' and 'Rice' match."""
    key = _normalise(name)
    key = key.replace(" okra ladies finger ", " okra ")
    key = key.replace(" ladies finger", "")
    if key.startswith("paddy "):
        key = key[len("paddy "):]
    return key.strip()


def _cultivation_methods_for(spec) -> list:
    """Cultivation methods a crop supports, derived from the catalog metadata.

    Soilless methods are opt-in metadata (:data:`HYDROPONIC_FRIENDLY`) rather than
    an assumption about the whole domain, so grapes are not advertised as a
    hydroponic crop. Everything else follows from the crop's own life cycle and
    domain, so no crop is ever duplicated per environment.
    """
    methods = ["open_field", "soil"]
    if spec.domain in ("Horticulture", "Plantation", "Forestry"):
        methods += ["protected", "nursery"]
    if spec.domain == "Plantation":
        methods += ["orchard", "plantation"]
    if spec.domain == "Forestry":
        methods += ["plantation"]
    if spec.category in ("Fruits", "Tree Crops"):
        methods += ["orchard", "plantation"]
    if spec.domain == "Field Crops" and spec.category == "Forage":
        methods += ["nursery"]
    if spec.category == "Nursery":
        methods += ["nursery"]
    if spec.code in HYDROPONIC_FRIENDLY:
        methods += ["hydroponic", "vertical"]
    known = {code for code, *_ in CULTIVATION_METHODS}
    return [code for code in dict.fromkeys(methods) if code in known]


def _apply_spec(crop: Crop, spec: CropSpec, node) -> None:
    crop.name = spec.name
    crop.domain = spec.domain
    crop.category = spec.category
    crop.subcategory = spec.subcategory
    crop.category_id = node.id if node else None
    crop.scientific_name = spec.scientific
    crop.local_names = spec.local_names
    crop.life_cycle_type = spec.life_cycle
    crop.growth_duration_days = spec.duration
    crop.season = spec.seasons
    crop.suitable_seasons = spec.seasons
    crop.suitable_climate = spec.climate
    crop.suitable_soil_types = spec.soil
    crop.water_requirement = spec.water
    crop.harvest_type = spec.harvest_type
    crop.production_unit = spec.unit
    crop.market_type = spec.market_type
    crop.lifecycle_stages = list(spec.lifecycle) if spec.lifecycle else None
    crop.suitable_cultivation_methods = _cultivation_methods_for(spec)
    crop.hydroponic_targets = dict(HYDROPONIC_TARGETS[spec.code]) if spec.code in HYDROPONIC_TARGETS else None
    crop.is_catalog = True
    crop.is_archived = False


def _seed_varieties(db: Session, crop: Crop, names) -> int:
    """Insert a crop's known varieties, skipping the ones already recorded."""
    added = 0
    for name in names or ():
        existing = (
            db.query(CropVariety)
            .filter(
                CropVariety.crop_id == crop.id,
                func.lower(CropVariety.name) == name.lower(),
            )
            .first()
        )
        if existing:
            continue
        db.add(CropVariety(crop_id=crop.id, name=name, duration_days=crop.growth_duration_days))
        added += 1
    return added


def _mirror_legacy_varieties(db: Session, crops) -> int:
    """Turn a legacy free-text ``crops.variety`` into a real variety row.

    The one-off schema migration does this for rows that predate
    ``crop_varieties``, but a crop created any other way (an older client, an
    import, a direct write) can still carry its variety only as free text. The
    crop system classifies crops here, so it also guarantees every crop's
    variety is selectable - otherwise a classified crop shows up with no
    varieties at all. Idempotent, so it is safe on every startup.
    """
    added = 0
    for crop in crops:
        name = (crop.variety or "").strip()
        if not name:
            continue
        existing = (
            db.query(CropVariety)
            .filter(
                CropVariety.crop_id == crop.id,
                func.lower(CropVariety.name) == name.lower(),
            )
            .first()
        )
        if existing:
            continue
        db.add(
            CropVariety(
                crop_id=crop.id,
                name=name,
                duration_days=crop.growth_duration_days,
                is_custom=True,
            )
        )
        added += 1
    return added


def _find_catalog_crop(db: Session, spec: CropSpec):
    """Locate the crop row this catalog entry should live on.

    Preference order: the stable ``crop_id`` code, then an exact (case
    insensitive) name, then a known synonym such as "Paddy (Rice)". Matching an
    existing row means it is classified rather than duplicated, so the farmer's
    crop cycles keep pointing at the same crop id.
    """
    crop = (
        db.query(Crop)
        .filter(Crop.crop_id == spec.code, Crop.is_archived.is_(False))
        .first()
    )
    if crop:
        return crop, False

    crop = (
        db.query(Crop)
        .filter(
            func.lower(Crop.name) == spec.name.lower(),
            Crop.is_archived.is_(False),
        )
        .first()
    )
    if crop:
        return crop, True

    wanted = _alias_key(spec.name)
    for candidate in db.query(Crop).filter(Crop.is_archived.is_(False)).all():
        if _alias_key(candidate.name) == wanted:
            return candidate, True
    return None, False


def seed_crops(db: Session):
    """Seed taxonomy, cultivation methods, the crop catalog and varieties.

    Returns the number of new crop rows inserted. Existing crops are classified
    in place, so crop cycles keep pointing at the same ids. Safe to run on every
    startup: every step matches on a stable code or name and never deletes a row.
    """
    seed_crop_taxonomy(db)

    nodes = {n.code: n for n in db.query(CropCategory).all()}
    added = 0
    classified = 0
    varieties_added = 0

    for spec in CROP_CATALOG:
        node = nodes.get(_taxonomy_code(spec.domain, spec.category, spec.subcategory))
        crop, created = _find_catalog_crop(db, spec)
        if crop is None:
            crop = Crop(crop_id=spec.code)
            created = True
            added += 1
        elif not created:
            classified += 1
        _apply_spec(crop, spec, node)
        db.add(crop)
        db.flush()
        varieties_added += _seed_varieties(db, crop, spec.varieties)

    db.commit()

    keepers = _consolidate_duplicate_crops(db)

    # Consolidation keeps whichever row holds the farmer's cycles, which may not
    # be the row the catalog was applied to above. Re-apply the metadata to the
    # survivor so the taxonomy, lifecycle and varieties never end up archived.
    reclassified = 0
    for spec in CROP_CATALOG:
        crop = keepers.get(_alias_key(spec.name))
        if crop is None or crop.is_archived:
            continue
        node = nodes.get(_taxonomy_code(spec.domain, spec.category, spec.subcategory))
        if _matches_spec(crop, spec, node):
            continue
        _apply_spec(crop, spec, node)
        db.add(crop)
        reclassified += 1
        varieties_added += _seed_varieties(db, crop, spec.varieties)
    if reclassified:
        db.commit()

    total = db.query(Crop).filter(Crop.is_archived.is_(False)).count()
    varieties = db.query(CropVariety).count()
    logger.info(
        "Crop catalog seeded: %d new crop(s), %d classified, %d varieties added, "
        "%d re-classified after merge (%d active crops, %d varieties).",
        added, classified, varieties_added, reclassified, total, varieties,
    )
    return added


def _matches_spec(crop: Crop, spec: CropSpec, node) -> bool:
    """True when the row already carries the catalog entry's key metadata."""
    return (
        crop.name == spec.name
        and crop.domain == spec.domain
        and crop.category == spec.category
        and crop.subcategory == spec.subcategory
        and crop.category_id == (node.id if node else None)
        and bool(crop.is_catalog)
        and list(crop.lifecycle_stages or []) == list(spec.lifecycle or [])
    )


def _move_varieties(db: Session, keeper: Crop, dup: Crop) -> None:
    """Re-point a duplicate crop's varieties at the crop that is being kept.

    Varieties follow the crop so a farmer's cycle never loses the variety it
    was recorded with. A name that already exists on the keeper is deactivated
    rather than deleted - the consolidation rule is "archive, never remove" - and
    any cycle using it is moved to the keeper's row of the same name.

    A catalog row's varieties are deliberately left behind. Its keeper is a
    farmer's row that has not yet been given the catalog identity, and
    :func:`seed_crops` re-seeds the catalog's own varieties onto the survivor
    straight after this runs. Moving them here as well would graft a farmer's
    custom variety onto the catalog row and duplicate every catalog variety.
    """
    if dup.is_catalog and not keeper.is_catalog:
        return

    keeper_names = {(v.name or "").strip().lower(): v for v in keeper.varieties}
    for variety in list(dup.varieties):
        key = (variety.name or "").strip().lower()
        existing = keeper_names.get(key)
        if existing is not None and existing.id != variety.id:
            for cycle in db.query(CropCycle).filter(CropCycle.variety_id == variety.id).all():
                cycle.variety_id = existing.id
            variety.is_active = False
            continue
        variety.crop_id = keeper.id
        keeper_names[key] = variety
    db.flush()


def _consolidate_duplicate_crops(db: Session) -> dict:
    """Fold duplicate crop rows together without deleting farmer data.

    The old seed created entries such as "Paddy (Rice)" while the app created
    "Rice", so several crops existed twice and a farmer's own crop could be
    shadowed by the catalog copy. Duplicates are archived, never removed: their
    crop cycles, varieties and health checks are re-pointed at the kept row
    first, so no cycle, check or task is lost.

    Returns a ``{alias_key: kept_crop}`` index so the caller can re-apply catalog
    metadata to whichever row survived - a farmer's busier "Paddy (Rice)" row may
    win the merge, and the taxonomy has to follow it.
    """
    groups = {}
    active_crops = db.query(Crop).filter(Crop.is_archived.is_(False)).all()
    mirrored = _mirror_legacy_varieties(db, active_crops)
    for crop in active_crops:
        groups.setdefault(_alias_key(crop.name), []).append(crop)

    archived = 0
    index = {}
    for key, rows in groups.items():
        if not key:
            continue
        # Prefer the row that already has activity, then the older one, so the
        # farmer's own data always decides which row survives.
        rows.sort(key=lambda c: (-_activity_count(db, c), c.created_at or c.id))
        keeper, duplicates = rows[0], rows[1:]
        index[key] = keeper

        for dup in duplicates:
            for cycle in db.query(CropCycle).filter(CropCycle.crop_id == dup.id).all():
                cycle.crop_id = keeper.id
            for check in db.query(CropHealthCheck).filter(CropHealthCheck.crop_id == dup.id).all():
                check.crop_id = keeper.id
            _move_varieties(db, keeper, dup)
            # The legacy free-text variety is a crop-level hint; keep the
            # keeper's value but adopt the duplicate's when the keeper has none.
            if not keeper.variety and dup.variety:
                keeper.variety = dup.variety
            dup.is_archived = True
            dup.is_catalog = False
            archived += 1

    if archived or mirrored:
        db.commit()
    if mirrored:
        logger.info(
            "Crop catalog: mirrored %d legacy free-text variety value(s) into crop_varieties.",
            mirrored,
        )
    if archived:
        logger.info(
            "Crop catalog: archived %d duplicate crop row(s) after re-pointing their cycles.",
            archived,
        )
    return index


def _activity_count(db: Session, crop: Crop) -> int:
    cycles = db.query(CropCycle).filter(CropCycle.crop_id == crop.id).count()
    checks = db.query(CropHealthCheck).filter(CropHealthCheck.crop_id == crop.id).count()
    return cycles + checks


if __name__ == "__main__":
    import app.models  # noqa: F401  (register all ORM models)
    from app.routers.sensors import Sensor, SensorReading  # noqa: F401
    from app.database.connection import SessionLocal

    db = SessionLocal()
    try:
        res = seed_crops(db)
        print(f"Seeded crops: {res} new (total {db.query(Crop).count()}).")
    finally:
        db.close()
