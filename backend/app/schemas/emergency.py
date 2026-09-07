from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class EmergencyReportCreate(BaseModel):
    emergency_type: str = Field(..., max_length=100)
    urgency: str = Field(..., max_length=20)
    location: str = Field(..., max_length=300)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contact_phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    reference_name: str = Field(..., max_length=200)
    message: Optional[str] = Field(None, max_length=5000)


class EmergencyReportResponse(BaseModel):
    id: str
    reference_id: Optional[str]
    farmer_id: str
    emergency_type: str
    urgency: str
    location: str
    latitude: Optional[float]
    longitude: Optional[float]
    contact_phone: str
    reference_name: str
    message: Optional[str]
    status: str
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True


class EmergencyReportList(BaseModel):
    reports: List[EmergencyReportResponse]
    total: int

    class Config:
        orm_mode = True
