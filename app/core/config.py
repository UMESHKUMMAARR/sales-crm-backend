"""
Central configuration — all settings from environment variables.
Never hardcode secrets. Use .env locally, platform env vars in production.
"""
from pydantic_settings import BaseSettings
from typing import Optional
import secrets


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Sales CRM Pro"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # development | staging | production

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(64)   # MUST override in prod via env var
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60          # 1 hour
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_MIN_LENGTH: int = 8

    # CORS — set exact origins in production, never "*"
    # ALLOWED_ORIGINS: str = "http://localhost:8081"

    # MongoDB
    MONGO_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "sales_crm_pro"

    # Rate limiting (requests per window)
    RATE_LIMIT_PER_MINUTE: int = 60
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10   # Stricter for auth endpoints

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
