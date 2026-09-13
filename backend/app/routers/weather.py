from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import httpx

from app.database.connection import get_db
from app.utils.auth import get_current_user
from app.models.user import User, UserAddress
from app.models.farm import Farm
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


def _wind_direction(degrees):
    if degrees is None:
        return None
    directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return directions[int((float(degrees) + 22.5) // 45) % 8]


def _resolve_location(latitude, longitude, current_user, db):
    if latitude is not None and longitude is not None:
        return latitude, longitude, "Selected location"
    farm = (db.query(Farm)
            .filter(Farm.user_id == current_user.id, Farm.is_active == True,
                    Farm.latitude.isnot(None), Farm.longitude.isnot(None))
            .order_by(Farm.created_at.asc()).first())
    if farm:
        return farm.latitude, farm.longitude, farm.district or farm.farm_name or "Farm location"
    address = (db.query(UserAddress)
               .filter(UserAddress.user_id == current_user.id, UserAddress.is_primary == True,
                       UserAddress.latitude.isnot(None), UserAddress.longitude.isnot(None))
               .first())
    if address:
        return address.latitude, address.longitude, address.district or address.village or "Saved location"
    raise HTTPException(status_code=422, detail="Set a farm or saved address location to view weather")


def _weather_insights(current, daily):
    alerts, advice = [], []
    rain = float(current.get("rain") or 0)
    wind = float(current.get("wind_speed_10m") or 0)
    temperature = float(current.get("temperature_2m") or 0)
    humidity = float(current.get("relative_humidity_2m") or 0)
    codes = daily.get("weather_code", [])
    precipitation = daily.get("precipitation_sum", [])
    max_wind = max([float(value or 0) for value in daily.get("wind_speed_10m_max", [])] or [wind])
    max_temp = max([float(value or 0) for value in daily.get("temperature_2m_max", [])] or [temperature])
    min_temp = min([float(value or 0) for value in daily.get("temperature_2m_min", [])] or [temperature])
    heavy_rain = max([float(value or 0) for value in precipitation] or [rain]) >= 20
    storm = any(int(code or 0) >= 95 for code in codes)
    if heavy_rain or rain >= 10:
        alerts.append({"severity": "warning", "title": "Heavy rain risk", "detail": "Rainfall may affect field access and harvest plans in the forecast period.", "period": "Next 7 days", "action": "Clear drainage and delay spraying or harvest during rain."})
        advice.append({"type": "warning", "category": "Irrigation", "title": "Reduce irrigation", "detail": "Check soil moisture before watering and use the forecast rainfall to avoid over-irrigation."})
        advice.append({"type": "info", "category": "Field work", "title": "Plan around rain", "detail": "Keep drainage channels clear and avoid working wet soil to prevent compaction."})
    if max_wind >= 40 or wind >= 30:
        alerts.append({"severity": "danger", "title": "Strong wind risk", "detail": "Strong winds may damage supports, covers, or young plants.", "period": "Forecast period", "action": "Secure loose materials and postpone spraying."})
        advice.append({"type": "warning", "category": "Crop protection", "title": "Secure vulnerable crops", "detail": "Support young plants and secure shade nets, covers, and equipment before strong winds."})
    if max_temp >= 38 or temperature >= 38:
        alerts.append({"severity": "danger", "title": "High temperature", "detail": "Heat stress risk is elevated for crops and livestock.", "period": "Forecast period", "action": "Provide water and shade and avoid midday field work."})
        advice.append({"type": "warning", "category": "Livestock", "title": "Protect livestock from heat", "detail": "Keep clean drinking water and shade available and check animals more often."})
    if min_temp <= 5:
        alerts.append({"severity": "warning", "title": "Low temperature risk", "detail": "Sensitive crops may be affected by low overnight temperatures.", "period": "Forecast period", "action": "Protect seedlings and monitor frost-prone areas."})
    if storm:
        alerts.append({"severity": "danger", "title": "Thunderstorm risk", "detail": "Thunderstorms are present in the forecast.", "period": "Forecast period", "action": "Avoid open fields during storms and disconnect exposed equipment."})
    if not advice and humidity >= 80:
        advice.append({"type": "info", "category": "Crop protection", "title": "Monitor for fungal disease", "detail": "High humidity can increase disease pressure; inspect leaves and improve airflow."})
    if not advice:
        advice.append({"type": "success", "category": "General", "title": "Favourable field conditions", "detail": "Conditions are suitable for routine field work. Check soil moisture before irrigation."})
    return alerts, advice


@router.get("/weather/current")
def get_current_weather(
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    latitude, longitude, location_label = _resolve_location(latitude, longitude, current_user, db)
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

    if cache and cache.fetched_at and cache.data.get("alerts") is not None:
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
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,rain,wind_speed_10m,wind_direction_10m,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code,wind_speed_10m_max,sunrise,sunset",
                    "forecast_days": 7,
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
        "feels_like": current.get("apparent_temperature"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_direction": _wind_direction(current.get("wind_direction_10m")),
        "weather_code": weather_code,
        "weather_condition": _weather_condition(weather_code),
        "description": _weather_condition(weather_code),
        "time": current.get("time"),
        "location_label": location_label,
        "sunrise": (data.get("daily", {}).get("sunrise") or [None])[0],
        "sunset": (data.get("daily", {}).get("sunset") or [None])[0],
    }
    result["alerts"], result["advice"] = _weather_insights(current, data.get("daily", {}))

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
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    latitude, longitude, _ = _resolve_location(latitude, longitude, current_user, db)
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

    if cache and cache.fetched_at and len(cache.data.get("forecast", [])) >= 14:
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
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code,wind_speed_10m_max,sunrise,sunset",
                    "current": "temperature_2m",
                    "forecast_days": 14,
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
            "precipitation_probability": daily.get("precipitation_probability_max", [])[i] if i < len(daily.get("precipitation_probability_max", [])) else None,
            "wind_speed": daily.get("wind_speed_10m_max", [])[i] if i < len(daily.get("wind_speed_10m_max", [])) else None,
            "wind_direction": None,
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
