"""Seed the market_prices table with VERIFIED official Government of India
Minimum Support Price (MSP) / Fair & Remunerative Price (FRP) data.

Every figure below is taken from the corresponding official Press Information
Bureau release (real source_urls) so the price cards, history chart, change
arrows and summary stats are all truthful. No prices, markets, sources,
timestamps or URLs are invented.

Protocol / honesty rules honoured by the rest of the app:
  - Live "AGMARKNET" daily mandi prices still need MARKET_PRICE_API_KEY in
    .env; until then the UI truthfully shows "Latest available official
    market data" (freshness label "latest") instead of a fake "Live" state.
  - The market column uses "All India (MSP)" so the national price scope is
    explicit; state/district remain NULL because MSP is a national figure,
    not a mandi record.

Usage:
    cd backend
    python seed_market_prices.py            # idempotent import
    python seed_market_prices.py --force    # re-import & re-evaluate alerts
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import SessionLocal, engine, Base  # noqa: E402
from app.models.market_price import MarketPrice, MarketDataSync  # noqa: E402
from app.services import market_price_service as svc  # noqa: E402

MINISTRY_SOURCE = "Ministry of Agriculture & Farmers Welfare (CCEA MSP)"

PIB_KHARIF_2026 = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2260618"
PIB_KHARIF_2025 = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2131983"
PIB_RABI_2026 = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2173566"
PIB_FRP_2025 = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2125471"

# (commodity, variety, modal_price_rs_per_quintal)
KHARIF_2026_27 = [
    ("Paddy", "Common", 2441), ("Paddy", "Grade A", 2461),
    ("Jowar", "Hybrid", 4023), ("Jowar", "Maldandi", 4073),
    ("Bajra", None, 2900), ("Ragi", None, 5205), ("Maize", None, 2410),
    ("Tur/Arhar", None, 8450), ("Moong", None, 8780), ("Urad", None, 8200),
    ("Groundnut", None, 7517), ("Sunflower Seed", None, 8343),
    ("Soybean (Yellow)", "Yellow", 5708), ("Sesamum", None, 10346),
    ("Nigerseed", None, 10052),
    ("Cotton", "Medium Staple", 8267), ("Cotton", "Long Staple", 8667),
]

KHARIF_2025_26 = [
    ("Paddy", "Common", 2369), ("Paddy", "Grade A", 2389),
    ("Jowar", "Hybrid", 3699), ("Jowar", "Maldandi", 3749),
    ("Bajra", None, 2775), ("Ragi", None, 4886), ("Maize", None, 2400),
    ("Tur/Arhar", None, 8000), ("Moong", None, 8768), ("Urad", None, 7800),
    ("Groundnut", None, 7263), ("Sunflower Seed", None, 7721),
    ("Soybean (Yellow)", "Yellow", 5328), ("Sesamum", None, 9846),
    ("Nigerseed", None, 9537),
    ("Cotton", "Medium Staple", 7710), ("Cotton", "Long Staple", 8110),
]

RABI_2026_27 = [
    ("Wheat", None, 2585), ("Barley", None, 2150),
    ("Gram", None, 5875), ("Lentil (Masur)", None, 7000),
    ("Rapeseed & Mustard", None, 6200), ("Safflower", None, 6540),
]

# Previous-year values referenced by the official Rabi 2026-27 release
# (announced 16 Oct 2024, corroborated by the PIB release table).
RABI_2025_26 = [
    ("Wheat", None, 2425), ("Barley", None, 1980),
    ("Gram", None, 5650), ("Lentil (Masur)", None, 6700),
    ("Rapeseed & Mustard", None, 5950), ("Safflower", None, 5940),
]

# Sugarcane FRP 2025-26 season @ basic recovery 10.25%
FRP_2025_26 = [
    ("Sugarcane", "10.25% recovery base", 355),
]

SEASONS = [
    # (label, price_date, list[(commodity, variety, modal)], source_url)
    ("Kharif 2026-27", "2026-05-13", KHARIF_2026_27, PIB_KHARIF_2026, "13 May 2026"),
    ("Kharif 2025-26", "2025-05-28", KHARIF_2025_26, PIB_KHARIF_2025, "28 May 2025"),
    ("Rabi 2026-27", "2025-10-01", RABI_2026_27, PIB_RABI_2026, "01 October 2025"),
    ("Rabi 2025-26", "2024-10-16", RABI_2025_26, PIB_RABI_2026, "16 October 2024"),
    ("FRP 2025-26 (Sugarcane)", "2025-04-30", FRP_2025_26, PIB_FRP_2025, "30 April 2025"),
]

MARKET = "All India (MSP)"


def build_rows():
    rows = []
    for label, price_date, entries, source_url, source_timestamp in SEASONS:
        for commodity, variety, modal in entries:
            rows.append({
                "commodity": commodity,
                "variety": variety,
                "grade": None,
                "category": svc.categorize_commodity(commodity),
                "market": MARKET,
                "district": None,
                "state": None,
                "min_price": None,
                "max_price": None,
                "modal_price": float(modal),
                "unit": "Rs/Quintal",
                "price_date": price_date,
                "arrival_date": None,
                "source": MINISTRY_SOURCE,
                "source_url": source_url,
                "source_timestamp": source_timestamp,
            })
    return rows


def import_msp_prices(db, force: bool = False) -> int:
    """Idempotent import of the verified MSP/FRP dataset.

    Returns the number of rows newly inserted (0 on a no-op re-run).
    Re-evaluates active alerts whenever data actually landed so farmers get
    truthful, immediate notifications.
    """
    Base.metadata.create_all(bind=engine)
    rows = build_rows()
    stored = svc.upsert_prices(db, rows)
    if stored or force:
        svc.evaluate_alerts(db)
        from app.utils.auth import generate_id
        sync = MarketDataSync(
            id=generate_id("FA-IDS", db, MarketDataSync),
            status="success",
            trigger="csv_import",
            source=MINISTRY_SOURCE,
            records_fetched=len(rows),
            records_stored=stored,
            message=f"Imported verified official MSP/FRP data ({len(rows)} rows).",
        )
        db.add(sync)
        db.commit()
    return stored


def main():
    force = "--force" in sys.argv
    db = SessionLocal()
    try:
        stored = import_msp_prices(db, force=force)
        total = db.query(MarketPrice).count()
        print(f"Market prices seeded: {stored} new rows. Total market_price rows: {total}.")
        if stored == 0 and not force:
            print("Nothing to import (verified MSP/FRP data already present).")
    finally:
        db.close()


if __name__ == "__main__":
    main()