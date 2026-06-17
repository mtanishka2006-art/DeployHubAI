"""Central application configuration.

All settings are environment-driven (12-factor). Sensible defaults let the
whole platform boot with zero configuration for local development and demos,
while every external dependency (Postgres, Kafka, Chroma, LLM provider) can be
wired up by setting the corresponding environment variable.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- App ----
    APP_NAME: str = "DeployHub AI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_PREFIX: str = "/api"

    # ---- Security / Auth ----
    JWT_SECRET: str = "change-me-in-production-please-32+chars-long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    # Bootstrap admin account (used to seed the first user).
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    # ---- CORS ----
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    # ---- Database ----
    # When unset, falls back to a local SQLite file so the platform runs with
    # zero infrastructure. In Docker Compose this points at Postgres.
    DATABASE_URL: str = "sqlite:///./deployhub.db"

    # ---- Messaging (Kafka) ----
    KAFKA_BOOTSTRAP_SERVERS: str = ""  # empty => in-memory event bus
    KAFKA_CLIENT_ID: str = "deployhub-ai"

    # ---- Vector memory (ChromaDB) ----
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    CHROMA_HOST: str = ""  # set to use a remote chroma server
    CHROMA_PORT: int = 8000
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # ---- LLM provider (optional) ----
    # If ANTHROPIC_API_KEY is set, agents augment their deterministic reasoning
    # with Claude. Otherwise the platform runs fully offline on heuristics.
    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-opus-4-8"

    # ---- App Connector Hub ----
    # Key for encrypting connector credentials at rest. Falls back to a key
    # deterministically derived from JWT_SECRET so it works with zero config.
    FERNET_KEY: str = ""
    # Background poller that pulls live data from connected apps.
    CONNECTOR_POLLING_ENABLED: bool = True
    CONNECTOR_POLL_TICK_SECONDS: int = 15  # how often the poller wakes up
    CONNECTOR_DEFAULT_INTERVAL_SECONDS: int = 60  # default per-app cadence

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def kafka_enabled(self) -> bool:
        return bool(self.KAFKA_BOOTSTRAP_SERVERS.strip())

    @property
    def llm_enabled(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
