from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.integrations.vision_service import TranslationService, SpeechService
from app.models.user import User
from app.utils.auth import get_current_user, get_optional_user

router = APIRouter(prefix="/api/v1", tags=["Translation & Speech"])


class TranslateRequest(BaseModel):
    text: str
    target_language: str
    source_language: str = "en"


class TTSRequest(BaseModel):
    text: str
    language: str = "en"


class STTRequest(BaseModel):
    audio_data: str
    language: str = "en"


@router.get("/translations/languages", response_model=dict)
def list_languages():
    return {"status": "success", "data": TranslationService.LANGUAGES}


@router.post("/translations/translate", response_model=dict)
async def translate(payload: TranslateRequest):
    result = await TranslationService.translate(payload.text, payload.target_language, payload.source_language)
    return {"status": "success", "data": result}


@router.post("/speech/text-to-speech", response_model=dict)
async def text_to_speech(payload: TTSRequest):
    result = await SpeechService.text_to_speech(payload.text, payload.language)
    return {"status": "success", "data": result}


@router.post("/speech/speech-to-text", response_model=dict)
async def speech_to_text(payload: STTRequest):
    result = await SpeechService.speech_to_text(payload.audio_data, payload.language)
    return {"status": "success", "data": result}
