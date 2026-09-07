"""Market price data service.

Single ingestion boundary for agricultural market prices:

    data.gov.in AGMARKNET API  ->  transform/validate  ->  market_prices table

The API key lives only in backend settings (.env) and is never returned to
clients. No price data is ever fabricated: if the source is unreachable or
not configured, callers get an explicit status and the stored (timestamped)
data is served with honest freshness labels.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import httpx
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.market_price import MarketPrice, MarketDataSync
from app.models.notification import Notification  # noqa: F401 (used via helper)
from app.utils.auth import generate_id
from app.utils.notification_helper import create_notification


# ---------------------------------------------------------------------------
# Commodity categorisation (static UI grouping of real commodity names)
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: List[tuple] = [
    ("Paddy", ["paddy", "rice", "dhan"]),
    ("Wheat", ["wheat"]),
    ("Maize", ["maize", "corn"]),
    ("Cotton", ["cotton", "kapas"]),
    ("Groundnut", ["groundnut", "peanut"]),
    ("Chillies", ["chilli", "chillies"]),
    ("Turmeric", ["turmeric", "haldi"]),
    ("Sugarcane", ["sugarcane"]),
    ("Pulses", [
        "toor", "arhar", "moong", "gram", "chana", "urad", "masoor", "lentil",
        "pulse", "peas (dry)", "horse gram", "cowpea", "rajma", "tur",
    ]),
    ("Oilseeds", [
        "mustard", "soybean", "soya", "sesame", "sesamum", "til", "castor",
        "linseed", "sunflower", "rapeseed", "niger", "safflower", "oilseed",
    ]),
    ("Vegetables", [
        "potato", "onion", "tomato", "brinjal", "bhindi", "cabbage",
        "cauliflower", "carrot", "cucumber", "beans", "green peas", "peas",
        "capsicum", "gourd", "pumpkin", "sweet potato", "radish", "beetroot",
        "okra", "eggplant", "spinach", "leafy", "greens", "colocasia", "yam",
        "drumstick", "mushroom", "vegetable", "tomato hybrid", "onion dry",
        "potato local", "bitter", "ash", "ridge", "bottle", "snake gourd",
        "amla", "raw mango", "tender coconut",
    ]),
    ("Fruits", [
        "apple", "banana", "mango", "orange", "papaya", "guava", "grapes",
        "pomegranate", "watermelon", "pineapple", "sapota", "custard apple",
        "ber", "plum", "peach", "pear", "coconut", "lemon", "mosambi",
        "kinnow", "sweet lime", "fruit", "chikoo", "litchi", "strawberry",
    ]),
    ("Spices", [
        "ginger", "garlic", "coriander", "cumin", "jeera", "pepper",
        "cardamom", "clove", "cinnamon", "nutmeg", "fennel", "fenugreek",
        "ajwain", "spice", "bay leaf", "turmeric (spice)",
    ]),
]

CATEGORY_ORDER = [
    "All", "Paddy", "Wheat", "Maize", "Cotton", "Groundnut", "Chillies",
    "Turmeric", "Sugarcane", "Pulses", "Oilseeds", "Vegetables", "Fruits",
    "Spices", "Other",
]


def categorize_commodity(name: Optional[str]) -> str:
    if not name:
        return "Other"
    lowered = name.strip().lower()
    for category, keywords in CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in lowered:
                return category
    return "Other"


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------

def source_configured() -> bool:
    return bool(settings.MARKET_PRICE_API_KEY)


def _parse_source_date(raw: Optional[str]) -> Optional[str]:
    """AGMARKNET dates arrive as DD/MM/YYYY; normalise to ISO YYYY-MM-DD."""
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_price(raw: Any) -> Optional[float]:
    try:
        value = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _clean_str(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def transform_record(rec: Dict[str, Any], source: str) -> Optional[Dict[str, Any]]:
    """Validate/transform one raw source record. Returns None if unusable."""
    commodity = _clean_str(rec.get("Commodity") or rec.get("commodity"))
    market = _clean_str(rec.get("Market") or rec.get("market"))
    price_date = _parse_source_date(
        rec.get("Price_Date") or rec.get("price_date") or rec.get("Arrival_Date")
    )
    modal = _parse_price(rec.get("Modal_Price") or rec.get("modal_price"))
    min_p = _parse_price(rec.get("Min_Price") or rec.get("min_price"))
    max_p = _parse_price(rec.get("Max_Price") or rec.get("max_price"))
    if not commodity or not market or not price_date:
        return None
    if modal is None and min_p is None and max_p is None:
        return None
    source_url = (
        _clean_str(rec.get("Market_Webpage"))
        or _clean_str(rec.get("District_Webpage"))
        or settings.MARKET_PRICE_SOURCE_URL
    )
    return {
        "commodity": commodity,
        "variety": _clean_str(rec.get("Variety") or rec.get("variety")),
        "grade": _clean_str(rec.get("Grade") or rec.get("grade")),
        "category": categorize_commodity(commodity),
        "market": market,
        "district": _clean_str(rec.get("District") or rec.get("district")),
        "state": _clean_str(rec.get("State") or rec.get("state")),
        "min_price": min_p,
        "max_price": max_p,
        "modal_price": modal if modal is not None else min_p,
        "unit": "Rs/Quintal",
        "price_date": price_date,
        "arrival_date": _parse_source_date(rec.get("Arrival_Date")),
        "source": source,
        "source_url": source_url,
        "source_timestamp": _clean_str(rec.get("Price_Date") or rec.get("Arrival_Date")),
    }


def upsert_prices(db: Session, rows: List[Dict[str, Any]]) -> int:
    """Insert new records; update existing ones matched on the natural key."""
    stored = 0
    next_id: Optional[str] = None
    for row in rows:
        q = db.query(MarketPrice).filter(
            MarketPrice.source == row["source"],
            MarketPrice.market == row["market"],
            MarketPrice.commodity == row["commodity"],
            MarketPrice.price_date == row["price_date"],
        )
        if row.get("variety"):
            q = q.filter(MarketPrice.variety == row["variety"])
        else:
            q = q.filter(or_(MarketPrice.variety.is_(None), MarketPrice.variety == ""))
        if row.get("grade"):
            q = q.filter(MarketPrice.grade == row["grade"])
        else:
            q = q.filter(or_(MarketPrice.grade.is_(None), MarketPrice.grade == ""))
        existing = q.first()
        if existing:
            changed = False
            for field in ("min_price", "max_price", "modal_price", "district",
                          "state", "source_url", "source_timestamp", "category",
                          "unit", "arrival_date"):
                if getattr(existing, field) != row.get(field):
                    setattr(existing, field, row.get(field))
                    changed = True
            if changed:
                existing.fetched_at = datetime.utcnow()
                stored += 1
            continue
        if next_id is None:
            next_id = generate_id("FA-MKP", db, MarketPrice)
        entry = MarketPrice(
            price_id=next_id,
            fetched_at=datetime.utcnow(),
            **{k: row.get(k) for k in (
                "commodity", "variety", "grade", "category", "market", "district",
                "state", "min_price", "max_price", "modal_price", "unit",
                "price_date", "arrival_date", "source", "source_url",
                "source_timestamp",
            )},
        )
        # Advance the sequential FA-MKP-###### id without re-querying the DB.
        try:
            prefix, num = next_id.rsplit("-", 1)
            next_id = f"{prefix}-{str(int(num) + 1).zfill(6)}"
        except ValueError:
            next_id = generate_id("FA-MKP", db, MarketPrice)
        db.add(entry)
        stored += 1
    db.commit()
    return stored


# ---------------------------------------------------------------------------
# Sync from external verified source
# ---------------------------------------------------------------------------

def _record_sync(db: Session, status: str, trigger: str, message: str,
                 fetched: int = 0, stored: int = 0) -> MarketDataSync:
    sync = MarketDataSync(
        status=status,
        trigger=trigger,
        source=settings.MARKET_PRICE_SOURCE_NAME,
        records_fetched=fetched,
        records_stored=stored,
        message=message[:500] if message else None,
        synced_at=datetime.utcnow(),
    )
    db.add(sync)
    db.commit()
    return sync


def sync_from_source(
    db: Session,
    trigger: str = "api",
    force: bool = False,
    filters: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Fetch the latest AGMARKNET data via data.gov.in and store it.

    Throttled: a successful sync younger than MARKET_PRICE_REFRESH_MINUTES is
    returned from cache unless force=True (still min 60s between live calls).
    """
    last = (
        db.query(MarketDataSync)
        .filter(MarketDataSync.status == "success")
        .order_by(MarketDataSync.synced_at.desc())
        .first()
    )
    now = datetime.utcnow()
    if last and not force:
        age = now - last.synced_at
        if age < timedelta(minutes=settings.MARKET_PRICE_REFRESH_MINUTES):
            return {
                "ok": True,
                "cached": True,
                "synced_at": last.synced_at.isoformat(),
                "records_stored": last.records_stored,
                "message": f"Served from cache (synced {int(age.total_seconds() // 60)} minutes ago).",
            }
    if last and force and (now - last.synced_at) < timedelta(seconds=60):
        return {
            "ok": True,
            "cached": True,
            "synced_at": last.synced_at.isoformat(),
            "records_stored": last.records_stored,
            "message": "Refresh rate-limited. Showing the most recent sync.",
        }

    if not source_configured():
        _record_sync(
            db, "not_configured", trigger,
            "MARKET_PRICE_API_KEY is not configured on the server.",
        )
        return {
            "ok": False,
            "reason": "not_configured",
            "message": "Live market data source is not configured on the server.",
        }

    url = f"{settings.MARKET_PRICE_API_BASE_URL.rstrip('/')}/{settings.MARKET_PRICE_RESOURCE_ID}"
    params: Dict[str, Any] = {
        "api-key": settings.MARKET_PRICE_API_KEY,
        "format": "json",
        "limit": settings.MARKET_PRICE_FETCH_LIMIT,
    }
    for key, value in (filters or {}).items():
        if value:
            params[f"filters[{key}]"] = value

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code in (401, 403):
            message = "Market data source rejected the server API key."
        elif status_code == 429:
            message = "Market data source rate limit reached. Try again later."
        else:
            message = f"Market data source returned HTTP {status_code}."
        _record_sync(db, "failed", trigger, message)
        return {"ok": False, "reason": "http_error", "message": message}
    except httpx.HTTPError:
        _record_sync(db, "failed", trigger, "Could not reach the market data source (network error).")
        return {
            "ok": False,
            "reason": "network_error",
            "message": "Market data is temporarily unavailable (source unreachable).",
        }
    except Exception:
        _record_sync(db, "failed", trigger, "Unexpected error while contacting the market data source.")
        return {
            "ok": False,
            "reason": "error",
            "message": "Market data is temporarily unavailable.",
        }

    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        _record_sync(db, "failed", trigger, "Market data source returned an invalid response.")
        return {
            "ok": False,
            "reason": "invalid_response",
            "message": "Market data is temporarily unavailable (invalid source response).",
        }

    rows = [r for r in (transform_record(rec, settings.MARKET_PRICE_SOURCE_NAME) for rec in records) if r]
    stored = upsert_prices(db, rows) if rows else 0
    _record_sync(
        db, "success", trigger,
        f"Fetched {len(records)} records from AGMARKNET via data.gov.in.",
        fetched=len(records), stored=stored,
    )
    evaluate_alerts(db)
    return {
        "ok": True,
        "cached": False,
        "synced_at": datetime.utcnow().isoformat(),
        "records_fetched": len(records),
        "records_stored": stored,
        "message": f"Market data refreshed ({stored} new/updated records).",
    }


# ---------------------------------------------------------------------------
# Freshness metadata (honest live/latest/stale labels)
# ---------------------------------------------------------------------------

def freshness_info(db: Session) -> Dict[str, Any]:
    total = db.query(func.count(MarketPrice.id)).scalar() or 0
    latest_price_date = db.query(func.max(MarketPrice.price_date)).scalar()
    latest_fetch = db.query(func.max(MarketPrice.fetched_at)).scalar()
    last_sync = (
        db.query(MarketDataSync)
        .order_by(MarketDataSync.synced_at.desc())
        .first()
    )
    now = datetime.utcnow()

    data_available = total > 0
    is_live = bool(
        source_configured()
        and last_sync
        and last_sync.status == "success"
        and last_sync.synced_at
        and (now - last_sync.synced_at) < timedelta(minutes=settings.MARKET_PRICE_REFRESH_MINUTES)
    )
    stale = bool(
        latest_fetch and (now - latest_fetch) > timedelta(hours=settings.MARKET_PRICE_STALE_HOURS)
    )

    if not data_available:
        label = "unavailable"
    elif is_live:
        label = "live"
    elif stale:
        label = "stale"
    else:
        label = "latest"

    return {
        "data_available": data_available,
        "source_configured": source_configured(),
        "source": settings.MARKET_PRICE_SOURCE_NAME,
        "source_url": settings.MARKET_PRICE_SOURCE_URL,
        "label": label,
        "is_live": is_live,
        "may_be_outdated": stale,
        "total_records": total,
        "latest_price_date": latest_price_date,
        "last_fetch_timestamp": latest_fetch.isoformat() if latest_fetch else None,
        "last_sync": {
            "status": last_sync.status,
            "message": last_sync.message,
            "synced_at": last_sync.synced_at.isoformat() if last_sync and last_sync.synced_at else None,
            "records_stored": last_sync.records_stored,
        } if last_sync else None,
    }


# ---------------------------------------------------------------------------
# Price change computation (current vs previous comparable record)
# ---------------------------------------------------------------------------

def previous_price(db: Session, row: MarketPrice) -> Optional[MarketPrice]:
    q = db.query(MarketPrice).filter(
        MarketPrice.market == row.market,
        MarketPrice.commodity == row.commodity,
        MarketPrice.price_date < row.price_date,
        MarketPrice.modal_price.isnot(None),
    )
    if row.variety:
        q = q.filter(MarketPrice.variety == row.variety)
    else:
        q = q.filter(or_(MarketPrice.variety.is_(None), MarketPrice.variety == ""))
    return q.order_by(MarketPrice.price_date.desc()).first()


def compute_change(current: Optional[float], prev: Optional[float]) -> Dict[str, Any]:
    if current is None or prev is None:
        return {
            "available": False,
            "direction": None,
            "absolute": None,
            "percent": None,
            "previous_price": prev,
        }
    diff = current - prev
    pct = (diff / prev * 100) if prev else 0.0
    if abs(pct) < 0.5 and abs(diff) < 1:
        direction = "stable"
    elif diff > 0:
        direction = "up"
    else:
        direction = "down"
    return {
        "available": True,
        "direction": direction,
        "absolute": round(diff, 2),
        "percent": round(pct, 2),
        "previous_price": round(prev, 2),
    }


def price_to_dict(row: MarketPrice, change: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = {
        "id": row.id,
        "price_id": row.price_id,
        "commodity": row.commodity,
        "variety": row.variety,
        "grade": row.grade,
        "category": row.category or categorize_commodity(row.commodity),
        "market": row.market,
        "district": row.district,
        "state": row.state,
        "min_price": row.min_price,
        "max_price": row.max_price,
        "modal_price": row.modal_price,
        "unit": row.unit or "Rs/Quintal",
        "price_date": row.price_date,
        "arrival_date": row.arrival_date,
        "source": row.source,
        "source_url": row.source_url,
        "source_timestamp": row.source_timestamp,
        "last_updated": row.fetched_at.isoformat() if row.fetched_at else None,
    }
    if change is not None:
        data["change"] = change
    return data


# ---------------------------------------------------------------------------
# Alert evaluation (real events only)
# ---------------------------------------------------------------------------

def evaluate_alerts(db: Session, user_id: Optional[str] = None) -> int:
    """Check active alerts against the latest real prices; notify on trigger.

    Returns the number of alerts triggered. Called after every successful
    data sync/import (the backend has no separate scheduler process).
    """
    from app.models.market_price import MarketPriceAlert

    q = db.query(MarketPriceAlert).filter(MarketPriceAlert.status == "active")
    if user_id:
        q = q.filter(MarketPriceAlert.user_id == user_id)
    alerts = q.all()
    triggered = 0

    for alert in alerts:
        alert.last_checked_at = datetime.utcnow()
        sub = db.query(MarketPrice).filter(
            func.lower(MarketPrice.commodity) == alert.commodity.strip().lower(),
            MarketPrice.modal_price.isnot(None),
        )
        if alert.market:
            sub = sub.filter(func.lower(MarketPrice.market) == alert.market.strip().lower())
        latest_date = sub.with_entities(func.max(MarketPrice.price_date)).scalar()
        if not latest_date:
            continue
        rows = sub.filter(MarketPrice.price_date == latest_date).all()
        if not rows:
            continue

        if alert.condition == "above":
            match = max(rows, key=lambda r: r.modal_price or 0)
            hit = (match.modal_price or 0) >= alert.target_price
        else:
            match = min(rows, key=lambda r: r.modal_price or float("inf"))
            hit = (match.modal_price or 0) <= alert.target_price

        if hit:
            alert.status = "triggered"
            alert.last_triggered_at = datetime.utcnow()
            direction = "reached or exceeded" if alert.condition == "above" else "dropped to or below"
            create_notification(
                db=db,
                user_id=alert.user_id,
                title="Price Alert Triggered",
                message=(
                    f"{alert.commodity} at {match.market} {direction} your target of "
                    f"Rs {alert.target_price:,.0f}/{(match.unit or 'Rs/Quintal').replace('Rs/', '')}. "
                    f"Current modal price: Rs {match.modal_price:,.0f} ({match.price_date})."
                ),
                notification_type="market",
                reference_id=alert.alert_id,
                reference_type="market_price_alert",
                icon="fa-chart-line",
                action_url="market-prices.html",
            )
            triggered += 1

    db.commit()
    return triggered


# ---------------------------------------------------------------------------
# AI Market Overview (data-driven, honest by construction)
# ---------------------------------------------------------------------------

def _fmt_rupee(value: Optional[float]) -> str:
    if value is None or not isinstance(value, (int, float)):
        return "—"
    return f"₹{value:,.0f}"


def _overview_unit(unit: Optional[str]) -> str:
    return (unit or "Rs/Quintal").replace("Rs/", "").replace("-", "/") or "Quintal"


def _move_label(move: Dict[str, Any]) -> str:
    label = move.get("commodity") or "Unknown"
    if move.get("variety"):
        label += f" ({move['variety']})"
    return label


def build_market_overview(
    db: Session,
    query,
    scope: str = "all available data",
) -> Optional[Dict[str, Any]]:
    """Build a market analysis strictly from the stored official records.

    Never invents figures: every number in the returned text comes from the
    market_prices table. An optional AI provider (when a key is configured)
    may reword the summary/insight — the router applies that enhancement only
    on top of this honest, real-data baseline.
    Returns None when the given scope has no usable price records.
    """
    rows = query.limit(2000).all()
    if not rows:
        return None

    commodities: set = set()
    markets: set = set()
    latest_date: Optional[str] = None
    source_name: Optional[str] = None
    moves: List[Dict[str, Any]] = []
    for row in rows:
        if row.modal_price is None:
            continue
        commodities.add(row.commodity)
        markets.add(row.market or "Unknown")
        if source_name is None:
            source_name = row.source or settings.MARKET_PRICE_SOURCE_NAME
        if latest_date is None or (row.price_date and row.price_date > latest_date):
            latest_date = row.price_date
        prev = previous_price(db, row)
        change = compute_change(row.modal_price, prev.modal_price if prev else None)
        moves.append({
            "commodity": row.commodity,
            "variety": row.variety,
            "grade": row.grade,
            "market": row.market,
            "state": row.state,
            "modal_price": row.modal_price,
            "unit": row.unit or "Rs/Quintal",
            "price_date": row.price_date,
            "source": row.source,
            "change": change,
        })
    if not moves:
        return None

    rising = sorted(
        (m for m in moves if m["change"]["available"] and m["change"]["direction"] == "up"),
        key=lambda m: m["change"]["percent"] or 0,
        reverse=True,
    )
    falling = sorted(
        (m for m in moves if m["change"]["available"] and m["change"]["direction"] == "down"),
        key=lambda m: m["change"]["percent"] or 0,
    )
    steady = [m for m in moves if m["change"]["available"] and m["change"]["direction"] == "stable"]
    comparable = [m for m in moves if m["change"]["available"]]
    highest = max(moves, key=lambda m: m["modal_price"] or 0) if moves else None

    latest_label = str(latest_date) if latest_date else "the latest announcement"
    summary = (
        f"Current official prices for {len(commodities)} commodities across "
        f"{len(markets)} market(s) — {len(moves)} verified records as of "
        f"{latest_label} (source: {source_name}). Compared with the previous "
        f"announced season, {len(rising)} record(s) rose, {len(falling)} fell and "
        f"{len(steady)} were steady, out of {len(comparable)} comparable record(s) "
        f"in {scope}."
    )

    key_trends: List[str] = []
    if rising:
        top = rising[0]
        c = top["change"]
        unit = _overview_unit(top["unit"])
        key_trends.append(
            f"{_move_label(top)} at {top['market']} shows the largest official rise, "
            f"{_fmt_rupee(abs(c['absolute']))} ({(abs(c['percent'] or 0)):.1f}% higher) "
            f"to {_fmt_rupee(top['modal_price'])}/{unit}."
        )
    if falling:
        top = falling[0]
        c = top["change"]
        unit = _overview_unit(top["unit"])
        key_trends.append(
            f"{_move_label(top)} at {top['market']} shows the largest official fall, "
            f"{_fmt_rupee(abs(c['absolute']))} ({(abs(c['percent'] or 0)):.1f}% lower) "
            f"to {_fmt_rupee(top['modal_price'])}/{unit}."
        )
    if highest:
        unit = _overview_unit(highest["unit"])
        key_trends.append(
            f"Highest listed price in this scope: {_fmt_rupee(highest['modal_price'])}/"
            f"{unit} for {_move_label(highest)} at {highest['market']}."
        )
    if steady:
        key_trends.append(
            f"{len(steady)} record(s) were steady versus the previous season, "
            "signalling stable procurement prices."
        )
    if len(commodities) >= 3:
        key_trends.append(
            f"{len(commodities)} distinct commodities are covered, spanning "
            f"{len(markets)} market(s) in {scope}."
        )

    farmer_insight = (
        f"Before selling, open Compare Markets in the item details and rank mandis by "
        f"the latest published price for your crop. The figures above are official "
        f"announcements; the actual price you receive still depends on quality, "
        f"quantity and negotiation."
    )
    if rising:
        top = rising[0]
        c = top["change"]
        unit = _overview_unit(top["unit"])
        farmer_insight = (
            f"{_move_label(top)} is showing the strongest official movement in this view, "
            f"up {(abs(c['percent'] or 0)):.1f}% to {_fmt_rupee(top['modal_price'])}/{unit} "
            f"at {top['market']}. If you hold this crop, compare mandis before selling; "
            f"the final rate still depends on quality and negotiation."
        )
    elif falling:
        top = falling[0]
        c = top["change"]
        unit = _overview_unit(top["unit"])
        farmer_insight = (
            f"{_move_label(top)} at {top['market']} is down "
            f"{(abs(c['percent'] or 0)):.1f}% versus the previous season "
            f"({_fmt_rupee(top['modal_price'])}/{unit}). Check local demand before "
            f"finalising a sale, and compare mandis in the item details for the best "
            f"published rate."
        )

    return {
        "basis": {
            "scope": scope,
            "commodity_count": len(commodities),
            "market_count": len(markets),
            "record_count": len(moves),
            "unit": "Rs/Quintal",
            "latest_price_date": latest_date,
            "source": source_name,
        },
        "summary": summary,
        "key_trends": key_trends,
        "farmer_insight": farmer_insight,
        "rising": rising[:4],
        "falling": falling[:4],
        "steady_count": len(steady),
        "no_change_count": len(moves) - len(comparable),
    }
