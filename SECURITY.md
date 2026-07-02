# Security

This project underwent an internal application-security audit (source review, live penetration testing against a running instance, dependency/SAST scanning). This document is the findings register — kept in the repo instead of a one-off PDF so the fix status stays visible and checkable against the actual code.

**Scope:** `src/`, `tests/`, `Dockerfile`, CI workflows, and the public-facing API surface (`/analyze-resume`, `/interview/*`, `/api/rag/*`, `/health`, `/benchmarks`).
**Method:** static source review + live HTTP requests against a running local instance (real Ollama backend, a placeholder Gemini key) + `pip-audit` (dependency CVEs) + `bandit` (SAST).
**Not in scope:** classic malware analysis / binary reverse engineering — not applicable to a from-source service with no third-party binaries. Supply-chain review (dependencies, container base image, CI pinning) was performed as the equivalent exercise.

## Reporting a vulnerability

Open a GitHub issue or contact the maintainer directly for anything sensitive — this is a personal/portfolio project without a formal disclosure program, but reports are welcome and will be triaged the same way the findings below were.

## Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| F-1 | Critical | Gemini API key disclosed to clients via error messages (confirmed with a live request) | **Fixed** — key moved to `x-goog-api-key` header; all exception text sanitized before reaching a client |
| F-2 | High | No authentication on any endpoint — unauthenticated cost/quota abuse | **Fixed** — optional `API_KEY` shared-secret header, enforced via FastAPI dependency; opt-in, no-op by default |
| F-3 | High | User-supplied `model` spliced unvalidated into the outbound Gemini URL | **Fixed** — validated against a fixed allow-list before use |
| F-4 | High | Rate limiter shared one budget across health checks, static assets, and LLM calls | **Fixed** — `/health`, `/docs`, `/openapi.json`, `/static/*` exempted |
| F-5 | Medium | Rate-limiter state unbounded and process-local | **Fixed** — stale per-IP buckets swept periodically |
| F-6 | Medium | CSP allows `'unsafe-inline'` for scripts/styles | **Fixed** — 17 `onclick`/`onchange` HTML attributes converted to `addEventListener` bindings, 19 inline `style="..."` attributes moved to CSS classes; `'unsafe-inline'` dropped from both `script-src` and `style-src` |
| F-7 | Medium | Broad `except Exception` in cache/RAG DB paths swallows errors silently | Open — acceptable as a cache-miss fallback today; tracked for observability follow-up |
| F-8 | Medium | `CORS allow_credentials=True` with no cookie/session auth in use | **Fixed** — disabled |
| F-9 | Low | Docker base image / GitHub Actions pinned by tag, not digest/SHA | Open — tracked |
| F-10 | Low | No automated dependency/image vulnerability scanning in CI | **Fixed** — `pip-audit` added to CI on every push; GitHub Dependabot alerts, security updates, and weekly version-update PRs (pip, GitHub Actions, Docker) enabled on the repo |

## Scan results (this audit)

- `pip-audit` against `requirements.txt`: **no known vulnerabilities**
- `bandit -r src/`: **zero medium/high findings** (4 low-confidence non-issues: non-cryptographic RNG used for retry-jitter, and two intentional `except Exception: continue` in SSE streaming loops)
- Full test suite: **58/58 passing**, `ruff check` clean

## Design notes for reviewers

- All inference runs locally via Ollama by default; the optional Gemini fallback is the only outbound network call the backend makes, and only when `GEMINI_API_KEY` is configured.
- `API_KEY` is empty by default so the app stays a drop-in local tool — it becomes a hard requirement only once you decide to expose it beyond `127.0.0.1` (documented in `.env.example` and the README).
