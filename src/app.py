"""
FastAPI application entrypoint for the local AI assistant.
Integrates modular routers, configures middlewares, and serves static files.
"""

from __future__ import annotations

import csv
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.config import settings
from src.routers import resume, interview, rag

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    models_available: list[str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting Local AI Assistant API")
    yield
    logger.info("Shutting down Local AI Assistant API")
    from src.assistant import close_async_client
    await close_async_client()


app = FastAPI(
    title="Local AI Assistant — Offline SLM",
    description="Private resume optimizer & mock interviewer powered by local Ollama models",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # CSP: Allow self, cdnjs (for pdf.js), and google fonts, and connect-src for ollama and gemini
    csp_value = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' http://localhost:* https://generativelanguage.googleapis.com; "
        "img-src 'self' data:;"
    )
    response.headers["Content-Security-Policy"] = csp_value
    return response


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    # Limit requests to prevent memory exhaustion DoS
    MAX_SIZE = settings.MAX_UPLOAD_SIZE
    max_size_mb = MAX_SIZE / (1024 * 1024)
    error_msg = f"Request payload too large (max {max_size_mb:.1f}MB)"

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_SIZE:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=413,
                    content={"detail": error_msg}
                )
        except ValueError:
            pass

    # Enforce size limits on chunked requests
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
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=413,
                content={"detail": error_msg}
            )
        raise e


# Include routers
app.include_router(resume.router)
app.include_router(interview.router)
app.include_router(rag.router)

# Mount static files and serve index.html
app.mount("/static", StaticFiles(directory="src/static"), name="static")


@app.get("/")
async def read_index():
    """Serve the single-page application frontend."""
    return FileResponse("src/static/index.html")


@app.get("/benchmarks", tags=["benchmarks"])
async def get_benchmarks():
    """Return the combined model comparison benchmark results."""
    csv_path = Path("benchmarks/benchmark_results_all.csv")
    if not csv_path.exists():
        return {"success": False, "error": "Benchmark results not found. Please run the benchmarks first."}

    results = []
    try:
        with csv_path.open(mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                processed_row = {}
                for k, v in row.items():
                    if v == "":
                        processed_row[k] = None
                    elif k in ["prompt_length_chars", "prompt_length_tokens_est", "response_length_chars", "response_length_tokens_est"]:
                        processed_row[k] = int(v)
                    elif k in ["time_to_first_token_s", "total_generation_time_s", "tokens_per_second", "peak_vram_mb", "peak_ram_mb"]:
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
        raise HTTPException(status_code=500, detail=f"Error reading benchmark results: {e}")


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check():
    """Basic health check — verifies Ollama is reachable and lists available models."""
    from src.assistant import get_async_client

    models = []
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

    # Remove duplicates but keep order
    seen = set()
    unique_models = [x for x in models if not (x in seen or seen.add(x))]

    status_str = "ok"
    return HealthResponse(status=status_str, models_available=unique_models)
