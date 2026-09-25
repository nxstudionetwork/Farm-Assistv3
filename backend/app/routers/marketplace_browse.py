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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id, verify_password
from app.models.user import User
from app.models.marketplace import (
    MarketplaceCategory,
    MarketplaceListing,
    MarketplaceEnquiry,
    MarketplaceSale,
    MarketplaceSellerSettings,
)
from app.models.listing_cart import ListingCart, ListingCartItem, ListingPurchaseKey
from app.models.wallet import Wallet, WalletTransaction
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
    wallet_pin: Optional[str] = Field(None, max_length=20)


class ListingCartAdd(BaseModel):
    quantity: float = Field(1, gt=0)


class ListingCartUpdate(BaseModel):
    quantity: float = Field(..., gt=0)


class ListingCartCheckout(BaseModel):
    payment_method: str = "cod"
    idempotency_key: Optional[str] = Field(None, max_length=80)
    delivery_name: Optional[str] = Field(None, max_length=200)
    delivery_phone: Optional[str] = Field(None, max_length=15)
    delivery_address: Optional[str] = Field(None, max_length=1000)
    wallet_pin: Optional[str] = Field(None, max_length=20)


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


def _payment_method(raw) -> str:
    method = (raw or "cod").strip().lower()
    if method == "cash_on_delivery":
        return "cod"
    return method if method in ("cod", "wallet") else "cod"


def _listing_remaining(listing: MarketplaceListing) -> float:
    return max(float(listing.quantity or 0) - float(listing.sold_quantity or 0), 0)


def _active_listing(db: Session, listing_id: str) -> MarketplaceListing:
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
    if not (listing.status == "active" and listing.is_active):
        raise HTTPException(status_code=400, detail="This listing is no longer available")
    return listing


def _replay_purchase(db: Session, buyer_id: str, idem_key: Optional[str], listing: MarketplaceListing) -> Optional[MarketplaceSale]:
    """Return the order a previous request already created for this key."""
    if not idem_key:
        return None
    key = (
        db.query(ListingPurchaseKey)
        .filter(ListingPurchaseKey.buyer_user_id == buyer_id, ListingPurchaseKey.idem_key == idem_key)
        .first()
    )
    if key and key.sale_id:
        found = db.query(MarketplaceSale).filter(MarketplaceSale.id == key.sale_id).first()
        if found:
            return found
    # Backward compatibility for sales created before the key table existed.
    return (
        db.query(MarketplaceSale)
        .filter(
            MarketplaceSale.buyer_user_id == buyer_id,
            MarketplaceSale.listing_id == listing.id,
        )
        .filter(MarketplaceSale.notes.like(f'%"idem": "{idem_key}"%'))
        .first()
    )


def _record_purchase_key(db: Session, buyer_id: str, idem_key: str, sale: MarketplaceSale) -> None:
    db.add(ListingPurchaseKey(buyer_user_id=buyer_id, idem_key=idem_key, sale_id=sale.id))


def _verify_wallet_payment(db: Session, current_user: User, amount: float, wallet_pin) -> Wallet:
    """Validate the wallet can pay before anything is written."""
    wallet = db.query(Wallet).filter(Wallet.user_id == current_user.id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if not wallet.is_active:
        raise HTTPException(status_code=403, detail="Wallet is inactive")
    if not wallet.is_setup_complete or not wallet.wallet_pin_hash:
        raise HTTPException(status_code=403, detail="Complete wallet setup before paying")
    if not (wallet_pin and verify_password(str(wallet_pin).strip(), wallet.wallet_pin_hash)):
        raise HTTPException(status_code=401, detail="Invalid wallet PIN")
    if round(float(wallet.balance or 0), 2) < amount:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")
    return wallet


def _debit_wallet(db: Session, wallet: Wallet, current_user: User, amount: float, sale_id: str, sale_pk: str) -> None:
    new_balance = round(float(wallet.balance or 0) - amount, 2)
    db.add(
        WalletTransaction(
            transaction_id=generate_id("FA-WTX", db, WalletTransaction),
            wallet_id=wallet.id,
            user_id=current_user.id,
            transaction_type="debit",
            amount=amount,
            balance_after=new_balance,
            description=f"Payment for input store order {sale_id}",
            reference_id=sale_id,
            payment_method="input_store_purchase",
            status="completed",
        )
    )
    wallet.balance = new_balance


def _sale_note(sale: MarketplaceSale) -> dict:
    try:
        value = json.loads(sale.notes or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _refund_wallet(db: Session, buyer: User, amount: float, sale_id: str) -> None:
    wallet = db.query(Wallet).filter(Wallet.user_id == buyer.id).first()
    if wallet is None:
        return
    new_balance = round(float(wallet.balance or 0) + amount, 2)
    db.add(
        WalletTransaction(
            transaction_id=generate_id("FA-WTX", db, WalletTransaction),
            wallet_id=wallet.id,
            user_id=buyer.id,
            transaction_type="credit",
            amount=amount,
            balance_after=new_balance,
            description=f"Refund for cancelled input store order {sale_id}",
            reference_id=sale_id,
            payment_method="input_store_refund",
            status="completed",
        )
    )
    wallet.balance = new_balance


def _notify_new_order(db: Session, current_user: User, listing: MarketplaceListing, sale: MarketplaceSale, quantity: float, total_amount: float) -> None:
    """Tell the selling farmer, then confirm to the buyer. Never the same person."""
    when = datetime.utcnow().strftime("%d %b %Y, %I:%M %p")
    create_notification(
        db=db,
        user_id=listing.user_id,
        title="New order received",
        message=(
            f"New order received for {listing.title} — {quantity:g} {listing.unit or 'unit'} "
            f"for Rs {_money(total_amount)} (order {sale.sale_id}, {when}). Status: pending."
        ),
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
    listing = _active_listing(db, listing_id)
    if listing.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot buy your own listing")

    quantity = float(payload.quantity)
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

    remaining = _listing_remaining(listing)
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

    method = _payment_method(payload.payment_method)

    # Hard idempotency: the unique constraint on (buyer, key) is what actually
    # blocks a double click, so a retry resolves to the one order it already made.
    if payload.idempotency_key:
        replay = _replay_purchase(db, current_user.id, payload.idempotency_key, listing)
        if replay is not None:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "data": _sale_payload(replay, listing),
                    "message": "Order already placed",
                },
            )

    if method == "wallet":
        wallet = _verify_wallet_payment(
            db,
            current_user,
            total_amount,
            payload.wallet_pin,
        )

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
            payment_status="pending" if method != "wallet" else "paid",
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

        if method == "wallet":
            _debit_wallet(db, wallet, current_user, total_amount, sale.sale_id, sale.id)

        _notify_new_order(db, current_user, listing, sale, quantity, total_amount)

        if payload.idempotency_key:
            _record_purchase_key(db, current_user.id, payload.idempotency_key, sale)

        db.commit()
        db.refresh(sale)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        # Lost a race on the idempotency key: the other request won.
        db.rollback()
        replay = _replay_purchase(db, current_user.id, payload.idempotency_key, listing) if payload.idempotency_key else None
        if replay is not None:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "data": _sale_payload(replay, listing),
                    "message": "Order already placed",
                },
            )
        raise HTTPException(status_code=409, detail="This order was already placed. Please refresh.")
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

    # A wallet-paid order is genuinely credited back; COD simply stays unpaid.
    refunded = False
    if sale.payment_status == "paid":
        note = _sale_note(sale)
        if note.get("payment_method") == "wallet":
            _refund_wallet(db, current_user, float(sale.total_amount or 0), sale.sale_id)
            refunded = True

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


# ─────────────────────────── listing (stock) cart ───────────────────────────
# Kept separate from the Product cart in marketplace.py, whose cart_items
# require a products FK. Same shopper, different catalogue.


def _listing_cart_for_user(db: Session, user_id: str) -> ListingCart:
    cart = db.query(ListingCart).filter(ListingCart.user_id == user_id).first()
    if not cart:
        cart = ListingCart(user_id=user_id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart


def _listing_cart_payload(db: Session, cart: ListingCart) -> dict:
    items = []
    stale = []
    cod_available = bool(cart.items)
    for item in list(cart.items):
        listing = item.listing
        if listing is None:
            stale.append(item)
            continue
        remaining = _listing_remaining(listing)
        buyable = bool(listing.status == "active" and listing.is_active and remaining > 0)
        price = round(float(listing.price or 0), 2)
        seller = db.query(User).filter(User.id == listing.user_id).first()
        items.append({
            "id": item.id,
            "listing_id": listing.id,
            "quantity": float(item.quantity or 0),
            "subtotal": round(price * float(item.quantity or 0), 2),
            "available": remaining,
            "buyable": buyable,
            "listing": {
                "id": listing.id,
                "listing_id": listing.listing_id,
                "title": listing.title,
                "price": price,
                "unit": listing.unit,
                "image_url": (listing.image_url if hasattr(listing, "image_url") else None),
                "seller": {"id": listing.user_id, "full_name": seller.full_name if seller else None},
            },
        })
        if not buyable:
            cod_available = False
    if stale:
        for item in stale:
            db.delete(item)
        db.commit()
    return {
        "items": items,
        "total": round(sum(i["subtotal"] for i in items), 2),
        "count": len(items),
        "cod_available": cod_available,
    }


@router.post("/listings/{listing_id}/cart")
def add_listing_to_cart(
    listing_id: str,
    payload: ListingCartAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = _active_listing(db, listing_id)
    if listing.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot buy your own listing")

    quantity = float(payload.quantity)
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

    cart = _listing_cart_for_user(db, current_user.id)
    item = (
        db.query(ListingCartItem)
        .filter(ListingCartItem.cart_id == cart.id, ListingCartItem.listing_id == listing.id)
        .first()
    )
    wanted = quantity + (float(item.quantity) if item else 0.0)
    if wanted > _listing_remaining(listing):
        raise HTTPException(
            status_code=409,
            detail=f"Only {_listing_remaining(listing):g} {listing.unit or 'unit'} available",
        )
    if item:
        item.quantity = wanted
        item.updated_at = datetime.utcnow()
    else:
        db.add(ListingCartItem(cart_id=cart.id, listing_id=listing.id, quantity=quantity))
    cart.updated_at = datetime.utcnow()
    db.commit()
    return {
        "status": "success",
        "data": _listing_cart_payload(db, _listing_cart_for_user(db, current_user.id)),
        "message": "Added to cart",
    }


@router.get("/cart")
def get_listing_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cart = _listing_cart_for_user(db, current_user.id)
    return {"status": "success", "data": _listing_cart_payload(db, cart)}


@router.patch("/cart/{item_id}")
def update_listing_cart_item(
    item_id: str,
    payload: ListingCartUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cart = _listing_cart_for_user(db, current_user.id)
    item = (
        db.query(ListingCartItem)
        .filter(ListingCartItem.id == item_id, ListingCartItem.cart_id == cart.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    quantity = float(payload.quantity)
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")
    if quantity > _listing_remaining(item.listing):
        raise HTTPException(
            status_code=409,
            detail=f"Only {_listing_remaining(item.listing):g} {item.listing.unit or 'unit'} available",
        )
    item.quantity = quantity
    item.updated_at = datetime.utcnow()
    cart.updated_at = datetime.utcnow()
    db.commit()
    return {
        "status": "success",
        "data": _listing_cart_payload(db, _listing_cart_for_user(db, current_user.id)),
        "message": "Cart updated",
    }


@router.delete("/cart/{item_id}")
def remove_listing_cart_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cart = _listing_cart_for_user(db, current_user.id)
    item = (
        db.query(ListingCartItem)
        .filter(ListingCartItem.id == item_id, ListingCartItem.cart_id == cart.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    db.delete(item)
    cart.updated_at = datetime.utcnow()
    db.commit()
    return {
        "status": "success",
        "data": _listing_cart_payload(db, _listing_cart_for_user(db, current_user.id)),
        "message": "Removed from cart",
    }


@router.post("/cart/checkout", status_code=201)
def checkout_listing_cart(
    payload: ListingCartCheckout,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Turn every item in the stock cart into a real order for its own farmer.

    The whole basket is validated before a single row is written, so a failure
    halfway through cannot leave the buyer with a half-placed order.
    """
    cart = _listing_cart_for_user(db, current_user.id)
    if not cart.items:
        raise HTTPException(status_code=400, detail="Your cart is empty")

    method = _payment_method(payload.payment_method)
    replay_key = payload.idempotency_key or f"cart-{cart.id}-{current_user.id}"

    replayed = _replay_cart_sale(db, current_user.id, replay_key)
    if replayed is not None:
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": replayed,
                "message": "Order already placed",
            },
        )

    # ── validate the whole basket first ──
    planned = []
    grand_total = 0.0
    for item in cart.items:
        listing = item.listing
        if listing is None:
            raise HTTPException(status_code=400, detail="A cart item is no longer available")
        if listing.user_id == current_user.id:
            raise HTTPException(status_code=400, detail="You cannot buy your own listing")
        if not (listing.status == "active" and listing.is_active):
            raise HTTPException(status_code=400, detail=f"'{listing.title}' is no longer available")
        remaining = _listing_remaining(listing)
        quantity = float(item.quantity or 0)
        if quantity <= 0:
            raise HTTPException(status_code=400, detail=f"Invalid quantity for '{listing.title}'")
        if quantity > remaining:
            raise HTTPException(
                status_code=409,
                detail=f"Only {remaining:g} {listing.unit or 'unit'} of '{listing.title}' left",
            )
        price = round(float(listing.price or 0), 2)
        if price <= 0:
            raise HTTPException(status_code=400, detail=f"'{listing.title}' is no longer purchasable")
        grand_total = round(grand_total + price * quantity, 2)
        planned.append((item, listing, quantity, price))

    if method == "wallet":
        wallet = _verify_wallet_payment(db, current_user, grand_total, payload.wallet_pin)

    sale_ids = []
    try:
        for index, (item, listing, quantity, unit_price) in enumerate(planned):
            total_amount = round(unit_price * quantity, 2)
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
                payment_status="paid" if method == "wallet" else "pending",
                delivery_status="pending",
                notes=json.dumps({
                    "idem": replay_key,
                    "cart_index": index,
                    "payment_method": method,
                    "delivery_name": payload.delivery_name or current_user.full_name,
                    "delivery_phone": payload.delivery_phone or current_user.phone_number,
                    "delivery_address": payload.delivery_address,
                    "listing_type": listing.listing_type,
                }),
            )
            db.add(sale)
            db.flush()

            listing.sold_quantity = round(float(listing.sold_quantity or 0) + quantity, 4)
            if listing.sold_quantity >= float(listing.quantity or 0):
                listing.status = "sold"
                listing.sold_at = datetime.utcnow()
            listing.updated_at = datetime.utcnow()

            if method == "wallet":
                _debit_wallet(db, wallet, current_user, total_amount, sale.sale_id, sale.id)

            _notify_new_order(db, current_user, listing, sale, quantity, total_amount)
            sale_ids.append(_sale_payload(sale, listing))
            db.delete(item)

        cart.updated_at = datetime.utcnow()
        db.flush()
        db.add(ListingPurchaseKey(buyer_user_id=current_user.id, idem_key=replay_key, sale_id=None))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        again = _replay_cart_sale(db, current_user.id, replay_key)
        if again is not None:
            return JSONResponse(
                status_code=200,
                content={"status": "success", "data": again, "message": "Order already placed"},
            )
        raise HTTPException(status_code=409, detail="This order was already placed. Please refresh.")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Checkout could not be completed. Please try again.")

    return {
        "status": "success",
        "data": {"orders": sale_ids, "count": len(sale_ids), "total": grand_total},
        "message": f"{len(sale_ids)} order(s) placed successfully",
    }


def _replay_cart_sale(db: Session, buyer_id: str, idem_key: str) -> Optional[dict]:
    key = (
        db.query(ListingPurchaseKey)
        .filter(ListingPurchaseKey.buyer_user_id == buyer_id, ListingPurchaseKey.idem_key == idem_key)
        .first()
    )
    if key is None:
        return None
    sales = (
        db.query(MarketplaceSale)
        .filter(MarketplaceSale.buyer_user_id == buyer_id)
        .filter(MarketplaceSale.notes.like(f'%"idem": "{idem_key}"%'))
        .order_by(MarketplaceSale.created_at)
        .all()
    )
    if not sales:
        return None
    return {
        "orders": [_sale_payload(s) for s in sales],
        "count": len(sales),
        "total": round(sum(float(s.total_amount or 0) for s in sales), 2),
    }