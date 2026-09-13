import os
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        extra="ignore",
    )

    APP_NAME: str = "Farm Assist"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'farm_assist.db').as_posix()}"

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def resolve_sqlite_path(cls, value: str) -> str:
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            return value
        database_path = Path(value[len(prefix):])
        if database_path.is_absolute():
            return value
        return f"{prefix}{(BACKEND_DIR / database_path).resolve().as_posix()}"

    SECRET_KEY: str = "farm-assist-dev-secret-key-change-in-production-2024"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_ISSUER: str = "farm-assist"

    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8080",
        "http://localhost:8000",
        "https://farm-assistv3.vercel.app",
    ]

    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = ""
    WEATHER_API_KEY: str = ""
    SMS_API_KEY: str = ""
    EMAIL_API_KEY: str = ""
    SMS_SENDER_ID: str = ""

    WEATHER_API_PROVIDER: str = "open-meteo"
    WEATHER_API_BASE_URL: str = "https://api.open-meteo.com/v1"

    AI_DEFAULT_MODEL: str = "local"
    AI_FALLBACK_ENABLED: bool = True

    NEWS_API_KEY: str = ""
    NEWS_API_BASE_URL: str = "https://newsapi.org/v2"

    MARKET_PRICE_API_KEY: str = ""
    MARKET_PRICE_API_BASE_URL: str = "https://api.data.gov.in/resource"
    MARKET_PRICE_RESOURCE_ID: str = "9ef84268-d588-465a-a308-a864a43d0070"
    MARKET_PRICE_SOURCE_NAME: str = "AGMARKNET (Ministry of Agriculture & Farmers Welfare)"
    MARKET_PRICE_SOURCE_URL: str = "https://agmarknet.gov.in"
    MARKET_PRICE_REFRESH_MINUTES: int = 30
    MARKET_PRICE_STALE_HOURS: int = 72
    MARKET_PRICE_FETCH_LIMIT: int = 500

    # ---- Government Schemes (official GoI sources) ----
    # Configure in backend/.env. Only URLs/keys from official Government of
    # India / Ministry of Agriculture & Farmers Welfare domains are supported;
    # nothing is fetched, stored or labelled "live" unless a source actually
    # responds with valid JSON. Sources stay configurable here (server-side),
    # never hardcoded on the frontend.
    GOV_SCHEMES_API_KEY: str = ""                     # data.gov.in / API Setu key
    GOV_SCHEMES_SOURCE_URLS: List[str] = []           # full official JSON endpoints
    GOV_SCHEMES_SOURCE_BASE: str = "https://api.data.gov.in/resource"
    GOV_SCHEMES_RESOURCE_IDS: List[str] = []          # optional data.gov.in resource ids
    GOV_SCHEMES_SOURCE_NAME: str = "Government of India Open Data (data.gov.in)"
    GOV_SCHEMES_SOURCE_URL: str = "https://data.gov.in"
    GOV_SCHEMES_REFRESH_MINUTES: int = 180
    GOV_SCHEMES_STALE_HOURS: int = 240
    GOV_SCHEMES_FETCH_LIMIT: int = 500

    TRANSLATION_API_KEY: str = ""
    SPEECH_API_KEY: str = ""

    FCM_SERVER_KEY: str = ""

    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_PATH: str = "uploads"
    STORAGE_MAX_FILE_SIZE_MB: int = 25
    STORAGE_ALLOWED_EXTENSIONS: str = "jpg,jpeg,png,gif,webp,pdf,doc,docx,xls,xlsx,ppt,pptx,csv,txt"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@farmassist.app"
    SUPPORT_EMAIL_TO: str = "farm.assist@outlook.com"

    # Wallet security caps (used to limit self-minted deposits without a live gateway)
    WALLET_MAX_SINGLE_DEPOSIT: float = 50000
    WALLET_MAX_DAILY_DEPOSITS: float = 100000

    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/farm_assist.log"


settings = Settings()

# reload_touch

