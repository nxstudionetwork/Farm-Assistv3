from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


class CommunityPostCreate(BaseModel):
    content: str
    image_url: Optional[str] = None
    post_type: Optional[str] = None


class CommunityCommentCreate(BaseModel):
    content: str


class CommunityCommentResponse(BaseModel):
    id: str
    post_id: str
    user_id: str
    content: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CommunityPostUser(BaseModel):
    id: str
    full_name: str
    phone_number: Optional[str] = None
    profile_image: Optional[str] = None

    class Config:
        from_attributes = True


class CommunityPostResponse(BaseModel):
    id: str
    post_id: Optional[str] = None
    user_id: str
    content: str
    image_url: Optional[str] = None
    post_type: Optional[str] = None
    likes_count: Optional[int] = None
    comments_count: Optional[int] = None
    shares_count: Optional[int] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    user: Optional[CommunityPostUser] = None
    comments: Optional[List[CommunityCommentResponse]] = None

    class Config:
        from_attributes = True


class ExpertResponse(BaseModel):
    id: str
    expert_id: Optional[str] = None
    user_id: Optional[str] = None
    full_name: str
    speciality: str
    qualification: Optional[str] = None
    experience_years: Optional[float] = None
    profile_image: Optional[str] = None
    bio: Optional[str] = None
    consultation_fee: Optional[float] = None
    rating: Optional[float] = None
    total_consultations: Optional[int] = None
    is_available: Optional[bool] = None
    location: Optional[str] = None
    languages: Optional[Any] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConsultationCreate(BaseModel):
    expert_id: str
    topic: Optional[str] = None
    description: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None


class ConsultationResponse(BaseModel):
    id: str
    consultation_id: Optional[str] = None
    farmer_id: str
    expert_id: str
    topic: Optional[str] = None
    description: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    rating: Optional[float] = None
    feedback: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
