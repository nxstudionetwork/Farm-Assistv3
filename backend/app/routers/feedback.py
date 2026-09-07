import uuid
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database.connection import get_db
from app.models.feedback import Feedback
from app.utils.auth import get_current_user
from app.integrations.notifications import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Feedback"])


async def _send_feedback_email(feedback_id, name, farmer_id, feedback_type, category, rating, message, related_page, user_email):
    try:
        await EmailService.send_feedback_email(feedback_id, name, farmer_id, feedback_type, rating, message, related_page, user_email)
    except Exception as e:
        logger.error(f"Failed to send feedback email: {e}")


def _gen_feedback_id(db: Session):
    last = db.query(Feedback).order_by(desc(Feedback.created_at)).first()
    if last and last.feedback_id:
        try:
            num = int(last.feedback_id.split("-")[-1]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        num = 1
    return f"FA-FB-{num:06d}"


def _feedback_dict(f):
    return {
        "id": f.id,
        "feedback_id": f.feedback_id,
        "name": f.name,
        "farmer_id": f.farmer_id,
        "email": f.email,
        "feedback_type": f.feedback_type,
        "category": f.category or "",
        "rating": f.rating,
        "message": f.message,
        "related_page": f.related_page,
        "status": f.status,
        "admin_reply": f.admin_reply,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


@router.post("/feedback")
async def create_feedback(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    feedback_type = (payload.get("feedback_type") or "General").strip()
    category = (payload.get("category") or "").strip()
    rating = payload.get("rating")
    message = (payload.get("message") or "").strip()
    related_page = (payload.get("related_page") or "").strip()

    if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    if not message or len(message) < 5:
        raise HTTPException(status_code=400, detail="Feedback message must be at least 5 characters")
    if len(message) > 5000:
        raise HTTPException(status_code=400, detail="Feedback message must be under 5000 characters")

    name = user.farmer_id or "User"
    try:
        if hasattr(user, "first_name") and user.first_name:
            name = user.first_name
        if hasattr(user, "full_name") and user.full_name:
            name = user.full_name
    except Exception:
        pass

    feedback = Feedback(
        id=str(uuid.uuid4()),
        feedback_id=_gen_feedback_id(db),
        user_id=user.id,
        farmer_id=user.farmer_id or "",
        name=name,
        email=getattr(user, "email", "") or "",
        feedback_type=feedback_type,
        category=category or None,
        rating=rating,
        message=message,
        related_page=related_page,
        status="new",
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    asyncio.create_task(_send_feedback_email(feedback.feedback_id, name, user.farmer_id or "", feedback_type, category, rating, message, related_page, getattr(user, "email", "") or ""))

    result = _feedback_dict(feedback)
    return {"status": "success", "data": result}


@router.get("/feedback")
def list_feedback(db: Session = Depends(get_db), user=Depends(get_current_user)):
    entries = (
        db.query(Feedback)
        .filter(Feedback.user_id == user.id)
        .order_by(desc(Feedback.created_at))
        .all()
    )
    return {
        "status": "success",
        "data": {
            "feedback": [_feedback_dict(f) for f in entries],
            "total": len(entries),
        },
    }


@router.get("/feedback/{feedback_id}")
def get_feedback(feedback_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    entry = (
        db.query(Feedback)
        .filter(Feedback.feedback_id == feedback_id, Feedback.user_id == user.id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"status": "success", "data": _feedback_dict(entry)}
