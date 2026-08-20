from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import httpx

from app.database.connection import get_db
from app.utils.auth import get_current_user
from app.models.user import User
from app.models.ai import WeatherCache

router = APIRouter(prefix="/api/v1", tags=["Weather"])

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

_WMO_CONDITIONS = {
    0: "Clear",
    1: "Mostly Clear",
    2: "Partly Cloudy",
    3: "Clouds",
    45: "Fog",
    48: "Fog",
    51: "Drizzle",
    53: "Drizzle",
    55: "Drizzle",
    56: "Drizzle",
    57: "Drizzle",
    61: "Rain",
    63: "Rain",
    65: "Rain",
    66: "Rain",
    67: "Rain",
    71: "Snow",
    73: "Snow",
    75: "Snow",
    77: "Snow",
    80: "Rain",
    81: "Rain",
    82: "Rain",
    85: "Snow",
    86: "Snow",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}


def _weather_condition(code) -> str:
    return _WMO_CONDITIONS.get(int(code), "Partly Cloudy") if code is not None else "Partly Cloudy"


@router.get("/weather/current")
def get_current_weather(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache = (
        db.query(WeatherCache)
        .filter(
            WeatherCache.latitude == round(latitude, 2),
            WeatherCache.longitude == round(longitude, 2),
            WeatherCache.weather_type == "current",
        )
        .order_by(WeatherCache.fetched_at.desc())
        .first()
    )

    if cache and cache.fetched_at:
        age_minutes = (datetime.utcnow() - cache.fetched_at).total_seconds() / 60
        if age_minutes < 30:
            return {"status": "success", "data": cache.data, "cached": True, "fetched_at": str(cache.fetched_at)}

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                OPEN_METEO_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,relative_humidity_2m,rain,wind_speed_10m,weather_code",
                    "timezone": "auto",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Failed to fetch weather data from Open-Meteo")
    except Exception:
        raise HTTPException(status_code=500, detail="Weather service unavailable")

    current = data.get("current", {})
    weather_code = current.get("weather_code")
    result = {
        "latitude": latitude,
        "longitude": longitude,
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "rain": current.get("rain"),
        "wind_speed": current.get("wind_speed_10m"),
        "weather_code": weather_code,
        "weather_condition": _weather_condition(weather_code),
        "description": _weather_condition(weather_code),
        "time": current.get("time"),
    }

    cache_entry = WeatherCache(
        latitude=round(latitude, 2),
        longitude=round(longitude, 2),
        data=result,
        weather_type="current",
    )
    db.add(cache_entry)
    db.commit()

    return {"status": "success", "data": result, "cached": False}


@router.get("/weather/forecast")
def get_forecast(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache = (
        db.query(WeatherCache)
        .filter(
            WeatherCache.latitude == round(latitude, 2),
            WeatherCache.longitude == round(longitude, 2),
            WeatherCache.weather_type == "forecast",
        )
        .order_by(WeatherCache.fetched_at.desc())
        .first()
    )

    if cache and cache.fetched_at:
        age_minutes = (datetime.utcnow() - cache.fetched_at).total_seconds() / 60
        if age_minutes < 60:
            return {"status": "success", "data": cache.data, "cached": True, "fetched_at": str(cache.fetched_at)}

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                OPEN_METEO_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                    "current": "temperature_2m",
                    "timezone": "auto",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Failed to fetch forecast data from Open-Meteo")
    except Exception:
        raise HTTPException(status_code=500, detail="Weather service unavailable")

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    codes = daily.get("weather_code", [])
    forecast = []
    for i, date in enumerate(dates):
        wc = codes[i] if i < len(codes) else None
        forecast.append({
            "date": date,
            "temperature_max": daily.get("temperature_2m_max", [])[i] if i < len(daily.get("temperature_2m_max", [])) else None,
            "temperature_min": daily.get("temperature_2m_min", [])[i] if i < len(daily.get("temperature_2m_min", [])) else None,
            "precipitation": daily.get("precipitation_sum", [])[i] if i < len(daily.get("precipitation_sum", [])) else None,
            "weather_code": wc,
            "weather_condition": _weather_condition(wc),
            "description": _weather_condition(wc),
        })

    result = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": data.get("timezone"),
        "forecast": forecast,
    }

    cache_entry = WeatherCache(
        latitude=round(latitude, 2),
        longitude=round(longitude, 2),
        data=result,
        weather_type="forecast",
    )
    db.add(cache_entry)
    db.commit()

    return {"status": "success", "data": result, "cached": False}
