from __future__ import annotations

from src.assistant import LLMClient
from src.config import settings

_clients: dict[str, LLMClient] = {}


def get_llm_client(model: str) -> LLMClient:
    """Return a cached LLMClient for *model*, creating one on first use."""
    if model not in _clients:
        _clients[model] = LLMClient(
            model=model,
            base_url=settings.OLLAMA_BASE_URL,
            max_retries=settings.LLM_MAX_RETRIES,
            timeout=settings.LLM_TIMEOUT,
        )
    return _clients[model]
