"""
Crop guidance knowledge base and plan builders for the Crop Health module.

This service turns a crop cycle (crop, sowing date, current stage) into:

* a full crop-cycle timeline (10 canonical stages, elapsed/remaining estimates),
* a "Your Crop Health Plan" grouped into Now / This Week / Coming Up, each item
  being an actionable recommendation with why/what/when/priority,
* the "Watch for This" list for the current stage (what to look out for),
* a structured, rule-based health-check result (Observation -> Possible concern
  -> Recommended action -> Follow-up).

Every crop profile is matched by name/category. When a crop is not in the
knowledge base a GENERIC profile is used and flagged with ``is_generic`` so the
UI can honestly label the guidance as general rather than pretending it is
crop-specific. No item ever claims a disease diagnosis.

The crop catalogue (backend/app/database/seed_crops.py) defines 18 crops:
Paddy (Rice), Wheat, Maize, Cotton, Sugarcane, Groundnut, Soybean, Chickpea,
Green Gram, Tomato, Chilli, Onion, Potato, Brinjal, Okra (Ladies Finger),
Cabbage, Sunflower and Mustard.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Canonical crop-cycle stages
# ---------------------------------------------------------------------------
STAGE_KEYS = [
    "land_prep",
    "seed_selection",
    "sowing",
    "germination",
    "vegetative",
    "flowering",
    "fruiting",
    "maturity",
    "harvest",
    "post_harvest",
]

STAGE_LABELS = {
    "land_prep": "Land Preparation",
    "seed_selection": "Seed Selection",
    "sowing": "Sowing / Planting",
    "germination": "Germination",
    "vegetative": "Vegetative Growth",
    "flowering": "Flowering",
    "fruiting": "Fruiting / Grain Fill",
    "maturity": "Maturity",
    "harvest": "Harvest",
    "post_harvest": "Post-Harvest",
}

STAGE_ICONS = {
    "land_prep": "fa-tractor",
    "seed_selection": "fa-seedling",
    "sowing": "fa-hand-holding-seedling",
    "germination": "fa-sprout",
    "vegetative": "fa-leaf",
    "flowering": "fa-spa",
    "fruiting": "fa-apple-whole",
    "maturity": "fa-wheat-awn",
    "harvest": "fa-scissors",
    "post_harvest": "fa-warehouse",
}

# Fraction of total growth duration at which each stage ends.
GENERIC_STAGE_BOUNDS: Dict[str, float] = {
    "land_prep": 0.02,
    "seed_selection": 0.03,
    "sowing": 0.06,
    "germination": 0.12,
    "vegetative": 0.42,
    "flowering": 0.58,
    "fruiting": 0.75,
    "maturity": 0.9,
    "harvest": 0.95,
    "post_harvest": 1.0,
}

# ---------------------------------------------------------------------------
# Generic activities (fallback for every stage / any crop)
# ---------------------------------------------------------------------------
GENERIC_ACTIVITIES: Dict[str, List[Dict[str, Any]]] = {
    "land_prep": [
        {
            "action": "Clear the field of stubble, weeds and last season's residue",
            "why": "A clean seedbed reduces pest shelter and weed competition",
            "when": "Now",
            "priority": "medium",
            "bucket": "now",
        },
        {
            "action": "Plough and level the field before sowing",
            "why": "Even tilth gives uniform germination and easier irrigation",
            "when": "This week",
            "priority": "high",
            "bucket": "this_week",
        },
    ],
    "seed_selection": [
        {
            "action": "Choose certified, disease-free seed of a variety suited to your season",
            "why": "Good seed is the cheapest way to protect yield",
            "when": "Now",
            "priority": "high",
            "bucket": "now",
        },
        {
            "action": "Do a germination test before sowing",
            "why": "Weak seed shows up late when it is hard to replant",
            "when": "This week",
            "priority": "medium",
            "bucket": "this_week",
        },
    ],
    "sowing": [
        {
            "action": "Sow at the recommended depth and spacing for the crop",
            "why": "Correct depth and spacing prevent seedling competition",
            "when": "Now",
            "priority": "high",
            "bucket": "now",
        },
        {
            "action": "Keep seedbed moisture even for the first week after sowing",
            "why": "Seed needs consistent moisture to begin germination",
            "when": "Now",
            "priority": "high",
            "bucket": "now",
        },
    ],
    "germination": [
        {
            "action": "Scout the field daily for even seedling emergence",
            "why": "Patchy germination needs early action, not a late surprise",
            "when": "Now",
            "priority": "high",
            "bucket": "now",
        },
        {
            "action": "Protect seedlings from birds and soil-born damping-off",
            "why": "Young seedlings are most fragile at this stage",
            "when": "This week",
            "priority": "medium",
            "bucket": "this_week",
        },
    ],
    "vegetative": [
        {
            "action": "Apply the main fertiliser dose matched to the crop's need",
            "why": "Leaves and stems grow fast and need nutrition now",
            "when": "This week",
            "priority": "high",
            "bucket": "this_week",
        },
        {
            "action": "Control weeds before they shade young plants",
            "why": "Weeds steal water, nutrients and sunlight",
            "when": "This week",
            "priority": "medium",
            "bucket": "this_week",
        },
        {
            "action": "Irrigate to keep moisture steady, avoid over-wetting",
            "why": "Even moisture builds strong roots and fewer stress symptoms",
            "when": "This week",
            "priority": "high",
            "bucket": "this_week",
        },
    ],
    "flowering": [
        {
            "action": "Watch water carefully - never let the crop dry out at flowering",
            "why": "Water stress at flowering severely cuts grain/fruit set",
            "when": "Now",
            "priority": "high",
            "bucket": "now",
        },
        {
            "action": "Minimise pesticide sprays during the peak flowering window",
            "why": "Protects pollinators that help fruit and grain form",
            "when": "This week",
            "priority": "medium",
            "bucket": "this_week",
        },
    ],
    "fruiting": [
        {
            "action": "Monitor fruit/grain fill and check moisture stays adequate",
            "why": "Fill is lost if the plant dries out or starves now",
            "when": "This week",
            "priority": "high",
            "bucket": "this_week",
        },
        {
            "action": "Watch for pest and borer damage - scout twice a week",
            "why": "Pests at fill cause direct yield loss",
            "when": "This week",
            "priority": "medium",
            "bucket": "this_week",
        },
    ],
    "maturity": [
        {
            "action": "Sample a few plants to check the crop is truly mature",
            "why": "Harvesting early or late both lose yield and quality",
            "when": "This week",
            "priority": "medium",
            "bucket": "this_week",
        },
        {
            "action": "Stop irrigation as the crop approaches harvest",
            "why": "A drier crop makes harvest and storage easier",
            "when": "This week",
            "priority": "low",
            "bucket": "this_week",
        },
    ],
    "harvest": [
        {
            "action": "Harvest at the right moisture stage for the crop",
            "why": "Timely harvest protects both quantity and quality",
            "when": "Now",
            "priority": "high",
            "bucket": "now",
        },
        {
            "action": "Arrange labour, tools and transport ahead of harvest",
            "why": "Harvest windows are narrow and weather-dependent",
            "when": "This week",
            "priority": "medium",
            "bucket": "this_week",
        },
    ],
    "post_harvest": [
        {
            "action": "Dry and store produce away from moisture and pests",
            "why": "A clean, dry store keeps the crop marketable longer",
            "when": "Now",
            "priority": "high",
            "bucket": "now",
        },
        {
            "action": "Record the harvest yield and note lessons for next season",
            "why": "Your own field history is the best planning tool",
            "when": "This week",
            "priority": "medium",
            "bucket": "this_week",
        },
    ],
}

# ---------------------------------------------------------------------------
# Generic "watch for this" items per stage (fallback)
# ---------------------------------------------------------------------------
GENERIC_WATCH: Dict[str, List[Dict[str, Any]]] = {
    "land_prep": [
        {
            "key": "water_logging",
            "title": "Waterlogging after heavy rain",
            "observe": "Standing water on the field for more than a day",
            "why": "Saturated soil chokes roots and delays seeding",
            "confirm": "Note if water stays after 24 hours and photos of the field",
            "next": "Improve drainage channels before sowing",
            "expert": "If the field stays wet for days after every rain",
            "severity": "medium",
        },
    ],
    "seed_selection": [
        {
            "key": "low_quality_seed",
            "title": "Suspect seed quality",
            "observe": "Off-colour, cracked or mixed seed; poor germination test",
            "why": "Weak seed carries disease and reduces final stand",
            "confirm": "A simple germination test count vs expected",
            "next": "Switch to certified seed before sowing",
            "expert": "If germination is far below the label claim",
            "severity": "medium",
        },
    ],
    "sowing": [
        {
            "key": "uneven_sowing",
            "title": "Uneven sowing depth",
            "observe": "Some seed too deep, some on the surface",
            "why": "Uneven depth means uneven emergence and thin stands",
            "confirm": "Dig up a few seeds and compare depth",
            "next": "Re-level and re-drill problem patches if seedlings fail",
            "expert": "If large areas fail to emerge",
            "severity": "medium",
        },
    ],
    "germination": [
        {
            "key": "patchy_germination",
            "title": "Patchy germination",
            "observe": "Gaps in the rows where seedlings did not emerge",
            "why": "Early gaps are hard to fill later",
            "confirm": "Count emerged seedlings in a few sample rows",
            "next": "Resow thin patches with fresh seed",
            "expert": "If germination is below ~70% across the field",
            "severity": "high",
        },
        {
            "key": "damping_off",
            "title": "Damping-off at the collar",
            "observe": "Young seedlings collapse at soil level, stems rot",
            "why": "Often a sign of over-moisture and fungal activity",
            "confirm": "Photos of the seedling base; note moisture levels",
            "next": "Reduce watering, avoid crowding, improve aeration",
            "expert": "If large patches collapse quickly",
            "severity": "high",
        },
    ],
    "vegetative": [
        {
            "key": "yellow_lower_leaves",
            "title": "Yellowing of older leaves",
            "observe": "Lower/older leaves yellow first, newer leaves stay green",
            "why": "Commonly nitrogen deficiency; also seen in transplant recovery",
            "confirm": "Which leaves are yellow, pattern across the field",
            "next": "Check fertiliser timing; consider a soil test",
            "expert": "If yellowing spreads fast or affects all leaves",
            "severity": "medium",
        },
        {
            "key": "leaf_eating_pests",
            "title": "Leaf-eating insects",
            "observe": "Holes in leaves, caterpillars, chewing marks",
            "why": "Vegetative leaf area drives later yield",
            "confirm": "Photos of damage and pest; note which part of leaf",
            "next": "Scout twice a week, identify the pest before acting",
            "expert": "If pest numbers are clearly above action threshold",
            "severity": "medium",
        },
    ],
    "flowering": [
        {
            "key": "flower_drop",
            "title": "Flower drop",
            "observe": "Flowers fall without setting fruit/grain",
            "why": "Often temperature stress, water stress or borers",
            "confirm": "Note timing, temperature and water status",
            "next": "Keep moisture steady and avoid stress at flowering",
            "expert": "If flower drop is widespread across the field",
            "severity": "high",
        },
    ],
    "fruiting": [
        {
            "key": "borer_damage",
            "title": "Fruit / grain borer damage",
            "observe": "Holes in fruit, bored stems, excreta near entry holes",
            "why": "Borers destroy marketable produce at the final stages",
            "confirm": "Photos of damage; break open one affected fruit",
            "next": "Remove affected parts, scout regularly",
            "expert": "If borer damage exceeds a few percent of plants",
            "severity": "high",
        },
        {
            "key": "poor_grain_fill",
            "title": "Poor grain / fruit fill",
            "observe": "Small or shrivelled grains, small fruits",
            "why": "Usually water, nutrition or pest stress during fill",
            "confirm": "Compare with healthy plants in the same field",
            "next": "Check moisture and nutrition; review the factors panel",
            "expert": "If the problem is uniform over the whole field",
            "severity": "medium",
        },
    ],
    "maturity": [
        {
            "key": "lodging",
            "title": "Lodging (plants falling over)",
            "observe": "Stems lean or fall under wind or weight",
            "why": "Lodged crop is hard to harvest and loses quality",
            "confirm": "Note wind events and fertiliser balance",
            "next": "Prioritise harvest of fallen areas first",
            "expert": "If a large area lodges",
            "severity": "medium",
        },
    ],
    "harvest": [
        {
            "key": "untimely_rain",
            "title": "Rain during harvest",
            "observe": "Wet crop, moisture re-entering dry seeds/grain",
            "why": "Wet harvest invites mould and storage loss",
            "confirm": "Forecast for the coming days",
            "next": "Bring forward or delay harvest to a dry window",
            "expert": "If stored produce starts heating or moulding",
            "severity": "high",
        },
    ],
    "post_harvest": [
        {
            "key": "storage_pests",
            "title": "Storage pests and mould",
            "observe": "Weevils, mould smell, heating bags",
            "why": "Poor storage destroys the value of a good harvest",
            "confirm": "Stored moisture and temperature checks",
            "next": "Dry fully, keep the store clean and sealed",
            "expert": "If stored produce is heavily infested",
            "severity": "medium",
        },
    ],
}

# ---------------------------------------------------------------------------
# Crop-specific knowledge (per-catalogue crop)
# ---------------------------------------------------------------------------
# Each entry overrides generic stage labels/bounds where a crop is genuinely
# different and adds crop-specific activities / watch items. Anything not
# listed falls back to GENERIC_ACTIVITIES / GENERIC_WATCH.
CROP_PROFILES: Dict[str, Dict[str, Any]] = {
    "paddy": {
        "match": ["paddy", "rice"],
        "label": "Paddy (Rice)",
        "bounds": {
            "land_prep": 0.03, "seed_selection": 0.04, "sowing": 0.08,
            "germination": 0.14, "vegetative": 0.45, "flowering": 0.62,
            "fruiting": 0.8, "maturity": 0.92, "harvest": 0.96, "post_harvest": 1.0,
        },
        "stage_labels": {"sowing": "Transplanting / Sowing", "fruiting": "Grain Fill"},
        "activities": {
            "land_prep": [
                {
                    "action": "Puddle the field to make the seedbed soft and watertight",
                    "why": "Paddy grows best in a well-puddled, level field",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
            "vegetative": [
                {
                    "action": "Keep a thin layer of standing water during tillering",
                    "why": "Rice tolerates shallow water and it suppresses weeds",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
                {
                    "action": "Apply nitrogen in split doses across tillering",
                    "why": "Split doses match uptake and reduce lodging",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
            "flowering": [
                {
                    "action": "Drain the field just before flowering, then re-flood",
                    "why": "Improves aeration at flowering and supports grain fill",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
            "maturity": [
                {
                    "action": "Drain the field 10-15 days before harvest",
                    "why": "Lets the soil dry enough for harvest machinery",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "germination": [
                {
                    "key": "stem_borer_moth",
                    "title": "Stem borer (dead hearts)",
                    "observe": "Central leaf dries (dead heart) in young plants",
                    "why": "Borer attacks cut tillers and reduce final panicle count",
                    "confirm": "Pull affected tiller and check for borer larva/egg mass",
                    "next": "Remove egg masses; scout after transplanting recovery",
                    "expert": "If dead hearts exceed the local action threshold",
                    "severity": "high",
                },
            ],
            "vegetative": [
                {
                    "key": "bacterial_leaf_blast",
                    "title": "Leaf blast brown spots on leaves",
                    "observe": "Spindle-shaped lesions with grey-green centre",
                    "why": "Blast reduces leaf area and later yield",
                    "confirm": "Photos of lesions, note weather humidity",
                    "next": "Balance nitrogen; keep water regime steady",
                    "expert": "If lesions spread to many leaves quickly",
                    "severity": "medium",
                },
            ],
        },
    },
    "wheat": {
        "match": ["wheat"],
        "label": "Wheat",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.03, "sowing": 0.06,
            "germination": 0.12, "vegetative": 0.45, "flowering": 0.6,
            "fruiting": 0.8, "maturity": 0.93, "harvest": 0.96, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Grain Development"},
        "activities": {
            "land_prep": [
                {
                    "action": "Prepare a fine, even seedbed for good drill sowing",
                    "why": "Wheat wants a firm, clod-free bed",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
            "vegetative": [
                {
                    "action": "Apply nitrogen at crown-root stage",
                    "why": "Feeds tillering which sets final yield potential",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
                {
                    "action": "Irrigate at the critical crown-root stage",
                    "why": "This is wheat's most water-sensitive phase",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
            ],
            "flowering": [
                {
                    "action": "Irrigate at heading and flowering",
                    "why": "Protects grain number and weight",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
        },
        "watch": {
            "vegetative": [
                {
                    "key": "yellow_rust",
                    "title": "Yellow rust pustules on leaves",
                    "observe": "Yellow powdery stripes on upper leaves",
                    "why": "Rust spreads fast in cool, humid weather and cuts yield",
                    "confirm": "Photos of pustule stripes; note if on flag leaf",
                    "next": "Scout daily; act early with a recommended fungicide",
                    "expert": "If rust reaches the flag leaf",
                    "severity": "high",
                },
            ],
            "flowering": [
                {
                    "key": "aphid_clusters",
                    "title": "Aphid clusters on ears",
                    "observe": "Black or green aphids on the head after flowering",
                    "why": "Heavy aphid load means sticky, low-quality grain",
                    "confirm": "Check ear bracts and note counts",
                    "next": "Wash or treat if numbers are high; check ladybirds first",
                    "expert": "If honeydew and sooty mould build up",
                    "severity": "medium",
                },
            ],
        },
    },
    "maize": {
        "match": ["maize", "corn"],
        "label": "Maize",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.07,
            "germination": 0.13, "vegetative": 0.45, "flowering": 0.6,
            "fruiting": 0.78, "maturity": 0.94, "harvest": 0.97, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Cob Fill", "maturity": "Grain Dry-down"},
        "activities": {
            "sowing": [
                {
                    "action": "Sow at proper spacing after soil warms up",
                    "why": "Cold, wet soil gives poor 'mosaic' germination",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
            "vegetative": [
                {
                    "action": "Top-dress nitrogen at knee-high stage",
                    "why": "Maize is a heavy nitrogen feeder at this stage",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
                {
                    "action": "Earthing up ridges",
                    "why": "Gives the plant support and improves water use",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
            "flowering": [
                {
                    "action": "Irrigate at tasselling and silking",
                    "why": "Water stress at silking is the biggest single yield cut",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
        },
        "watch": {
            "flowering": [
                {
                    "key": "fall_armyworm",
                    "title": "Fall armyworm whorl damage",
                    "observe": "Saw-dust like frass and ragged feeding in the whorl",
                    "why": "Armyworm destroys the growing point if missed early",
                    "confirm": "Peel the whorl, look for small larvae",
                    "next": "Act early with a recommended control; repeat scouting",
                    "expert": "If fresh whorl damage keeps appearing",
                    "severity": "critical",
                },
            ],
        },
    },
    "cotton": {
        "match": ["cotton"],
        "label": "Cotton",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.03, "sowing": 0.05,
            "germination": 0.1, "vegetative": 0.35, "flowering": 0.55,
            "fruiting": 0.78, "maturity": 0.92, "harvest": 0.96, "post_harvest": 1.0,
        },
        "stage_labels": {"flowering": "Flowering & Boll Formation", "fruiting": "Boll Development"},
        "activities": {
            "vegetative": [
                {
                    "action": "Monitor plant square formation",
                    "why": "Square count early predicts the final boll load",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
            "flowering": [
                {
                    "action": "Scout for bollworms weekly - do not spray on a fixed calendar",
                    "why": "Spraying only when thresholds are hit keeps costs and resistance down",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
            ],
            "harvest": [
                {
                    "action": "Pick bolls at the right maturity, skip stain-damaged ones",
                    "why": "Clean, dry lint is worth significantly more",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
        },
        "watch": {
            "flowering": [
                {
                    "key": "pink_bollworm",
                    "title": "Pink bollworm damage",
                    "observe": "Burnt, brown locule / 'rosette' flowers, exit holes in bolls",
                    "why": "Bollworm destroys lint inside the boll",
                    "confirm": "Cut open affected bolls and look for larvae",
                    "next": "Remove infested bolls; follow pest advisory",
                    "expert": "If lint damage appears in many bolls",
                    "severity": "critical",
                },
                {
                    "key": "sucking_pests",
                    "title": "Sucking pests (jassids, aphids, whitefly)",
                    "observe": "Curled, yellowing leaves and sticky honeydew",
                    "why": "Heavy sucking pressure stunts plants and spreads virus",
                    "confirm": "Count on lower leaf surfaces, check whitefly",
                    "next": "Use threshold-based spraying, conserve predators",
                    "expert": "If whitefly populations are very high",
                    "severity": "medium",
                },
            ],
        },
    },
    "sugarcane": {
        "match": ["sugarcane", "sugar cane"],
        "label": "Sugarcane",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.07,
            "germination": 0.15, "vegetative": 0.3, "flowering": 0.55,
            "fruiting": 0.85, "maturity": 0.98, "harvest": 0.99, "post_harvest": 1.0,
        },
        "stage_labels": {"sowing": "Setts Planting", "fruiting": "Cane Growth & Juice Accumulation", "post_harvest": "Ratoon / Second Crop"},
        "activities": {
            "sowing": [
                {
                    "action": "Plant healthy cane setts with good buds",
                    "why": "Cane quality comes from the sett",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
            "vegetative": [
                {
                    "action": "Earthing up and trash-mulching between rows",
                    "why": "Conserves moisture and suppresses weeds over the long cycle",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
            "fruiting": [
                {
                    "action": "Ensure steady irrigation through the long growth phase",
                    "why": "Sugarcane is thirsty over its long cycle",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "germination": [
                {
                    "key": "sett_rot",
                    "title": "Sett rot",
                    "observe": "Setts fail to sprout or sprouts die back",
                    "why": "Poor setts or over-moisture rot the seed piece",
                    "confirm": "Dig out unsprouted setts and check",
                    "next": "Improve drainage; use certified disease-free setts",
                    "expert": "If more than ~20% of setts fail",
                    "severity": "medium",
                },
            ],
            "vegetative": [
                {
                    "key": "shoot_borer",
                    "title": "Shoot borer (dead heart)",
                    "observe": "Central shoot dead/dry, small holes in young cane",
                    "why": "Borer kills tillers early in the long cycle",
                    "confirm": "Check shoot bases for borer entry",
                    "next": "Remove and destroy affected shoots, follow advisory",
                    "expert": "If dead hearts are common",
                    "severity": "high",
                },
            ],
        },
    },
    "groundnut": {
        "match": ["groundnut", "peanut"],
        "label": "Groundnut",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.07,
            "germination": 0.12, "vegetative": 0.35, "flowering": 0.5,
            "fruiting": 0.7, "maturity": 0.92, "harvest": 0.96, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Pegging & Pod Formation"},
        "activities": {
            "flowering": [
                {
                    "action": "Ensure pegs can reach the soil - keep soil loose and moist",
                    "why": "Pegs that cannot reach soil do not form pods",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
            "fruiting": [
                {
                    "action": "Avoid deep tilling during pod fill",
                    "why": "Deep tillage disturbs pods and cuts yield",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "flowering": [
                {
                    "key": "groundnut_rust_tikka",
                    "title": "Tikka / early leaf spot",
                    "observe": "Brown spots with yellow halo on older leaves",
                    "why": "Leaf spots defoliate and starve the pegging crop",
                    "confirm": "Photos of spotting pattern on lower vs upper leaves",
                    "next": "Spray a recommended fungicide at symptom onset",
                    "expert": "If defoliation is clearly advancing",
                    "severity": "medium",
                },
            ],
        },
    },
    "soybean": {
        "match": ["soybean", "soyabean", "soya"],
        "label": "Soybean",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.07,
            "germination": 0.12, "vegetative": 0.35, "flowering": 0.55,
            "fruiting": 0.75, "maturity": 0.9, "harvest": 0.95, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Pod Fill"},
        "activities": {
            "land_prep": [
                {
                    "action": "Keep tillage light to protect soil moisture",
                    "why": "Soybean needs moisture conserved for an even stand",
                    "when": "Now",
                    "priority": "medium",
                    "bucket": "now",
                },
            ],
            "vegetative": [
                {
                    "action": "Watch nodulation on roots",
                    "why": "Healthy nodules mean the plant fixes its own nitrogen",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "flowering": [
                {
                    "key": "yellow_mosaic",
                    "title": "Yellow mosaic (yellow patches on leaves)",
                    "observe": "Irregular bright yellow patches, often on top leaves",
                    "why": "Whitefly-spread virus stunts growth and pods",
                    "confirm": "Note pattern; check whiteflies underneath leaves",
                    "next": "Control whitefly early; remove affected plants",
                    "expert": "If mosaic plants are spread across the field",
                    "severity": "high",
                },
            ],
        },
    },
    "chickpea": {
        "match": ["chickpea", "chana", "gram"],
        "label": "Chickpea",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.07,
            "germination": 0.12, "vegetative": 0.35, "flowering": 0.5,
            "fruiting": 0.7, "maturity": 0.9, "harvest": 0.95, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Pod Formation"},
        "activities": {
            "vegetative": [
                {
                    "action": "Avoid excess irrigation during vegetative phase",
                    "why": "Chickpea prefers less water than most crops",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
            "flowering": [
                {
                    "action": "Time one critical irrigation at flowering",
                    "why": "The single most yield-protecting water for chickpea",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
        },
        "watch": {
            "vegetative": [
                {
                    "key": "wilt",
                    "title": "Fusarium wilt",
                    "observe": "Sudden wilting and yellowing of a plant or row",
                    "why": "Wilt is soil-borne and plants die quickly",
                    "confirm": "Check plant base for browning; note the pattern",
                    "next": "Remove dead plants; rotate the next crop",
                    "expert": "If wilt patches appear in several places",
                    "severity": "critical",
                },
            ],
        },
    },
    "green_gram": {
        "match": ["green gram", "moong", "mung"],
        "label": "Green Gram",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.08,
            "germination": 0.14, "vegetative": 0.35, "flowering": 0.55,
            "fruiting": 0.78, "maturity": 0.9, "harvest": 0.95, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Pod Development"},
        "activities": {
            "sowing": [
                {
                    "action": "Sow promptly after the season's first rains",
                    "why": "Green gram is a quick crop that likes early moisture",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
        },
        "watch": {
            "flowering": [
                {
                    "key": "yellow_mosaic_gram",
                    "title": "Yellow mosaic on leaves",
                    "observe": "Bright yellow patches and curling on young leaves",
                    "why": "Whitefly-spread virus sickens this fast crop",
                    "confirm": "Check for whitefly; note spread pattern",
                    "next": "Manage whitefly early, remove badly affected plants",
                    "expert": "If mosaic spreads through the crop",
                    "severity": "high",
                },
            ],
        },
    },
    "tomato": {
        "match": ["tomato"],
        "label": "Tomato",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.07,
            "germination": 0.12, "vegetative": 0.35, "flowering": 0.5,
            "fruiting": 0.75, "maturity": 0.9, "harvest": 0.95, "post_harvest": 1.0,
        },
        "stage_labels": {"sowing": "Seedling Transplanting", "fruiting": "Fruit Setting & Development"},
        "activities": {
            "sowing": [
                {
                    "action": "Transplant healthy seedlings at the right spacing",
                    "why": "Staking and spacing keep air moving and disease low",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
            "vegetative": [
                {
                    "action": "Stake and prune suckers as plants grow",
                    "why": "Air flow cuts fungal pressure and improves ripening",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
            "fruiting": [
                {
                    "action": "Maintain steady moisture to prevent blossom-end rot",
                    "why": "Irregular watering is the main cause of blossom-end rot",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "vegetative": [
                {
                    "key": "late_blight",
                    "title": "Late blight",
                    "observe": "Water-soaked dark patches that turn brown and rot leaves",
                    "why": "Blight can wipe a tomato crop within days in humid weather",
                    "confirm": "Photos of patches and weather humidity",
                    "next": "Act fast with a recommended fungicide",
                    "expert": "If spots spread to stems and fruits",
                    "severity": "critical",
                },
            ],
            "fruiting": [
                {
                    "key": "blossom_end_rot",
                    "title": "Blossom-end rot",
                    "observe": "Sunken, dark leathery patch at the fruit's bottom",
                    "why": "A calcium/water balance issue, not a disease",
                    "confirm": "Note watering regularity and variety",
                    "next": "Water evenly, add mulch, consider calcium amendment",
                    "expert": "If it affects a large share of fruit",
                    "severity": "medium",
                },
            ],
        },
    },
    "chilli": {
        "match": ["chilli", "chili", "pepper"],
        "label": "Chilli",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.07,
            "germination": 0.13, "vegetative": 0.35, "flowering": 0.52,
            "fruiting": 0.78, "maturity": 0.9, "harvest": 0.95, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Fruit Development & Multiple Picking"},
        "activities": {
            "fruiting": [
                {
                    "action": "Harvest in pickings through the season",
                    "why": "Chilli fruits bounce back over many picks",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "vegetative": [
                {
                    "key": "thrips_bugs",
                    "title": "Thrips and mite curling",
                    "observe": "Curled, silvery leaves with tiny insects inside",
                    "why": "Thrips also spread the viral 'leaf curl'",
                    "confirm": "Hold a curled leaf up to light and look for tiny insects",
                    "next": "Use threshold-based spraying, remove infested tips",
                    "expert": "If curling spreads to most new leaves",
                    "severity": "high",
                },
            ],
        },
    },
    "onion": {
        "match": ["onion"],
        "label": "Onion",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.05, "sowing": 0.08,
            "germination": 0.13, "vegetative": 0.5, "flowering": 0.65,
            "fruiting": 0.85, "maturity": 0.95, "harvest": 0.97, "post_harvest": 1.0,
        },
        "stage_labels": {"sowing": "Transplanting / Bulb-set", "fruiting": "Bulb Development"},
        "activities": {
            "vegetative": [
                {
                    "action": "Top-dress nitrogen before bulb expansion",
                    "why": "Feeds leaf growth that feeds the bulb",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
            ],
            "fruiting": [
                {
                    "action": "Reduce water as bulbs mature",
                    "why": "Drier conditions help bulbs store well",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
            "harvest": [
                {
                    "action": "Harvest when tops fall over and dry",
                    "why": "A sign the bulb has finished growing",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "vegetative": [
                {
                    "key": "thrips_onion",
                    "title": "Onion thrips",
                    "observe": "Silver-white streaks and curling of onion spears",
                    "why": "Thrips slow bulb growth through the season",
                    "confirm": "Count small thrips between the outer leaves",
                    "next": "Threshold-based spray, good weed control",
                    "expert": "If streaks appear on most plants",
                    "severity": "medium",
                },
            ],
            "fruiting": [
                {
                    "key": "purple_blotch",
                    "title": "Purple blotch on leaves",
                    "observe": "Purple-brown oval spots that yellow leaf tips",
                    "why": "The disease reduces leaf area feeding the bulb",
                    "confirm": "Photos of spots, note humidity",
                    "next": "Improve airflow, use a recommended fungicide",
                    "expert": "If leaf tips yellow over large areas",
                    "severity": "medium",
                },
            ],
        },
    },
    "potato": {
        "match": ["potato"],
        "label": "Potato",
        "bounds": {
            "land_prep": 0.03, "seed_selection": 0.05, "sowing": 0.08,
            "germination": 0.13, "vegetative": 0.4, "flowering": 0.55,
            "fruiting": 0.8, "maturity": 0.9, "harvest": 0.95, "post_harvest": 1.0,
        },
        "stage_labels": {"sowing": "Tuber Planting", "fruiting": "Tuber Bulking"},
        "activities": {
            "sowing": [
                {
                    "action": "Plant well-sprouted, certified seed tubers",
                    "why": "Sprouted healthy seed gives an even, early stand",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
            "fruiting": [
                {
                    "action": "Keep moisture steady during tuber bulking",
                    "why": "Irregular water causes knobby, cracked tubers",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
            ],
            "harvest": [
                {
                    "action": "Harvest after vines senesce, dry tubers before storage",
                    "why": "Wet, bruised tubers rot in storage",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "vegetative": [
                {
                    "key": "late_blight_potato",
                    "title": "Late blight",
                    "observe": "Dark water-soaked leaf patches that spread fast",
                    "why": "Blight can destroy foliage and tubers in wet spells",
                    "confirm": "Photos of patches; check lower leaves",
                    "next": "Act early with a recommended fungicide",
                    "expert": "If blight reaches stems",
                    "severity": "critical",
                },
            ],
            "fruiting": [
                {
                    "key": "tuber_cracks",
                    "title": "Knobby / cracked tubers",
                    "observe": "Misshapen or cracked tubers at harvest",
                    "why": "Usually from uneven watering during bulking",
                    "confirm": "Note watering consistency through the season",
                    "next": "Mulch and irrigate evenly in future crops",
                    "expert": "If cracks are widespread",
                    "severity": "medium",
                },
            ],
        },
    },
    "brinjal": {
        "match": ["brinjal", "eggplant"],
        "label": "Brinjal",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.05, "sowing": 0.08,
            "germination": 0.14, "vegetative": 0.36, "flowering": 0.52,
            "fruiting": 0.8, "maturity": 0.92, "harvest": 0.96, "post_harvest": 1.0,
        },
        "stage_labels": {"sowing": "Seedling Transplanting"},
        "activities": {
            "sowing": [
                {
                    "action": "Transplant healthy seedlings with proper spacing",
                    "why": "Long-season crop needs room to keep fruiting",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
            "fruiting": [
                {
                    "action": "Harvest fruit regularly to keep the plant fruiting",
                    "why": "Picking regularly extends the season",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "fruiting": [
                {
                    "key": "shoot_fruit_borer",
                    "title": "Shoot and fruit borer",
                    "observe": "Wilting shoots and bore holes with frass in fruit",
                    "why": "Borer makes fruit unmarketable",
                    "confirm": "Cut open a fruit; pull affected shoots",
                    "next": "Remove infested shoots and fruit; scout weekly",
                    "expert": "If borer is found in many plants",
                    "severity": "high",
                },
            ],
        },
    },
    "okra": {
        "match": ["okra", "ladies finger", "lady finger"],
        "label": "Okra",
        "bounds": {
            "land_prep": 0.03, "seed_selection": 0.05, "sowing": 0.09,
            "germination": 0.15, "vegetative": 0.35, "flowering": 0.55,
            "fruiting": 0.8, "maturity": 0.92, "harvest": 0.96, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Pod Harvesting"},
        "activities": {
            "fruiting": [
                {
                    "action": "Harvest pods every 1-2 days at finger size",
                    "why": "Quick crop - pods become fibrous if left two days",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
        },
        "watch": {
            "vegetative": [
                {
                    "key": "yellow_mosaic_okra",
                    "title": "Yellow vein mosaic",
                    "observe": "Net-veined, yellowed, stunted plants",
                    "why": "Virus spread by whitefly stunts the quick crop",
                    "confirm": "Note the vein-clearing pattern and whitefly",
                    "next": "Manage whitefly early; powdery-feeding keep clean",
                    "expert": "If mosaic plants are widespread",
                    "severity": "high",
                },
            ],
            "fruiting": [
                {
                    "key": "fruit_borer_okra",
                    "title": "Fruit borer holes",
                    "observe": "Small holes with frass in young pods",
                    "why": "Bored pods are unsaleable",
                    "confirm": "Open affected pods",
                    "next": "Pick and destroy affected pods early",
                    "expert": "If borer is in many pods",
                    "severity": "medium",
                },
            ],
        },
    },
    "cabbage": {
        "match": ["cabbage"],
        "label": "Cabbage",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.05, "sowing": 0.08,
            "germination": 0.15, "vegetative": 0.4, "flowering": 0.6,
            "fruiting": 0.85, "maturity": 0.95, "harvest": 0.97, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Head Formation"},
        "activities": {
            "fruiting": [
                {
                    "action": "Watch soil moisture during head formation",
                    "why": "Irregular water causes cracked heads",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
                {
                    "action": "Top-dress nitrogen during head formation",
                    "why": "Heads swell fast and need steady feeding",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
            "harvest": [
                {
                    "action": "Harvest firm heads with a clean cut",
                    "why": "Firm heads with good keeping quality earn more",
                    "when": "This week",
                    "priority": "high",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "vegetative": [
                {
                    "key": "diamondback_moth",
                    "title": "Diamondback moth larvae",
                    "observe": "Small green caterpillars and shot-holes in leaves",
                    "why": "Larvae live inside the head and ruin it",
                    "confirm": "Check the leaf base of new leaves",
                    "next": "Scout often, act early, rotate controls",
                    "expert": "If many hearts are affected",
                    "severity": "medium",
                },
            ],
        },
    },
    "sunflower": {
        "match": ["sunflower"],
        "label": "Sunflower",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.07,
            "germination": 0.13, "vegetative": 0.38, "flowering": 0.5,
            "fruiting": 0.75, "maturity": 0.92, "harvest": 0.96, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Seed Fill"},
        "activities": {
            "flowering": [
                {
                    "action": "Put beehives near the field for pollination",
                    "why": "Bee activity lifts seed set on the head",
                    "when": "This week",
                    "priority": "medium",
                    "bucket": "this_week",
                },
            ],
        },
        "watch": {
            "flowering": [
                {
                    "key": "head_borer",
                    "title": "Head borer on the flower",
                    "observe": "Larvae feeding inside the flower head",
                    "why": "Borer eats the maturing seeds",
                    "confirm": "Peel back the back of the head gently",
                    "next": "Remove and dispose affected heads",
                    "expert": "If several heads are affected",
                    "severity": "high",
                },
            ],
        },
    },
    "mustard": {
        "match": ["mustard", "rapeseed", "raya"],
        "label": "Mustard",
        "bounds": {
            "land_prep": 0.02, "seed_selection": 0.04, "sowing": 0.07,
            "germination": 0.13, "vegetative": 0.35, "flowering": 0.5,
            "fruiting": 0.7, "maturity": 0.92, "harvest": 0.96, "post_harvest": 1.0,
        },
        "stage_labels": {"fruiting": "Pod / Siliqua Development"},
        "activities": {
            "land_prep": [
                {
                    "action": "Sow early in the season for a strong start",
                    "why": "Early sowing avoids powdery mildew and aphid peaks",
                    "when": "Now",
                    "priority": "high",
                    "bucket": "now",
                },
            ],
        },
        "watch": {
            "flowering": [
                {
                    "key": "aphid_pod",
                    "title": "Aphids on inflorescence",
                    "observe": "Aphid clusters and sticky honeydew on flowers and pods",
                    "why": "Aphids sap the crop and cause poor seed set",
                    "confirm": "Count aphids on young pods; check natural enemies",
                    "next": "Spray only if aphids exceed threshold; preserve ladybirds",
                    "expert": "If honeydew and sooty mould build up",
                    "severity": "medium",
                },
            ],
        },
    },
}

# Default stage bounds if a profile does not override them.
_DEFAULT_BOUNDS = dict(GENERIC_STAGE_BOUNDS)

# ---------------------------------------------------------------------------
# Symptom catalogue for "Check Crop Health"
# ---------------------------------------------------------------------------
# code -> human label + how to record it
SYMPTOM_CATALOGUE: List[Dict[str, str]] = [
    {"code": "yellowing_lower", "label": "Yellowing of older / lower leaves", "tip": "Older leaves, not new growth"},
    {"code": "wilting", "label": "Wilting", "tip": "Leaves droop even after watering"},
    {"code": "leaf_spots", "label": "Spots or lesions on leaves", "tip": "Dark, pale or ringed spots"},
    {"code": "holes_leaves", "label": "Holes / chewing in leaves", "tip": "Evidence of leaf-eating insects"},
    {"code": "borer_holes", "label": "Bored stems, shoots or fruit", "tip": "Small holes, frass, dead shoots"},
    {"code": "stunted_growth", "label": "Stunted / slow growth", "tip": "Plants smaller than expected"},
    {"code": "poor_stand", "label": "Poor germination / gaps in rows", "tip": "Seedlings failed to emerge"},
    {"code": "flower_drop", "label": "Flowers falling without setting", "tip": "Few flowers become fruit/grain"},
    {"code": "water_stress", "label": "Signs of water stress", "tip": "Dry, crispy or folded leaves"},
    {"code": "lodging", "label": "Plants falling / leaning over", "tip": "Stems bent or flattened"},
    {"code": "discoloured_fruit", "label": "Discoloured or rotted fruit", "tip": "Soft, sunken or dark patches"},
    {"code": "virus_symptoms", "label": "Mottling / mosaic / curling", "tip": "Irregular leaf patterns or curl"},
]

# symptom code -> structured assessment (never a diagnosis)
SYMPTOM_ASSESSMENTS: Dict[str, Dict[str, Any]] = {
    "yellowing_lower": {
        "concern": "Nitrogen imbalance is the most common cause, but stress from water, pests or disease can look the same.",
        "action": "Check whether the yellowing is on older leaves only. Review fertiliser timing and consider a soil test.",
        "follow_up": "Re-check in 4-5 days. If yellowing moves to new leaves, note it in a follow-up check.",
        "status": "watch",
    },
    "wilting": {
        "concern": "Could be water stress or root / stem damage. Continuous wilting after watering needs attention.",
        "action": "Check soil moisture at root depth and look at the stem base for browning or borer holes.",
        "follow_up": "Re-check the next day. If the plant recovers overnight, adjust watering.",
        "status": "attention",
    },
    "leaf_spots": {
        "concern": "Possible fungal or bacterial leaf spots. Many are cosmetic, some spread quickly in humid weather.",
        "action": "Photograph the spots, note whether they are spreading, and keep the foliage dry.",
        "follow_up": "Re-check in 3-4 days. If spots spread to stems or fruit, contact an expert.",
        "status": "watch",
    },
    "holes_leaves": {
        "concern": "Leaf-eating insects are present. Low numbers are often fine; dense damage is not.",
        "action": "Scout the underside of leaves and around the crop. Identify the pest before any action.",
        "follow_up": "Scout twice over the next week and re-check the damage level.",
        "status": "attention",
    },
    "borer_holes": {
        "concern": "Stem / shoot / fruit borers are a real yield risk at any stage after establishment.",
        "action": "Remove and destroy affected shoots or fruit. Mark the affected area for repeat checks.",
        "follow_up": "Scout weekly and act if fresh holes keep appearing.",
        "status": "critical",
    },
    "stunted_growth": {
        "concern": "Slow growth usually points to water, nutrition, compaction or a weak start.",
        "action": "Compare with the crop's expected stage and check the health factors panel (moisture, soil, weather).",
        "follow_up": "Re-check in a week after improving the most likely factor.",
        "status": "watch",
    },
    "poor_stand": {
        "concern": "Patchy stands can be seed, water, or soil issues from sowing.",
        "action": "Dig up a few skipped spots and check seed depth and soil moisture.",
        "follow_up": "Decide within the first two weeks whether to re-sow thin patches.",
        "status": "attention",
    },
    "flower_drop": {
        "concern": "Flower drop is commonly linked to water, temperature or borer stress around flowering.",
        "action": "Keep the soil moisture steady and avoid rough disturbance during flowering.",
        "follow_up": "Re-check at the next flowering flush.",
        "status": "attention",
    },
    "water_stress": {
        "concern": "The crop is short of water at a sensitive time, which cuts yield fast.",
        "action": "Irrigate soon and re-check the soil moisture schedule.",
        "follow_up": "Check the crop's recovery in 2-3 days.",
        "status": "critical",
    },
    "lodging": {
        "concern": "Fallen plants are hard to harvest and may rot in contact with soil.",
        "action": "Prioritise harvest of lodged areas first; reduce nitrogen in future.",
        "follow_up": "Harvest the affected area as soon as the crop is ready.",
        "status": "attention",
    },
    "discoloured_fruit": {
        "concern": "Fruit damage can be disease, sun-scald or a nutrient issue like blossom-end rot.",
        "action": "Photograph the fruit and note the pattern (bottom end, side, top).",
        "follow_up": "Check neighbouring plants for the same symptom.",
        "status": "attention",
    },
    "virus_symptoms": {
        "concern": "Mosaic, mottling and curling suggest a possible viral issue often spread by insects.",
        "action": "Record the pattern and check for the insect vector (usually whitefly or aphids).",
        "follow_up": "Control the vector early; verify before removing plants.",
        "status": "attention",
    },
}

SEVERITY_RANK = {"normal": 0, "watch": 1, "attention": 2, "critical": 3}
SEVERITY_LABELS = {
    "normal": "Looking healthy",
    "watch": "Watch closely",
    "attention": "Needs attention",
    "critical": "Act now",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> date:
    return date.today()


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _fmt(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def normalize_crop_name(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def get_crop_profile(name: Optional[str]) -> Tuple[Dict[str, Any], bool]:
    """Return (profile, is_generic). Matches by crop name keywords."""
    normalized = normalize_crop_name(name)
    for key, profile in CROP_PROFILES.items():
        for token in profile.get("match", []):
            if token in normalized:
                return profile, False
    return {"label": name or "This crop", "bounds": dict(GENERIC_STAGE_BOUNDS)}, True


def stage_bounds(profile: Dict[str, Any]) -> Dict[str, float]:
    return dict(_DEFAULT_BOUNDS, **(profile.get("bounds") or {}))


def stage_list(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    bounds = stage_bounds(profile)
    labels = dict(STAGE_LABELS, **(profile.get("stage_labels") or {}))
    result = []
    for key in STAGE_KEYS:
        result.append({
            "key": key,
            "label": labels.get(key, STAGE_LABELS[key]),
            "icon": STAGE_ICONS[key],
            "end_pct": bounds[key],
        })
    return result


def _stage_start_pct(bounds: Dict[str, float], key: str) -> float:
    idx = STAGE_KEYS.index(key)
    if idx == 0:
        return 0.0
    return bounds.get(STAGE_KEYS[idx - 1], 0.0)


def compute_stage_state(
    profile: Dict[str, Any],
    days_since_sowing: float,
    total_days: Optional[float],
) -> str:
    """Map an elapsed time onto the stage the crop is in."""
    if total_days is None or total_days <= 0:
        return "vegetative"
    fraction = max(0.0, min(1.0, days_since_sowing / total_days))
    bounds = stage_bounds(profile)
    for key in STAGE_KEYS:
        if fraction <= bounds[key]:
            return key
    return STAGE_KEYS[-1]


def build_cycle(
    crop_name: Optional[str],
    days_since_sowing: Optional[int],
    total_days: Optional[float],
    current_stage: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a full crop-cycle timeline with per-stage dates and state.
    Used by the Crop Health overview.
    """
    profile, is_generic = get_crop_profile(crop_name)
    bounds = stage_bounds(profile)
    labels = dict(STAGE_LABELS, **(profile.get("stage_labels") or {}))
    stages = []
    today = _now()

    effective_days = int(days_since_sowing) if days_since_sowing is not None else 0
    effective_state = compute_stage_state(profile, float(effective_days), total_days)
    if current_stage and current_stage in STAGE_KEYS:
        effective_state = current_stage

    current_idx = STAGE_KEYS.index(effective_state) if effective_state in STAGE_KEYS else 6
    current_pct = bounds.get(effective_state, 0.5)
    sown = today - timedelta(days=effective_days)

    for idx, key in enumerate(STAGE_KEYS):
        start_pct = _stage_start_pct(bounds, key)
        end_pct = bounds[key]
        if total_days:
            start_day = int(round(start_pct * total_days))
            end_day = int(round(end_pct * total_days))
        else:
            start_day, end_day = None, None
        state = "completed" if idx < current_idx else ("current" if idx == current_idx else "upcoming")
        stages.append({
            "key": key,
            "label": labels[key],
            "icon": STAGE_ICONS[key],
            "index": idx,
            "state": state,
            "start_day": start_day,
            "end_day": end_day,
            "start_date": _fmt(sown + timedelta(days=start_day)) if (total_days and start_day is not None) else None,
            "end_date": _fmt(sown + timedelta(days=end_day)) if (total_days and end_day is not None) else None,
        })

    overall = round(current_pct * 100)
    next_stage = None
    if current_idx < len(STAGE_KEYS) - 1:
        next_stage = {
            "key": STAGE_KEYS[current_idx + 1],
            "label": labels[STAGE_KEYS[current_idx + 1]],
        }

    return {
        "crop": crop_name or "This crop",
        "crop_name_slug": normalize_crop_name(crop_name or ""),
        "is_generic": is_generic,
        "total_days": total_days,
        "days_since_sowing": effective_days,
        "current_stage": effective_state,
        "current_label": labels.get(effective_state, STAGE_LABELS.get(effective_state, effective_state)),
        "current_icon": STAGE_ICONS.get(effective_state, "fa-leaf"),
        "next_stage": next_stage,
        "overall_pct": overall,
        "stages": stages,
    }


# ---------------------------------------------------------------------------
# Plan builder
# ---------------------------------------------------------------------------


def _activity_items(profile: Dict[str, Any], stage: str) -> List[Dict[str, Any]]:
    acts = profile.get("activities") or {}
    acts = dict(GENERIC_ACTIVITIES, **acts)
    return acts.get(stage, [])


def plan_bucket_key(bucket: str) -> str:
    return bucket if bucket in ("now", "this_week", "coming_up") else "this_week"


def build_plan(
    crop_name: Optional[str],
    stage: str,
    days_since_sowing: Optional[int],
    total_days: Optional[float],
    factors: Optional[Dict[str, Any]] = None,
    weather: Optional[Dict[str, Any]] = None,
    tasks_due: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build 'Your Crop Health Plan' grouped into Now / This Week / Coming Up.
    Each item keeps: action, why, when, priority, stage, bucket, category,
    plus optional source ('data' when driven by real field/weather data).
    """
    profile, is_generic = get_crop_profile(crop_name)
    factors = factors or {}
    weather = weather or {}
    tasks_due = tasks_due or []
    now_bucket: List[Dict[str, Any]] = []
    week_bucket: List[Dict[str, Any]] = []
    coming_bucket: List[Dict[str, Any]] = []

    stages_map = {s["key"]: s for s in stage_list(profile)}
    stage_label = stages_map.get(stage, {}).get("label", STAGE_LABELS.get(stage, stage))

    # 1. Stage activities with an explicit bucket from the knowledge base.
    for act in _activity_items(profile, stage):
        bucket = plan_bucket_key(act.get("bucket", "this_week"))
        item = {
            "action": act["action"],
            "why": act["why"],
            "when": act["when"],
            "priority": act.get("priority", "medium"),
            "stage": stage,
            "stage_label": stage_label,
            "bucket": bucket,
            "source": "stage",
            "category": f"{crop_name or 'Crop'} - {stage_label}",
            "can_track": True,
        }
        (now_bucket if bucket == "now" else week_bucket if bucket == "this_week" else coming_bucket).append(item)

    # 2. Data-driven items from real field/weather data.
    water = factors.get("water") or {}
    water_status = water.get("status") or "ok"
    soil = factors.get("soil") or {}
    soil_status = soil.get("status") or "ok"
    pest = factors.get("pest") or {}
    pest_status = pest.get("status") or "ok"
    growth = factors.get("growth") or {}
    growth_status = growth.get("status") or "ok"
    care = factors.get("care") or {}
    care_status = care.get("status") or "ok"

    if water_status in ("attention", "critical"):
        now_bucket.append({
            "action": "Irrigate soon to relieve water stress",
            "why": f"Field water status is '{water_status}' and the crop is in the {stage_label.lower()} stage.",
            "when": "As soon as possible",
            "priority": "high",
            "stage": stage,
            "stage_label": stage_label,
            "bucket": "now",
            "source": "data",
            "category": "Irrigation",
            "can_track": True,
        })
    elif water_status == "watch":
        week_bucket.append({
            "action": "Monitor field moisture and plan next irrigation",
            "why": "Field water status is 'watch' heading into a sensitive stage.",
            "when": "This week",
            "priority": "medium",
            "stage": stage,
            "stage_label": stage_label,
            "bucket": "this_week",
            "source": "data",
            "category": "Irrigation",
            "can_track": True,
        })

    if soil_status == "needs_test" or not soil.get("available"):
        week_bucket.append({
            "action": "Schedule a soil test for this plot",
            "why": "No recent soil test exists, so nutrition is unknown.",
            "when": "This week",
            "priority": "medium",
            "stage": stage,
            "stage_label": stage_label,
            "bucket": "this_week",
            "source": "data",
            "category": "Soil",
            "can_track": True,
        })

    if pest_status in ("attention", "critical"):
        now_bucket.append({
            "action": f"Scout and act on current pest pressure ({pest_status})",
            "why": "Pest monitoring shows active pressure at a sensitive stage.",
            "when": "Now",
            "priority": "high",
            "stage": stage,
            "stage_label": stage_label,
            "bucket": "now",
            "source": "data",
            "category": "Pest & Disease",
            "can_track": True,
        })
    elif pest_status == "watch":
        week_bucket.append({
            "action": "Increase scouting frequency for pests",
            "why": "Pest monitoring is at 'watch' level.",
            "when": "This week",
            "priority": "medium",
            "stage": stage,
            "stage_label": stage_label,
            "bucket": "this_week",
            "source": "data",
            "category": "Pest & Disease",
            "can_track": True,
        })

    if growth_status in ("attention", "critical"):
        now_bucket.append({
            "action": "Investigate why growth is lagging expectations",
            "why": f"Growth is '{growth_status}' for this point in the cycle.",
            "when": "Now",
            "priority": "high",
            "stage": stage,
            "stage_label": stage_label,
            "bucket": "now",
            "source": "data",
            "category": "Growth",
            "can_track": True,
        })

    if care_status in ("attention", "critical"):
        week_bucket.append({
            "action": "Follow up on flagged care items (fertiliser, upkeep)",
            "why": "Care items have been flagged as needing action.",
            "when": "This week",
            "priority": "medium",
            "stage": stage,
            "stage_label": stage_label,
            "bucket": "this_week",
            "source": "data",
            "category": "Crop Care",
            "can_track": True,
        })

    # 3. Weather-driven items.
    alerts = weather.get("alerts") or []
    heavy_rain = any("rain" in str(a).lower() or "storm" in str(a).lower() for a in alerts)
    forecast = weather.get("forecast") or weather.get("daily") or []
    try:
        wet_soon = [d for d in forecast[:7]
                    if ((d.get("precipitation") if d.get("precipitation") is not None else d.get("rain")) or 0) > 0]
        if wet_soon:
            heavy_rain = True
    except Exception:
        wet_soon = []
    if heavy_rain:
        now_bucket.append({
            "action": "Plan around likely rain in the coming days",
            "why": "Weather forecast shows rain that could affect spraying, harvest or drainage.",
            "when": "Before the rain arrives",
            "priority": "medium",
            "stage": stage,
            "stage_label": stage_label,
            "bucket": "now",
            "source": "data",
            "category": "Weather",
            "can_track": True,
        })

    # 4. Coming Up - build from the next stage's activities + known tasks.
    next_key = None
    try:
        idx = STAGE_KEYS.index(stage)
        if idx < len(STAGE_KEYS) - 1:
            next_key = STAGE_KEYS[idx + 1]
    except ValueError:
        next_key = None

    if next_key:
        next_label = stages_map[next_key]["label"]
        for act in _activity_items(profile, next_key):
            item = {
                "action": f"Get ready for {next_label.lower()}: {act['action'].lower()}",
                "why": act["why"],
                "when": "Coming up",
                "priority": act.get("priority", "medium"),
                "stage": next_key,
                "stage_label": next_label,
                "bucket": "coming_up",
                "source": "stage",
                "category": f"{crop_name or 'Crop'} - {stage_label}",
                "can_track": True,
            }
            coming_bucket.append(item)

    for t in tasks_due:
        if t.get("due_date") and t.get("task_id"):
            coming_bucket.append({
                "action": f"Upcoming task: {t.get('title')}",
                "why": "Already scheduled in your tasks list.",
                "when": t.get("due_date"),
                "priority": t.get("priority", "medium"),
                "stage": stage,
                "stage_label": stage_label,
                "bucket": "coming_up",
                "source": "data",
                "category": t.get("category") or "Crop Care",
                "can_track": False,
                "existing_task_id": t.get("task_id"),
            })

    def _sort_key(item):
        order = {"high": 0, "medium": 1, "low": 2}
        return order.get(item.get("priority", "medium"), 1)

    return {
        "now": sorted(now_bucket, key=_sort_key),
        "this_week": sorted(week_bucket, key=_sort_key),
        "coming_up": sorted(coming_bucket, key=_sort_key),
        "crop": crop_name,
        "is_generic": is_generic,
    }


# ---------------------------------------------------------------------------
# Watch-for builder
# ---------------------------------------------------------------------------


def build_watch(crop_name: Optional[str], stage: str) -> List[Dict[str, Any]]:
    """Watch-for-this list for the current stage (crop-specific + generic)."""
    profile, _ = get_crop_profile(crop_name)
    watch = profile.get("watch") or {}
    merged: List[Dict[str, Any]] = []
    seen = set()
    for item in GENERIC_WATCH.get(stage, []):
        merged.append(dict(item))
        seen.add(item["key"])
    for item in watch.get(stage, []):
        if item["key"] not in seen:
            merged.append(dict(item))
            seen.add(item["key"])
    return merged


# ---------------------------------------------------------------------------
# Health check evaluation
# ---------------------------------------------------------------------------


def severity_label(status: str) -> str:
    return SEVERITY_LABELS.get(status, "Watch closely")


def worst_severity(statuses: List[str]) -> str:
    worst = "normal"
    for s in statuses:
        if SEVERITY_RANK.get(s, 0) > SEVERITY_RANK.get(worst, 0):
            worst = s
    return worst


def evaluate_check(
    crop_name: Optional[str],
    stage: str,
    symptoms: List[str],
    observations: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Rule-based health-check result. Returns an Observation, possible concern,
    recommended action and follow-up. Never claims a definitive diagnosis.
    is_generic reflects whether crop-specific knowledge exists.
    """
    profile, is_generic = get_crop_profile(crop_name)
    normalized = [s for s in (symptoms or []) if s]
    valid = [s for s in normalized if s in SYMPTOM_ASSESSMENTS]
    unknown = [s for s in normalized if s not in SYMPTOM_ASSESSMENTS]

    statuses = []
    concern_parts = []
    action_parts = []
    follow_parts = []

    for code in valid:
        spec = SYMPTOM_ASSESSMENTS[code]
        statuses.append(spec["status"])
        concern_parts.append(spec["concern"])
        action_parts.append(spec["action"])
        follow_parts.append(spec["follow_up"])

    if not valid and unknown:
        statuses.append("watch")
        concern_parts.append("Symptoms reported but not covered by the built-in quick reference.")
        action_parts.append("Keep records of what you see (photos, date, part of plant) and ask an expert.")
        follow_parts.append("Re-check in a few days and log a follow-up.")

    if not valid and not normalized:
        statuses.append("normal")
        concern_parts.append("No specific symptoms were reported for this check.")
        action_parts.append("Keep following the crop plan for the " + (stage or "current") + " stage.")
        follow_parts.append("Log the next check at the following stage.")

    status = worst_severity(statuses)

    # Build a compact observation summary.
    selected_labels = []
    for code in valid:
        for s in SYMPTOM_CATALOGUE:
            if s["code"] == code:
                selected_labels.append(s["label"])
                break
    selected_labels.extend([f"other: {c}" for c in unknown])
    observation = (
        ("Observed: " + ", ".join(selected_labels) + ". ")
        if selected_labels
        else "No symptoms reported. "
    )
    if observations:
        observation += f"Notes: {observations}"

    return {
        "crop": crop_name,
        "is_generic": is_generic,
        "stage": stage,
        "symptom_codes": normalized,
        "selected_labels": selected_labels,
        "observation": observation,
        "possible_concern": ("Possible concern: " + " ".join(concern_parts)) if concern_parts else "Possible concern: none reported.",
        "recommended_action": ("Recommended action: " + " ".join(action_parts)) if action_parts else "Recommended action: follow the current stage plan.",
        "follow_up": ("Follow-up: " + " ".join(follow_parts)) if follow_parts else "Follow-up: log the next check at the next stage.",
        "health_status": status,
        "health_status_label": severity_label(status),
        "helper_note": "This is automated guidance from your field observations - it is not a diagnosis. Confirm with photos or a local expert before treatment.",
    }


def health_status_summary(status: str) -> Dict[str, Any]:
    label = SEVERITY_LABELS.get(status, "Watch closely")
    return {"status": status, "label": label}


def build_task_meta(
    crop_name: Optional[str],
    stage: str,
    action: str,
    due_date: Optional[str] = None,
    priority: str = "medium",
) -> Dict[str, Any]:
    """Metadata used to create a CropTask from a plan item."""
    profile, is_generic = get_crop_profile(crop_name)
    return {
        "title": action[:200],
        "description": f"Created from Crop Health plan ({crop_name or 'Crop'} · {stage}).",
        "category": f"{crop_name or 'Crop'} - {STAGE_LABELS.get(stage, stage)}",
        "due_date": due_date or _fmt(_now() + timedelta(days=3)),
        "priority": priority if priority in ("high", "medium", "low") else "medium",
        "is_generic": is_generic,
    }