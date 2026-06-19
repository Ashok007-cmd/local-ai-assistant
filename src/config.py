"""
Configuration module for the local AI assistant.
Loads settings from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    # Ollama settings
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "llama3.2:3b")
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "120.0"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    LLM_MAX_CONCURRENCY: int = int(os.getenv("LLM_MAX_CONCURRENCY", "1"))

    # Gemini settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # Cache settings
    CACHE_DB_PATH: str = os.getenv("CACHE_DB_PATH", "benchmarks/cache.db")
    CACHE_TTL_HOURS: int = int(os.getenv("CACHE_TTL_HOURS", "24"))

    # RAG index settings (separate DB to avoid lock contention with cache)
    RAG_DB_PATH: str = os.getenv("RAG_DB_PATH", "benchmarks/rag.db")

    # Security settings
    CORS_ORIGINS: list[str] = [
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000").split(",") if origin.strip()
    ]
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", str(2 * 1024 * 1024)))



settings = Settings()

