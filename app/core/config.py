"""
Application configuration using Pydantic Settings.
All secrets and settings are loaded from environment variables.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="OBS Fog Server", description="Application name")
    app_version: str = Field(default="2.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", description="Environment"
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    app_base_url: str = Field(
        default="http://localhost:8080", description="Public base URL"
    )
    allowed_hosts: list[str] = Field(
        default=["*"], description="Allowed hosts for CORS"
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/obsfog",
        description="PostgreSQL connection string",
    )
    database_pool_size: int = Field(default=5, description="Database pool size")
    database_max_overflow: int = Field(default=10, description="Max overflow connections")

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis connection string"
    )

    # JWT Authentication
    jwt_secret: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_USE_LONG_RANDOM_STRING",
        description="JWT secret key - MUST be changed in production",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration in minutes"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7, description="Refresh token expiration in days"
    )

    # Session
    session_cookie_name: str = Field(
        default="obsfog_session", description="Session cookie name"
    )
    session_secure: bool = Field(
        default=True, description="Secure cookie flag (HTTPS only)"
    )

    # Telegram Bot
    telegram_bot_token: str = Field(default="", description="Telegram bot token")
    telegram_bot_username: str = Field(default="obsfog_bot", description="Telegram bot username")
    telegram_admin_id: int = Field(default=0, description="Admin Telegram chat ID")
    telegram_required: bool = Field(default=True, description="Require Telegram binding")
    telegram_max_file_mb: int = Field(
        default=50, description="Max file size for Telegram (MB)"
    )

    # Telegram Wallet Payment (USDT TON)
    telegram_wallet_token: str = Field(
        default="", description="Telegram Wallet provider token"
    )
    premium_price_usdt: float = Field(
        default=10.0, description="Premium subscription price in USDT"
    )
    premium_duration_days: int = Field(
        default=30, description="Premium subscription duration in days"
    )

    # Streaming
    hls_base_url: str = Field(
        default="http://nginx:8080/hls", description="HLS base URL"
    )
    rtmp_url: str = Field(
        default="rtmp://localhost:1935/live", description="RTMP URL"
    )
    clip_seconds: int = Field(default=420, description="Clip duration in seconds")
    clip_retention_hours: int = Field(
        default=72, description="Clip retention in hours"
    )

    # Rate Limiting
    rate_limit_requests: int = Field(
        default=100, description="Rate limit requests per window"
    )
    rate_limit_window_seconds: int = Field(
        default=60, description="Rate limit window in seconds"
    )

    # Approval System
    approval_required: bool = Field(
        default=False, description="Require admin approval for new users"
    )

    # Timezone
    display_tz: str = Field(default="Europe/Amsterdam", description="Display timezone")

    # File Encryption (for Steam files)
    file_encryption_key: str = Field(
        default="", description="Fernet encryption key for Steam files"
    )

    # SteamSlot Admin
    steamslot_admin_user: str = Field(
        default="admin", description="SteamSlot admin username"
    )
    steamslot_admin_pass: str = Field(
        default="changeme", description="SteamSlot admin password"
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure database URL uses async driver."""
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("sqlite://") and "aiosqlite" not in v:
            return v.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return v

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @property
    def cors_origins(self) -> list[str]:
        """Get CORS origins based on environment."""
        if self.debug:
            return ["*"]
        return self.allowed_hosts


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
