"""
FastAPI application entrypoint for the local AI assistant.
Integrates modular routers, configures middlewares, and serves static files.
"""

from __future__ import annotations

import collections
import csv
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import settings
from src.routers import interview, rag, resume

_log_fmt = os.getenv("LOG_FORMAT", "text")
if _log_fmt == "json":
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}',
    )
else:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory sliding-window rate limiter (per remote IP, requests per minute)
# ---------------------------------------------------------------------------
_rate_buckets: dict[str, collections.deque] = collections.defaultdict(collections.deque)

# Paths that never count against the per-IP rate-limit budget: cheap, high-frequency,
# and not LLM-backed, so they shouldn't compete with expensive inference calls for the
# same request budget (a single page load otherwise burns most of the default 60 rpm).
_RATE_LIMIT_EXEMPT_PREFIXES = ("/static/",)
_RATE_LIMIT_EXEMPT_PATHS = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})


def _is_rate_limit_exempt(path: str) -> bool:
    return path in _RATE_LIMIT_EXEMPT_PATHS or path.startswith(_RATE_LIMIT_EXEMPT_PREFIXES)


_rate_limit_check_count = 0


def _is_rate_limited(ip: str) -> bool:
    """Return True if *ip* has exceeded RATE_LIMIT_RPM in the last 60 seconds."""
    global _rate_limit_check_count
    if settings.RATE_LIMIT_RPM <= 0:
        return False
    now = time.monotonic()
    bucket = _rate_buckets[ip]
    # Evict timestamps older than 60 s
    while bucket and now - bucket[0] > 60.0:
        bucket.popleft()
    limited = len(bucket) >= settings.RATE_LIMIT_RPM
    if not limited:
        bucket.append(now)

    # Bound dict growth: sweep fully-expired IP entries periodically rather than on
    # every request, so long-running processes don't accumulate one entry per client
    # IP forever.
    _rate_limit_check_count += 1
    if _rate_limit_check_count % 256 == 0:
        _evict_stale_buckets(now)

    return limited


def _evict_stale_buckets(now: float) -> None:
    stale = [candidate_ip for candidate_ip, bucket in _rate_buckets.items() if not bucket or now - bucket[-1] > 60.0]
    for candidate_ip in stale:
        del _rate_buckets[candidate_ip]


class HealthResponse(BaseModel):
    status: str
    models_available: list[str]
    rate_limit_rpm: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting Local AI Assistant API (v%s)", app.version)
    yield
    logger.info("Shutting down Local AI Assistant API")
    from src.assistant import close_async_client
    await close_async_client()


app = FastAPI(
    title="Local AI Assistant — Offline SLM",
    description=(
        "**Private-by-design** AI assistant powered by local Ollama models with optional "
        "Google Gemini cloud fallback.\n\n"
        "- Resume text never leaves your machine when using Ollama.\n"
        "- All responses are schema-validated via Pydantic with an auto-retry loop.\n"
        "- SQLite WAL cache eliminates repeat inference cost.\n\n"
        "Interactive docs: [/docs](/docs) · OpenAPI spec: [/openapi.json](/openapi.json)"
    ),
    version="1.2.2",
    contact={
        "name": "Ashok Kumar",
        "url": "https://github.com/Ashok007-cmd/local-ai-assistant",
    },
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    lifespan=lifespan,
    openapi_tags=[
        {"name": "system", "description": "Health checks and system status."},
        {"name": "resume", "description": "Resume optimization and skill-gap analysis."},
        {"name": "interview", "description": "Mock interview generation and streaming feedback."},
        {"name": "rag", "description": "Document indexing and full-text search (SQLite FTS5)."},
        {"name": "benchmarks", "description": "Local SLM performance benchmark results."},
    ],
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Sliding-window rate limiter: rejects excess requests with HTTP 429."""
    if _is_rate_limit_exempt(request.url.path):
        return await call_next(request)
    ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(ip):
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded. Max {settings.RATE_LIMIT_RPM} requests/minute."},
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=()"
    response.headers["X-API-Version"] = app.version

    # No 'unsafe-inline' on script-src or style-src: the frontend has no inline
    # <script>/<style> blocks or onclick=/style= HTML attributes — all UI wiring uses
    # addEventListener (app.js) and CSS classes (styles.css). See SECURITY.md F-6.
    csp_value = (
        "default-src 'self'; "
        "script-src 'self' https://cdnjs.cloudflare.com; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' http://localhost:* https://generativelanguage.googleapis.com; "
        "img-src 'self' data:;"
    )
    response.headers["Content-Security-Policy"] = csp_value
    return response


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """Reject payloads exceeding MAX_UPLOAD_SIZE to prevent memory-exhaustion DoS."""
    MAX_SIZE = settings.MAX_UPLOAD_SIZE
    max_size_mb = MAX_SIZE / (1024 * 1024)
    error_msg = f"Request payload too large (max {max_size_mb:.1f}MB)"

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_SIZE:
                return JSONResponse(status_code=413, content={"detail": error_msg})
        except ValueError:
            pass

    body_size = 0
    original_receive = request._receive

    async def receive_with_limit():
        nonlocal body_size
        message = await original_receive()
        if message["type"] in ("http.request", b"http.request"):
            body_size += len(message.get("body", b""))
            if body_size > MAX_SIZE:
                raise RuntimeError(error_msg)
        return message

    request._receive = receive_with_limit

    try:
        return await call_next(request)
    except RuntimeError as e:
        if str(e) == error_msg:
            return JSONResponse(status_code=413, content={"detail": error_msg})
        raise


# Include routers
app.include_router(resume.router)
app.include_router(interview.router)
app.include_router(rag.router)

# Mount static files and serve index.html
app.mount("/static", StaticFiles(directory="src/static"), name="static")


@app.get("/", include_in_schema=False)
async def read_index():
    """Serve the single-page application frontend."""
    return FileResponse("src/static/index.html")


@app.get("/benchmarks", tags=["benchmarks"], summary="Model benchmark results")
async def get_benchmarks():
    """Return combined SLM benchmark results (TPS, TTFT, VRAM, JSON compliance)."""
    csv_path = Path("benchmarks/benchmark_results_all.csv")
    if not csv_path.exists():
        return {"success": False, "error": "Benchmark results not found. Run benchmarks/run_benchmarks.sh first."}

    results = []
    try:
        with csv_path.open(mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                processed_row: dict = {}
                _INT_KEYS = {
                    "prompt_length_chars", "prompt_length_tokens_est",
                    "response_length_chars", "response_length_tokens_est",
                }
                _FLOAT_KEYS = {
                    "time_to_first_token_s", "total_generation_time_s",
                    "tokens_per_second", "peak_vram_mb", "peak_ram_mb",
                }
                for k, v in row.items():
                    if v == "":
                        processed_row[k] = None
                    elif k in _INT_KEYS:
                        processed_row[k] = int(v)
                    elif k in _FLOAT_KEYS:
                        try:
                            processed_row[k] = float(v)
                        except ValueError:
                            processed_row[k] = v
                    elif k == "success":
                        processed_row[k] = v.lower() == "true"
                    else:
                        processed_row[k] = v
                results.append(processed_row)
        return {"success": True, "data": results}
    except Exception as e:
        logger.error("Error reading benchmark results: %s", e)
        raise HTTPException(status_code=500, detail="Failed to read benchmark results. Check server logs.")


@app.get("/health", response_model=HealthResponse, tags=["system"], summary="Service health check")
async def health_check():
    """Verify Ollama/Gemini connectivity and list available models."""
    from src.assistant import get_async_client

    models: list[str] = []
    gemini_active = bool(settings.GEMINI_API_KEY)
    if gemini_active:
        models.extend(["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"])

    ollama_online = False
    try:
        client = get_async_client()
        resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=3.0)
        resp.raise_for_status()
        ollama_models = [m["name"] for m in resp.json().get("models", [])]
        models.extend(ollama_models)
        ollama_online = True
    except Exception:
        logger.warning("Ollama not reachable during health check")

    if not ollama_online and not gemini_active:
        raise HTTPException(status_code=503, detail="Neither Ollama nor Gemini API is available")

    seen: set[str] = set()
    unique_models = [x for x in models if not (x in seen or seen.add(x))]

    return HealthResponse(
        status="ok",
        models_available=unique_models,
        rate_limit_rpm=settings.RATE_LIMIT_RPM,
    )
