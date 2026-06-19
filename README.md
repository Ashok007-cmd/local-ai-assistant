# Local AI Assistant — Offline Resume Optimizer & Mock Interviewer

[![CI](https://github.com/Ashok007-cmd/local-ai-assistant/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Ashok007-cmd/local-ai-assistant/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com)

A **private-by-design** AI assistant that runs entirely on your local machine. Optimize your resume, practice mock interviews with real-time streaming feedback, and search your own documents — all without sending a single character to the cloud.

Powered by **Ollama** (local SLMs) with optional **Google Gemini** fallback.

---

## Features

| Feature | Details |
|---|---|
| **Resume Optimizer** | Skill gap analysis, match score (0–100), bullet-point rewrites, format issue detection |
| **Mock Interviewer** | Role-tailored questions (behavioral / technical / STAR), real-time streaming coaching feedback |
| **Voice Mode** | Speak answers via Web Speech API; questions are read aloud via Speech Synthesis |
| **PDF Parser** | Client-side PDF text extraction via PDF.js — file never leaves the browser |
| **RAG Search** | SQLite FTS5 full-text search over indexed documents for context retrieval |
| **Multi-language UI** | English, Spanish, German — all labels, prompts, and coaching text localized |
| **Model Benchmarks** | Built-in performance dashboard comparing TPS, TTFT, VRAM, and JSON compliance rates |
| **Session History** | Past analyses and interviews stored in browser IndexedDB (no server-side storage) |
| **Local Cache** | SQLite-backed LLM response cache; zero-wait on repeated identical queries |

---

## Architecture

```
┌─────────────────────────────┐
│     Browser SPA (Vanilla JS)│
│  PDF.js · IndexedDB · SSE   │
└──────────────┬──────────────┘
               │ HTTP / EventStream
               ▼
┌─────────────────────────────┐
│   FastAPI Backend (Python)  │
│  /analyze-resume            │
│  /interview/generate-*      │
│  /interview/submit-answer-  │
│    stream (SSE)             │
│  /api/rag/{index,search,    │
│    clear}                   │
│  /health  /benchmarks       │
└──────┬───────────────┬──────┘
       │               │
  ┌────▼────┐    ┌─────▼──────┐
  │ Ollama  │    │Google Gemini│
  │ (local) │    │  (optional) │
  └─────────┘    └────────────┘
       │
  ┌────▼────────────────────┐
  │ SQLite (WAL mode)       │
  │  • query_cache (LLM)    │
  │  • rag_documents_fts    │
  └─────────────────────────┘
```

**Key design decisions:**
- Single Uvicorn worker + asyncio semaphore (`LLM_MAX_CONCURRENCY`) keeps local GPU/CPU load stable.
- Pydantic schema enforcement with auto-retry loop (up to `LLM_MAX_RETRIES`) corrects malformed LLM output automatically.
- All LLM responses are cached by `sha256(prompt + schema + model)` with configurable TTL.
- RAG index lives in a **separate** SQLite file from the cache to avoid write-lock contention.

---

## Quick Start

### Prerequisites

- Python **3.10 or later**
- [Ollama](https://ollama.com/download) installed and running (for local models)
- *(Optional)* A Google Gemini API key for cloud fallback

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
```

Edit `.env` to set your preferences (all settings have sensible defaults):

```env
# Required only for Gemini cloud models
GEMINI_API_KEY=your_key_here

# Local Ollama URL (default works for standard install)
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=llama3.2:3b
```

### 3 — Pull a model (Ollama)

```bash
ollama pull llama3.2:3b        # 2 GB — fast, good quality
ollama pull gemma3:4b          # 3 GB — excellent JSON compliance
ollama pull mistral:7b         # 4 GB — best quality
```

### 4 — Run

```bash
uvicorn src.app:app --reload
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## Docker

```bash
# Build and start
docker-compose up --build

# With Gemini key
GEMINI_API_KEY=your_key docker-compose up --build
```

The app will be available at **http://localhost:8000**. Ollama must still be running on the host (the compose file maps `host.docker.internal → host-gateway` automatically).

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Ollama + Gemini connectivity check, lists available models |
| `POST` | `/analyze-resume` | Full resume analysis against a target role |
| `POST` | `/interview/generate-questions` | Generate one tailored interview question |
| `POST` | `/interview/submit-answer` | Structured feedback on a submitted answer |
| `POST` | `/interview/submit-answer-stream` | Real-time SSE streaming coaching + metrics |
| `POST` | `/api/rag/index` | Index a document into the FTS5 search index |
| `POST` | `/api/rag/search` | Full-text search over indexed documents |
| `DELETE` | `/api/rag/clear` | Clear all indexed documents |
| `GET` | `/benchmarks` | Benchmark results CSV as JSON |

Interactive API docs: **[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## Supported Models

| Model | Size | Best for |
|---|---|---|
| `llama3.2:3b` | 2 GB | Speed, low-RAM systems |
| `qwen2.5:3b` | 2 GB | JSON compliance, multilingual |
| `gemma3:4b` | 3 GB | Balanced quality + speed |
| `phi4-mini:latest` | 3 GB | Reasoning tasks |
| `mistral:7b` | 4 GB | Highest response quality |
| `gemini-2.5-flash` | Cloud | Zero local GPU required |

---

## Configuration Reference

All settings are environment variables (set in `.env`):

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `DEFAULT_MODEL` | `llama3.2:3b` | Model used when none is specified |
| `LLM_TIMEOUT` | `120.0` | Per-request timeout in seconds |
| `LLM_MAX_RETRIES` | `3` | Retry attempts for invalid LLM output |
| `LLM_MAX_CONCURRENCY` | `1` | Max simultaneous inference requests |
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key (optional) |
| `CACHE_DB_PATH` | `benchmarks/cache.db` | LLM response cache SQLite path |
| `RAG_DB_PATH` | `benchmarks/rag.db` | RAG FTS5 index SQLite path |
| `CACHE_TTL_HOURS` | `24` | Cache entry lifetime in hours |
| `CORS_ORIGINS` | `http://localhost:8000,...` | Allowed CORS origins (comma-separated) |
| `MAX_UPLOAD_SIZE` | `2097152` | Max request body size in bytes (2 MB) |

---

## Running Tests

```bash
pytest -v --cov=src
```

49 tests covering: Pydantic models, JSON parsing, retry logic, async operations, cache, RAG, streaming SSE, i18n, security headers, and size-limit middleware.

---

## Project Structure

```
local-ai-assistant/
├── src/
│   ├── app.py           # FastAPI entrypoint, middlewares, lifespan
│   ├── assistant.py     # LLMClient — Ollama + Gemini, retry, streaming, cache
│   ├── cache.py         # SQLite WAL response cache
│   ├── config.py        # Settings loaded from environment
│   ├── models.py        # Pydantic schemas (resume, interview, RAG)
│   ├── rag_index.py     # SQLite FTS5 full-text search index
│   ├── routers/
│   │   ├── resume.py    # /analyze-resume
│   │   ├── interview.py # /interview/* (generate, submit, stream)
│   │   └── rag.py       # /api/rag/{index,search,clear}
│   └── static/
│       ├── index.html   # Single-page dashboard
│       ├── app.js       # Frontend logic (IndexedDB, SSE, PDF.js, i18n)
│       └── styles.css   # Dark-glass UI design system
├── benchmarks/          # Benchmark runner + CSV results
├── tests/               # pytest suite (49 tests)
├── Dockerfile           # Multi-stage, non-root user
├── docker-compose.yml   # App + volume mapping
├── requirements.txt     # Python dependencies
└── pyproject.toml       # Ruff + Black + pytest config
```

---

## Security

- **No telemetry**: All inference runs locally. Resume text never leaves your machine when using Ollama.
- **Request size limit**: Payloads over 2 MB are rejected with HTTP 413.
- **Security headers**: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and a scoped `Content-Security-Policy` on every response.
- **Non-root Docker**: Container runs as uid `10001` (non-root user `appuser`).
- **No innerHTML with untrusted content**: All LLM-generated text is inserted via DOM `textContent` to prevent XSS.
- **CORS**: Defaults to localhost origins only; configure `CORS_ORIGINS` for production.

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) and follow the [Code of Conduct](CODE_OF_CONDUCT.md).

1. Fork → feature branch → PR against `main`
2. Run `ruff check src/ tests/` and `pytest` before opening a PR
3. The CI matrix tests Python 3.10, 3.11, and 3.12

---

## License

MIT — see [LICENSE](LICENSE).
