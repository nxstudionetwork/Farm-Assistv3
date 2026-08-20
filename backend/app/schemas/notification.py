from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class NotificationCreate(BaseModel):
    user_id: str
    title: str
    message: str
    notification_type: str
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None
    icon: Optional[str] = None
    action_url: Optional[str] = None


class NotificationResponse(BaseModel):
    id: str
    notification_id: Optional[str] = None
    user_id: str
    title: str
    message: str
    notification_type: str
    reference_id: Optional[str] = None
    reference_type: Optional[str] = None
    is_read: Optional[bool] = None
    icon: Optional[str] = None
    action_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
