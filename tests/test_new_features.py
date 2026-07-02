from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.assistant import (
    ALLOWED_GEMINI_MODELS,
    LLMClient,
    _sanitize_error_message,
    convert_to_gemini_schema,
    resolve_schema_refs,
)
from src.models import InterviewFeedback, InterviewQuestion


@pytest.fixture(autouse=True)
def clear_cache_before_each_test():
    from src.cache import response_cache
    response_cache.clear()

def test_resolve_schema_refs():
    schema = {
        "$defs": {
            "SubModel": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"}
                }
            }
        },
        "type": "object",
        "properties": {
            "sub": {"$ref": "#/$defs/SubModel"}
        }
    }
    resolved = resolve_schema_refs(schema)
    assert "$defs" not in resolved
    assert resolved["properties"]["sub"]["properties"]["field"]["type"] == "string"


def test_convert_to_gemini_schema():
    schema = {
        "$defs": {
            "Category": {
                "type": "string",
                "enum": ["technical", "soft_skill"]
            }
        },
        "type": "object",
        "properties": {
            "name": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "null"}
                ]
            },
            "cat": {"$ref": "#/$defs/Category"}
        },
        "required": ["cat"]
    }
    gemini_schema = convert_to_gemini_schema(schema)
    assert gemini_schema["type"] == "OBJECT"
    assert gemini_schema["properties"]["name"]["type"] == "STRING"
    assert gemini_schema["properties"]["cat"]["type"] == "STRING"
    assert gemini_schema["properties"]["cat"]["enum"] == ["technical", "soft_skill"]


class TestGeminiClientRouting:
    @patch("src.assistant.settings")
    @patch("httpx.Client.post")
    def test_sync_gemini_route(self, mock_post, mock_settings):
        mock_settings.GEMINI_API_KEY = "dummy-key"
        mock_settings.LLM_MAX_RETRIES = 3
        mock_settings.LLM_TIMEOUT = 120.0

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": (
                            '{"score": 8.0, "strengths": ["test"], "weaknesses": ["test"],'
                            ' "suggested_answer_framework": "test", "missed_keywords": []}'
                        )
                    }]
                }
            }]
        }
        mock_post.return_value = mock_response

        client = LLMClient(model="gemini-2.5-flash")
        res = client.generate_structured(
            prompt="Test prompt",
            schema=InterviewFeedback
        )
        assert res.success is True
        assert res.data.score == 8.0
        assert mock_post.call_count == 1

    @pytest.mark.asyncio
    @patch("src.assistant.settings")
    @patch("httpx.AsyncClient.post")
    async def test_async_gemini_route(self, mock_post, mock_settings):
        mock_settings.GEMINI_API_KEY = "dummy-key"
        mock_settings.LLM_MAX_RETRIES = 3
        mock_settings.LLM_TIMEOUT = 120.0

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": (
                            '{"score": 9.5, "strengths": ["test"], "weaknesses": ["test"],'
                            ' "suggested_answer_framework": "test", "missed_keywords": []}'
                        )
                    }]
                }
            }]
        }
        mock_post.return_value = mock_response

        client = LLMClient(model="gemini-2.5-flash")
        res = await client.generate_structured_async(
            prompt="Test prompt",
            schema=InterviewFeedback
        )
        assert res.success is True
        assert res.data.score == 9.5
        assert mock_post.call_count == 1


class TestStreamingRoutes:
    def test_submit_answer_stream_endpoint(self):
        client = TestClient(app)

        AsyncMock()
        async def mock_generator(*args, **kwargs):
            yield "coaching critique text"
            yield "===METRICS==="
            yield (
                '{"score": 8.0, "strengths": ["A"], "weaknesses": ["B"],'
                ' "suggested_answer_framework": "STAR", "missed_keywords": []}'
            )

        mock_client = MagicMock()
        mock_client.stream_raw_async.return_value = mock_generator()

        with patch("src.routers.interview.get_llm_client", return_value=mock_client):
            payload = {
                "question": {
                    "question": "Tell me about yourself",
                    "question_type": "behavioral",
                    "difficulty": "easy",
                    "target_skill": "communication",
                    "ideal_answer_keywords": ["experience", "background"]
                },
                "answer": "My name is John Doe and I have 5 years of software engineering experience.",
                "model": "llama3.2:3b"
            }

            response = client.post("/interview/submit-answer-stream", json=payload)
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            content = response.content.decode("utf-8")
            assert "event: coaching" in content
            assert "event: metrics" in content
            assert "coaching critique text" in content
            assert "score" in content

    def test_request_size_limit_middleware(self):
        client = TestClient(app)
        # Create a payload larger than 2MB
        huge_payload = "a" * (2 * 1024 * 1024 + 100)

        response = client.post("/analyze-resume", content=huge_payload)
        assert response.status_code == 413
        assert "Request payload too large" in response.json()["detail"]


class TestI18nRoutes:
    @patch("src.routers.interview.get_llm_client")
    def test_generate_questions_with_language(self, mock_get_client):
        client = TestClient(app)
        mock_llm = AsyncMock()
        mock_llm.generate_structured_async.return_value = MagicMock(
            success=True,
            attempts=1,
            errors=[],
            data=InterviewQuestion(
                question="¿Háblame de ti?",
                question_type="behavioral",
                difficulty="medium",
                target_skill="comunicación",
                ideal_answer_keywords=["experiencia"]
            )
        )
        mock_get_client.return_value = mock_llm

        payload = {
            "resume_text": "Este es mi curriculum de prueba para el desarrollo de software.",
            "target_role": "Desarrollador de Software",
            "model": "llama3.2:3b",
            "language": "spanish"
        }
        response = client.post("/interview/generate-questions", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["data"]["question"] == "¿Háblame de ti?"

        # Verify language is passed into the prompt
        args, kwargs = mock_llm.generate_structured_async.call_args
        assert "spanish" in kwargs.get("prompt", "")

    @patch("src.routers.interview.get_llm_client")
    def test_submit_answer_with_language(self, mock_get_client):
        client = TestClient(app)
        mock_llm = AsyncMock()
        mock_llm.generate_structured_async.return_value = MagicMock(
            success=True,
            attempts=1,
            errors=[],
            data=InterviewFeedback(
                score=9.0,
                strengths=["Gut strukturiert"],
                weaknesses=["Nichts"],
                suggested_answer_framework="STAR",
                missed_keywords=[]
            )
        )
        mock_get_client.return_value = mock_llm

        payload = {
            "question": {
                "question": "Erzählen Sie mir über sich",
                "question_type": "behavioral",
                "difficulty": "easy",
                "target_skill": "communication",
                "ideal_answer_keywords": ["Erfahrung"]
            },
            "answer": "Ich habe fünf Jahre Erfahrung in der Softwareentwicklung.",
            "model": "llama3.2:3b",
            "language": "german"
        }
        response = client.post("/interview/submit-answer", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["data"]["score"] == 9.0

        # Verify language is passed into the prompt
        args, kwargs = mock_llm.generate_structured_async.call_args
        assert "german" in kwargs.get("prompt", "")

    def test_submit_answer_stream_german_fallback(self):
        client = TestClient(app)

        # We simulate a stream that outputs invalid JSON so the fallback is triggered
        async def mock_generator(*args, **kwargs):
            yield "coaching feedback"
            yield "===METRICS==="
            yield 'malformed json'

        mock_client = MagicMock()
        mock_client.stream_raw_async.return_value = mock_generator()

        with patch("src.routers.interview.get_llm_client", return_value=mock_client):
            payload = {
                "question": {
                    "question": "Tell me about yourself",
                    "question_type": "behavioral",
                    "difficulty": "easy",
                    "target_skill": "communication",
                    "ideal_answer_keywords": ["experience"]
                },
                "answer": "My name is John Doe.",
                "model": "llama3.2:3b",
                "language": "german"
            }
            response = client.post("/interview/submit-answer-stream", json=payload)
            assert response.status_code == 200

            content = response.content.decode("utf-8")
            assert "event: coaching" in content
            assert "event: metrics" in content
            # German metrics fallback strings must be in the output
            assert "Antwort erfolgreich übermittelt" in content
            assert "Detaillierte Metriken konnten aufgrund eines Parsing-Fehlers" in content
            assert "Bitte überprüfen Sie das Coaching-Feedback oben." in content

    def test_submit_answer_stream_spanish_fallback(self):
        client = TestClient(app)

        async def mock_generator(*args, **kwargs):
            yield "coaching feedback"
            yield "===METRICS==="
            yield 'malformed json'

        mock_client = MagicMock()
        mock_client.stream_raw_async.return_value = mock_generator()

        with patch("src.routers.interview.get_llm_client", return_value=mock_client):
            payload = {
                "question": {
                    "question": "Tell me about yourself",
                    "question_type": "behavioral",
                    "difficulty": "easy",
                    "target_skill": "communication",
                    "ideal_answer_keywords": ["experience"]
                },
                "answer": "My name is John Doe.",
                "model": "llama3.2:3b",
                "language": "spanish"
            }
            response = client.post("/interview/submit-answer-stream", json=payload)
            assert response.status_code == 200

            content = response.content.decode("utf-8")
            assert "event: coaching" in content
            assert "event: metrics" in content
            # Spanish metrics fallback strings
            assert "Respuesta enviada con éxito" in content
            assert "No se pudo generar el análisis de métricas" in content


def test_security_headers():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in response.headers
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert "Permissions-Policy" in response.headers


def test_csp_has_no_unsafe_inline():
    """Regression test for SECURITY.md F-6: the frontend has no inline
    <script>/<style> blocks or onclick=/style= HTML attributes, so CSP
    shouldn't need 'unsafe-inline' for either directive."""
    client = TestClient(app)
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in csp


def test_static_assets_have_no_inline_handlers_or_styles():
    """Regression test for SECURITY.md F-6: onclick=/onchange=/style= attributes
    were moved to addEventListener bindings (app.js) and CSS classes (styles.css)."""
    client = TestClient(app)
    html = client.get("/").text
    assert "onclick=" not in html
    assert "onchange=" not in html
    assert 'style="' not in html

    app_js = client.get("/static/app.js").text
    assert 'style="' not in app_js


@pytest.mark.asyncio
async def test_async_client_lifecycle():
    from src.assistant import close_async_client, get_async_client
    client1 = get_async_client()
    assert client1 is not None
    assert not client1.is_closed

    client2 = get_async_client()
    assert client1 is client2  # Shared instance

    await close_async_client()
    assert client1.is_closed


class TestSecurityFixes:
    """Regression tests for the audit findings: API-key leakage, model allow-listing,
    optional API-key auth, and rate-limiter path exemptions."""

    def test_sanitize_error_message_redacts_gemini_key(self):
        req = httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
            "?key=AIzaREALSECRETVALUE12345",
        )
        resp = httpx.Response(400, request=req, json={"error": "bad request"})
        try:
            resp.raise_for_status()
            raise AssertionError("expected raise_for_status to raise")
        except httpx.HTTPStatusError as e:
            sanitized = _sanitize_error_message(e)

        assert "AIzaREALSECRETVALUE12345" not in sanitized
        assert "key=[REDACTED]" in sanitized

    @patch("src.assistant.settings")
    @patch("httpx.Client.post")
    def test_gemini_request_never_puts_key_in_url(self, mock_post, mock_settings):
        """The API key must travel as a header, never as a `?key=` query param,
        so it can't end up in logs, proxies, or (via F-1) client-facing errors."""
        mock_settings.GEMINI_API_KEY = "dummy-key"
        mock_settings.LLM_MAX_RETRIES = 1
        mock_settings.LLM_TIMEOUT = 120.0

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        feedback_json = (
            '{"score": 5.0, "strengths": [], "weaknesses": [], '
            '"suggested_answer_framework": null, "missed_keywords": []}'
        )
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": feedback_json}]}}]
        }
        mock_post.return_value = mock_response

        client = LLMClient(model="gemini-1.5-flash")
        client.generate_structured(prompt="Test", schema=InterviewFeedback)

        called_url = mock_post.call_args.args[0]
        called_headers = mock_post.call_args.kwargs.get("headers", {})
        assert "key=" not in called_url
        assert called_headers.get("x-goog-api-key") == "dummy-key"

    @patch("src.assistant.settings")
    def test_unknown_gemini_model_rejected(self, mock_settings):
        mock_settings.GEMINI_API_KEY = "dummy-key"
        client = LLMClient(model="gemini-not-a-real-model")
        with pytest.raises(ValueError, match="Unsupported Gemini model"):
            client._query_gemini("prompt")

    def test_allowed_gemini_models_is_nonempty(self):
        assert "gemini-1.5-flash" in ALLOWED_GEMINI_MODELS


class TestApiKeyAuth:
    def test_endpoints_open_by_default(self):
        """API_KEY unset (default) — mutating endpoints stay open for local use."""
        client = TestClient(app)
        response = client.post("/api/rag/search", json={"query": "test"})
        assert response.status_code == 200

    def test_endpoint_rejects_missing_or_wrong_key_when_configured(self):
        with patch("src.auth.settings") as mock_settings:
            mock_settings.API_KEY = "shh-secret"
            client = TestClient(app)

            no_key = client.post("/api/rag/search", json={"query": "test"})
            assert no_key.status_code == 401

            wrong_key = client.post(
                "/api/rag/search", json={"query": "test"}, headers={"X-API-Key": "wrong"}
            )
            assert wrong_key.status_code == 401

            right_key = client.post(
                "/api/rag/search", json={"query": "test"}, headers={"X-API-Key": "shh-secret"}
            )
            assert right_key.status_code == 200


class TestRateLimitExemptions:
    def test_health_and_static_are_exempt(self):
        from src.app import _is_rate_limit_exempt
        assert _is_rate_limit_exempt("/health") is True
        assert _is_rate_limit_exempt("/docs") is True
        assert _is_rate_limit_exempt("/openapi.json") is True
        assert _is_rate_limit_exempt("/static/app.js") is True
        assert _is_rate_limit_exempt("/analyze-resume") is False


class TestErrorObservability:
    """Regression tests for SECURITY.md F-7: cache/RAG DB failures still degrade
    gracefully (miss/empty result) rather than crashing a request, but are now
    counted so a rising error rate is visible instead of silent."""

    def test_cache_records_error_count_on_failure(self):
        from src.cache import response_cache
        before = response_cache.error_count
        with patch.object(response_cache, "_get_conn", side_effect=RuntimeError("simulated DB failure")):
            result = response_cache.get("some prompt", "SomeSchema", "some-model")
        assert result is None
        assert response_cache.error_count == before + 1

    def test_rag_index_records_error_count_on_failure(self):
        from src.rag_index import rag_index
        before = rag_index.error_count
        with patch.object(rag_index, "_get_conn", side_effect=RuntimeError("simulated DB failure")):
            results = rag_index.search_documents("some query")
        assert results == []
        assert rag_index.error_count == before + 1

    def test_health_exposes_cache_and_rag_error_counts(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "llama3.2:3b"}]}

        mock_async_client = AsyncMock()
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        client = TestClient(app)
        with patch("src.assistant.get_async_client", return_value=mock_async_client):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["cache_errors"], int)
        assert isinstance(data["rag_errors"], int)


