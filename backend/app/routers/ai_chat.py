"""
AI Chat Router - Complete conversation management with proper farmer isolation.
Handles conversation creation, message persistence, and AI provider integration.
"""
import uuid
import secrets
import httpx
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from app.database.connection import get_db
from app.config import settings
from app.utils.auth import get_current_user
from app.models.user import User
from app.models.ai import AIConversation, AIConversationRecord, AISettingsRecord
from app.models.farm import Farm
from app.models.finance import Expense

router = APIRouter(prefix="/api/v1/ai", tags=["AI Chat Assistant"])

# System prompt for AI - agriculture-focused
AI_SYSTEM_PROMPT = """You are Farm Assist AI, an expert agricultural assistant for Indian farmers. 

Your role:
- Provide practical, region-specific farming advice
- Focus on crops, soil, irrigation, pests, diseases, livestock, farm management
- Use simple, friendly language suited for farmers
- Give responses in clear bullet points when appropriate
- Always acknowledge the farmer's specific situation

Format guidance:
- Use bullet points for lists (not large paragraphs)
- Short sentences and clear sections
- Include practical steps or recommendations
- Add cautions where needed

If asked non-agricultural questions, politely redirect:
"I'm Farm Assist AI, focused on agriculture and farming. I can help with crops, livestock, soil, irrigation, pests, and farm management. What farming topic can I help you with?"

Never:
- Make up agricultural facts
- Claim certainty on medical/chemical dosages
- Ignore safety warnings
- Provide advice outside agriculture"""


class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class SettingsUpdate(BaseModel):
    language: Optional[str] = None
    response_style: Optional[str] = None
    appearance: Optional[str] = None
    chat_history_enabled: Optional[bool] = None


def _get_title_from_message(text: str) -> str:
    """Derive a short conversation title from the first user message."""
    text = " ".join((text or "").split())
    if not text:
        return "New Chat"
    return text[:50] + ("..." if len(text) > 50 else "")


def _record_for(db: Session, conversation_id: str, user_id: str) -> AIConversationRecord:
    """Fetch the conversation record owned by user, or None."""
    return db.query(AIConversationRecord).filter(
        AIConversationRecord.conversation_id == conversation_id,
        AIConversationRecord.user_id == user_id,
    ).first()


def _get_or_create_record(db: Session, conversation_id: str, user_id: str, title: str) -> AIConversationRecord:
    """Get the record for this conversation, creating one if it doesn't exist yet."""
    record = _record_for(db, conversation_id, user_id)
    if record:
        return record
    record = AIConversationRecord(
        conversation_id=conversation_id,
        user_id=user_id,
        title=title or "New Chat",
    )
    db.add(record)
    db.flush()
    return record


def _get_ai_response(message: str, current_user: User, db: Session) -> str:
    """
    Get AI response from configured provider with fallback.
    Order: OpenAI → Gemini → Claude → Local
    """
    
    # Build conversation history for context
    history_messages = [
        {"role": "system", "content": AI_SYSTEM_PROMPT},
        {"role": "user", "content": message}
    ]
    
    # Try OpenAI
    if settings.OPENAI_API_KEY:
        try:
            async def openai_call():
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "gpt-4o-mini",
                            "messages": history_messages,
                            "max_tokens": 1000,
                            "temperature": 0.7,
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return data["choices"][0]["message"]["content"]
                    return None
            
            # Try synchronous call as fallback
            import httpx as sync_httpx
            client = sync_httpx.Client(timeout=30)
            try:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": history_messages,
                        "max_tokens": 1000,
                        "temperature": 0.7,
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
            finally:
                client.close()
        except Exception as e:
            pass  # Fall through to next provider
    
    # Try Gemini
    if settings.GEMINI_API_KEY:
        try:
            import httpx as sync_httpx
            client = sync_httpx.Client(timeout=30)
            try:
                resp = client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{
                            "parts": [{"text": message}]
                        }],
                        "systemInstruction": {"parts": [{"text": AI_SYSTEM_PROMPT}]}
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "candidates" in data and len(data["candidates"]) > 0:
                        return data["candidates"][0]["content"]["parts"][0]["text"]
            finally:
                client.close()
        except Exception:
            pass  # Fall through to next provider
    
    # Try Claude
    if settings.ANTHROPIC_API_KEY:
        try:
            import httpx as sync_httpx
            client = sync_httpx.Client(timeout=30)
            try:
                resp = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": settings.ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-3-5-sonnet-20241022",
                        "max_tokens": 1000,
                        "system": AI_SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": message}],
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["content"][0]["text"]
            finally:
                client.close()
        except Exception:
            pass  # Fall through to local
    
    # Local response (always available)
    return _get_local_response(message, current_user, db)


def _get_local_response(message: str, current_user: User, db: Session) -> str:
    """Fallback local AI response based on keyword matching."""
    msg = message.lower()
    
    # Get farmer context
    farms = db.query(Farm).filter(Farm.user_id == current_user.id).all()
    farm_context = ""
    if farms:
        farm_names = [f.farm_name for f in farms]
        farm_context = f"\n\n(I see you have farms: {', '.join(farm_names)})"
    
    # Crop-related queries
    if any(w in msg for w in ["crop", "plant", "cultivat", "grow"]):
        if any(w in msg for w in ["rice", "paddy", "dhaan"]):
            return (
                "🌾 **Rice Cultivation Guide**\n\n"
                "**Best Season:**\n"
                "• Kharif (Jun-Jul)\n"
                "• Rabi (Jan-Feb)\n\n"
                "**Key Steps:**\n"
                "• Maintain 2-5 cm water level during vegetative stage\n"
                "• Use certified seeds (IR-64, Samba Mahsuri, Swarna)\n"
                "• Apply NPK: 120:60:60 kg/ha\n"
                "• Watch for blast disease and brown planthopper\n"
                "• Harvest at 80% grain maturity\n\n"
                "**Important:** Get a soil test before applying fertilizers." + farm_context
            )
        elif any(w in msg for w in ["tomato", "tamatar"]):
            return (
                "🍅 **Tomato Farming**\n\n"
                "**Transplanting:**\n"
                "• Use 25-30 day old seedlings\n"
                "• Spacing: 60cm × 45cm\n\n"
                "**Care:**\n"
                "• Regular irrigation, avoid waterlogging\n"
                "• Stake plants for better quality\n"
                "• Watch for early blight and fruit borer\n"
                "• First harvest: 60-80 days after transplanting\n\n"
                "**Common Issues:**\n"
                "• Leaf curl virus → Remove infected plants\n"
                "• Fruit borer → Use pheromone traps\n"
                "• Early blight → Spray carbendazim (1g/L)" + farm_context
            )
        else:
            return (
                "🌱 **General Crop Advice**\n\n"
                "**Planning:**\n"
                "• Choose based on soil, climate, water availability\n"
                "• Use certified seeds from authorized dealers\n"
                "• Follow proper sowing time for your region\n\n"
                "**Farming:**\n"
                "• Get soil test before planning\n"
                "• Apply balanced fertilizers\n"
                "• Implement Integrated Pest Management (IPM)\n"
                "• Maintain proper irrigation schedule\n"
                "• Keep detailed records\n\n"
                "**Tip:** Rotate crops each season to improve soil health." + farm_context
            )
    
    # Weather & irrigation
    elif any(w in msg for w in ["weather", "rain", "temperature", "irrigat", "water"]):
        return (
            "☀️ **Weather & Irrigation Guide**\n\n"
            "**Before Operations:**\n"
            "• Check weather forecast always\n"
            "• Avoid spraying during rain or extreme heat\n"
            "• Plan based on rainfall predictions\n\n"
            "**Irrigation:**\n"
            "• Drip irrigation saves 30-50% water\n"
            "• Critical stages need more water\n"
            "• Ensure proper drainage in monsoon\n"
            "• Mulching conserves moisture in summer\n\n"
            "**Tip:** Use local weather apps for real-time forecasts." + farm_context
        )
    
    # Finance & expenses
    elif any(w in msg for w in ["expense", "cost", "budget", "finance", "profit", "loss"]):
        total_expenses = 0
        try:
            expenses = db.query(Expense).filter(Expense.user_id == current_user.id).all()
            total_expenses = sum(e.amount for e in expenses if e.amount)
        except:
            pass
        
        return (
            "💰 **Farm Finance**\n\n"
            f"**Your Expenses:** ₹{total_expenses:,.2f}\n\n"
            "**Good Practices:**\n"
            "• Track all farm expenses carefully\n"
            "• Maintain separate records by category\n"
            "• Plan budget season-wise\n"
            "• Keep receipts for tax & loans\n\n"
            "**Income Improvement:**\n"
            "• Explore government subsidies\n"
            "• Consider crop insurance (PMFBY)\n"
            "• Diversify crops for better returns\n"
            "• Sell at peak market rates\n\n"
            "**Tip:** Use Farm Assist Finance tools to track everything." + farm_context
        )
    
    # Pest & disease
    elif any(w in msg for w in ["disease", "pest", "insect", "bug", "yellow", "brown", "leaf", "spot"]):
        return (
            "🐛 **Pest & Disease Management**\n\n"
            "**First Steps:**\n"
            "• Identify the exact pest/disease\n"
            "• Remove infected plant parts\n"
            "• Use Integrated Pest Management (IPM)\n\n"
            "**Treatment Options:**\n"
            "1. Organic: Neem oil, Trichoderma, Pseudomonas\n"
            "2. Chemical: Use only if organic fails\n"
            "3. Biological: Install traps, beneficial insects\n\n"
            "**Prevention:**\n"
            "• Proper plant spacing for air flow\n"
            "• Crop rotation breaks pest cycles\n"
            "• Avoid waterlogging\n"
            "• Keep field clean\n\n"
            "**⚠️ Important:** Consult agricultural expert for diagnosis." + farm_context
        )
    
    # Market & selling
    elif any(w in msg for w in ["market", "sell", "price", "rate", "mandi", "buyer"]):
        return (
            "🏪 **Market & Selling Tips**\n\n"
            "**Selling Strategies:**\n"
            "• Sell when prices are high\n"
            "• Direct selling avoids middlemen\n"
            "• Join farmer cooperatives\n"
            "• Store well to sell later\n\n"
            "**Using Farm Assist:**\n"
            "• Check live market prices\n"
            "• Register as seller\n"
            "• Connect with direct buyers\n"
            "• Join marketplace groups\n\n"
            "**Tip:** Compare 3 markets before selling." + farm_context
        )
    
    # Government schemes
    elif any(w in msg for w in ["government", "scheme", "yojana", "subsidy", "loan", "pm-"]):
        return (
            "🏛️ **Government Schemes**\n\n"
            "**Major Schemes:**\n"
            "• PM-KISAN: ₹6,000/year in 3 installments\n"
            "• PMFBY: Crop insurance at low premium\n"
            "• KCC: Kisan Credit Card for loans\n"
            "• PM-KUSUM: Solar energy solutions\n\n"
            "**On Farm Assist:**\n"
            "• Check all available schemes\n"
            "• Easy eligibility checking\n"
            "• Help with applications\n"
            "• Track approval status\n\n"
            "**Tip:** Apply early to avoid delays." + farm_context
        )
    
    # Greeting
    elif any(w in msg for w in ["hello", "hi", "namaste", "hey"]):
        return (
            "🌾 **Welcome to Farm Assist AI!**\n\n"
            "I'm here to help with:\n"
            "• Crop cultivation & planning\n"
            "• Pest & disease management\n"
            "• Irrigation & water management\n"
            "• Farm finances & tracking\n"
            "• Weather & seasonal advice\n"
            "• Government schemes\n"
            "• Market prices & selling\n"
            "• Livestock care\n\n"
            "**Ask me anything about farming!**" + farm_context
        )
    
    # Default response
    else:
        return (
            "🤔 **Need help with your farm?**\n\n"
            "Try asking about:\n"
            "• 'How to grow rice?' → Crop guidance\n"
            "• 'My tomato leaves are yellow' → Diagnosis\n"
            "• 'How much water do crops need?' → Irrigation advice\n"
            "• 'What's the market price?' → Market info\n"
            "• 'Government schemes' → Subsidy info\n"
            "• 'Pest management' → Disease solutions\n\n"
            "I focus on farming & agriculture topics.\n"
            "Describe your farm situation for better advice!" + farm_context
        )


# ==================== API ENDPOINTS ====================

@router.post("/conversations", status_code=201)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new AI conversation with persisted metadata."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Generate conversation ID
    conv_id = f"conv-{uuid.uuid4().hex[:12]}"
    
    record = AIConversationRecord(
        conversation_id=conv_id,
        user_id=current_user.id,
        title=payload.title or "New Chat",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    
    return {
        "status": "success",
        "data": {
            "conversation_id": conv_id,
            "title": record.title,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
    }


@router.get("/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all conversations for the authenticated user with titles."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from sqlalchemy import func, and_
    
    # Get unique conversations with latest message for each
    subquery = db.query(
        AIConversation.conversation_id,
        func.max(AIConversation.created_at).label("max_created"),
    ).filter(
        AIConversation.user_id == current_user.id
    ).group_by(
        AIConversation.conversation_id
    ).subquery()
    
    conversations = db.query(AIConversation).join(
        subquery,
        and_(
            AIConversation.conversation_id == subquery.c.conversation_id,
            AIConversation.created_at == subquery.c.max_created
        )
    ).order_by(desc(AIConversation.created_at)).all()
    
    # Map conversation_id -> record
    conv_ids = [c.conversation_id for c in conversations]
    records = {}
    if conv_ids:
        for rec in db.query(AIConversationRecord).filter(
            AIConversationRecord.conversation_id.in_(conv_ids),
            AIConversationRecord.user_id == current_user.id
        ).all():
            records[rec.conversation_id] = rec
    
    result = []
    for conv in conversations:
        cid = conv.conversation_id
        record = records.get(cid)
        
        # Backfill record if missing (legacy conversations)
        if record is None:
            record = _get_or_create_record(db, cid, current_user.id, _get_title_from_message(conv.content))
            db.flush()
        
        # Count messages in this conversation
        msg_count = db.query(func.count(AIConversation.id)).filter(
            AIConversation.conversation_id == cid,
            AIConversation.user_id == current_user.id
        ).scalar() or 0
        
        result.append({
            "conversation_id": cid,
            "title": record.title or cid,
            "message_count": msg_count,
            "last_message": conv.content[:100] if conv.content else "",
            "last_updated": (conv.created_at or record.updated_at).isoformat() if (conv.created_at or record.updated_at) else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "is_shared": record.is_shared or False,
        })
    
    db.commit()
    
    return {
        "status": "success",
        "data": {
            "conversations": result,
            "total": len(result),
        }
    }


@router.get("/conversations/search")
def search_conversations(
    q: str = Query(..., min_length=1, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search conversations by title or message content."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Search message content
    content_hits = db.query(AIConversation).filter(
        AIConversation.user_id == current_user.id,
        AIConversation.content.ilike(f"%{q}%")
    ).order_by(desc(AIConversation.created_at)).all()
    
    # Search titles in records
    title_hits = db.query(AIConversationRecord).filter(
        AIConversationRecord.user_id == current_user.id,
        AIConversationRecord.title.ilike(f"%{q}%")
    ).order_by(desc(AIConversationRecord.updated_at)).all()
    
    # Merge into ordered unique conversation list
    ordered_ids = []
    merged = {}
    for rec in title_hits:
        if rec.conversation_id not in merged:
            merged[rec.conversation_id] = {
                "conversation_id": rec.conversation_id,
                "title": rec.title,
                "matched_messages": [],
            }
            ordered_ids.append(rec.conversation_id)
    for msg in content_hits:
        cid = msg.conversation_id
        if cid not in merged:
            first = db.query(AIConversationRecord).filter(
                AIConversationRecord.conversation_id == cid,
                AIConversationRecord.user_id == current_user.id
            ).first()
            merged[cid] = {
                "conversation_id": cid,
                "title": (first.title if first else None) or cid,
                "matched_messages": [],
            }
            ordered_ids.append(cid)
        merged[cid]["matched_messages"].append({
            "role": msg.role,
            "content": msg.content[:200],
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })
    
    results = [merged[cid] for cid in ordered_ids][:20]
    
    return {
        "status": "success",
        "data": {
            "query": q,
            "results": results,
            "count": len(results),
        }
    }


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific conversation with all its messages."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Verify ownership
    first_msg = db.query(AIConversation).filter(
        AIConversation.conversation_id == conversation_id,
        AIConversation.user_id == current_user.id
    ).first()
    
    if not first_msg:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get all messages in order
    messages = db.query(AIConversation).filter(
        AIConversation.conversation_id == conversation_id,
        AIConversation.user_id == current_user.id
    ).order_by(AIConversation.created_at.asc()).all()
    
    message_list = [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
        for msg in messages
    ]
    
    record = _record_for(db, conversation_id, current_user.id)
    
    return {
        "status": "success",
        "data": {
            "conversation_id": conversation_id,
            "title": (record.title if record else None) or conversation_id,
            "is_shared": bool(record.is_shared) if record else False,
            "messages": message_list,
            "message_count": len(message_list),
        }
    }


@router.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message and get AI response."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    message_text = payload.content.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    if len(message_text) > 5000:
        raise HTTPException(status_code=400, detail="Message too long")
    
    # Verify ownership or create if new
    existing = db.query(AIConversation).filter(
        AIConversation.conversation_id == conversation_id,
        AIConversation.user_id == current_user.id
    ).first()
    
    if not existing:
        # Check if conversation exists for another user (security)
        other_user_conv = db.query(AIConversation).filter(
            AIConversation.conversation_id == conversation_id
        ).first()
        
        if other_user_conv and other_user_conv.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Unauthorized")
    
    # Store user message
    user_msg = AIConversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        role="user",
        content=message_text,
        model="latest",
    )
    db.add(user_msg)
    db.flush()
    
    # Get or create the conversation record; auto-title from first user message
    existing_record = _record_for(db, conversation_id, current_user.id)
    if existing_record is None:
        existing_record = _get_or_create_record(db, conversation_id, current_user.id, _get_title_from_message(message_text))
    elif existing_record.title in (None, "", "New Chat"):
        existing_record.title = _get_title_from_message(message_text)
    existing_record.updated_at = datetime.utcnow()
    db.flush()
    
    # Get AI response
    ai_response = _get_ai_response(message_text, current_user, db)
    
    # Store AI response
    ai_msg = AIConversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        role="assistant",
        content=ai_response,
        model="latest",
    )
    db.add(ai_msg)
    db.commit()
    
    return {
        "status": "success",
        "data": {
            "conversation_id": conversation_id,
            "user_message": {
                "id": user_msg.id,
                "role": "user",
                "content": message_text,
                "created_at": user_msg.created_at.isoformat() if user_msg.created_at else None,
            },
            "ai_message": {
                "id": ai_msg.id,
                "role": "assistant",
                "content": ai_response,
                "created_at": ai_msg.created_at.isoformat() if ai_msg.created_at else None,
            }
        }
    }


@router.post("/conversations/{conversation_id}/regenerate")
def regenerate_last_response(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Regenerate the last assistant response for a conversation."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Verify ownership
    messages = db.query(AIConversation).filter(
        AIConversation.conversation_id == conversation_id,
        AIConversation.user_id == current_user.id
    ).order_by(AIConversation.created_at.asc()).all()
    
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Drop trailing assistant messages; keep the newest user message as prompt
    while messages and messages[-1].role == "assistant":
        db.delete(messages.pop())
    
    if not messages:
        raise HTTPException(status_code=400, detail="No user message to regenerate from")
    
    prompt = messages[-1].content
    db.flush()
    
    ai_response = _get_ai_response(prompt, current_user, db)
    
    ai_msg = AIConversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        role="assistant",
        content=ai_response,
        model="latest",
    )
    db.add(ai_msg)
    
    record = _record_for(db, conversation_id, current_user.id)
    if record:
        record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ai_msg)
    
    return {
        "status": "success",
        "data": {
            "conversation_id": conversation_id,
            "ai_message": {
                "id": ai_msg.id,
                "role": "assistant",
                "content": ai_response,
                "created_at": ai_msg.created_at.isoformat() if ai_msg.created_at else None,
            }
        }
    }


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a conversation and all its messages."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Verify ownership
    conversations = db.query(AIConversation).filter(
        AIConversation.conversation_id == conversation_id,
        AIConversation.user_id == current_user.id
    ).all()
    
    if not conversations:
        # No messages yet; check if a record exists
        record = _record_for(db, conversation_id, current_user.id)
        if not record:
            raise HTTPException(status_code=404, detail="Conversation not found")
        db.delete(record)
        db.commit()
        return {
            "status": "success",
            "message": "Conversation deleted"
        }
    
    # Delete all messages in conversation
    for msg in conversations:
        db.delete(msg)
    
    # Delete the metadata record if present
    record = _record_for(db, conversation_id, current_user.id)
    if record:
        db.delete(record)
    
    db.commit()
    
    return {
        "status": "success",
        "message": "Conversation deleted"
    }


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rename a conversation. Persists the title."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    record = _record_for(db, conversation_id, current_user.id)
    if record is None:
        # Only allow rename if user owns messages in the conversation
        owned = db.query(AIConversation).filter(
            AIConversation.conversation_id == conversation_id,
            AIConversation.user_id == current_user.id
        ).first()
        if not owned:
            raise HTTPException(status_code=404, detail="Conversation not found")
        record = _get_or_create_record(db, conversation_id, current_user.id, payload.title)
    
    record.title = payload.title.strip()
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    
    return {
        "status": "success",
        "data": {
            "conversation_id": conversation_id,
            "title": record.title,
        }
    }




# ==================== SHARE ENDPOINTS ====================

@router.post("/conversations/{conversation_id}/share")
def share_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a read-only share link for a conversation owned by the user."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    record = _record_for(db, conversation_id, current_user.id)
    if record is None:
        owned = db.query(AIConversation).filter(
            AIConversation.conversation_id == conversation_id,
            AIConversation.user_id == current_user.id
        ).first()
        if not owned:
            raise HTTPException(status_code=404, detail="Conversation not found")
        record = _get_or_create_record(db, conversation_id, current_user.id, _get_title_from_message(owned.content))
    
    if not record.share_token:
        record.share_token = secrets.token_urlsafe(24)
    record.is_shared = True
    db.commit()
    db.refresh(record)
    
    return {
        "status": "success",
        "data": {
            "conversation_id": conversation_id,
            "share_token": record.share_token,
            "is_shared": True,
        }
    }


@router.delete("/conversations/{conversation_id}/share")
def revoke_share(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke the share link for a conversation."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    record = _record_for(db, conversation_id, current_user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    record.is_shared = False
    record.share_token = None
    db.commit()
    
    return {
        "status": "success",
        "message": "Share link revoked"
    }


@router.get("/shared/{token}")
def get_shared_conversation(
    token: str,
    db: Session = Depends(get_db),
):
    """View a shared conversation read-only (no auth required)."""
    record = db.query(AIConversationRecord).filter(
        AIConversationRecord.share_token == token,
        AIConversationRecord.is_shared == True
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Shared conversation not found")
    
    messages = db.query(AIConversation).filter(
        AIConversation.conversation_id == record.conversation_id,
        AIConversation.user_id == record.user_id
    ).order_by(AIConversation.created_at.asc()).all()
    
    return {
        "status": "success",
        "data": {
            "conversation_id": record.conversation_id,
            "title": record.title,
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ],
        }
    }


# ==================== SETTINGS ENDPOINTS ====================

@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the authenticated user's AI chat settings."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    record = db.query(AISettingsRecord).filter(
        AISettingsRecord.user_id == current_user.id
    ).first()
    
    if record is None:
        return {
            "status": "success",
            "data": {
                "language": "en",
                "response_style": "friendly",
                "appearance": "system",
                "chat_history_enabled": True,
            }
        }
    
    return {
        "status": "success",
        "data": {
            "language": record.language or "en",
            "response_style": record.response_style or "friendly",
            "appearance": record.appearance or "system",
            "chat_history_enabled": record.chat_history_enabled if record.chat_history_enabled is not None else True,
        }
    }


@router.put("/settings")
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist the authenticated user's AI chat settings."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    record = db.query(AISettingsRecord).filter(
        AISettingsRecord.user_id == current_user.id
    ).first()
    
    if record is None:
        record = AISettingsRecord(user_id=current_user.id)
        db.add(record)
    
    if payload.language is not None:
        record.language = payload.language
    if payload.response_style is not None:
        record.response_style = payload.response_style
    if payload.appearance is not None:
        record.appearance = payload.appearance
    if payload.chat_history_enabled is not None:
        record.chat_history_enabled = payload.chat_history_enabled
    record.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(record)
    
    return {
        "status": "success",
        "data": {
            "language": record.language or "en",
            "response_style": record.response_style or "friendly",
            "appearance": record.appearance or "system",
            "chat_history_enabled": record.chat_history_enabled if record.chat_history_enabled is not None else True,
        }
    }
