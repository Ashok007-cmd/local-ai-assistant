"""
SQLite FTS5 full-text search indexing database for local RAG.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)

# Thread-local storage for SQLite connection reuse
_local = threading.local()


class RAGIndex:
    """SQLite-backed full-text search (FTS5) index for documents."""

    def __init__(self, db_path: str = settings.RAG_DB_PATH):
        self.db_path = Path(db_path)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection."""
        if not hasattr(_local, "rag_conn") or _local.rag_conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            _local.rag_conn = conn
        return _local.rag_conn

    def _init_db(self) -> None:
        """Create DB directory and initialize FTS5 table if it doesn't exist."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                # FTS5 virtual table
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS rag_documents_fts USING fts5(
                        title,
                        content
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to initialize SQLite FTS5 RAG index at %s: %s", self.db_path, e)

    def index_document(self, title: str, content: str) -> None:
        """Upsert a document into the FTS5 index — replaces any existing entry with the same title."""
        try:
            conn = self._get_conn()
            # Delete existing rows with the same title first (FTS5 has no native upsert)
            conn.execute("DELETE FROM rag_documents_fts WHERE title = ?", (title,))
            conn.execute(
                "INSERT INTO rag_documents_fts (title, content) VALUES (?, ?)",
                (title, content),
            )
            conn.commit()
            logger.info("Indexed document: %s", title)
        except Exception as e:
            logger.error("Error indexing document %s: %s", title, e)

    def search_documents(self, query: str) -> list[dict[str, Any]]:
        """Search documents using FTS5 MATCH query synchronously, returning BM25 ranked matches."""
        try:
            # Basic sanitization for FTS5 queries (strip special character punctuation to avoid syntax errors)
            clean_query = "".join(c if c.isalnum() or c.isspace() else " " for c in query).strip()
            if not clean_query:
                return []

            # Formulate a simple word-match query (e.g. "python AND language")
            words = [w for w in clean_query.split() if w]
            if not words:
                return []
            # Use OR for broader overlap matching
            fts_query = " OR ".join(words)

            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT title, content, rank
                FROM rag_documents_fts
                WHERE rag_documents_fts MATCH ?
                ORDER BY rank ASC
                """,
                (fts_query,)
            )
            rows = cursor.fetchall()
            results = []
            for title, content, rank in rows:
                results.append({
                    "document": {
                        "title": title,
                        "content": content
                    },
                    "score": float(-rank)
                })
            return results
        except Exception as e:
            logger.error("Error searching FTS5 index for '%s': %s", query, e)
            return []

    def clear(self) -> None:
        """Clear all documents from index synchronously."""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM rag_documents_fts")
            conn.commit()
            logger.info("FTS5 index cleared")
        except Exception as e:
            logger.error("Failed to clear FTS5 index: %s", e)

    def get_count(self) -> int:
        """Get total number of indexed documents synchronously."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM rag_documents_fts")
            return cursor.fetchone()[0]
        except Exception:
            return 0

    # Async counterparts using asyncio.to_thread
    async def index_document_async(self, title: str, content: str) -> None:
        """Insert a document into the FTS5 index asynchronously."""
        await asyncio.to_thread(self.index_document, title, content)

    async def search_documents_async(self, query: str) -> list[dict[str, Any]]:
        """Search documents asynchronously."""
        return await asyncio.to_thread(self.search_documents, query)

    async def clear_async(self) -> None:
        """Clear FTS5 index asynchronously."""
        await asyncio.to_thread(self.clear)

    async def get_count_async(self) -> int:
        """Get total number of indexed documents asynchronously."""
        return await asyncio.to_thread(self.get_count)


# Global RAG index instance
rag_index = RAGIndex()
