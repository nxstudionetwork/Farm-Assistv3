"""Live Market Prices API.

Public price data (visible to any authenticated farmer) comes exclusively
from the market_prices table, which is populated only by verified sources
(AGMARKNET via data.gov.in, or official CSV import). Watchlist and alerts are
private and strictly scoped to the requesting farmer.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.config import settings
from app.utils.auth import get_current_user, generate_id
from app.models.user import User, FarmerProfile, UserAddress, UserSettings
from app.models.farm import Farm
from app.models.crop import Crop, CropCycle
from app.models.market_price import (
    MarketPrice, MarketWatchlist, MarketPriceAlert,
)
from app.schemas.market_price import (
    WatchlistCreate, WatchlistResponse, AlertCreate, AlertResponse,
)
from app.services import market_price_service as svc

router = APIRouter(prefix="/api/v1", tags=["Market Prices"])

# Small TTL cache for the AI overview. The endpoint is cheap in data-driven
# mode but may call an LLM (up to ~15s) when a provider key is configured;
# re-serving recent scopes avoids recomputation and repeated slow calls.
_AI_OVERVIEW_CACHE: Dict[str, Dict[str, Any]] = {}
_AI_OVERVIEW_CACHE_TTL = 90.0


def _latest_only_query(db: Session):
    """Base query restricted to the newest record per (market, commodity, variety)."""
    var_key = func.coalesce(MarketPrice.variety, "")
    latest_sub = (
        db.query(
            MarketPrice.market.label("market"),
            MarketPrice.commodity.label("commodity"),
            var_key.label("var_key"),
            func.max(MarketPrice.price_date).label("max_date"),
        )
        .group_by(MarketPrice.market, MarketPrice.commodity, var_key)
        .subquery()
    )
    return db.query(MarketPrice).join(
        latest_sub,
        and_(
            MarketPrice.market == latest_sub.c.market,
            MarketPrice.commodity == latest_sub.c.commodity,
            func.coalesce(MarketPrice.variety, "") == latest_sub.c.var_key,
            MarketPrice.price_date == latest_sub.c.max_date,
        ),
    )


def _apply_filters(q, *, search: Optional[str] = None, category: Optional[str] = None,
                   state: Optional[str] = None, district: Optional[str] = None,
                   region: Optional[str] = None, market: Optional[str] = None,
                   commodity: Optional[str] = None):
    if search:
        like = f"%{search.strip().lower()}%"
        q = q.filter(or_(
            func.lower(MarketPrice.commodity).like(like),
            func.lower(MarketPrice.market).like(like),
            func.lower(func.coalesce(MarketPrice.district, "")).like(like),
            func.lower(func.coalesce(MarketPrice.state, "")).like(like),
            func.lower(func.coalesce(MarketPrice.region, "")).like(like),
            func.lower(func.coalesce(MarketPrice.variety, "")).like(like),
        ))
    if category and category.lower() != "all":
        q = q.filter(func.lower(MarketPrice.category) == category.strip().lower())
    if state:
        q = q.filter(func.lower(MarketPrice.state) == state.strip().lower())
    if district:
        q = q.filter(func.lower(MarketPrice.district) == district.strip().lower())
    if region:
        q = q.filter(func.lower(MarketPrice.region) == region.strip().lower())
    if market:
        q = q.filter(func.lower(MarketPrice.market) == market.strip().lower())
    if commodity:
        q = q.filter(func.lower(MarketPrice.commodity) == commodity.strip().lower())
    return q


# ---------------------------------------------------------------------------
# Summary / metadata endpoints (declared before the /{price_id} catch-all)
# ---------------------------------------------------------------------------

@router.get("/market-prices/summary")
def market_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    freshness = svc.freshness_info(db)
    data: dict = {
        "tracked_commodities": 0,
        "markets_covered": 0,
        "states_covered": 0,
        "regions_covered": 0,
        "highest_increase": None,
        "highest_decrease": None,
        "latest_price_date": freshness.get("latest_price_date"),
        "last_updated": freshness.get("last_fetch_timestamp"),
    }
    if not freshness["data_available"]:
        return {"status": "success", "data": {**data, "freshness": freshness}}

    data["tracked_commodities"] = db.query(func.count(func.distinct(MarketPrice.commodity))).scalar() or 0
    data["markets_covered"] = db.query(func.count(func.distinct(MarketPrice.market))).scalar() or 0
    data["states_covered"] = db.query(func.count(func.distinct(MarketPrice.state))).scalar() or 0
    data["regions_covered"] = (
        db.query(func.count(func.distinct(MarketPrice.region)))
        .filter(MarketPrice.region.isnot(None))
        .scalar() or 0
    )

    latest_date = freshness.get("latest_price_date")
    if latest_date:
        rows = (
            db.query(MarketPrice)
            .filter(MarketPrice.price_date == latest_date, MarketPrice.modal_price.isnot(None))
            .limit(1000)
            .all()
        )
        prev_map = svc.previous_prices_batch(db, rows)
        best_up, best_down = None, None
        for row in rows:
            prev = prev_map.get((row.market, row.commodity, row.variety or ""))
            if not prev:
                continue
            change = svc.compute_change(row.modal_price, prev.modal_price)
            if not change["available"] or change["percent"] is None:
                continue
            item = {**svc.price_to_dict(row, change)}
            if change["direction"] == "up" and (best_up is None or change["percent"] > best_up["change"]["percent"]):
                best_up = item
            if change["direction"] == "down" and (best_down is None or change["percent"] < best_down["change"]["percent"]):
                best_down = item
        data["highest_increase"] = best_up
        data["highest_decrease"] = best_down

    return {"status": "success", "data": {**data, "freshness": freshness}}


@router.get("/market-prices/categories")
def market_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(MarketPrice.category, func.count(func.distinct(MarketPrice.commodity)))
        .group_by(MarketPrice.category)
        .all()
    )
    counts = {}
    for category, count in rows:
        key = category or "Other"
        counts[key] = counts.get(key, 0) + (count or 0)
    categories = [{"name": name, "count": counts.get(name, 0)} for name in svc.CATEGORY_ORDER]
    return {"status": "success", "data": {"categories": categories}}


@router.get("/market-prices/markets")
def market_locations(
    state: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    states_q = db.query(func.distinct(MarketPrice.state)).filter(MarketPrice.state.isnot(None))
    states = sorted(s for (s,) in states_q.all() if s)

    districts_q = db.query(func.distinct(MarketPrice.district)).filter(MarketPrice.district.isnot(None))
    if state:
        districts_q = districts_q.filter(func.lower(MarketPrice.state) == state.strip().lower())
    districts = sorted(d for (d,) in districts_q.all() if d)

    regions_q = db.query(func.distinct(MarketPrice.region)).filter(MarketPrice.region.isnot(None))
    if state:
        regions_q = regions_q.filter(func.lower(MarketPrice.state) == state.strip().lower())
    if district:
        regions_q = regions_q.filter(func.lower(MarketPrice.district) == district.strip().lower())
    regions = sorted(r for (r,) in regions_q.all() if r)

    markets_q = db.query(func.distinct(MarketPrice.market))
    if state:
        markets_q = markets_q.filter(func.lower(MarketPrice.state) == state.strip().lower())
    if district:
        markets_q = markets_q.filter(func.lower(MarketPrice.district) == district.strip().lower())
    if region:
        markets_q = markets_q.filter(func.lower(MarketPrice.region) == region.strip().lower())
    markets = sorted(m for (m,) in markets_q.all() if m)

    return {"status": "success", "data": {
        "states": states,
        "districts": districts,
        "regions": regions,
        "markets": markets[:500],
    }}


@router.get("/market-prices/search")
def market_search(
    q: str = Query(..., min_length=2, max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    like = f"%{q.strip().lower()}%"

    def distinct_values(column, extra_state=False):
        query = db.query(func.distinct(column)).filter(
            column.isnot(None), func.lower(column).like(like)
        ).limit(8)
        return sorted(v for (v,) in query.all() if v)

    return {"status": "success", "data": {
        "commodities": distinct_values(MarketPrice.commodity),
        "markets": distinct_values(MarketPrice.market),
        "districts": distinct_values(MarketPrice.district),
        "states": distinct_values(MarketPrice.state),
        "regions": distinct_values(MarketPrice.region),
        "varieties": distinct_values(MarketPrice.variety),
    }}


@router.get("/market-prices/history")
def price_history(
    commodity: str = Query(..., min_length=1, max_length=120),
    market: Optional[str] = Query(None, max_length=200),
    variety: Optional[str] = Query(None, max_length=120),
    state: Optional[str] = Query(None, max_length=120),
    region: Optional[str] = Query(None, max_length=120),
    days: int = Query(30, ge=1, le=730),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cutoff = (datetime.utcnow().date() - timedelta(days=days)).isoformat()
    q = db.query(MarketPrice).filter(
        func.lower(MarketPrice.commodity) == commodity.strip().lower(),
        MarketPrice.price_date >= cutoff,
    )
    if market:
        q = q.filter(func.lower(MarketPrice.market) == market.strip().lower())
    if variety:
        q = q.filter(func.lower(MarketPrice.variety) == variety.strip().lower())
    if state:
        q = q.filter(func.lower(MarketPrice.state) == state.strip().lower())
    if region:
        q = q.filter(func.lower(MarketPrice.region) == region.strip().lower())
    rows = q.order_by(MarketPrice.price_date.asc()).all()

    series_map: dict = {}
    for row in rows:
        if row.modal_price is None:
            continue
        entry = series_map.setdefault(row.price_date, {
            "date": row.price_date, "modals": [], "mins": [], "maxs": [], "records": 0,
        })
        entry["modals"].append(row.modal_price)
        if row.min_price is not None:
            entry["mins"].append(row.min_price)
        if row.max_price is not None:
            entry["maxs"].append(row.max_price)
        entry["records"] += 1

    series = []
    for date_key in sorted(series_map):
        e = series_map[date_key]
        series.append({
            "date": date_key,
            "modal_price": round(sum(e["modals"]) / len(e["modals"]), 2),
            "min_price": round(sum(e["mins"]) / len(e["mins"]), 2) if e["mins"] else None,
            "max_price": round(sum(e["maxs"]) / len(e["maxs"]), 2) if e["maxs"] else None,
            "records": e["records"],
        })

    return {"status": "success", "data": {
        "commodity": commodity,
        "market": market,
        "variety": variety,
        "days": days,
        "unit": "Rs/Quintal",
        "aggregated": (not market) or any(e["records"] > 1 for e in series),
        "points": series,
    }}


@router.get("/market-prices/compare")
def compare_markets(
    commodity: str = Query(..., min_length=1, max_length=120),
    state: Optional[str] = Query(None, max_length=120),
    district: Optional[str] = Query(None, max_length=120),
    region: Optional[str] = Query(None, max_length=120),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = _apply_filters(
        _latest_only_query(db),
        commodity=commodity, state=state, district=district, region=region,
    )
    rows = q.order_by(MarketPrice.modal_price.desc()).all()
    entries = [svc.price_to_dict(r) for r in rows if r.modal_price is not None]

    data: dict = {
        "commodity": commodity,
        "markets": entries,
        "lowest": None,
        "highest": None,
        "average": None,
        "market_count": len(entries),
        "disclaimer": (
            "Highest listed market price. Actual selling price may vary based on "
            "quality, quantity, negotiations and market conditions."
        ),
    }
    if entries:
        prices = [e["modal_price"] for e in entries]
        data["highest"] = entries[0]
        data["lowest"] = entries[-1]
        data["average"] = round(sum(prices) / len(prices), 2)
    return {"status": "success", "data": data}


@router.get("/market-prices/recommended")
def recommended_prices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """'Relevant to Your Farm' — built only from the farmer's real profile,
    farms, active crop cycles and saved location. Never random commodities."""
    crops: list = []
    profile = db.query(FarmerProfile).filter(FarmerProfile.user_id == current_user.id).first()
    if profile and profile.preferred_crops:
        crops.extend(c.strip() for c in profile.preferred_crops.split(",") if c.strip())
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if user_settings and user_settings.farm_default_crop:
        crops.append(user_settings.farm_default_crop.strip())

    farms = db.query(Farm).filter(Farm.user_id == current_user.id).all()
    farm_ids = [f.id for f in farms]
    if farm_ids:
        rows = (
            db.query(Crop.name)
            .join(CropCycle, CropCycle.crop_id == Crop.id)
            .filter(CropCycle.farm_id.in_(farm_ids), CropCycle.status == "active")
            .distinct()
            .all()
        )
        crops.extend(name for (name,) in rows if name)

    states = sorted({f.state.strip() for f in farms if f.state and f.state.strip()})
    if not states:
        address = (
            db.query(UserAddress)
            .filter(UserAddress.user_id == current_user.id)
            .order_by(UserAddress.is_primary.desc())
            .first()
        )
        if address and address.state:
            states.append(address.state.strip())

    crops = list(dict.fromkeys(crops))[:8]
    if not crops and not states:
        return {"status": "success", "data": {
            "available": False,
            "reason": "Add your farm details or preferred crops to get market recommendations.",
            "items": [],
        }}

    items = []
    seen = set()
    base = _latest_only_query(db)
    if crops:
        crop_filters = []
        for crop_name in crops:
            token = crop_name.strip().lower()
            if len(token) >= 3:
                crop_filters.append(func.lower(MarketPrice.commodity).like(f"%{token}%"))
        if crop_filters:
            rows = base.filter(or_(*crop_filters)).order_by(MarketPrice.price_date.desc()).limit(60).all()
            for row in rows:
                key = (row.market, row.commodity, row.variety)
                if key in seen:
                    continue
                seen.add(key)
                change = svc.compute_change(row.modal_price, (svc.previous_price(db, row) or _NullRow()).modal_price)
                entry = svc.price_to_dict(row, change)
                entry["reason"] = f"Based on your crop: {row.commodity}"
                if states and row.state and row.state.strip().lower() in [s.lower() for s in states]:
                    entry["reason"] += f" near you ({row.state})"
                items.append(entry)

    if len(items) < 3 and states:
        rows = (
            base.filter(func.lower(MarketPrice.state) == states[0].lower())
            .order_by(MarketPrice.price_date.desc())
            .limit(30)
            .all()
        )
        for row in rows:
            key = (row.market, row.commodity, row.variety)
            if key in seen:
                continue
            seen.add(key)
            change = svc.compute_change(row.modal_price, (svc.previous_price(db, row) or _NullRow()).modal_price)
            entry = svc.price_to_dict(row, change)
            entry["reason"] = f"Based on your location: {row.state}"
            items.append(entry)

    return {"status": "success", "data": {
        "available": bool(items),
        "reason": None if items else "No market data currently matches your farm profile.",
        "items": items[:6],
    }}


class _NullRow:
    modal_price = None


# ---------------------------------------------------------------------------
# AI Market Overview (real data → backend → AI service)
# ---------------------------------------------------------------------------

def _resolve_ai_provider() -> tuple:
    """Return (api_key, provider, base_url, model) when an AI provider is
    configured, else (None, None, None, None). Never invoked in tests; no
    external calls happen unless an API key is present in settings."""
    if settings.OPENAI_API_KEY:
        return settings.OPENAI_API_KEY, "openai", "https://api.openai.com/v1", "gpt-4o-mini"
    if settings.GEMINI_API_KEY:
        return settings.GEMINI_API_KEY, "gemini", "https://generativelanguage.googleapis.com/v1beta", "gemini-1.5-flash"
    if settings.ANTHROPIC_API_KEY:
        return settings.ANTHROPIC_API_KEY, "claude", "https://api.anthropic.com", "claude-3-5-haiku-latest"
    return None, None, None, None


async def _post_json(url: str, payload: dict, headers: dict) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _overview_scope_label(*, search=None, category=None, state=None, district=None,
                          region=None, market=None, commodity=None) -> str:
    parts: List[str] = []
    if search:
        parts.append(f"search \"{search}\"")
    if category and category.lower() != "all":
        parts.append(category)
    if state:
        parts.append(state)
    if district:
        parts.append(district)
    if region:
        parts.append(f"region {region}")
    if market:
        parts.append(market)
    if commodity:
        parts.append(commodity)
    return ", ".join(parts) if parts else "all available data"


async def _ai_enhance_overview(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best-effort: ask a configured AI provider to reword the overview from the
    real figures only. Returns None when no provider is configured or the call
    fails, so the data-driven baseline is always served."""
    api_key, provider, base_url, model = _resolve_ai_provider()
    if not api_key:
        return None
    digest = {
        "basis": payload.get("basis"),
        "summary": payload.get("summary"),
        "rising": [{
            "commodity": m.get("commodity"), "variety": m.get("variety"),
            "market": m.get("market"), "modal_price": m.get("modal_price"),
            "percent": (m.get("change") or {}).get("percent"),
            "unit": m.get("unit"),
        } for m in payload.get("rising", [])],
        "falling": [{
            "commodity": m.get("commodity"), "variety": m.get("variety"),
            "market": m.get("market"), "modal_price": m.get("modal_price"),
            "percent": (m.get("change") or {}).get("percent"),
            "unit": m.get("unit"),
        } for m in payload.get("falling", [])],
        "key_trends": payload.get("key_trends"),
    }
    prompt = (
        "You are Farm Assist's market analyst. Using ONLY the official figures "
        "provided below (never invent commodity, market, price, date or percentage) "
        "return a JSON object with exactly these keys: 'summary' (one short "
        "farmer-friendly paragraph), 'key_trends' (an array of 3-5 bullet strings "
        "derived strictly from the data), 'farmer_insight' (one actionable, "
        "data-bound selling tip referencing a specific commodity, market and figure). "
        "Output valid JSON only. Data: " + json.dumps(digest)
    )
    try:
        if provider == "openai":
            body = await _post_json(
                f"{base_url}/chat/completions",
                {
                    "model": model, "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}],
                },
                {"Authorization": f"Bearer {api_key}"},
            )
            out = body["choices"][0]["message"]["content"]
        elif provider == "gemini":
            body = await _post_json(
                f"{base_url.rstrip('/')}/models/{model}:generateContent",
                {"contents": [{"parts": [{"text": prompt}]}]},
                {"x-goog-api-key": api_key},
            )
            out = body["candidates"][0]["content"]["parts"][0]["text"]
        elif provider == "claude":
            body = await _post_json(
                f"{base_url}/v1/messages",
                {
                    "model": model, "max_tokens": 800, "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}],
                },
                {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
            out = body["content"][0]["text"]
        else:
            return None
    except Exception:
        return None
    out = (out or "").strip()
    if out.startswith("```"):
        out = out.strip("`").lstrip()
        if out.lower().startswith("json"):
            out = out[4:].strip()
    try:
        parsed = json.loads(out)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    summary = str(parsed.get("summary") or "").strip()
    trends = [str(t).strip() for t in parsed.get("key_trends", []) if str(t).strip()][:5]
    insight = str(parsed.get("farmer_insight") or "").strip()
    if not summary and not trends:
        return None
    return {"model": provider, "summary": summary, "key_trends": trends, "farmer_insight": insight}


@router.get("/market-prices/ai-overview")
async def market_ai_overview(
    q: Optional[str] = Query(None, max_length=100),
    category: Optional[str] = Query(None, max_length=60),
    state: Optional[str] = Query(None, max_length=120),
    district: Optional[str] = Query(None, max_length=120),
    region: Optional[str] = Query(None, max_length=120),
    market: Optional[str] = Query(None, max_length=200),
    commodity: Optional[str] = Query(None, max_length=120),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI Market Overview built from the real filtered market data.

    Deterministic baseline analysis always works and never fabricates figures.
    When an AI provider key is configured, the provider may reword the summary
    strictly from the same verified numbers.
    """
    scope = _overview_scope_label(
        search=q, category=category, state=state, district=district,
        region=region, market=market, commodity=commodity,
    )
    cache_key = scope
    cached = _AI_OVERVIEW_CACHE.get(cache_key)
    if cached and (datetime.utcnow().timestamp() - cached["_ts"]) < _AI_OVERVIEW_CACHE_TTL:
        return {"status": "success", "data": {
            **cached["data"],
            "generated_at": datetime.utcnow().isoformat(),
            "model": cached["data"].get("model"),
        }}
    query = _apply_filters(
        _latest_only_query(db),
        search=q, category=category, state=state, district=district,
        region=region, market=market, commodity=commodity,
    )
    overview = svc.build_market_overview(db, query, scope)
    if not overview:
        return {"status": "success", "data": {
            "available": False,
            "insufficient": True,
            "message": "Not enough current market data to generate a reliable overview.",
            "model": None,
            "generated_at": datetime.utcnow().isoformat(),
        }}
    enhanced = await _ai_enhance_overview(overview)
    if enhanced:
        overview["model"] = enhanced["model"]
        if enhanced.get("summary"):
            overview["summary"] = enhanced["summary"]
        if enhanced.get("key_trends"):
            overview["key_trends"] = enhanced["key_trends"]
        if enhanced.get("farmer_insight"):
            overview["farmer_insight"] = enhanced["farmer_insight"]
    else:
        overview["model"] = "data-driven"
    data = {
        "available": True,
        "insufficient": False,
        "message": None,
        "generated_at": datetime.utcnow().isoformat(),
        **overview,
    }
    _AI_OVERVIEW_CACHE[cache_key] = {"_ts": datetime.utcnow().timestamp(), "data": dict(data)}
    return {"status": "success", "data": data}


@router.post("/market-prices/refresh")
def refresh_market_data(
    force: bool = Query(False),
    state: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    commodity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = {}
    if state:
        filters["State"] = state
    if district:
        filters["District"] = district
    if region:
        filters["Region"] = region
    if commodity:
        filters["Commodity"] = commodity
    result = svc.sync_from_source(db, trigger="api", force=force, filters=filters or None)
    return {"status": "success", "data": {
        "refresh": result,
        "freshness": svc.freshness_info(db),
    }}


# ---------------------------------------------------------------------------
# Watchlist (private, farmer-scoped)
# ---------------------------------------------------------------------------

def _watchlist_entry(db: Session, row: MarketWatchlist) -> dict:
    data = WatchlistResponse.model_validate(row).model_dump()
    data["created_at"] = row.created_at.isoformat() if row.created_at else None
    q = db.query(MarketPrice).filter(
        func.lower(MarketPrice.commodity) == row.commodity.strip().lower(),
        MarketPrice.modal_price.isnot(None),
    )
    if row.market:
        q = q.filter(func.lower(MarketPrice.market) == row.market.strip().lower())
    latest = q.order_by(MarketPrice.price_date.desc()).first()
    if latest:
        change = svc.compute_change(latest.modal_price, (svc.previous_price(db, latest) or _NullRow()).modal_price)
        data["latest_price"] = svc.price_to_dict(latest, change)
    else:
        data["latest_price"] = None
    return data


@router.get("/market-prices/watchlist")
def get_watchlist(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(MarketWatchlist)
        .filter(MarketWatchlist.user_id == current_user.id)
        .order_by(MarketWatchlist.created_at.desc())
        .all()
    )
    items = [_watchlist_entry(db, r) for r in rows]
    return {"status": "success", "data": {"items": items, "total": len(items)}}


@router.post("/market-prices/watchlist")
def add_to_watchlist(
    payload: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    duplicate = (
        db.query(MarketWatchlist)
        .filter(
            MarketWatchlist.user_id == current_user.id,
            func.lower(MarketWatchlist.commodity) == payload.commodity.strip().lower(),
            (func.lower(MarketWatchlist.market) == payload.market.strip().lower())
            if payload.market else MarketWatchlist.market.is_(None),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="This item is already in your watchlist.")

    row = MarketWatchlist(
        watch_id=generate_id("FA-MWL", db, MarketWatchlist),
        user_id=current_user.id,
        commodity=payload.commodity.strip(),
        market=payload.market.strip() if payload.market else None,
        district=payload.district.strip() if payload.district else None,
        state=payload.state.strip() if payload.state else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "success", "data": _watchlist_entry(db, row)}


@router.delete("/market-prices/watchlist/{watch_id}")
def remove_from_watchlist(
    watch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(MarketWatchlist)
        .filter(MarketWatchlist.watch_id == watch_id, MarketWatchlist.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    db.delete(row)
    db.commit()
    return {"status": "success", "data": {"removed": watch_id}}


# ---------------------------------------------------------------------------
# Price alerts (private, farmer-scoped)
# ---------------------------------------------------------------------------

@router.get("/market-prices/alerts")
def list_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(MarketPriceAlert)
        .filter(MarketPriceAlert.user_id == current_user.id)
        .order_by(MarketPriceAlert.created_at.desc())
        .all()
    )
    items = []
    for row in rows:
        data = AlertResponse.model_validate(row).model_dump()
        for field in ("created_at", "last_checked_at", "last_triggered_at"):
            data[field] = getattr(row, field).isoformat() if getattr(row, field) else None
        items.append(data)
    return {"status": "success", "data": {
        "items": items,
        "total": len(items),
        "monitoring": {
            "automated": svc.source_configured(),
            "note": (
                "Alerts are checked automatically whenever new market data is synced "
                "to the server. If the live source is not configured, alerts are stored "
                "and checked against imported/available market data."
            ),
        },
    }}


@router.post("/market-prices/alerts")
def create_alert(
    payload: AlertCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = MarketPriceAlert(
        alert_id=generate_id("FA-MAL", db, MarketPriceAlert),
        user_id=current_user.id,
        commodity=payload.commodity.strip(),
        market=payload.market.strip() if payload.market else None,
        target_price=payload.target_price,
        condition=payload.condition,
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    # Immediately evaluate against real data so the farmer gets instant,
    # truthful feedback if the condition is already met.
    svc.evaluate_alerts(db, user_id=current_user.id)
    db.refresh(row)
    data = AlertResponse.model_validate(row).model_dump()
    for field in ("created_at", "last_checked_at", "last_triggered_at"):
        data[field] = getattr(row, field).isoformat() if getattr(row, field) else None
    return {"status": "success", "data": data}


@router.delete("/market-prices/alerts/{alert_id}")
def delete_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(MarketPriceAlert)
        .filter(MarketPriceAlert.alert_id == alert_id, MarketPriceAlert.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Price alert not found.")
    db.delete(row)
    db.commit()
    return {"status": "success", "data": {"removed": alert_id}}


# ---------------------------------------------------------------------------
# Price list + detail
# ---------------------------------------------------------------------------

@router.get("/market-prices")
def list_market_prices(
    q: Optional[str] = Query(None, max_length=100),
    category: Optional[str] = Query(None, max_length=60),
    state: Optional[str] = Query(None, max_length=120),
    district: Optional[str] = Query(None, max_length=120),
    region: Optional[str] = Query(None, max_length=120),
    market: Optional[str] = Query(None, max_length=200),
    commodity: Optional[str] = Query(None, max_length=120),
    sort: Optional[str] = Query("recent", pattern="^(recent|highest|lowest)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = _apply_filters(
        _latest_only_query(db),
        search=q, category=category, state=state, district=district,
        region=region, market=market, commodity=commodity,
    )
    total = query.count()
    if sort == "highest":
        order = (
            func.coalesce(MarketPrice.modal_price, -1).desc(),
            MarketPrice.commodity.asc(),
            MarketPrice.variety.asc(),
        )
    elif sort == "lowest":
        order = (
            func.coalesce(MarketPrice.modal_price, 1e12).asc(),
            MarketPrice.commodity.asc(),
            MarketPrice.variety.asc(),
        )
    else:
        order = (
            MarketPrice.price_date.desc(),
            MarketPrice.commodity.asc(),
            MarketPrice.market.asc(),
        )
    rows = (
        query.order_by(*order)
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    items = []
    prev_map = svc.previous_prices_batch(db, rows)
    for row in rows:
        prev = prev_map.get((row.market, row.commodity, row.variety or ""))
        change = svc.compute_change(row.modal_price, prev.modal_price if prev else None)
        entry = svc.price_to_dict(row, change)
        if prev:
            entry["change"]["previous_date"] = prev.price_date
        items.append(entry)

    return {"status": "success", "data": {
        "page": page,
        "limit": limit,
        "sort": sort,
        "total": total,
        "total_pages": (total + limit - 1) // limit if total else 0,
        "items": items,
        "freshness": svc.freshness_info(db),
    }}


@router.get("/market-prices/{price_id}")
def get_market_price(
    price_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(MarketPrice)
        .filter(or_(MarketPrice.id == price_id, MarketPrice.price_id == price_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Market price record not found.")
    prev = svc.previous_price(db, row)
    change = svc.compute_change(row.modal_price, prev.modal_price if prev else None)
    data = svc.price_to_dict(row, change)
    if prev:
        data["change"]["previous_date"] = prev.price_date
    return {"status": "success", "data": data}
