from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CropCreate(BaseModel):
    name: str
    variety: Optional[str] = None
    category: Optional[str] = None
    season: Optional[str] = None
    growth_duration_days: Optional[float] = None


class CropResponse(BaseModel):
    id: str
    crop_id: Optional[str] = None
    name: str
    variety: Optional[str] = None
    category: Optional[str] = None
    season: Optional[str] = None
    growth_duration_days: Optional[float] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CropCycleCreate(BaseModel):
    farm_id: str
    plot_id: Optional[str] = None
    crop_id: str
    sowing_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    current_stage: Optional[str] = None
    seed_quantity: Optional[float] = None
    seed_unit: Optional[str] = None
    fertilizer_usage: Optional[str] = None
    pesticide_usage: Optional[str] = None
    irrigation_schedule: Optional[str] = None
    notes: Optional[str] = None


class CropCycleUpdate(BaseModel):
    plot_id: Optional[str] = None
    crop_id: Optional[str] = None
    sowing_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    actual_harvest_date: Optional[str] = None
    current_stage: Optional[str] = None
    seed_quantity: Optional[float] = None
    seed_unit: Optional[str] = None
    fertilizer_usage: Optional[str] = None
    pesticide_usage: Optional[str] = None
    irrigation_schedule: Optional[str] = None
    yield_quantity: Optional[float] = None
    yield_unit: Optional[str] = None
    revenue: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class CropCycleResponse(BaseModel):
    id: str
    cycle_id: Optional[str] = None
    farm_id: str
    plot_id: Optional[str] = None
    crop_id: str
    sowing_date: Optional[str] = None
    expected_harvest_date: Optional[str] = None
    actual_harvest_date: Optional[str] = None
    current_stage: Optional[str] = None
    seed_quantity: Optional[float] = None
    seed_unit: Optional[str] = None
    fertilizer_usage: Optional[str] = None
    pesticide_usage: Optional[str] = None
    irrigation_schedule: Optional[str] = None
    yield_quantity: Optional[float] = None
    yield_unit: Optional[str] = None
    revenue: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CropTaskCreate(BaseModel):
    crop_cycle_id: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: Optional[str] = None


class CropTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


class CropTaskResponse(BaseModel):
    id: str
    task_id: Optional[str] = None
    crop_cycle_id: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FarmJournalCreate(BaseModel):
    farm_id: Optional[str] = None
    plot_id: Optional[str] = None
    activity: str
    notes: Optional[str] = None


class FarmJournalResponse(BaseModel):
    id: str
    user_id: str
    farm_id: Optional[str] = None
    plot_id: Optional[str] = None
    activity: str
    notes: Optional[str] = None
    entry_date: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
