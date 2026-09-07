from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class WatchlistCreate(BaseModel):
    commodity: str = Field(..., min_length=1, max_length=120)
    market: Optional[str] = Field(None, max_length=200)
    district: Optional[str] = Field(None, max_length=120)
    state: Optional[str] = Field(None, max_length=120)

    @field_validator("commodity", "market", "district", "state")
    @classmethod
    def strip_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        text = v.strip()
        return text or None


class WatchlistResponse(BaseModel):
    id: str
    watch_id: Optional[str] = None
    commodity: str
    market: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertCreate(BaseModel):
    commodity: str = Field(..., min_length=1, max_length=120)
    market: Optional[str] = Field(None, max_length=200)
    target_price: float = Field(..., gt=0)
    condition: str = Field("above", pattern="^(above|below)$")

    @field_validator("commodity", "market")
    @classmethod
    def strip_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        text = v.strip()
        return text or None


class AlertResponse(BaseModel):
    id: str
    alert_id: Optional[str] = None
    commodity: str
    market: Optional[str] = None
    target_price: float
    condition: str
    status: str
    last_checked_at: Optional[datetime] = None
    last_triggered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
