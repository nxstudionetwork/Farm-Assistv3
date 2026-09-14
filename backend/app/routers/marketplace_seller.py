"""Marketplace - Farmer SELLING platform API.

The Marketplace is exclusively the farmer's selling side of Farm Assist:

* Farmers list crops, produce, tools, equipment, machinery and other
  agriculture-related goods for sale.
* Every listing and every sale is owned by the authenticated farmer. A farmer
  ID is NEVER trusted from the frontend - ownership is derived from the JWT
  (``get_current_user``) and enforced on every query.
* Buyer enquiries are connected to the existing Messages system (each enquiry
  links a ``conversations`` row) and are never a duplicate messaging channel.
* Input Store products (``products`` catalogue) are NOT exposed here. This
  router only reads/writes ``marketplace_listings`` and its related tables.
"""

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User, FarmerProfile, UserAddress
from app.models.marketplace import (
    MarketplaceCategory,
    MarketplaceListing,
    MarketplaceListingImage,
    MarketplaceEnquiry,
    MarketplaceSale,
    MarketplaceBuyerRecommendation,
)
from app.models.messages import Conversation, ConversationParticipant, Message

router = APIRouter(prefix="/api/v1/marketplace", tags=["Marketplace - Seller"])

LISTING_STATUSES = ["active", "pending", "sold", "paused", "expired", "cancelled"]
SALE_STATUSES = ["pending", "confirmed", "completed", "cancelled"]
PAYMENT_STATUSES = ["pending", "partial", "paid"]
DELIVERY_STATUSES = ["pending", "pickup", "delivered"]
MAX_IMAGES = 5

UNITS = ["kg", "g", "quintal", "tonne", "bag", "pack", "bundle", "piece", "set", "unit", "litre", "dozen"]
PRICING_TYPES = ["fixed", "negotiable"]
CONTACT_METHODS = ["in-app", "phone", "whatsapp"]
ENQUIRY_STATUSES = ["new", "replied", "accepted", "completed", "rejected"]


# ---------------------------------------------------------------------------
# Pydantic payloads
# ---------------------------------------------------------------------------
class ListingCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    category_id: str = Field(..., min_length=1)
    description: Optional[str] = Field(None, max_length=5000)
    quantity: float = Field(gt=0)
    unit: str = "kg"
    price: float = Field(gt=0)
    pricing_type: str = "fixed"
    location: Optional[str] = Field(None, max_length=200)
    availability: Optional[str] = Field(None, max_length=60)
    harvest_date: Optional[str] = Field(None, max_length=20)
    quality_grade: Optional[str] = Field(None, max_length=60)
    condition_type: Optional[str] = Field(None, max_length=20)
    condition_detail: Optional[str] = Field(None, max_length=2000)
    age_year: Optional[str] = Field(None, max_length=60)
    brand: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    usage_details: Optional[str] = Field(None, max_length=2000)
    contact_method: Optional[str] = "in-app"
    notes: Optional[str] = Field(None, max_length=2000)
    status: str = "active"
    images: List[str] = []

    @field_validator("unit")
    @classmethod
    def _unit(cls, v):
        if v not in UNITS:
            raise ValueError(f"Invalid unit. Must be one of: {', '.join(UNITS)}")
        return v

    @field_validator("pricing_type")
    @classmethod
    def _pricing_type(cls, v):
        if v not in PRICING_TYPES:
            raise ValueError(f"Invalid pricing type. Must be one of: {', '.join(PRICING_TYPES)}")
        return v

    @field_validator("contact_method")
    @classmethod
    def _contact_method(cls, v):
        if v not in CONTACT_METHODS:
            raise ValueError(f"Invalid contact method. Must be one of: {', '.join(CONTACT_METHODS)}")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v not in LISTING_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(LISTING_STATUSES)}")
        return v

    @field_validator("images")
    @classmethod
    def _images(cls, v):
        if len(v) > MAX_IMAGES:
            raise ValueError(f"Maximum {MAX_IMAGES} photos allowed per listing")
        return v


class ListingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    category_id: Optional[str] = None
    description: Optional[str] = Field(None, max_length=5000)
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = None
    price: Optional[float] = Field(None, gt=0)
    pricing_type: Optional[str] = None
    location: Optional[str] = Field(None, max_length=200)
    availability: Optional[str] = Field(None, max_length=60)
    harvest_date: Optional[str] = Field(None, max_length=20)
    quality_grade: Optional[str] = Field(None, max_length=60)
    condition_type: Optional[str] = Field(None, max_length=20)
    condition_detail: Optional[str] = Field(None, max_length=2000)
    age_year: Optional[str] = Field(None, max_length=60)
    brand: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    usage_details: Optional[str] = Field(None, max_length=2000)
    contact_method: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = None
    images: Optional[List[str]] = None


class ListingStatusUpdate(BaseModel):
    status: str


class SaleCreate(BaseModel):
    buyer_name: Optional[str] = Field(None, max_length=200)
    buyer_phone: Optional[str] = Field(None, max_length=20)
    quantity: float = Field(gt=0)
    unit_price: Optional[float] = Field(None, gt=0)
    payment_status: str = "pending"
    status: str = "pending"
    notes: Optional[str] = Field(None, max_length=2000)


class SaleUpdate(BaseModel):
    status: Optional[str] = None
    payment_status: Optional[str] = None
    delivery_status: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    notes: Optional[str] = None


class EnquiryReply(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class EnquiryStatusUpdate(BaseModel):
    status: str


class BuyerMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class BuyerRecommendUpdate(BaseModel):
    recommended: bool


def _category_payload(cat):
    if not cat:
        return None
    return {"id": cat.id, "name": cat.name, "slug": cat.slug, "group": cat.group, "icon": cat.icon}


def _listing_payload(db: Session, listing: MarketplaceListing) -> dict:
    sold_quantity = float(listing.sold_quantity or 0)
    remaining = max(float(listing.quantity or 0) - sold_quantity, 0)
    buyer = None
    if listing.sold_quantity and listing.status == "sold":
        latest_sale = (
            db.query(MarketplaceSale)
            .filter(MarketplaceSale.listing_id == listing.id, MarketplaceSale.status == "completed")
            .order_by(MarketplaceSale.created_at.desc())
            .first()
        )
        if latest_sale:
            buyer = {"name": latest_sale.buyer_name, "phone": latest_sale.buyer_phone}
    enquiries_count = db.query(func.count(MarketplaceEnquiry.id)).filter(
        MarketplaceEnquiry.listing_id == listing.id
    ).scalar() or 0
    return {
        "id": listing.id,
        "listing_id": listing.listing_id,
        "title": listing.title,
        "description": listing.description,
        "category": _category_payload(listing.category),
        "category_id": listing.category_id,
        "quantity": listing.quantity,
        "unit": listing.unit,
        "price": listing.price,
        "pricing_type": listing.pricing_type or "fixed",
        "location": listing.location,
        "availability": listing.availability,
        "harvest_date": listing.harvest_date,
        "quality_grade": listing.quality_grade,
        "condition_type": listing.condition_type,
        "condition_detail": listing.condition_detail,
        "age_year": listing.age_year,
        "brand": listing.brand,
        "model": listing.model,
        "usage_details": listing.usage_details,
        "contact_method": listing.contact_method or "in-app",
        "notes": listing.notes,
        "status": listing.status,
        "is_active": bool(listing.is_active),
        "sold_quantity": sold_quantity,
        "remaining_quantity": remaining,
        "total_views": listing.total_views or 0,
        "interested_count": listing.interested_count or 0,
        "enquiries_count": enquiries_count,
        "buyer": buyer,
        "images": [{"url": img.image_url, "sort_order": img.sort_order} for img in (listing.images or [])],
        "sold_at": str(listing.sold_at) if listing.sold_at else None,
        "created_at": str(listing.created_at) if listing.created_at else None,
        "updated_at": str(listing.updated_at) if listing.updated_at else None,
    }


def _sale_payload(db: Session, sale: MarketplaceSale) -> dict:
    listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == sale.listing_id).first()
    buyer_user = None
    if sale.buyer_user_id:
        u = db.query(User).filter(User.id == sale.buyer_user_id).first()
        if u:
            buyer_user = {
                "id": u.id,
                "full_name": u.full_name or sale.buyer_name,
                "phone_number": u.phone_number or sale.buyer_phone,
                "farmer_id": u.farmer_id,
            }
    return {
        "id": sale.id,
        "sale_id": sale.sale_id,
        "listing_id": sale.listing_id,
        "listing": {
            "id": listing.id if listing else None,
            "listing_id": listing.listing_id if listing else None,
            "title": listing.title if listing else "",
            "price": listing.price if listing else None,
            "unit": listing.unit if listing else None,
            "category": _category_payload(listing.category) if listing else None,
            "images": [{"url": img.image_url, "sort_order": img.sort_order} for img in (listing.images or [])] if listing else [],
            "status": listing.status if listing else None,
        },
        "buyer_user_id": sale.buyer_user_id,
        "buyer": buyer_user,
        "buyer_name": sale.buyer_name,
        "buyer_phone": sale.buyer_phone,
        "quantity": sale.quantity,
        "unit_price": sale.unit_price,
        "total_amount": sale.total_amount,
        "status": sale.status,
        "payment_status": sale.payment_status,
        "delivery_status": sale.delivery_status,
        "notes": sale.notes,
        "sold_at": str(sale.sold_at) if sale.sold_at else None,
        "created_at": str(sale.created_at) if sale.created_at else None,
        "updated_at": str(sale.updated_at) if sale.updated_at else None,
    }


def _enquiry_payload(db: Session, enquiry: MarketplaceEnquiry) -> dict:
    listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == enquiry.listing_id).first()
    buyer = None
    if enquiry.buyer_user_id:
        u = db.query(User).filter(User.id == enquiry.buyer_user_id).first()
        if u:
            buyer = {
                "id": u.id,
                "full_name": enquiry.buyer_name or u.full_name,
                "phone_number": enquiry.buyer_phone or u.phone_number,
                "farmer_id": u.farmer_id,
            }
    return {
        "id": enquiry.id,
        "listing_id": enquiry.listing_id,
        "listing": {
            "id": listing.id if listing else None,
            "listing_id": listing.listing_id if listing else None,
            "title": listing.title if listing else "",
            "price": listing.price if listing else None,
            "unit": listing.unit if listing else None,
        },
        "buyer": buyer,
        "buyer_name": enquiry.buyer_name,
        "buyer_phone": enquiry.buyer_phone,
        "message": enquiry.message,
        "status": enquiry.status,
        "conversation_id": enquiry.conversation_id,
        "created_at": str(enquiry.created_at) if enquiry.created_at else None,
        "updated_at": str(enquiry.updated_at) if enquiry.updated_at else None,
    }


def _owner_seller(category_id: Optional[str], db: Session) -> MarketplaceCategory:
    """Parse & verify a category reference (id or slug)."""
    if not category_id:
        return None
    cat = db.query(MarketplaceCategory).filter(
        (MarketplaceCategory.id == category_id) | (MarketplaceCategory.slug == category_id),
        MarketplaceCategory.is_active == True,
    ).first()
    return cat


def _get_owned_listing(listing_id: str, user_id: str, db: Session) -> MarketplaceListing:
    listing = db.query(MarketplaceListing).filter(
        (MarketplaceListing.id == listing_id) | (MarketplaceListing.listing_id == listing_id),
        MarketplaceListing.user_id == user_id,
    ).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
@router.get("/categories")
def list_sell_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cats = (
        db.query(MarketplaceCategory)
        .filter(MarketplaceCategory.is_active == True)
        .order_by(MarketplaceCategory.display_order, MarketplaceCategory.name)
        .all()
    )
    produce = []
    items = []
    for cat in cats:
        entry = _category_payload(cat)
        if cat.group == "produce":
            produce.append(entry)
        else:
            items.append(entry)
    return {"status": "success", "data": {"produce": produce, "items": items, "total": len(cats)}}


# ---------------------------------------------------------------------------
# Dashboard & Insights
# ---------------------------------------------------------------------------
@router.get("/dashboard")
def seller_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.id
    listing_ids = [r[0] for r in db.query(MarketplaceListing.id).filter(MarketplaceListing.user_id == uid).all()]

    base = db.query(MarketplaceListing).filter(MarketplaceListing.user_id == uid)
    active_count = base.filter(MarketplaceListing.status == "active", MarketplaceListing.is_active == True).count()
    pending_count = base.filter(MarketplaceListing.status == "pending", MarketplaceListing.is_active == True).count()
    paused_count = base.filter(MarketplaceListing.status == "paused", MarketplaceListing.is_active == True).count()
    total_listings = base.count()
    # Only listings with remaining stock are awaiting a buyer.
    awaiting_buyer = base.filter(
        MarketplaceListing.status.in_(["active", "pending"]),
        MarketplaceListing.is_active == True,
        MarketplaceListing.quantity > func.coalesce(MarketplaceListing.sold_quantity, 0),
    ).count()

    pending_sales = 0
    confirmed_sales = 0
    completed_sales = 0
    cancelled_sales = 0
    total_sales_value = 0.0
    completed_sale_rows = []
    if listing_ids:
        pending_sales = db.query(func.count(MarketplaceSale.id)).filter(
            MarketplaceSale.listing_id.in_(listing_ids), MarketplaceSale.status == "pending"
        ).scalar() or 0
        confirmed_sales = db.query(func.count(MarketplaceSale.id)).filter(
            MarketplaceSale.listing_id.in_(listing_ids), MarketplaceSale.status == "confirmed"
        ).scalar() or 0
        completed_sales = db.query(func.count(MarketplaceSale.id)).filter(
            MarketplaceSale.listing_id.in_(listing_ids), MarketplaceSale.status == "completed"
        ).scalar() or 0
        cancelled_sales = db.query(func.count(MarketplaceSale.id)).filter(
            MarketplaceSale.listing_id.in_(listing_ids), MarketplaceSale.status == "cancelled"
        ).scalar() or 0
        total_sales_value = db.query(func.coalesce(func.sum(MarketplaceSale.total_amount), 0)).filter(
            MarketplaceSale.listing_id.in_(listing_ids), MarketplaceSale.status == "completed"
        ).scalar() or 0
        completed_sale_rows = (
            db.query(MarketplaceSale)
            .filter(MarketplaceSale.listing_id.in_(listing_ids), MarketplaceSale.status == "completed")
            .order_by(MarketplaceSale.sold_at.desc(), MarketplaceSale.created_at.desc())
            .limit(5)
            .all()
        )

    sold_listings = db.query(MarketplaceListing).filter(
        MarketplaceListing.user_id == uid, MarketplaceListing.status == "sold"
    ).count()

    recently_sold = []
    for sale in completed_sale_rows:
        payload = _sale_payload(db, sale)
        recently_sold.append({
            "id": payload["id"],
            "sale_id": payload["sale_id"],
            "title": payload["listing"]["title"] if payload["listing"] else "",
            "category": (payload["listing"]["category"] or {}).get("name") if payload["listing"] else None,
            "quantity": payload["quantity"],
            "unit": payload["listing"]["unit"] if payload["listing"] else None,
            "total_amount": payload["total_amount"],
            "payment_status": payload["payment_status"],
            "delivery_status": payload["delivery_status"],
            "sold_at": payload["sold_at"] or payload["created_at"],
            "image_url": (payload["listing"]["images"][0]["url"] if payload["listing"] and payload["listing"]["images"] else None),
        })

    return {
        "status": "success",
        "data": {
            "active_listings": active_count,
            "pending_listings": pending_count,
            "paused_listings": paused_count,
            "total_listings": total_listings,
            "awaiting_buyer": awaiting_buyer,
            "pending_sales": pending_sales,
            "confirmed_sales": confirmed_sales,
            "completed_sales": completed_sales,
            "cancelled_sales": cancelled_sales,
            "sold_items": sold_listings,
            "total_sales": {"count": completed_sales, "value": round(total_sales_value, 2)},
            "recently_sold": recently_sold,
            "seller": {
                "id": current_user.id,
                "full_name": current_user.full_name,
                "farmer_id": current_user.farmer_id,
                "phone_number": current_user.phone_number,
            },
        },
    }


@router.get("/insights")
def sales_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.id
    listing_ids = [r[0] for r in db.query(MarketplaceListing.id).filter(MarketplaceListing.user_id == uid).all()]

    # Count wallets of the seller (listings that have completed sales).
    sold_rows = (
        db.query(MarketplaceListing)
        .filter(
            MarketplaceListing.user_id == uid,
            MarketplaceListing.is_active == True,
            MarketplaceListing.status == "sold",
        )
        .all()
    )
    total_items_sold = len(sold_rows)

    completed = []
    if listing_ids:
        completed = (
            db.query(MarketplaceSale)
            .filter(MarketplaceSale.listing_id.in_(listing_ids), MarketplaceSale.status == "completed")
            .all()
        )

    total_quantity_sold = 0.0
    total_sales_value = 0.0
    category_totals = {}
    for sale in completed:
        listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == sale.listing_id).first()
        total_quantity_sold += float(sale.quantity or 0)
        total_sales_value += float(sale.total_amount or 0)
        if listing:
            cat_name = (listing.category.name if listing.category else None) or "Uncategorised"
            category_totals[cat_name] = category_totals.get(cat_name, 0) + float(sale.total_amount or 0)

    most_sold_category = max(category_totals, key=category_totals.get) if category_totals else None

    # Sales trend: aggregate completed sales by calendar month.
    trend = []
    if completed:
        by_month = {}
        now = datetime.utcnow()
        for i in range(5, -1, -1):
            mark = (now - timedelta(days=30 * i)).strftime("%Y-%m")
            by_month[mark] = {"month": mark, "sales": 0, "value": 0.0}
        for sale in completed:
            month = (sale.sold_at or sale.created_at or datetime.utcnow()).strftime("%Y-%m")
            bucket = by_month.setdefault(month, {"month": month, "sales": 0, "value": 0.0})
            bucket["sales"] += 1
            bucket["value"] = round(bucket["value"] + float(sale.total_amount or 0), 2)
        trend = [by_month[k] for k in sorted(by_month.keys())]

    recent = []
    if listing_ids:
        recent_rows = (
            db.query(MarketplaceSale)
            .filter(MarketplaceSale.listing_id.in_(listing_ids), MarketplaceSale.status == "completed")
            .order_by(MarketplaceSale.sold_at.desc(), MarketplaceSale.created_at.desc())
            .limit(5)
            .all()
        )
        for sale in recent_rows:
            payload = _sale_payload(db, sale)
            recent.append({
                "id": payload["id"],
                "sale_id": payload["sale_id"],
                "title": payload["listing"]["title"] if payload["listing"] else "",
                "quantity": payload["quantity"],
                "total_amount": payload["total_amount"],
                "sold_at": payload["sold_at"] or payload["created_at"],
            })

    return {
        "status": "success",
        "data": {
            "has_data": bool(completed),
            "total_items_sold": total_items_sold,
            "total_quantity_sold": round(total_quantity_sold, 2),
            "total_sales_value": round(total_sales_value, 2),
            "most_sold_category": most_sold_category,
            "category_totals": {k: round(v, 2) for k, v in category_totals.items()},
            "sales_trend": trend,
            "recent_sales": recent,
            "sale_count": len(completed),
        },
    }


# ---------------------------------------------------------------------------
# Listings (My Listings)
# ---------------------------------------------------------------------------
@router.get("/listings")
def list_listings(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    location: Optional[str] = None,
    condition_type: Optional[str] = None,
    availability: Optional[str] = None,
    group: Optional[str] = Query(None, pattern="^(produce|items)$"),
    sort: Optional[str] = Query(None, pattern="^(newest|price_asc|price_desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(MarketplaceListing).filter(
        MarketplaceListing.user_id == current_user.id,
    )

    if status:
        if status not in LISTING_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(LISTING_STATUSES)}")
        q = q.filter(MarketplaceListing.status == status)
    else:
        q = q.filter(MarketplaceListing.is_active == True)
    if search:
        term = f"%{search}%"
        q = q.filter(
            or_(
                MarketplaceListing.title.ilike(term),
                MarketplaceListing.description.ilike(term),
                MarketplaceListing.brand.ilike(term),
                MarketplaceListing.model.ilike(term),
            )
        )
    if category_id:
        cat = _owner_seller(category_id, db)
        if not cat:
            raise HTTPException(status_code=400, detail="Invalid category")
        q = q.filter(MarketplaceListing.category_id == cat.id)
    if min_price is not None:
        q = q.filter(MarketplaceListing.price >= min_price)
    if max_price is not None:
        q = q.filter(MarketplaceListing.price <= max_price)
    if location:
        q = q.filter(MarketplaceListing.location.ilike(f"%{location}%"))
    if condition_type:
        q = q.filter(MarketplaceListing.condition_type == condition_type)
    if availability:
        q = q.filter(MarketplaceListing.availability.ilike(f"%{availability}%"))
    if group:
        q = q.join(MarketplaceCategory, MarketplaceListing.category_id == MarketplaceCategory.id).filter(
            MarketplaceCategory.group == group
        )

    total = q.count()
    order_by = MarketplaceListing.created_at.desc()
    if sort == "price_asc":
        order_by = MarketplaceListing.price.asc()
    elif sort == "price_desc":
        order_by = MarketplaceListing.price.desc()
    rows = q.order_by(order_by).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_listing_payload(db, l) for l in rows],
        },
    }


@router.post("/listings", status_code=201)
def create_listing(
    payload: ListingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    category = _owner_seller(payload.category_id, db)
    if not category:
        raise HTTPException(status_code=400, detail="Select a valid sell category")

    listing_id = generate_id("FA-LST", db, MarketplaceListing)
    listing = MarketplaceListing(
        listing_id=listing_id,
        user_id=current_user.id,
        category_id=category.id,
        title=payload.title.strip(),
        description=payload.description,
        quantity=payload.quantity,
        unit=payload.unit,
        price=payload.price,
        pricing_type=payload.pricing_type if payload.pricing_type in PRICING_TYPES else "fixed",
        location=payload.location,
        availability=payload.availability,
        harvest_date=payload.harvest_date,
        quality_grade=payload.quality_grade,
        condition_type=payload.condition_type,
        condition_detail=payload.condition_detail,
        age_year=payload.age_year,
        brand=payload.brand,
        model=payload.model,
        usage_details=payload.usage_details,
        contact_method=payload.contact_method if payload.contact_method in CONTACT_METHODS else "in-app",
        notes=payload.notes,
        status=payload.status if payload.status in LISTING_STATUSES else "active",
        is_active=True,
        total_views=0,
        interested_count=0,
    )
    db.add(listing)
    db.flush()

    for idx, url in enumerate(payload.images[:MAX_IMAGES]):
        db.add(MarketplaceListingImage(listing_id=listing.id, image_url=url, sort_order=idx))

    db.commit()
    db.refresh(listing)
    return {"status": "success", "data": _listing_payload(db, listing)}


@router.get("/listings/{listing_id}")
def get_listing(
    listing_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = _get_owned_listing(listing_id, current_user.id, db)
    return {"status": "success", "data": _listing_payload(db, listing)}


@router.put("/listings/{listing_id}")
def update_listing(
    listing_id: str,
    payload: ListingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = _get_owned_listing(listing_id, current_user.id, db)

    updates = {
        "title": payload.title,
        "description": payload.description,
        "quantity": payload.quantity,
        "unit": payload.unit,
        "price": payload.price,
        "pricing_type": payload.pricing_type,
        "location": payload.location,
        "availability": payload.availability,
        "harvest_date": payload.harvest_date,
        "quality_grade": payload.quality_grade,
        "condition_type": payload.condition_type,
        "condition_detail": payload.condition_detail,
        "age_year": payload.age_year,
        "brand": payload.brand,
        "model": payload.model,
        "usage_details": payload.usage_details,
        "contact_method": payload.contact_method,
        "notes": payload.notes,
        "status": payload.status,
    }
    for field, value in updates.items():
        if value is None:
            continue
        if field == "status" and value not in LISTING_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid listing status")
        if field == "pricing_type" and value not in PRICING_TYPES:
            raise HTTPException(status_code=400, detail="Invalid pricing type")
        if field == "contact_method" and value not in CONTACT_METHODS:
            raise HTTPException(status_code=400, detail="Invalid contact method")
        setattr(listing, field, value)

    if payload.category_id:
        category = _owner_seller(payload.category_id, db)
        if not category:
            raise HTTPException(status_code=400, detail="Invalid category")
        listing.category_id = category.id

    if payload.images is not None:
        if len(payload.images) > MAX_IMAGES:
            raise HTTPException(status_code=400, detail=f"Maximum {MAX_IMAGES} photos allowed")
        db.query(MarketplaceListingImage).filter(MarketplaceListingImage.listing_id == listing.id).delete()
        for idx, url in enumerate(payload.images[:MAX_IMAGES]):
            db.add(MarketplaceListingImage(listing_id=listing.id, image_url=url, sort_order=idx))

    listing.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(listing)
    return {"status": "success", "data": _listing_payload(db, listing)}


@router.patch("/listings/{listing_id}/status")
def update_listing_status(
    listing_id: str,
    payload: ListingStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = _get_owned_listing(listing_id, current_user.id, db)
    status = payload.status
    if status not in LISTING_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(LISTING_STATUSES)}")

    if status == "sold" and listing.status == "sold":
        raise HTTPException(status_code=400, detail="Listing is already marked as sold")

    if status == "sold":
        # Marking sold externally (no sale record) is allowed, but a completed
        # sale should be recorded via POST /listings/{id}/sales for history.
        listing.status = "sold"
        listing.sold_quantity = float(listing.quantity or 0)
        listing.sold_at = listing.sold_at or datetime.utcnow()
        listing.interested_count = listing.interested_count or 0
    elif status == "cancelled":
        listing.status = "cancelled"
        listing.is_active = False
    elif status == "paused":
        if listing.status == "sold":
            raise HTTPException(status_code=400, detail="A sold listing cannot be paused")
        listing.status = "paused"
    elif status == "active":
        if listing.status == "sold":
            raise HTTPException(status_code=400, detail="A sold listing cannot be reactivated")
        listing.status = "active"
        listing.is_active = True
    else:
        listing.status = status
        listing.is_active = True

    listing.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(listing)
    return {"status": "success", "data": _listing_payload(db, listing)}


@router.delete("/listings/{listing_id}")
def delete_listing(
    listing_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = _get_owned_listing(listing_id, current_user.id, db)
    has_sales = (
        db.query(MarketplaceSale)
        .filter(MarketplaceSale.listing_id == listing.id)
        .count()
    )
    if has_sales:
        # Keep history; hide the listing so past sales remain intact.
        listing.is_active = False
        listing.updated_at = datetime.utcnow()
        db.commit()
        return {"status": "success", "data": {"id": listing.id, "soft_deleted": True}, "message": "Listing hidden (sales history kept)"}
    db.delete(listing)
    db.commit()
    return {"status": "success", "data": {"id": listing_id, "soft_deleted": False}, "message": "Listing deleted"}


# ---------------------------------------------------------------------------
# Sales / Orders
# ---------------------------------------------------------------------------
@router.post("/listings/{listing_id}/sales", status_code=201)
def record_sale(
    listing_id: str,
    payload: SaleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = _get_owned_listing(listing_id, current_user.id, db)
    if listing.status not in ["active", "pending", "paused"]:
        raise HTTPException(status_code=400, detail=f"Cannot record a sale for a '{listing.status}' listing")

    if payload.status not in SALE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid sale status. Must be one of: {', '.join(SALE_STATUSES)}")
    if payload.payment_status not in PAYMENT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid payment status. Must be one of: {', '.join(PAYMENT_STATUSES)}")

    available = float(listing.quantity or 0) - float(listing.sold_quantity or 0)
    if payload.quantity > available + 1e-9:
        raise HTTPException(status_code=400, detail=f"Insufficient quantity. Only {available} {listing.unit} available")

    unit_price = payload.unit_price if payload.unit_price is not None else float(listing.price or 0)
    total = round(unit_price * payload.quantity, 2)

    sale_id = generate_id("FA-SAL", db, MarketplaceSale)
    sale = MarketplaceSale(
        sale_id=sale_id,
        listing_id=listing.id,
        buyer_name=payload.buyer_name,
        buyer_phone=payload.buyer_phone,
        quantity=payload.quantity,
        unit_price=unit_price,
        total_amount=total,
        status=payload.status,
        payment_status=payload.payment_status,
        delivery_status="pending",
        notes=payload.notes,
    )
    db.add(sale)
    if payload.status == "completed":
        sale.sold_at = datetime.utcnow()
    db.flush()

    if payload.status in ("confirmed", "completed"):
        listing.sold_quantity = float(listing.sold_quantity or 0) + payload.quantity
        if float(listing.sold_quantity or 0) >= float(listing.quantity or 0) - 1e-9:
            listing.status = "sold"
            listing.sold_at = listing.sold_at or (sale.sold_at or datetime.utcnow())
        listing.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(sale)
    return {"status": "success", "data": _sale_payload(db, sale)}


@router.get("/sales")
def list_sales(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    category_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing_ids = [r[0] for r in db.query(MarketplaceListing.id).filter(MarketplaceListing.user_id == current_user.id).all()]
    if not listing_ids:
        return {"status": "success", "data": {"total": 0, "page": page, "limit": limit, "total_pages": 0, "items": []}}

    q = db.query(MarketplaceSale).filter(MarketplaceSale.listing_id.in_(listing_ids))
    if status:
        if status not in SALE_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(SALE_STATUSES)}")
        q = q.filter(MarketplaceSale.status == status)
    if category_id:
        cat = _owner_seller(category_id, db)
        if not cat:
            raise HTTPException(status_code=400, detail="Invalid category")
        ids = [r[0] for r in db.query(MarketplaceListing.id).filter(
            MarketplaceListing.user_id == current_user.id,
            MarketplaceListing.category_id == cat.id,
        ).all()]
        if not ids:
            return {"status": "success", "data": {"total": 0, "page": page, "limit": limit, "total_pages": 0, "items": []}}
        q = q.filter(MarketplaceSale.listing_id.in_(ids))

    total = q.count()
    rows = q.order_by(MarketplaceSale.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_sale_payload(db, s) for s in rows],
        },
    }


@router.get("/sales/{sale_id}")
def get_sale(
    sale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = db.query(MarketplaceSale).filter(
        (MarketplaceSale.id == sale_id) | (MarketplaceSale.sale_id == sale_id)
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == sale.listing_id).first()
    if not listing or listing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sale not found")
    return {"status": "success", "data": _sale_payload(db, sale)}


@router.patch("/sales/{sale_id}")
def update_sale(
    sale_id: str,
    payload: SaleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = db.query(MarketplaceSale).filter(
        (MarketplaceSale.id == sale_id) | (MarketplaceSale.sale_id == sale_id)
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == sale.listing_id).first()
    if not listing or listing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sale not found")

    if payload.status is not None:
        if payload.status not in SALE_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid sale status. Must be one of: {', '.join(SALE_STATUSES)}")

        previous_status = sale.status
        new_status = payload.status
        sale_qty = float(sale.quantity or 0)

        # Commit stock the first time a sale occupies confirmed/completed state.
        if new_status in ("confirmed", "completed") and previous_status in ("pending", "cancelled"):
            listing.sold_quantity = float(listing.sold_quantity or 0) + sale_qty
        # Restore stock when a committed sale is cancelled.
        if new_status == "cancelled" and previous_status in ("confirmed", "completed"):
            listing.sold_quantity = max(float(listing.sold_quantity or 0) - sale_qty, 0)

        sale.status = new_status
        if new_status == "completed":
            sale.sold_at = sale.sold_at or datetime.utcnow()
            if not listing.sold_at:
                listing.sold_at = datetime.utcnow()
        if new_status == "cancelled":
            sale.sold_at = None

        # Recompute the listing sold state after any stock change.
        if float(listing.sold_quantity or 0) >= float(listing.quantity or 0) - 1e-9:
            if listing.status in ("active", "pending", "paused"):
                listing.status = "sold"
                if not listing.sold_at:
                    listing.sold_at = datetime.utcnow()
        elif listing.status == "sold":
            listing.status = "active"
            listing.sold_at = None
        listing.updated_at = datetime.utcnow()
    if payload.payment_status is not None:
        if payload.payment_status not in PAYMENT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid payment status. Must be one of: {', '.join(PAYMENT_STATUSES)}")
        sale.payment_status = payload.payment_status
    if payload.delivery_status is not None:
        if payload.delivery_status not in DELIVERY_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid delivery status. Must be one of: {', '.join(DELIVERY_STATUSES)}")
        sale.delivery_status = payload.delivery_status
    if payload.buyer_name is not None:
        sale.buyer_name = payload.buyer_name
    if payload.buyer_phone is not None:
        sale.buyer_phone = payload.buyer_phone
    if payload.notes is not None:
        sale.notes = payload.notes

    sale.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(sale)
    return {"status": "success", "data": _sale_payload(db, sale)}


# ---------------------------------------------------------------------------
# Buyer Enquiries (connected to Messages)
# ---------------------------------------------------------------------------
@router.get("/enquiries")
def list_enquiries(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="new|replied|accepted|completed|rejected"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing_ids = [r[0] for r in db.query(MarketplaceListing.id).filter(MarketplaceListing.user_id == current_user.id).all()]
    if not listing_ids:
        return {"status": "success", "data": {"total": 0, "page": page, "limit": limit, "total_pages": 0, "items": []}}

    q = db.query(MarketplaceEnquiry).filter(MarketplaceEnquiry.listing_id.in_(listing_ids))
    if status:
        if status not in ENQUIRY_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid enquiry status")
        q = q.filter(MarketplaceEnquiry.status == status)

    total = q.count()
    rows = q.order_by(MarketplaceEnquiry.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_enquiry_payload(db, e) for e in rows],
        },
    }


def _find_or_create_conversation(db: Session, user_a: str, user_b: str) -> Conversation:
    conv_a = db.query(ConversationParticipant).filter(
        ConversationParticipant.user_id == user_a
    ).subquery()
    found = (
        db.query(ConversationParticipant.conversation_id)
        .join(conv_a, conv_a.c.conversation_id == ConversationParticipant.conversation_id)
        .filter(ConversationParticipant.user_id == user_b)
        .first()
    )
    if found:
        conv = db.query(Conversation).filter(Conversation.id == found.conversation_id, Conversation.type == "direct").first()
        if conv:
            db.query(ConversationParticipant).filter(
                ConversationParticipant.conversation_id == conv.id,
            ).update({"deleted_at": None})
            db.commit()
            return conv

    conv_id = generate_id("FA-CNV", db, Conversation)
    conv = Conversation(conversation_id=conv_id, type="direct", name=None)
    db.add(conv)
    db.flush()
    db.add(ConversationParticipant(conversation_id=conv.id, user_id=user_a))
    db.add(ConversationParticipant(conversation_id=conv.id, user_id=user_b))
    db.commit()
    db.refresh(conv)
    return conv


def _send_message(db: Session, conversation_id: str, sender_id: str, content: str) -> Message:
    msg_id = generate_id("FA-MSG", db, Message)
    message = Message(
        message_id=msg_id,
        conversation_id=conversation_id,
        sender_id=sender_id,
        content=content.strip(),
        message_type="text",
        status="sent",
    )
    db.add(message)
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv:
        conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return message


@router.post("/enquiries/{enquiry_id}/reply", status_code=201)
def reply_enquiry(
    enquiry_id: str,
    payload: EnquiryReply,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enquiry = db.query(MarketplaceEnquiry).filter(MarketplaceEnquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == enquiry.listing_id).first()
    if not listing or listing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    if not enquiry.buyer_user_id:
        raise HTTPException(status_code=400, detail="Cannot reply to this enquiry (no linked buyer account)")

    conversation = None
    if enquiry.conversation_id:
        conversation = db.query(Conversation).filter(Conversation.id == enquiry.conversation_id).first()
    if not conversation:
        conversation = _find_or_create_conversation(db, current_user.id, enquiry.buyer_user_id)
        enquiry.conversation_id = conversation.id

    message = _send_message(db, conversation.id, current_user.id, payload.message)
    enquiry.status = "replied"
    enquiry.updated_at = datetime.utcnow()
    db.commit()

    return {
        "status": "success",
        "data": {
            "id": enquiry.id,
            "conversation_id": conversation.id,
            "message_id": message.message_id,
            "status": enquiry.status,
        },
    }


@router.patch("/enquiries/{enquiry_id}/status")
def update_enquiry_status(
    enquiry_id: str,
    payload: EnquiryStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enquiry = db.query(MarketplaceEnquiry).filter(MarketplaceEnquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == enquiry.listing_id).first()
    if not listing or listing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Enquiry not found")

    if payload.status not in ENQUIRY_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid enquiry status")
    enquiry.status = payload.status
    enquiry.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(enquiry)
    return {"status": "success", "data": _enquiry_payload(db, enquiry)}


# ---------------------------------------------------------------------------
# Potential buyers (seller dashboard "Buyers waiting for your produce" strip)
# ---------------------------------------------------------------------------
@router.get("/buyers")
def list_potential_buyers(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.id

    # Only listings the seller currently has on the market build the buyer pool
    listings = (
        db.query(MarketplaceListing)
        .filter(
            MarketplaceListing.user_id == uid,
            MarketplaceListing.is_active == True,
            MarketplaceListing.status.in_(["active", "pending"]),
        )
        .all()
    )

    if not listings:
        return {"status": "success", "data": {"total": 0, "page": page, "limit": limit, "items": []}}

    listing_ids = [l.id for l in listings]
    cat_names = set()
    for l in listings:
        if l.category and l.category.name:
            cat_names.add(l.category.name.strip().lower())

    # 1. Buyers who actually enquired on the seller's listings
    enq_rows = (
        db.query(MarketplaceEnquiry)
        .filter(
            MarketplaceEnquiry.listing_id.in_(listing_ids),
            MarketplaceEnquiry.buyer_user_id.isnot(None),
            MarketplaceEnquiry.buyer_user_id != uid,
        )
        .all()
    )
    enq_by_buyer: dict = {}
    for e in enq_rows:
        enq_by_buyer.setdefault(e.buyer_user_id, []).append(e)
    candidate_ids = set(enq_by_buyer.keys())

    # 2. Buyers whose preferred crops overlap the seller's listed categories
    if cat_names:
        profiles = (
            db.query(FarmerProfile)
            .filter(FarmerProfile.preferred_crops.isnot(None), FarmerProfile.user_id != uid)
            .all()
        )
        for p in profiles:
            crops = [c.strip().lower() for c in (p.preferred_crops or "").split(",") if c.strip()]
            if any(c and (any(c in n or n in c for n in cat_names)) for c in crops):
                candidate_ids.add(p.user_id)

    if not candidate_ids:
        return {"status": "success", "data": {"total": 0, "page": page, "limit": limit, "items": []}}

    users = db.query(User).filter(User.id.in_(candidate_ids), User.is_active == True).all()
    if not users:
        return {"status": "success", "data": {"total": 0, "page": page, "limit": limit, "items": []}}

    user_map = {u.id: u for u in users}

    recs = (
        db.query(MarketplaceBuyerRecommendation)
        .filter(MarketplaceBuyerRecommendation.seller_id == uid)
        .all()
    )
    rec_by_buyer = {r.buyer_id: r for r in recs}

    addrs = db.query(UserAddress).filter(UserAddress.user_id.in_(candidate_ids)).all()
    addr_by_user: dict = {}
    for a in addrs:
        addr_by_user.setdefault(a.user_id, []).append(a)

    def _location_for(u: User) -> Optional[str]:
        p = u.farmer_profile if isinstance(u.farmer_profile, FarmerProfile) else None
        if p and p.farm_location:
            return p.farm_location
        lst = addr_by_user.get(u.id) or []
        pri = next((a for a in lst if a.is_primary), (lst[0] if lst else None))
        if pri:
            parts = [pri.village, pri.mandal, pri.district, pri.state]
            parts = [x for x in parts if x]
            return ", ".join(parts) or None
        return None

    def _crop_tokens(u: User) -> List[str]:
        p = u.farmer_profile if isinstance(u.farmer_profile, FarmerProfile) else None
        if not p or not p.preferred_crops:
            return []
        return [c.strip() for c in p.preferred_crops.split(",") if c.strip()]

    items = []
    for u in users:
        enqs = enq_by_buyer.get(u.id, [])
        crops = [c.lower() for c in _crop_tokens(u)]
        matched = []
        for l in listings:
            l_cat = (l.category.name or "").strip().lower() if l.category else ""
            on_enq = any(e.listing_id == l.id for e in enqs)
            pref_match = any(l_cat and c and (c in l_cat or l_cat in c) for c in crops)
            if on_enq or pref_match:
                matched.append(l)
        prefs = _crop_tokens(u)[:4]
        for l in matched:
            if l.category and l.category.name and l.category.name.lower() not in [x.lower() for x in prefs] and len(prefs) < 4:
                prefs.append(l.category.name)
        latest_enq = max(enqs, key=lambda e: e.created_at or datetime.min) if enqs else None
        phone = None
        if enqs:
            phone = (latest_enq.buyer_phone if latest_enq and latest_enq.buyer_phone else None) or u.phone_number
        last_at = latest_enq.created_at.isoformat() if latest_enq and latest_enq.created_at else None
        is_rec = u.id in rec_by_buyer
        items.append({
            "id": u.id,
            "full_name": u.full_name,
            "farmer_id": u.farmer_id,
            "phone_number": phone,
            "location": _location_for(u),
            "preferences": prefs,
            "matched_listings": {"count": len(matched), "titles": [l.title for l in matched[:3]]},
            "enquiries_count": len(enqs),
            "last_enquired_at": last_at,
            "is_recommended": is_rec,
            "recommendation_id": rec_by_buyer[u.id].recommendation_id if is_rec else None,
            "profile_image": u.profile_image,
        })

    items.sort(key=lambda b: (0 if b["is_recommended"] else 1, b["last_enquired_at"] or "", b["full_name"] or ""))
    total = len(items)
    start = (page - 1) * limit
    paged = items[start:start + limit]

    return {"status": "success", "data": {"total": total, "page": page, "limit": limit, "items": paged}}


@router.post("/buyers/{buyer_id}/message", status_code=201)
def message_buyer(
    buyer_id: str,
    payload: BuyerMessage,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if buyer_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot message yourself")
    buyer = db.query(User).filter(User.id == buyer_id, User.is_active == True).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")

    conversation = _find_or_create_conversation(db, current_user.id, buyer.id)
    message = _send_message(db, conversation.id, current_user.id, payload.message)
    return {
        "status": "success",
        "data": {
            "conversation_id": conversation.id,
            "conversation_public_id": conversation.conversation_id,
            "message_id": message.message_id,
            "buyer_id": buyer.id,
            "buyer_name": buyer.full_name,
            "status": message.status,
        },
    }


@router.post("/buyers/{buyer_id}/recommend")
def set_buyer_recommendation(
    buyer_id: str,
    payload: BuyerRecommendUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if buyer_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot recommend yourself")
    buyer = db.query(User).filter(User.id == buyer_id, User.is_active == True).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")

    existing = (
        db.query(MarketplaceBuyerRecommendation)
        .filter(
            MarketplaceBuyerRecommendation.seller_id == current_user.id,
            MarketplaceBuyerRecommendation.buyer_id == buyer.id,
        )
        .first()
    )

    if payload.recommended:
        if not existing:
            existing = MarketplaceBuyerRecommendation(
                recommendation_id=generate_id("FA-BRC", db, MarketplaceBuyerRecommendation),
                seller_id=current_user.id,
                buyer_id=buyer.id,
            )
            db.add(existing)
            db.commit()
            db.refresh(existing)
        return {
            "status": "success",
            "data": {
                "buyer_id": buyer.id,
                "recommended": True,
                "recommendation_id": existing.recommendation_id,
            },
        }

    if existing:
        db.delete(existing)
        db.commit()
    return {
        "status": "success",
        "data": {"buyer_id": buyer.id, "recommended": False, "recommendation_id": None},
    }
