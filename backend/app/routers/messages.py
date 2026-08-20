from datetime import datetime
from typing import Optional
import os
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.auth import get_current_user, generate_id
from app.config import settings
from app.models.user import User
from app.models.messages import (
    Conversation, ConversationParticipant, Message, MessageReaction,
    Contact, MessageAttachment,
)

router = APIRouter(prefix="/api/v1/messages", tags=["Messages"])


class ConversationCreate(BaseModel):
    user_id: Optional[str] = None
    farmer_id: Optional[str] = None
    name: Optional[str] = None


class MessageCreate(BaseModel):
    content: str
    message_type: str = "text"
    attachment_url: Optional[str] = None


class ReactionCreate(BaseModel):
    emoji: str


def _user_info(user: User) -> dict:
    return {
        "id": user.id,
        "farmer_id": user.farmer_id,
        "full_name": user.full_name,
        "profile_image": user.profile_image,
    }


def _resolve_target_user(db: Session, user_id: Optional[str], farmer_id: Optional[str]) -> User:
    if user_id:
        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        return target
    if farmer_id:
        target = db.query(User).filter(User.farmer_id == farmer_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        return target
    raise HTTPException(status_code=400, detail="user_id or farmer_id is required")


def _find_existing_direct_conversation(db: Session, user_a: str, user_b: str) -> Optional[Conversation]:
    conv_a = (
        db.query(ConversationParticipant)
        .filter(ConversationParticipant.user_id == user_a)
        .subquery()
    )
    conv_b = (
        db.query(ConversationParticipant.conversation_id)
        .join(conv_a, conv_a.c.conversation_id == ConversationParticipant.conversation_id)
        .filter(ConversationParticipant.user_id == user_b)
        .first()
    )
    if conv_b:
        conv = db.query(Conversation).filter(
            Conversation.id == conv_b.conversation_id,
            Conversation.type == "direct",
        ).first()
        return conv
    return None


def _get_last_message(db: Session, conversation_id: str) -> Optional[Message]:
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .first()
    )


def _get_unread_count(db: Session, conversation_id: str, user_id: str) -> int:
    participant = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
        .first()
    )
    if not participant or not participant.last_read_at:
        return db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.sender_id != user_id,
        ).count()
    return db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.sender_id != user_id,
        Message.created_at > participant.last_read_at,
    ).count()


def _get_other_participant(db: Session, conversation_id: str, current_user_id: str) -> Optional[dict]:
    other = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id != current_user_id,
        )
        .first()
    )
    if not other:
        return None
    user = db.query(User).filter(User.id == other.user_id).first()
    if not user:
        return None
    return _user_info(user)


def _message_to_dict(db: Session, msg: Message) -> dict:
    sender = db.query(User).filter(User.id == msg.sender_id).first()
    reactions = (
        db.query(MessageReaction)
        .filter(MessageReaction.message_id == msg.id)
        .all()
    )
    reaction_list = []
    for r in reactions:
        ru = db.query(User).filter(User.id == r.user_id).first()
        reaction_list.append({
            "id": r.id,
            "user_id": r.user_id,
            "emoji": r.emoji,
            "user_name": ru.full_name if ru else None,
            "created_at": str(r.created_at) if r.created_at else None,
        })
    return {
        "id": msg.id,
        "message_id": msg.message_id,
        "conversation_id": msg.conversation_id,
        "sender_id": msg.sender_id,
        "sender": _user_info(sender) if sender else None,
        "content": msg.content,
        "message_type": msg.message_type,
        "attachment_url": msg.attachment_url,
        "created_at": str(msg.created_at) if msg.created_at else None,
        "updated_at": str(msg.updated_at) if msg.updated_at else None,
        "reactions": reaction_list,
    }


def _conversation_to_dict(db: Session, conv: Conversation, current_user_id: str) -> dict:
    last_msg = _get_last_message(db, conv.id)
    unread = _get_unread_count(db, conv.id, current_user_id)
    other = _get_other_participant(db, conv.id, current_user_id)
    last_message = None
    if last_msg:
        last_message = {
            "id": last_msg.id,
            "message_id": last_msg.message_id,
            "content": last_msg.content,
            "message_type": last_msg.message_type,
            "sender_id": last_msg.sender_id,
            "created_at": str(last_msg.created_at) if last_msg.created_at else None,
        }
    return {
        "id": conv.id,
        "conversation_id": conv.conversation_id,
        "type": conv.type,
        "name": conv.name,
        "other_participant": other,
        "last_message": last_message,
        "unread_count": unread,
        "created_at": str(conv.created_at) if conv.created_at else None,
        "updated_at": str(conv.updated_at) if conv.updated_at else None,
    }


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = (
        db.query(func.count(Message.id))
        .join(ConversationParticipant, ConversationParticipant.conversation_id == Message.conversation_id)
        .filter(
            ConversationParticipant.user_id == current_user.id,
            Message.sender_id != current_user.id,
        )
        .filter(
            (ConversationParticipant.last_read_at == None) | (Message.created_at > ConversationParticipant.last_read_at)
        )
        .scalar()
    )
    return {"status": "success", "data": {"unread_count": total or 0}}


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    participant_rows = (
        db.query(ConversationParticipant)
        .filter(ConversationParticipant.user_id == current_user.id)
        .all()
    )
    conv_ids = [p.conversation_id for p in participant_rows]
    conversations = (
        db.query(Conversation)
        .filter(Conversation.id.in_(conv_ids))
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    items = [_conversation_to_dict(db, c, current_user.id) for c in conversations]
    return {"status": "success", "data": {"conversations": items, "total": len(items)}}


@router.post("/conversations", status_code=201)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = _resolve_target_user(db, payload.user_id, payload.farmer_id)
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot create conversation with yourself")
    existing = _find_existing_direct_conversation(db, current_user.id, target.id)
    if existing:
        return {"status": "success", "data": _conversation_to_dict(db, existing, current_user.id)}

    conv_id = generate_id("FA-CNV", db, Conversation)
    conversation = Conversation(
        conversation_id=conv_id,
        type="direct",
        name=payload.name,
    )
    db.add(conversation)
    db.flush()
    db.add(ConversationParticipant(conversation_id=conversation.id, user_id=current_user.id))
    db.add(ConversationParticipant(conversation_id=conversation.id, user_id=target.id))
    db.commit()
    db.refresh(conversation)
    return {"status": "success", "data": _conversation_to_dict(db, conversation, current_user.id)}


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(Conversation).filter(
        (Conversation.id == conversation_id) | (Conversation.conversation_id == conversation_id)
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    is_participant = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conv.id,
            ConversationParticipant.user_id == current_user.id,
        )
        .first()
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="You are not a participant in this conversation")
    return {"status": "success", "data": _conversation_to_dict(db, conv, current_user.id)}


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: str,
    before_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(Conversation).filter(
        (Conversation.id == conversation_id) | (Conversation.conversation_id == conversation_id)
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    is_participant = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conv.id,
            ConversationParticipant.user_id == current_user.id,
        )
        .first()
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="You are not a participant in this conversation")

    q = db.query(Message).filter(Message.conversation_id == conv.id)
    if before_id:
        cursor_msg = db.query(Message).filter(
            (Message.id == before_id) | (Message.message_id == before_id)
        ).first()
        if cursor_msg:
            q = q.filter(Message.created_at < cursor_msg.created_at)
    messages = q.order_by(Message.created_at.desc()).limit(limit + 1).all()
    has_more = len(messages) > limit
    messages = messages[:limit]
    items = [_message_to_dict(db, m) for m in reversed(messages)]
    return {
        "status": "success",
        "data": {
            "messages": items,
            "has_more": has_more,
            "total": q.count(),
        },
    }


@router.post("/conversations/{conversation_id}/messages", status_code=201)
def send_message(
    conversation_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(Conversation).filter(
        (Conversation.id == conversation_id) | (Conversation.conversation_id == conversation_id)
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    is_participant = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conv.id,
            ConversationParticipant.user_id == current_user.id,
        )
        .first()
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="You are not a participant in this conversation")
    if not payload.content or not payload.content.strip():
        raise HTTPException(status_code=400, detail="Message content is required")
    if payload.message_type not in ("text", "image", "file", "system"):
        raise HTTPException(status_code=400, detail="Invalid message_type")

    msg_id = generate_id("FA-MSG", db, Message)
    message = Message(
        message_id=msg_id,
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=payload.content.strip(),
        message_type=payload.message_type,
        attachment_url=payload.attachment_url,
    )
    db.add(message)
    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return {"status": "success", "data": _message_to_dict(db, message)}


@router.put("/conversations/{conversation_id}/read")
def mark_as_read(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(Conversation).filter(
        (Conversation.id == conversation_id) | (Conversation.conversation_id == conversation_id)
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    participant = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conv.id,
            ConversationParticipant.user_id == current_user.id,
        )
        .first()
    )
    if not participant:
        raise HTTPException(status_code=403, detail="You are not a participant in this conversation")
    participant.last_read_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "data": {"message": "Conversation marked as read"}}


@router.post("/conversations/{conversation_id}/messages/{message_id}/reactions", status_code=201)
def add_reaction(
    conversation_id: str,
    message_id: str,
    payload: ReactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    msg = db.query(Message).filter(
        (Message.id == message_id) | (Message.message_id == message_id),
        Message.conversation_id == conversation_id,
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    is_participant = (
        db.query(ConversationParticipant)
        .filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
        .first()
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="You are not a participant in this conversation")
    if not payload.emoji or len(payload.emoji) > 10:
        raise HTTPException(status_code=400, detail="Valid emoji is required")
    existing = (
        db.query(MessageReaction)
        .filter(
            MessageReaction.message_id == msg.id,
            MessageReaction.user_id == current_user.id,
            MessageReaction.emoji == payload.emoji,
        )
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()
        return {"status": "success", "data": {"message": "Reaction removed"}}
    reaction = MessageReaction(
        message_id=msg.id,
        user_id=current_user.id,
        emoji=payload.emoji,
    )
    db.add(reaction)
    db.commit()
    db.refresh(reaction)
    return {"status": "success", "data": {"id": reaction.id, "emoji": reaction.emoji, "message": "Reaction added"}}


class ContactCreate(BaseModel):
    farmer_id: str


class UserSearchQuery(BaseModel):
    query: str


def _contact_to_dict(c: Contact, db: Session) -> dict:
    cu = db.query(User).filter(User.id == c.contact_user_id).first()
    if not cu:
        return None
    is_online = False
    return {
        "id": c.id,
        "contact_user_id": c.contact_user_id,
        "nickname": c.nickname,
        "created_at": str(c.created_at),
        "user": _user_info(cu),
        "is_online": is_online,
    }


def _attachment_to_dict(a: MessageAttachment) -> dict:
    return {
        "id": a.id,
        "attachment_id": a.attachment_id,
        "file_name": a.file_name,
        "file_type": a.file_type,
        "file_size": a.file_size,
        "file_url": a.file_url,
        "created_at": str(a.created_at),
    }


@router.get("/contacts")
def list_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contacts = (
        db.query(Contact)
        .filter(Contact.user_id == current_user.id)
        .order_by(Contact.created_at.desc())
        .all()
    )
    items = [_contact_to_dict(c, db) for c in contacts if _contact_to_dict(c, db)]
    return {"status": "success", "data": {"contacts": items, "total": len(items)}}


@router.post("/contacts", status_code=201)
def add_contact(
    payload: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fid = payload.farmer_id.strip().upper()
    target = db.query(User).filter(User.farmer_id == fid).first()
    if not target:
        raise HTTPException(status_code=404, detail="Farmer not found with this ID")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot add yourself as a contact")
    existing = (
        db.query(Contact)
        .filter(Contact.user_id == current_user.id, Contact.contact_user_id == target.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Contact already added")
    contact = Contact(user_id=current_user.id, contact_user_id=target.id)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return {"status": "success", "data": _contact_to_dict(contact, db)}


@router.delete("/contacts/{contact_id}")
def remove_contact(
    contact_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = (
        db.query(Contact)
        .filter(Contact.id == contact_id, Contact.user_id == current_user.id)
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
    return {"status": "success", "data": {"message": "Contact removed"}}


@router.get("/users/search")
def search_users(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    term = f"%{q}%"
    users = (
        db.query(User)
        .filter(
            User.is_active == True,
            User.id != current_user.id,
            or_(
                User.farmer_id.ilike(term),
                User.full_name.ilike(term),
                User.phone_number.ilike(term),
            ),
        )
        .limit(20)
        .all()
    )
    items = [_user_info(u) for u in users]
    return {"status": "success", "data": {"users": items, "total": len(items)}}


@router.post("/upload", status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed = settings.STORAGE_ALLOWED_EXTENSIONS.split(",") if hasattr(settings, 'STORAGE_ALLOWED_EXTENSIONS') else ["jpg","jpeg","png","gif","pdf","doc","docx"]
    ext = (file.filename.rsplit(".", 1)[-1] if "." in file.filename else "").lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed")
    max_mb = getattr(settings, 'STORAGE_MAX_FILE_SIZE_MB', 10)
    contents = await file.read()
    if len(contents) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {max_mb}MB limit")
    upload_dir = getattr(settings, 'STORAGE_LOCAL_PATH', 'uploads')
    msg_dir = os.path.join(upload_dir, "messages")
    os.makedirs(msg_dir, exist_ok=True)
    safe_name = f"{_uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(msg_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(contents)
    file_url = f"/uploads/messages/{safe_name}"
    att_id = generate_id("FA-ATT", db, MessageAttachment)
    attachment = MessageAttachment(
        attachment_id=att_id,
        message_id="",
        file_name=file.filename,
        file_type=file.content_type or f"application/{ext}",
        file_size=len(contents),
        file_url=file_url,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return {"status": "success", "data": _attachment_to_dict(attachment)}
