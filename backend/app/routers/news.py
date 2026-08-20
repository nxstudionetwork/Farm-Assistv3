from typing import Optional
from fastapi import APIRouter, Depends, Query
from app.integrations.news_service import NewsService, MarketPriceService

router = APIRouter(prefix="/api/v1", tags=["News & Market"])


@router.get("/news", response_model=dict)
async def get_news(
    category: str = "agriculture",
    query: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    result = await NewsService.get_news(category, query, page, page_size)
    return {"status": "success", "data": result}


@router.get("/market-prices", response_model=dict)
async def get_market_prices(
    crop: Optional[str] = None,
    location: Optional[str] = None,
):
    result = await MarketPriceService.get_prices(crop, location)
    return {"status": "success", "data": result}
