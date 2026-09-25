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

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.marketplace import (
    MarketplaceCategory,
    MarketplaceListing,
    MarketplaceEnquiry,
    MarketplaceSale,
    MarketplaceSellerSettings,
)
from app.utils.notification_helper import create_notification
from app.routers.marketplace_seller import (
    _find_or_create_conversation,
    _settings_payload,
)

router = APIRouter(prefix="/api/v1/marketplace/browse", tags=["Marketplace - Browse"])


class EnquiryCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    requested_quantity: Optional[float] = Field(None, gt=0)
    offered_price: Optional[float] = Field(None, gt=0)


class PurchaseCreate(BaseModel):
    quantity: float = Field(1, gt=0)
    payment_method: str = "cod"
    idempotency_key: Optional[str] = Field(None, max_length=80)
    delivery_name: Optional[str] = Field(None, max_length=200)
    delivery_phone: Optional[str] = Field(None, max_length=15)
    delivery_address: Optional[str] = Field(None, max_length=1000)


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


PURCHASE_STATUS_LABELS = {
    "pending": "Order placed",
    "confirmed": "Order confirmed",
    "completed": "Delivered",
    "cancelled": "Cancelled",
}

DELIVERY_STATUS_LABELS = {
    "pending": "Awaiting dispatch",
    "dispatched": "Dispatched",
    "pickup": "Ready for pickup",
    "delivered": "Delivered",
}


def _sale_meta(sale: MarketplaceSale) -> dict:
    """Delivery/payment metadata is stored in ``notes`` as JSON so no column has
    to be added to an already-provisioned ``marketplace_sales`` table."""
    if not sale.notes:
        return {}
    try:
        data = json.loads(sale.notes)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _sale_payload(sale: MarketplaceSale, listing: Optional[MarketplaceListing] = None) -> dict:
    listing = listing or sale.listing
    meta = _sale_meta(sale)
    remaining = None
    if listing is not None:
        remaining = max(float(listing.quantity or 0) - float(listing.sold_quantity or 0), 0)
    status = sale.status or "pending"
    delivery_status = sale.delivery_status or "pending"
    return {
        "id": sale.id,
        "sale_id": sale.sale_id,
        "listing_id": sale.listing_id,
        "item_name": listing.title if listing is not None else None,
        "title": listing.title if listing is not None else None,
        "listing_type": listing.listing_type if listing is not None else None,
        "unit": listing.unit if listing is not None else None,
        "quantity": sale.quantity,
        "unit_price": sale.unit_price,
        "total_amount": sale.total_amount,
        "status": status,
        "status_label": PURCHASE_STATUS_LABELS.get(status, "Order placed"),
        "delivery_status": delivery_status,
        "delivery_status_label": DELIVERY_STATUS_LABELS.get(delivery_status, "Awaiting dispatch"),
        "payment_status": sale.payment_status,
        "payment_method": meta.get("payment_method"),
        "delivery_address": meta.get("delivery_address"),
        "delivery_name": meta.get("delivery_name"),
        "delivery_phone": meta.get("delivery_phone"),
        "seller_id": listing.user_id if listing is not None else None,
        "remaining_quantity": remaining,
        "can_cancel": status not in ("completed", "cancelled"),
        "created_at": str(sale.created_at) if sale.created_at else None,
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


def _money(value) -> str:
    return f"{float(value or 0):.2f}"


@router.post("/listings/{listing_id}/purchase", status_code=201)
def purchase_listing(
    listing_id: str,
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Buy a stock listing outright.

    The buyer's identity is always the authenticated JWT user and the seller is
    always read from the listing, so a buyer can never order from themselves and
    can never redirect an order to another farmer. Price and availability are
    re-read from the database; the amount sent by the client is never trusted.
    """
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
        raise HTTPException(status_code=400, detail="You cannot buy your own listing")
    if not (listing.status == "active" and listing.is_active):
        raise HTTPException(status_code=400, detail="This listing is no longer available")

    quantity = float(payload.quantity)
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

    remaining = max(float(listing.quantity or 0) - float(listing.sold_quantity or 0), 0)
    if remaining <= 0:
        raise HTTPException(status_code=409, detail="This item is out of stock")
    if quantity > remaining:
        raise HTTPException(
            status_code=409,
            detail=f"Only {remaining:g} {listing.unit or 'unit'} available",
        )

    unit_price = round(float(listing.price or 0), 2)
    if unit_price <= 0:
        raise HTTPException(status_code=409, detail="This item is no longer purchasable")
    total_amount = round(unit_price * quantity, 2)

    # Duplicate-click protection: the same idempotency key always resolves to the
    # one order it already created, so a double click cannot double-charge.
    if payload.idempotency_key:
        existing = (
            db.query(MarketplaceSale)
            .filter(
                MarketplaceSale.buyer_user_id == current_user.id,
                MarketplaceSale.listing_id == listing.id,
                MarketplaceSale.status != "cancelled",
            )
            .filter(MarketplaceSale.notes.like(f'%"idem": "{payload.idempotency_key}"%'))
            .first()
        )
        if existing:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "data": _sale_payload(existing, listing),
                    "message": "Order already placed",
                },
            )

    method = (payload.payment_method or "cod").strip().lower()
    if method not in ("cod", "wallet", "cash_on_delivery"):
        method = "cod"

    try:
        sale = MarketplaceSale(
            sale_id=generate_id("FA-SAL", db, MarketplaceSale),
            listing_id=listing.id,
            buyer_user_id=current_user.id,
            buyer_name=current_user.full_name,
            buyer_phone=current_user.phone_number,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=total_amount,
            status="pending",
            payment_status="pending",
            delivery_status="pending",
            notes=json.dumps(
                {
                    "idem": payload.idempotency_key,
                    "payment_method": method,
                    "delivery_name": payload.delivery_name or current_user.full_name,
                    "delivery_phone": payload.delivery_phone or current_user.phone_number,
                    "delivery_address": payload.delivery_address,
                    "listing_type": listing.listing_type,
                }
            ),
        )
        db.add(sale)
        db.flush()

        # Availability is reduced here so the card quantity/stock stays correct.
        listing.sold_quantity = round(float(listing.sold_quantity or 0) + quantity, 4)
        if listing.sold_quantity >= float(listing.quantity or 0):
            listing.status = "sold"
            listing.sold_at = datetime.utcnow()
        listing.updated_at = datetime.utcnow()

        when = datetime.utcnow().strftime("%d %b %Y, %I:%M %p")
        seller_message = (
            f"New order received for {listing.title} — {quantity:g} {listing.unit or 'unit'} "
            f"for Rs {_money(total_amount)} (order {sale.sale_id}, {when}). Status: pending."
        )
        create_notification(
            db=db,
            user_id=listing.user_id,
            title="New order received",
            message=seller_message,
            notification_type="order",
            reference_id=sale.id,
            reference_type="marketplace_sale",
            icon="fa-bag-shopping",
            action_url="marketplace.html",
        )
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Order placed successfully",
            message=(
                f"Your order for {listing.title} x {quantity:g} "
                f"({_money(total_amount)}) is confirmed. Reference {sale.sale_id}. "
                "The seller has been notified."
            ),
            notification_type="order",
            reference_id=sale.id,
            reference_type="marketplace_sale",
            icon="fa-receipt",
            action_url="input-store.html",
        )

        db.commit()
        db.refresh(sale)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Order could not be placed. Please try again.")

    return {
        "status": "success",
        "data": _sale_payload(sale, listing),
        "message": "Order placed successfully",
    }


@router.get("/purchases")
def list_my_purchases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sales = (
        db.query(MarketplaceSale)
        .filter(MarketplaceSale.buyer_user_id == current_user.id)
        .order_by(MarketplaceSale.created_at.desc())
        .all()
    )
    return {
        "status": "success",
        "data": [_sale_payload(s) for s in sales],
    }


@router.post("/purchases/{sale_id}/cancel")
def cancel_purchase(
    sale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = (
        db.query(MarketplaceSale)
        .filter(
            (MarketplaceSale.id == sale_id) | (MarketplaceSale.sale_id == sale_id),
            MarketplaceSale.buyer_user_id == current_user.id,
        )
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Order not found")
    if sale.status == "cancelled":
        return {"status": "success", "data": _sale_payload(sale), "message": "Order already cancelled"}
    if sale.status == "completed":
        raise HTTPException(status_code=400, detail="A delivered order cannot be cancelled")

    listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == sale.listing_id).first()
    sale.status = "cancelled"
    sale.payment_status = "refunded" if sale.payment_status == "paid" else sale.payment_status
    sale.updated_at = datetime.utcnow()

    if listing is not None:
        listing.sold_quantity = max(float(listing.sold_quantity or 0) - float(sale.quantity or 0), 0)
        if listing.status == "sold" and listing.sold_quantity < float(listing.quantity or 0):
            listing.status = "active"
            listing.sold_at = None
        listing.updated_at = datetime.utcnow()

    create_notification(
        db=db,
        user_id=listing.user_id if listing is not None else None,
        title="Order cancelled",
        message=(
            f"Order {sale.sale_id} for {listing.title if listing is not None else 'your listing'} "
            "was cancelled by the buyer and the stock has been released."
        ),
        notification_type="order",
        reference_id=sale.id,
        reference_type="marketplace_sale",
        icon="fa-circle-xmark",
        action_url="marketplace.html",
    )
    db.commit()
    db.refresh(sale)
    return {"status": "success", "data": _sale_payload(sale, listing), "message": "Order cancelled"}


@router.post("/sales/{sale_id}/status")
def update_sale_status(
    sale_id: str,
    status: str = Query(..., pattern="^(confirmed|dispatched|completed|cancelled)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Seller-side order lifecycle; every transition notifies the buyer."""
    sale = (
        db.query(MarketplaceSale)
        .filter((MarketplaceSale.id == sale_id) | (MarketplaceSale.sale_id == sale_id))
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Order not found")
    listing = db.query(MarketplaceListing).filter(MarketplaceListing.id == sale.listing_id).first()
    if listing is None or listing.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the seller can update this order")
    if sale.status == "cancelled":
        raise HTTPException(status_code=400, detail="This order was cancelled")

    if status == "cancelled":
        sale.status = "cancelled"
        listing.sold_quantity = max(float(listing.sold_quantity or 0) - float(sale.quantity or 0), 0)
        if listing.status == "sold" and listing.sold_quantity < float(listing.quantity or 0):
            listing.status = "active"
            listing.sold_at = None
    elif status == "completed":
        sale.status = "completed"
        sale.delivery_status = "delivered"
        sale.payment_status = "paid"
        sale.sold_at = datetime.utcnow()
    elif status == "dispatched":
        sale.delivery_status = "dispatched"
        if sale.status == "pending":
            sale.status = "confirmed"
    else:
        sale.status = "confirmed"

    sale.updated_at = datetime.utcnow()
    listing.updated_at = datetime.utcnow()

    titles = {
        "confirmed": "Order confirmed",
        "dispatched": "Order dispatched",
        "completed": "Order delivered",
        "cancelled": "Order cancelled",
    }
    icons = {
        "confirmed": "fa-circle-check",
        "dispatched": "fa-truck-fast",
        "completed": "fa-box-open",
        "cancelled": "fa-circle-xmark",
    }
    create_notification(
        db=db,
        user_id=sale.buyer_user_id,
        title=titles[status],
        message=(
            f"Your order {sale.sale_id} for {listing.title} is now "
            f"{titles[status].lower().replace('order ', '')}."
        ),
        notification_type="order",
        reference_id=sale.id,
        reference_type="marketplace_sale",
        icon=icons[status],
        action_url="input-store.html",
    )
    db.commit()
    db.refresh(sale)
    return {"status": "success", "data": _sale_payload(sale, listing), "message": "Order updated"}