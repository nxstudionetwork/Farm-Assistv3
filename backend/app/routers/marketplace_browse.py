"""Marketplace - BUYER facing API.

Farmers sell through ``marketplace_seller``; their active listings are browsed
here by other authenticated users (buyers). Buyers can open a listing and send
an enquiry that lands straight into the farmer's Buyer Enquiries tab and their
Messages conversation.

Ownership is never trusted from the frontend: the enquiry's buyer is always the
authenticated JWT user, and the listing's owner is read from the database.
The farmer's Marketplace settings control what a buyer can see/do:

* ``allow_buyer_enquiries`` -> guards the enquiry endpoint.
* ``show_contact_to_buyers`` / ``show_location_to_buyers`` -> fields returned.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user
from app.models.user import User
from app.models.marketplace import (
    MarketplaceCategory,
    MarketplaceListing,
    MarketplaceEnquiry,
    MarketplaceSellerSettings,
)
from app.routers.marketplace_seller import (
    _find_or_create_conversation,
    _settings_payload,
)

router = APIRouter(prefix="/api/v1/marketplace/browse", tags=["Marketplace - Browse"])


class EnquiryCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    requested_quantity: Optional[float] = Field(None, gt=0)
    offered_price: Optional[float] = Field(None, gt=0)


def _browse_listing_payload(db: Session, listing: MarketplaceListing, settings: Optional[MarketplaceSellerSettings], viewer_id: str) -> dict:
    show_location = not settings or bool(settings.show_location_to_buyers)
    show_contact = not settings or bool(settings.show_contact_to_buyers)
    seller = db.query(User).filter(User.id == listing.user_id).first()
    return {
        "id": listing.id,
        "listing_id": listing.listing_id,
        "title": listing.title,
        "description": listing.description,
        "category": (
            {"id": listing.category.id, "name": listing.category.name, "slug": listing.category.slug,
             "group": listing.category.group} if listing.category else None
        ),
        "quantity": listing.quantity,
        "unit": listing.unit,
        "price": listing.price,
        "pricing_type": listing.pricing_type or "fixed",
        "location": listing.location if show_location else None,
        "availability": listing.availability,
        "harvest_date": listing.harvest_date,
        "quality_grade": listing.quality_grade,
        "condition_type": listing.condition_type,
        "condition_detail": listing.condition_detail if listing.condition_type == "used" else None,
        "age_year": listing.age_year,
        "brand": listing.brand,
        "model": listing.model,
        "usage_details": listing.usage_details,
        "contact_method": listing.contact_method if show_contact else None,
        "status": listing.status,
        "remaining_quantity": max(float(listing.quantity or 0) - float(listing.sold_quantity or 0), 0),
        "total_views": listing.total_views or 0,
        "images": [{"url": img.image_url, "sort_order": img.sort_order} for img in (listing.images or [])],
        "created_at": str(listing.created_at) if listing.created_at else None,
        "seller": {
            "id": seller.id if seller else None,
            "full_name": seller.full_name if seller else None,
            "farmer_id": seller.farmer_id if seller else None,
        } if show_contact else {"id": seller.id if seller else None, "full_name": None, "farmer_id": None},
        "is_owner": listing.user_id == viewer_id,
        "can_enquire": bool(listing.user_id != viewer_id and (not settings or bool(settings.allow_buyer_enquiries))),
    }


def _enquiry_payload(enquiry: MarketplaceEnquiry) -> dict:
    return {
        "id": enquiry.id,
        "listing_id": enquiry.listing_id,
        "status": enquiry.status,
        "conversation_id": enquiry.conversation_id,
        "created_at": str(enquiry.created_at) if enquiry.created_at else None,
    }


@router.get("/listings")
def browse_listings(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    search: Optional[str] = None,
    category_id: Optional[str] = None,
    group: Optional[str] = Query(None, pattern="^(produce|items)$"),
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    location: Optional[str] = None,
    availability: Optional[str] = None,
    sort: Optional[str] = Query(None, pattern="^(newest|price_asc|price_desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(MarketplaceListing).join(MarketplaceCategory, MarketplaceListing.category_id == MarketplaceCategory.id).filter(
        MarketplaceListing.status == "active",
        MarketplaceListing.is_active == True,  # noqa: E712
        MarketplaceListing.is_deleted == False,  # noqa: E712
        MarketplaceListing.user_id != current_user.id,
        MarketplaceCategory.is_active == True,  # noqa: E712
    )
    if search:
        term = f"%{search}%"
        q = q.filter(
            MarketplaceListing.title.ilike(term)
            | MarketplaceListing.description.ilike(term)
            | MarketplaceListing.brand.ilike(term)
            | MarketplaceListing.model.ilike(term)
        )
    if category_id:
        category = db.query(MarketplaceCategory).filter(
            (MarketplaceCategory.id == category_id) | (MarketplaceCategory.slug == category_id),
            MarketplaceCategory.is_active == True,  # noqa: E712
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Invalid category")
        q = q.filter(MarketplaceListing.category_id == category.id)
    if group:
        q = q.filter(MarketplaceCategory.group == group)
    if min_price is not None:
        q = q.filter(MarketplaceListing.price >= min_price)
    if max_price is not None:
        q = q.filter(MarketplaceListing.price <= max_price)
    if location:
        q = q.filter(MarketplaceListing.location.ilike(f"%{location}%"))
    if availability:
        q = q.filter(MarketplaceListing.availability.ilike(f"%{availability}%"))

    total = q.count()
    if sort == "price_asc":
        order_by = MarketplaceListing.price.asc()
    elif sort == "price_desc":
        order_by = MarketplaceListing.price.desc()
    else:
        order_by = MarketplaceListing.created_at.desc()
    rows = q.order_by(order_by).offset((page - 1) * limit).limit(limit).all()

    settings = db.query(MarketplaceSellerSettings).filter(
        MarketplaceSellerSettings.user_id == current_user.id
    ).first()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_browse_listing_payload(db, l, settings, current_user.id) for l in rows],
        },
    }


@router.get("/listings/{listing_id}")
def browse_listing_detail(
    listing_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = (
        db.query(MarketplaceListing)
        .filter(
            (MarketplaceListing.id == listing_id) | (MarketplaceListing.listing_id == listing_id),
            MarketplaceListing.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    settings = db.query(MarketplaceSellerSettings).filter(
        MarketplaceSellerSettings.user_id == listing.user_id
    ).first()

    # A hidden (cancelled/sold/paused/expired) listing is only visible to its owner.
    if not (listing.status == "active" and listing.is_active):
        if listing.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Listing not found")
        payload = _browse_listing_payload(db, listing, settings, current_user.id)
        payload["seller"] = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "farmer_id": current_user.farmer_id,
        }
        payload["is_owner"] = True
        return {"status": "success", "data": payload}

    # Track a real view for the owner's insights.
    listing.total_views = (listing.total_views or 0) + 1
    listing.updated_at = datetime.utcnow()
    db.commit()

    return {"status": "success", "data": _browse_listing_payload(db, listing, settings, current_user.id)}


@router.post("/listings/{listing_id}/enquire", status_code=201)
def create_enquiry(
    listing_id: str,
    payload: EnquiryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = (
        db.query(MarketplaceListing)
        .filter(
            (MarketplaceListing.id == listing_id) | (MarketplaceListing.listing_id == listing_id),
            MarketplaceListing.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot enquire about your own listing")
    if not (listing.status == "active" and listing.is_active):
        raise HTTPException(status_code=400, detail="This listing is no longer available")

    settings = db.query(MarketplaceSellerSettings).filter(
        MarketplaceSellerSettings.user_id == listing.user_id
    ).first()
    if settings is not None and not settings.allow_buyer_enquiries:
        raise HTTPException(status_code=400, detail="This seller is currently not accepting buyer enquiries")

    enquiry = MarketplaceEnquiry(
        listing_id=listing.id,
        buyer_user_id=current_user.id,
        buyer_name=current_user.full_name,
        buyer_phone=current_user.phone_number,
        message=payload.message.strip(),
        requested_quantity=payload.requested_quantity,
        offered_price=payload.offered_price,
        status="new",
    )
    db.add(enquiry)
    db.flush()

    conversation = _find_or_create_conversation(db, current_user.id, listing.user_id)
    enquiry.conversation_id = conversation.id
    enquiry.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(enquiry)

    return {
        "status": "success",
        "data": _enquiry_payload(enquiry),
        "message": "Your enquiry has been sent to the seller",
    }