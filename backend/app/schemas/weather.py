from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class WeatherResponse(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    wind_speed: Optional[float] = None
    weather_condition: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    fetched_at: Optional[datetime] = None


class WeatherForecastResponse(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    forecast: Optional[Any] = None
    fetched_at: Optional[datetime] = None
