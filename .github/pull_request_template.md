## Summary
<!-- 2–4 bullet points describing what this PR does and why. -->
- 
- 

## Type of change
- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (existing behaviour changes)
- [ ] Security fix
- [ ] Documentation / tooling update
- [ ] Refactor / performance improvement

## How was this tested?
<!-- Describe the test cases you ran or added. -->
- [ ] `pytest -v --cov=src` passes locally
- [ ] `ruff check src/ tests/` passes locally
- [ ] Manual test against Ollama (`ollama pull <model>` + `uvicorn src.app:app --reload`)
- [ ] Docker build tested (`docker-compose up --build`)

## Checklist
- [ ] Code follows the project style (`ruff` + `Black`, line-length 120)
- [ ] New behaviour is covered by tests
- [ ] CHANGELOG.md updated (if user-visible change)
- [ ] README.md updated (if API, config, or feature changed)
- [ ] No secrets, API keys, or `.env` files committed
- [ ] Security implications considered (XSS, injection, CORS, rate limiting)
