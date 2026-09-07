"""
News fetching service.

Fetches real agriculture and general news from public RSS feeds (no API keys
required), normalizes entries into a common dictionary shape, and optionally
falls back to the NewsAPI.org endpoint when NEWS_API_KEY is configured.

No mock/placeholder data is ever produced by this module. If a source fails it
is skipped; only successfully parsed real articles are returned.
"""

import hashlib
import re
import socket
from datetime import datetime, timezone
from typing import Dict, List, Optional

import feedparser
import requests

from app.config import settings

# Blocked / unreliable sources that frequently break or go offline are listed
# here so the fetcher never wastes time on them.
_BLOCKED = {"nytimes"}

# A constant user-agent avoids being rejected by many CDNs.
_UA = "Mozilla/5.0 (compatible; FarmAssistNews/1.0; +https://farmassist.local)"

# Normalized source metadata. url is the RSS feed URL. attribution is the
# human-facing outlet name. lang is the primary language. region defaults to
# "India" unless a more specific one is given.
SOURCES: List[Dict] = [
    {
        "name": "the_hindu_business",
        "url": "https://www.thehindubusinessline.com/agriculture/feeder/default.rss",
        "attribution": "The Hindu Business Line",
        "lang": "en",
        "region": "India",
        "category": "market",
    },
    {
        "name": "the_hindu",
        "url": "https://www.thehindu.com/news/national/feeder/default.rss",
        "attribution": "The Hindu",
        "lang": "en",
        "region": "India",
        "category": "general",
    },
    {
        "name": "economic_times",
        "url": "https://economictimes.indiatimes.com/rssfeeds/6291879.cms?catid=12091476",
        "attribution": "Economic Times Agriculture",
        "lang": "en",
        "region": "India",
        "category": "market",
    },
    {
        "name": "business_standard_agri",
        "url": "https://www.business-standard.com/rss/markets/commodities-101.rss",
        "attribution": "Business Standard",
        "lang": "en",
        "region": "India",
        "category": "market",
    },
    {
        "name": "time_of_india",
        "url": "https://timesofindia.indiatimes.com/rssfeeds/1221656.cms",
        "attribution": "Times of India",
        "lang": "en",
        "region": "India",
        "category": "general",
    },
    {
        "name": "business_today",
        "url": "https://www.businesstoday.in/rss/feeds/agri/",
        "attribution": "Business Today",
        "lang": "en",
        "region": "India",
        "category": "market",
    },
    {
        "name": "krishak_jagat",
        "url": "https://www.krishakjagat.org/feed/",
        "attribution": "Krishak Jagat",
        "lang": "hi",
        "region": "India",
        "category": "general",
    },
    {
        "name": "hindustan_agri",
        "url": "https://www.hindustantimes.com/feeds/rss/agriculture/rssfeed.xml",
        "attribution": "Hindustan Times",
        "lang": "en",
        "region": "India",
        "category": "general",
    },
    {
        "name": "future_farming",
        "url": "https://www.futurefarming.com/feed/",
        "attribution": "Future Farming",
        "lang": "en",
        "region": "Global",
        "category": "technology",
    },
    {
        "name": "ag_funder",
        "url": "https://agfundernews.com/feed",
        "attribution": "AFN (AgFunderNews)",
        "lang": "en",
        "region": "Global",
        "category": "technology",
    },
    {
        "name": "usa_agri",
        "url": "https://www.agri-pulse.com/rss/",
        "attribution": "Agri-Pulse",
        "lang": "en",
        "region": "Global",
        "category": "government",
    },
]

# Agriculture relevance keywords. An article is kept only if its title/summary/
# content contains one of these (case-insensitive), so the feed stays focused on
# farming and agriculture rather than general world/politics/celebrity news.
_AGRI_RELEVANCE = {
    "farm", "farmer", "farmers", "farming", "agriculture", "agricultural",
    "agri", "crop", "crops", "harvest", "sowing", "monsoon", "irrigation",
    "fertilizer", "fertiliser", "pesticide", "pesticides", "soil", "manure",
    "seed", "seeds", "yield", "agronom", "horticulture", "plantation",
    "organic farming", "agro", "mandi", "pm-kisan", "kisan", "krishi",
    "agri-pulse", "agricultural news", "plantation", "agroforestry",
    "livestock", "cattle", "poultry", "dairy", "goat", "sheep", "fishery",
    "fisheries", "aquaculture", "sericulture", "apiary", "beekeeping",
    "wheat", "rice", "paddy", "maize", "corn", "sugarcane", "cotton",
    "pulses", "soybean", "groundnut", "mustard", "millet", "oilseed",
    "vegetable", "vegetables", "fruit", "fruits", "spice", "spices",
    "commodity", "commodities", "foodgrain", "food grain", "grains",
    "harvesting", "plough", "tractor", "greenhouse", "green house",
    "drip", "mulch", "weeding", "grafting", "nursery", "reap", "reaping",
}

# Keyword -> category heuristic applied when a feed does not declare one.
# Order matters: the first matching keyword wins, so put the most specific /
# dominant topics first so crops aren't mis-labelled as "general".
_CATEGORY_KEYWORDS = {
    # Machinery & equipment (check before generic "farm")
    "tractor": "machinery", "harvester": "machinery", "tillage": "machinery",
    "machinery": "machinery", "equipment": "machinery", "drone": "machinery",
    "sprayer": "machinery", "implements": "machinery", "mechanisation": "machinery",
    "mechanization": "machinery", "robotics": "machinery",
    # Irrigation & water management
    "irrigation": "irrigation", "drip": "irrigation", "water": "irrigation",
    "sprinkler": "irrigation", "canal": "irrigation", "aquifer": "irrigation",
    "groundwater": "irrigation", "drought": "irrigation",
    # Soil & fertilizer
    "soil": "soil", "fertilizer": "soil", "fertiliser": "soil",
    "manure": "soil", "compost": "soil", "nutrient": "soil",
    "micronutrient": "soil", "urea": "soil", "nematicide": "soil",
    # Seeds & planting material
    "seed": "seeds", "seeds": "seeds", "seedling": "seeds", "sowing": "seeds",
    "planting": "seeds", "nursery": "seeds", "variety": "seeds",
    "hybrid": "seeds", "germination": "seeds",
    # Pests & crop protection
    "pest": "crops", "pesticide": "crops", "insect": "crops", "fungus": "crops",
    "disease": "crops", "weed": "crops", "plant protection": "crops",
    # Crops & harvest & yield
    "crop": "crops", "crops": "crops", "harvest": "crops", "harvesting": "crops",
    "yield": "crops", "wheat": "crops", "rice": "crops", "paddy": "crops",
    "maize": "crops", "corn": "crops", "sugarcane": "crops", "cotton": "crops",
    "pulses": "crops", "soybean": "crops", "groundnut": "crops", "mustard": "crops",
    "millet": "crops", "oilseed": "crops", "vegetable": "crops",
    "vegetables": "crops", "fruit": "crops", "fruits": "crops", "horticulture": "crops",
    # Weather & climate (broad) — check after specific crop/irrigation terms
    "monsoon": "weather", "weather": "weather", "rainfall": "weather",
    "climate": "weather", "temperature": "weather", "heatwave": "weather",
    "cold wave": "weather", "unseasonal": "weather", "hailstorm": "weather",
    "forecast": "weather", "el nino": "weather", "la nina": "weather",
    # Livestock & dairy
    "livestock": "livestock", "cattle": "livestock", "poultry": "livestock",
    "dairy": "livestock", "cow": "livestock", "buffalo": "livestock",
    "goat": "livestock", "sheep": "livestock", "fishery": "livestock",
    "fisheries": "livestock", "aquaculture": "livestock", "sericulture": "livestock",
    "apiculture": "livestock", "beekeeping": "livestock", "animal husbandry": "livestock",
    # Government, schemes & policy
    "subsidy": "government", "scheme": "government", "policy": "government",
    "government": "government", "pm-kisan": "government", "pmfby": "government",
    "msp": "government", "procurement": "government", "mandate": "government",
    "parliament": "government", "finance minister": "government", "budget": "government",
    "agreement": "government", "regulatory": "government",
    # Markets, prices, exports, finance
    "price": "market", "market": "market", "mandi": "market", "export": "market",
    "import": "market", "commodity": "market", "commodities": "market",
    "trading": "market", "futures": "market", "spike": "market", "rates": "market",
    "rupee": "market", "tender": "market", "demand": "market",
    # Agri technology & innovation
    "technology": "technology", "agritech": "technology", "agri-tech": "technology",
    "precision": "technology", "data": "technology", "digital": "technology",
    "app": "technology", "artificial intelligence": "technology", "robot": "technology",
    "innovation": "technology", "startup": "technology", "start-up": "technology",
    "satellite": "technology", "iot": "technology", "vertical farming": "technology",
    # Sustainable / organic farming
    "organic": "sustainability", "sustainable": "sustainability",
    "regenerative": "sustainability", "agroforestry": "sustainability",
    "biodiversity": "sustainability", "carbon": "sustainability",
    "emissions": "sustainability", "eco": "sustainability", "permaculture": "sustainability",
}

# State names used to detect region. We prefer explicit region metadata; where
# a feed is generic "India" we try to refine from article text.
_STATES = [
    "Andhra Pradesh", "Telangana", "Tamil Nadu", "Karnataka", "Kerala",
    "Maharashtra", "Gujarat", "Rajasthan", "Punjab", "Haryana", "Uttar Pradesh",
    "Madhya Pradesh", "Bihar", "West Bengal", "Odisha", "Assam", "Chattisgarh",
    "Chhattisgarh", "Jharkhand", "Goa",
]

_BREAKING_WORDS = ["breaking", "live", "urgent", "alert", "flash"]

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"\s+")


def _sanitize_image_url(url: Optional[str]) -> Optional[str]:
    """Return a real http(s) image URL, or None when it isn't usable.

    Only genuine remote image URLs are kept (no data-URIs, no empty strings).
    Many CDN image URLs carry no extension, so we don't require one.
    """
    if not url:
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://", "//")):
        return None
    if url.startswith("//"):
        url = "https:" + url
    if url.lower().startswith("data:"):
        return None
    # Drop obvious favicons and tracking pixels / tiny placeholders.
    if any(ext in url.lower() for ext in (".ico", ".svg", "favicon", "pixel", "track")):
        return None
    return url



_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

def _looks_latin(text: Optional[str]) -> bool:
    """True when text is predominantly Latin script (English/etc.), not Devanagari."""
    if not text:
        return True
    dev = len(_DEVANAGARI_RE.findall(text))
    total = sum(1 for ch in text if ch.isalpha())
    if total == 0:
        return True
    # If >15% of alphabetic chars are Devanagari it's a non-English (Hindi) item.
    return (dev / total) <= 0.15


_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',
    re.IGNORECASE,
)
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

def _extract_og_image(article_url: str, timeout: int = 8) -> Optional[str]:
    """Fetch the live article page and pull its real primary image (og:image).

    This lets every news card use a genuine image straight from the source
    outlet, even when the RSS feed omits an image from its metadata.
    """
    if not article_url or not article_url.startswith(("http://", "https://")):
        return None
    try:
        resp = requests.get(
            article_url,
            headers={"User-Agent": _UA, "Accept": "text/html,*/*"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception:
        return None

    for pattern in (_OG_IMAGE_RE, _OG_IMAGE_RE2):
        m = pattern.search(html)
        if m:
            url = _sanitize_image_url(m.group(1))
            if url:
                return url
    # Fall back to the first reasonably sized <img> on the page.
    for m in _IMG_SRC_RE.finditer(html):
        url = _sanitize_image_url(m.group(1))
        if url:
            return url
    return None


# Explicitly non-agriculture topics. If a title/summary mentions any of these
# it is dropped, even if it also contains an agriculture keyword. This keeps
# the feed free of stock/defence/banking/auto/entertainment clutter that leaks
# through general-news mirrors.
_NON_AGRI = {
    "share price", "sharemarket", "stock price", "defence psu", "bpsu",
    "hdfc bank", "sbi", "pnb", "icici", "axis bank", "kotak", "rbl", "federal bank",
    "credit score", "ipo", "mutual fund", "sensex", "nifty", "bullion",
    "cricket", "bollywood", "movie", "film", "celebrity", "netflix", "ott",
    "gold price", "silver price", "crude price", "fuel price", "cng price",
    "ev ", "electric car", "gym", "fitness", "real estate", "property market",
    "bse", "nse", "shares", "stock", "dividend", "insurance premium",
    "etechnical", "manufacturing deflator", "bond yield", "bharat cell",
}

# A small set of known noise domains whose content is unreliable/mislabeled.
_BLOCKED_FEEDS = {
    "business_today",  # its "agri" feed returns general business/share news
    "time_of_india",   # general city feed, not agriculture-dedicated
    "krishak_jagat",   # Hindi-only outlet; disable to keep the feed English
    "the_hindu",       # a general national-news feed, not agriculture-dedicated
}


def _clean_html(raw: Optional[str]) -> str:
    if not raw:
        return ""
    text = _HTML_TAG_RE.sub(" ", raw)
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def _hash_key(feed_name: str, link: str, title: str) -> str:
    base = f"{feed_name}:{link}:{title}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _guess_category(text: str) -> str:
    low = text.lower()
    for kw, cat in _CATEGORY_KEYWORDS.items():
        if kw in low:
            return cat
    return "general"


def _guess_region(text: str, default_region: str) -> Optional[str]:
    if default_region and default_region != "India":
        return default_region if default_region != "Global" else None
    for state in _STATES:
        if state.lower() in text.lower():
            return state
    # Fall back to "India" for feeds marked India unless clearly global.
    if default_region == "India":
        return "India"
    return None


def _is_breaking(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in _BREAKING_WORDS)


def _is_agri_relevant(text: str) -> bool:
    """Return True if the article text is about farming/agriculture."""
    low = text.lower()
    return any(kw in low for kw in _AGRI_RELEVANCE)


def _parse_date(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        # feedparser returns time.struct_time tuples; build tz-aware UTC.
        if hasattr(value, "tm_year"):
            dt = datetime(value.tm_year, value.tm_mon, value.tm_mday,
                          value.tm_hour, value.tm_min, value.tm_sec,
                          tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        if isinstance(value, str):
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        pass
    return None


def _fetch_feed(source: Dict, timeout: int = 12) -> List[Dict]:
    """Fetch and normalize one RSS feed into article dicts."""
    try:
        headers = {"User-Agent": _UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"}
        resp = requests.get(source["url"], headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.content)
    except Exception:
        return []

    if feed.bozo and not getattr(feed, "entries", None):
        return []

    articles: List[Dict] = []
    seen = set()
    for entry in feed.get("entries", []):
        title = _clean_html(getattr(entry, "title", ""))
        link = getattr(entry, "link", "") or ""
        if not title:
            continue

        description = _clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        content_text = ""
        raw_content = ""
        if getattr(entry, "content", None):
            try:
                raw_content = entry.content[0].get("value", "")
                content_text = _clean_html(raw_content)
            except Exception:
                content_text = ""
        if not content_text:
            raw_content = raw_content or (getattr(entry, "summary", "") or getattr(entry, "description", "") or "")
            content_text = _clean_html(raw_content)

        # dedupe within this feed
        dedupe = _hash_key(source["name"], link, title)
        if dedupe in seen:
            continue
        seen.add(dedupe)

        # media / enclosure image
        image_url = None
        media = getattr(entry, "media_content", None)
        if media:
            try:
                candidates = [m for m in media if m.get("url")]
                if candidates:
                    image_url = candidates[0]["url"]
            except Exception:
                image_url = None
        if not image_url and getattr(entry, "media_thumbnail", None):
            try:
                image_url = entry.media_thumbnail[0].get("url")
            except Exception:
                image_url = None
        # enclosure (many RSS feeds put the image here)
        if not image_url and getattr(entry, "enclosures", None):
            try:
                for enc in entry.enclosures:
                    href = enc.get("href") or enc.get("url") or ""
                    typ = enc.get("type") or ""
                    if "image" in typ or href.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                        image_url = href
                        break
            except Exception:
                image_url = image_url
        # fall back to the first <img> inside the content HTML for feeds that
        # embed images there rather than in the standard media fields.
        if not image_url and content_text:
            try:
                m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_content)
                if m:
                    image_url = m.group(1)
            except Exception:
                image_url = image_url
        image_url = _sanitize_image_url(image_url)

        author = getattr(entry, "author", None) or getattr(entry, "creator", None)
        if author:
            author = _clean_html(author)

        combined = f"{title}. {description} {content_text}".strip()
        # Keep the feed focused on farming and agriculture: drop clearly
        # unrelated articles coming in via the general-news mirrors.
        if not _is_agri_relevant(combined):
            continue
        low_combined = combined.lower()
        if any(bad in low_combined for bad in _NON_AGRI):
            continue
        # Prefer English content for the app UI.
        if source.get("lang", "en") == "en" and not _looks_latin(combined):
            continue
        # Prefer content-based category guessing for a richer, more accurate
        # agriculture taxonomy; fall back to the feed's declared category only
        # when the content doesn't hint at anything more specific.
        guessed = _guess_category(combined)
        category = guessed if guessed != "general" else (source.get("category") or "general")
        # Every card must show a real image taken from the news source. When the
        # RSS/embed/media fields produced nothing, fetch the live article page
        # and pull its primary image (og:image); drop the item if none is found
        # so no static placeholder is ever used.
        if not image_url:
            image_url = _extract_og_image(link)
            if not image_url:
                continue
        image_url = _sanitize_image_url(image_url)
        if not image_url:
            continue
        region = _guess_region(combined, source.get("region"))
        breaking = _is_breaking(title)
        published = _parse_date(getattr(entry, "published_parsed", None) or
                                getattr(entry, "updated_parsed", None))

        articles.append({
            "external_id": _hash_key(source["name"], link, title),
            "title": title,
            "summary": (description or content_text or "")[:500],
            "content": (content_text or description or ""),
            "image_url": image_url,
            "source_name": source["attribution"],
            "source_url": source["url"],
            "article_url": link,
            "author": author,
            "category": category,
            "region": region,
            "is_breaking": breaking,
            "published_at": published,
            "lang": source.get("lang", "en"),
        })
    return articles


def fetch_all_sources(timeout: int = 12, max_per_source: int = 25) -> List[Dict]:
    """Fetch all configured RSS sources and return a flat list of articles."""
    all_articles: List[Dict] = []
    for source in SOURCES:
        if source["name"] in _BLOCKED:
            continue
        if source["name"] in _BLOCKED_FEEDS:
            continue
        try:
            items = _fetch_feed(source, timeout=timeout)
        except Exception:
            items = []
        # trim to the newest N per source
        if len(items) > max_per_source:
            items = items[:max_per_source]
        all_articles.extend(items)
    return all_articles


def fetch_from_newsapi(query: str = "agriculture India", page_size: int = 30) -> List[Dict]:
    """Optional NewsAPI.org fallback. Returns [] when no key configured."""
    if not settings.NEWS_API_KEY:
        return []
    try:
        url = f"{settings.NEWS_API_BASE_URL}/everything"
        params = {
            "q": query,
            "pageSize": page_size,
            "sortBy": "publishedAt",
            "language": "en",
            "apiKey": settings.NEWS_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=12)
        if resp.status_code != 200:
            return []
        data = resp.json().get("articles", [])
    except Exception:
        return []

    results = []
    for a in data:
        title = _clean_html(a.get("title") or "")
        if not title:
            continue
        source_name = (a.get("source") or {}).get("name") or "News API"
        link = a.get("url") or ""
        published = a.get("publishedAt")
        pub_dt = _parse_date(published) if published else None

        combined = f"{title}. {a.get('description') or ''} {a.get('content') or ''}"
        if not _is_agri_relevant(combined):
            continue
        if any(bad in combined.lower() for bad in _NON_AGRI):
            continue
        if not _looks_latin(combined):
            continue
        category = _guess_category(combined)
        image = _sanitize_image_url(a.get("urlToImage")) or _extract_og_image(link)
        if not image:
            continue
        results.append({
            "external_id": hashlib.sha256(f"newsapi:{link}:{title}".encode("utf-8")).hexdigest(),
            "title": title,
            "summary": _clean_html(a.get("description") or "")[:500],
            "content": _clean_html(a.get("content") or "") or _clean_html(a.get("description") or ""),
            "image_url": image,
            "source_name": source_name,
            "source_url": None,
            "article_url": link,
            "author": a.get("author"),
            "category": category,
            "region": None,
            "is_breaking": _is_breaking(title),
            "published_at": pub_dt,
            "lang": "en",
        })
    return results


def fetch_news(include_newsapi: bool = True, timeout: int = 12) -> List[Dict]:
    """Stub helper that adds connectivity guard before fetching."""
    articles = fetch_all_sources(timeout=timeout)
    if include_newsapi:
        articles.extend(fetch_from_newsapi())
    return articles
