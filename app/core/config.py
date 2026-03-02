from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    Application configuration settings.
    All values can be overridden via environment variables.
    """
    
    # Application
    APP_NAME: str = "DayDay Tax API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/dayday_tax"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 10
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_HOSTS: list[str] = ["*"]
    
    # Security
    SECRET_KEY: str = "change-this-in-production-use-a-secure-random-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # CORS
    CORS_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 100
    
    # Task Processing
    TASK_TIMEOUT_SECONDS: int = 300
    MAX_CONCURRENT_TASKS: int = 10
    
    # Android Farm / Accountant Pool
    ACCOUNTANT_POOL_SIZE: int = 10
    SESSION_COOKIE_LIFETIME_HOURS: int = 24
    
    # Billing
    MONTHLY_SUBSCRIPTION_FEE: float = 10.00
    BILLING_DAY_OF_MONTH: int = 1  # Day to run monthly billing
    
    # Webhooks
    MILLION_WEBHOOK_SECRET: str = "change-this-million-webhook-secret-token"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
