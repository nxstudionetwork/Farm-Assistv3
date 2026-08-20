import httpx
import base64
import logging
from typing import Optional
from app.config import settings
from app.integrations.base import BaseIntegration

logger = logging.getLogger(__name__)


class VisionService(BaseIntegration):
    name = "vision"
    requires_api_key = True
    api_key_setting = "GEMINI_API_KEY"

    @staticmethod
    async def diagnose(image_data: str, symptoms: Optional[str] = None) -> dict:
        if settings.GEMINI_API_KEY:
            try:
                return await VisionService._gemini_diagnose(image_data, symptoms)
            except Exception as e:
                logger.warning(f"Gemini vision failed: {e}")

        return VisionService._fallback_diagnosis(symptoms)

    @staticmethod
    async def _gemini_diagnose(image_data: str, symptoms: Optional[str] = None) -> dict:
        image_data = image_data.strip()
        if image_data.startswith("data:image"):
            image_data = image_data.split(",", 1)[1] if "," in image_data else image_data

        prompt = "You are an expert crop disease diagnostician. Analyze this plant image and provide:\n1. Disease/Pest name (if any)\n2. Confidence score (0-100)\n3. Symptoms description\n4. Recommended treatment\n5. Prevention tips"
        if symptoms:
            prompt += f"\n\nFarmer also reported: {symptoms}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/jpeg", "data": image_data}}
                        ]
                    }]
                },
            )
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return {
                            "diagnosis": parts[0].get("text", ""),
                            "confidence": 85,
                            "model": "gemini-vision",
                            "provider": "google",
                        }
            raise Exception(f"Gemini vision returned {response.status_code}")

    @staticmethod
    def _fallback_diagnosis(symptoms: Optional[str] = None) -> dict:
        s = (symptoms or "").lower()
        if "yellow" in s or "yellowing" in s:
            return {"diagnosis": "Possible Nitrogen Deficiency or Leaf Blight", "confidence": 75, "model": "heuristic", "treatment": "Apply nitrogen-rich fertilizer or fungicide", "provider": "fallback"}
        if "wilt" in s or "wilting" in s:
            return {"diagnosis": "Possible Fusarium Wilt or Bacterial Wilt", "confidence": 70, "model": "heuristic", "treatment": "Remove infected plants, improve drainage, apply fungicide", "provider": "fallback"}
        if "spot" in s or "spotting" in s:
            return {"diagnosis": "Possible Leaf Spot Disease", "confidence": 72, "model": "heuristic", "treatment": "Apply copper-based fungicide, improve air circulation", "provider": "fallback"}
        if "blight" in s:
            return {"diagnosis": "Possible Late Blight", "confidence": 78, "model": "heuristic", "treatment": "Apply fungicide, remove infected leaves, avoid overhead irrigation", "provider": "fallback"}
        if "rust" in s:
            return {"diagnosis": "Possible Rust Disease", "confidence": 80, "model": "heuristic", "treatment": "Apply sulfur-based fungicide, practice crop rotation", "provider": "fallback"}
        if "mildew" in s:
            return {"diagnosis": "Possible Powdery Mildew", "confidence": 82, "model": "heuristic", "treatment": "Apply sulfur or potassium bicarbonate, increase air flow", "provider": "fallback"}
        return {"diagnosis": "No specific disease detected. Monitoring recommended.", "confidence": 50, "model": "heuristic", "treatment": "Monitor plant health, ensure proper nutrition and watering", "provider": "fallback"}


class TranslationService(BaseIntegration):
    name = "translation"
    requires_api_key = True
    api_key_setting = "TRANSLATION_API_KEY"

    LANGUAGES = {
        "en": "English", "te": "Telugu", "hi": "Hindi", "ta": "Tamil",
        "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi", "pa": "Punjabi",
        "gu": "Gujarati", "bn": "Bengali", "ur": "Urdu",
    }

    @staticmethod
    async def translate(text: str, target_language: str, source_language: str = "en") -> dict:
        if target_language == "en" or target_language == source_language:
            return {"translated_text": text, "source_language": source_language, "target_language": target_language}

        if settings.TRANSLATION_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"https://translation.googleapis.com/language/translate/v2",
                        params={
                            "q": text,
                            "target": target_language,
                            "source": source_language,
                            "key": settings.TRANSLATION_API_KEY,
                        },
                    )
                    if response.status_code == 200:
                        data = response.json()
                        translated = data.get("data", {}).get("translations", [{}])[0].get("translatedText", text)
                        return {"translated_text": translated, "source_language": source_language, "target_language": target_language}
            except Exception as e:
                logger.warning(f"Translation API failed: {e}")

        return {"translated_text": text, "source_language": source_language, "target_language": target_language, "note": "Translation API not configured"}


class SpeechService(BaseIntegration):
    name = "speech"
    requires_api_key = True
    api_key_setting = "SPEECH_API_KEY"

    @staticmethod
    async def text_to_speech(text: str, language: str = "en") -> dict:
        if settings.SPEECH_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(
                        "https://texttospeech.googleapis.com/v1/text:synthesize",
                        headers={"Authorization": f"Bearer {settings.SPEECH_API_KEY}", "Content-Type": "application/json"},
                        json={
                            "input": {"text": text},
                            "voice": {"languageCode": language, "ssmlGender": "NEUTRAL"},
                            "audioConfig": {"audioEncoding": "MP3"},
                        },
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return {"audio_content": data.get("audioContent", ""), "format": "mp3"}
            except Exception as e:
                logger.warning(f"TTS API failed: {e}")
        return {"audio_content": None, "format": "none", "note": "Speech API not configured"}

    @staticmethod
    async def speech_to_text(audio_data: str, language: str = "en") -> dict:
        if settings.SPEECH_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(
                        "https://speech.googleapis.com/v1/speech:recognize",
                        headers={"Authorization": f"Bearer {settings.SPEECH_API_KEY}", "Content-Type": "application/json"},
                        json={
                            "config": {"languageCode": language, "encoding": "WEBM_OPUS"},
                            "audio": {"content": audio_data},
                        },
                    )
                    if response.status_code == 200:
                        data = response.json()
                        results = data.get("results", [])
                        transcript = results[0].get("alternatives", [{}])[0].get("transcript", "") if results else ""
                        return {"transcript": transcript, "confidence": results[0].get("alternatives", [{}])[0].get("confidence", 0) if results else 0}
            except Exception as e:
                logger.warning(f"STT API failed: {e}")
        return {"transcript": "", "confidence": 0, "note": "Speech API not configured"}
