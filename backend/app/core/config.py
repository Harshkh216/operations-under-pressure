"""Application configuration loaded from environment variables.

All secrets live in the environment, never in code. Sensible defaults are
provided for local development only; production deployments must override
every secret via their environment.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database -----------------------------------------------------------
    # PostgreSQL in production (postgresql+psycopg://user:pass@host:5432/dbname);
    # SQLite for local tests (set DATABASE_URL=sqlite:///./test.db).
    DATABASE_URL: str = "sqlite:///./operations.db"

    # --- Auth / JWT ---------------------------------------------------------
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    # --- CORS ---------------------------------------------------------------
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Outbox background processor ---------------------------------------
    # When enabled, a background asyncio task drains the outbox table.
    OUTBOX_ENABLED: bool = True
    OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0
    OUTBOX_MAX_ATTEMPTS: int = 5
    # For demo purposes the "delivery" is a no-op logger. In production this
    # would be an external webhook / message bus.
    OUTBOX_SINK_URL: str | None = None

    # --- Pagination defaults ------------------------------------------------
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Re-export for convenience.
__all__ = ["settings", "get_settings"]

# Suppress the bcrypt 4 warning from passlib when running locally.
os.environ.setdefault("PASSLIB_BCRYPT_DISABLE", "0")
