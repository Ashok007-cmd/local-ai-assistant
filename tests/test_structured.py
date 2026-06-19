"""
Tests for structured output parsing, Pydantic validation, and retry logic.
Uses mock data and does NOT require a running Ollama instance.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.models import (
    BulletPointImprovement,
    InterviewQuestion,
    ResumeAnalysisResult,
    SkillAnalysis,
    SkillCategory,
    SkillGap,
    parse_llm_json_output,
)
from src.assistant import LLMClient, LLMResponse, default_resume_fallback

@pytest.fixture(autouse=True)
def clear_cache_before_each_test():
    from src.cache import response_cache
    response_cache.clear()

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestPydanticModels:
    """Verify Pydantic schema construction and validation rules."""

    def test_skill_gap_valid(self):
        sg = SkillGap(
            skill_name="Kubernetes",
            category=SkillCategory.TECHNICAL,
            importance="High",
        )
        assert sg.skill_name == "Kubernetes"
        assert sg.category == SkillCategory.TECHNICAL

    def test_skill_gap_invalid_category(self):
        with pytest.raises(ValidationError):
            SkillGap(
                skill_name="Kubernetes",
                category="invalid_category",
                importance="High",
            )

    def test_bullet_point_improvement(self):
        bpi = BulletPointImprovement(
            original="Worked on stuff",
            improved="Led development of microservices architecture serving 10k+ users",
            rationale="Adds metrics and leadership context",
        )
        assert bpi.original == "Worked on stuff"

    def test_skill_analysis_score_bounds(self):
        # Valid
        sa = SkillAnalysis(
            missing_skills=[],
            matching_score=75.5,
            bullet_point_improvements=[],
            strengths=["Team player"],
        )
        assert sa.matching_score == 75.5

        # Below 0
        with pytest.raises(ValidationError):
            SkillAnalysis(
                missing_skills=[],
                matching_score=-5.0,
                bullet_point_improvements=[],
                strengths=[],
            )

        # Above 100
        with pytest.raises(ValidationError):
            SkillAnalysis(
                missing_skills=[],
                matching_score=150.0,
                bullet_point_improvements=[],
                strengths=[],
            )

    def test_interview_question(self):
        iq = InterviewQuestion(
            question="Describe a time you led a difficult project",
            question_type="behavioral",
            difficulty="medium",
            target_skill="leadership",
            ideal_answer_keywords=["stakeholder", "deadline", "outcome"],
        )
        assert iq.difficulty == "medium"

    def test_resume_analysis_full(self):
        ra = ResumeAnalysisResult(
            candidate_name="Jane Doe",
            target_role="Senior Engineer",
            years_experience=6.0,
            skill_analysis=SkillAnalysis(
                missing_skills=[
                    SkillGap(
                        skill_name="Docker",
                        category=SkillCategory.TECHNICAL,
                        importance="Required for deployment",
                    )
                ],
                matching_score=82.0,
                bullet_point_improvements=[
                    BulletPointImprovement(
                        original="Did coding",
                        improved="Architected scalable microservices",
                        rationale="More impactful",
                    )
                ],
                strengths=["Python expertise", "System design"],
            ),
            format_issues=["Missing LinkedIn URL"],
            overall_recommendation="Strong candidate for senior role",
        )
        assert ra.candidate_name == "Jane Doe"
        assert ra.skill_analysis.matching_score == 82.0


# ---------------------------------------------------------------------------
# JSON parsing tests
# ---------------------------------------------------------------------------


class TestJsonParsing:
    """Verify robust JSON extraction from LLM responses."""

    def test_plain_json(self):
        raw = '{"name": "test", "score": 95}'
        result = parse_llm_json_output(raw)
        assert result["name"] == "test"

    def test_json_with_markdown_fence(self):
        raw = '```json\n{"name": "test", "score": 95}\n```'
        result = parse_llm_json_output(raw)
        assert result["score"] == 95

    def test_json_with_text_before_and_after(self):
        raw = 'Here is the analysis:\n\n```json\n{"name": "test"}\n```\n\nHope this helps!'
        result = parse_llm_json_output(raw)
        assert result["name"] == "test"

    def test_malformed_json(self):
        raw = '{"name": "test" missing comma}'
        with pytest.raises(json.JSONDecodeError):
            parse_llm_json_output(raw)

    def test_empty_string(self):
        with pytest.raises(json.JSONDecodeError):
            parse_llm_json_output("")

    def test_nested_json(self):
        raw = json.dumps({
            "skill_analysis": {
                "missing_skills": [{"skill_name": "K8s", "category": "technical", "importance": "High"}],
                "matching_score": 70.0,
                "bullet_point_improvements": [],
                "strengths": ["Python"],
            }
        })
        result = parse_llm_json_output(raw)
        assert result["skill_analysis"]["matching_score"] == 70.0


# ---------------------------------------------------------------------------
# Retry mechanism tests
# ---------------------------------------------------------------------------


class TestRetryMechanism:
    """Verify the auto-retry logic when the model returns invalid outputs."""

    @patch("src.assistant.LLMClient._query_ollama")
    def test_success_on_first_attempt(self, mock_query):
        """Valid JSON on first try should succeed immediately."""
        mock_query.return_value = json.dumps({
            "missing_skills": [],
            "matching_score": 85.0,
            "bullet_point_improvements": [],
            "strengths": ["Fast learner"],
        })

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured(
            prompt="Test",
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 1
        assert len(result.errors) == 0
        assert result.data.matching_score == 85.0
        assert mock_query.call_count == 1

    @patch("src.assistant.LLMClient._query_ollama")
    def test_retry_on_invalid_json(self, mock_query):
        """Invalid JSON should trigger retry with error feedback."""
        # First call returns invalid JSON, second call returns valid JSON
        mock_query.side_effect = [
            "Not valid json at all",
            json.dumps({
                "missing_skills": [],
                "matching_score": 90.0,
                "bullet_point_improvements": [],
                "strengths": ["Detail oriented"],
            }),
        ]

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured(
            prompt="Test",
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 2
        assert mock_query.call_count == 2

    @patch("src.assistant.LLMClient._query_ollama")
    def test_retry_on_validation_error(self, mock_query):
        """Pydantic validation failure should trigger retry."""
        mock_query.side_effect = [
            # Missing required field "strengths"
            json.dumps({
                "missing_skills": [],
                "matching_score": 90.0,
                "bullet_point_improvements": [],
                # "strengths" is missing
            }),
            json.dumps({
                "missing_skills": [],
                "matching_score": 90.0,
                "bullet_point_improvements": [],
                "strengths": ["Fixed"],
            }),
        ]

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured(
            prompt="Test",
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 2
        assert result.data.strengths == ["Fixed"]

    @patch("src.assistant.LLMClient._query_ollama")
    def test_exhaust_retries_with_fallback(self, mock_query):
        """After exhausting retries, should return fallback data."""
        mock_query.return_value = "Completely invalid output"

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured(
            prompt="Test",
            schema=SkillAnalysis,
            fallback_factory=lambda: SkillAnalysis(
                missing_skills=[],
                matching_score=0.0,
                bullet_point_improvements=[],
                strengths=["Fallback activated"],
            ),
        )

        assert result.success is False
        assert result.attempts == 3
        assert result.data is not None
        assert result.data.strengths == ["Fallback activated"]
        assert mock_query.call_count == 3

    @patch("src.assistant.LLMClient._query_ollama")
    def test_exhaust_retries_no_fallback(self, mock_query):
        """After exhausting retries with no fallback, data should be None."""
        mock_query.return_value = "Invalid"

        client = LLMClient(model="test-model", max_retries=2)
        result = client.generate_structured(
            prompt="Test",
            schema=SkillAnalysis,
        )

        assert result.success is False
        assert result.attempts == 2
        assert result.data is None

    @patch("src.assistant.LLMClient._query_ollama")
    def test_retry_feedback_includes_previous_output(self, mock_query):
        """The retry prompt should include the previous invalid output and error details."""
        responses = [
            '{"invalid": "structure"}',
            json.dumps({
                "missing_skills": [],
                "matching_score": 75.0,
                "bullet_point_improvements": [],
                "strengths": ["Persistent"],
            }),
        ]
        mock_query.side_effect = responses

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured(
            prompt="Analyze this resume",
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 2

        # Check that the second call included the first output
        second_call_prompt = mock_query.call_args_list[1][0][0]
        assert "invalid" in second_call_prompt or "Validate" in second_call_prompt

    @patch("src.assistant.LLMClient._query_ollama")
    def test_empty_response_retry(self, mock_query):
        """Empty response from model should trigger retry."""
        mock_query.side_effect = [
            "",
            json.dumps({
                "missing_skills": [],
                "matching_score": 80.0,
                "bullet_point_improvements": [],
                "strengths": ["Recovered from empty"],
            }),
        ]

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured(
            prompt="Test",
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 2

    @patch("src.assistant.LLMClient._query_ollama_chat")
    def test_chat_success_on_first_attempt(self, mock_query):
        mock_query.return_value = json.dumps({
            "missing_skills": [],
            "matching_score": 85.0,
            "bullet_point_improvements": [],
            "strengths": ["Fast learner"],
        })

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured_chat(
            messages=[{"role": "user", "content": "Test"}],
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 1
        assert len(result.errors) == 0
        assert result.data.matching_score == 85.0
        assert mock_query.call_count == 1

    @patch("src.assistant.LLMClient._query_ollama_chat")
    def test_chat_retry_on_invalid_json(self, mock_query):
        mock_query.side_effect = [
            "Not valid json at all",
            json.dumps({
                "missing_skills": [],
                "matching_score": 90.0,
                "bullet_point_improvements": [],
                "strengths": ["Detail oriented"],
            }),
        ]

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured_chat(
            messages=[{"role": "user", "content": "Test"}],
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 2
        assert mock_query.call_count == 2

    @patch("src.assistant.LLMClient._query_ollama_chat")
    def test_chat_retry_on_validation_error(self, mock_query):
        mock_query.side_effect = [
            json.dumps({
                "missing_skills": [],
                "matching_score": 90.0,
                "bullet_point_improvements": [],
            }),
            json.dumps({
                "missing_skills": [],
                "matching_score": 90.0,
                "bullet_point_improvements": [],
                "strengths": ["Fixed"],
            }),
        ]

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured_chat(
            messages=[{"role": "user", "content": "Test"}],
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 2
        assert result.data.strengths == ["Fixed"]

    @patch("src.assistant.LLMClient._query_ollama_chat")
    def test_chat_exhaust_retries_with_fallback(self, mock_query):
        mock_query.return_value = "Completely invalid output"

        client = LLMClient(model="test-model", max_retries=3)
        result = client.generate_structured_chat(
            messages=[{"role": "user", "content": "Test"}],
            schema=SkillAnalysis,
            fallback_factory=lambda: SkillAnalysis(
                missing_skills=[],
                matching_score=0.0,
                bullet_point_improvements=[],
                strengths=["Fallback activated"],
            ),
        )

        assert result.success is False
        assert result.attempts == 3
        assert result.data is not None
        assert result.data.strengths == ["Fallback activated"]
        assert mock_query.call_count == 3


    def test_default_resume_fallback(self):
        """Verify the default fallback factory returns valid data."""
        fallback = default_resume_fallback()
        assert isinstance(fallback, ResumeAnalysisResult)
        assert fallback.skill_analysis.matching_score == 0.0
        assert "error" in fallback.skill_analysis.missing_skills[0].skill_name.lower()


# ---------------------------------------------------------------------------
# Integration-style tests (mocked Ollama)
# ---------------------------------------------------------------------------


class TestLLMClientIntegration:
    """End-to-end tests with mocked HTTP calls."""

    @patch("src.assistant.LLMClient._query_ollama")
    def test_resume_analysis_flow(self, mock_query):
        """Full resume analysis flow with valid output."""
        mock_query.return_value = json.dumps({
            "candidate_name": "John Doe",
            "target_role": "Senior Engineer",
            "years_experience": 5.0,
            "skill_analysis": {
                "missing_skills": [
                    {
                        "skill_name": "Kubernetes",
                        "category": "technical",
                        "importance": "Required for cloud deployment",
                    }
                ],
                "matching_score": 72.0,
                "bullet_point_improvements": [
                    {
                        "original": "Worked on APIs",
                        "improved": "Designed RESTful APIs handling 10k RPM",
                        "rationale": "Quantifies impact",
                    }
                ],
                "strengths": ["Python", "System Design"],
            },
            "format_issues": ["No LinkedIn"],
            "overall_recommendation": "Strong technical foundation",
        })

        client = LLMClient(model="test-model")
        result = client.generate_structured(
            prompt="Analyze resume for Senior Engineer",
            schema=ResumeAnalysisResult,
            system_prompt="You are a resume reviewer.",
        )

        assert result.success is True
        assert result.data.candidate_name == "John Doe"
        assert result.data.skill_analysis.matching_score == 72.0
        assert len(result.data.skill_analysis.bullet_point_improvements) == 1

    @patch("src.assistant.LLMClient._query_ollama")
    def test_interview_question_flow(self, mock_query):
        """Interview question generation flow."""
        mock_query.return_value = json.dumps({
            "question": "Tell me about a challenging project",
            "question_type": "behavioral",
            "difficulty": "medium",
            "target_skill": "problem_solving",
            "ideal_answer_keywords": ["challenge", "solution", "outcome"],
        })

        client = LLMClient(model="test-model")
        result = client.generate_structured(
            prompt="Generate interview question",
            schema=InterviewQuestion,
        )

        assert result.success is True
        assert "challenging" in result.data.question
        assert result.data.question_type == "behavioral"


class TestFastAPIRoutes:
    """Verify endpoint routing, status codes, and mock integration in app.py."""

    def test_health_check_endpoint(self):
        from fastapi.testclient import TestClient
        from src.app import app
        from unittest.mock import AsyncMock

        client = TestClient(app)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "models": [{"name": "llama3.2:3b"}, {"name": "qwen2.5:3b"}]
        }

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)
        mock_async_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            assert "llama3.2:3b" in response.json()["models_available"]

    def test_benchmarks_endpoint_missing_file(self):
        from fastapi.testclient import TestClient
        from src.app import app

        client = TestClient(app)
        with patch("pathlib.Path.exists", return_value=False):
            response = client.get("/benchmarks")
            assert response.status_code == 200
            assert response.json()["success"] is False
            assert "not found" in response.json()["error"]

    def test_benchmarks_endpoint_valid(self):
        from fastapi.testclient import TestClient
        from src.app import app
        from pathlib import Path
        import tempfile

        client = TestClient(app)

        csv_data = (
            "model,prompt_name,prompt_length_chars,prompt_length_tokens_est,"
            "response_length_chars,response_length_tokens_est,time_to_first_token_s,"
            "total_generation_time_s,tokens_per_second,peak_vram_mb,peak_ram_mb,success,error,extra\n"
            "llama3.2:3b,resume_short_run1,100,25,200,50,0.02,1.0,50.0,0.0,0.0,True,,\n"
        )

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".csv", delete=False) as tmp:
            tmp.write(csv_data)
            tmp.flush()
            tmp_path = Path(tmp.name)

            with patch("src.app.Path") as mock_path:
                mock_instance = MagicMock()
                mock_instance.exists.return_value = True
                mock_instance.open.side_effect = lambda *args, **kwargs: open(tmp_path, *args, **kwargs)
                mock_path.return_value = mock_instance

                response = client.get("/benchmarks")
                assert response.status_code == 200
                res_data = response.json()
                assert res_data["success"] is True
                assert len(res_data["data"]) == 1
                assert res_data["data"][0]["model"] == "llama3.2:3b"
                assert res_data["data"][0]["tokens_per_second"] == 50.0
                assert res_data["data"][0]["success"] is True

            try:
                tmp_path.unlink()
            except OSError:
                pass

    def test_serve_index_html(self):
        from fastapi.testclient import TestClient
        from src.app import app
        
        client = TestClient(app)
        with patch("src.app.FileResponse") as mock_file_resp:
            mock_file_resp.return_value = MagicMock()
            response = client.get("/")
            assert response.status_code == 200


class TestAsyncOperations:
    """Verify asynchronous structured LLM querying."""

    @pytest.mark.asyncio
    @patch("src.assistant.LLMClient._query_ollama_async")
    async def test_async_success_on_first_attempt(self, mock_query):
        mock_query.return_value = json.dumps({
            "missing_skills": [],
            "matching_score": 95.0,
            "bullet_point_improvements": [],
            "strengths": ["Fast learner"],
        })

        client = LLMClient(model="test-model", max_retries=3)
        result = await client.generate_structured_async(
            prompt="Test async",
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 1
        assert result.data.matching_score == 95.0
        assert mock_query.call_count == 1

    @pytest.mark.asyncio
    @patch("src.assistant.LLMClient._query_ollama_chat_async")
    async def test_async_chat_success(self, mock_query):
        mock_query.return_value = json.dumps({
            "missing_skills": [],
            "matching_score": 88.0,
            "bullet_point_improvements": [],
            "strengths": ["Async works"],
        })

        client = LLMClient(model="test-model", max_retries=3)
        result = await client.generate_structured_chat_async(
            messages=[{"role": "user", "content": "Test async chat"}],
            schema=SkillAnalysis,
        )

        assert result.success is True
        assert result.attempts == 1
        assert result.data.matching_score == 88.0


class TestCacheOperations:
    """Verify database caching logic."""

    def test_cache_hit_and_miss(self):
        from src.cache import response_cache
        prompt = "Test cache hit and miss"
        schema_name = "SkillAnalysis"
        model = "test-model"
        data = {
            "missing_skills": [],
            "matching_score": 75.0,
            "bullet_point_improvements": [],
            "strengths": ["Cache is working"],
        }

        # Cache miss
        assert response_cache.get(prompt, schema_name, model) is None

        # Cache set
        response_cache.set(prompt, schema_name, model, data)

        # Cache hit
        cached = response_cache.get(prompt, schema_name, model)
        assert cached is not None
        assert cached["matching_score"] == 75.0
        assert cached["strengths"] == ["Cache is working"]

    @pytest.mark.asyncio
    @patch("src.assistant.LLMClient._query_ollama_async")
    async def test_async_client_uses_cache(self, mock_query):
        from src.cache import response_cache
        prompt = "Test async client uses cache"
        schema_name = "SkillAnalysis"
        model = "test-model"
        data = {
            "missing_skills": [],
            "matching_score": 82.0,
            "bullet_point_improvements": [],
            "strengths": ["Cached before call"],
        }

        # Manually cache it first
        response_cache.set(prompt, schema_name, model, data)

        # Query client
        client = LLMClient(model=model)
        result = await client.generate_structured_async(
            prompt=prompt,
            schema=SkillAnalysis,
        )

        # The client should return cached value and NOT query the LLM API
        assert result.success is True
        assert result.data.matching_score == 82.0
        assert mock_query.call_count == 0


class TestConcurrencyControl:
    """Verify semaphore limiting."""

    @pytest.mark.asyncio
    @patch("src.assistant.LLMClient._query_ollama_async")
    async def test_semaphore_serializes_requests(self, mock_query):
        import asyncio

        # Mock query that takes some time to resolve
        async def slow_query(*args, **kwargs):
            await asyncio.sleep(0.05)
            return json.dumps({
                "missing_skills": [],
                "matching_score": 99.0,
                "bullet_point_improvements": [],
                "strengths": ["Concurrent test"],
            })

        mock_query.side_effect = slow_query

        client = LLMClient(model="test-model")

        # Run two queries concurrently
        t1 = asyncio.create_task(client.generate_structured_async("prompt1", SkillAnalysis))
        t2 = asyncio.create_task(client.generate_structured_async("prompt2", SkillAnalysis))

        results = await asyncio.gather(t1, t2)
        assert results[0].success is True
        assert results[1].success is True
        assert mock_query.call_count == 2


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from src.app import app
    return TestClient(app)


def test_rag_search_no_documents(client):
    from src.rag_index import rag_index
    rag_index.clear()

    response = client.post("/api/rag/search", json={"query": "test query"})
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "test query"
    assert len(data["results"]) == 0
    assert "No documents available" in data["context"]


def test_rag_search_success(client):
    from src.rag_index import rag_index
    rag_index.clear()

    # Index document first
    doc = {
        "title": "Python 101",
        "content": "Python is a high-level programming language."
    }
    res_idx = client.post("/api/rag/index", json=doc)
    assert res_idx.status_code == 200

    # Search it
    response = client.post("/api/rag/search", json={"query": "python"})
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "python"
    assert len(data["results"]) > 0
    assert data["results"][0]["document"]["title"] == "Python 101"
    assert "Python is a high-level programming language." in data["context"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

