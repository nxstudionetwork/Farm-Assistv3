import httpx
import json
from typing import Optional
from app.config import settings


async def chat_with_ai(message: str, conversation_id: Optional[str] = None, model: Optional[str] = None) -> dict:
    if settings.OPENAI_API_KEY and model in (None, "openai", "gpt"):
        return await _openai_chat(message, conversation_id)
    elif settings.GEMINI_API_KEY and model in (None, "gemini"):
        return await _gemini_chat(message, conversation_id)
    elif settings.ANTHROPIC_API_KEY and model in (None, "claude"):
        return await _claude_chat(message, conversation_id)
    else:
        return _local_farm_assistant(message, conversation_id)


async def _openai_chat(message: str, conversation_id: Optional[str] = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are Farm Assist AI, an expert agricultural assistant helping Indian farmers. Provide practical, region-specific advice about farming, crops, weather, finance, and government schemes. Respond in simple, helpful language."},
                        {"role": "user", "content": message},
                    ],
                    "max_tokens": 1000,
                },
            )
            if response.status_code == 200:
                data = response.json()
                return {"response": data["choices"][0]["message"]["content"], "model": "openai", "conversation_id": conversation_id}
    except Exception:
        pass
    return _local_farm_assistant(message, conversation_id)


async def _gemini_chat(message: str, conversation_id: Optional[str] = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={settings.GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": f"You are Farm Assist AI, an expert Indian agriculture assistant.\n\nUser: {message}"}]}]},
            )
            if response.status_code == 200:
                data = response.json()
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text:
                    return {"response": text, "model": "gemini", "conversation_id": conversation_id}
    except Exception:
        pass
    return _local_farm_assistant(message, conversation_id)


async def _claude_chat(message: str, conversation_id: Optional[str] = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": f"You are Farm Assist AI, an expert Indian agriculture assistant. Help the farmer with their question: {message}"}],
                },
            )
            if response.status_code == 200:
                data = response.json()
                text = data.get("content", [{}])[0].get("text", "")
                if text:
                    return {"response": text, "model": "claude", "conversation_id": conversation_id}
    except Exception:
        pass
    return _local_farm_assistant(message, conversation_id)


def _local_farm_assistant(message: str, conversation_id: Optional[str] = None) -> dict:
    msg = message.lower()

    if any(w in msg for w in ["yellow", "leaves", "yellowing"]):
        response = "Yellowing leaves can indicate several issues:\n1. **Nitrogen deficiency** - Apply urea or DAP fertilizer\n2. **Overwatering** - Check drainage, reduce irrigation\n3. **Pest infestation** - Check for aphids or mites underneath leaves\n4. **Iron deficiency** - Apply iron sulphate (2g/L)\n\nRecommendation: Check soil moisture and recent fertilizer application. If leaves are yellow at bottom, it's likely nitrogen deficiency."
    elif any(w in msg for w in ["rain", "rainfall", "monsoon", "rainy"]):
        response = "Based on current weather patterns:\n- Keep drainage channels clear\n- Avoid fertilizer application 24 hours before rain\n- Harvest mature crops before heavy rain\n- Store harvested produce in dry locations\n- Monitor waterlogged fields closely\n\nTip: Use the Weather section in the app for 7-day forecast updates."
    elif any(w in msg for w in ["price", "market", "sell", "rate", "mandi"]):
        response = "Current market guidance:\n- Check the Market Prices section for real-time mandi rates\n- Compare prices across nearby mandis before selling\n- Consider selling during peak demand seasons\n- Store produce if current prices are below average\n- Use warehouse facilities for better prices\n\nTip: Register on e-NAM for transparent pricing."
    elif any(w in msg for w in ["pest", "insect", "bug", "attack", "spray"]):
        response = "Common pest management:\n1. **Aphids** - Neem oil spray (5ml/L)\n2. **Stem borer** - Release Trichogramma egg cards\n3. **Whitefly** - Yellow sticky traps + neem oil\n4. **Fruit borer** - Install pheromone traps\n\nIntegrated approach:\n- Use biological control first\n- Apply chemical pesticides only when needed\n- Follow safety precautions during spraying\n- Rotate pesticides to prevent resistance"
    elif any(w in msg for w in ["fertilizer", "npk", "urea", "compost", "manure"]):
        response = "Fertilizer recommendations by crop:\n\n🌾 **Rice**: N:P:K = 120:60:60 kg/ha\n🌾 **Wheat**: N:P:K = 120:60:40 kg/ha\n🌱 **Cotton**: N:P:K = 120:60:60 kg/ha\n\nTips:\n- Apply basal dose during sowing\n- Top dress nitrogen in 2-3 split doses\n- Use soil testing for precise recommendations\n- Add organic compost for soil health\n- Use drip fertigation for better efficiency"
    elif any(w in msg for w in ["irrigation", "water", "drip", "sprinkler"]):
        response = "Irrigation best practices:\n\n💧 **Drip Irrigation**: 40-60% water savings\n💧 **Sprinkler**: Good for uneven terrain\n💧 **Flood**: Traditional but less efficient\n\nGeneral guidelines:\n- Irrigate early morning or evening\n- Check soil moisture before irrigating\n- Rice: keep 5cm standing water\n- Cotton: critical irrigation at flowering\n- Use mulching to reduce water evaporation\n\nTip: Install moisture sensors for optimal scheduling."
    elif any(w in msg for w in ["scheme", "government", "subsidy", "pm-kisan", "loan"]):
        response = "Popular Government Schemes for Farmers:\n\n1. **PM-KISAN** - Rs 6,000/year income support\n2. **PMFBY** - Crop insurance at low premium\n3. **KCC** - Kisan Credit Card at 4% interest\n4. **PMKSY** - Irrigation subsidy (55-75%)\n5. **SMAM** - 40-50% subsidy on farm equipment\n\nHow to apply:\n- Visit your nearest CSC (Common Service Center)\n- Apply online at pmkisan.gov.in\n- Keep Aadhaar card and land records ready\n\nTip: Check the Government Schemes section in the app."
    elif any(w in msg for w in ["crop", "which crop", "sow", "plant", "grow"]):
        response = "Crop planning advice:\n\n**Kharif Season (June-October)**:\n- Rice, Cotton, Maize, Groundnut, Soybean\n\n**Rabi Season (October-March)**:\n- Wheat, Mustard, Gram, Vegetables\n\n**Zaid Season (March-June)**:\n- Watermelon, Cucumber, Fodder\n\nChoose based on:\n- Your soil type and water availability\n- Market demand and price trends\n- Crop rotation for soil health\n- Your equipment and labor availability\n\nTip: Use the Crop Management section to track your crop cycles."
    elif any(w in msg for w in ["hello", "hi", "hey", "namaste"]):
        response = "Namaste! 🙏 Welcome to Farm Assist AI.\n\nI can help you with:\n🌾 Crop advice and management\n💧 Irrigation and water management\n🐛 Pest and disease control\n💰 Market prices and selling\n📋 Government schemes and subsidies\n🧪 Fertilizer recommendations\n🌤️ Weather-based farming advice\n\nWhat would you like to know about today?"
    else:
        response = f"Thank you for your question. Based on my agricultural knowledge:\n\nFor the query about '{message[:50]}...', here are my recommendations:\n\n1. Visit your nearest agricultural extension office for localized advice\n2. Check the soil health card for your land\n3. Consult with experienced farmers in your area\n4. Use the various tools in Farm Assist for calculations\n\nIs there something specific about this topic you'd like to know more about?"

    return {"response": response, "model": "local", "conversation_id": conversation_id}


async def get_recommendations(farm_data: dict) -> list:
    recommendations = []
    area = farm_data.get("total_area", 0)
    crop = farm_data.get("primary_crop", "")
    soil = farm_data.get("soil_type", "")

    if area > 0:
        recommendations.append({
            "type": "irrigation",
            "title": "Consider Drip Irrigation",
            "description": f"For your {area} acre farm, drip irrigation can save 40-60% water. Government subsidy available under PMKSY.",
            "priority": "medium",
        })

    if soil and "black" in soil.lower():
        recommendations.append({
            "type": "crop",
            "title": "Suitable Crops for Black Soil",
            "description": "Black soil is ideal for Cotton, Soybean, and Wheat. Consider crop rotation for best yields.",
            "priority": "high",
        })

    recommendations.append({
        "type": "finance",
        "title": "Apply for Kisan Credit Card",
        "description": "KCC provides agricultural credit at 4% interest with subvention. Apply at your nearest bank.",
        "priority": "medium",
    })

    recommendations.append({
        "type": "insurance",
        "title": "Get Crop Insurance",
        "description": "Enroll in PMFBY to protect against crop loss due to natural calamities. Premium is very low (1.5-5%).",
        "priority": "high",
    })

    return recommendations
