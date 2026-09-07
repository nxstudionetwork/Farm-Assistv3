from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User, UserSettings
from app.models.notification import Notification
from app.utils.notification_helper import disabled_notification_types

router = APIRouter(prefix="/api/v1", tags=["Notifications"])


class NotificationCreate(BaseModel):
    title: str
    message: str
    notification_type: str
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None
    icon: Optional[str] = None
    action_url: Optional[str] = None


# Granular notification_type values -> broad, user-facing category bucket.
# Categories power the filter chips and are always derived on the backend so we
# never trust an arbitrary category from the client.
TYPE_TO_CATEGORY = {
    "service_request": "services",
    "services": "services",
    "emergency": "emergency",
    "learning": "learning",
    "course": "learning",
    "market": "market",
    "order": "market",
    "wallet": "wallet",
    "payment": "wallet",
    "consultation": "consultations",
    "weather": "farmassist",
    "crop_task": "farmassist",
    "task": "farmassist",
    "pest": "farmassist",
    "technique": "farmassist",
    "sensor": "farmassist",
    "community": "farmassist",
    "message": "farmassist",
    "chat": "farmassist",
    "scheme": "farmassist",
    "government": "farmassist",
    "govt": "farmassist",
}

# notification_type value -> the Farm Assist team that sent it.
TYPE_TO_SENDER = {
    "service_request": ("Farm Assist Services", "services", "fa-concierge-bell"),
    "services": ("Farm Assist Services", "services", "fa-concierge-bell"),
    "emergency": ("Farm Assist Emergency", "emergency", "fa-triangle-exclamation"),
    "learning": ("Farm Assist Learning", "learning", "fa-graduation-cap"),
    "course": ("Farm Assist Learning", "learning", "fa-graduation-cap"),
    "market": ("Farm Assist Market", "market", "fa-chart-line"),
    "order": ("Farm Assist Market", "market", "fa-shopping-cart"),
    "wallet": ("Farm Assist Wallet", "wallet", "fa-wallet"),
    "payment": ("Farm Assist Wallet", "wallet", "fa-rupee-sign"),
    "consultation": ("Farm Assist Consultations", "consultations", "fa-user-doctor"),
    "weather": ("Farm Assist Weather", "farmassist", "fa-cloud-sun"),
    "crop_task": ("Farm Assist Team", "farmassist", "fa-seedling"),
    "task": ("Farm Assist Team", "farmassist", "fa-calendar-check"),
    "pest": ("Farm Assist AI", "farmassist", "fa-bug"),
    "technique": ("Farm Assist Learning", "learning", "fa-seedling"),
    "sensor": ("Farm Assist Team", "farmassist", "fa-microchip"),
    "community": ("Farm Assist Community", "farmassist", "fa-fire"),
    "message": ("Farm Assist Team", "farmassist", "fa-envelope"),
    "chat": ("Farm Assist Team", "farmassist", "fa-envelope"),
    "scheme": ("Farm Assist Scheme", "farmassist", "fa-landmark"),
    "government": ("Farm Assist Scheme", "farmassist", "fa-landmark"),
    "govt": ("Farm Assist Scheme", "farmassist", "fa-landmark"),
}

VALID_CATEGORIES = {
    "all", "unread", "farmassist", "services", "market",
    "learning", "emergency", "system", "wallet", "consultations",
}


def _category_for(notification_type):
    return TYPE_TO_CATEGORY.get((notification_type or "").lower(), "farmassist")


def _sender_for(notification_type):
    return TYPE_TO_SENDER.get(
        (notification_type or "").lower(),
        ("Farm Assist Team", "farmassist", "fa-bell"),
    )


def _notif_dict(n):
    sender_name, sender_type, sender_icon = _sender_for(n.notification_type)
    return {
        "id": n.id,
        "notification_id": n.notification_id,
        "sender_name": sender_name,
        "sender_type": sender_type,
        "sender_icon": sender_icon,
        "category": _category_for(n.notification_type),
        "title": n.title,
        "message": n.message,
        "notification_type": n.notification_type,
        "reference_id": n.reference_id,
        "reference_type": n.reference_type,
        "is_read": n.is_read,
        "is_archived": n.is_archived if hasattr(n, 'is_archived') else False,
        "icon": n.icon or sender_icon,
        "action_url": n.action_url,
        "created_at": str(n.created_at) if n.created_at else None,
        "updated_at": str(n.updated_at) if hasattr(n, 'updated_at') and n.updated_at else None,
    }


@router.get("/notifications")
def list_notifications(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    is_read: Optional[bool] = None,
    is_archived: Optional[bool] = None,
    notification_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sender: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_deleted == False,
    )
    if is_archived is not None:
        q = q.filter(Notification.is_archived == is_archived)
    else:
        q = q.filter(Notification.is_archived == False)
    if is_read is not None:
        q = q.filter(Notification.is_read == is_read)
    if notification_type:
        q = q.filter(Notification.notification_type == notification_type)

    # Category filter buckets the granular types into the user-facing chips.
    if category:
        cat = category.lower()
        valid = VALID_CATEGORIES - {"all", "unread"}
        if cat in valid:
            type_values = [
                t for t, c in TYPE_TO_CATEGORY.items() if c == cat
            ]
            type_values.append(cat)
            q = q.filter(Notification.notification_type.in_(type_values))
        elif cat == "unread":
            q = q.filter(Notification.is_read == False)

    # Sender filter (derived from notification_type too).
    if sender:
        sender_types = [
            t for t, s in TYPE_TO_SENDER.items() if s[1] == sender.lower()
        ]
        q = q.filter(Notification.notification_type.in_(sender_types))

    # Search across sender name, title, message and reference id.
    if search:
        term = search.strip()
        if term:
            like = f"%{term}%"
            q = q.filter(
                or_(
                    Notification.title.ilike(like),
                    Notification.message.ilike(like),
                    Notification.reference_id.ilike(like),
                    Notification.reference_type.ilike(like),
                    Notification.notification_type.ilike(like),
                )
            )

    settings_row = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    disabled = disabled_notification_types(settings_row)
    if disabled:
        q = q.filter(~Notification.notification_type.in_(disabled))

    total = q.count()
    items = q.order_by(Notification.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 0,
            "items": [_notif_dict(n) for n in items],
            "categories": sorted(VALID_CATEGORIES),
        },
    }


@router.get("/notifications/archived")
def list_archived(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_deleted == False,
        Notification.is_archived == True,
    )
    total = q.count()
    items = q.order_by(Notification.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 0,
            "items": [_notif_dict(n) for n in items],
        },
    }


@router.get("/notifications/unread")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
        Notification.is_deleted == False,
        Notification.is_archived == False,
    )

    settings_row = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    disabled = disabled_notification_types(settings_row)
    if disabled:
        count = count.filter(~Notification.notification_type.in_(disabled))

    return {"status": "success", "data": {"unread_count": count.count()}}


@router.get("/notifications/{notification_id}")
def get_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
        Notification.is_deleted == False,
    ).first()
    if not notif:
        notif = db.query(Notification).filter(
            Notification.notification_id == notification_id,
            Notification.user_id == current_user.id,
            Notification.is_deleted == False,
        ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "success", "data": _notif_dict(notif)}


@router.put("/notifications/{notification_id}/read")
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        notif = db.query(Notification).filter(
            Notification.notification_id == notification_id,
            Notification.user_id == current_user.id,
        ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_read = True
    notif.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(notif)

    return {
        "status": "success",
        "data": {
            "id": notif.id,
            "notification_id": notif.notification_id,
            "is_read": True,
            "message": "Notification marked as read",
        },
    }


@router.put("/notifications/{notification_id}/unread")
def mark_unread(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        notif = db.query(Notification).filter(
            Notification.notification_id == notification_id,
            Notification.user_id == current_user.id,
        ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_read = False
    notif.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(notif)

    return {
        "status": "success",
        "data": {
            "id": notif.id,
            "notification_id": notif.notification_id,
            "is_read": False,
            "message": "Notification marked as unread",
        },
    }


@router.put("/notifications/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
            Notification.is_deleted == False,
        )
        .update({"is_read": True, "updated_at": datetime.utcnow()})
    )
    db.commit()

    return {
        "status": "success",
        "data": {
            "updated_count": updated,
            "message": f"{updated} notifications marked as read",
        },
    }


@router.put("/notifications/{notification_id}/archive")
def archive_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        notif = db.query(Notification).filter(
            Notification.notification_id == notification_id,
            Notification.user_id == current_user.id,
        ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_archived = True
    notif.updated_at = datetime.utcnow()
    db.commit()

    return {"status": "success", "data": {"message": "Notification archived"}}


@router.put("/notifications/{notification_id}/unarchive")
def unarchive_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        notif = db.query(Notification).filter(
            Notification.notification_id == notification_id,
            Notification.user_id == current_user.id,
        ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_archived = False
    notif.updated_at = datetime.utcnow()
    db.commit()

    return {"status": "success", "data": {"message": "Notification unarchived"}}


@router.delete("/notifications/{notification_id}")
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        notif = db.query(Notification).filter(
            Notification.notification_id == notification_id,
            Notification.user_id == current_user.id,
        ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_deleted = True
    notif.updated_at = datetime.utcnow()
    db.commit()

    return {"status": "success", "data": {"message": "Notification deleted"}}


@router.post("/notifications", status_code=201)
def create_notification_api(
    body: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif_id = generate_id("FA-NOT", db, Notification)
    notification = Notification(
        notification_id=notif_id,
        user_id=current_user.id,
        title=body.title,
        message=body.message,
        notification_type=body.notification_type,
        reference_id=body.reference_id,
        reference_type=body.reference_type,
        icon=body.icon,
        action_url=body.action_url,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    return {
        "status": "success",
        "data": {
            "id": notification.id,
            "notification_id": notification.notification_id,
            "message": "Notification created successfully",
        },
    }
