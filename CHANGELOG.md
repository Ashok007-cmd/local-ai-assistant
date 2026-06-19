# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
