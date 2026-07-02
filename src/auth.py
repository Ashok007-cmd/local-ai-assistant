"""Optional shared-secret API key enforcement for mutating endpoints."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.config import settings


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require a matching X-API-Key header when API_KEY is configured.

    No-op when API_KEY is unset, preserving the default open local-only behavior.
    """
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")
