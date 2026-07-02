"""
LLM query wrapper with Pydantic validation, automatic retry mechanism, and async execution.
Handles communication with Ollama, ensures structured output, and manages response caching.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from src.cache import response_cache
from src.config import settings
from src.models import ResumeAnalysisResult, parse_llm_json_output

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Gemini models this app knows how to route to. Rejecting anything else before it
# reaches the outbound URL avoids splicing an unvalidated user string into an
# authenticated request path.
ALLOWED_GEMINI_MODELS = frozenset({"gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"})

_KEY_QUERY_PARAM_RE = re.compile(r"([?&]key=)[^&\s'\"]+")


def _sanitize_error_message(e: Exception) -> str:
    """Return a client-safe error string.

    httpx exceptions stringify to include the full request URL, which for Gemini
    contains `?key=<API key>` — never let that reach an HTTP response. Any other
    query-string `key=` param is redacted the same way as defense in depth.
    """
    return _KEY_QUERY_PARAM_RE.sub(r"\1[REDACTED]", str(e))


def _validate_gemini_model(model: str) -> None:
    if model not in ALLOWED_GEMINI_MODELS:
        raise ValueError(f"Unsupported Gemini model: {model!r}. Allowed: {sorted(ALLOWED_GEMINI_MODELS)}")

# Global semaphore to limit concurrent inference requests to Ollama
_global_semaphore = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)

# Reusable asynchronous HTTP client for performance optimization
_shared_async_client: httpx.AsyncClient | None = None

def get_async_client() -> httpx.AsyncClient:
    global _shared_async_client
    if _shared_async_client is None or _shared_async_client.is_closed:
        _shared_async_client = httpx.AsyncClient(timeout=settings.LLM_TIMEOUT)
    return _shared_async_client

async def close_async_client() -> None:
    global _shared_async_client
    if _shared_async_client is not None and not _shared_async_client.is_closed:
        await _shared_async_client.aclose()
        _shared_async_client = None


def resolve_schema_refs(schema: dict) -> dict:
    """Recursively expand $ref references using definitions in $defs."""
    defs = schema.get("$defs", {})

    def resolve(item: Any) -> Any:
        if isinstance(item, dict):
            if "$ref" in item:
                ref_path = item["$ref"]
                ref_key = ref_path.split("/")[-1]
                if ref_key in defs:
                    resolved_def = resolve(defs[ref_key])
                    merged = {k: v for k, v in item.items() if k != "$ref"}
                    merged.update(resolved_def)
                    return merged
            return {k: resolve(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [resolve(i) for i in item]
        return item

    resolved = resolve(schema)
    if "$defs" in resolved:
        del resolved["$defs"]
    return resolved


def convert_to_gemini_schema(schema: dict) -> dict:
    """Convert standard JSON Schema to Gemini-compatible schema (uppercase types, resolved refs)."""
    resolved = resolve_schema_refs(schema)

    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            if "anyOf" in item:
                types = [x for x in item["anyOf"] if isinstance(x, dict) and x.get("type") != "null"]
                if types:
                    first_type = clean(types[0])
                    merged = {k: clean(v) for k, v in item.items() if k not in ["anyOf", "type"]}
                    merged.update(first_type)
                    return merged
            cleaned = {}
            for k, v in item.items():
                if k == "type" and isinstance(v, str):
                    cleaned[k] = v.upper()
                elif k == "enum" and isinstance(v, list):
                    cleaned[k] = v
                elif k in ["title", "examples", "default"]:
                    continue
                else:
                    cleaned[k] = clean(v)
            return cleaned
        elif isinstance(item, list):
            return [clean(i) for i in item]
        return item

    return clean(resolved)


class LLMResponse(BaseModel):
    """Wraps the parsed and validated response from the LLM."""

    success: bool
    data: Any = None
    raw_output: str = ""
    attempts: int = 0
    errors: list[str] = []


class LLMClient:

    """Client for interacting with Ollama-hosted models with structured output enforcement."""

    def __init__(
        self,
        model: str = settings.DEFAULT_MODEL,
        base_url: str = settings.OLLAMA_BASE_URL,
        max_retries: int = settings.LLM_MAX_RETRIES,
        timeout: float = settings.LLM_TIMEOUT,
        temperature: float = 0.1,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self.temperature = temperature

    def _build_generate_url(self) -> str:
        return f"{self.base_url}/api/generate"

    def _build_chat_url(self) -> str:
        return f"{self.base_url}/api/chat"

    def _sleep_with_backoff(self, attempt: int) -> None:
        """Sleep with exponential backoff and randomized jitter."""
        if attempt < self.max_retries:
            sleep_time = (2 ** attempt) + random.uniform(0.1, 1.0)
            logger.info("Backoff retry: sleeping for %.2fs before attempt %d", sleep_time, attempt + 1)
            time.sleep(sleep_time)

    async def _sleep_with_backoff_async(self, attempt: int) -> None:
        """Sleep with exponential backoff and randomized jitter asynchronously."""
        if attempt < self.max_retries:
            sleep_time = (2 ** attempt) + random.uniform(0.1, 1.0)
            logger.info("Async backoff retry: sleeping for %.2fs before attempt %d", sleep_time, attempt + 1)
            await asyncio.sleep(sleep_time)

    # ---------------------------------------------------------------------------
    # Synchronous methods (retained for backward compatibility and test runner)
    # ---------------------------------------------------------------------------

    def _query_ollama(self, prompt: str, system_prompt: str | None = None, format: str | None = None) -> str:
        """Send a prompt to Ollama's /api/generate endpoint and return the raw text."""
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": self.temperature,
            "options": {
                "num_predict": 2048,
            },
        }

        if format:
            payload["format"] = format

        if system_prompt:
            payload["system"] = system_prompt

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self._build_generate_url(), json=payload)
            response.raise_for_status()
            result = response.json()

        return result.get("response", "")

    def _query_ollama_chat(
        self,
        messages: list[dict[str, str]],
        format: str | None = None,
    ) -> str:
        """Send a chat-format request to Ollama and return the response text."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": self.temperature,
        }

        if format:
            payload["format"] = format

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self._build_chat_url(), json=payload)
            response.raise_for_status()
            result = response.json()

        return result.get("message", {}).get("content", "")

    def _query_gemini(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[T] | None = None,
    ) -> str:
        """Send a prompt to the Google Gemini API synchronously."""
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")
        _validate_gemini_model(self.model)

        model_name = self.model
        if "/" not in model_name:
            model_name = f"models/{model_name}"

        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent"

        contents = [{
            "role": "user",
            "parts": [{"text": prompt}]
        }]

        payload: dict[str, Any] = {
            "contents": contents,
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        generation_config: dict[str, Any] = {
            "temperature": self.temperature,
        }

        if schema:
            generation_config["responseMimeType"] = "application/json"
            pydantic_schema = schema.model_json_schema()
            gemini_schema = convert_to_gemini_schema(pydantic_schema)
            generation_config["responseSchema"] = gemini_schema

        payload["generationConfig"] = generation_config

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json=payload, headers={"x-goog-api-key": settings.GEMINI_API_KEY})
            response.raise_for_status()
            result = response.json()

        try:
            candidates = result.get("candidates", [])
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return ""
            return parts[0].get("text", "")
        except (KeyError, IndexError) as e:
            logger.error("Failed to parse Gemini API response: %s", e)
            raise ValueError(f"Invalid response structure from Gemini API: {e}")

    def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        system_prompt: str | None = None,
        fallback_factory: Callable[[], T] | None = None,
    ) -> LLMResponse:
        """
        Generate a response and validate against the given Pydantic schema (Synchronous).
        Checks local query cache first.
        """
        # 1. Check SQLite Cache
        cached = response_cache.get(prompt, schema.__name__, self.model)
        if cached is not None:
            try:
                validated = schema.model_validate(cached)
                return LLMResponse(
                    success=True,
                    data=validated,
                    raw_output=json.dumps(cached),
                    attempts=1,
                    errors=[],
                )
            except ValidationError as e:
                logger.warning("Cached data failed validation for schema %s: %s", schema.__name__, e)

        errors: list[str] = []
        last_raw = ""

        # Check if Gemini model
        if self.model.startswith("gemini-"):
            for attempt in range(1, self.max_retries + 1):
                logger.info(
                    "Gemini attempt %d/%d for model=%s schema=%s",
                    attempt, self.max_retries, self.model, schema.__name__,
                )
                try:
                    last_raw = self._query_gemini(prompt, system_prompt=system_prompt, schema=schema)
                except Exception as e:
                    logger.warning("Gemini query failed on attempt %d: %s", attempt, e)
                    errors.append(f"API error: {_sanitize_error_message(e)}")
                    self._sleep_with_backoff(attempt)
                    continue

                if not last_raw.strip():
                    errors.append("Empty response from model")
                    self._sleep_with_backoff(attempt)
                    continue

                try:
                    parsed = parse_llm_json_output(last_raw)
                except (json.JSONDecodeError, ValueError) as e:
                    errors.append(f"JSON parse error: {e}")
                    self._sleep_with_backoff(attempt)
                    continue

                try:
                    validated = schema.model_validate(parsed)
                    response_cache.set(prompt, schema.__name__, self.model, parsed)
                    return LLMResponse(
                        success=True,
                        data=validated,
                        raw_output=last_raw,
                        attempts=attempt,
                        errors=errors,
                    )
                except ValidationError as e:
                    error_messages = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
                    errors.extend(error_messages)
                    self._sleep_with_backoff(attempt)
                    continue

            if fallback_factory:
                try:
                    fallback_data = fallback_factory()
                    return LLMResponse(
                        success=False,
                        data=fallback_data,
                        raw_output=last_raw,
                        attempts=self.max_retries,
                        errors=errors,
                    )
                except Exception as e:
                    errors.append(f"Fallback factory failed: {e}")
            return LLMResponse(
                success=False,
                raw_output=last_raw,
                attempts=self.max_retries,
                errors=errors,
            )

        if not system_prompt:
            schema_example = schema.model_json_schema()
            system_prompt = (
                "You are a precise JSON generator. "
                "You MUST respond with valid JSON only — no markdown, no explanations, no extra text. "
                "The JSON must strictly conform to the following schema:\n\n"
                f"{json.dumps(schema_example, indent=2)}\n\n"
                "Output ONLY the JSON object, wrapped in ```json ... ``` if needed, "
                "but ensure it is parseable."
            )

        for attempt in range(1, self.max_retries + 1):
            logger.info(
                "Attempt %d/%d for model=%s schema=%s",
                attempt,
                self.max_retries,
                self.model,
                schema.__name__,
            )

            current_prompt = prompt
            if errors:
                correction_prompt = (
                    "\n\n---\n"
                    "Your previous response failed validation. "
                    "Here is your previous (invalid) output:\n"
                    f"```\n{last_raw}\n```\n\n"
                    "Validation errors:\n"
                    + "\n".join(f"  - {e}" for e in errors)
                    + "\n\n"
                    "Please correct the JSON to match the required schema exactly. "
                    "Respond with ONLY valid JSON."
                )
                current_prompt = prompt + correction_prompt

            try:
                last_raw = self._query_ollama(current_prompt, system_prompt=system_prompt, format="json")
            except Exception as e:
                logger.warning("Ollama query failed on attempt %d: %s", attempt, e)
                errors.append(f"API error: {_sanitize_error_message(e)}")
                self._sleep_with_backoff(attempt)
                continue

            if not last_raw.strip():
                errors.append("Empty response from model")
                self._sleep_with_backoff(attempt)
                continue

            try:
                parsed = parse_llm_json_output(last_raw)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("JSON parse failed on attempt %d: %s", attempt, e)
                errors.append(f"JSON parse error: {e}")
                self._sleep_with_backoff(attempt)
                continue

            try:
                validated = schema.model_validate(parsed)
                # Save to Cache on success
                response_cache.set(prompt, schema.__name__, self.model, parsed)
                return LLMResponse(
                    success=True,
                    data=validated,
                    raw_output=last_raw,
                    attempts=attempt,
                    errors=errors,
                )
            except ValidationError as e:
                error_messages = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
                logger.warning(
                    "Pydantic validation failed on attempt %d: %s",
                    attempt,
                    error_messages,
                )
                errors.extend(error_messages)
                self._sleep_with_backoff(attempt)
                continue

        # Fallback
        if fallback_factory:
            try:
                fallback_data = fallback_factory()
                return LLMResponse(
                    success=False,
                    data=fallback_data,
                    raw_output=last_raw,
                    attempts=self.max_retries,
                    errors=errors,
                )
            except Exception as e:
                errors.append(f"Fallback factory failed: {e}")

        return LLMResponse(
            success=False,
            raw_output=last_raw,
            attempts=self.max_retries,
            errors=errors,
        )

    def generate_structured_chat(
        self,
        messages: list[dict[str, str]],
        schema: type[T],
        fallback_factory: Callable[[], T] | None = None,
    ) -> LLMResponse:
        """Chat-format version of generate_structured."""
        # Simple cache logic for chat using serialized messages as key
        cache_key = json.dumps(messages, sort_keys=True)
        cached = response_cache.get(cache_key, schema.__name__, self.model)
        if cached is not None:
            try:
                validated = schema.model_validate(cached)
                return LLMResponse(
                    success=True,
                    data=validated,
                    raw_output=json.dumps(cached),
                    attempts=1,
                    errors=[],
                )
            except ValidationError:
                pass

        errors: list[str] = []
        last_raw = ""

        for attempt in range(1, self.max_retries + 1):
            logger.info(
                "Chat attempt %d/%d for model=%s schema=%s",
                attempt,
                self.max_retries,
                self.model,
                schema.__name__,
            )

            current_messages = list(messages)
            if errors:
                current_messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response was invalid. "
                        f"Errors: {'; '.join(errors)}\n"
                        f"Your invalid output:\n{last_raw}\n\n"
                        "Please correct the JSON to match the schema exactly."
                    ),
                })

            try:
                last_raw = self._query_ollama_chat(current_messages, format="json")
            except Exception as e:
                logger.warning("Chat query failed on attempt %d: %s", attempt, e)
                errors.append(f"API error: {_sanitize_error_message(e)}")
                self._sleep_with_backoff(attempt)
                continue

            if not last_raw.strip():
                errors.append("Empty response from model")
                self._sleep_with_backoff(attempt)
                continue

            try:
                parsed = parse_llm_json_output(last_raw)
            except (json.JSONDecodeError, ValueError) as e:
                errors.append(f"JSON parse error: {e}")
                self._sleep_with_backoff(attempt)
                continue

            try:
                validated = schema.model_validate(parsed)
                response_cache.set(cache_key, schema.__name__, self.model, parsed)
                return LLMResponse(
                    success=True,
                    data=validated,
                    raw_output=last_raw,
                    attempts=attempt,
                    errors=errors,
                )
            except ValidationError as e:
                error_messages = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
                errors.extend(error_messages)
                self._sleep_with_backoff(attempt)
                continue

        if fallback_factory:
            try:
                fallback_data = fallback_factory()
                return LLMResponse(
                    success=False,
                    data=fallback_data,
                    raw_output=last_raw,
                    attempts=self.max_retries,
                    errors=errors,
                )
            except Exception as e:
                errors.append(f"Fallback factory failed: {e}")

        return LLMResponse(
            success=False,
            raw_output=last_raw,
            attempts=self.max_retries,
            errors=errors,
        )

    # ---------------------------------------------------------------------------
    # Asynchronous methods (Optimized for production event-loop stability)
    # ---------------------------------------------------------------------------

    async def _query_ollama_async(
        self, prompt: str, system_prompt: str | None = None, format: str | None = None
    ) -> str:
        """Send a prompt to Ollama's /api/generate endpoint asynchronously."""
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": self.temperature,
            "options": {
                "num_predict": 2048,
            },
        }

        if format:
            payload["format"] = format

        if system_prompt:
            payload["system"] = system_prompt

        client = get_async_client()
        response = await client.post(self._build_generate_url(), json=payload)
        response.raise_for_status()
        result = response.json()

        return result.get("response", "")

    async def _query_ollama_chat_async(
        self,
        messages: list[dict[str, str]],
        format: str | None = None,
    ) -> str:
        """Send a chat-format request to Ollama asynchronously."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": self.temperature,
        }

        if format:
            payload["format"] = format

        client = get_async_client()
        response = await client.post(self._build_chat_url(), json=payload)
        response.raise_for_status()
        result = response.json()

        return result.get("message", {}).get("content", "")
    async def _query_gemini_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
        schema: type[T] | None = None,
    ) -> str:
        """Send a prompt to the Google Gemini API asynchronously."""
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")
        _validate_gemini_model(self.model)

        model_name = self.model
        if "/" not in model_name:
            model_name = f"models/{model_name}"

        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent"

        contents = [{
            "role": "user",
            "parts": [{"text": prompt}]
        }]

        payload: dict[str, Any] = {
            "contents": contents,
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        generation_config: dict[str, Any] = {
            "temperature": self.temperature,
        }

        if schema:
            generation_config["responseMimeType"] = "application/json"
            pydantic_schema = schema.model_json_schema()
            gemini_schema = convert_to_gemini_schema(pydantic_schema)
            generation_config["responseSchema"] = gemini_schema

        payload["generationConfig"] = generation_config

        client = get_async_client()
        response = await client.post(url, json=payload, headers={"x-goog-api-key": settings.GEMINI_API_KEY})
        response.raise_for_status()
        result = response.json()

        try:
            candidates = result.get("candidates", [])
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return ""
            return parts[0].get("text", "")
        except (KeyError, IndexError) as e:
            logger.error("Failed to parse Gemini API response: %s", e)
            raise ValueError(f"Invalid response structure from Gemini API: {e}")

    async def stream_raw_async(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ):
        """Stream raw tokens from Ollama or Gemini API asynchronously."""
        if self.model.startswith("gemini-"):
            if not settings.GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY is not configured.")
            _validate_gemini_model(self.model)
            model_name = self.model
            if "/" not in model_name:
                model_name = f"models/{model_name}"
            url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:streamGenerateContent?alt=sse"

            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            }
            if system_prompt:
                payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

            client = get_async_client()
            headers = {"x-goog-api-key": settings.GEMINI_API_KEY}
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("[") or line.startswith(","):
                        line = line[1:].strip()
                    if line.endswith("]"):
                        line = line[:-1].strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        text = chunk["candidates"][0]["content"]["parts"][0]["text"]
                        yield text
                    except Exception:
                        continue
        else:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": True,
                "temperature": self.temperature,
            }
            if system_prompt:
                payload["system"] = system_prompt

            client = get_async_client()
            async with client.stream("POST", self._build_generate_url(), json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        yield chunk.get("response", "")
                    except Exception:
                        continue

    async def generate_structured_async(
        self,
        prompt: str,
        schema: type[T],
        system_prompt: str | None = None,
        fallback_factory: Callable[[], T] | None = None,
    ) -> LLMResponse:
        """
        Generate a response and validate against Pydantic schema asynchronously.
        Enforces global semaphore concurrency limits and checks the database cache.
        """
        # 1. Check Cache first (outside the Semaphore lock for zero-wait cache hits)
        cached = await response_cache.get_async(prompt, schema.__name__, self.model)
        if cached is not None:
            try:
                validated = schema.model_validate(cached)
                return LLMResponse(
                    success=True,
                    data=validated,
                    raw_output=json.dumps(cached),
                    attempts=1,
                    errors=[],
                )
            except ValidationError:
                pass

        errors: list[str] = []
        last_raw = ""

        # Check if Gemini model — also rate-limited via semaphore to avoid API bursts
        if self.model.startswith("gemini-"):
            async with _global_semaphore:
                for attempt in range(1, self.max_retries + 1):
                    logger.info(
                        "Async Gemini attempt %d/%d for model=%s schema=%s",
                        attempt, self.max_retries, self.model, schema.__name__,
                    )
                    try:
                        last_raw = await self._query_gemini_async(prompt, system_prompt=system_prompt, schema=schema)
                    except Exception as e:
                        logger.warning("Gemini async query failed on attempt %d: %s", attempt, e)
                        errors.append(f"API error: {_sanitize_error_message(e)}")
                        await self._sleep_with_backoff_async(attempt)
                        continue

                    if not last_raw.strip():
                        errors.append("Empty response from model")
                        await self._sleep_with_backoff_async(attempt)
                        continue

                    try:
                        parsed = parse_llm_json_output(last_raw)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning("JSON parse failed on Gemini async attempt %d: %s", attempt, e)
                        errors.append(f"JSON parse error: {e}")
                        await self._sleep_with_backoff_async(attempt)
                        continue

                    try:
                        validated = schema.model_validate(parsed)
                        await response_cache.set_async(prompt, schema.__name__, self.model, parsed)
                        return LLMResponse(
                            success=True,
                            data=validated,
                            raw_output=last_raw,
                            attempts=attempt,
                            errors=errors,
                        )
                    except ValidationError as e:
                        error_messages = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
                        logger.warning(
                            "Pydantic validation failed on Gemini async attempt %d: %s",
                            attempt, error_messages,
                        )
                        errors.extend(error_messages)
                        await self._sleep_with_backoff_async(attempt)
                        continue

            if fallback_factory:
                try:
                    fallback_data = fallback_factory()
                    return LLMResponse(
                        success=False,
                        data=fallback_data,
                        raw_output=last_raw,
                        attempts=self.max_retries,
                        errors=errors,
                    )
                except Exception as e:
                    errors.append(f"Fallback factory failed: {e}")
            return LLMResponse(
                success=False,
                raw_output=last_raw,
                attempts=self.max_retries,
                errors=errors,
            )

        if not system_prompt:
            schema_example = schema.model_json_schema()
            system_prompt = (
                "You are a precise JSON generator. "
                "You MUST respond with valid JSON only — no markdown, no explanations, no extra text. "
                "The JSON must strictly conform to the following schema:\n\n"
                f"{json.dumps(schema_example, indent=2)}\n\n"
                "Output ONLY the JSON object, wrapped in ```json ... ``` if needed, "
                "but ensure it is parseable."
            )

        errors = []
        last_raw = ""


        # Acquire concurrency lock to avoid overloading local CPU/GPU/VRAM
        async with _global_semaphore:
            for attempt in range(1, self.max_retries + 1):
                logger.info(
                    "Async attempt %d/%d for model=%s schema=%s",
                    attempt,
                    self.max_retries,
                    self.model,
                    schema.__name__,
                )

                current_prompt = prompt
                if errors:
                    correction_prompt = (
                        "\n\n---\n"
                        "Your previous response failed validation. "
                        "Here is your previous (invalid) output:\n"
                        f"```\n{last_raw}\n```\n\n"
                        "Validation errors:\n"
                        + "\n".join(f"  - {e}" for e in errors)
                        + "\n\n"
                        "Please correct the JSON to match the required schema exactly. "
                        "Respond with ONLY valid JSON."
                    )
                    current_prompt = prompt + correction_prompt

                try:
                    last_raw = await self._query_ollama_async(
                        current_prompt, system_prompt=system_prompt, format="json"
                    )
                except Exception as e:
                    logger.warning("Ollama async query failed on attempt %d: %s", attempt, e)
                    errors.append(f"API error: {_sanitize_error_message(e)}")
                    await self._sleep_with_backoff_async(attempt)
                    continue

                if not last_raw.strip():
                    errors.append("Empty response from model")
                    await self._sleep_with_backoff_async(attempt)
                    continue

                try:
                    parsed = parse_llm_json_output(last_raw)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("JSON parse failed on async attempt %d: %s", attempt, e)
                    errors.append(f"JSON parse error: {e}")
                    await self._sleep_with_backoff_async(attempt)
                    continue

                try:
                    validated = schema.model_validate(parsed)
                    # Cache the successful parsed response
                    await response_cache.set_async(prompt, schema.__name__, self.model, parsed)
                    return LLMResponse(
                        success=True,
                        data=validated,
                        raw_output=last_raw,
                        attempts=attempt,
                        errors=errors,
                    )
                except ValidationError as e:
                    error_messages = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
                    logger.warning(
                        "Pydantic validation failed on async attempt %d: %s",
                        attempt,
                        error_messages,
                    )
                    errors.extend(error_messages)
                    await self._sleep_with_backoff_async(attempt)
                    continue

        if fallback_factory:
            try:
                fallback_data = fallback_factory()
                return LLMResponse(
                    success=False,
                    data=fallback_data,
                    raw_output=last_raw,
                    attempts=self.max_retries,
                    errors=errors,
                )
            except Exception as e:
                errors.append(f"Fallback factory failed: {e}")

        return LLMResponse(
            success=False,
            raw_output=last_raw,
            attempts=self.max_retries,
            errors=errors,
        )

    async def generate_structured_chat_async(
        self,
        messages: list[dict[str, str]],
        schema: type[T],
        fallback_factory: Callable[[], T] | None = None,
    ) -> LLMResponse:
        """Chat-format version of generate_structured_async."""
        cache_key = json.dumps(messages, sort_keys=True)
        cached = await response_cache.get_async(cache_key, schema.__name__, self.model)
        if cached is not None:
            try:
                validated = schema.model_validate(cached)
                return LLMResponse(
                    success=True,
                    data=validated,
                    raw_output=json.dumps(cached),
                    attempts=1,
                    errors=[],
                )
            except ValidationError:
                pass

        errors: list[str] = []
        last_raw = ""

        async with _global_semaphore:
            for attempt in range(1, self.max_retries + 1):
                logger.info(
                    "Async chat attempt %d/%d for model=%s schema=%s",
                    attempt,
                    self.max_retries,
                    self.model,
                    schema.__name__,
                )

                current_messages = list(messages)
                if errors:
                    current_messages.append({
                        "role": "user",
                        "content": (
                            "Your previous response was invalid. "
                            f"Errors: {'; '.join(errors)}\n"
                            f"Your invalid output:\n{last_raw}\n\n"
                            "Please correct the JSON to match the schema exactly."
                        ),
                    })

                try:
                    last_raw = await self._query_ollama_chat_async(current_messages, format="json")
                except Exception as e:
                    logger.warning("Chat async query failed on attempt %d: %s", attempt, e)
                    errors.append(f"API error: {_sanitize_error_message(e)}")
                    await self._sleep_with_backoff_async(attempt)
                    continue

                if not last_raw.strip():
                    errors.append("Empty response from model")
                    await self._sleep_with_backoff_async(attempt)
                    continue

                try:
                    parsed = parse_llm_json_output(last_raw)
                except (json.JSONDecodeError, ValueError) as e:
                    errors.append(f"JSON parse error: {e}")
                    await self._sleep_with_backoff_async(attempt)
                    continue

                try:
                    validated = schema.model_validate(parsed)
                    await response_cache.set_async(cache_key, schema.__name__, self.model, parsed)
                    return LLMResponse(
                        success=True,
                        data=validated,
                        raw_output=last_raw,
                        attempts=attempt,
                        errors=errors,
                    )
                except ValidationError as e:
                    error_messages = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
                    errors.extend(error_messages)
                    await self._sleep_with_backoff_async(attempt)
                    continue

        if fallback_factory:
            try:
                fallback_data = fallback_factory()
                return LLMResponse(
                    success=False,
                    data=fallback_data,
                    raw_output=last_raw,
                    attempts=self.max_retries,
                    errors=errors,
                )
            except Exception as e:
                errors.append(f"Fallback factory failed: {e}")

        return LLMResponse(
            success=False,
            raw_output=last_raw,
            attempts=self.max_retries,
            errors=errors,
        )


def default_resume_fallback() -> ResumeAnalysisResult:
    """Return a safe default when all retries are exhausted."""
    from src.models import BulletPointImprovement, SkillAnalysis, SkillCategory, SkillGap

    return ResumeAnalysisResult(
        target_role="unknown",
        skill_analysis=SkillAnalysis(
            missing_skills=[
                SkillGap(
                    skill_name="error_processing",
                    category=SkillCategory.TECHNICAL,
                    importance="Model failed to analyze the resume",
                    suggested_resource=None,
                )
            ],
            matching_score=0.0,
            bullet_point_improvements=[
                BulletPointImprovement(
                    original="N/A",
                    improved="N/A",
                    rationale="Model failed to generate improvements after retries",
                )
            ],
            strengths=["Analysis could not be completed"],
        ),
        overall_recommendation="Please retry the analysis. The model encountered a parsing error.",
    )
