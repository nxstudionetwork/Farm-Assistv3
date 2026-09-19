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
    marketplace_seller, monitoring, livestock, soil_irrigation,
    crop_health, marketplace_browse,
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
app.include_router(marketplace_browse.router)
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
app.include_router(monitoring.router)
app.include_router(tools_equipment.router, prefix="/api/equipment")
app.include_router(tools_equipment.router, prefix="/api/v1/tools-equipment")
app.include_router(livestock.router)
app.include_router(soil_irrigation.router)
app.include_router(crop_health.router)



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
    from sqlalchemy.exc import OperationalError
    import time

    def _run_seed_suite():
        db = SessionLocal()
        try:
            from app.database.restore_historical_accounts import ensure_historical_accounts
            restore_summary = ensure_historical_accounts(db)

            from app.database.seed_demo_login import ensure_demo_login_user
            demo_login = ensure_demo_login_user(db)

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

            # Tools & Equipment rich catalogue (18-category taxonomy, BUY + RENT).
            # The standalone seeder is idempotent; only run it when the taxonomy
            # categories are still empty so startup stays fast on existing DBs.
            from app.models.marketplace import Product, ProductCategory
            from app.equipment_taxonomy import CATEGORY_SLUGS as _TAX_SLUGS
            tools_catalogue_rows = (
                db.query(func.count(Product.id))
                .join(ProductCategory, Product.category_id == ProductCategory.id)
                .filter(ProductCategory.slug.in_(_TAX_SLUGS), Product.is_active == True)  # noqa: E712
                .scalar()
                or 0
            )
            tools_summary = None
            if tools_catalogue_rows < 400:
                from app.database.seed_tools_equipment import seed as seed_tools_catalogue
                tools_summary = seed_tools_catalogue(db)

            from app.input_store_taxonomy import INPUT_STORE_SLUGS
            from app.models.marketplace import Product, ProductCategory
            input_products = (
                db.query(func.count(Product.id))
                .join(ProductCategory, Product.category_id == ProductCategory.id)
                .filter(ProductCategory.slug.in_(INPUT_STORE_SLUGS), Product.is_active == True)  # noqa: E712
                .scalar()
                or 0
            )
            input_summary = None
            if input_products < 400:
                from app.database.seed_input_store import seed as seed_input_store
                input_summary = seed_input_store(db)

            from app.database.seed_soil_irrigation import seed_soil_irrigation_demo
            soil_summary = seed_soil_irrigation_demo(db)

            from app.database.seed_workers import seed_workers as seed_worker_catalogue
            workers_summary = seed_worker_catalogue(db)

            from app.database.seed_sensor_devices import seed_sensor_devices
            sensor_catalogue = seed_sensor_devices(db)

            # Content catalogue (farm techniques, learning courses, experts hub,
            # government schemes, insurance products). Each seeder is idempotent
            # and restores the full published catalogue on every boot so a fresh
            # or wiped database never leaves these pages empty.
            from app.models.community import Expert
            from app.models.insurance import InsuranceProduct

            from app.database.seed_techniques import seed_techniques as _seed_techniques
            techniques_summary = _seed_techniques(db)

            from app.database.seed_learning import seed_learning as _seed_learning
            learning_summary = _seed_learning(db)

            from app.database.seed_experts import seed_experts as _seed_experts
            experts_summary = {"created": _seed_experts(db), "total": db.query(Expert).count()}

            from app.database.seed_schemes import seed as _seed_schemes
            schemes_summary = _seed_schemes(db)

            from app.database.seed_insurance_products import seed_insurance_products as _seed_insurance_products
            insurance_summary = {"created": _seed_insurance_products(db), "total": db.query(InsuranceProduct).count()}
        finally:
            db.close()
        return {
            "created": created,
            "demo": demo_summary,
            "demo_login": demo_login,
            "mkt": mkt_seeded,
            "market": market_seeded,
            "eq": eq_summary,
            "tools": tools_summary,
            "input": input_summary,
            "workers": workers_summary,
            "sensor_catalogue": sensor_catalogue,
            "techniques": techniques_summary,
            "learning": learning_summary,
            "experts": experts_summary,
            "schemes": schemes_summary,
            "insurance": insurance_summary,
        }

    created = demo_summary = market_seeded = input_summary = None
    demo_login = None
    eq_summary = None
    tools_summary = None
    workers_summary = None
    sensors_catalogue_report = None
    techniques_summary = learning_summary = experts_summary = schemes_summary = insurance_summary = None
    for _attempt in range(1, 5):
        try:
            _report = _run_seed_suite()
            created = _report["created"]
            demo_summary = _report["demo"]
            demo_login = _report["demo_login"]
            mkt_seeded = _report["mkt"]
            market_seeded = _report["market"]
            eq_summary = _report["eq"]
            tools_summary = _report["tools"]
            input_summary = _report["input"]
            workers_summary = _report["workers"]
            sensors_catalogue_report = _report["sensor_catalogue"]
            techniques_summary = _report["techniques"]
            learning_summary = _report["learning"]
            experts_summary = _report["experts"]
            schemes_summary = _report["schemes"]
            insurance_summary = _report["insurance"]
            break
        except OperationalError as _exc:
            print(f"Startup seeding attempt {_attempt} aborted (database busy: {_exc}); retrying...")
            time.sleep(2 * _attempt)
    if eq_summary is None and market_seeded is None:
        print("WARNING: startup seeding did not fully complete after retries; API remains available.")
    if demo_login and demo_login.get("status") == "created":
        print(f"Created demo login account: {demo_login['phone']} / PIN {demo_login['pin']} (farmer {demo_login['farmer_id']})")
    if workers_summary:
        print(
            f"Workers catalogue ready: {workers_summary['total_workers']} workers "
            f"(added {workers_summary['workers_seeded']}, "
            f"availability rows {workers_summary['availability_seeded']})."
        )
    if sensors_catalogue_report is not None:
        print(
            f"Sensor device catalogue seeded: {sensors_catalogue_report.get('devices_seeded', 0)} "
            "unclaimed devices available to connect."
        )

    print(f"{settings.APP_NAME} v{settings.APP_VERSION} started. DB tables created.")
    if techniques_summary is not None:
        print("Farm techniques catalogue ready (Techniques Hub fully populated).")
    if learning_summary:
        print(f"Learning centre ready: {learning_summary.get('total_courses')} courses "
              f"(created {learning_summary.get('created')}, existing {learning_summary.get('already_existing')}).")
    if experts_summary and experts_summary.get("total"):
        print(f"Experts Hub ready: {experts_summary['total']} experts "
              f"(created {experts_summary.get('created')}).")
    if schemes_summary and schemes_summary.get("total"):
        print(f"Government schemes ready: {schemes_summary['total']} verified schemes "
              f"(added {schemes_summary.get('added')}).")
    if insurance_summary and insurance_summary.get("total"):
        print(f"Insurance products ready: {insurance_summary['total']} products "
              f"(created {insurance_summary.get('created')}).")
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
    if tools_summary:
        print(
            f"Tools & Equipment catalogue ready: {tools_summary['categories']} categories, "
            f"created {tools_summary['products_created']} BUY products "
            f"(moved {tools_summary.get('moved_products', 0)}) and "
            f"{tools_summary['rentals_created']} RENT machinery "
            f"(touched {tools_summary.get('touched_rentals', 0)})."
        )
    if input_summary:
        print(f"Seeded Input Store catalogue: {input_summary['products']} products in {input_summary['categories']} categories.")



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

    @app.get("/farm-operations")
    @app.get("/farm-operations/")
    @app.get("/farm-operations.html")
    @app.get("/operations")
    @app.get("/operations/")
    @app.get("/operations.html")
    async def old_farm_operations_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/farm.html", status_code=301)

    @app.get("/{full_path:path}")
    @app.post("/{full_path:path}")
    @app.put("/{full_path:path}")
    @app.patch("/{full_path:path}")
    @app.delete("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # API calls that reach the catch-all mean the route does not exist on
        # this backend build. Return JSON (never the SPA HTML) so the frontend
        # can surface a precise error instead of "unexpected response".
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"success": False, "code": "route_not_found", "detail": f"API endpoint not found: /{full_path}"},
            )
        file_path = frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            # Never cache HTML/JS/CSS so browser + service-worker updates are
            # picked up immediately after deployment.
            name = file_path.name.lower()
            if name.endswith('.html') or name.endswith('.js') or name.endswith('.css'):
                return FileResponse(file_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
            return FileResponse(file_path)
        return FileResponse(frontend_dir / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
