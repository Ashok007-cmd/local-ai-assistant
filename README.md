# Local AI Assistant — Offline Resume Optimizer & Mock Interviewer

[![CI](https://github.com/Ashok007-cmd/local-ai-assistant/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Ashok007-cmd/local-ai-assistant/actions/workflows/ci.yml)
[![Docker](https://github.com/Ashok007-cmd/local-ai-assistant/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Ashok007-cmd/local-ai-assistant/pkgs/container/local-ai-assistant)
[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063)](https://docs.pydantic.dev)
[![Coverage](https://img.shields.io/badge/coverage-72%25-yellowgreen)](tests/)
[![Security Audit](https://img.shields.io/badge/security%20audit-passed-brightgreen)](SECURITY.md)
[![Version](https://img.shields.io/badge/version-1.2.1-blue)](CHANGELOG.md)

> **Private by design.** A production-grade AI assistant that runs entirely on your local machine — no cloud, no telemetry, no data leaving your device. Optimize resumes, practice interviews with real-time streaming coaching, and search your documents using local SLMs via Ollama.

---

## Table of Contents

- [Why This Project](#why-this-project)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Docker](#docker)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Supported Models](#supported-models)
- [Security](#security)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)
- [Benchmarks](#benchmarks)
- [Contributing](#contributing)
- [License](#license)

---

## Why This Project

Most AI tools send your resume, job history, and personal data to third-party servers. This project eliminates that risk entirely — all inference runs on your own GPU/CPU through [Ollama](https://ollama.com), with an optional Google Gemini fallback when cloud is acceptable.

**Built to showcase:**
- End-to-end LLM system design with structured output enforcement and retry loops
- Async FastAPI backend with streaming SSE, semaphore-based concurrency control, and SQLite WAL caching
- Security-first architecture: rate limiting, CSP headers, XSS hardening, CORS hygiene, non-root Docker
- Full test coverage across models, retry logic, streaming, i18n, cache, and security headers
- Production Python patterns: Pydantic v2 `BaseSettings`, `asyncio.to_thread`, shared client factory

---

## Features

| Feature | Details |
|---|---|
| **Resume Optimizer** | Skill gap analysis, match score (0–100), bullet-point rewrites with rationale, format issue detection |
| **Mock Interviewer** | Role-tailored behavioral / technical / situational / STAR questions generated from your resume |
| **Streaming Coaching** | Real-time SSE coaching feedback stream followed by structured JSON metrics block |
| **Voice Mode** | Speak answers via Web Speech API; questions read aloud via Speech Synthesis |
| **PDF Parser** | Client-side PDF text extraction via PDF.js — file bytes never leave the browser |
| **RAG Document Search** | SQLite FTS5 full-text index with upsert semantics and BM25 ranking |
| **Multi-language UI** | English, Spanish, German — all labels, prompts, and coaching text localized |
| **Session History** | Past analyses and interviews stored in browser IndexedDB (zero server-side storage) |
| **Response Cache** | SHA-256-keyed SQLite WAL cache; zero-wait on repeated identical queries with configurable TTL |
| **Model Benchmarks** | Built-in dashboard comparing TPS, TTFT, VRAM, RAM, and JSON compliance rates across models |
| **Rate Limiting** | Sliding-window rate limiter (per IP, configurable RPM) returns HTTP 429 with `Retry-After` |
| **Dual Provider** | Automatic Ollama → Gemini fallback routing by model name prefix |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│           Browser SPA  (Vanilla JS)          │
│  PDF.js · IndexedDB · SSE · Web Speech API  │
└────────────────────┬────────────────────────┘
                     │  HTTP / EventStream (SSE)
                     ▼
┌─────────────────────────────────────────────┐
│         FastAPI Backend  (Python 3.10+)      │
│                                             │
│  Middleware stack (innermost → outermost):  │
│    limit_upload_size  →  add_security_headers│
│    rate_limit_middleware  →  CORSMiddleware  │
│                                             │
│  Routers:                                   │
│    POST  /analyze-resume                    │
│    POST  /interview/generate-questions      │
│    POST  /interview/submit-answer           │
│    POST  /interview/submit-answer-stream    │
│    POST  /api/rag/{index,search}            │
│    DELETE /api/rag/clear                    │
│    GET   /health  /benchmarks               │
└──────────┬──────────────────────┬───────────┘
           │                      │
     ┌─────▼──────┐        ┌──────▼──────────┐
     │  Ollama    │        │  Google Gemini  │
     │  (local)   │        │  (optional)     │
     └─────┬──────┘        └─────────────────┘
           │
  ┌────────▼──────────────────────┐
  │   SQLite  (WAL mode)          │
  │  • query_cache  (LLM cache)   │
  │  • rag_documents_fts (FTS5)   │
  └───────────────────────────────┘
```

**Key design decisions:**

| Decision | Rationale |
|---|---|
| Single Uvicorn worker + `asyncio.Semaphore` | Prevents GPU/VRAM overload under concurrent requests |
| Pydantic schema validation + auto-retry loop | Corrects malformed LLM JSON automatically (up to `LLM_MAX_RETRIES`) |
| `sha256(prompt + schema + model)` cache key | Deterministic, collision-resistant, covers schema changes |
| Separate SQLite files for cache and RAG | Eliminates WAL write-lock contention between two hot write paths |
| `asyncio.to_thread` for SQLite ops | Keeps the async event loop unblocked during I/O |
| RAG upsert semantics | Re-indexing the same title replaces instead of duplicating |
| Per-IP sliding-window rate limiter | Pure-stdlib, no Redis dependency for local deployments |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.10+, FastAPI 0.115+, Uvicorn |
| **AI / LLM** | Ollama (local), Google Gemini API (optional) |
| **Validation** | Pydantic v2, `pydantic-settings` |
| **HTTP Client** | httpx (async + sync, shared client lifecycle) |
| **Database** | SQLite (WAL mode) — response cache + FTS5 RAG index |
| **Frontend** | Vanilla JS, IndexedDB, Web Speech API, PDF.js, SSE |
| **DevOps** | Docker (multi-stage, non-root), GitHub Actions CI matrix |
| **Quality** | pytest, pytest-asyncio, pytest-cov, ruff, Black |

---

## Quick Start

### Prerequisites

- Python **3.10 or later**
- [Ollama](https://ollama.com/download) installed and running
- *(Optional)* Google Gemini API key for cloud fallback

### 1 — Clone & install

```bash
git clone https://github.com/Ashok007-cmd/local-ai-assistant.git
cd local-ai-assistant
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2 — Configure

```bash
cp .env.example .env
# Edit .env — all settings have safe defaults, only GEMINI_API_KEY is optional
```

### 3 — Pull a model

```bash
ollama pull llama3.2:3b        # 2 GB — fast, low RAM
ollama pull gemma3:4b          # 3 GB — best JSON compliance
ollama pull mistral:7b         # 4 GB — highest quality
```

### 4 — Run

```bash
uvicorn src.app:app --reload
```

Open **http://localhost:8000** — the SPA loads immediately.

> **Interactive API docs:** http://localhost:8000/docs

---

## Docker

```bash
# Build and start
docker-compose up --build

# With Gemini cloud fallback
GEMINI_API_KEY=your_key docker-compose up --build

# Production (no reload)
docker run -p 8000:8000 ghcr.io/ashok007-cmd/local-ai-assistant:main
```

The compose file maps `host.docker.internal → host-gateway` so the container can reach Ollama on your host.

The image runs as **uid 10001** (non-root `appuser`), uses a multi-stage build to minimise attack surface, and includes a Python `urllib` healthcheck to avoid adding `curl` to the image.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Connectivity check — returns available models and rate-limit config |
| `POST` | `/analyze-resume` | Full resume analysis: skill gaps, match score, bullet rewrites, format issues |
| `POST` | `/interview/generate-questions` | One tailored interview question from resume + role |
| `POST` | `/interview/submit-answer` | Structured `InterviewFeedback` (score, strengths, missed keywords) |
| `POST` | `/interview/submit-answer-stream` | **SSE stream** — coaching text chunks then `===METRICS===` JSON block |
| `POST` | `/api/rag/index` | Upsert a document into the FTS5 search index |
| `POST` | `/api/rag/search` | BM25-ranked full-text search over indexed documents |
| `DELETE` | `/api/rag/clear` | Remove all indexed documents |
| `GET` | `/benchmarks` | SLM benchmark CSV parsed as JSON (TPS, TTFT, VRAM, compliance) |

### Example — Resume Analysis

```bash
curl -s -X POST http://localhost:8000/analyze-resume \
  -H "Content-Type: application/json" \
  -d '{
    "resume_text": "Senior Python developer, 6 years experience...",
    "target_role": "Staff Engineer",
    "model": "gemma3:4b",
    "language": "english"
  }' | python -m json.tool
```

### Example — Streaming Interview Feedback

```bash
curl -N -X POST http://localhost:8000/interview/submit-answer-stream \
  -H "Content-Type: application/json" \
  -d '{
    "question": {"question":"Tell me about a system you designed","question_type":"technical","difficulty":"hard","target_skill":"system design","ideal_answer_keywords":["scalability","trade-offs","latency"]},
    "answer": "I designed a distributed cache layer...",
    "model": "llama3.2:3b"
  }'
```

Response events: `coaching` (streaming text), `coaching_done`, `metrics` (JSON), `error`.

---

## Configuration

All settings are environment variables (loaded from `.env` via `pydantic-settings`):

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `DEFAULT_MODEL` | `llama3.2:3b` | Model when none is specified in the request |
| `LLM_TIMEOUT` | `120.0` | Per-request timeout in seconds |
| `LLM_MAX_RETRIES` | `3` | Retry attempts for invalid/malformed LLM output |
| `LLM_MAX_CONCURRENCY` | `1` | Max simultaneous inference requests (semaphore) |
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key — enables cloud models |
| `API_KEY` | *(empty)* | Shared-secret key. When set, requires a matching `X-API-Key` header on `/analyze-resume`, `/interview/*`, `/api/rag/*` |
| `CACHE_DB_PATH` | `benchmarks/cache.db` | SQLite path for the LLM response cache |
| `RAG_DB_PATH` | `benchmarks/rag.db` | SQLite path for the FTS5 RAG index |
| `CACHE_TTL_HOURS` | `24` | Cache entry lifetime in hours |
| `CORS_ORIGINS` | `http://localhost:8000,...` | Comma-separated allowed CORS origins |
| `MAX_UPLOAD_SIZE` | `2097152` | Max request body in bytes (2 MB) |
| `RATE_LIMIT_RPM` | `60` | Max requests per minute per IP on inference routes (0 = disabled); `/health`, `/docs`, `/static/*` are exempt |
| `LOG_FORMAT` | `text` | Set to `json` for structured machine-readable logs |

---

## Supported Models

| Model | Size | Best for |
|---|---|---|
| `llama3.2:3b` | 2 GB | Speed, low-RAM systems |
| `qwen2.5:3b` | 2 GB | JSON compliance, multilingual |
| `gemma3:4b` | 3 GB | Balanced quality + JSON reliability |
| `phi4-mini:latest` | 3 GB | Reasoning-heavy tasks |
| `mistral:7b` | 4 GB | Highest response quality |
| `gemini-2.5-flash` | Cloud | Zero local GPU required |
| `gemini-1.5-pro` | Cloud | Most capable cloud option |

Models prefixed with `gemini-` are automatically routed to the Gemini API; all others go to Ollama.

---

## Security

This project has undergone an internal security audit (application-layer pentest + dependency/SAST scan). See **[SECURITY.md](SECURITY.md)** for the full findings and fixes — including one confirmed-via-live-request critical issue (Gemini API key disclosure through error messages) that has since been patched and regression-tested.

| Control | Implementation |
|---|---|
| **No telemetry** | All inference runs locally via Ollama. Resume text never leaves the machine. |
| **XSS prevention** | `escapeHtml()` applied to all `innerHTML` interpolations of LLM/user data in the frontend |
| **Content Security Policy** | Scoped CSP on every response (self + cdnjs + Google Fonts only), no `'unsafe-inline'` on `script-src` or `style-src` — all UI wiring uses `addEventListener` and CSS classes |
| **Security headers** | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `X-XSS-Protection`, `Permissions-Policy` |
| **Rate limiting** | Sliding-window per-IP rate limiter, scoped to inference/mutating routes only; HTTP 429 with `Retry-After: 60` on breach |
| **Optional API-key auth** | Set `API_KEY` to require a matching `X-API-Key` header on `/analyze-resume`, `/interview/*`, and `/api/rag/*` — required once the app is reachable beyond `127.0.0.1` |
| **Request size limit** | Payloads > 2 MB rejected with HTTP 413 (configurable via `MAX_UPLOAD_SIZE`) |
| **CORS** | Defaults to localhost only, credential-less; never ships with wildcard `*` |
| **Non-root Docker** | Container runs as uid `10001` (`appuser`), not root |
| **No innerHTML with untrusted content** | LLM text uses DOM `textContent` or `escapeHtml()` — never raw interpolation |
| **Secrets never in URLs or error responses** | Gemini API key travels as an `x-goog-api-key` header, never a URL query param; all outbound-request exceptions are sanitized before reaching a client-facing error |
| **Model allow-listing** | Gemini model names are validated against a fixed allow-list before being used to build an outbound request URL |
| **Dependency scanning** | `pip-audit` + `bandit` run as part of the audit workflow; CI runs `pip-audit` on every push |

---

## Running Tests

```bash
# Full suite with coverage
pytest -v --cov=src --cov-report=term-missing

# Specific test class
pytest tests/test_structured.py::TestRetryMechanism -v

# Watch mode (requires pytest-watch)
ptw tests/
```

**58 tests** covering:

- Pydantic model validation and field bounds
- JSON parsing with markdown fences, trailing text, nested objects
- Retry loop (JSON errors, validation errors, empty responses, exhausted retries)
- Async structured generation and cache integration
- Semaphore concurrency serialisation
- FastAPI routes (health, benchmarks, RAG, streaming SSE)
- Security headers (CSP, X-Frame-Options, X-XSS-Protection, Permissions-Policy)
- i18n fallbacks (German and Spanish streaming error messages)
- Request size-limit middleware (HTTP 413)
- Gemini schema conversion (`resolve_schema_refs`, `convert_to_gemini_schema`)
- Security regressions: API-key never appears in outbound URLs or client-facing errors, Gemini model allow-listing, optional `X-API-Key` auth, rate-limit path exemptions

---

## Project Structure

```
local-ai-assistant/
├── src/
│   ├── app.py              # FastAPI app, middleware stack, lifespan hooks
│   ├── assistant.py        # LLMClient — Ollama + Gemini, retry, streaming, cache
│   ├── auth.py             # Optional X-API-Key enforcement (no-op unless API_KEY is set)
│   ├── cache.py            # SQLite WAL response cache (thread-local connections)
│   ├── config.py           # Pydantic BaseSettings — typed env config with .env loading
│   ├── models.py           # Pydantic schemas: ResumeAnalysisResult, InterviewQuestion, etc.
│   ├── rag_index.py        # SQLite FTS5 full-text search index with upsert semantics
│   └── routers/
│       ├── _client.py      # Shared LLMClient factory (get_llm_client)
│       ├── resume.py       # POST /analyze-resume
│       ├── interview.py    # POST /interview/* (generate, submit, stream)
│       └── rag.py          # POST/DELETE /api/rag/*
├── src/static/
│   ├── index.html          # Single-page dashboard shell
│   ├── app.js              # Frontend logic (IndexedDB, SSE, PDF.js, i18n, escapeHtml)
│   └── styles.css          # Dark-glass UI design system
├── tests/
│   ├── test_structured.py  # Core model, retry, async, cache, RAG, route tests
│   └── test_new_features.py# Gemini routing, streaming SSE, i18n, security header tests
├── benchmarks/
│   ├── benchmark_runner.py # SLM benchmark harness (TPS, TTFT, VRAM)
│   └── run_benchmarks.sh   # Shell script to run all model benchmarks
├── .github/
│   ├── workflows/
│   │   ├── ci.yml          # CI matrix: Python 3.10 / 3.11 / 3.12, ruff, pytest, coverage
│   │   └── docker-publish.yml # Publish to GHCR on push to main or release tag
│   └── ISSUE_TEMPLATE/     # Bug report and feature request templates
├── Dockerfile              # Multi-stage (builder + runner), non-root uid 10001
├── docker-compose.yml      # App + host.docker.internal Ollama bridge
├── requirements.txt        # Runtime + test dependencies
├── pyproject.toml          # ruff (E,W,F,I,B,UP) + Black + pytest-asyncio config
├── .env.example            # All config variables with safe defaults (no wildcard CORS)
├── CHANGELOG.md            # Keep-a-Changelog format, semver
├── SECURITY.md             # Audit findings register, scan results, fix status
├── CONTRIBUTING.md         # Fork → branch → PR workflow
└── CODE_OF_CONDUCT.md      # Contributor Covenant
```

---

## Benchmarks

Results from benchmarking on a typical developer laptop (no dedicated GPU):

| Model | TPS | TTFT | JSON Compliance | RAM |
|---|---|---|---|---|
| `gemma3:4b` | ~22 t/s | ~0.8 s | 100% | ~3.2 GB |
| `llama3.2:3b` | ~28 t/s | ~0.6 s | 96% | ~2.1 GB |
| `qwen2.5:3b` | ~25 t/s | ~0.7 s | 98% | ~2.0 GB |
| `mistral:7b` | ~12 t/s | ~1.4 s | 94% | ~4.1 GB |

> Run your own benchmarks: `bash benchmarks/run_benchmarks.sh`
> Results available at `GET /benchmarks` in the API and in the dashboard UI.

*TPS = tokens per second · TTFT = time to first token · JSON Compliance = % of responses that parsed without retry*

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and follow the [Code of Conduct](CODE_OF_CONDUCT.md).

```bash
# Before opening a PR
ruff check src/ tests/    # Lint
pytest -v --cov=src       # Tests
```

1. Fork → feature branch → PR against `main`
2. CI must pass (ruff + pytest on Python 3.10, 3.11, 3.12)
3. Add or update tests for any new behaviour

---

## License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  Built with FastAPI · Pydantic · Ollama · SQLite · Vanilla JS<br>
  <a href="https://github.com/Ashok007-cmd/local-ai-assistant">github.com/Ashok007-cmd/local-ai-assistant</a>
</p>
