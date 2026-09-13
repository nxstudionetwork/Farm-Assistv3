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

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, and_, desc, asc
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
    labels = [t[0] for t in db.query(Equipment.type).distinct().all() if t[0]]
    return [label for label in labels if slug_for_type(label) == slug]


def _rental_payload(e: Equipment) -> dict:
    slug = slug_for_type(e.type)
    cat = CATEGORY_BY_SLUG.get(slug, {})
    images = []
    if e.image_url:
        images.append(e.image_url)
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
        "owner_id": e.owner_id,
        "provider": "Farm Assist Catalogue" if not e.owner_id else None,
        "category_slug": slug,
        "category_name": cat.get("name", "Other Equipment"),
        "mode": "rent",
        "created_at": str(e.created_at) if e.created_at else None,
    }


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
# 2. CATEGORIES
# ---------------------------------------------------------------------------
@router.get("/categories")
def list_equipment_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    categories = db.query(ProductCategory).filter(
        ProductCategory.slug.in_(EQUIPMENT_CATEGORY_SLUGS)
    ).all()

    # If no slug match found, get all categories with equipment products
    if not categories:
        categories = db.query(ProductCategory).all()

    items = []
    for cat in categories:
        count = db.query(Product).filter(
            Product.category_id == cat.id,
            Product.is_active == True,
        ).count()
        items.append({
            "id": cat.id,
            "name": cat.name,
            "slug": cat.slug,
            "icon": cat.icon or "fa-toolbox",
            "rentable": CATEGORY_BY_SLUG.get(cat.slug, {}).get("rentable", False),
            "count": count,
        })

    # Sort categories with highest count first
    items.sort(key=lambda c: (-c["count"], c["name"]))

    return {
        "status": "success",
        "data": {
            "items": items,
            "total_categories": len(items),
        },
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

    # Sellers
    sellers = [
        {
            "id": s.id,
            "shop_name": s.shop_name,
            "location": s.location,
            "is_verified": bool(s.is_verified),
        }
        for s in db.query(Seller).order_by(Seller.shop_name).all()
    ]

    # Min/Max Price
    min_price_row = base_q.with_entities(Product.price).order_by(Product.price.asc()).first()
    max_price_row = base_q.with_entities(Product.price).order_by(Product.price.desc()).first()

    # Locations (from equipment metadata)
    locations = [
        r[0]
        for r in db.query(EquipmentMetadata.location)
        .filter(EquipmentMetadata.location.isnot(None), EquipmentMetadata.location != "")
        .distinct()
        .order_by(EquipmentMetadata.location)
        .all()
    ]

    return {
        "status": "success",
        "data": {
            "brands": brands or [],
            "power_sources": power_sources,
            "suitable_uses": suitable_uses,
            "crops": crops,
            "sellers": sellers,
            "locations": locations,
            "price_range": {
                "min": float(min_price_row[0]) if min_price_row else 100.0,
                "max": float(max_price_row[0]) if max_price_row else 50000.0,
            },
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
            "items": [_rental_payload(e) for e in items],
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

    booking_id = generate_id("FA-BKG", db, EquipmentBooking)
    total_cost = (equip.daily_rate or 0) * payload.duration_days
    booking_date = payload.booking_date or datetime.utcnow().strftime("%Y-%m-%d")

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
    return {"status": "success", "data": _rental_payload(equip)}
