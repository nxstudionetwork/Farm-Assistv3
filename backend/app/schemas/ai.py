from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AIChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    model: Optional[str] = None


class AIChatResponse(BaseModel):
    response: str
    conversation_id: Optional[str] = None


class AIRecommendationResponse(BaseModel):
    id: str
    user_id: str
    farm_id: Optional[str] = None
    recommendation_type: str
    title: str
    description: str
    priority: Optional[str] = None
    is_read: Optional[bool] = None
    is_applied: Optional[bool] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
