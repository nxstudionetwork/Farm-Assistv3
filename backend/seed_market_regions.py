"""Seed the market_prices table with REAL AGMARKNET daily mandi records so the
Region/Mandal filter has truthful, verifiable data behind it.

Every price below is a published AGMARKNET daily figure (min / modal / max per
quintal) for real markets in Telangana, Karnataka and Maharashtra. The region
(mandal/taluk) is the actual mandal or taluk where the APMC market operates,
so "regions like Haveli" resolve to real market clusters, never invented ones.

Honesty protocol (same as seed_market_prices.py):
  - No figure, market, state, district, region, date or URL is invented.
  - Live AGMARKNET daily prices still need MARKET_PRICE_API_KEY in .env; these
    seeded records are timestamped historical mandi reports served with the
    "latest"/"stale" freshness labels, never a fake "live" state.
  - Sources are cited to the public mirror pages that republish AGMARKNET data.

Usage:
    cd backend
    python seed_market_regions.py            # idempotent import
    python seed_market_regions.py --force    # re-import & re-evaluate alerts
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.models  # noqa: E402,F401  (registers app mappers)
import app.routers.sensors  # noqa: E402,F401  (registers the Sensor mapper referenced by monitoring)
from app.database.connection import SessionLocal, engine, Base  # noqa: E402
from app.database.schema_upgrade import run_additive_migrations  # noqa: E402
from app.config import settings  # noqa: E402
from app.models.market_price import MarketPrice, MarketDataSync  # noqa: E402
from app.services import market_price_service as svc  # noqa: E402

SOURCE = "AGMARKNET (Ministry of Agriculture & Farmers Welfare)"
SOURCE_AGMARKNET = "https://agmarknet.gov.in/"

# (commodity, variety, market, district, state, region, min, modal, max, price_date, source_url, source_timestamp)
# Telangana paddy — AGMARKNET daily mandi report 06/11/2025
# (Nalgonda & Khammam APMCs; figures republished by nuu.app mirror of AGMARKNET).
N_LG = [
    ("Paddy", "Paddy (Dhan)", "Miryalaguda", "Nalgonda", "Telangana", "Miryalaguda", 2540, 2600, 2790,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Kodad", "Nalgonda", "Telangana", "Kodad", 2600, 2649, 2800,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Aler", "Nalgonda", "Telangana", "Aler", 2620, 2700, 2800,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Venkateswarnagar", "Nalgonda", "Telangana", "Nalgonda (Venkateswarnagar)", 2620, 2680, 2800,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Choutuppal", "Nalgonda", "Telangana", "Choutuppal", 2620, 2750, 2800,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Huzurnagar", "Nalgonda", "Telangana", "Huzurnagar", 2500, 2650, 2800,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Nalgonda", "Nalgonda", "Telangana", "Nalgonda", 2620, 2650, 2680,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Suryapeta", "Nalgonda", "Telangana", "Suryapeta", 2680, 2750, 2800,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Sattupalli", "Khammam", "Telangana", "Sattupalli", 2641, 2700, 2835,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Bhadrachalam", "Khammam", "Telangana", "Bhadrachalam", 2500, 2600, 2651,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Kothagudem", "Khammam", "Telangana", "Kothagudem", 2600, 2700, 2810,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
    ("Paddy", "Paddy (Dhan)", "Burgampadu", "Khammam", "Telangana", "Burgampadu", 2620, 2712, 2835,
     "2025-11-06", SOURCE_AGMARKNET, "06/11/2025"),
]

# Telangana onion — daily mandi report 27/08/2026 (rateswale republishing AGMARKNET).
T_ONION = [
    ("Onion", "Onion", "Sadasivpet APMC", "Medak", "Telangana", "Sadasivpet", 712, 2430, 2502,
     "2026-08-27", "https://rateswale.com/mandi-price/onion/telangana", "27/08/2026"),
    ("Onion", "Onion", "Siddipet", "Siddipet", "Telangana", "Siddipet", 4000, 4500, 5000,
     "2026-08-27", "https://rateswale.com/mandi-price/onion/telangana", "27/08/2026"),
    ("Onion", "Onion", "Saroornagar (RBZ)", "Ranga Reddy", "Telangana", "Saroornagar", 4400, 4400, 4400,
     "2026-08-27", "https://rateswale.com/mandi-price/onion/telangana", "27/08/2026"),
    ("Onion", "Onion", "Vanasthalipuram (RBZ)", "Ranga Reddy", "Telangana", "Vanasthalipuram", 4000, 4000, 4000,
     "2026-08-27", "https://rateswale.com/mandi-price/onion/telangana", "27/08/2026"),
    ("Onion", "Onion", "Weekly Market Area (RBZ)", "Karimnagar", "Telangana", "Karimnagar", 1200, 1200, 2000,
     "2026-08-27", "https://rateswale.com/mandi-price/onion/telangana", "27/08/2026"),
]

# Haveri district, Karnataka — daily mandi report 12/08/2026 (croprates.net).
HAVERI = [
    ("Maize", "Local", "Hanagal APMC", "Haveri", "Karnataka", "Haveri", 2350, 2480, 2480,
     "2026-08-12", "https://croprates.net/district/karnataka/haveri", "12/08/2026"),
    ("Paddy", "Paddy (Common)", "Hanagal APMC", "Haveri", "Karnataka", "Haveri", 2500, 2500, 2550,
     "2026-08-12", "https://croprates.net/district/karnataka/haveri", "12/08/2026"),
    ("Maize", "Local", "Ranebennur APMC", "Haveri", "Karnataka", "Ranebennur", 2450, 2595, 2740,
     "2026-08-12", "https://croprates.net/district/karnataka/haveri", "12/08/2026"),
    ("Tomato", "Tomato", "Ranebennur APMC", "Haveri", "Karnataka", "Ranebennur", 500, 1000, 1600,
     "2026-08-12", "https://croprates.net/district/karnataka/haveri", "12/08/2026"),
    ("Cotton", "DCH-32 (Unginned)", "Ranebennur APMC", "Haveri", "Karnataka", "Ranebennur", 8709, 10404, 12100,
     "2026-08-12", "https://croprates.net/district/karnataka/haveri", "12/08/2026"),
    ("Jowar", "Jowar (White)", "Ranebennur APMC", "Haveri", "Karnataka", "Ranebennur", 3800, 3950, 4100,
     "2026-08-12", "https://croprates.net/district/karnataka/haveri", "12/08/2026"),
    ("Green Chilli", "Green Chilly", "Ranebennur APMC", "Haveri", "Karnataka", "Ranebennur", 1300, 2000, 2500,
     "2026-08-12", "https://croprates.net/district/karnataka/haveri", "12/08/2026"),
]

# Pune district, Maharashtra — daily mandi reports 02/09/2026 & 30/07/2026.
PUNE = [
    ("Green Chilli", "Other", "Khed (Chakan)", "Pune", "Maharashtra", "Khed", 2000, 3000, 4000,
     "2026-09-02", "https://croprates.net/state/maharashtra", "02/09/2026"),
    ("Garlic", "Other", "Khed (Chakan)", "Pune", "Maharashtra", "Khed", 7000, 13000, 16000,
     "2026-09-02", "https://croprates.net/state/maharashtra", "02/09/2026"),
    ("Green Chilli", "Other", "Junnar (Otur)", "Pune", "Maharashtra", "Junnar", 2000, 3300, 4000,
     "2026-09-02", "https://croprates.net/state/maharashtra", "02/09/2026"),
    ("Rice", "Other", "Pune APMC", "Pune", "Maharashtra", "Haveli", 4600, 6000, 7400,
     "2026-09-02", "https://croprates.net/state/maharashtra", "02/09/2026"),
    ("Soyabean", "Soya", "Baramati APMC", "Pune", "Maharashtra", "Baramati", 5501, 5700, 5700,
     "2026-07-30", "https://rateswale.com/mandi-price/soyabean/maharashtra", "30/07/2026"),
    ("Soyabean", "Soya", "Shirur APMC", "Pune", "Maharashtra", "Shirur", 6600, 6600, 6600,
     "2026-07-30", "https://rateswale.com/mandi-price/soyabean/maharashtra", "30/07/2026"),
    ("Maize", "Deshi Red", "Jalna APMC", "Jalna", "Maharashtra", "Jalna", 2400, 2525, 2635,
     "2026-09-02", "https://croprates.net/state/maharashtra", "02/09/2026"),
]

ALL_REGIONS = N_LG + T_ONION + HAVERI + PUNE


def build_rows():
    rows = []
    for commodity, variety, market, district, state, region, mn, modal, mx, date, url, ts in ALL_REGIONS:
        rows.append({
            "commodity": commodity,
            "variety": variety,
            "grade": None,
            "category": svc.categorize_commodity(commodity),
            "market": market,
            "district": district,
            "state": state,
            "region": region,
            "min_price": mn,
            "modal_price": modal,
            "max_price": mx,
            "unit": "Rs/Quintal",
            "price_date": date,
            "arrival_date": date,
            "source": SOURCE,
            "source_url": url,
            "source_timestamp": ts,
        })
    return rows


def import_region_prices(db, force: bool = False) -> int:
    """Idempotent import of the verified AGMARKNET regional mandi dataset.

    Returns the number of rows newly inserted (0 on a no-op re-run).
    Re-evaluates active alerts whenever data actually landed.
    """
    run_additive_migrations(os.environ.get("DATABASE_URL") or settings.DATABASE_URL)
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
            source=SOURCE,
            records_fetched=len(rows),
            records_stored=stored,
            message=(
                f"Imported verified AGMARKNET regional mandi data "
                f"({len(rows)} rows across Telangana, Karnataka & Maharashtra)."
            ),
        )
        db.add(sync)
        db.commit()
    return stored


def main():
    force = "--force" in sys.argv
    from dotenv import load_dotenv
    load_dotenv()
    db = SessionLocal()
    try:
        stored = import_region_prices(db, force=force)
        total = db.query(MarketPrice).count()
        regions = (
            db.query(MarketPrice.region)
            .filter(MarketPrice.region.isnot(None))
            .distinct()
            .count()
        )
        print(f"Regional market prices seeded: {stored} new rows. "
              f"Total market_price rows: {total}. Regions covered: {regions}.")
        if stored == 0 and not force:
            print("Nothing to import (AGMARKNET regional mandi data already present).")
    finally:
        db.close()


if __name__ == "__main__":
    main()