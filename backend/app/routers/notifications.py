from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.notification import Notification

router = APIRouter(prefix="/api/v1", tags=["Notifications"])


@router.get("/notifications")
def list_notifications(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    is_read: Optional[bool] = None,
    notification_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if is_read is not None:
        q = q.filter(Notification.is_read == is_read)
    if notification_type:
        q = q.filter(Notification.notification_type == notification_type)

    total = q.count()
    items = q.order_by(Notification.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "status": "success",
        "data": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "items": [
                {
                    "id": n.id,
                    "notification_id": n.notification_id,
                    "title": n.title,
                    "message": n.message,
                    "notification_type": n.notification_type,
                    "reference_id": n.reference_id,
                    "reference_type": n.reference_type,
                    "is_read": n.is_read,
                    "icon": n.icon,
                    "action_url": n.action_url,
                    "created_at": str(n.created_at) if n.created_at else None,
                }
                for n in items
            ],
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
    ).count()

    return {"status": "success", "data": {"unread_count": count}}


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


@router.put("/notifications/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)
        .update({"is_read": True})
    )
    db.commit()

    return {
        "status": "success",
        "data": {
            "updated_count": updated,
            "message": f"{updated} notifications marked as read",
        },
    }


@router.post("/notifications", status_code=201)
def create_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str,
    reference_id: Optional[str] = None,
    reference_type: Optional[str] = None,
    icon: Optional[str] = None,
    action_url: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notif_id = generate_id("FA-NOT", db, Notification)
    notification = Notification(
        notification_id=notif_id,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        reference_id=reference_id,
        reference_type=reference_type,
        icon=icon,
        action_url=action_url,
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
