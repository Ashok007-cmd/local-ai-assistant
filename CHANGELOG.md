# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] — 2026-06-28

### Security
- **XSS hardening** — added `escapeHtml()` utility in `app.js`; all 12 `innerHTML` template-literal sites that interpolated LLM-sourced or user-supplied data now escape output, closing a stored-XSS vector
- **CORS default fixed** — `.env.example` no longer ships with `CORS_ORIGINS=*`; defaults to `localhost` only
- **New HTTP security headers** — `X-XSS-Protection: 1; mode=block`, `Permissions-Policy`, and `X-API-Version` added to every response
- **Error message sanitisation** — internal Python exception text is no longer forwarded to API clients; errors are logged server-side only

### Added
- **In-memory rate limiter** — sliding-window middleware (60 req/min per IP by default, configurable via `RATE_LIMIT_RPM`); returns HTTP 429 with `Retry-After: 60` on breach
- **Pydantic `BaseSettings` config** — `src/config.py` migrated from raw `os.getenv()` to `pydantic-settings`; gains `.env` file auto-loading, field-level validators (`gt`, `ge`, `le`), and CORS list coercion
- **RAG upsert semantics** — re-indexing a document with the same title now replaces the existing entry instead of creating duplicates
- **Structured JSON logging** — set `LOG_FORMAT=json` to emit machine-readable log lines (useful for log aggregators)
- **Enhanced OpenAPI docs** — rich description, contact, license, and tag descriptions; `HealthResponse` now includes `rate_limit_rpm`
- **Shared client factory** — `src/routers/_client.py` eliminates the duplicated `_get_client` / `clients` dict that existed in both `resume.py` and `interview.py`

### Changed
- Version bumped to `1.1.0`
- `requirements.txt` adds `pydantic-settings>=2.0.0`

---

## [1.0.0] — 2026-06-19

### Added
- **Resume Optimizer** — skill gap analysis, match score (0–100), bullet-point rewrites, and format issue detection powered by local Ollama models
- **Mock Interviewer** — role-tailored behavioral, technical, and STAR interview questions with real-time streaming coaching feedback via Server-Sent Events
- **Voice Mode** — speak answers via Web Speech API; questions read aloud via Speech Synthesis API
- **RAG Document Search** — index PDF and text documents with SQLite FTS5 full-text search; context injected into LLM prompts automatically
- **Multi-language UI** — English, Spanish, and German localization via a built-in `t()` i18n system
- **Response Cache** — SQLite WAL-mode cache avoids redundant LLM inference calls with configurable TTL
- **Google Gemini Fallback** — optional cloud fallback (`gemini-2.5-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`) when Ollama is unavailable
- **Pydantic v2 structured output** — auto-retry validation loop corrects malformed LLM JSON responses
- **Async concurrency control** — global semaphore limits parallel Ollama/Gemini requests
- **Shared async HTTP client** — single reusable `httpx.AsyncClient` across all request handlers
- **Security headers middleware** — CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- **Upload size limit middleware** — protects against memory exhaustion via configurable `MAX_UPLOAD_SIZE`
- **Benchmark runner** — scripts to measure TTFT, tokens/s, VRAM, and RAM across supported models
- **Docker support** — multi-stage `Dockerfile` with non-root user; `docker-compose.yml` for one-command deployment
- **CI pipeline** — GitHub Actions matrix testing Python 3.10, 3.11, and 3.12 with ruff linting and pytest

### Security
- Replaced all `innerHTML` assignments with `textContent` / `createElement` to prevent XSS from LLM-generated content
- CORS origins restricted to localhost by default (no wildcard `*`)
- RAG index uses a separate SQLite database from the response cache to eliminate lock contention

[1.0.0]: https://github.com/Ashok007-cmd/local-ai-assistant/releases/tag/v1.0.0
