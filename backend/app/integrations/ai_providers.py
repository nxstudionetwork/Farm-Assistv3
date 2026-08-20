import httpx
import json
import logging
from typing import Optional, List, Dict
from app.config import settings
from app.integrations.base import BaseIntegration

logger = logging.getLogger(__name__)


class AIProviderManager:
    PROVIDERS = []

    @classmethod
    def register(cls, provider_class):
        cls.PROVIDERS.append(provider_class)
        return provider_class

    @classmethod
    async def chat(cls, message: str, conversation_id: Optional[str] = None, model: Optional[str] = None) -> dict:
        model = (model or settings.AI_DEFAULT_MODEL or "local").lower()

        priority = ["openai", "gemini", "claude", "local"]
        if model != "local":
            priority = [model] + [p for p in priority if p != model]

        errors = []
        for provider_name in priority:
            provider = cls._get_provider(provider_name)
            if not provider:
                continue
            if provider.requires_api_key and not provider.is_available():
                errors.append(f"{provider.name}: API key not configured")
                if not settings.AI_FALLBACK_ENABLED:
                    continue
            try:
                result = await provider.chat(message, conversation_id)
                if result and result.get("response"):
                    return result
                errors.append(f"{provider.name}: empty response")
            except Exception as e:
                errors.append(f"{provider.name}: {str(e)}")
                logger.warning(f"AI provider {provider.name} failed: {e}")
                continue

        logger.error(f"All AI providers failed: {'; '.join(errors)}")
        return LocalProvider.chat(message, conversation_id)

    @classmethod
    def _get_provider(cls, name: str):
        for p in cls.PROVIDERS:
            if p.name == name:
                return p
        return None

    @classmethod
    def get_status(cls) -> List[dict]:
        return [p.get_status() for p in cls.PROVIDERS]


class OpenAIChatProvider(BaseIntegration, AIProviderManager):
    name = "openai"
    requires_api_key = True
    api_key_setting = "OPENAI_API_KEY"

    @staticmethod
    async def chat(message: str, conversation_id: Optional[str] = None) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "You are Farm Assist AI, an expert agricultural assistant helping Indian farmers. Provide practical, region-specific advice about farming, crops, weather, finance, and government schemes. Respond in simple, helpful language."},
                        {"role": "user", "content": message},
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.7,
                },
            )
            if response.status_code == 200:
                data = response.json()
                return {"response": data["choices"][0]["message"]["content"], "model": "openai", "conversation_id": conversation_id}
            raise Exception(f"OpenAI API returned {response.status_code}")


class GeminiChatProvider(BaseIntegration, AIProviderManager):
    name = "gemini"
    requires_api_key = True
    api_key_setting = "GEMINI_API_KEY"

    @staticmethod
    async def chat(message: str, conversation_id: Optional[str] = None) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": f"You are Farm Assist AI, an expert Indian agriculture assistant. Help the farmer.\n\nFarmer: {message}"}]}]},
            )
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")
                        if text:
                            return {"response": text, "model": "gemini", "conversation_id": conversation_id}
            raise Exception(f"Gemini API returned {response.status_code}")


class ClaudeChatProvider(BaseIntegration, AIProviderManager):
    name = "claude"
    requires_api_key = True
    api_key_setting = "ANTHROPIC_API_KEY"

    @staticmethod
    async def chat(message: str, conversation_id: Optional[str] = None) -> dict:
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
                    "messages": [{"role": "user", "content": f"You are Farm Assist AI, an expert Indian agriculture assistant. Help the farmer.\n\nFarmer: {message}"}],
                },
            )
            if response.status_code == 200:
                data = response.json()
                content_blocks = data.get("content", [])
                if content_blocks:
                    text = content_blocks[0].get("text", "")
                    if text:
                        return {"response": text, "model": "claude", "conversation_id": conversation_id}
            raise Exception(f"Claude API returned {response.status_code}")


class LocalProvider(BaseIntegration):
    name = "local"
    requires_api_key = False

    @staticmethod
    def chat(message: str, conversation_id: Optional[str] = None) -> dict:
        msg = message.lower()
        response = LocalProvider._get_response(msg)
        return {"response": response, "model": "local", "conversation_id": conversation_id}

    @staticmethod
    def _get_response(msg: str) -> str:
        if any(w in msg for w in ["yellow", "leaves", "yellowing"]):
            return "Yellowing leaves can indicate several issues:\n1. **Nitrogen deficiency** - Apply urea or DAP fertilizer\n2. **Overwatering** - Check drainage, reduce irrigation\n3. **Pest infestation** - Check for aphids or mites underneath leaves\n4. **Iron deficiency** - Apply iron sulphate (2g/L)\n\nRecommendation: Check soil moisture and recent fertilizer application. If leaves are yellow at bottom, it's likely nitrogen deficiency."
        if any(w in msg for w in ["rain", "rainfall", "monsoon", "rainy"]):
            return "Based on current weather patterns:\n- Keep drainage channels clear\n- Avoid fertilizer application 24 hours before rain\n- Harvest mature crops before heavy rain\n- Store harvested produce in dry locations\n- Monitor waterlogged fields closely\n\nTip: Use the Weather section in the app for 7-day forecast updates."
        if any(w in msg for w in ["price", "market", "sell", "rate", "mandi"]):
            return "Current market guidance:\n- Check the Market Prices section for real-time mandi rates\n- Compare prices across nearby mandis before selling\n- Consider selling during peak demand seasons\n- Store produce if current prices are below average\n- Use warehouse facilities for better prices\n\nTip: Register on e-NAM for transparent pricing."
        if any(w in msg for w in ["pest", "insect", "bug", "attack", "spray"]):
            return "Common pest management:\n1. **Aphids** - Neem oil spray (5ml/L)\n2. **Stem borer** - Release Trichogramma egg cards\n3. **Whitefly** - Yellow sticky traps + neem oil\n4. **Fruit borer** - Install pheromone traps\n\nIntegrated approach:\n- Use biological control first\n- Apply chemical pesticides only when needed\n- Follow safety precautions during spraying\n- Rotate pesticides to prevent resistance"
        if any(w in msg for w in ["fertilizer", "npk", "urea", "compost", "manure"]):
            return "Fertilizer recommendations by crop:\n\n🌾 **Rice**: N:P:K = 120:60:60 kg/ha\n🌾 **Wheat**: N:P:K = 120:60:40 kg/ha\n🌱 **Cotton**: N:P:K = 120:60:60 kg/ha\n\nTips:\n- Apply basal dose during sowing\n- Top dress nitrogen in 2-3 split doses\n- Use soil testing for precise recommendations\n- Add organic compost for soil health"
        if any(w in msg for w in ["irrigation", "water", "drip", "sprinkler"]):
            return "Irrigation best practices:\n\n💧 **Drip Irrigation**: 40-60% water savings\n💧 **Sprinkler**: Good for uneven terrain\n💧 **Flood**: Traditional but less efficient\n\nGeneral guidelines:\n- Irrigate early morning or evening\n- Check soil moisture before irrigating\n- Use mulching to reduce water evaporation"
        if any(w in msg for w in ["scheme", "government", "subsidy", "pm-kisan", "loan"]):
            return "Popular Government Schemes for Farmers:\n\n1. **PM-KISAN** - Rs 6,000/year income support\n2. **PMFBY** - Crop insurance at low premium\n3. **KCC** - Kisan Credit Card at 4% interest\n4. **PMKSY** - Irrigation subsidy (55-75%)\n5. **SMAM** - 40-50% subsidy on farm equipment\n\nTip: Check the Government Schemes section in the app."
        if any(w in msg for w in ["crop", "which crop", "sow", "plant", "grow"]):
            return "Crop planning advice:\n\n**Kharif Season (June-October)**: Rice, Cotton, Maize, Groundnut, Soybean\n**Rabi Season (October-March)**: Wheat, Mustard, Gram, Vegetables\n**Zaid Season (March-June)**: Watermelon, Cucumber, Fodder\n\nChoose based on your soil type, water availability, and market demand."
        if any(w in msg for w in ["hello", "hi", "hey", "namaste"]):
            return "Namaste! 🙏 Welcome to Farm Assist AI.\n\nI can help you with:\n🌾 Crop advice and management\n💧 Irrigation and water management\n🐛 Pest and disease control\n💰 Market prices and selling\n📋 Government schemes and subsidies\n🧪 Fertilizer recommendations\n🌤️ Weather-based farming advice\n\nWhat would you like to know about today?"
        return f"For your query about '{message[:60]}...', here are my recommendations:\n\n1. Visit your nearest agricultural extension office for localized advice\n2. Check the soil health card for your land\n3. Consult with experienced farmers in your area\n4. Use the various tools in Farm Assist for calculations\n\nIs there something specific you'd like to know more about?"


AIProviderManager.register(OpenAIChatProvider)
AIProviderManager.register(GeminiChatProvider)
AIProviderManager.register(ClaudeChatProvider)
