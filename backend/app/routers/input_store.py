"""Input Store - specialised agricultural-input storefront API.

The Input Store is intentionally NOT a second e-commerce system. It is a
themed, agriculture-focused view over the existing Marketplace product
database. It reuses the same ``products``, ``product_categories`` and
``sellers`` tables and talks to the shared cart / wishlist / order APIs in
``marketplace.py``.

Everything here is scoped to the authenticated farmer (``get_current_user``)
and only exposes *active* products. All filters, sort options and search are
executed in SQL so the full catalogue is never shipped to the frontend.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user
from app.models.user import User, FarmerProfile
from app.models.marketplace import (
    Product,
    ProductCategory,
    Seller,
    ProductCrop,
)

router = APIRouter(prefix="/api/v1/input-store", tags=["Input Store"])

MAX_LIMIT = 100
DEFAULT_LIMIT = 24

# Canonical crop aliases used by the recommendation engine so a farmer's
# profile ("Paddy", "Rice") matches product crop tags ("paddy", "rice").
CROP_ALIASES = {
    "paddy": ["paddy", "rice", "paddy/rice"],
    "rice": ["paddy", "rice", "paddy/rice"],
    "chilli": ["chilli", "chili", "green chilli"],
    "groundnut": ["groundnut", "peanut"],
    "vegetables": ["vegetables", "vegetable", "veg"],
    "maize": ["maize", "corn"],
    "soybean": ["soybean", "soyabean", "soya"],
    "cotton": ["cotton"],
}


def _normalise_crop(name: str) -> str:
    if not name:
        return ""
    token = str(name).strip().lower()
    if token in CROP_ALIASES:
        return token
    for canonical, aliases in CROP_ALIASES.items():
        if token in aliases:
            return canonical
    return token


def _category_payload(db: Session, category_id: Optional[str]) -> Optional[dict]:
    if not category_id:
        return None
    cat = db.query(ProductCategory).filter(ProductCategory.id == category_id).first()
    if not cat:
        return None
    return {"id": cat.id, "name": cat.name, "slug": cat.slug, "icon": cat.icon}


def _seller_payload(db: Session, seller_id: Optional[str]) -> Optional[dict]:
    if not seller_id:
        return None
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
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


def _product_payload(db: Session, product: Product) -> dict:
    tags = _tags(product)
    crops = sorted({crop.crop_name for crop in product.crops}) if product.crops else []
    payload = {
        "id": product.id,
        "product_id": product.product_id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "mrp": product.original_price if (product.original_price and product.original_price > product.price) else None,
        "original_price": product.original_price,
        "discount": _discount(product),
        "unit": product.unit,
        "pack_size": tags.get("pack_size") or tags.get("pack") or None,
        "stock_quantity": product.stock_quantity,
        "stock_status": _stock_status(product),
        "in_stock": float(product.stock_quantity or 0) > 0,
        "min_order_quantity": product.min_order_quantity,
        "image_url": product.image_url,
        "images": product.images or [product.image_url] if product.image_url else [],
        "brand": product.brand,
        "rating": product.rating,
        "total_reviews": product.total_reviews,
        "is_organic": bool(tags.get("organic")) or "organic" in (product.name or "").lower(),
        "is_verified": bool(tags.get("verified")),
        "crops": crops,
        "crop_names": [c.title() for c in crops],
        "usage": tags.get("usage"),
        "application_rate": tags.get("application_rate") or tags.get("dosage"),
        "safety": tags.get("safety"),
        "manufacturer": tags.get("manufacturer"),
        "certification": tags.get("certification"),
        "specifications": tags.get("specifications"),
        "category": _category_payload(db, product.category_id),
        "seller": _seller_payload(db, product.seller_id),
        "created_at": str(product.created_at) if product.created_at else None,
    }
    return payload


def _apply_filters(
    q,
    search: Optional[str],
    category_id: Optional[str],
    crop: Optional[str],
    brand: Optional[str],
    seller_id: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    in_stock: Optional[bool],
    organic: Optional[bool],
    min_rating: Optional[float],
    db: Session,
):
    q = q.filter(Product.is_active == True)
    if search:
        term = f"%{search}%"
        conditions = [
            Product.name.ilike(term),
            Product.brand.ilike(term),
            Product.description.ilike(term),
        ]
        # Category + seller joins for search
        cat_ids = [
            c.id for c in db.query(ProductCategory).filter(ProductCategory.name.ilike(term)).all()
        ]
        if cat_ids:
            conditions.append(Product.category_id.in_(cat_ids))
        seller_ids = [
            s.id for s in db.query(Seller).filter(or_(Seller.shop_name.ilike(term), Seller.location.ilike(term))).all()
        ]
        if seller_ids:
            conditions.append(Product.seller_id.in_(seller_ids))
        q = q.filter(or_(*conditions))
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if crop:
        crop_tokens = [_normalise_crop(t) for t in crop.replace(",", " ").split() if _normalise_crop(t)]
        if crop_tokens:
            sub = db.query(ProductCrop.product_id).filter(ProductCrop.crop_name.in_(crop_tokens))
            q = q.filter(Product.id.in_(sub))
    if brand:
        q = q.filter(Product.brand == brand)
    if seller_id:
        q = q.filter(Product.seller_id == seller_id)
    if min_price is not None:
        q = q.filter(Product.price >= min_price)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)
    if in_stock:
        q = q.filter(Product.stock_quantity > 0)
    if organic:
        q = q.filter(Product.tags.isnot(None))
        q = q.filter(
            or_(
                Product.tags.like('%"organic": true%'),
                Product.tags.like('%"organic":true%'),
            )
        )
    if min_rating is not None:
        q = q.filter(Product.rating >= min_rating)
    return q


@router.get("/products")
def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    crop: Optional[str] = None,
    brand: Optional[str] = None,
    seller_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: bool = False,
    organic: bool = False,
    min_rating: Optional[float] = None,
    sort_by: str = Query("relevance", pattern="^(relevance|price|rating|created_at|name)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = _apply_filters(
        db.query(Product).join(Product.category, isouter=True).join(Product.seller, isouter=True),
        search=search,
        category_id=category_id,
        crop=crop,
        brand=brand,
        seller_id=seller_id,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        organic=organic,
        min_rating=min_rating,
        db=db,
    )

    desc = sort_order == "desc"
    if sort_by == "price":
        q = q.order_by(Product.price.desc() if desc else Product.price.asc())
    elif sort_by == "rating":
        q = q.order_by(Product.rating.desc() if desc else Product.rating.asc(), Product.created_at.desc())
    elif sort_by == "name":
        q = q.order_by(Product.name.desc() if desc else Product.name.asc())
    else:
        # default: newest products first; relevance ordering applied below
        q = q.order_by(Product.created_at.desc())

    rows = q.all()

    # Relevance ranking (only when a search term is present): exact/name starts-with
    # matches rank above generic brand/category matches.
    if search and sort_by == "relevance":
        term = search.strip().lower()

        def score(row):
            name = (row.name or "").lower()
            brand = (row.brand or "").lower()
            cat = (row.category.name or "") if row.category else ""
            if name == term:
                return 0
            if name.startswith(term):
                return 1
            if term in name:
                return 2
            if term in cat or term in brand:
                return 3
            return 4

        rows.sort(key=lambda r: score(r))

    total = len(rows)
    start = (page - 1) * limit
    items = rows[start:start + limit]

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_product_payload(db, p) for p in items],
        },
    }


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(ProductCategory, Product.id)
        .join(Product, Product.category_id == ProductCategory.id)
        .filter(Product.is_active == True)
        .all()
    )
    grouped = {}
    for cat, _pid in rows:
        entry = grouped.setdefault(
            cat.id,
            {"id": cat.id, "name": cat.name, "slug": cat.slug, "icon": cat.icon, "count": 0},
        )
        entry["count"] += 1

    items = sorted(grouped.values(), key=lambda c: (-c["count"], c["name"]))
    return {"status": "success", "data": {"items": items}}


@router.get("/filters")
def list_filters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    brands = [
        r[0]
        for r in db.query(Product.brand)
        .filter(Product.is_active == True, Product.brand.isnot(None), Product.brand != "")
        .distinct()
        .order_by(Product.brand)
        .all()
    ]
    sellers = [
        {
            "id": s.id,
            "shop_name": s.shop_name,
            "location": s.location,
            "is_verified": bool(s.is_verified),
        }
        for s in db.query(Seller)
        .filter(Seller.id.in_(db.query(Product.seller_id).filter(Product.is_active == True)))
        .order_by(Seller.shop_name)
        .all()
    ]
    crops = [
        r[0]
        for r in db.query(ProductCrop.crop_name)
        .distinct()
        .order_by(ProductCrop.crop_name)
        .all()
    ]
    min_price = db.query(Product.price).filter(Product.is_active == True).order_by(Product.price.asc()).first()
    max_price = db.query(Product.price).filter(Product.is_active == True).order_by(Product.price.desc()).first()
    return {
        "status": "success",
        "data": {
            "brands": brands or [],
            "sellers": sellers or [],
            "crops": [c.title() for c in (crops or [])],
            "price_range": {
                "min": min_price[0] if min_price else 0,
                "max": max_price[0] if max_price else 0,
            },
        },
    }


@router.get("/products/{product_id}")
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not product:
        product = db.query(Product).filter(Product.product_id == product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"status": "success", "data": _product_payload(db, product)}


@router.get("/recommended")
def recommended(
    limit: int = Query(12, ge=1, le=40),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Products matched to the authenticated farmer's actual crops.

    Uses ``farmer_profiles.preferred_crops`` (set during onboarding) and the
    farmer's registered farm location to prefer local sellers. Only crops that
    actually exist in the catalogue contribute matches - no random/fake picks.
    """
    profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == current_user.id).first()
    crops = []
    if profile and profile.preferred_crops:
        crops = [
            _normalise_crop(t)
            for t in str(profile.preferred_crops).replace(",", ",").replace(";", ",").split(",")
            if _normalise_crop(t)
        ]

    if not crops:
        return {"status": "success", "data": {"crops": [], "items": [], "reason": "no_crops"}}

    crop_matches = (
        db.query(ProductCrop.product_id)
        .filter(ProductCrop.crop_name.in_(crops))
        .join(Product, Product.id == ProductCrop.product_id)
        .filter(Product.is_active == True, Product.stock_quantity > 0)
        .distinct()
        .all()
    )
    product_ids = [r[0] for r in crop_matches]
    if not product_ids:
        return {"status": "success", "data": {"crops": crops, "items": [], "reason": "no_matches"}}

    items = (
        db.query(Product)
        .filter(Product.id.in_(product_ids))
        .order_by(Product.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "crops": crops,
            "items": [_product_payload(db, p) for p in items],
            "reason": "matched",
        },
    }