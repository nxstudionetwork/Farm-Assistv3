"""Tools & Equipment Router - Professional Agricultural Marketplace API.

Provides full backend endpoints for Tools & Equipment (Buy & Rent modes):
- Products catalogue with multi-field search, multi-faceted filtering, sorting, pagination.
- Category listings with real item counts.
- Dynamic filter facets (power source, brand, suitable activity, price range).
- Smart farm recommendations using the authenticated farmer's crops, land size, and tasks.
- Recently viewed equipment with strict per-farmer isolation.
- Side-by-side equipment comparison (up to 4 items).
- Equipment details with complete technical specifications and seller profile.
- Rental machinery listings and bookings with calendar integration.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, and_, desc, asc, func
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User, FarmerProfile
from app.models.farm import Farm
from app.models.crop import Crop, CropCycle, CropTask
from app.models.worker import Equipment, EquipmentBooking
from app.models.marketplace import (
    Product,
    ProductCategory,
    Seller,
    ProductCrop,
    EquipmentMetadata,
    FarmerRecentlyViewed,
    MarketplaceCart,
    MarketplaceCartItem,
    MarketplaceOrder,
    OrderItem,
    MarketplaceWishlist,
    EquipmentReport,
)
from app.equipment_taxonomy import (
    CATEGORY_SLUGS,
    RENTABLE_SLUGS,
    CATEGORY_BY_SLUG,
    RENT_TYPE_BY_SLUG,
    slug_for_type,
)

router = APIRouter(tags=["Tools & Equipment"])

# Supported equipment category slugs - the spec-driven machine-type taxonomy.
# Deliberately distinct from the Input Store slugs ("irrigation", "sprayers",
# ...) so the two storefronts never leak products into each other even though
# they share the ``products`` table.
EQUIPMENT_CATEGORY_SLUGS = CATEGORY_SLUGS


class RentalBookingRequest(BaseModel):
    equipment_id: str
    booking_date: Optional[str] = None
    duration_days: int = Field(default=1, ge=1, le=90)
    notes: Optional[str] = None


def _tags(product: Product) -> dict:
    raw = product.tags
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _discount(product: Product) -> Optional[float]:
    price = product.price or 0
    mrp = product.original_price or 0
    if mrp > price > 0:
        return round(((mrp - price) / mrp) * 100, 1)
    return None


def _stock_status(product: Product) -> str:
    stock = float(product.stock_quantity or 0)
    if stock <= 0:
        return "out"
    if stock <= float(product.min_order_quantity or 1) * 3:
        return "low"
    return "in"


def _category_payload(cat: Optional[ProductCategory]) -> Optional[dict]:
    if not cat:
        return None
    return {
        "id": cat.id,
        "name": cat.name,
        "slug": cat.slug,
        "icon": cat.icon or "fa-toolbox",
    }


def _seller_payload(seller: Optional[Seller]) -> Optional[dict]:
    if not seller:
        return None
    return {
        "id": seller.id,
        "shop_name": seller.shop_name,
        "location": seller.location,
        "is_verified": bool(seller.is_verified),
        "rating": seller.rating or 0.0,
        "total_sales": seller.total_sales or 0,
    }


def _equipment_payload(db: Session, product: Product) -> dict:
    meta = product.equipment_metadata
    tags = _tags(product)

    # Resolve specs either from EquipmentMetadata table or from tags JSON
    # (only real values - no fabricated fallbacks; the frontend shows a field
    # only when it actually exists for the product).
    power_source = (meta.power_source if meta else None) or tags.get("power_source")
    weight = (meta.weight if meta else None) or tags.get("weight")
    dimensions = (meta.dimensions if meta else None) or tags.get("dimensions")
    material = (meta.material if meta else None) or tags.get("material")
    warranty = (meta.warranty if meta else None) or tags.get("warranty")
    suitable_use = (meta.suitable_use if meta else None) or tags.get("suitable_use")
    equipment_type = (
        (meta.equipment_type if meta else None)
        or tags.get("equipment_type")
        or (product.category.name if product.category else None)
    )
    operating_width = (meta.operating_width if meta else None) or tags.get("operating_width")
    capacity = (meta.capacity if meta else None) or tags.get("capacity")
    location = (meta.location if meta else None) or tags.get("location")
    condition = (meta.condition if meta else None) or tags.get("condition")
    delivery_available = meta.delivery_available if meta else None
    pickup_available = meta.pickup_available if meta else None

    crops = sorted({c.crop_name for c in product.crops}) if product.crops else []
    specifications = tags.get("specifications") if isinstance(tags.get("specifications"), dict) else None

    images = product.images
    if not images or not isinstance(images, list):
        images = [product.image_url] if product.image_url else []

    return {
        "id": product.id,
        "product_id": product.product_id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "mrp": product.original_price if (product.original_price and product.original_price > product.price) else None,
        "original_price": product.original_price,
        "discount": _discount(product),
        "unit": product.unit or "piece",
        "stock_quantity": product.stock_quantity or 0,
        "stock_status": _stock_status(product),
        "in_stock": float(product.stock_quantity or 0) > 0,
        "min_order_quantity": product.min_order_quantity or 1,
        "image_url": product.image_url,
        "thumbnail_url": product.image_url,
        "images": images,
        "gallery_images": images,
        "alt_text": f"{product.name} - {product.brand or 'Farm Assist'} Agricultural Equipment",
        "brand": product.brand,
        "rating": product.rating,
        "total_reviews": product.total_reviews or 0,
        "is_active": product.is_active,
        "category": _category_payload(product.category),
        "seller": _seller_payload(product.seller),
        "equipment_type": equipment_type,
        "power_source": power_source,
        "weight": weight,
        "dimensions": dimensions,
        "material": material,
        "warranty": warranty,
        "suitable_use": suitable_use,
        "operating_width": operating_width,
        "capacity": capacity,
        "location": location,
        "condition": condition,
        "delivery_available": delivery_available,
        "pickup_available": pickup_available,
        "catalog": bool(tags.get("source") == "catalogue"),
        "crops": crops,
        "crop_names": [c.title() for c in crops],
        "specifications": specifications,
        "created_at": str(product.created_at) if product.created_at else None,
    }


def _equipment_base_query(db: Session):
    """Query products belonging to equipment categories or having equipment metadata."""
    # Find all category IDs for equipment
    cat_ids = [
        c.id for c in db.query(ProductCategory.id).filter(
            ProductCategory.slug.in_(EQUIPMENT_CATEGORY_SLUGS)
        ).all()
    ]

    q = db.query(Product).outerjoin(EquipmentMetadata, Product.id == EquipmentMetadata.product_id).outerjoin(
        ProductCategory, Product.category_id == ProductCategory.id
    ).filter(Product.is_active == True)

    if cat_ids:
        q = q.filter(
            or_(
                Product.category_id.in_(cat_ids),
                EquipmentMetadata.id.isnot(None),
                Product.tags.like('%"equipment_type"%'),
                Product.tags.like('%"power_source"%'),
            )
        )
    return q


def _rent_types_for_category(db: Session, slug: str) -> list:
    """All ``Equipment.type`` labels that belong to a taxonomy category."""
    labels = [RENT_TYPE_BY_SLUG[slug]] if slug in RENT_TYPE_BY_SLUG else []
    labels += [
        t[0]
        for t in db.query(Equipment.type).distinct().all()
        if t[0] and t[0] not in labels and slug_for_type(t[0]) == slug
    ]
    return labels


def _rental_payload(db: Session, e: Equipment, booking_counts: Optional[dict] = None) -> dict:
    slug = slug_for_type(e.type)
    cat = CATEGORY_BY_SLUG.get(slug, {})
    images = []
    if e.image_url:
        images.append(e.image_url)

    # Live availability derived from real bookings (never fabricated).
    avail = _availability_payload(db, e)
    counts = booking_counts or {}
    created = e.created_at or datetime.utcnow()
    return {
        "id": e.id,
        "equipment_id": e.equipment_id,
        "name": e.name,
        "type": e.type,
        "brand": e.brand,
        "model": e.model,
        "daily_rate": e.daily_rate,
        "hourly_rate": e.hourly_rate,
        "deposit_amount": e.deposit_amount,
        "min_duration_days": e.min_duration_days or 1,
        "rental_terms": e.rental_terms,
        "location": e.location,
        "image_url": e.image_url,
        "images": images,
        "description": e.description,
        "is_available": e.is_available,
        "condition": e.condition,
        "listing_status": e.listing_status,
        "owner_id": e.owner_id,
        "provider": None,
        "booking_count": counts.get(e.id, 0),
        "recently_added": bool(created and (datetime.utcnow() - created).days <= 30),
        "category_slug": slug,
        "category_name": cat.get("name", "Other Equipment"),
        "availability_status": avail["status"],
        "availability_label": avail["label"],
        "available_now": avail["available_now"],
        "next_available_date": avail["next_available_date"],
        "mode": "rent",
        "created_at": str(e.created_at) if e.created_at else None,
    }


ACTIVE_BOOKING_STATUS = ("requested", "confirmed")


def _active_bookings(db: Session, equip_id: str) -> list:
    return (
        db.query(EquipmentBooking)
        .filter(
            EquipmentBooking.equipment_id == equip_id,
            EquipmentBooking.status.in_(ACTIVE_BOOKING_STATUS),
        )
        .all()
    )


def _booking_window(b: EquipmentBooking):
    """Booking occupies [start, start + duration_days). Returns ISO strings."""
    start = b.booking_date or ""
    end = ""
    if start:
        try:
            _s = datetime.strptime(start, "%Y-%m-%d")
            end = (_s + timedelta(days=b.duration_days or 1)).strftime("%Y-%m-%d")
        except Exception:
            end = ""
    return start, end


def _next_available_date(db: Session, equip: Equipment, active: Optional[list] = None) -> Optional[str]:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    active = _active_bookings(db, equip.id) if active is None else active
    if equip.is_available and not active:
        return today
    if not active:
        return None
    ends = []
    for b in active:
        _s, e = _booking_window(b)
        if e:
            ends.append(e)
    return min(ends) if ends else None


def _availability_payload(db: Session, equip: Equipment) -> dict:
    active = _active_bookings(db, equip.id)
    next_date = _next_available_date(db, equip, active)
    if not equip.is_available:
        return {
            "status": "unavailable",
            "label": "Unavailable",
            "available_now": False,
            "next_available_date": next_date,
            "active_bookings": len(active),
        }
    if active:
        return {
            "status": "booked",
            "label": "Booked",
            "available_now": False,
            "next_available_date": next_date,
            "active_bookings": len(active),
        }
    return {
        "status": "available",
        "label": "Available Now",
        "available_now": True,
        "next_available_date": next_date,
        "active_bookings": 0,
    }


def _range_overlaps(s1: str, e1: str, s2: str, e2: str) -> bool:
    if not (s1 and e1 and s2 and e2):
        return False
    return s2 < e1 and s1 < e2


def _rental_booking_payload(db: Session, b: EquipmentBooking) -> dict:
    equip = db.query(Equipment).filter(Equipment.id == b.equipment_id).first()
    item = {
        "id": b.id,
        "booking_id": b.booking_id,
        "equipment_name": equip.name if equip else "Agricultural Machinery",
        "type": equip.type if equip else "Equipment",
        "equipment_id": equip.equipment_id if equip else None,
        "category_slug": slug_for_type(equip.type) if equip else "other-equipment",
        "category_name": CATEGORY_BY_SLUG.get(slug_for_type(equip.type), {}).get("name", "Other") if equip else "Other",
        "brand": equip.brand if equip else None,
        "daily_rate": equip.daily_rate if equip else 0,
        "hourly_rate": equip.hourly_rate if equip else None,
        "deposit_amount": equip.deposit_amount if equip else None,
        "min_duration_days": equip.min_duration_days if equip else 1,
        "rental_terms": equip.rental_terms if equip else None,
        "location": equip.location if equip else None,
        "image_url": equip.image_url if equip else None,
        "booking_date": b.booking_date,
        "duration_days": b.duration_days,
        "total_cost": b.total_cost,
        "status": b.status,
        "created_at": str(b.created_at) if b.created_at else None,
    }
    return item


# ---------------------------------------------------------------------------
# 1. LIST PRODUCTS (BUY MODE)
# ---------------------------------------------------------------------------
@router.get("/products")
@router.get("")
def list_equipment_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    category: Optional[str] = None,
    category_id: Optional[str] = None,
    equipment_type: Optional[str] = None,
    power_source: Optional[str] = None,
    suitable_use: Optional[str] = None,
    crop: Optional[str] = None,
    brand: Optional[str] = None,
    seller_id: Optional[str] = None,
    location: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: bool = False,
    min_rating: Optional[float] = None,
    sort_by: str = Query("relevance", pattern="^(relevance|price|rating|created_at|name)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = _equipment_base_query(db)

    # Search across name, brand, description, equipment_type, suitable_use
    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Product.name.ilike(term),
                Product.brand.ilike(term),
                Product.description.ilike(term),
                EquipmentMetadata.equipment_type.ilike(term),
                EquipmentMetadata.suitable_use.ilike(term),
                EquipmentMetadata.power_source.ilike(term),
            )
        )

    # Category filter (by slug or name or id)
    cat_filter = category or category_id
    if cat_filter and cat_filter != "all":
        cat_obj = db.query(ProductCategory).filter(
            or_(
                ProductCategory.slug == cat_filter,
                ProductCategory.id == cat_filter,
                ProductCategory.name.ilike(f"%{cat_filter}%"),
            )
        ).first()
        if cat_obj:
            type_labels = [cat_obj.name]
            if cat_obj.slug in RENT_TYPE_BY_SLUG:
                type_labels.append(RENT_TYPE_BY_SLUG[cat_obj.slug])
            conds = [
                Product.category_id == cat_obj.id,
                EquipmentMetadata.equipment_type.ilike(f"%{cat_obj.name}%"),
            ]
            for label in type_labels[1:]:
                conds.append(EquipmentMetadata.equipment_type.ilike(f"%{label}%"))
            q = q.filter(or_(*conds))

    if location and location != "all":
        term = f"%{location.strip()}%"
        q = q.filter(
            or_(
                EquipmentMetadata.location.ilike(term),
                Product.tags.like(f'%"location": "%{location}%"'),
            )
        )

    if equipment_type and equipment_type != "all":
        q = q.filter(EquipmentMetadata.equipment_type.ilike(f"%{equipment_type}%"))

    if power_source and power_source != "all":
        q = q.filter(EquipmentMetadata.power_source.ilike(f"%{power_source}%"))

    if suitable_use and suitable_use != "all":
        q = q.filter(EquipmentMetadata.suitable_use.ilike(f"%{suitable_use}%"))

    if brand and brand != "all":
        q = q.filter(Product.brand == brand)

    if seller_id and seller_id != "all":
        q = q.filter(Product.seller_id == seller_id)

    if crop and crop != "all":
        crop_name = crop.strip().lower()
        sub = db.query(ProductCrop.product_id).filter(
            or_(ProductCrop.crop_name == crop_name, ProductCrop.crop_name == "general")
        )
        q = q.filter(Product.id.in_(sub))

    if min_price is not None:
        q = q.filter(Product.price >= min_price)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)

    if in_stock:
        q = q.filter(Product.stock_quantity > 0)

    if min_rating is not None:
        q = q.filter(Product.rating >= min_rating)

    # Sorting
    desc_order = sort_order == "desc"
    if sort_by == "price":
        q = q.order_by(Product.price.desc() if desc_order else Product.price.asc())
    elif sort_by == "rating":
        q = q.order_by(Product.rating.desc() if desc_order else Product.rating.asc())
    elif sort_by == "name":
        q = q.order_by(Product.name.desc() if desc_order else Product.name.asc())
    else:
        q = q.order_by(Product.created_at.desc())

    rows = q.all()

    # Relevance scoring if search term exists
    if search and sort_by == "relevance":
        term_lower = search.strip().lower()

        def score(row):
            name = (row.name or "").lower()
            brand = (row.brand or "").lower()
            meta = row.equipment_metadata
            eq_type = (meta.equipment_type or "").lower() if meta else ""
            use = (meta.suitable_use or "").lower() if meta else ""
            if name == term_lower:
                return 0
            if name.startswith(term_lower):
                return 1
            if term_lower in name:
                return 2
            if term_lower in eq_type or term_lower in use:
                return 3
            if term_lower in brand:
                return 4
            return 5

        rows.sort(key=score)

    total = len(rows)
    start = (page - 1) * limit
    items = rows[start : start + limit]

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit),
            "items": [_equipment_payload(db, p) for p in items],
        },
    }


# ---------------------------------------------------------------------------
# 2. CATEGORIES (spec-driven taxonomy with real BUY + RENT counts)
# ---------------------------------------------------------------------------
@router.get("/categories")
def list_equipment_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = {
        c.slug: c
        for c in db.query(ProductCategory)
        .filter(ProductCategory.slug.in_(CATEGORY_SLUGS))
        .all()
    }

    # Pre-taxonomy databases: fall back to any category holding equipment products.
    if not existing:
        items = []
        for cat in db.query(ProductCategory).all():
            count = (
                db.query(Product)
                .filter(Product.category_id == cat.id, Product.is_active == True)  # noqa: E712
                .count()
            )
            if not count:
                continue
            items.append({
                "id": cat.id,
                "name": cat.name,
                "slug": cat.slug,
                "icon": cat.icon or "fa-toolbox",
                "rentable": False,
                "count": count,
                "buy_count": count,
                "rent_count": 0,
            })
        items.sort(key=lambda c: (-c["count"], c["name"]))
        return {
            "status": "success",
            "data": {"items": items, "total_categories": len(items)},
        }

    items = []
    for slug in CATEGORY_SLUGS:
        info = CATEGORY_BY_SLUG[slug]
        pc = existing.get(slug)
        buy_count = 0
        if pc:
            buy_count = (
                db.query(Product)
                .filter(Product.category_id == pc.id, Product.is_active == True)  # noqa: E712
                .count()
            )
        rent_count = 0
        if info["rentable"]:
            labels = _rent_types_for_category(db, slug)
            if labels:
                rent_count = (
                    db.query(Equipment)
                    .filter(Equipment.type.in_(labels), Equipment.listing_status == "active")
                    .count()
                )
        items.append({
            "id": pc.id if pc else None,
            "name": info["name"],
            "slug": slug,
            "icon": info["icon"],
            "rentable": info["rentable"],
            "count": buy_count + rent_count,
            "buy_count": buy_count,
            "rent_count": rent_count,
        })

    items.sort(key=lambda c: (-c["count"], c["name"]))
    return {
        "status": "success",
        "data": {"items": items, "total_categories": len(items)},
    }


# ---------------------------------------------------------------------------
# 3. FILTERS FACETS
# ---------------------------------------------------------------------------
@router.get("/filters")
def list_equipment_filters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_q = _equipment_base_query(db)

    # Brands
    brands = [
        r[0]
        for r in base_q.with_entities(Product.brand)
        .filter(Product.brand.isnot(None), Product.brand != "")
        .distinct()
        .order_by(Product.brand)
        .all()
    ]

    # Power sources
    power_sources = [
        r[0]
        for r in db.query(EquipmentMetadata.power_source)
        .filter(EquipmentMetadata.power_source.isnot(None), EquipmentMetadata.power_source != "")
        .distinct()
        .order_by(EquipmentMetadata.power_source)
        .all()
    ]
    if not power_sources:
        power_sources = ["Manual", "Electric", "Battery", "Fuel", "Solar"]

    # Suitable uses
    suitable_uses = [
        r[0]
        for r in db.query(EquipmentMetadata.suitable_use)
        .filter(EquipmentMetadata.suitable_use.isnot(None), EquipmentMetadata.suitable_use != "")
        .distinct()
        .order_by(EquipmentMetadata.suitable_use)
        .all()
    ]
    if not suitable_uses:
        suitable_uses = [
            "Land preparation", "Planting", "Irrigation", "Weeding",
            "Spraying", "Harvesting", "Safety", "Storage", "Transport", "Maintenance"
        ]

    # Crops
    crops = [
        r[0].title()
        for r in db.query(ProductCrop.crop_name)
        .distinct()
        .order_by(ProductCrop.crop_name)
        .all()
        if r[0] != "general"
    ]

    # Sellers (scoped to tools-equipment products that actually carry a marketplace seller)
    seller_ids = [
        r[0]
        for r in base_q.filter(Product.seller_id.isnot(None)).with_entities(Product.seller_id).distinct().all()
    ]
    sellers = [
        {
            "id": s.id,
            "shop_name": s.shop_name,
            "location": s.location,
            "is_verified": bool(s.is_verified),
        }
        for s in db.query(Seller)
        .filter(Seller.id.in_(seller_ids) if seller_ids else False)
        .order_by(Seller.shop_name)
        .all()
    ]

    # Min/Max Price
    min_price_row = base_q.with_entities(Product.price).order_by(Product.price.asc()).first()
    max_price_row = base_q.with_entities(Product.price).order_by(Product.price.desc()).first()

    # Locations (from equipment metadata + rental machinery)
    locations = sorted({
        r[0]
        for r in db.query(EquipmentMetadata.location)
        .filter(EquipmentMetadata.location.isnot(None), EquipmentMetadata.location != "")
        .distinct()
        .all()
    } | {
        r[0]
        for r in db.query(Equipment.location)
        .filter(Equipment.location.isnot(None), Equipment.location != "")
        .distinct()
        .all()
    })

    # Conditions (from buy metadata + rental machinery; only real values)
    conditions = sorted({
        r[0]
        for r in db.query(EquipmentMetadata.condition)
        .filter(EquipmentMetadata.condition.isnot(None), EquipmentMetadata.condition != "")
        .distinct()
        .all()
    } | {
        r[0]
        for r in db.query(Equipment.condition)
        .filter(Equipment.condition.isnot(None), Equipment.condition != "")
        .distinct()
        .all()
    })

    # Rental daily-rate range (for the unified price filter in ALL/RENT modes)
    min_rate_row = db.query(Equipment.daily_rate).order_by(Equipment.daily_rate.asc()).first()
    max_rate_row = db.query(Equipment.daily_rate).order_by(Equipment.daily_rate.desc()).first()
    rate_range = {
        "min": float(min_rate_row[0]) if min_rate_row and min_rate_row[0] is not None else 100.0,
        "max": float(max_rate_row[0]) if max_rate_row and max_rate_row[0] is not None else 10000.0,
    }

    has_verified_sellers = bool(
    any(s["is_verified"] for s in sellers)
)

    return {
        "status": "success",
        "data": {
            "brands": brands or [],
            "power_sources": power_sources,
            "suitable_uses": suitable_uses,
            "crops": crops,
            "sellers": sellers,
            "locations": locations,
            "conditions": conditions,
            "price_range": {
                "min": float(min_price_row[0]) if min_price_row and min_price_row[0] is not None else 100.0,
                "max": float(max_price_row[0]) if max_price_row and max_price_row[0] is not None else 50000.0,
            },
            "rate_range": rate_range,
            "has_verified_sellers": has_verified_sellers,
        },
    }


# ---------------------------------------------------------------------------
# 4. RECOMMENDATIONS FOR AUTHENTICATED FARMER
# ---------------------------------------------------------------------------
@router.get("/recommended")
def get_recommended_equipment(
    limit: int = Query(8, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recommends real equipment matching farmer's crops, land size, and tasks."""
    profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == current_user.id).first()
    farmer_crops = set()

    # 1. From FarmerProfile
    if profile and profile.preferred_crops:
        for c in str(profile.preferred_crops).replace(";", ",").split(","):
            token = c.strip().lower()
            if token:
                farmer_crops.add(token)

    # 2. From Active Farm CropCycles
    user_farms = db.query(Farm.id).filter(Farm.user_id == current_user.id).all()
    farm_ids = [f[0] for f in user_farms]
    if farm_ids:
        active_cycles = (
            db.query(Crop.name)
            .join(CropCycle, CropCycle.crop_id == Crop.id)
            .filter(CropCycle.farm_id.in_(farm_ids), CropCycle.status == "active")
            .all()
        )
        for c in active_cycles:
            if c[0]:
                farmer_crops.add(c[0].strip().lower())

    # 3. Check upcoming tasks for activity context
    task_types = set()
    if farm_ids:
        tasks = (
            db.query(CropTask.category, CropTask.title, CropTask.description)
            .join(CropCycle, CropTask.crop_cycle_id == CropCycle.id)
            .filter(CropCycle.farm_id.in_(farm_ids), CropTask.status == "pending")
            .limit(10)
            .all()
        )
        for cat, title, desc in tasks:
            combined = f"{cat or ''} {title or ''} {desc or ''}".lower()

            for activity in ["irrigation", "spraying", "harvesting", "weeding", "planting", "land preparation"]:
                if activity in combined:
                    task_types.add(activity.title())

    # Find matched products
    matched_product_ids = set()
    recommendation_reasons = {}

    if farmer_crops:
        crop_rows = (
            db.query(ProductCrop.product_id, ProductCrop.crop_name)
            .filter(ProductCrop.crop_name.in_(list(farmer_crops)))
            .all()
        )
        for pid, cname in crop_rows:
            matched_product_ids.add(pid)
            recommendation_reasons[pid] = f"Recommended for your {cname.title()} crop"

    if task_types:
        task_rows = (
            db.query(EquipmentMetadata.product_id, EquipmentMetadata.suitable_use)
            .filter(EquipmentMetadata.suitable_use.in_(list(task_types)))
            .all()
        )
        for pid, act in task_rows:
            matched_product_ids.add(pid)
            recommendation_reasons[pid] = f"Matches upcoming {act} task"

    items = []
    if matched_product_ids:
        items = (
            _equipment_base_query(db)
            .filter(Product.id.in_(list(matched_product_ids)), Product.stock_quantity > 0)
            .order_by(Product.rating.desc(), Product.created_at.desc())
            .limit(limit)
            .all()
        )

    # Fallback to top-rated essential equipment if farmer has no crop data or no match
    if not items:
        items = (
            _equipment_base_query(db)
            .filter(Product.stock_quantity > 0)
            .order_by(Product.rating.desc(), Product.total_reviews.desc())
            .limit(limit)
            .all()
        )
        for p in items:
            recommendation_reasons[p.id] = "Curated from the Farm Assist equipment catalogue"

    payloads = []
    for p in items:
        p_data = _equipment_payload(db, p)
        p_data["recommendation_reason"] = recommendation_reasons.get(p.id, "Recommended for your farm")
        payloads.append(p_data)

    return {
        "status": "success",
        "data": {
            "farmer_crops": sorted(list(farmer_crops)),
            "active_tasks": sorted(list(task_types)),
            "items": payloads,
        },
    }


# ---------------------------------------------------------------------------
# 5. RECENTLY VIEWED (PER-FARMER ISOLATED)
# ---------------------------------------------------------------------------
@router.get("/recent")
def get_recently_viewed(
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(FarmerRecentlyViewed)
        .filter(FarmerRecentlyViewed.user_id == current_user.id)
        .order_by(desc(FarmerRecentlyViewed.viewed_at))
        .limit(limit)
        .all()
    )

    items = []
    for r in rows:
        if r.product and r.product.is_active:
            items.append(_equipment_payload(db, r.product))

    return {
        "status": "success",
        "data": {
            "items": items,
            "count": len(items),
        },
    }


@router.post("/viewed/{product_id}")
def record_product_view(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = db.query(Product).filter(
        or_(Product.id == product_id, Product.product_id == product_id),
        Product.is_active == True,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    rec = db.query(FarmerRecentlyViewed).filter(
        FarmerRecentlyViewed.user_id == current_user.id,
        FarmerRecentlyViewed.product_id == product.id,
    ).first()

    if rec:
        rec.viewed_at = datetime.utcnow()
    else:
        rec = FarmerRecentlyViewed(
            user_id=current_user.id,
            product_id=product.id,
            viewed_at=datetime.utcnow(),
        )
        db.add(rec)
    db.commit()

    return {"status": "success", "message": "View recorded"}


# ---------------------------------------------------------------------------
# 6. COMPARE EQUIPMENT (UP TO 4 PRODUCTS)
# ---------------------------------------------------------------------------
@router.get("/compare")
def compare_equipment(
    ids: str = Query(..., description="Comma-separated product IDs"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="No product IDs provided")
    if len(id_list) > 4:
        id_list = id_list[:4]

    products = (
        db.query(Product)
        .filter(or_(Product.id.in_(id_list), Product.product_id.in_(id_list)))
        .all()
    )

    items = [_equipment_payload(db, p) for p in products]
    return {
        "status": "success",
        "data": {
            "items": items,
            "compared_count": len(items),
        },
    }


# ---------------------------------------------------------------------------
# 8. UNIFIED BROWSE (ALL | RENT | BUY)
# ---------------------------------------------------------------------------
# A single catalogue used by the Tools & Equipment page: Buy products and Rent
# machinery are merged server-side with one faceted filter set, one sort, and
# shared pagination. Availability is computed from real bookings.
# ---------------------------------------------------------------------------


class RentListingCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    type: str = Field(..., min_length=2, max_length=100)
    brand: Optional[str] = None
    model: Optional[str] = None
    description: Optional[str] = None
    daily_rate: float = Field(..., gt=0)
    hourly_rate: Optional[float] = Field(default=None, ge=0)
    deposit_amount: Optional[float] = Field(default=None, ge=0)
    min_duration_days: int = Field(default=1, ge=1, le=90)
    rental_terms: Optional[str] = None
    location: Optional[str] = None
    condition: Optional[str] = None
    image_url: Optional[str] = None
    is_available: bool = True


class BuyListingCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    category: Optional[str] = Field(default=None, min_length=2, max_length=100)
    category_slug: Optional[str] = Field(default=None, min_length=2, max_length=100)
    brand: Optional[str] = None
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    stock_quantity: float = Field(default=1, ge=0)
    condition: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None
    delivery_available: bool = True
    pickup_available: bool = True


class ListingStatusUpdate(BaseModel):
    is_available: bool


def _provider_name(db: Session, e: Equipment) -> str:
    if e.owner_id:
        owner = db.query(User).filter(User.id == e.owner_id).first()
        if owner and owner.full_name:
            return owner.full_name
    return "Farm Assist Catalogue"


def _is_recent_created(created) -> bool:
    return bool(created and (datetime.utcnow() - created).total_seconds() <= 30 * 86400)


def _buy_filtered(
    db,
    search=None,
    category=None,
    brand=None,
    location=None,
    condition=None,
    power_source=None,
    suitable_use=None,
    min_price=None,
    max_price=None,
    in_stock=False,
    delivery_available=False,
    pickup_available=False,
    verified_sellers=False,
    min_rating=None,
    recently_added_days=None,
    availability_now=False,
):
    q = _equipment_base_query(db)

    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Product.name.ilike(term),
                Product.brand.ilike(term),
                Product.description.ilike(term),
                EquipmentMetadata.equipment_type.ilike(term),
                EquipmentMetadata.suitable_use.ilike(term),
                EquipmentMetadata.power_source.ilike(term),
            )
        )

    if category and category != "all":
        cat_obj = (
            db.query(ProductCategory)
            .filter(
                or_(
                    ProductCategory.slug == category,
                    ProductCategory.id == category,
                    ProductCategory.name.ilike(f"%{category}%"),
                )
            )
            .first()
        )
        if cat_obj:
            type_labels = [cat_obj.name]
            if cat_obj.slug in RENT_TYPE_BY_SLUG:
                type_labels.append(RENT_TYPE_BY_SLUG[cat_obj.slug])
            conds = [Product.category_id == cat_obj.id]
            for label in type_labels:
                conds.append(EquipmentMetadata.equipment_type.ilike(f"%{label}%"))
            q = q.filter(or_(*conds))

    if location and location != "all":
        term = f"%{location.strip()}%"
        q = q.filter(
            or_(
                EquipmentMetadata.location.ilike(term),
                Product.tags.like(f'%"location": "%{location}%"'),
            )
        )

    if brand and brand != "all":
        q = q.filter(Product.brand == brand)
    if condition and condition != "all":
        q = q.filter(EquipmentMetadata.condition == condition)
    if power_source and power_source != "all":
        q = q.filter(EquipmentMetadata.power_source.ilike(f"%{power_source}%"))
    if suitable_use and suitable_use != "all":
        q = q.filter(EquipmentMetadata.suitable_use.ilike(f"%{suitable_use}%"))

    if min_price is not None:
        q = q.filter(Product.price >= min_price)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)

    if in_stock or availability_now:
        q = q.filter(Product.stock_quantity > 0)
    if delivery_available:
        q = q.filter(EquipmentMetadata.delivery_available == True)  # noqa: E712
    if pickup_available:
        q = q.filter(EquipmentMetadata.pickup_available == True)  # noqa: E712
    if verified_sellers:
        verified_ids = [r[0] for r in db.query(Seller.id).filter(Seller.is_verified == True).all()]  # noqa: E712
        if verified_ids:
            q = q.filter(Product.seller_id.in_(verified_ids))
        else:
            q = q.filter(Product.id.in_([]))
    if min_rating is not None:
        q = q.filter(Product.rating >= min_rating)
    if recently_added_days:
        q = q.filter(Product.created_at >= datetime.utcnow() - timedelta(days=recently_added_days))

    return q.all()


def _rent_filtered(
    db,
    search=None,
    category=None,
    brand=None,
    location=None,
    condition=None,
    min_price=None,
    max_price=None,
    availability_now=False,
    recently_added_days=None,
):
    q = db.query(Equipment).filter(Equipment.listing_status == "active")

    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Equipment.name.ilike(term),
                Equipment.brand.ilike(term),
                Equipment.description.ilike(term),
                Equipment.type.ilike(term),
                Equipment.location.ilike(term),
            )
        )

    if category and category != "all":
        labels = _rent_types_for_category(db, category)
        q = q.filter(Equipment.type.in_(labels) if labels else Equipment.type.in_(["__none__"]))

    if brand and brand != "all":
        q = q.filter(Equipment.brand.ilike(f"%{brand}%"))
    if location and location != "all":
        q = q.filter(Equipment.location.ilike(f"%{location}%"))
    if condition and condition != "all":
        q = q.filter(Equipment.condition == condition)

    if min_price is not None:
        q = q.filter(Equipment.daily_rate >= min_price)
    if max_price is not None:
        q = q.filter(Equipment.daily_rate <= max_price)

    if availability_now:
        active_sub = (
            db.query(EquipmentBooking.equipment_id)
            .filter(EquipmentBooking.status.in_(ACTIVE_BOOKING_STATUS))
            .distinct()
        )
        q = q.filter(
            Equipment.is_available == True,  # noqa: E712
            ~Equipment.id.in_(active_sub),
        )

    if recently_added_days:
        q = q.filter(Equipment.created_at >= datetime.utcnow() - timedelta(days=recently_added_days))

    return q.all()


_EPOCH = datetime(1970, 1, 1)


def _epoch_ts(value) -> float:
    if not value:
        return 0.0
    try:
        return (value - _EPOCH).total_seconds()
    except Exception:
        return 0.0


def _relevance(product_or_equip, search, name_attr="name") -> int:
    name = (getattr(product_or_equip, name_attr) or "").lower()
    term = (search or "").strip().lower()
    if name == term:
        return 0
    if name.startswith(term):
        return 1
    if term in name:
        return 2
    return 3


def _buy_sort_key(p, sort_by, search):
    name = (p.name or "").lower()
    if sort_by == "price":
        return (float(p.price or 0), name)
    if sort_by == "rating":
        return ((p.rating or 0), name)
    if sort_by == "created_at":
        return (_epoch_ts(p.created_at), name)
    if sort_by == "popular":
        pop = (p.total_reviews or 0)
        return (pop, name)
    if sort_by == "name":
        return (0, name)
    if search:
        return (_relevance(p, search), name)
    return (_epoch_ts(p.created_at), name)


def _rent_sort_key(e, sort_by, search, booking_counts):
    name = (e.name or "").lower()
    if sort_by == "price":
        return (float(e.daily_rate or 0), name)
    if sort_by == "rating":
        return (0.0, name)
    if sort_by == "created_at":
        return (_epoch_ts(e.created_at), name)
    if sort_by == "popular":
        return ((booking_counts or {}).get(e.id, 0), name)
    if sort_by == "name":
        return (0, name)
    if search:
        return (_relevance(e, search), name)
    return (_epoch_ts(e.created_at), name)


@router.get("/browse")
def browse_equipment(
    mode: str = Query("all", pattern="^(all|rent|buy)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=60),
    search: Optional[str] = None,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    location: Optional[str] = None,
    condition: Optional[str] = None,
    power_source: Optional[str] = None,
    suitable_use: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: bool = False,
    availability: Optional[str] = Query(None, pattern="^(available_now|any)$"),
    delivery_available: bool = False,
    pickup_available: bool = False,
    verified_sellers: bool = False,
    min_rating: Optional[float] = None,
    recently_added_days: Optional[int] = None,
    sort_by: str = Query("relevance", pattern="^(relevance|price|rating|created_at|popular|name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One unified, paginated catalogue mixing Buy products and Rent machinery."""
    availability_now = availability == "available_now"
    desc_flag = sort_order == "desc"

    candidates = []  # (key0, key1, kind, id, obj)

    booking_counts = None
    if mode in ("all", "rent") and sort_by == "popular":
        booking_counts = dict(
            db.query(
                EquipmentBooking.equipment_id,
                func.count(EquipmentBooking.id),
            )
            .group_by(EquipmentBooking.equipment_id)
            .all()
        )

    if mode in ("all", "buy"):
        for p in _buy_filtered(
            db,
            search=search,
            category=category,
            brand=brand,
            location=location,
            condition=condition,
            power_source=power_source,
            suitable_use=suitable_use,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
            delivery_available=delivery_available,
            pickup_available=pickup_available,
            verified_sellers=verified_sellers,
            min_rating=min_rating,
            recently_added_days=recently_added_days,
            availability_now=availability_now,
        ):
            k0, k1 = _buy_sort_key(p, sort_by, search)
            candidates.append((k0, k1, "buy", p.id, p))

    if mode in ("all", "rent"):
        for e in _rent_filtered(
            db,
            search=search,
            category=category,
            brand=brand,
            location=location,
            condition=condition,
            min_price=min_price,
            max_price=max_price,
            availability_now=availability_now,
            recently_added_days=recently_added_days,
        ):
            k0, k1 = _rent_sort_key(e, sort_by, search, booking_counts)
            candidates.append((k0, k1, "rent", e.id, e))

    candidates.sort(key=lambda c: (c[0], c[1]), reverse=desc_flag)

    # Mixed "All" mode must interleave Buy and Rent so every page shows both
    # types (no single-type pages regardless of sort order).
    if mode == "all" and candidates:
        buy_list = [c for c in candidates if c[2] == "buy"]
        rent_list = [c for c in candidates if c[2] == "rent"]
        interleaved = []
        b, r = 0, 0
        while b < len(buy_list) or r < len(rent_list):
            if r < len(rent_list):
                interleaved.append(rent_list[r])
                r += 1
            if b < len(buy_list):
                interleaved.append(buy_list[b])
                b += 1
        candidates = interleaved

    total = len(candidates)
    start = (page - 1) * limit
    page_items = candidates[start : start + limit]

    items = []
    for _k0, _k1, kind, _oid, obj in page_items:
        if kind == "rent":
            p = _rental_payload(db, obj)
            p["provider"] = _provider_name(db, obj)
        else:
            p = _equipment_payload(db, obj)
            p["mode"] = "buy"
        items.append(p)

    buy_total = sum(1 for c in candidates if c[2] == "buy")
    rent_total = sum(1 for c in candidates if c[2] == "rent")

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit),
            "items": items,
            "aggregate": {"total": total, "buy": buy_total, "rent": rent_total},
        },
    }


# ---------------------------------------------------------------------------
# 9. FARM ACTIVITY TIMELINE
# ---------------------------------------------------------------------------
@router.get("/activity")
def get_farm_equipment_activity(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    events = []
    uid = current_user.id

    for v in (
        db.query(FarmerRecentlyViewed)
        .filter(FarmerRecentlyViewed.user_id == uid)
        .order_by(desc(FarmerRecentlyViewed.viewed_at))
        .limit(60)
        .all()
    ):
        p = v.product
        if not p:
            continue
        events.append({
            "type": "viewed",
            "title": f"Viewed {p.name}",
            "subtitle": "Recently viewed",
            "timestamp": str(v.viewed_at) if v.viewed_at else None,
            "product_id": p.product_id if p.product_id else p.id,
            "image_url": p.image_url,
            "meta": {"price": p.price},
        })

    for b in (
        db.query(EquipmentBooking)
        .filter(EquipmentBooking.farmer_id == uid)
        .order_by(desc(EquipmentBooking.created_at))
        .limit(60)
        .all()
    ):
        equip = db.query(Equipment).filter(Equipment.id == b.equipment_id).first()
        events.append({
            "type": "booking",
            "title": f"{b.status.title()} booking · {equip.name if equip else 'Machinery'}",
            "subtitle": f"{b.booking_date or 'Scheduled'} · {b.duration_days} day(s)",
            "timestamp": str(b.created_at) if b.created_at else None,
            "booking_id": b.booking_id,
            "equipment_id": equip.equipment_id if equip else None,
            "image_url": equip.image_url if equip else None,
            "meta": {"status": b.status, "total_cost": b.total_cost},
        })

    for o in (
        db.query(MarketplaceOrder)
        .filter(MarketplaceOrder.user_id == uid)
        .order_by(desc(MarketplaceOrder.created_at))
        .limit(60)
        .all()
    ):
        events.append({
            "type": "order",
            "title": f"Order {o.order_id} · ₹{int(o.total_amount or 0):,}",
            "subtitle": f"{o.status.title() if o.status else 'Order'} · {o.items[0].product_name if o.items else 'Equipment order'}",
            "timestamp": str(o.created_at) if o.created_at else None,
            "order_id": o.order_id,
            "image_url": (o.items[0].product.image_url if o.items and o.items[0].product else None),
            "meta": {"status": o.status, "total_amount": o.total_amount},
        })

    for w in (
        db.query(MarketplaceWishlist)
        .filter(MarketplaceWishlist.user_id == uid)
        .order_by(desc(MarketplaceWishlist.created_at))
        .limit(60)
        .all()
    ):
        p = w.product
        if not p:
            continue
        events.append({
            "type": "saved",
            "title": f"Saved {p.name}",
            "subtitle": "Added to saved equipment",
            "timestamp": str(w.created_at) if w.created_at else None,
            "product_id": p.product_id if p.product_id else p.id,
            "image_url": p.image_url,
            "meta": {"price": p.price},
        })

    events.sort(key=lambda e: e["timestamp"] or "", reverse=True)
    events = events[:limit]

    return {
        "status": "success",
        "data": {"items": events, "count": len(events)},
    }


# ---------------------------------------------------------------------------
# 10. MY LISTINGS (My Listings - Rent & Buy) - strictly owner-scoped
# ---------------------------------------------------------------------------
@router.get("/mylistings")
def get_my_listings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rent_rows = (
        db.query(Equipment)
        .filter(Equipment.owner_id == current_user.id)
        .order_by(desc(Equipment.created_at))
        .all()
    )
    booking_counts = {}
    if rent_rows:
        booking_counts = dict(
            db.query(
                EquipmentBooking.equipment_id,
                func.count(EquipmentBooking.id),
            )
            .filter(EquipmentBooking.equipment_id.in_([e.id for e in rent_rows]))
            .group_by(EquipmentBooking.equipment_id)
            .all()
        )

    rent_items = []
    for e in rent_rows:
        p = _rental_payload(db, e, booking_counts)
        p["provider"] = _provider_name(db, e)
        rent_items.append(p)

    seller = db.query(Seller).filter(Seller.user_id == current_user.id).first()
    buy_items = []
    if seller:
        for pr in (
            db.query(Product)
            .filter(Product.seller_id == seller.id)
            .order_by(desc(Product.created_at))
            .all()
        ):
            pp = _equipment_payload(db, pr)
            pp["mode"] = "buy"
            buy_items.append(pp)

    return {
        "status": "success",
        "data": {
            "rent": rent_items,
            "buy": buy_items,
            "counts": {"rent": len(rent_items), "buy": len(buy_items)},
        },
    }


@router.post("/mylistings/rent", status_code=201)
def create_rent_listing(
    payload: RentListingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = Equipment(
        equipment_id=generate_id("FA-OWN", db, Equipment),
        name=payload.name.strip(),
        type=payload.type.strip(),
        brand=payload.brand,
        model=payload.model,
        description=payload.description,
        daily_rate=payload.daily_rate,
        hourly_rate=payload.hourly_rate,
        deposit_amount=payload.deposit_amount,
        min_duration_days=payload.min_duration_days,
        rental_terms=payload.rental_terms,
        location=payload.location,
        image_url=payload.image_url,
        condition=payload.condition,
        owner_id=current_user.id,
        is_available=payload.is_available,
        listing_status="active",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    p = _rental_payload(db, item)
    p["provider"] = _provider_name(db, item)
    return {"status": "success", "message": "Rental listing created", "data": p}


@router.put("/mylistings/rent/{equipment_id}")
def update_rent_listing(
    equipment_id: str,
    payload: RentListingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = (
        db.query(Equipment)
        .filter(
            Equipment.owner_id == current_user.id,
            or_(Equipment.id == equipment_id, Equipment.equipment_id == equipment_id),
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Rental listing not found")
    item.name = payload.name.strip()
    item.type = payload.type.strip()
    item.brand = payload.brand
    item.model = payload.model
    item.description = payload.description
    item.daily_rate = payload.daily_rate
    item.hourly_rate = payload.hourly_rate
    item.deposit_amount = payload.deposit_amount
    item.min_duration_days = payload.min_duration_days
    item.rental_terms = payload.rental_terms
    item.location = payload.location
    item.image_url = payload.image_url
    item.condition = payload.condition
    item.is_available = payload.is_available
    db.commit()
    db.refresh(item)
    p = _rental_payload(db, item)
    p["provider"] = _provider_name(db, item)
    return {"status": "success", "message": "Rental listing updated", "data": p}


@router.patch("/mylistings/rent/{equipment_id}/status")
def set_rent_listing_availability(
    equipment_id: str,
    payload: ListingStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = (
        db.query(Equipment)
        .filter(
            Equipment.owner_id == current_user.id,
            or_(Equipment.id == equipment_id, Equipment.equipment_id == equipment_id),
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Rental listing not found")
    item.is_available = payload.is_available
    db.commit()
    return {
        "status": "success",
        "message": "Listing is now available" if payload.is_available else "Listing marked unavailable",
        "data": _rental_payload(db, item),
    }


@router.delete("/mylistings/rent/{equipment_id}")
def delete_rent_listing(
    equipment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = (
        db.query(Equipment)
        .filter(
            Equipment.owner_id == current_user.id,
            or_(Equipment.id == equipment_id, Equipment.equipment_id == equipment_id),
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Rental listing not found")
    active = _active_bookings(db, item.id)
    if active:
        raise HTTPException(
            status_code=409,
            detail=f"{item.name} has {len(active)} active booking(s); cancel them before deleting",
        )
    item.listing_status = "inactive"
    item.is_available = False
    db.commit()
    return {"status": "success", "message": "Rental listing deactivated"}


def _ensure_farmer_seller(db: Session, user: User) -> Seller:
    seller = db.query(Seller).filter(Seller.user_id == user.id).first()
    if seller:
        return seller
    seller = Seller(
        seller_id=generate_id("FA-SFL", db, Seller),
        user_id=user.id,
        shop_name=f"{user.full_name or 'Farmer'}'s Farm Shop",
        location=None,
        rating=0.0,
        total_sales=0,
        is_verified=False,
    )
    db.add(seller)
    db.flush()
    return seller


@router.post("/mylistings/buy", status_code=201)
def create_buy_listing(
    payload: BuyListingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seller = _ensure_farmer_seller(db, current_user)
    cat_slug = (payload.category_slug or payload.category or "").strip().lower()
    cat = (
        db.query(ProductCategory)
        .filter(ProductCategory.slug == cat_slug)
        .first()
    )
    if not cat:
        cat = (
            db.query(ProductCategory)
            .filter(ProductCategory.slug == "other-equipment")
            .first()
        )
    eq_type = RENT_TYPE_BY_SLUG.get(cat_slug) or (
        cat.name if cat else payload.category
    )
    product = Product(
        product_id=generate_id("FA-FSL", db, Product),
        seller_id=seller.id,
        category_id=cat.id if cat else None,
        name=payload.name.strip(),
        description=payload.description,
        price=payload.price,
        unit="unit",
        stock_quantity=payload.stock_quantity,
        min_order_quantity=1,
        image_url=payload.image_url,
        images=[payload.image_url] if payload.image_url else None,
        brand=payload.brand,
        rating=0.0,
        total_reviews=0,
        is_active=True,
        supports_cod=True,
        tags={
            "source": "farmer",
            "equipment_type": eq_type,
            "location": payload.location,
        },
    )
    db.add(product)
    db.flush()
    db.add(
        EquipmentMetadata(
            product_id=product.id,
            equipment_type=eq_type,
            location=payload.location,
            condition=payload.condition,
            delivery_available=payload.delivery_available,
            pickup_available=payload.pickup_available,
        )
    )
    db.commit()
    db.refresh(product)
    p = _equipment_payload(db, product)
    p["mode"] = "buy"
    return {"status": "success", "message": "Buy listing created", "data": p}


@router.put("/mylistings/buy/{product_id}")
def update_buy_listing(
    product_id: str,
    payload: BuyListingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seller = db.query(Seller).filter(Seller.user_id == current_user.id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Buy listing not found")
    product = (
        db.query(Product)
        .filter(
            Product.seller_id == seller.id,
            or_(Product.id == product_id, Product.product_id == product_id),
        )
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Buy listing not found")

    cat_slug = (payload.category_slug or payload.category or "").strip().lower()
    cat = (
        db.query(ProductCategory)
        .filter(ProductCategory.slug == cat_slug)
        .first()
    )
    if not cat:
        cat = (
            db.query(ProductCategory)
            .filter(ProductCategory.slug == "other-equipment")
            .first()
        )
    eq_type = RENT_TYPE_BY_SLUG.get(cat_slug) or (
        cat.name if cat else payload.category
    )

    product.name = payload.name.strip()
    product.description = payload.description
    product.price = payload.price
    product.stock_quantity = payload.stock_quantity
    product.image_url = payload.image_url
    product.images = [payload.image_url] if payload.image_url else product.images
    product.brand = payload.brand
    product.category_id = cat.id if cat else product.category_id
    tags = product.tags if isinstance(product.tags, dict) else {}
    tags["equipment_type"] = eq_type
    tags["location"] = payload.location
    product.tags = tags

    meta = product.equipment_metadata
    if not meta:
        meta = EquipmentMetadata(product_id=product.id)
        db.add(meta)
    meta.equipment_type = eq_type
    meta.location = payload.location
    meta.condition = payload.condition
    meta.delivery_available = payload.delivery_available
    meta.pickup_available = payload.pickup_available

    db.commit()
    db.refresh(product)
    p = _equipment_payload(db, product)
    p["mode"] = "buy"
    return {"status": "success", "message": "Buy listing updated", "data": p}


@router.delete("/mylistings/buy/{product_id}")
def delete_buy_listing(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seller = db.query(Seller).filter(Seller.user_id == current_user.id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Buy listing not found")
    product = (
        db.query(Product)
        .filter(
            Product.seller_id == seller.id,
            or_(Product.id == product_id, Product.product_id == product_id),
        )
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Buy listing not found")
    product.is_active = False
    db.commit()
    return {"status": "success", "message": "Buy listing deactivated"}


# ---------------------------------------------------------------------------
# 11. RENTAL AVAILABILITY (from real bookings)
# ---------------------------------------------------------------------------
@router.get("/rentals/{equipment_id}/availability")
def get_rental_availability(
    equipment_id: str,
    start_date: Optional[str] = None,
    days: int = Query(1, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equip = (
        db.query(Equipment)
        .filter(or_(Equipment.id == equipment_id, Equipment.equipment_id == equipment_id))
        .first()
    )
    if not equip:
        raise HTTPException(status_code=404, detail="Rental equipment not found")

    active = _active_bookings(db, equip.id)
    per_day = None
    if start_date:
        try:
            _s = datetime.strptime(start_date, "%Y-%m-%d")
        except Exception:
            raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD")
        per_day = []
        for i in range(days):
            day = _s + timedelta(days=i)
            iso = day.strftime("%Y-%m-%d")
            end = (day + timedelta(days=1)).strftime("%Y-%m-%d")
            occupied = any(
                _range_overlaps(iso, end, *(_booking_window(b))) for b in active
            )
            per_day.append({
                "date": iso,
                "available": bool(equip.is_available) and not occupied,
            })

    return {
        "status": "success",
        "data": {
            "equipment_id": equip.equipment_id,
            "equipment_name": equip.name,
            "availability": _availability_payload(db, equip),
            "requested_period": {"start_date": start_date, "days": days},
            "per_day": per_day,
        },
    }


# ---------------------------------------------------------------------------
# 7. PRODUCT DETAILS
# ---------------------------------------------------------------------------
@router.get("/products/{product_id}")
@router.get("/{product_id}")
def get_equipment_detail(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = (
        db.query(Product)
        .filter(or_(Product.id == product_id, Product.product_id == product_id), Product.is_active == True)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Equipment product not found")

    # Record view in recently viewed
    try:
        rec = db.query(FarmerRecentlyViewed).filter(
            FarmerRecentlyViewed.user_id == current_user.id,
            FarmerRecentlyViewed.product_id == product.id,
        ).first()
        if rec:
            rec.viewed_at = datetime.utcnow()
        else:
            db.add(FarmerRecentlyViewed(user_id=current_user.id, product_id=product.id))
        db.commit()
    except Exception:
        db.rollback()

    return {
        "status": "success",
        "data": _equipment_payload(db, product),
    }


# ---------------------------------------------------------------------------
# 8. RENTALS (RENT MODE)
# ---------------------------------------------------------------------------
@router.get("/rentals/categories")
def list_rental_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Machine-type rental categories with live equipment counts."""
    items = []
    for slug in RENTABLE_SLUGS:
        labels = _rent_types_for_category(db, slug)
        count = 0
        if labels:
            count = db.query(Equipment).filter(Equipment.type.in_(labels)).count()
        cat = CATEGORY_BY_SLUG[slug]
        items.append({
            "slug": slug,
            "name": cat["name"],
            "icon": cat["icon"],
            "count": count,
            "rentable": True,
        })
    items.sort(key=lambda c: (-c["count"], c["name"]))
    return {"status": "success", "data": {"items": items, "total_categories": len(items)}}


@router.get("/rentals/filters")
def list_rental_filters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    locations = [
        r[0]
        for r in db.query(Equipment.location)
        .filter(Equipment.location.isnot(None), Equipment.location != "")
        .distinct()
        .order_by(Equipment.location)
        .all()
    ]
    min_row = (
        db.query(Equipment.daily_rate)
        .filter(Equipment.daily_rate.isnot(None))
        .order_by(Equipment.daily_rate.asc())
        .first()
    )
    max_row = (
        db.query(Equipment.daily_rate)
        .filter(Equipment.daily_rate.isnot(None))
        .order_by(Equipment.daily_rate.desc())
        .first()
    )
    rate_range = {
        "min": float(min_row[0]) if min_row else 100.0,
        "max": float(max_row[0]) if max_row else 10000.0,
    }
    return {
        "status": "success",
        "data": {
            "locations": locations,
            "rate_range": rate_range,
            "categories": [
                {
                    "slug": slug,
                    "name": CATEGORY_BY_SLUG[slug]["name"],
                    "icon": CATEGORY_BY_SLUG[slug]["icon"],
                }
                for slug in RENTABLE_SLUGS
            ],
        },
    }


@router.get("/rentals/list")
def list_rentals(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    type: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    search: Optional[str] = None,
    min_rate: Optional[float] = None,
    max_rate: Optional[float] = None,
    is_available: Optional[bool] = None,
    sort_by: str = Query("created_at", pattern="^(created_at|rate|name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Equipment)
    if is_available is not None:
        q = q.filter(Equipment.is_available == is_available)
    if type and type != "all":
        q = q.filter(Equipment.type.ilike(f"%{type}%"))
    if category and category != "all":
        labels = _rent_types_for_category(db, category)
        if labels:
            q = q.filter(Equipment.type.in_(labels))
        else:
            q = q.filter(Equipment.type.in_(["__none__"]))
    if location and location != "all":
        q = q.filter(Equipment.location.ilike(f"%{location}%"))
    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Equipment.name.ilike(term),
                Equipment.brand.ilike(term),
                Equipment.description.ilike(term),
                Equipment.type.ilike(term),
                Equipment.location.ilike(term),
            )
        )
    if min_rate is not None:
        q = q.filter(Equipment.daily_rate >= min_rate)
    if max_rate is not None:
        q = q.filter(Equipment.daily_rate <= max_rate)

    total = q.count()

    desc_order = sort_order == "desc"
    if sort_by == "rate":
        q = q.order_by(Equipment.daily_rate.desc() if desc_order else Equipment.daily_rate.asc())
    elif sort_by == "name":
        q = q.order_by(Equipment.name.desc() if desc_order else Equipment.name.asc())
    else:
        q = q.order_by(Equipment.created_at.desc() if desc_order else Equipment.created_at.asc())

    items = q.offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit),
            "items": [_rental_payload(db, e) for e in items],
        },
    }


@router.get("/rentals/my-bookings")
def get_my_rental_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bookings = (
        db.query(EquipmentBooking)
        .filter(EquipmentBooking.farmer_id == current_user.id)
        .order_by(EquipmentBooking.created_at.desc())
        .all()
    )
    return {
        "status": "success",
        "data": {
            "items": [_rental_booking_payload(db, b) for b in bookings],
            "count": len(bookings),
        },
    }


@router.post("/rentals/book", status_code=201)
def book_rental_equipment(
    payload: RentalBookingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equip = (
        db.query(Equipment)
        .filter(or_(Equipment.id == payload.equipment_id, Equipment.equipment_id == payload.equipment_id))
        .first()
    )
    if not equip:
        raise HTTPException(status_code=404, detail="Rental equipment not found")
    if not equip.is_available:
        raise HTTPException(status_code=409, detail="This equipment is currently unavailable for rent")

    min_days = equip.min_duration_days or 1
    if payload.duration_days < min_days:
        raise HTTPException(
            status_code=400,
            detail=f"{equip.type} {equip.name} has a minimum rental period of {min_days} day(s)",
        )

    booking_date = payload.booking_date or datetime.utcnow().strftime("%Y-%m-%d")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if booking_date < today:
        raise HTTPException(
            status_code=400,
            detail="Booking start date cannot be in the past",
        )

    # No double-booking: reject if the requested window overlaps any active booking.
    requested_start = booking_date
    requested_end = (datetime.strptime(booking_date, "%Y-%m-%d") + timedelta(days=payload.duration_days)).strftime("%Y-%m-%d")
    for existing in _active_bookings(db, equip.id):
        e_start, e_end = _booking_window(existing)
        if _range_overlaps(requested_start, requested_end, e_start, e_end):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{equip.name} is already booked {existing.booking_date or 'shortly'} for "
                    f"{existing.duration_days} day(s). Choose different dates."
                ),
            )

    booking_id = generate_id("FA-BKG", db, EquipmentBooking)
    total_cost = (equip.daily_rate or 0) * payload.duration_days

    booking = EquipmentBooking(
        booking_id=booking_id,
        equipment_id=equip.id,
        farmer_id=current_user.id,
        booking_date=booking_date,
        duration_days=payload.duration_days,
        total_cost=total_cost,
        status="requested",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Sync with farm calendar if calendar service exists (shows rental requests)
    try:
        from app.services.calendar_service import sync_equipment_bookings
        sync_equipment_bookings(db, current_user.id)
    except Exception:
        pass

    return {
        "status": "success",
        "data": {
            "booking_id": booking.booking_id,
            "equipment_id": equip.equipment_id,
            "equipment_name": equip.name,
            "equipment_type": equip.type,
            "daily_rate": equip.daily_rate,
            "duration_days": booking.duration_days,
            "total_cost": booking.total_cost,
            "deposit": equip.deposit_amount,
            "rental_terms": equip.rental_terms,
            "booking_date": booking_date,
            "status": booking.status,
            "message": f"Your rental request for {equip.name} for {booking.duration_days} day(s) has been submitted",
        },
    }


@router.patch("/rentals/bookings/{booking_id}")
def cancel_rental_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = (
        db.query(EquipmentBooking)
        .filter(
            EquipmentBooking.booking_id == booking_id,
            EquipmentBooking.farmer_id == current_user.id,
        )
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rental booking not found")

    if booking.status not in ("requested", "confirmed"):
        raise HTTPException(status_code=409, detail=f"A {booking.status} booking cannot be cancelled")

    booking.status = "cancelled"
    db.commit()
    db.refresh(booking)
    return {"status": "success", "message": "Rental request cancelled", "data": _rental_booking_payload(db, booking)}


@router.get("/rentals/{equipment_id}")
def get_rental_detail(
    equipment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equip = (
        db.query(Equipment)
        .filter(or_(Equipment.id == equipment_id, Equipment.equipment_id == equipment_id))
        .first()
    )
    if not equip:
        raise HTTPException(status_code=404, detail="Rental equipment not found")
    return {"status": "success", "data": _rental_payload(db, equip)}


class ReportCreate(BaseModel):
    target_type: str
    target_id: str
    reason: str
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# 11. REPORT LISTING (equipment moderation reports - authenticated farmer only)
# ---------------------------------------------------------------------------
@router.post("/report", status_code=201)
def create_listing_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_type = (payload.target_type or "").strip().lower()
    if target_type not in ("buy", "rent"):
        raise HTTPException(status_code=400, detail="Invalid report target type")

    reason = (payload.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Please select a report reason")
    if len(reason) > 100:
        raise HTTPException(status_code=400, detail="Report reason is too long")

    target = None
    if target_type == "buy":
        target = (
            db.query(Product)
            .filter(or_(Product.id == payload.target_id, Product.product_id == payload.target_id))
            .first()
        )
        if not target:
            raise HTTPException(status_code=404, detail="Equipment listing not found")
    else:
        target = (
            db.query(Equipment)
            .filter(or_(Equipment.id == payload.target_id, Equipment.equipment_id == payload.target_id))
            .first()
        )
        if not target:
            raise HTTPException(status_code=404, detail="Rental listing not found")

    # Idempotency guard: same farmer reporting the same listing within 60s
    cutoff = datetime.utcnow() - timedelta(seconds=60)
    recent = (
        db.query(EquipmentReport)
        .filter(
            EquipmentReport.reporter_id == current_user.id,
            EquipmentReport.target_type == target_type,
            EquipmentReport.target_id == str(target.id),
            EquipmentReport.created_at >= cutoff,
        )
        .first()
    )
    if recent:
        raise HTTPException(
            status_code=429,
            detail="You already reported this listing. Our team is reviewing it.",
        )

    report = EquipmentReport(
        target_type=target_type,
        target_id=str(target.id),
        product_id=str(target.id) if target_type == "buy" else None,
        equipment_id=str(target.id) if target_type == "rent" else None,
        reporter_id=current_user.id,
        reason=reason,
        message=(payload.message or "").strip()[:600] or None,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {
        "status": "success",
        "message": "Thank you. Your report has been submitted for review.",
        "data": {"report_id": report.id, "target_id": str(target.id)},
    }
