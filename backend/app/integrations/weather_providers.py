import httpx
from typing import Optional
from app.config import settings
from app.integrations.base import BaseIntegration


WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Slight rain showers", 81: "Moderate rain showers",
    82: "Violent rain showers", 85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


class OpenMeteoProvider(BaseIntegration):
    name = "open-meteo"
    requires_api_key = False
    base_url = "https://api.open-meteo.com/v1"

    @staticmethod
    async def get_current(latitude: float, longitude: float) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{OpenMeteoProvider.base_url}/forecast",
                    params={
                        "latitude": latitude,
                        "longitude": longitude,
                        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,rain,snowfall,weather_code,wind_speed_10m,wind_direction_10m,uv_index,pressure_msl,surface_pressure",
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code,wind_speed_10m_max,uv_index_max,sunrise,sunset",
                        "timezone": "auto",
                        "forecast_days": 14,
                    },
                )
                if response.status_code == 200:
                    return OpenMeteoProvider._parse_weather(response.json())
        except Exception:
            pass
        return OpenMeteoProvider._fallback_weather()

    @staticmethod
    def _parse_weather(data: dict) -> dict:
        current = data.get("current", {})
        daily = data.get("daily", {})
        code = current.get("weather_code", 0)
        return {
            "temperature": current.get("temperature_2m", 0),
            "feels_like": current.get("apparent_temperature", 0),
            "humidity": current.get("relative_humidity_2m", 0),
            "rain": current.get("rain", 0),
            "snowfall": current.get("snowfall", 0),
            "wind_speed": current.get("wind_speed_10m", 0),
            "wind_direction": current.get("wind_direction_10m", 0),
            "uv_index": current.get("uv_index", 0),
            "pressure": current.get("pressure_msl", 0) or current.get("surface_pressure", 0),
            "description": WEATHER_CODES.get(code, "Unknown"),
            "weather_code": code,
            "forecast": [
                {
                    "date": daily.get("time", [])[i] if i < len(daily.get("time", [])) else "",
                    "max_temp": daily.get("temperature_2m_max", [])[i] if i < len(daily.get("temperature_2m_max", [])) else 0,
                    "min_temp": daily.get("temperature_2m_min", [])[i] if i < len(daily.get("temperature_2m_min", [])) else 0,
                    "precipitation": daily.get("precipitation_sum", [])[i] if i < len(daily.get("precipitation_sum", [])) else 0,
                    "precipitation_probability": daily.get("precipitation_probability_max", [])[i] if i < len(daily.get("precipitation_probability_max", [])) else 0,
                    "wind_speed": daily.get("wind_speed_10m_max", [])[i] if i < len(daily.get("wind_speed_10m_max", [])) else 0,
                    "uv_index": daily.get("uv_index_max", [])[i] if i < len(daily.get("uv_index_max", [])) else 0,
                    "sunrise": daily.get("sunrise", [])[i] if i < len(daily.get("sunrise", [])) else "",
                    "sunset": daily.get("sunset", [])[i] if i < len(daily.get("sunset", [])) else "",
                    "description": WEATHER_CODES.get(
                        daily.get("weather_code", [0])[i] if i < len(daily.get("weather_code", [])) else 0, "Unknown"
                    ),
                }
                for i in range(min(14, len(daily.get("time", []))))
            ],
            "provider": "open-meteo",
        }

    @staticmethod
    def _fallback_weather() -> dict:
        return {
            "temperature": 28,
            "feels_like": 30,
            "humidity": 70,
            "rain": 0,
            "wind_speed": 12,
            "description": "Partly cloudy",
            "weather_code": 2,
            "forecast": [],
            "provider": "fallback",
        }


class OpenWeatherMapProvider(BaseIntegration):
    name = "openweathermap"
    requires_api_key = True
    api_key_setting = "WEATHER_API_KEY"
    base_url = "https://api.openweathermap.org/data/2.5"

    @staticmethod
    async def get_current(latitude: float, longitude: float) -> dict:
        if not settings.WEATHER_API_KEY:
            return OpenMeteoProvider._fallback_weather()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{OpenWeatherMapProvider.base_url}/onecall",
                    params={
                        "lat": latitude,
                        "lon": longitude,
                        "appid": settings.WEATHER_API_KEY,
                        "units": "metric",
                        "exclude": "minutely,alerts",
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    current = data.get("current", {})
                    weather = (current.get("weather") or [{}])[0]
                    return {
                        "temperature": current.get("temp", 0),
                        "feels_like": current.get("feels_like", 0),
                        "humidity": current.get("humidity", 0),
                        "rain": (current.get("rain", {}) or {}).get("1h", 0),
                        "wind_speed": current.get("wind_speed", 0),
                        "wind_direction": current.get("wind_deg", 0),
                        "uv_index": current.get("uvi", 0),
                        "pressure": current.get("pressure", 0),
                        "description": weather.get("description", "Unknown").capitalize(),
                        "weather_code": weather.get("id", 0),
                        "forecast": [
                            {
                                "date": d.get("dt", 0),
                                "max_temp": d.get("temp", {}).get("max", 0),
                                "min_temp": d.get("temp", {}).get("min", 0),
                                "precipitation": d.get("pop", 0) * 100,
                                "wind_speed": d.get("wind_speed", 0),
                                "description": (d.get("weather") or [{}])[0].get("description", "Unknown").capitalize(),
                            }
                            for d in data.get("daily", [])[:7]
                        ],
                        "provider": "openweathermap",
                    }
        except Exception:
            pass
        return await OpenMeteoProvider.get_current(latitude, longitude)


async def get_weather(latitude: float, longitude: float) -> dict:
    if settings.WEATHER_API_KEY and settings.WEATHER_API_PROVIDER == "openweathermap":
        return await OpenWeatherMapProvider.get_current(latitude, longitude)
    return await OpenMeteoProvider.get_current(latitude, longitude)
