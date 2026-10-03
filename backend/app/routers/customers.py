"""
Customer-only API.

Every endpoint here depends on ``get_current_customer``, which authenticates the
bearer token, loads the user from the database, and then checks the role stored
on that row. Frontend route guards are a convenience; this is the actual
enforcement, and it does not trust anything the caller can edit.

Ownership is resolved from the token in all cases. There is no endpoint that
accepts a ``customer_id`` and acts on it, which is what makes Customer A's
inability to read Customer B's data structural rather than a promise.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.customer import CustomerPlant
from app.models.marketplace import MarketplaceOrder
from app.models.notification import Notification
from app.models.user import User, UserAddress
from app.schemas.customer import (
    CustomerAddressRequest,
    CustomerProfileUpdate,
    CustomerSettingsUpdate,
)
from app.services import customer_service
from app.utils.auth import generate_id, get_current_customer, user_role

router = APIRouter(prefix="/api/v1/customers", tags=["Customer"])

PLANT_STATUSES = ("growing", "harvested", "removed")


class CustomerPlantCreate(BaseModel):
    crop_id: Optional[str] = None
    nickname: Optional[str] = None
    planted_on: Optional[str] = None
    expected_harvest_on: Optional[str] = None
    quantity: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("planted_on", "expected_harvest_on")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Dates must be in YYYY-MM-DD format")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("Quantity must be at least 1")
        return v


class CustomerPlantUpdate(BaseModel):
    crop_id: Optional[str] = None
    nickname: Optional[str] = None
    planted_on: Optional[str] = None
    expected_harvest_on: Optional[str] = None
    quantity: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        status_value = v.strip().lower()
        if status_value not in PLANT_STATUSES:
            raise ValueError(
                "Status must be one of: " + ", ".join(PLANT_STATUSES)
            )
        return status_value


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #
@router.get("/me", response_model=dict)
def get_customer_profile(
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """The authenticated customer's own profile.

    The Customer ID in the response comes from the ``customers`` row, which was
    found via the token. There is no request parameter that could widen it.
    """
    customer = customer_service.require_customer(db, current_user)
    return {
        "status": "success",
        "data": customer_service.customer_summary_payload(db, current_user, customer),
    }


@router.put("/me", response_model=dict)
def update_customer_profile(
    payload: CustomerProfileUpdate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer = customer_service.require_customer(db, current_user)

    if payload.full_name:
        current_user.full_name = payload.full_name
    if payload.date_of_birth is not None:
        customer.date_of_birth = payload.date_of_birth
    if payload.gender is not None:
        customer.gender = payload.gender
    if payload.bio is not None:
        customer.bio = payload.bio

    if payload.email is not None and payload.email != current_user.email:
        taken = (
            db.query(User)
            .filter(User.email == payload.email, User.id != current_user.id)
            .first()
        )
        if taken:
            raise HTTPException(status_code=400, detail="Email already registered")
        # Changing the address invalidates proof of the previous one.
        current_user.email = payload.email
        current_user.email_verified = False
        current_user.email_verified_at = None

    customer_service.sync_customer_from_user(db, current_user, customer)
    db.commit()
    db.refresh(customer)

    return {
        "status": "success",
        "message": "Profile updated successfully",
        "data": customer_service.customer_summary_payload(db, current_user, customer),
    }


# --------------------------------------------------------------------------- #
# Addresses
# --------------------------------------------------------------------------- #
@router.get("/me/addresses", response_model=dict)
def list_addresses(
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer_service.require_customer(db, current_user)
    rows = (
        db.query(UserAddress)
        .filter(UserAddress.user_id == current_user.id)
        .order_by(UserAddress.is_primary.desc(), UserAddress.created_at.desc())
        .all()
    )
    return {
        "status": "success",
        "data": [customer_service.address_payload(a) for a in rows],
    }


@router.post("/me/addresses", response_model=dict, status_code=status.HTTP_201_CREATED)
def add_address(
    payload: CustomerAddressRequest,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer = customer_service.require_customer(db, current_user)

    existing = (
        db.query(UserAddress).filter(UserAddress.user_id == current_user.id).count()
    )
    # The first address a customer saves is the delivery default.
    is_primary = bool(payload.is_primary) or existing == 0
    if is_primary:
        db.query(UserAddress).filter(
            UserAddress.user_id == current_user.id, UserAddress.is_primary == True
        ).update({UserAddress.is_primary: False})

    address = UserAddress(
        user_id=current_user.id,
        address_line=payload.address_line,
        village=payload.village,
        mandal=payload.mandal,
        district=payload.district,
        state=payload.state,
        country=payload.country or "India",
        pincode=payload.pincode,
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_primary=is_primary,
    )
    db.add(address)
    db.commit()
    db.refresh(address)

    return {
        "status": "success",
        "message": "Address saved successfully",
        "data": customer_service.address_payload(address),
    }


def _owned_address(db: Session, user: User, address_id: str) -> UserAddress:
    """Fetch an address, proving it belongs to the caller before use.

    Filtering on ``user_id`` in the query itself is the point: an address ID
    belonging to somebody else simply does not match, so there is no branch where
    the ownership check could be forgotten.
    """
    address = (
        db.query(UserAddress)
        .filter(UserAddress.id == address_id, UserAddress.user_id == user.id)
        .first()
    )
    if address is None:
        raise HTTPException(status_code=404, detail="Address not found")
    return address


@router.put("/me/addresses/{address_id}", response_model=dict)
def update_address(
    address_id: str,
    payload: CustomerAddressRequest,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer_service.require_customer(db, current_user)
    address = _owned_address(db, current_user, address_id)

    for field in (
        "address_line", "village", "mandal", "district",
        "state", "pincode", "latitude", "longitude",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(address, field, value)
    if payload.country:
        address.country = payload.country
    if payload.is_primary:
        db.query(UserAddress).filter(
            UserAddress.user_id == current_user.id,
            UserAddress.id != address.id,
            UserAddress.is_primary == True,
        ).update({UserAddress.is_primary: False})
        address.is_primary = True

    db.commit()
    db.refresh(address)
    return {
        "status": "success",
        "message": "Address updated successfully",
        "data": customer_service.address_payload(address),
    }


@router.delete("/me/addresses/{address_id}", response_model=dict)
def delete_address(
    address_id: str,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer_service.require_customer(db, current_user)
    address = _owned_address(db, current_user, address_id)
    was_primary = bool(address.is_primary)
    db.delete(address)
    db.commit()

    if was_primary:
        # Promote the next saved address so the customer is never left without
        # a delivery default.
        replacement = (
            db.query(UserAddress)
            .filter(UserAddress.user_id == current_user.id)
            .order_by(UserAddress.created_at.desc())
            .first()
        )
        if replacement is not None:
            replacement.is_primary = True
            db.commit()

    return {"status": "success", "message": "Address removed successfully"}


# --------------------------------------------------------------------------- #
# Points
# --------------------------------------------------------------------------- #
@router.get("/me/points", response_model=dict)
def get_points(
    limit: int = 25,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer = customer_service.require_customer(db, current_user)
    entries = customer_service.points_history(db, customer, limit=limit)
    return {
        "status": "success",
        "data": {
            "balance": int(customer.points_balance or 0),
            "customer_id": customer.customer_id,
            "history": [
                {
                    "entry_id": e.entry_id,
                    "points": e.points,
                    "reason": e.reason,
                    "balance_after": e.balance_after,
                    "reference_type": e.reference_type,
                    "reference_id": e.reference_id,
                    "created_at": e.created_at,
                }
                for e in entries
            ],
        },
    }


# --------------------------------------------------------------------------- #
# Settings (customer preferences, separate from the farmer sheet)
# --------------------------------------------------------------------------- #
@router.get("/me/settings", response_model=dict)
def get_settings(
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer_service.require_customer(db, current_user)
    settings = customer_service.get_or_create_customer_settings(db, current_user)
    db.commit()
    return {
        "status": "success",
        "data": customer_service.customer_settings_payload(settings),
    }


@router.put("/me/settings", response_model=dict)
def update_settings(
    payload: CustomerSettingsUpdate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer_service.require_customer(db, current_user)
    settings = customer_service.get_or_create_customer_settings(db, current_user)

    if payload.notifications:
        allowed = {
            "orders": "notif_orders",
            "products": "notif_products",
            "grow": "notif_grow",
            "community": "notif_community",
            "points": "notif_points",
        }
        for key, column in allowed.items():
            if key in payload.notifications:
                setattr(settings, column, bool(payload.notifications[key]))

    if payload.shopping:
        if "default_address_id" in payload.shopping:
            address_id = payload.shopping.get("default_address_id")
            if address_id:
                # Ownership is proven before a customer's default can point at
                # somebody else's saved address.
                _owned_address(db, current_user, address_id)
            settings.shopping_default_address_id = address_id or None
        if "preferences" in payload.shopping:
            settings.shopping_preferences = payload.shopping.get("preferences") or {}

    if payload.grow:
        if "reminders" in payload.grow:
            settings.grow_reminders = bool(payload.grow["reminders"])
        if "plant_care_reminders" in payload.grow:
            settings.plant_care_reminders = bool(payload.grow["plant_care_reminders"])

    if payload.community:
        if "notifications" in payload.community:
            settings.community_notifications = bool(payload.community["notifications"])
        if "privacy" in payload.community:
            settings.community_privacy = payload.community.get("privacy") or {}

    if payload.app:
        if "language" in payload.app and payload.app["language"]:
            settings.language = str(payload.app["language"])[:10]
        if "theme" in payload.app and payload.app["theme"]:
            settings.theme = str(payload.app["theme"])[:20]
        if "text_size" in payload.app and payload.app["text_size"]:
            settings.text_size = str(payload.app["text_size"])[:20]
        if "reduce_motion" in payload.app:
            settings.reduce_motion = bool(payload.app["reduce_motion"])

    settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(settings)

    return {
        "status": "success",
        "message": "Settings updated successfully",
        "data": customer_service.customer_settings_payload(settings),
    }


# --------------------------------------------------------------------------- #
# Grow -- the customer's own plants, drawn from the real crop catalogue
# --------------------------------------------------------------------------- #
@router.get("/me/plants", response_model=dict)
def list_plants(
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer = customer_service.require_customer(db, current_user)
    query = db.query(CustomerPlant).filter(
        CustomerPlant.customer_pk == customer.id
    )
    if status_filter:
        query = query.filter(CustomerPlant.status == status_filter.strip().lower())
    plants = query.order_by(CustomerPlant.created_at.desc()).all()
    return {
        "status": "success",
        "data": {
            "customer_id": customer.customer_id,
            "plants": [customer_service.plant_payload(p) for p in plants],
        },
    }


@router.post("/me/plants", response_model=dict, status_code=status.HTTP_201_CREATED)
def add_plant(
    payload: CustomerPlantCreate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    from app.models.crop import Crop

    customer = customer_service.require_customer(db, current_user)

    if payload.crop_id:
        exists = db.query(Crop).filter(Crop.id == payload.crop_id).first()
        if exists is None:
            raise HTTPException(status_code=404, detail="Crop not found in catalogue")

    plant = CustomerPlant(
        customer_pk=customer.id,
        customer_id=customer.customer_id,
        user_id=current_user.id,
        crop_id=payload.crop_id,
        nickname=payload.nickname,
        planted_on=payload.planted_on,
        expected_harvest_on=payload.expected_harvest_on,
        quantity=payload.quantity,
        status="growing",
        notes=payload.notes,
    )
    db.add(plant)
    db.flush()
    plant.plant_id = generate_id("FA-PLT", db, CustomerPlant)
    db.commit()
    db.refresh(plant)

    return {
        "status": "success",
        "message": "Added to your Grow list",
        "data": customer_service.plant_payload(plant),
    }


def _owned_plant(db: Session, customer, plant_id: str) -> CustomerPlant:
    """Find one of *this* customer's plants by its public identifier.

    The path parameter is called ``plant_id`` and that is the value handed out
    in ``plant_payload``, so ``FA-PLT-...`` is what a client sends. The numeric
    primary key is accepted too, because it also appears in the payload and a
    client that used it should not be left guessing.

    Either way the ownership filter is not optional: guessing another
    customer's identifier returns the same 404 as an identifier that does not
    exist, so this cannot be used to discover that a plant is someone else's.
    """
    filters = [CustomerPlant.customer_pk == customer.id]
    identifier = str(plant_id)
    if identifier.isdigit():
        filters.append(CustomerPlant.id == int(identifier))
    else:
        filters.append(CustomerPlant.plant_id == identifier)

    plant = db.query(CustomerPlant).filter(*filters).first()
    if plant is None:
        raise HTTPException(status_code=404, detail="Plant not found")
    return plant


@router.put("/me/plants/{plant_id}", response_model=dict)
def update_plant(
    plant_id: str,
    payload: CustomerPlantUpdate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer = customer_service.require_customer(db, current_user)
    plant = _owned_plant(db, customer, plant_id)

    if payload.crop_id is not None:
        from app.models.crop import Crop

        exists = db.query(Crop).filter(Crop.id == payload.crop_id).first()
        if exists is None:
            raise HTTPException(status_code=404, detail="Crop not found in catalogue")
        plant.crop_id = payload.crop_id
    for field in (
        "nickname", "planted_on", "expected_harvest_on",
        "quantity", "status", "notes",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(plant, field, value)

    plant.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(plant)

    return {
        "status": "success",
        "message": "Plant updated",
        "data": customer_service.plant_payload(plant),
    }


@router.delete("/me/plants/{plant_id}", response_model=dict)
def delete_plant(
    plant_id: str,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    customer = customer_service.require_customer(db, current_user)
    plant = _owned_plant(db, customer, plant_id)
    db.delete(plant)
    db.commit()
    return {"status": "success", "message": "Plant removed"}


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@router.get("/me/dashboard", response_model=dict)
def customer_dashboard(
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """Everything the Customer Dashboard home screen shows.

    Every count and row is filtered by the authenticated user's id, so the
    numbers can only ever describe this customer.
    """
    customer = customer_service.require_customer(db, current_user)

    recent_orders = (
        db.query(MarketplaceOrder)
        .filter(MarketplaceOrder.user_id == current_user.id)
        .order_by(MarketplaceOrder.created_at.desc())
        .limit(3)
        .all()
    )
    unread = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712 - SQL boolean column
            Notification.is_deleted == False,  # noqa: E712
        )
        .count()
    )
    plants = (
        db.query(CustomerPlant)
        .filter(
            CustomerPlant.customer_pk == customer.id,
            CustomerPlant.status == "growing",
        )
        .order_by(CustomerPlant.created_at.desc())
        .limit(3)
        .all()
    )
    primary_address = (
        db.query(UserAddress)
        .filter(UserAddress.user_id == current_user.id, UserAddress.is_primary == True)  # noqa: E712
        .first()
    )

    summary = customer_service.customer_summary_payload(db, current_user, customer)

    return {
        "status": "success",
        "data": {
            "customer_id": customer.customer_id,
            "full_name": customer.full_name,
            "role": user_role(current_user),
            "points_balance": int(customer.points_balance or 0),
            "verification_status": summary["verification_status"],
            "stats": summary["stats"],
            "unread_notifications": unread,
            "default_address": (
                customer_service.address_payload(primary_address)
                if primary_address
                else None
            ),
            "recent_orders": [
                {
                    "order_id": o.order_id,
                    "total_amount": o.total_amount,
                    "status": o.status,
                    "payment_status": o.payment_status,
                    "created_at": o.created_at,
                }
                for o in recent_orders
            ],
            "growing": [customer_service.plant_payload(p) for p in plants],
        },
    }
