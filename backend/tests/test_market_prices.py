import os
import sys

_test_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_market_prices.db")
if os.path.exists(_test_db):
    os.remove(_test_db)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import engine, Base, SessionLocal
from app.models import *
from seed_market_prices import import_msp_prices

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db(db):
    Base.metadata.create_all(bind=engine)
    import_msp_prices(db)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def register(client, name, phone):
    resp = client.post("/api/v1/auth/register", json={
        "full_name": name,
        "email": f"{name.lower().replace(' ', '')}@market.test",
        "phone_number": phone,
        "password": "Password@123",
        "role": "farmer",
    })
    assert resp.status_code in (200, 201), resp.text
    token = resp.json()["data"].get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def headers_a():
    return register(client, "Farmer A", "9110000001")


@pytest.fixture
def headers_b():
    return register(client, "Farmer B", "9110000002")


def test_requires_auth():
    assert client.get("/api/v1/market-prices/summary").status_code == 401
    assert client.get("/api/v1/market-prices?category=paddy").status_code == 401


def test_summary_reporting_real_data(headers_a):
    resp = client.get("/api/v1/market-prices/summary", headers=headers_a)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["freshness"]["data_available"] is True
    assert data["tracked_commodities"] >= 18
    assert data["markets_covered"] == 1
    assert data["highest_increase"] is not None
    assert data["highest_increase"]["change"]["percent"] > 0
    assert data["highest_increase"]["change"]["available"] is True
    assert data["latest_price_date"]


def test_list_filters_by_category(headers_a):
    resp = client.get("/api/v1/market-prices?category=paddy", headers=headers_a)
    data = resp.json()["data"]
    items = data["items"]
    assert data["total"] == 2
    assert data["sort"] == "recent"
    assert all(i["category"] == "Paddy" for i in items)
    common = next(i for i in items if i["variety"] == "Common")
    assert common["commodity"] == "Paddy"
    assert common["market"] == "All India (MSP)"
    assert common["modal_price"] == 2441.0
    assert common["change"]["available"] is True
    assert common["change"]["absolute"] == 72
    assert common["change"]["previous_date"] == "2025-05-28"


def test_list_sort_highest_lowest(headers_a):
    by_price = client.get(
        "/api/v1/market-prices?category=paddy&sort=highest",
        headers=headers_a,
    ).json()["data"]["items"]
    by_lowest = client.get(
        "/api/v1/market-prices?category=paddy&sort=lowest",
        headers=headers_a,
    ).json()["data"]["items"]
    assert by_price[0]["variety"] == "Grade A"
    assert by_price[1]["variety"] == "Common"
    assert by_lowest[0]["variety"] == "Common"
    assert by_lowest[1]["variety"] == "Grade A"


def test_oilseeds_categorization(headers_a):
    resp = client.get("/api/v1/market-prices?category=oilseeds", headers=headers_a)
    items = resp.json()["data"]["items"]
    commodities = {i["commodity"] for i in items}
    assert len(items) >= 5
    assert {"Sesamum", "Nigerseed", "Sunflower Seed"}.issubset(commodities)


def test_commodities_endpoint_lists_and_searches(headers_a):
    resp = client.get("/api/v1/market-prices/commodities", headers=headers_a)
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = [c["name"].lower() for c in data["commodities"]]
    assert "paddy" in names and "sesamum" in names
    assert all(c["name"] and c["category"] for c in data["commodities"])

    resp = client.get("/api/v1/market-prices/commodities", params={"q": "sesam"}, headers=headers_a)
    hits = [c["name"].lower() for c in resp.json()["data"]["commodities"]]
    assert "sesamum" in hits and len(hits) < len(names)

    resp = client.get("/api/v1/market-prices/commodities", params={"q": "zzzz-no-match"}, headers=headers_a)
    assert resp.json()["data"]["commodities"] == []


def test_detail_carries_verified_source(headers_a):
    listed = client.get("/api/v1/market-prices?category=paddy", headers=headers_a).json()["data"]["items"]
    resp = client.get(f"/api/v1/market-prices/{listed[0]['id']}", headers=headers_a)
    det = resp.json()["data"]
    assert det["price_id"]
    assert "pib.gov.in" in det["source_url"]
    assert det["source"]
    assert det["unit"] == "Rs/Quintal"
    assert det["change"]["previous_date"] == "2025-05-28"


def test_history_spans_verified_seasons(headers_a):
    resp = client.get(
        "/api/v1/market-prices/history",
        params={"commodity": "Paddy", "market": "All India (MSP)", "variety": "Common", "days": 730},
        headers=headers_a,
    )
    data = resp.json()["data"]
    assert [p["date"] for p in data["points"]] == ["2025-05-28", "2026-05-13"]
    assert data["points"][1]["modal_price"] == 2441.0
    assert data["points"][0]["modal_price"] == 2369.0


def test_history_recent_window_has_single_point(headers_a):
    resp = client.get(
        "/api/v1/market-prices/history",
        params={"commodity": "Paddy", "market": "All India (MSP)", "days": 180},
        headers=headers_a,
    )
    points = resp.json()["data"]["points"]
    assert len(points) == 1
    assert points[0]["date"] == "2026-05-13"


def test_compare_markets(headers_a):
    resp = client.get(
        "/api/v1/market-prices/compare",
        params={"commodity": "Paddy"},
        headers=headers_a,
    )
    data = resp.json()["data"]
    assert data["market_count"] == 2
    assert data["average"] == 2451.0
    assert data["highest"]["variety"] == "Grade A"
    assert data["lowest"]["variety"] == "Common"
    assert "Highest listed market price" in data["disclaimer"]


def test_search(headers_a):
    resp = client.get("/api/v1/market-prices/search", params={"q": "whea"}, headers=headers_a)
    assert "Wheat" in resp.json()["data"]["commodities"]
    data = resp.json()["data"]
    assert all("whea" in c.lower() for c in data["commodities"])


def test_recommended_empty_profile(headers_a):
    resp = client.get("/api/v1/market-prices/recommended", headers=headers_a)
    data = resp.json()["data"]
    assert data["available"] is False
    assert data["items"] == []
    assert "farm details" in data["reason"].lower()


def test_watchlist_isolation(headers_a, headers_b):
    add = client.post(
        "/api/v1/market-prices/watchlist",
        json={"commodity": "Paddy", "market": "All India (MSP)"},
        headers=headers_a,
    )
    assert add.status_code in (200, 201)
    watch_id = add.json()["data"]["watch_id"]
    latest = add.json()["data"]["latest_price"]
    assert latest["modal_price"] in (2441.0, 2461.0)

    wa = client.get("/api/v1/market-prices/watchlist", headers=headers_a).json()["data"]
    wb = client.get("/api/v1/market-prices/watchlist", headers=headers_b).json()["data"]
    assert wa["total"] == 1
    assert wb["total"] == 0

    dup = client.post(
        "/api/v1/market-prices/watchlist",
        json={"commodity": "Paddy", "market": "All India (MSP)"},
        headers=headers_a,
    )
    assert dup.status_code == 409

    gone = client.delete(f"/api/v1/market-prices/watchlist/{watch_id}", headers=headers_a)
    assert gone.status_code == 200
    assert client.get("/api/v1/market-prices/watchlist", headers=headers_a).json()["data"]["total"] == 0


def test_alert_triggers_and_notifies_only_owner(headers_a, headers_b):
    resp = client.post(
        "/api/v1/market-prices/alerts",
        json={"commodity": "Paddy", "target_price": 2000, "condition": "above"},
        headers=headers_a,
    )
    assert resp.status_code in (200, 201)
    alert = resp.json()["data"]
    assert alert["status"] == "triggered"
    assert alert["last_triggered_at"]

    na = client.get("/api/v1/notifications", headers=headers_a).json()["data"]
    alerted = [n for n in na["items"] if "Price Alert Triggered" in n.get("title", "")]
    assert len(alerted) >= 1
    assert alerted[0]["notification_type"] == "market"

    nb = client.get("/api/v1/notifications", headers=headers_b).json()["data"]
    assert not any("Price Alert Triggered" in n.get("title", "") for n in nb["items"])

    forge = client.delete(f"/api/v1/market-prices/alerts/{alert['alert_id']}", headers=headers_b)
    assert forge.status_code == 404
    owner = client.delete(f"/api/v1/market-prices/alerts/{alert['alert_id']}", headers=headers_a)
    assert owner.status_code == 200


def test_refresh_without_api_key_is_honest(headers_a):
    resp = client.post("/api/v1/market-prices/refresh", headers=headers_a)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["freshness"]["data_available"] is True
    assert "cache" in data["refresh"]["message"].lower()


def test_ai_overview_built_from_real_data(headers_a):
    resp = client.get("/api/v1/market-prices/ai-overview", headers=headers_a)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["available"] is True
    assert data["insufficient"] is False
    assert data["model"] in ("data-driven", "openai", "gemini", "claude")
    assert data["generated_at"]
    assert data["basis"]["commodity_count"] >= 18
    assert data["basis"]["market_count"] == 1
    assert data["summary"]
    assert data["key_trends"]
    assert data["farmer_insight"]
    assert isinstance(data["rising"], list)
    assert isinstance(data["falling"], list)
    for move in data["rising"] + data["falling"]:
        assert move["modal_price"] > 0
        assert move["change"]["percent"] is not None


def test_ai_overview_respects_filters(headers_a):
    resp = client.get(
        "/api/v1/market-prices/ai-overview",
        params={"category": "paddy"},
        headers=headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["available"] is True
    assert "paddy" in data["basis"]["scope"].lower()
    assert all("Paddy" in m["commodity"] for m in data["rising"] + data["falling"])


def test_ai_overview_unfiltered_search_no_match(headers_a):
    resp = client.get(
        "/api/v1/market-prices/ai-overview",
        params={"q": "no-such-crop-xyz"},
        headers=headers_a,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["available"] is False
    assert data["insufficient"] is True
    assert "Not enough current market data" in data["message"]


def test_location_cascade_filters_districts_and_markets(headers_a, db):
    from app.models.market_price import MarketPrice
    db.add_all([
        MarketPrice(commodity="Paddy", variety="Common", market="Nalgonda Market", district="Nalgonda", state="Telangana", modal_price=2400.0, unit="Rs/Quintal", price_date="2026-05-20", source="AGMARKNET demo"),
        MarketPrice(commodity="Paddy", variety="Common", market="Khammam Market", district="Khammam", state="Telangana", modal_price=2450.0, unit="Rs/Quintal", price_date="2026-05-20", source="AGMARKNET demo"),
        MarketPrice(commodity="Paddy", variety="Common", market="Guntur Market", district="Guntur", state="Andhra Pradesh", modal_price=2380.0, unit="Rs/Quintal", price_date="2026-05-20", source="AGMARKNET demo"),
    ])
    db.commit()

    resp = client.get("/api/v1/market-prices/markets", headers=headers_a)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "Telangana" in data["states"] and "Andhra Pradesh" in data["states"]
    # The filter supports the complete official India State/UT list (36).
    for official in ("Telangana", "Maharashtra", "Rajasthan", "Delhi", "Puducherry"):
        assert official in data["states"]

    resp = client.get("/api/v1/market-prices/markets", params={"state": "Telangana"}, headers=headers_a)
    data = resp.json()["data"]
    # Districts merge the official master for the chosen State/UT with the
    # districts present in the data, and never include another state's
    # districts.
    assert data["districts"][0] == "Adilabad"
    assert "Hyderabad" in data["districts"]
    assert "Khammam" in data["districts"] and "Nalgonda" in data["districts"]
    assert "Guntur" not in data["districts"]

    resp = client.get("/api/v1/market-prices/markets", params={"state": "Telangana", "district": "Nalgonda"}, headers=headers_a)
    data = resp.json()["data"]
    assert data["markets"] == ["Nalgonda Market"]

    # A State/UT with no market data still lists its official districts and
    # simply returns no markets ("All States/Districts" honoured).
    resp = client.get("/api/v1/market-prices/markets", params={"state": "Puducherry"}, headers=headers_a)
    data = resp.json()["data"]
    assert data["districts"] == ["Karaikal", "Mahe", "Puducherry", "Yanam"]
    assert data["markets"] == []


def test_location_cascade_returns_regions(headers_a, db):
    from app.models.market_price import MarketPrice
    db.add_all([
        MarketPrice(commodity="Paddy", variety="Common", market="Kodad Market", district="Nalgonda", state="Telangana", region="Kodad", modal_price=2600.0, unit="Rs/Quintal", price_date="2026-05-20", source="AGMARKNET demo"),
        MarketPrice(commodity="Paddy", variety="Common", market="Suryapeta Market", district="Nalgonda", state="Telangana", region="Suryapeta", modal_price=2750.0, unit="Rs/Quintal", price_date="2026-05-20", source="AGMARKNET demo"),
        MarketPrice(commodity="Paddy", variety="Common", market="Nalgonda Market", district="Nalgonda", state="Telangana", region="Nalgonda", modal_price=2650.0, unit="Rs/Quintal", price_date="2026-05-20", source="AGMARKNET demo"),
        MarketPrice(commodity="Paddy", variety="Common", market="Pune APMC", district="Pune", state="Maharashtra", region="Haveli", modal_price=6000.0, unit="Rs/Quintal", price_date="2026-05-20", source="AGMARKNET demo"),
    ])
    db.commit()

    resp = client.get("/api/v1/market-prices/markets", params={"state": "Telangana"}, headers=headers_a)
    data = resp.json()["data"]
    assert "Kodad" in data["regions"]
    assert "Haveli" not in data["regions"]

    resp = client.get("/api/v1/market-prices/markets", params={"state": "Telangana", "district": "Nalgonda"}, headers=headers_a)
    data = resp.json()["data"]
    assert set(data["regions"]) == {"Kodad", "Nalgonda", "Suryapeta"}
    assert data["markets"] == ["Kodad Market", "Nalgonda Market", "Suryapeta Market"]

    resp = client.get("/api/v1/market-prices/markets", params={"state": "Maharashtra", "district": "Pune", "region": "Haveli"}, headers=headers_a)
    data = resp.json()["data"]
    assert data["markets"] == ["Pune APMC"]

    resp = client.get("/api/v1/market-prices/search", params={"q": "havel"}, headers=headers_a)
    assert "Haveli" in resp.json()["data"]["regions"]


def test_list_filters_by_region(headers_a, db):
    from app.models.market_price import MarketPrice
    db.add_all([
        MarketPrice(commodity="Paddy", variety="Common", market="Kodad Market", district="Nalgonda", state="Telangana", region="Kodad", modal_price=2600.0, unit="Rs/Quintal", price_date="2026-05-21", source="AGMARKNET demo"),
        MarketPrice(commodity="Paddy", variety="Common", market="Choutuppal Market", district="Nalgonda", state="Telangana", region="Choutuppal", modal_price=2750.0, unit="Rs/Quintal", price_date="2026-05-21", source="AGMARKNET demo"),
        MarketPrice(commodity="Onion", variety="Onion", market="Siddipet", district="Siddipet", state="Telangana", region="Siddipet", modal_price=4500.0, unit="Rs/Quintal", price_date="2026-05-21", source="AGMARKNET demo"),
    ])
    db.commit()

    resp = client.get("/api/v1/market-prices", params={"state": "Telangana", "region": "Kodad"}, headers=headers_a)
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["market"] == "Kodad Market"
    assert data["items"][0]["region"] == "Kodad"


def test_compare_markets_scoped_to_region(headers_a, db):
    from app.models.market_price import MarketPrice
    db.add_all([
        MarketPrice(commodity="Paddy", variety="Common", market="Kodad Market", district="Nalgonda", state="Telangana", region="Kodad", modal_price=2600.0, unit="Rs/Quintal", price_date="2026-05-21", source="AGMARKNET demo"),
        MarketPrice(commodity="Paddy", variety="Common", market="Choutuppal Market", district="Nalgonda", state="Telangana", region="Choutuppal", modal_price=2750.0, unit="Rs/Quintal", price_date="2026-05-21", source="AGMARKNET demo"),
    ])
    db.commit()

    resp = client.get(
        "/api/v1/market-prices/compare",
        params={"commodity": "Paddy", "state": "Telangana", "region": "Kodad"},
        headers=headers_a,
    )
    data = resp.json()["data"]
    assert data["market_count"] == 1
    assert data["markets"][0]["region"] == "Kodad"