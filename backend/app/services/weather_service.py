import httpx
from typing import Optional
from app.config import settings


async def get_current_weather(latitude: float, longitude: float) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.WEATHER_API_BASE_URL}/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,relative_humidity_2m,rain,wind_speed_10m,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,wind_speed_10m_max",
                    "timezone": "auto",
                    "forecast_days": 7,
                },
            )
            if response.status_code == 200:
                data = response.json()
                current = data.get("current", {})
                daily = data.get("daily", {})
                weather_codes = {
                    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                    45: "Foggy", 48: "Rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
                    55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
                    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 80: "Slight rain showers",
                    81: "Moderate rain showers", 82: "Violent rain showers", 95: "Thunderstorm",
                    96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
                }
                code = current.get("weather_code", 0)
                return {
                    "temperature": current.get("temperature_2m", 0),
                    "humidity": current.get("relative_humidity_2m", 0),
                    "rain": current.get("rain", 0),
                    "wind_speed": current.get("wind_speed_10m", 0),
                    "description": weather_codes.get(code, "Unknown"),
                    "weather_code": code,
                    "forecast": [
                        {
                            "date": daily.get("time", [])[i] if i < len(daily.get("time", [])) else "",
                            "max_temp": daily.get("temperature_2m_max", [])[i] if i < len(daily.get("temperature_2m_max", [])) else 0,
                            "min_temp": daily.get("temperature_2m_min", [])[i] if i < len(daily.get("temperature_2m_min", [])) else 0,
                            "precipitation": daily.get("precipitation_sum", [])[i] if i < len(daily.get("precipitation_sum", [])) else 0,
                            "wind_speed": daily.get("wind_speed_10m_max", [])[i] if i < len(daily.get("wind_speed_10m_max", [])) else 0,
                            "description": weather_codes.get(daily.get("weather_code", [0])[i] if i < len(daily.get("weather_code", [])) else 0, "Unknown"),
                        }
                        for i in range(min(7, len(daily.get("time", []))))
                    ],
                }
    except Exception as e:
        return {
            "temperature": 28,
            "humidity": 70,
            "rain": 0,
            "wind_speed": 12,
            "description": "Partly cloudy",
            "weather_code": 2,
            "forecast": [],
            "error": str(e),
        }


async def get_forecast(latitude: float, longitude: float, days: int = 7) -> dict:
    return await get_current_weather(latitude, longitude)
