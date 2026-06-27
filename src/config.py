"""
Configuration module for the local AI assistant.
Loads and validates settings from environment variables using Pydantic BaseSettings.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Ollama settings
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
    DEFAULT_MODEL: str = Field(default="llama3.2:3b")
    LLM_TIMEOUT: float = Field(default=120.0, gt=0)
    LLM_MAX_RETRIES: int = Field(default=3, ge=1, le=10)
    LLM_MAX_CONCURRENCY: int = Field(default=1, ge=1, le=16)

    # Gemini settings
    GEMINI_API_KEY: str = Field(default="")

    # Cache settings
    CACHE_DB_PATH: str = Field(default="benchmarks/cache.db")
    CACHE_TTL_HOURS: int = Field(default=24, ge=1)

    # RAG index settings (separate DB to avoid lock contention with cache)
    RAG_DB_PATH: str = Field(default="benchmarks/rag.db")

    # Security settings
    CORS_ORIGINS: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )
    MAX_UPLOAD_SIZE: int = Field(default=2 * 1024 * 1024, ge=1024)

    # Rate limiting (requests per minute per IP, 0 = disabled)
    RATE_LIMIT_RPM: int = Field(default=60, ge=0)

    @field_validator("OLLAMA_BASE_URL")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v  # type: ignore[return-value]


settings = Settings()
