"""Seed the Marketplace seller categories.

The Marketplace is the farmer SELLING platform. Its category tree is
intentionally separate from the Input Store (BUY side) ``product_categories``
so the two domains never mix. Idempotent - safe to run repeatedly.
"""

from sqlalchemy.orm import Session

from app.models.marketplace import MarketplaceCategory

PRODUCE_CATEGORIES = [
    ("rice", "Rice", "fa-seedling"),
    ("vegetables", "Vegetables", "fa-carrot"),
    ("fruits", "Fruits", "fa-apple-whole"),
    ("pulses", "Pulses", "fa-seedling"),
    ("grains", "Grains", "fa-wheat-awn"),
    ("spices", "Spices", "fa-pepper-hot"),
    ("oilseeds", "Oilseeds", "fa-seedling"),
    ("other-produce", "Other Produce", "fa-boxes-stacked"),
]

ITEM_CATEGORIES = [
    ("tools", "Tools", "fa-hammer"),
    ("equipment", "Equipment", "fa-tools"),
    ("machinery", "Machinery", "fa-tractor"),
    ("irrigation-equipment", "Irrigation Equipment", "fa-faucet-drip"),
    ("farm-accessories", "Farm Accessories", "fa-box-open"),
    ("livestock-products", "Livestock Products", "fa-cow"),
    ("animal-feed", "Animal Feed", "fa-bowl-food"),
    ("other-items", "Other Farm Items", "fa-box"),
]


def seed_marketplace_categories(db: Session) -> dict:
    created = 0
    for order, (slug, name, icon) in enumerate(PRODUCE_CATEGORIES, start=1):
        existing = db.query(MarketplaceCategory).filter(MarketplaceCategory.slug == slug).first()
        if existing:
            existing.group = "produce"
            existing.name = name
            existing.icon = icon
            existing.display_order = order
            continue
        db.add(MarketplaceCategory(
            name=name, slug=slug, group="produce", icon=icon, display_order=order, is_active=True,
        ))
        created += 1

    for order, (slug, name, icon) in enumerate(ITEM_CATEGORIES, start=1):
        existing = db.query(MarketplaceCategory).filter(MarketplaceCategory.slug == slug).first()
        if existing:
            existing.group = "items"
            existing.name = name
            existing.icon = icon
            existing.display_order = 100 + order
            continue
        db.add(MarketplaceCategory(
            name=name, slug=slug, group="items", icon=icon, display_order=100 + order, is_active=True,
        ))
        created += 1

    db.commit()
    return {"categories_created": created, "total": len(PRODUCE_CATEGORIES) + len(ITEM_CATEGORIES)}