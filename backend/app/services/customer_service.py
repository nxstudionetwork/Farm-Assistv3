"""
Shared customer-account logic.

Everything here operates on the *authenticated* user, never on an ID supplied
by the caller. That is the whole point of the module: a customer endpoint takes
a token, resolves the customer from it, and can therefore only ever reach its
own records. Passing a ``customer_id`` in a query string to see somebody
else's orders is not a pattern that exists anywhere in here.
"""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.customer import (
    Customer, CustomerPlant, CustomerPointsEntry, CustomerSettings,
)
from app.models.user import User, UserAddress
from app.utils.auth import generate_id, user_role

#: Credited once, at registration, and recorded in the ledger like every other
#: movement so the balance a customer sees is always explainable.
WELCOME_POINTS = 100

POINTS_REASON_WELCOME = "welcome_bonus"


def get_customer_for_user(db: Session, user: User) -> Optional[Customer]:
    """The customer profile owned by ``user``, or None."""
    return (
        db.query(Customer)
        .filter(Customer.user_id == user.id)
        .first()
    )


def require_customer(db: Session, user: User) -> Customer:
    """Resolve the customer profile for ``user`` or fail with a 403.

    Reaching a customer-only endpoint without a customer profile means the
    role and the data are out of step, which is a server-side integrity problem
    rather than something the caller did, so it is a 403 and not a 404.
    """
    customer = get_customer_for_user(db, user)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No customer account is linked to this login.",
        )
    return customer


def verification_status_for(user: User) -> str:
    """The honest verification posture of an account.

    Derived only from channels the OTP service actually confirmed, so there is
    no code path that can report a customer as verified on the strength of
    something they merely typed.
    """
    phone = bool(getattr(user, "phone_verified", False))
    email = bool(getattr(user, "email_verified", False))
    if phone and email:
        return "verified"
    if phone:
        return "phone_verified"
    if email:
        return "email_verified"
    return "pending"


def sync_customer_from_user(db: Session, user: User, customer: Optional[Customer] = None) -> Customer:
    """Mirror the authoritative user fields onto the customer profile.

    ``users`` owns the contact details and the verification ledger. The
    customer profile keeps a copy so customer-facing reads do not have to join,
    and this function is the single place that copy is refreshed -- called
    after registration, after an OTP is verified, and after any contact change.
    """
    customer = customer or get_customer_for_user(db, user)
    if customer is None:
        return None
    customer.full_name = user.full_name
    customer.phone_number = user.phone_number
    customer.email = user.email
    customer.preferred_language = user.preferred_language or "en"
    customer.phone_verified = bool(getattr(user, "phone_verified", False))
    customer.email_verified = bool(getattr(user, "email_verified", False))
    customer.verification_status = verification_status_for(user)
    customer.updated_at = datetime.utcnow()
    return customer


def award_points(
    db: Session,
    customer: Customer,
    points: int,
    reason: str,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
) -> CustomerPointsEntry:
    """Move the customer's points balance and write the matching ledger row."""
    # The ledger row points at customers.id, which is only assigned when the
    # profile is flushed. Callers that award on the way in (registration) have
    # not flushed yet, so do it here rather than making every caller remember.
    if customer.id is None:
        db.flush()

    balance = int(customer.points_balance or 0) + int(points)
    if balance < 0:
        balance = 0
    entry = CustomerPointsEntry(
        entry_id=generate_id("FA-CPT", db, CustomerPointsEntry),
        customer_pk=customer.id,
        customer_id=customer.customer_id,
        user_id=customer.user_id,
        points=int(points),
        reason=reason,
        balance_after=balance,
        reference_type=reference_type,
        reference_id=reference_id,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    customer.points_balance = balance
    return entry


def points_history(db: Session, customer: Customer, limit: int = 25):
    """The customer's own points movements, newest first.

    Scoped by ``customer_pk``, which was resolved from the authenticated user,
    so there is no way to ask for another customer's ledger.
    """
    return (
        db.query(CustomerPointsEntry)
        .filter(CustomerPointsEntry.customer_pk == customer.id)
        .order_by(
            CustomerPointsEntry.created_at.desc(),
            CustomerPointsEntry.id.desc(),
        )
        .limit(max(1, min(int(limit), 100)))
        .all()
    )


def customer_settings_payload(settings: CustomerSettings) -> dict:
    """Customer preference sheet as returned to the client."""
    return {
        "notifications": {
            "orders": bool(settings.notif_orders),
            "products": bool(settings.notif_products),
            "grow": bool(settings.notif_grow),
            "community": bool(settings.notif_community),
            "points": bool(settings.notif_points),
        },
        "shopping": {
            "default_address_id": settings.shopping_default_address_id,
            "preferences": settings.shopping_preferences or {},
        },
        "grow": {
            "reminders": bool(settings.grow_reminders),
            "plant_care_reminders": bool(settings.plant_care_reminders),
        },
        "community": {
            "notifications": bool(settings.community_notifications),
            "privacy": settings.community_privacy or {},
        },
        "app": {
            "language": settings.language or "en",
            "theme": settings.theme or "system",
            "text_size": settings.text_size or "medium",
            "reduce_motion": bool(settings.reduce_motion),
        },
    }


def get_or_create_customer_settings(db: Session, user: User) -> CustomerSettings:
    """Fetch the customer's preferences, creating the row on first read.

    Created lazily rather than at registration so an account that exists from
    an older build still gets a complete settings sheet.
    """
    settings = (
        db.query(CustomerSettings)
        .filter(CustomerSettings.user_id == user.id)
        .first()
    )
    if settings is None:
        settings = CustomerSettings(user_id=user.id, language=user.preferred_language or "en")
        db.add(settings)
        db.flush()
    return settings


def address_payload(address: UserAddress) -> dict:
    return {
        "id": address.id,
        "address_line": address.address_line,
        "village": address.village,
        "mandal": address.mandal,
        "district": address.district,
        "state": address.state,
        "country": address.country or "India",
        "pincode": address.pincode,
        "latitude": address.latitude,
        "longitude": address.longitude,
        "is_primary": bool(address.is_primary),
    }


def customer_summary_payload(db: Session, user: User, customer: Customer) -> dict:
    """The customer profile the header and profile screen both need.

    Everything here is read from the authenticated user's own rows, so the same
    function is safe to call from any customer endpoint.
    """
    from app.models.marketplace import MarketplaceCart, MarketplaceOrder, MarketplaceWishlist

    orders = (
        db.query(MarketplaceOrder)
        .filter(MarketplaceOrder.user_id == user.id)
        .count()
    )
    wishlist = (
        db.query(MarketplaceWishlist)
        .filter(MarketplaceWishlist.user_id == user.id)
        .count()
    )
    addresses = (
        db.query(UserAddress)
        .filter(UserAddress.user_id == user.id)
        .order_by(UserAddress.is_primary.desc())
        .all()
    )
    try:
        cart_items = (
            db.query(MarketplaceCart)
            .filter(MarketplaceCart.user_id == user.id)
            .count()
        )
    except Exception:
        cart_items = 0

    return {
        "customer_id": customer.customer_id,
        "full_name": customer.full_name,
        "role": user_role(user),
        "phone_number": user.phone_number,
        "email": user.email,
        "profile_image": user.profile_image,
        "preferred_language": user.preferred_language,
        "date_of_birth": customer.date_of_birth,
        "gender": customer.gender,
        "verification_status": customer.verification_status or verification_status_for(user),
        "phone_verified": bool(user.phone_verified),
        "email_verified": bool(user.email_verified),
        "is_active": bool(user.is_active),
        "points_balance": int(customer.points_balance or 0),
        "created_at": customer.created_at,
        "updated_at": customer.updated_at,
        "stats": {
            "orders": orders,
            "wishlist": wishlist,
            "carts": cart_items,
            "addresses": len(addresses),
        },
        "addresses": [address_payload(a) for a in addresses],
    }


def plant_payload(plant: CustomerPlant) -> dict:
    """A customer plant, joined with the real crop catalogue entry.

    ``crop_name`` is read from ``crops`` rather than stored twice, so the Grow
    tab always shows the catalogue's current name for the variety.
    """
    crop = plant.crop
    return {
        "id": plant.id,
        "plant_id": plant.plant_id,
        "customer_id": plant.customer_id,
        "crop_id": plant.crop_id,
        "crop_name": getattr(crop, "name", None) if crop else None,
        "crop_variety": getattr(crop, "variety", None) if crop else None,
        "crop_category": getattr(crop, "category", None) if crop else None,
        "nickname": plant.nickname,
        "planted_on": plant.planted_on,
        "expected_harvest_on": plant.expected_harvest_on,
        "quantity": plant.quantity,
        "status": plant.status or "growing",
        "notes": plant.notes,
        "created_at": plant.created_at,
    }


__all__ = [
    "WELCOME_POINTS",
    "POINTS_REASON_WELCOME",
    "get_customer_for_user",
    "require_customer",
    "verification_status_for",
    "sync_customer_from_user",
    "award_points",
    "points_history",
    "customer_settings_payload",
    "get_or_create_customer_settings",
    "address_payload",
    "customer_summary_payload",
    "plant_payload",
]
