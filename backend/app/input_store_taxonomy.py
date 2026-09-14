"""Shared Input Store taxonomy.

Single source of truth for the Input Store category slugs, display names,
icons and coarse "product type" labels. Both the catalogue seeder
(``app.database.seed_input_store``) and the API router
(``app.routers.input_store``) import from here so the slug whitelist and the
``product_type`` filter labels can never drift apart.

Domain boundaries
-----------------
The slugs below are the Input Store BUY-side catalogue and must never collide
with the Tools & Equipment storefront slugs (``app.equipment_taxonomy``).
Notably ``sprayers`` is already an equipment slug, so the Input Store sprayer
category uses ``spraying-equipment`` instead.
"""

#: (slug, display name, font-awesome icon) - stable order for the storefront.
CATEGORIES = [
    ("seeds", "Seeds", "fa-seedling"),
    ("fertilizers", "Fertilizers", "fa-flask"),
    ("organic-fertilizers", "Organic Fertilizers", "fa-leaf"),
    ("micronutrients", "Micronutrients", "fa-cubes"),
    ("plant-growth", "Plant Growth Products", "fa-arrow-trend-up"),
    ("soil-conditioners", "Soil Conditioners", "fa-earth-americas"),
    ("bio-fertilizers", "Bio-fertilizers", "fa-vial"),
    ("pesticides", "Pesticides", "fa-bug-slash"),
    ("insecticides", "Insecticides", "fa-bug"),
    ("fungicides", "Fungicides", "fa-shield-halved"),
    ("herbicides", "Herbicides", "fa-glass-water"),
    ("animal-feed", "Animal Feed", "fa-bowl-food"),
    ("livestock-supplies", "Livestock Supplies", "fa-cow"),
    ("irrigation", "Irrigation Supplies", "fa-faucet-drip"),
    ("nursery", "Nursery & Planting Materials", "fa-seedling"),
    ("consumables", "Farming Consumables", "fa-box"),
    ("spraying-equipment", "Sprayers", "fa-spray-can"),
    ("farm-tools", "Farm Tools", "fa-screwdriver-wrench"),
]

CATEGORIES_BY_SLUG = {slug: (name, icon) for slug, name, icon in CATEGORIES}

#: Whitelist used by the API router - only these categories are ever exposed.
INPUT_STORE_SLUGS = tuple(slug for slug, _n, _i in CATEGORIES)

#: Coarse product-type label used for the "Product type" filter.
TYPE_BY_SLUG = {
    "seeds": "Seed",
    "fertilizers": "Fertilizer",
    "organic-fertilizers": "Organic Fertilizer",
    "micronutrients": "Micronutrient",
    "plant-growth": "Plant Growth Promoter",
    "soil-conditioners": "Soil Conditioner",
    "bio-fertilizers": "Bio-fertilizer",
    "pesticides": "Pesticide",
    "insecticides": "Insecticide",
    "fungicides": "Fungicide",
    "herbicides": "Herbicide",
    "animal-feed": "Animal Feed",
    "livestock-supplies": "Livestock Supply",
    "irrigation": "Irrigation Supply",
    "nursery": "Nursery Supply",
    "consumables": "Farming Consumable",
    "spraying-equipment": "Sprayer",
    "farm-tools": "Farm Tool",
}

#: Default subcategory label when a row has no finer-grained grouping.
SUB_BY_SLUG = {slug: label for slug, label in TYPE_BY_SLUG.items()}