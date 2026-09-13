"""Shared Tools & Equipment taxonomy.

The spec-driven machine-type category taxonomy used by both the Tools &
Equipment router (``app.routers.tools_equipment``) and the catalogue seeder
(``app.database.seed_tools_equipment``).

Each category has a stable slug, a human readable name, a Font Awesome icon
and a ``rentable`` flag. Machinery categories (``rentable=True``) also expose a
canonical machine type label used for the ``Equipment.type`` column of the
rent catalogue, so both sides of the page count and filter the same rows.
"""

#: (slug, name, icon, rentable)
TAXONOMY = [
    ("tractors", "Tractors", "fa-tractor", True),
    ("harvesters", "Harvesters", "fa-wheat-awn", True),
    ("cutting-machines", "Cutting Machines", "fa-scissors", True),
    ("grass-cutters", "Grass Cutters", "fa-leaf", True),
    ("brush-cutters", "Brush Cutters", "fa-brush", True),
    ("rotavators", "Rotavators", "fa-hard-drive", True),
    ("tillers", "Tillers", "fa-gears", True),
    ("seeders", "Seeders", "fa-seedling", True),
    ("sprayers", "Sprayers", "fa-spray-can", True),
    ("irrigation-equipment", "Irrigation Equipment", "fa-faucet-drip", True),
    ("ploughs", "Ploughs", "fa-shovel", True),
    ("cultivators", "Cultivators", "fa-shovel", True),
    ("threshers", "Threshers", "fa-fan", True),
    ("pumps", "Pumps", "fa-droplet", True),
    ("trailers", "Trailers", "fa-truck", True),
    ("agricultural-tools", "Agricultural Tools", "fa-hand", False),
    ("safety-equipment", "Safety Equipment", "fa-helmet-safety", False),
    ("other-equipment", "Other Equipment", "fa-box-open", False),
]

CATEGORY_SLUGS = [slug for slug, _name, _icon, _rentable in TAXONOMY]
RENTABLE_SLUGS = [slug for slug, _name, _icon, _rentable in TAXONOMY if _rentable]

CATEGORY_BY_SLUG = {
    slug: {"name": name, "icon": icon, "rentable": rentable}
    for slug, name, icon, rentable in TAXONOMY
}

#: Canonical machine type label used for ``Equipment.type`` per rentable category.
RENT_TYPE_BY_SLUG = {
    "tractors": "Tractor",
    "harvesters": "Harvester",
    "cutting-machines": "Cutting Machine",
    "grass-cutters": "Grass Cutter",
    "brush-cutters": "Brush Cutter",
    "rotavators": "Rotavator",
    "tillers": "Tiller",
    "seeders": "Seeder",
    "sprayers": "Sprayer",
    "irrigation-equipment": "Irrigation Equipment",
    "ploughs": "Plough",
    "cultivators": "Cultivator",
    "threshers": "Thresher",
    "pumps": "Water Pump",
    "trailers": "Trailer",
}

#: Ordered (keyword -> slug) rules. The first match wins; unmatched values are
#: classified as ``other-equipment``. Order matters (e.g. "power tiller" before
#: "tiller", "chaff cutter" before generic "cutter").
TYPE_KEYWORDS = [
    ("brush cutter", "brush-cutters"),
    ("grass cutter", "grass-cutters"),
    ("lawn mower", "grass-cutters"),
    ("rotavator", "rotavators"),
    ("power tiller", "tillers"),
    ("tiller", "tillers"),
    ("harvester", "harvesters"),
    ("combine", "harvesters"),
    ("thresher", "threshers"),
    ("sheller", "threshers"),
    ("dehusker", "threshers"),
    ("chaff cutter", "cutting-machines"),
    ("set cutter", "cutting-machines"),
    ("crop cutter", "cutting-machines"),
    ("cutter", "cutting-machines"),
    ("seeder", "seeders"),
    ("seed drill", "seeders"),
    ("drill", "seeders"),
    ("planter", "seeders"),
    ("transplanter", "seeders"),
    ("spray", "sprayers"),
    ("water pump", "pumps"),
    ("pump", "pumps"),
    ("plough", "ploughs"),
    ("plow", "ploughs"),
    ("cultivator", "cultivators"),
    ("harrow", "cultivators"),
    ("sub-soiler", "cultivators"),
    ("subsoiler", "cultivators"),
    ("ridge", "cultivators"),
    ("trailer", "trailers"),
    ("trolley", "trailers"),
    ("cart", "trailers"),
    ("wagon", "trailers"),
    ("tractor", "tractors"),
    ("drip", "irrigation-equipment"),
    ("sprinkler", "irrigation-equipment"),
    ("hose", "irrigation-equipment"),
    ("valve", "irrigation-equipment"),
    ("irrigation", "irrigation-equipment"),
    ("helmet", "safety-equipment"),
    ("gloves", "safety-equipment"),
    ("mask", "safety-equipment"),
    ("goggles", "safety-equipment"),
    ("boots", "safety-equipment"),
    ("rainwear", "safety-equipment"),
    ("safety", "safety-equipment"),
    ("hoe", "agricultural-tools"),
    ("sickle", "agricultural-tools"),
    ("spade", "agricultural-tools"),
    ("shovel", "agricultural-tools"),
    ("fork", "agricultural-tools"),
    ("rake", "agricultural-tools"),
    ("trowel", "agricultural-tools"),
    ("shears", "agricultural-tools"),
    ("pruner", "agricultural-tools"),
    ("knife", "agricultural-tools"),
    ("saw", "agricultural-tools"),
    ("axe", "agricultural-tools"),
    ("pickaxe", "agricultural-tools"),
    ("tool", "agricultural-tools"),
]


def slug_for_type(value) -> str:
    """Classify a free-text equipment type string into a taxonomy slug."""
    if not value:
        return "other-equipment"
    text = str(value).strip().lower()
    for keyword, slug in TYPE_KEYWORDS:
        if keyword in text:
            return slug
    return "other-equipment"