from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import httpx

from app.database.connection import get_db
from app.utils.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/v1", tags=["Maps"])


@router.get("/maps/geocode")
def geocode_address(
    address: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": address,
                    "format": "json",
                    "limit": 5,
                    "countrycodes": "in",
                },
                headers={"User-Agent": "FarmAssist/1.0"},
            )
            resp.raise_for_status()
            results = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")

    if not results:
        return {"status": "success", "data": {"results": [], "message": "No results found"}}

    return {
        "status": "success",
        "data": {
            "results": [
                {
                    "display_name": r.get("display_name"),
                    "latitude": float(r.get("lat", 0)),
                    "longitude": float(r.get("lon", 0)),
                    "type": r.get("type"),
                    "importance": r.get("importance"),
                }
                for r in results
            ]
        },
    }


@router.get("/maps/reverse-geocode")
def reverse_geocode(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "json",
                },
                headers={"User-Agent": "FarmAssist/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Reverse geocoding service unavailable")

    if not data or "error" in data:
        return {"status": "success", "data": {"address": None, "message": "No address found for these coordinates"}}

    addr = data.get("address", {})
    return {
        "status": "success",
        "data": {
            "display_name": data.get("display_name"),
            "address": {
                "house_number": addr.get("house_number"),
                "road": addr.get("road"),
                "village": addr.get("village") or addr.get("hamlet"),
                "mandal": addr.get("suburb") or addr.get("county"),
                "district": addr.get("district") or addr.get("state_district"),
                "state": addr.get("state"),
                "pincode": addr.get("postcode"),
                "country": addr.get("country"),
            },
            "latitude": latitude,
            "longitude": longitude,
        },
    }

from app.config import settings

@router.get("/maps/key")
def get_maps_key(current_user: User = Depends(get_current_user)):
    """Return Google Maps API key for the frontend.
    The key is read from settings and sent only to authenticated users.
    """
    return {"status": "success", "data": {"google_maps_api_key": settings.GOOGLE_MAPS_API_KEY}}
