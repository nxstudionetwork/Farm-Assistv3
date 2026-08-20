import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "Farm Assist"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    DATABASE_URL: str = "sqlite:///./farm_assist.db"

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
    MARKET_PRICE_API_BASE_URL: str = ""

    TRANSLATION_API_KEY: str = ""
    SPEECH_API_KEY: str = ""

    FCM_SERVER_KEY: str = ""

    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_PATH: str = "uploads"
    STORAGE_MAX_FILE_SIZE_MB: int = 10
    STORAGE_ALLOWED_EXTENSIONS: str = "jpg,jpeg,png,gif,pdf,doc,docx,xlsx,csv"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@farmassist.app"
    SUPPORT_EMAIL_TO: str = "farm.assist@outlook.com"

    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/farm_assist.log"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
