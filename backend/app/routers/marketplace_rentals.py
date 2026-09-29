"""Marketplace - EQUIPMENT RENTAL requests.

Farmers list equipment (Tractors, power tillers, ...) as Rent listings on the
Marketplace. Other farmers rent them from the Tools & Equipment page: a rental
request is created on the listing, the listing owner receives a notification,
and decides (approve / reject). The decision notification reaches the
requester, who tracks the status on the Tools & Equipment page.

Ownership is never trusted from the frontend: the requester is always the
authenticated JWT user and the listing owner is read from the database. The
conversation is persisted in ``marketplace_rental_requests`` and notifications
go through the shared ``create_notification`` helper (no second system).
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.utils.notification_helper import create_notification
from app.models.user import User
from app.models.marketplace import (
    MarketplaceListing,
    MarketplaceRentalRequest,
    MarketplaceSellerSettings,
)

router = APIRouter(prefix="/api/v1/marketplace/rentals", tags=["Marketplace - Equipment Rentals"])

#: Statuses a requester may still cancel.
CANCELLABLE = ("pending", "approved")
#: Statuses a request must be in before an owner may decide it.
DECIDABLE = ("pending",)
#: Active statuses that reserve a date range.
RESERVING = ("pending", "approved")


class RentalRequestCreate(BaseModel):
    start_date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    end_date: str = Field(..., description="ISO date (YYYY-MM-DD), inclusive")
    requested_quantity: float = Field(1, gt=0)
    message: Optional[str] = Field(None, max_length=2000)


class RentalDecision(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    reason: Optional[str] = Field(None, max_length=1000)


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date. Use YYYY-MM-DD.")


def _get_listing(db: Session, listing_id: str) -> MarketplaceListing:
    listing = (
        db.query(MarketplaceListing)
        .filter(
            or_(MarketplaceListing.id == listing_id, MarketplaceListing.listing_id == listing_id),
            MarketplaceListing.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


def _request_by_id(db: Session, request_id: str) -> MarketplaceRentalRequest:
    req = (
        db.query(MarketplaceRentalRequest)
        .filter(
            or_(MarketplaceRentalRequest.id == request_id, MarketplaceRentalRequest.request_id == request_id)
        )
        .first()
    )
    if not req:
        raise HTTPException(status_code=404, detail="Rental request not found")
    return req


def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """True when the inclusive date ranges share any day."""
    return start_a <= end_b and start_b <= end_a


def _reserved_conflict(db: Session, listing_id: str, start: datetime, end: datetime, exclude_id: Optional[str] = None) -> bool:
    """An approved/decided reservation already covers the requested period."""
    q = db.query(MarketplaceRentalRequest).filter(
        MarketplaceRentalRequest.listing_id == listing_id,
        MarketplaceRentalRequest.status.in_(RESERVING),
    )
    if exclude_id:
        q = q.filter(MarketplaceRentalRequest.id != exclude_id)
    for row in q.all():
        row_start = _parse_date(row.start_date)
        row_end = _parse_date(row.end_date)
        if row_start and row_end and _overlaps(start, end, row_start, row_end):
            return True
    return False


def _listing_lite(db: Session, listing: MarketplaceListing) -> dict:
    return {
        "id": listing.id,
        "listing_id": listing.listing_id,
        "title": listing.title,
        "listing_type": listing.listing_type or "sell",
        "price": listing.price,
        "unit": listing.unit,
        "rental_period": listing.rental_period,
        "security_deposit": listing.security_deposit,
        "location": listing.location,
        "images": [{"url": img.image_url, "sort_order": img.sort_order} for img in (listing.images or [])],
        "category": (
            {"id": listing.category.id, "name": listing.category.name, "slug": listing.category.slug}
            if listing.category else None
        ),
        "status": listing.status,
    }


def _request_payload(db: Session, req: MarketplaceRentalRequest, viewer_id: str) -> dict:
    requester = db.query(User).filter(User.id == req.requester_user_id).first()
    owner = db.query(User).filter(User.id == req.owner_user_id).first()
    return {
        "id": req.id,
        "request_id": req.request_id,
        "status": req.status,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "requested_quantity": req.requested_quantity,
        "message": req.message,
        "decline_reason": req.decline_reason,
        "is_owner": req.owner_user_id == viewer_id,
        "is_requester": req.requester_user_id == viewer_id,
        "listing": _listing_lite(db, req.listing),
        "requester": {
            "id": requester.id if requester else None,
            "full_name": requester.full_name if requester else None,
            "phone_number": requester.phone_number if requester else None,
            "farmer_id": requester.farmer_id if requester else None,
        } if requester else None,
        "owner": {
            "id": owner.id if owner else None,
            "full_name": owner.full_name if owner else None,
            "phone_number": owner.phone_number if owner else None,
            "farmer_id": owner.farmer_id if owner else None,
        } if owner else None,
        "created_at": str(req.created_at) if req.created_at else None,
        "decided_at": str(req.decided_at) if req.decided_at else None,
        "cancelled_at": str(req.cancelled_at) if req.cancelled_at else None,
        "updated_at": str(req.updated_at) if req.updated_at else None,
    }


def _read_status(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip().lower()
    allowed = ("pending", "approved", "rejected", "cancelled", "completed")
    if raw not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(allowed)}")
    return raw


# ---------------------------------------------------------------------------
# Create a rental request (renter -> owner)
# ---------------------------------------------------------------------------
@router.post("/listings/{listing_id}/requests", status_code=201)
def create_rental_request(
    listing_id: str,
    payload: RentalRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = _get_listing(db, listing_id)
    if listing.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot rent your own listing")
    if (listing.listing_type or "sell") != "rent":
        raise HTTPException(status_code=400, detail="This listing is not available for rent")
    if not (listing.status == "active" and listing.is_active):
        raise HTTPException(status_code=400, detail="This listing is no longer available")

    start = _parse_date(payload.start_date)
    end = _parse_date(payload.end_date)
    if start is None or end is None:
        raise HTTPException(status_code=400, detail="Start and end dates are required")
    if end < start:
        raise HTTPException(status_code=400, detail="End date must not be before the start date")

    if listing.available_from:
        avail_from = _parse_date(listing.available_from)
        if avail_from and start < avail_from:
            raise HTTPException(
                status_code=400,
                detail=f"This equipment is available only from {listing.available_from}",
            )
    if listing.available_until:
        avail_until = _parse_date(listing.available_until)
        if avail_until and end > avail_until:
            raise HTTPException(
                status_code=400,
                detail=f"This equipment is available only until {listing.available_until}",
            )

    if _reserved_conflict(db, listing.id, start, end):
        raise HTTPException(status_code=409, detail="That period is already booked. Pick different dates.")

    duplicate = (
        db.query(MarketplaceRentalRequest)
        .filter(
            MarketplaceRentalRequest.listing_id == listing.id,
            MarketplaceRentalRequest.requester_user_id == current_user.id,
            MarketplaceRentalRequest.status.in_(RESERVING),
        )
        .all()
    )
    for row in duplicate:
        row_start = _parse_date(row.start_date)
        row_end = _parse_date(row.end_date)
        if row_start and row_end and _overlaps(start, end, row_start, row_end):
            raise HTTPException(
                status_code=409,
                detail="You already have a pending or approved rental request for this equipment in that period.",
            )

    req = MarketplaceRentalRequest(
        request_id=generate_id("FA-REQ", db, MarketplaceRentalRequest),
        listing_id=listing.id,
        requester_user_id=current_user.id,
        owner_user_id=listing.user_id,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        requested_quantity=payload.requested_quantity,
        message=payload.message.strip() if payload.message else None,
        status="pending",
    )
    db.add(req)
    db.flush()

    create_notification(
        db=db,
        user_id=listing.user_id,
        title="New equipment rental request",
        message=(
            f"{current_user.full_name or 'A farmer'} wants to rent "
            f"{listing.title} from {start.strftime('%d %b')} to {end.strftime('%d %b')}. "
            f"Approve or reject this request."
        ),
        notification_type="market",
        reference_id=req.id,
        reference_type="marketplace_rental_request",
        icon="fa-tractor",
        action_url="tools.html#incoming-rental-requests",
    )

    db.commit()
    db.refresh(req)
    return {
        "status": "success",
        "data": _request_payload(db, req, current_user.id),
        "message": "Your rental request has been sent to the owner for approval.",
    }


# ---------------------------------------------------------------------------
# My requests (as the renter)
# ---------------------------------------------------------------------------
@router.get("/requests")
def list_my_requests(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(MarketplaceRentalRequest).filter(
        MarketplaceRentalRequest.requester_user_id == current_user.id
    )
    st = _read_status(status)
    if st:
        q = q.filter(MarketplaceRentalRequest.status == st)
    total = q.count()
    rows = (
        q.order_by(MarketplaceRentalRequest.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_request_payload(db, r, current_user.id) for r in rows],
        },
    }


# ---------------------------------------------------------------------------
# Incoming requests (as the listing owner)
# ---------------------------------------------------------------------------
@router.get("/requests/incoming")
def list_incoming_requests(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(MarketplaceRentalRequest).filter(
        MarketplaceRentalRequest.owner_user_id == current_user.id
    )
    st = _read_status(status)
    if st:
        q = q.filter(MarketplaceRentalRequest.status == st)
    total = q.count()
    rows = (
        q.order_by(
            MarketplaceRentalRequest.status == "pending",
            MarketplaceRentalRequest.created_at.desc(),
        )
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [_request_payload(db, r, current_user.id) for r in rows],
        },
    }


# ---------------------------------------------------------------------------
# Badge counts for the Tools & Equipment page
# ---------------------------------------------------------------------------
@router.get("/requests/counts")
def rental_request_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    outgoing = (
        db.query(func.count(MarketplaceRentalRequest.id))
        .filter(
            MarketplaceRentalRequest.requester_user_id == current_user.id,
            MarketplaceRentalRequest.status.in_(("pending", "approved")),
        ).scalar() or 0
    )
    incoming = (
        db.query(func.count(MarketplaceRentalRequest.id))
        .filter(
            MarketplaceRentalRequest.owner_user_id == current_user.id,
            MarketplaceRentalRequest.status == "pending",
        ).scalar() or 0
    )
    return {
        "status": "success",
        "data": {"outgoing": outgoing, "incoming": incoming},
    }


# ---------------------------------------------------------------------------
# Owner decision (approve / reject)
# ---------------------------------------------------------------------------
@router.patch("/requests/{request_id}/decision")
def decide_rental_request(
    request_id: str,
    payload: RentalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _request_by_id(db, request_id)
    if req.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the listing owner can approve or reject this rental request.",
        )
    if req.status not in DECIDABLE:
        raise HTTPException(status_code=409, detail=f"This request has already been {req.status}.")

    if payload.decision == "approved":
        start = _parse_date(req.start_date)
        end = _parse_date(req.end_date)
        if start and end and _reserved_conflict(db, req.listing_id, start, end, exclude_id=req.id):
            raise HTTPException(
                status_code=409,
                detail="That period is already booked under another approved request. Reject this one or ask for different dates.",
            )
        req.status = "approved"
    else:
        req.status = "rejected"
    req.decided_at = datetime.utcnow()
    if payload.reason:
        req.decline_reason = payload.reason.strip()

    requester_name = req.requester.full_name if req.requester else "The farmer"
    if req.status == "approved":
        title = "Rental request approved"
        message = (
            f"The owner approved your rental request for {req.listing.title} "
            f"({req.start_date} to {req.end_date}). Contact the owner to arrange pickup."
        )
        icon = "fa-circle-check"
    else:
        title = "Rental request declined"
        reason_txt = f" Reason: {req.decline_reason}" if req.decline_reason else ""
        message = (
            f"The owner declined your rental request for {req.listing.title} "
            f"({req.start_date} to {req.end_date}).{reason_txt}"
        )
        icon = "fa-circle-xmark"

    create_notification(
        db=db,
        user_id=req.requester_user_id,
        title=title,
        message=message,
        notification_type="market",
        reference_id=req.id,
        reference_type="marketplace_rental_request",
        icon=icon,
        action_url="tools.html#my-rental-requests",
    )

    db.commit()
    db.refresh(req)
    return {
        "status": "success",
        "data": _request_payload(db, req, current_user.id),
        "message": "Request " + ("approved" if req.status == "approved" else "declined") + f" - {requester_name} has been notified.",
    }


# ---------------------------------------------------------------------------
# Requester cancel
# ---------------------------------------------------------------------------
@router.patch("/requests/{request_id}/cancel")
def cancel_rental_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = _request_by_id(db, request_id)
    if req.requester_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the requester can cancel this rental request.")
    if req.status not in CANCELLABLE:
        raise HTTPException(status_code=409, detail=f"This request is {req.status} and cannot be cancelled.")

    req.status = "cancelled"
    req.cancelled_at = datetime.utcnow()

    create_notification(
        db=db,
        user_id=req.owner_user_id,
        title="Rental request cancelled",
        message=(
            f"{req.requester.full_name or 'A farmer'} cancelled their rental request "
            f"for {req.listing.title} ({req.start_date} to {req.end_date})."
        ),
        notification_type="market",
        reference_id=req.id,
        reference_type="marketplace_rental_request",
        icon="fa-ban",
        action_url="tools.html#incoming-rental-requests",
    )

    db.commit()
    db.refresh(req)
    return {
        "status": "success",
        "data": _request_payload(db, req, current_user.id),
        "message": "Your rental request has been cancelled.",
    }