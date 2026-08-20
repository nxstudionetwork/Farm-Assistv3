import httpx
import logging
from typing import Optional
from app.config import settings
from app.integrations.base import BaseIntegration

logger = logging.getLogger(__name__)


class NewsService(BaseIntegration):
    name = "news"
    requires_api_key = True
    api_key_setting = "NEWS_API_KEY"

    @staticmethod
    async def get_news(category: str = "agriculture", query: Optional[str] = None, page: int = 1, page_size: int = 10) -> dict:
        if settings.NEWS_API_KEY:
            try:
                q = query or f"Indian agriculture {category}"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{settings.NEWS_API_BASE_URL}/everything",
                        params={
                            "q": q,
                            "apiKey": settings.NEWS_API_KEY,
                            "language": "en",
                            "sortBy": "publishedAt",
                            "page": page,
                            "pageSize": min(page_size, 100),
                        },
                    )
                    if response.status_code == 200:
                        data = response.json()
                        articles = []
                        for a in data.get("articles", []):
                            articles.append({
                                "title": a.get("title", ""),
                                "description": a.get("description", ""),
                                "source": a.get("source", {}).get("name", ""),
                                "url": a.get("url", ""),
                                "image_url": a.get("urlToImage", ""),
                                "published_at": a.get("publishedAt", ""),
                            })
                        return {
                            "articles": articles,
                            "total_results": data.get("totalResults", 0),
                            "provider": "newsapi",
                        }
                    logger.warning(f"News API returned {response.status_code}")
            except Exception as e:
                logger.warning(f"News API failed: {e}")

        return NewsService._fallback_news(category)

    @staticmethod
    def _fallback_news(category: str) -> dict:
        articles = [
            {"title": "PM-KISAN 18th Instalment Released - ₹21,000 Crore Transferred", "description": "The 18th instalment of PM-KISAN scheme has been released, benefiting over 9.5 crore farmers across India.", "source": "PIB India", "url": "#", "image_url": "", "published_at": "2026-07-30T10:00:00Z"},
            {"title": "Kharif Sowing Crosses 1,050 Lakh Hectares - Normal Monsoon Boosts Planting", "description": "Kharif sowing has crossed 1,050 lakh hectares with normal monsoon rains boosting planting across major states.", "source": "Agriculture Ministry", "url": "#", "image_url": "", "published_at": "2026-07-29T08:30:00Z"},
            {"title": "Government Launches Digital Crop Survey in 600 Districts", "description": "The Ministry of Agriculture has launched a digital crop survey to capture real-time data on crop area, yield estimation, and farmer details.", "source": "Economic Times", "url": "#", "image_url": "", "published_at": "2026-07-28T06:00:00Z"},
            {"title": "MSP for Rabi Crops Increased - Wheat, Mustard Get Higher Prices", "description": "The government has announced increased Minimum Support Prices for rabi crops including wheat (₹2,275/quintal) and mustard.", "source": "AgriWatch", "url": "#", "image_url": "", "published_at": "2026-07-27T12:00:00Z"},
            {"title": "Soil Health Card 2.0 Launched with AI-Based Recommendations", "description": "The upgraded Soil Health Card scheme now provides AI-powered fertilizer recommendations based on soil test results.", "source": "ICAR", "url": "#", "image_url": "", "published_at": "2026-07-26T09:00:00Z"},
        ]
        return {"articles": articles, "total_results": len(articles), "provider": "fallback"}


class MarketPriceService(BaseIntegration):
    name = "market-price"
    requires_api_key = False

    MOCK_PRICES = {
        "paddy": {"min": 2040, "max": 2180, "avg": 2100, "unit": "quintal", "mandi": "Warangal"},
        "wheat": {"min": 2275, "max": 2400, "avg": 2340, "unit": "quintal", "mandi": "Punjab"},
        "cotton": {"min": 6500, "max": 7200, "avg": 6850, "unit": "quintal", "mandi": "Guntur"},
        "maize": {"min": 1950, "max": 2100, "avg": 2025, "unit": "quintal", "mandi": "Maharashtra"},
        "soybean": {"min": 4300, "max": 4600, "avg": 4450, "unit": "quintal", "mandi": "Indore"},
        "groundnut": {"min": 5200, "max": 5600, "avg": 5400, "unit": "quintal", "mandi": "Gujarat"},
        "tur (arhar)": {"min": 6500, "max": 7000, "avg": 6750, "unit": "quintal", "mandi": "Maharashtra"},
        "sugarcane": {"min": 3400, "max": 3600, "avg": 3500, "unit": "tonne", "mandi": "UP"},
        "onion": {"min": 1800, "max": 2500, "avg": 2100, "unit": "quintal", "mandi": "Nashik"},
        "potato": {"min": 1500, "max": 2000, "avg": 1750, "unit": "quintal", "mandi": "Agra"},
        "tomato": {"min": 1200, "max": 3500, "avg": 2000, "unit": "quintal", "mandi": "Kolar"},
    }

    @staticmethod
    async def get_prices(crop: Optional[str] = None, location: Optional[str] = None) -> dict:
        if settings.MARKET_PRICE_API_KEY and settings.MARKET_PRICE_API_BASE_URL:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{settings.MARKET_PRICE_API_BASE_URL}/prices",
                        params={"crop": crop, "location": location},
                        headers={"Authorization": f"Bearer {settings.MARKET_PRICE_API_KEY}"},
                    )
                    if response.status_code == 200:
                        return response.json()
            except Exception as e:
                pass

        return MarketPriceService._fallback_prices(crop, location)

    @staticmethod
    def _fallback_prices(crop: Optional[str], location: Optional[str]) -> dict:
        prices = []
        for name, data in MarketPriceService.MOCK_PRICES.items():
            if crop and crop.lower() not in name.lower():
                continue
            prices.append({
                "crop": name.title(),
                "min_price": data["min"],
                "max_price": data["max"],
                "avg_price": data["avg"],
                "unit": data["unit"],
                "mandi": data["mandi"],
                "date": "2026-07-30",
            })
        return {"prices": prices, "provider": "fallback"}
