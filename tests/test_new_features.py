from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.app import app
from src.assistant import LLMClient, convert_to_gemini_schema, resolve_schema_refs
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


