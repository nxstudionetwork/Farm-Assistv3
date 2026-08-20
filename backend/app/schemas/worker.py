from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


class WorkerCreate(BaseModel):
    full_name: str
    phone_number: Optional[str] = None
    village: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    skills: Optional[List[str]] = None
    experience_years: Optional[float] = None
    hourly_rate: Optional[float] = None
    daily_rate: Optional[float] = None
    bio: Optional[str] = None


class WorkerResponse(BaseModel):
    id: str
    worker_id: Optional[str] = None
    full_name: str
    phone_number: Optional[str] = None
    profile_image: Optional[str] = None
    village: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    skills: Optional[Any] = None
    experience_years: Optional[float] = None
    hourly_rate: Optional[float] = None
    daily_rate: Optional[float] = None
    rating: Optional[float] = None
    is_available: Optional[bool] = None
    bio: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkerBookingCreate(BaseModel):
    worker_id: str
    farm_id: Optional[str] = None
    work_type: Optional[str] = None
    booking_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_days: Optional[int] = None
    hours_per_day: Optional[float] = None
    notes: Optional[str] = None


class WorkerBookingResponse(BaseModel):
    id: str
    booking_id: Optional[str] = None
    farmer_id: str
    worker_id: str
    farm_id: Optional[str] = None
    work_type: Optional[str] = None
    booking_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_days: Optional[int] = None
    hours_per_day: Optional[float] = None
    total_cost: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EquipmentCreate(BaseModel):
    name: str
    type: str
    brand: Optional[str] = None
    model: Optional[str] = None
    description: Optional[str] = None
    daily_rate: Optional[float] = None
    hourly_rate: Optional[float] = None
    location: Optional[str] = None


class EquipmentResponse(BaseModel):
    id: str
    equipment_id: Optional[str] = None
    name: str
    type: str
    brand: Optional[str] = None
    model: Optional[str] = None
    description: Optional[str] = None
    daily_rate: Optional[float] = None
    hourly_rate: Optional[float] = None
    owner_id: Optional[str] = None
    is_available: Optional[bool] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EquipmentBookingCreate(BaseModel):
    equipment_id: str
    booking_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_days: Optional[int] = None


class EquipmentBookingResponse(BaseModel):
    id: str
    booking_id: Optional[str] = None
    equipment_id: str
    farmer_id: str
    booking_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_days: Optional[int] = None
    total_cost: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
