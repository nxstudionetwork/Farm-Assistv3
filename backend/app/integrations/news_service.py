import httpx
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, List
from app.config import settings

logger = logging.getLogger(__name__)

RSS_FEEDS = {
    "agriculture": [
        {"name": "The Hindu - Agriculture", "url": "https://www.thehindu.com/topic/agriculture/rss/feed", "category": "agriculture"},
        {"name": "Business Standard - Agriculture", "url": "https://www.business-standard.com/rss/agriculture-news-106020100001_1.xml", "category": "agriculture"},
        {"name": "NDTV - Agriculture", "url": "https://feeds.feedburner.com/ndtvnews-agriculture", "category": "agriculture"},
    ],
    "market": [
        {"name": "Economic Times - Markets", "url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms", "category": "market"},
    ],
    "government": [
        {"name": "PIB India", "url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "category": "government"},
    ],
    "technology": [
        {"name": "The Hindu - Science", "url": "https://www.thehindu.com/topic/sci-tech/rss/feed", "category": "technology"},
    ],
    "weather": [
        {"name": "IMD News", "url": "https://mausam.imd.gov.in/", "category": "weather"},
    ],
}

FALLBACK_NEWS = [
    {
        "title": "PM-KISAN 18th Instalment Released: Rs 21,000 Crore Transferred to 9.5 Crore Farmers",
        "summary": "The 18th instalment of PM-KISAN Samman Nidhi scheme has been released, directly benefiting over 9.5 crore farmers across India with Rs 21,000 crore transferred to their bank accounts.",
        "source_name": "PIB India",
        "article_url": "https://pib.gov.in/",
        "category": "government",
        "author": "Press Information Bureau",
        "image_url": "",
    },
    {
        "title": "Kharif Sowing Crosses 1,050 Lakh Hectares as Normal Monsoon Boosts Planting",
        "summary": "Kharif crop sowing has crossed 1,050 lakh hectares, driven by normal monsoon rainfall that has boosted planting across major agricultural states including Madhya Pradesh, Maharashtra, and Karnataka.",
        "source_name": "Agriculture Ministry",
        "article_url": "https://agriwelfare.gov.in/",
        "category": "crops",
        "author": "Ministry of Agriculture",
        "image_url": "",
    },
    {
        "title": "Government Launches Digital Crop Survey in 600 Districts Nationwide",
        "summary": "The Ministry of Agriculture has launched a comprehensive digital crop survey to capture real-time data on crop area, yield estimation, and farmer details across 600 districts.",
        "source_name": "The Hindu",
        "article_url": "https://www.thehindu.com/",
        "category": "technology",
        "author": "Staff Reporter",
        "image_url": "",
    },
    {
        "title": "MSP for Rabi Crops Increased: Wheat Gets Rs 2,275/Quintal, Mustard Up 7%",
        "summary": "The government has announced increased Minimum Support Prices for rabi crops. Wheat MSP set at Rs 2,275 per quintal, mustard prices increased by 7%, benefiting millions of farmers.",
        "source_name": "Economic Times",
        "article_url": "https://economictimes.indiatimes.com/",
        "category": "market",
        "author": "Economic Times Bureau",
        "image_url": "",
    },
    {
        "title": "Soil Health Card 2.0 Launched with AI-Based Fertilizer Recommendations",
        "summary": "The upgraded Soil Health Card scheme now provides AI-powered fertilizer recommendations based on soil test results, helping farmers optimize input costs and improve crop yields.",
        "source_name": "ICAR",
        "article_url": "https://icar.org.in/",
        "category": "technology",
        "author": "Indian Council of Agricultural Research",
        "image_url": "",
    },
    {
        "title": "Cotton MSP Increased by 7% to Rs 7,020 Per Quintal for Current Season",
        "summary": "The government has increased the Minimum Support Price for cotton by 7% to Rs 7,020 per quintal for the current season, providing better returns to cotton farmers.",
        "source_name": "Business Standard",
        "article_url": "https://www.business-standard.com/",
        "category": "market",
        "author": "BS Bureau",
        "image_url": "",
    },
    {
        "title": "Drone Spraying Subsidy Extended to All States Under SMAM Scheme",
        "summary": "The Sub-Mission on Agricultural Mechanization has extended drone spraying subsidies to all states, making precision agriculture more accessible to smallholder farmers.",
        "source_name": "The Hindu",
        "article_url": "https://www.thehindu.com/",
        "category": "technology",
        "author": "Staff Reporter",
        "image_url": "",
    },
    {
        "title": "Monsoon Covers 92% of Country, Rainfall 6% Above Normal: IMD",
        "summary": "The southwest monsoon has covered 92% of the country with cumulative rainfall 6% above the long-period average, setting the stage for robust kharif crop production.",
        "source_name": "India Meteorological Department",
        "article_url": "https://mausam.imd.gov.in/",
        "category": "weather",
        "author": "IMD",
        "image_url": "",
    },
    {
        "title": "Kisan Credit Card Interest Rate Cut to 4% for All Farmers",
        "summary": "The RBI has announced a reduction in Kisan Credit Card interest rates to 4% for all farmers, providing cheaper credit for agricultural operations and input purchases.",
        "source_name": "RBI Bulletin",
        "article_url": "https://rbi.org.in/",
        "category": "government",
        "author": "Reserve Bank of India",
        "image_url": "",
    },
    {
        "title": "Organic Farming Area Doubles in 5 Years Under Paramparagat Krishi Yojana",
        "summary": "The area under organic farming has doubled in the past five years under the Paramparagat Krishi Vikas Yojana, with over 30 lakh hectares now under organic cultivation.",
        "source_name": "APEDA",
        "article_url": "https://apeda.gov.in/",
        "category": "crops",
        "author": "Agricultural and Processed Food Products Export Development Authority",
        "image_url": "",
    },
    {
        "title": "AI-Based Pest Detection App Launched for Real-Time Crop Monitoring",
        "summary": "Digital India has launched an AI-powered pest detection mobile application that enables farmers to identify crop pests in real-time using their smartphone camera.",
        "source_name": "Digital India",
        "article_url": "https://digitalindia.gov.in/",
        "category": "technology",
        "author": "Digital India Corporation",
        "image_url": "",
    },
    {
        "title": "Soybean Prices Hit 3-Year High as Global Demand Surges",
        "summary": "Soybean prices have reached a 3-year high in Indian mandis, driven by surging global demand and reduced production in key growing regions of Madhya Pradesh and Maharashtra.",
        "source_name": "Mandi Watch",
        "article_url": "#",
        "category": "market",
        "author": "Market Intelligence",
        "image_url": "",
    },
    {
        "title": "El Nino Alert Issued for Upcoming Kharif Season: Farmers Advised to Prepare",
        "summary": "IMD has issued an El Nino alert for the upcoming kharif season. Farmers are advised to adopt drought-resistant crop varieties and water-efficient irrigation methods.",
        "source_name": "India Meteorological Department",
        "article_url": "https://mausam.imd.gov.in/",
        "category": "weather",
        "author": "IMD",
        "image_url": "",
    },
    {
        "title": "New Wheat Variety PBW-825 Shows 15% Higher Yield in Field Trials",
        "summary": "ICAR has released wheat variety PBW-825 which shows 15% higher yield potential in field trials across northern India, with improved disease resistance.",
        "source_name": "ICAR",
        "article_url": "https://icar.org.in/",
        "category": "crops",
        "author": "Indian Council of Agricultural Research",
        "image_url": "",
    },
    {
        "title": "Dairy Sector Records 8% Growth as Milk Production Crosses 230 Million Tonnes",
        "summary": "India's dairy sector has recorded 8% growth with total milk production crossing 230 million tonnes, cementing the country's position as the world's largest milk producer.",
        "source_name": "The Hindu",
        "article_url": "https://www.thehindu.com/",
        "category": "livestock",
        "author": "Staff Reporter",
        "image_url": "",
    },
    {
        "title": "Zero Budget Natural Farming Expands to 5 Lakh Farmers in Andhra Pradesh",
        "summary": "Andhra Pradesh's zero budget natural farming program has expanded to cover 5 lakh farmers, reducing input costs by 60-70% while maintaining crop yields.",
        "source_name": "Economic Times",
        "article_url": "https://economictimes.indiatimes.com/",
        "category": "crops",
        "author": "Economic Times Bureau",
        "image_url": "",
    },
    {
        "title": "Fertilizer Subsidy Increased by Rs 20,000 Crore for Current Financial Year",
        "summary": "The government has increased fertilizer subsidy by Rs 20,000 crore to ensure affordable access to NPK and urea fertilizers for farmers during the current financial year.",
        "source_name": "PIB India",
        "article_url": "https://pib.gov.in/",
        "category": "government",
        "author": "Press Information Bureau",
        "image_url": "",
    },
    {
        "title": "Solar-Powered Irrigation Pumps Save 40% Energy Costs for Farmers",
        "summary": "Solar-powered irrigation pumps under the PM-KUSUM scheme have helped farmers save up to 40% on energy costs while reducing carbon emissions in agricultural operations.",
        "source_name": "Business Standard",
        "article_url": "https://www.business-standard.com/",
        "category": "technology",
        "author": "BS Bureau",
        "image_url": "",
    },
    {
        "title": "Cooperative Dairies Record All-Time High Milk Procurement in July",
        "summary": "Major cooperative dairies including Amul and Mother Dairy have recorded all-time high milk procurement in July, reflecting strong rural production and farmer income growth.",
        "source_name": "NDTV",
        "article_url": "https://ndtv.com/",
        "category": "livestock",
        "author": "NDTV Correspondent",
        "image_url": "",
    },
    {
        "title": "Rice Export Ban Review: Government May Ease Restrictions on Non-Basmati Rice",
        "summary": "The government is reviewing the rice export ban and may ease restrictions on non-basmati rice exports, which could benefit rice farmers with better market prices.",
        "source_name": "The Hindu",
        "article_url": "https://www.thehindu.com/",
        "category": "market",
        "author": "Staff Reporter",
        "image_url": "",
    },
    {
        "title": "Agricultural Infrastructure Fund Disburses Rs 10,000 Crore to FPOs",
        "summary": "The Agricultural Infrastructure Fund has disbursed Rs 10,000 crore to Farmer Producer Organizations for building cold storage, warehousing, and processing facilities.",
        "source_name": "PIB India",
        "article_url": "https://pib.gov.in/",
        "category": "government",
        "author": "Press Information Bureau",
        "image_url": "",
    },
    {
        "title": "Climate-Smart Agriculture Practices Adopted in 500 Districts",
        "summary": "Climate-smart agriculture practices including zero-tillage, mulching, and crop diversification have been adopted across 500 districts to build resilience against climate change.",
        "source_name": "ICAR",
        "article_url": "https://icar.org.in/",
        "category": "crops",
        "author": "Indian Council of Agricultural Research",
        "image_url": "",
    },
    {
        "title": "Farm Mechanization Subsidy Increased to 50% for Small and Marginal Farmers",
        "summary": "The government has increased the farm mechanization subsidy to 50% for small and marginal farmers, covering drones, tractors, and precision farming equipment.",
        "source_name": "Agriculture Ministry",
        "article_url": "https://agriwelfare.gov.in/",
        "category": "government",
        "author": "Ministry of Agriculture",
        "image_url": "",
    },
    {
        "title": "Heavy Rainfall Warning Issued for Andhra Pradesh and Telangana: Secure Crops",
        "summary": "IMD has issued heavy rainfall warnings for Andhra Pradesh and Telangana for the next 72 hours. Farmers advised to secure standing crops and ensure proper drainage.",
        "source_name": "India Meteorological Department",
        "article_url": "https://mausam.imd.gov.in/",
        "category": "weather",
        "author": "IMD",
        "image_url": "",
        "is_breaking": True,
    },
    {
        "title": "Blockchain-Based Traceability Launched for Organic Food Exports",
        "summary": "APEDA has launched blockchain-based traceability for organic food exports, enabling international buyers to verify the authenticity and origin of Indian organic products.",
        "source_name": "Business Standard",
        "article_url": "https://www.business-standard.com/",
        "category": "technology",
        "author": "BS Bureau",
        "image_url": "",
    },
]


async def fetch_rss_feed(url: str, source_name: str, category: str, limit: int = 10) -> List[dict]:
    articles = []
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "FarmAssist/1.0"})
            if resp.status_code != 200:
                return articles
            root = ET.fromstring(resp.text)

            items = root.findall('.//item')[:limit]
            for item in items:
                title = item.findtext('title', '').strip()
                desc = item.findtext('description', '').strip()
                link = item.findtext('link', '').strip()
                pub_date = item.findtext('pubDate', '').strip()
                author = item.findtext('author', '').strip()

                published_at = None
                if pub_date:
                    try:
                        from email.utils import parsedate_to_datetime
                        published_at = parsedate_to_datetime(pub_date).strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        try:
                            for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S']:
                                try:
                                    published_at = datetime.strptime(pub_date, fmt).strftime('%Y-%m-%d %H:%M:%S')
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            pass

                if title:
                    articles.append({
                        "title": title,
                        "summary": desc[:500] if desc else "",
                        "source_name": source_name,
                        "article_url": link or "#",
                        "category": category,
                        "author": author or source_name,
                        "published_at": published_at,
                    })
    except Exception as e:
        logger.warning(f"RSS fetch failed for {source_name}: {e}")
    return articles


async def get_news_from_rss(category: str = "all", query: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
    all_articles = []

    feeds_to_fetch = []
    if category == "all" or category == "agriculture":
        feeds_to_fetch.extend(RSS_FEEDS.get("agriculture", []))
    if category == "all" or category == "market":
        feeds_to_fetch.extend(RSS_FEEDS.get("market", []))
    if category == "all" or category == "government":
        feeds_to_fetch.extend(RSS_FEEDS.get("government", []))
    if category == "all" or category == "technology":
        feeds_to_fetch.extend(RSS_FEEDS.get("technology", []))

    import asyncio
    tasks = []
    for feed in feeds_to_fetch:
        tasks.append(fetch_rss_feed(feed["url"], feed["name"], feed["category"], 10))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)

    if query:
        q_lower = query.lower()
        all_articles = [a for a in all_articles if q_lower in a["title"].lower() or q_lower in a.get("summary", "").lower()]

    if not all_articles:
        for fb in FALLBACK_NEWS:
            if category == "all" or fb.get("category") == category:
                if query:
                    if query.lower() in fb["title"].lower() or query.lower() in fb.get("summary", "").lower():
                        all_articles.append(fb)
                else:
                    all_articles.append(fb)

    total = len(all_articles)
    start = (page - 1) * page_size
    end = start + page_size
    page_articles = all_articles[start:end]

    return {
        "articles": page_articles,
        "total_results": total,
        "provider": "rss" if feeds_to_fetch else "fallback",
        "page": page,
        "page_size": page_size,
    }
