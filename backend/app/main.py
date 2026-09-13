import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError

# Ensure log/stream handlers never crash on currency symbols (₹) under a
# non-UTF-8 Windows console (charmap codec). Alternative encodings degrade to '?'.
for _stream in (sys.stdout, sys.stderr):
    try:
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .config import settings
from .database.connection import engine, Base
from .utils.exceptions import AppException



import app.models

from .routers import (
    auth, users, farms, crops, finance, workers,
    marketplace, government, community, notifications,
    weather, maps, ai, ai_chat,
    loans, loan_products, sensors, storage, news, translation, qrcode, analytics,
    services, farmbuzz, messages, support, feedback, wallet, documents,
    learning, techniques, emergency, market_prices,
    insurance, calendar, input_store, tools_equipment,
    marketplace_seller,
)


from app.middleware.security import SecurityHeadersMiddleware, RateLimitMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Farm Assist - Complete Agriculture Super App Backend",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)

if settings.RATE_LIMIT_ENABLED:
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(farms.router)
app.include_router(crops.router)
app.include_router(finance.router)
app.include_router(workers.router)
app.include_router(marketplace.router)
app.include_router(marketplace_seller.router)
app.include_router(input_store.router)
app.include_router(government.router)
app.include_router(community.router)
app.include_router(notifications.router)
app.include_router(weather.router)
app.include_router(maps.router)
app.include_router(ai.router)
app.include_router(ai_chat.router)
app.include_router(loan_products.router)
app.include_router(loans.router)
app.include_router(insurance.router)
app.include_router(sensors.router)
app.include_router(storage.router)
app.include_router(news.router)
app.include_router(translation.router)
app.include_router(qrcode.router)
app.include_router(analytics.router)
app.include_router(services.router)
app.include_router(farmbuzz.router)
app.include_router(messages.router)
app.include_router(support.router)
app.include_router(feedback.router)
app.include_router(wallet.router)
app.include_router(documents.router)
app.include_router(learning.router)
app.include_router(techniques.router)
app.include_router(emergency.router)
app.include_router(market_prices.router)
app.include_router(calendar.router)
app.include_router(tools_equipment.router, prefix="/api/equipment")
app.include_router(tools_equipment.router, prefix="/api/v1/tools-equipment")



@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        loc = " -> ".join(str(l) for l in error["loc"])
        errors.append({"field": loc, "message": error["msg"]})
    return JSONResponse(
        status_code=422,
        content={"success": False, "detail": "Validation error", "errors": errors},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"success": False, "detail": "Internal server error"},
    )


@app.on_event("startup")
async def startup():
    from app.database.schema_upgrade import run_additive_migrations
    Base.metadata.create_all(bind=engine)
    run_additive_migrations(settings.DATABASE_URL)
    os.makedirs(settings.STORAGE_LOCAL_PATH, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    from app.database.connection import SessionLocal
    from app.database.seed_communities import seed_communities
    from app.database.seed_community_demo import seed_demo
    db = SessionLocal()
    try:
        created = seed_communities(db)
        demo_summary = seed_demo(db)

        from app.database.seed_marketplace import seed_marketplace_categories
        mkt_seeded = seed_marketplace_categories(db)

        from sqlalchemy import func
        from app.models.market_price import MarketPrice
        has_market_data = db.query(func.count(MarketPrice.id)).scalar() or 0
        market_seeded = 0
        eq_summary = None
        if not has_market_data:
            try:
                from seed_market_prices import import_msp_prices
            except ImportError:
                _backend_dir = Path(__file__).resolve().parent.parent
                if str(_backend_dir) not in sys.path:
                    sys.path.insert(0, str(_backend_dir))
                from seed_market_prices import import_msp_prices
            market_seeded = import_msp_prices(db)

        from app.models.marketplace import EquipmentMetadata
        has_equipment = db.query(func.count(EquipmentMetadata.id)).scalar() or 0
        if not has_equipment:
            from app.database.seed_equipment import seed_equipment
            eq_summary = seed_equipment(db)
    finally:
        db.close()

    print(f"{settings.APP_NAME} v{settings.APP_VERSION} started. DB tables created.")
    if created:
        print(f"Seeded {created} community groups.")
    if demo_summary and not demo_summary.get("skipped"):
        print(f"Seeded demo community feed: {demo_summary.get('posts')} posts, "
              f"{demo_summary.get('comments')} comments, {demo_summary.get('answers')} answers, "
              f"{demo_summary.get('likes')} likes, {demo_summary.get('saves')} saves.")
    if market_seeded:
        print(f"Seeded {market_seeded} verified market price records (official MSP/FRP).")
    if mkt_seeded:
        print(f"Seeded marketplace sell categories (created {mkt_seeded['categories_created']}, total {mkt_seeded['total']}).")
    if eq_summary:
        print(f"Seeded {eq_summary['products_seeded']} tools & equipment products and {eq_summary['rentals_seeded']} rental machinery.")



@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "services": {
            "weather": bool(settings.WEATHER_API_KEY or settings.WEATHER_API_PROVIDER == "open-meteo"),
            "ai": {"openai": bool(settings.OPENAI_API_KEY), "gemini": bool(settings.GEMINI_API_KEY), "claude": bool(settings.ANTHROPIC_API_KEY), "local": True},
            "maps": bool(settings.GOOGLE_MAPS_API_KEY),
            "email": bool(settings.SMTP_HOST and settings.SMTP_USER),
            "sms": bool(settings.SMS_API_KEY),
        },
    }


@app.get("/api/v1/integrations/status")
async def integrations_status():
    from app.integrations.ai_providers import AIProviderManager
    return {
        "status": "success",
        "data": {
            "ai": AIProviderManager.get_status(),
            "weather": {"provider": settings.WEATHER_API_PROVIDER, "configured": True},
            "maps": {"configured": bool(settings.GOOGLE_MAPS_API_KEY)},
            "news": {"configured": bool(settings.NEWS_API_KEY)},
            "translation": {"configured": bool(settings.TRANSLATION_API_KEY)},
            "speech": {"configured": bool(settings.SPEECH_API_KEY)},
            "storage": {"backend": settings.STORAGE_BACKEND},
        },
    }


@app.get("/api/v1/locations/states")
def get_states():
    from app.routers.auth import LOCATIONS
    states = []
    for state_name, districts in LOCATIONS.items():
        states.append({"name": state_name, "district_count": len(districts)})
    return {"status": "success", "data": states}


@app.get("/api/v1/locations/districts/{state}")
def get_districts(state: str):
    from app.routers.auth import LOCATIONS
    state_key = None
    for k in LOCATIONS:
        if k.lower() == state.lower():
            state_key = k
            break
    if not state_key:
        return {"status": "success", "data": []}
    districts = []
    for dist_name, mandals in LOCATIONS[state_key].items():
        districts.append({"name": dist_name, "mandal_count": len(mandals)})
    return {"status": "success", "data": districts}


@app.get("/api/v1/locations/mandals/{state}/{district}")
def get_mandals(state: str, district: str):
    from app.routers.auth import LOCATIONS
    state_key = None
    for k in LOCATIONS:
        if k.lower() == state.lower():
            state_key = k
            break
    if not state_key:
        return {"status": "success", "data": []}
    dist_key = None
    for k in LOCATIONS[state_key]:
        if k.lower() == district.lower():
            dist_key = k
            break
    if not dist_key:
        return {"status": "success", "data": []}
    mandals = []
    for mandal_name, villages in LOCATIONS[state_key][dist_key].items():
        mandals.append({"name": mandal_name, "village_count": len(villages)})
    return {"status": "success", "data": mandals}


@app.get("/api/v1/locations/villages/{state}/{district}/{mandal}")
def get_villages(state: str, district: str, mandal: str):
    from app.routers.auth import LOCATIONS
    state_key = None
    for k in LOCATIONS:
        if k.lower() == state.lower():
            state_key = k
            break
    if not state_key:
        return {"status": "success", "data": []}
    dist_key = None
    for k in LOCATIONS[state_key]:
        if k.lower() == district.lower():
            dist_key = k
            break
    if not dist_key:
        return {"status": "success", "data": []}
    mandal_key = None
    for k in LOCATIONS[state_key][dist_key]:
        if k.lower() == mandal.lower():
            mandal_key = k
            break
    if not mandal_key:
        return {"status": "success", "data": []}
    villages = [{"name": v} for v in LOCATIONS[state_key][dist_key][mandal_key]]
    return {"status": "success", "data": villages}


# Uploads are served only through the authenticated, ownership-checked
# /api/v1/storage/* endpoints. No public static mount is registered to avoid
# bypassing authorization or exposing private files (documents, message
# attachments, etc.).

frontend_dir = Path(__file__).parent.parent.parent / "frontend"
if frontend_dir.exists():

    @app.get("/consultations")
    @app.get("/consultations/")
    @app.get("/consultations.html")
    async def old_consultations_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/expert.html", status_code=301)

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dir / "index.html")
