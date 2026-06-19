"""
Local cache implementation using SQLite for fast retrieval of repeated queries.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)

# Thread-local storage for SQLite connection reuse
_local = threading.local()


class ResponseCache:
    """SQLite-backed local cache for storing validated LLM responses."""

    def __init__(self, db_path: str = settings.CACHE_DB_PATH, ttl_hours: int = settings.CACHE_TTL_HOURS):
        self.db_path = Path(db_path)
        self.ttl_seconds = ttl_hours * 3600
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection."""
        if not hasattr(_local, "cache_conn") or _local.cache_conn is None:
            # We use check_same_thread=False since connection is thread-local and safe
            conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            _local.cache_conn = conn
        return _local.cache_conn

    def _init_db(self) -> None:
        """Create DB directory and initialize tables if they don't exist."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS query_cache (
                        key TEXT PRIMARY KEY,
                        response_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to initialize SQLite cache database at %s: %s", self.db_path, e)

    def _generate_key(self, prompt: str, schema_name: str, model: str) -> str:
        """Create a stable, unique hash key based on inputs."""
        payload = {
            "prompt": prompt,
            "schema": schema_name,
            "model": model
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, prompt: str, schema_name: str, model: str) -> dict[str, Any] | None:
        """Retrieve cached response if it exists and is not expired."""
        key = self._generate_key(prompt, schema_name, model)
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT response_json, created_at FROM query_cache WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            response_json, created_at = row
            # Check expiration
            if time.time() - created_at > self.ttl_seconds:
                logger.info("Cache entry expired for key %s. Deleting.", key)
                cursor.execute("DELETE FROM query_cache WHERE key = ?", (key,))
                conn.commit()
                return None

            logger.info("Cache hit for key %s", key)
            return json.loads(response_json)
        except Exception as e:
            logger.warning("Error reading from query cache: %s", e)
            return None

    def set(self, prompt: str, schema_name: str, model: str, data: dict[str, Any]) -> None:
        """Save response to the cache, overwriting any existing entry."""
        key = self._generate_key(prompt, schema_name, model)
        try:
            response_json = json.dumps(data)
            conn = self._get_conn()
            conn.execute(
                """
                INSERT OR REPLACE INTO query_cache (key, response_json, created_at)
                VALUES (?, ?, ?)
                """,
                (key, response_json, time.time())
            )
            conn.commit()
            logger.info("Cached response successfully under key %s", key)
        except Exception as e:
            logger.warning("Error writing to query cache: %s", e)

    def clear(self) -> None:
        """Delete all cached queries."""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM query_cache")
            conn.commit()
            logger.info("Query cache cleared")
        except Exception as e:
            logger.error("Failed to clear query cache: %s", e)

    async def get_async(self, prompt: str, schema_name: str, model: str) -> dict[str, Any] | None:
        """Retrieve cached response asynchronously using thread pool delegation."""
        import asyncio
        return await asyncio.to_thread(self.get, prompt, schema_name, model)

    async def set_async(self, prompt: str, schema_name: str, model: str, data: dict[str, Any]) -> None:
        """Save response to the cache asynchronously using thread pool delegation."""
        import asyncio
        await asyncio.to_thread(self.set, prompt, schema_name, model, data)

    async def clear_async(self) -> None:
        """Delete all cached queries asynchronously using thread pool delegation."""
        import asyncio
        await asyncio.to_thread(self.clear)


# Global cache instance
response_cache = ResponseCache()
