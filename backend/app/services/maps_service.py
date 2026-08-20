import httpx
from typing import Optional
from app.config import settings


async def reverse_geocode(latitude: float, longitude: float) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "json",
                    "addressdetails": 1,
                },
                headers={"User-Agent": "FarmAssist/1.0"},
            )
            if response.status_code == 200:
                data = response.json()
                addr = data.get("address", {})
                return {
                    "display_name": data.get("display_name", ""),
                    "village": addr.get("village", addr.get("town", addr.get("city", ""))),
                    "mandal": addr.get("county", addr.get("state_district", "")),
                    "district": addr.get("state_district", addr.get("county", "")),
                    "state": addr.get("state", ""),
                    "country": addr.get("country", ""),
                    "pincode": addr.get("postcode", ""),
                    "latitude": latitude,
                    "longitude": longitude,
                }
    except Exception as e:
        return {"display_name": f"Location ({latitude}, {longitude})", "error": str(e)}


async def forward_geocode(address: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": address,
                    "format": "json",
                    "limit": 5,
                },
                headers={"User-Agent": "FarmAssist/1.0"},
            )
            if response.status_code == 200:
                data = response.json()
                results = []
                for r in data:
                    results.append({
                        "display_name": r.get("display_name", ""),
                        "latitude": float(r.get("lat", 0)),
                        "longitude": float(r.get("lon", 0)),
                    })
                return {"results": results}
    except Exception as e:
        return {"results": [], "error": str(e)}
