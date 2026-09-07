import os
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.config import settings
from app.utils.auth import get_current_user, generate_id
from app.models.user import User
from app.models.ai import AIConversation, AIRecommendation
from app.models.farm import Farm

router = APIRouter(prefix="/api/v1", tags=["AI Assistant"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    model: str = "local"


class AnalyzeFarmRequest(BaseModel):
    farm_id: Optional[str] = None


class DiagnoseRequest(BaseModel):
    symptoms: str
    crop_type: Optional[str] = None
    image_description: Optional[str] = None
    image_url: Optional[str] = None


def _get_local_response(message: str, user: User, db: Session) -> str:
    msg = message.lower()

    farms = db.query(Farm).filter(Farm.user_id == user.id).all()
    farm_context = ""
    if farms:
        farm_names = [f.farm_name for f in farms]
        farm_context = f" (Your farms: {', '.join(farm_names)})"

    if any(w in msg for w in ["crop", "plant", "seed", "sow", "harvest"]):
        if any(w in msg for w in ["rice", "paddy", "dhaan"]):
            return (
                f"Rice Cultivation Advice{farm_context}:\n"
                "- Sow during Kharif (Jun-Jul) or Rabi (Jan-Feb) season\n"
                "- Maintain water level of 2-5 cm during vegetative stage\n"
                "- Use certified seeds (IR-64, Samba Mahsuri, or Swarna)\n"
                "- Apply NPK fertilizer: 120:60:60 kg/ha\n"
                "- Watch for blast disease and brown planthopper\n"
                "- Harvest when 80% grains turn golden"
            )
        elif any(w in msg for w in ["wheat", "gehu"]):
            return (
                f"Wheat Cultivation Advice{farm_context}:\n"
                "- Sow in Rabi season (Nov-Dec) after rice harvest\n"
                "- Use certified seeds: HD-3226, PBW-723, or WH-1270\n"
                "- Sowing rate: 100-125 kg/ha with row spacing 20-23 cm\n"
                "- Apply NPK: 120:60:60 kg/ha (half N at sowing, half at first irrigation)\n"
                "- Irrigate at critical stages: crown root, tillering, jointing, flowering\n"
                "- Harvest when grain moisture is around 14%"
            )
        elif any(w in msg for w in ["tomato", "tamatar"]):
            return (
                f"Tomato Farming Advice{farm_context}:\n"
                "- Transplant seedlings at 25-30 days old\n"
                "- Spacing: 60cm x 45cm for determinate varieties\n"
                "- Regular irrigation but avoid waterlogging\n"
                "- Stake plants for better fruit quality\n"
                "- Watch for early blight, fruit borer, and leaf curl virus\n"
                "- First harvest typically 60-80 days after transplanting"
            )
        elif any(w in msg for w in ["cotton", "kapas"]):
            return (
                f"Cotton Cultivation Advice{farm_context}:\n"
                "- Sow during Kharif season (May-June) when soil temp > 20C\n"
                "- Use Bt cotton hybrids for better pest resistance\n"
                "- Spacing: 90cm x 60cm\n"
                "- Apply NPK: 120:60:60 kg/ha\n"
                "- Irrigate every 10-15 days during critical stages\n"
                "- Watch for bollworm, whitefly, and aphids"
            )
        else:
            return (
                f"General Crop Advice{farm_context}:\n"
                "- Choose crops based on your soil type, climate, and water availability\n"
                "- Use certified and quality seeds from authorized dealers\n"
                "- Follow proper sowing time for your region\n"
                "- Apply balanced fertilizers based on soil test\n"
                "- Implement Integrated Pest Management (IPM)\n"
                "- Maintain proper irrigation schedule\n"
                "- Keep records of all activities for future reference"
            )
    elif any(w in msg for w in ["weather", "rain", "temperature", "climate", "mausam"]):
        return (
            f"Weather Advisory{farm_context}:\n"
            "- Check weather forecast before scheduling field operations\n"
            "- Avoid spraying pesticides during rain or extreme heat\n"
            "- Ensure proper drainage during heavy rainfall\n"
            "- Protect crops from frost during winter\n"
            "- Use mulching to conserve moisture in summer\n"
            "- Plan irrigation based on weather predictions\n"
            "Tip: Use the /api/v1/weather/current endpoint with your coordinates for real-time weather."
        )
    elif any(w in msg for w in ["expense", "cost", "budget", "money", "kharcha", "paisa"]):
        total_expenses = 0
        from app.models.finance import Expense
        expenses = db.query(Expense).filter(Expense.user_id == user.id).all()
        total_expenses = sum(e.amount for e in expenses if e.amount)

        return (
            f"Financial Advice{farm_context}:\n"
            f"- Your recorded expenses: Rs. {total_expenses:,.2f}\n"
            "- Track all farm expenses for better financial planning\n"
            "- Maintain separate records for different expense categories\n"
            "- Plan budget for each crop season in advance\n"
            "- Look into government subsidies and crop insurance\n"
            "- Consider crop diversification for better income\n"
            "- Keep receipts for tax benefits and loan applications"
        )
    elif any(w in msg for w in ["worker", "labor", "hire", "mazdoor"]):
        return (
            f"Worker Management Advice{farm_context}:\n"
            "- Browse available workers in the /api/v1/workers section\n"
            "- Check worker ratings and reviews before booking\n"
            "- Define clear work requirements and payment terms\n"
            "- Keep records of worker payments\n"
            "- Consider hiring skilled workers for specific tasks\n"
            "- Build long-term relationships with reliable workers"
        )
    elif any(w in msg for w in ["disease", "pest", "insect", "bug", "rog", "keet"]):
        return (
            f"Plant Health Advisory{farm_context}:\n"
            "- Identify the exact disease/pest before applying treatment\n"
            "- Use Integrated Pest Management (IPM) approach\n"
            "- Start with organic remedies: neem oil, Trichoderma, Pseudomonas\n"
            "- Use chemical pesticides as last resort and follow dosage\n"
            "- Remove and destroy infected plant parts\n"
            "- Ensure proper spacing for air circulation\n"
            "- Rotate crops to break pest cycles\n"
            "Tip: Describe the symptoms and I can provide more specific advice."
        )
    elif any(w in msg for w in ["market", "sell", "price", "rate", "bazaar"]):
        return (
            f"Market Advisory{farm_context}:\n"
            "- Check current market prices in the Marketplace section\n"
            "- Sell during peak market rates for better returns\n"
            "- Consider direct selling to buyers to avoid middlemen\n"
            "- Store produce properly to sell when prices improve\n"
            "- Register as a seller on Farm Assist marketplace\n"
            "- Join farmer cooperatives for collective bargaining"
        )
    elif any(w in msg for w in ["government", "scheme", "yojana", "subsidy"]):
        return (
            f"Government Schemes{farm_context}:\n"
            "- Check available schemes in /api/v1/government-schemes\n"
            "- PM-KISAN: Rs. 6,000/year in 3 installments\n"
            "- PMFBY: Crop insurance at low premium\n"
            "- KCC: Kisan Credit Card for easy farm loans\n"
            "- PM-KUSUM: Solar energy for farmers\n"
            "- Apply through Farm Assist for streamlined process"
        )
    elif any(w in msg for w in ["hello", "hi", "namaste", "hey"]):
        return (
            f"Namaste{farm_context}! Welcome to Farm Assist AI.\n"
            "I can help you with:\n"
            "- Crop cultivation advice\n"
            "- Weather information\n"
            "- Financial planning\n"
            "- Worker and equipment hiring\n"
            "- Disease and pest management\n"
            "- Market prices and selling\n"
            "- Government schemes\n"
            "What would you like to know?"
        )
    elif any(w in msg for w in ["thank", "shukriya", "dhanyavad"]):
        return "You're welcome! Feel free to ask if you need any more farming advice. Happy farming!"
    else:
        return (
            f"I'm here to help with your farming needs{farm_context}.\n"
            "Try asking about:\n"
            "- 'How to grow rice?' - Crop advice\n"
            "- 'Weather in my area' - Weather info\n"
            "- 'Track my expenses' - Financial help\n"
            "- 'Find farm workers' - Labor management\n"
            "- 'My tomato plants have yellow leaves' - Disease diagnosis\n"
            "- 'Government schemes for farmers' - Scheme info\n"
            "Or just describe your farming question!"
        )


@router.post("/ai/chat")
def ai_chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = payload.message
    conversation_id = payload.conversation_id
    model = payload.model or "local"
    if not conversation_id:
        conversation_id = f"FA-CON-{uuid.uuid4().hex[:8].upper()}"
    else:
        # Enforce ownership: if the supplied conversation already exists, it must
        # belong to this user. Prevents reading/poisoning another user's history.
        existing = (
            db.query(AIConversation)
            .filter(AIConversation.conversation_id == conversation_id)
            .first()
        )
        if existing and existing.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Conversation not found")

    user_msg = AIConversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        role="user",
        content=message,
        model=model,
    )
    db.add(user_msg)
    db.commit()

    assistant_response = None
    tokens_used = 0

    if model == "openai" and settings.OPENAI_API_KEY:
        try:
            import httpx
            history = (
                db.query(AIConversation)
                .filter(
                    AIConversation.conversation_id == conversation_id,
                    AIConversation.user_id == current_user.id,
                )
                .order_by(AIConversation.created_at.asc())
                .all()
            )
            messages = [{"role": "system", "content": "You are a helpful farming assistant for Indian farmers. Provide practical, actionable advice."}]
            for h in history:
                messages.append({"role": h.role, "content": h.content})
            messages.append({"role": "user", "content": message})

            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={"model": "gpt-4o-mini", "messages": messages, "max_tokens": 1000},
                )
                resp.raise_for_status()
                data = resp.json()
            assistant_response = data["choices"][0]["message"]["content"]
            tokens_used = data.get("usage", {}).get("total_tokens", 0)
        except Exception:
            assistant_response = _get_local_response(message, current_user, db)
    elif model == "gemini" and settings.GEMINI_API_KEY:
        try:
            import httpx
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={settings.GEMINI_API_KEY}",
                    json={"contents": [{"parts": [{"text": message}]}]},
                )
                resp.raise_for_status()
                data = resp.json()
            assistant_response = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            assistant_response = _get_local_response(message, current_user, db)
    elif model == "claude" and settings.ANTHROPIC_API_KEY:
        try:
            import httpx
            with httpx.Client(timeout=30) as client:
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
                        "messages": [{"role": "user", "content": message}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            assistant_response = data["content"][0]["text"]
        except Exception:
            assistant_response = _get_local_response(message, current_user, db)
    else:
        assistant_response = _get_local_response(message, current_user, db)

    ai_msg = AIConversation(
        conversation_id=conversation_id,
        user_id=current_user.id,
        role="assistant",
        content=assistant_response,
        model=model,
        tokens_used=tokens_used,
    )
    db.add(ai_msg)
    db.commit()

    return {
        "status": "success",
        "data": {
            "conversation_id": conversation_id,
            "response": assistant_response,
            "model": model,
            "tokens_used": tokens_used,
        },
    }


@router.post("/ai/recommendations")
def get_recommendations(
    payload: AnalyzeFarmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    farm_id = payload.farm_id
    q = db.query(AIRecommendation).filter(AIRecommendation.user_id == current_user.id)
    if farm_id:
        q = q.filter(AIRecommendation.farm_id == farm_id)

    existing = q.order_by(AIRecommendation.created_at.desc()).limit(10).all()

    if existing:
        return {
            "status": "success",
            "data": {
                "recommendations": [
                    {
                        "id": r.id,
                        "type": r.recommendation_type,
                        "title": r.title,
                        "description": r.description,
                        "priority": r.priority,
                        "is_read": r.is_read,
                        "is_applied": r.is_applied,
                        "created_at": str(r.created_at) if r.created_at else None,
                    }
                    for r in existing
                ]
            },
        }

    farm = None
    if farm_id:
        farm = db.query(Farm).filter(Farm.id == farm_id, Farm.user_id == current_user.id).first()
    elif not farm:
        farm = db.query(Farm).filter(Farm.user_id == current_user.id).first()

    recs = []
    default_recs = [
        {"type": "crop", "title": "Try Crop Rotation", "description": "Rotate your crops to improve soil health. Consider pulses or oilseeds after cereal crops.", "priority": "medium"},
        {"type": "finance", "title": "Review Monthly Expenses", "description": "Track your farm expenses regularly. Use the Finance section to categorize and monitor spending.", "priority": "medium"},
        {"type": "weather", "title": "Monitor Weather Conditions", "description": "Check weather forecasts before scheduling irrigation or spraying. Use the Weather section for real-time data.", "priority": "low"},
        {"type": "irrigation", "title": "Optimize Irrigation", "description": "Consider drip irrigation to save water and improve yields. Can reduce water usage by 30-50%.", "priority": "medium"},
    ]

    for rec in default_recs:
        arec = AIRecommendation(
            user_id=current_user.id,
            farm_id=farm_id,
            recommendation_type=rec["type"],
            title=rec["title"],
            description=rec["description"],
            priority=rec["priority"],
        )
        db.add(arec)
        recs.append(arec)

    db.commit()

    return {
        "status": "success",
        "data": {
            "recommendations": [
                {
                    "id": r.id,
                    "type": r.recommendation_type,
                    "title": r.title,
                    "description": r.description,
                    "priority": r.priority,
                }
                for r in recs
            ]
        },
    }


@router.post("/ai/analyze-farm")
def analyze_farm(
    payload: AnalyzeFarmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    farm_id = payload.farm_id
    farm = None
    if farm_id:
        farm = (
            db.query(Farm)
            .filter(Farm.user_id == current_user.id)
            .filter((Farm.id == farm_id) | (Farm.farm_id == farm_id))
            .first()
        )
    if not farm:
        farm = db.query(Farm).filter(Farm.user_id == current_user.id).order_by(Farm.created_at.asc()).first()
    if not farm:
        raise HTTPException(status_code=404, detail="No farm found. Create a farm first.")

    from app.models.finance import Expense, Income
    from app.models.crop import CropCycle

    from sqlalchemy import or_
    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        or_(Expense.farm_id == farm.id, Expense.farm_id == farm.farm_id),
    ).all()
    incomes = db.query(Income).filter(
        Income.user_id == current_user.id,
        or_(Income.farm_id == farm.id, Income.farm_id == farm.farm_id),
    ).all()
    cycles = db.query(CropCycle).filter(
        or_(CropCycle.farm_id == farm.id, CropCycle.farm_id == farm.farm_id)
    ).all()

    total_expense = sum(e.amount for e in expenses if e.amount)
    total_income = sum(i.amount for i in incomes if i.amount)
    active_cycles = len([c for c in cycles if c.status == "active"])

    analysis = {
        "farm_id": farm.farm_id,
        "farm_name": farm.farm_name,
        "total_area": farm.total_area,
        "area_unit": farm.area_unit,
        "soil_type": farm.soil_type,
        "total_expenses": total_expense,
        "total_income": total_income,
        "net_profit": total_income - total_expense,
        "active_crop_cycles": active_cycles,
        "profit_margin": round(((total_income - total_expense) / total_income * 100), 2) if total_income > 0 else 0,
        "suggestions": [],
    }

    if total_expense > 0 and total_income > 0:
        margin = (total_income - total_expense) / total_income * 100
        if margin < 20:
            analysis["suggestions"].append("Profit margin is low. Consider reducing input costs or exploring higher-value crops.")
        else:
            analysis["suggestions"].append("Good profit margin. Consider reinvesting in farm improvements.")

    if not farm.water_source:
        analysis["suggestions"].append("Consider adding a water source for reliable irrigation.")
    if not farm.soil_type:
        analysis["suggestions"].append("Get a soil test done to understand your land better.")
    if active_cycles == 0:
        analysis["suggestions"].append("No active crop cycles. Plan your next planting season.")

    return {"status": "success", "data": {"analysis": analysis}}


@router.post("/ai/diagnose")
def diagnose_crop_issue(
    payload: DiagnoseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    symptoms = payload.symptoms
    crop_type = payload.crop_type
    sym = symptoms.lower()
    diagnosis = {
        "symptoms": symptoms,
        "crop_type": crop_type,
        "possible_issues": [],
        "recommendations": [],
    }

    if any(w in sym for w in ["yellow", "pale", "light green"]):
        diagnosis["possible_issues"].append({
            "issue": "Nutrient Deficiency (Nitrogen/Iron)",
            "confidence": "high",
            "description": "Yellowing of leaves often indicates nitrogen or iron deficiency.",
        })
        diagnosis["recommendations"].extend([
            "Apply nitrogen-rich fertilizer (Urea: 50 kg/ha)",
            "Check soil pH - iron deficiency occurs in alkaline soils",
            "Consider foliar spray of ferrous sulfate (0.5%)",
        ])

    if any(w in sym for w in ["brown", "spot", "lesion", "blight"]):
        diagnosis["possible_issues"].append({
            "issue": "Fungal Disease (Blight/Leaf Spot)",
            "confidence": "high",
            "description": "Brown spots or lesions indicate fungal infection.",
        })
        diagnosis["recommendations"].extend([
            "Remove and destroy affected leaves",
            "Spray fungicide: Mancozeb (2.5g/L) or Carbendazim (1g/L)",
            "Ensure proper plant spacing for air circulation",
            "Avoid overhead irrigation",
        ])

    if any(w in sym for w in ["wilting", "drooping", "collapse"]):
        diagnosis["possible_issues"].append({
            "issue": "Wilt Disease / Water Stress",
            "confidence": "medium",
            "description": "Wilting can be caused by Fusarium wilt, root rot, or water stress.",
        })
        diagnosis["recommendations"].extend([
            "Check soil moisture - waterlogged or dry soil can cause wilting",
            "Inspect roots for rot or damage",
            "Apply Trichoderma viride (4g/kg soil) for soil-borne diseases",
            "Ensure proper drainage",
        ])

    if any(w in sym for w in ["insect", "worm", "eat", "holes", "bite"]):
        diagnosis["possible_issues"].append({
            "issue": "Pest Damage",
            "confidence": "high",
            "description": "Visible insect damage or pest presence detected.",
        })
        diagnosis["recommendations"].extend([
            "Identify the specific pest for targeted treatment",
            "Use neem oil spray (5ml/L) as first line of defense",
            "Install yellow sticky traps for whiteflies and aphids",
            "Consider biological control agents",
        ])

    if any(w in sym for w in ["root", "rot", "mold", "fungus"]):
        diagnosis["possible_issues"].append({
            "issue": "Root Rot / Soil Disease",
            "confidence": "medium",
            "description": "Root-related issues often from waterlogged or pathogen-infected soil.",
        })
        diagnosis["recommendations"].extend([
            "Improve soil drainage",
            "Apply Trichoderma harzianum to soil",
            "Reduce irrigation frequency",
            "Consider raised bed cultivation",
        ])

    if not diagnosis["possible_issues"]:
        diagnosis["possible_issues"].append({
            "issue": "Insufficient Information",
            "confidence": "low",
            "description": "Could not determine a specific issue from the described symptoms.",
        })
        diagnosis["recommendations"].extend([
            "Provide more details about the symptoms (color, pattern, affected parts)",
            "Mention when the symptoms first appeared",
            "Include information about recent weather and farming activities",
            "Take clear photos of affected plants for better diagnosis",
        ])

    diagnosis["disclaimer"] = "This is an AI-based preliminary diagnosis. For accurate diagnosis, consult a local agricultural expert or visit the nearest KVK (Krishi Vigyan Kendra)."

    return {"status": "success", "data": {"diagnosis": diagnosis}}
