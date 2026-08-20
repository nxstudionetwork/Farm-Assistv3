import uuid
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database.connection import get_db
from app.models.support import SupportTicket
from app.utils.auth import get_current_user
from app.integrations.notifications import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Support"])


async def _send_support_email(ticket_id, name, farmer_id, category, subject, description, user_email):
    try:
        await EmailService.send_support_email(ticket_id, name, farmer_id, category, subject, description, user_email)
    except Exception as e:
        logger.error(f"Failed to send support email: {e}")


def _gen_ticket_id(db: Session):
    last = db.query(SupportTicket).order_by(desc(SupportTicket.created_at)).first()
    if last and last.ticket_id:
        try:
            num = int(last.ticket_id.split("-")[-1]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        num = 1
    return f"FA-TKT-{num:06d}"


def _ticket_dict(t):
    return {
        "id": t.id,
        "ticket_id": t.ticket_id,
        "name": t.name,
        "farmer_id": t.farmer_id,
        "category": t.category,
        "subject": t.subject,
        "description": t.description,
        "status": t.status,
        "admin_reply": t.admin_reply,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.post("/tickets")
async def create_ticket(payload: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    name = (payload.get("name") or "").strip()
    category = (payload.get("category") or "").strip()
    subject = (payload.get("subject") or "").strip()
    description = (payload.get("description") or "").strip()

    if not name or not category or not subject or not description:
        raise HTTPException(status_code=400, detail="All fields are required")
    if len(subject) > 300:
        raise HTTPException(status_code=400, detail="Subject must be under 300 characters")
    if len(description) > 5000:
        raise HTTPException(status_code=400, detail="Description must be under 5000 characters")

    ticket = SupportTicket(
        id=str(uuid.uuid4()),
        ticket_id=_gen_ticket_id(db),
        user_id=user.id,
        farmer_id=user.farmer_id or "",
        name=name,
        category=category,
        subject=subject,
        description=description,
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    asyncio.create_task(_send_support_email(ticket.ticket_id, name, user.farmer_id or "", category, subject, description, getattr(user, "email", "") or ""))

    result = _ticket_dict(ticket)
    return {"status": "success", "data": result}


@router.get("/tickets")
def list_tickets(db: Session = Depends(get_db), user=Depends(get_current_user)):
    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == user.id)
        .order_by(desc(SupportTicket.created_at))
        .all()
    )
    return {
        "status": "success",
        "data": {
            "tickets": [_ticket_dict(t) for t in tickets],
            "total": len(tickets),
        },
    }


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ticket = (
        db.query(SupportTicket)
        .filter(SupportTicket.ticket_id == ticket_id, SupportTicket.user_id == user.id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"status": "success", "data": _ticket_dict(ticket)}
